import asyncio
from datetime import UTC, datetime, timedelta
import hashlib
import hmac
import secrets
from io import BytesIO
from uuid import UUID

from fastapi import HTTPException
from PIL import Image
from pymongo import AsyncMongoClient, ReturnDocument
from pymongo.errors import PyMongoError

from app.core.config import Settings
from app.core.database import transaction
from app.modules.auth.documents import (
    SignatureEnvelopeDocument,
    UserDocument,
)
from app.modules.auth.passwords import verify_password
from app.modules.auth.rate_limit import LoginRateLimiter
from app.modules.document.documents import (
    DocumentVersionDocument,
    LetterDocument,
)
from app.modules.document.markdown_source import parse_markdown_source
from app.modules.document.pdf_renderer import (
    MarkdownPDFRenderer,
    RenderLimitExceeded,
    SignatureDoesNotFit,
)
from app.modules.document.storage import ArtifactStore
from app.modules.signature.documents import SigningAuthorizationDocument
from app.modules.signature.schemas import (
    SignedVersionResponse,
    SigningAuthorizationRequest,
    SigningAuthorizationResponse,
)
from app.modules.template.repositories import TemplateRepository


SIGNING_AUTHORIZATION_SECONDS = 60
MAX_SIGNATURE_BYTES = 2 * 1024 * 1024
MAX_SIGNED_RENDER_SECONDS = 20


def hash_signing_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


class SignatureRenderService:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._renderer = MarkdownPDFRenderer(settings)
        self._store = ArtifactStore(settings.ARTIFACT_ROOT)
        self._templates = TemplateRepository()
        self._rate_limiter = LoginRateLimiter(settings)

    async def authorize(
        self,
        payload: SigningAuthorizationRequest,
        actor: UserDocument,
        network_address: str,
    ) -> SigningAuthorizationResponse:
        await self._rate_limiter.ensure_allowed(actor.normalized_email, network_address)
        if not verify_password(actor.password_hash, payload.password):
            await self._rate_limiter.record_failure(actor.normalized_email, network_address)
            raise HTTPException(status_code=401, detail="UNAUTHENTICATED")

        now = datetime.now(UTC)
        document = await LetterDocument.find_one(LetterDocument.id == payload.document_id)
        if document is None or not self._is_signer(document, actor):
            raise HTTPException(status_code=404, detail="NOT_FOUND")
        version = await DocumentVersionDocument.find_one(
            DocumentVersionDocument.document_id == document.id,
            DocumentVersionDocument.id == payload.version_id,
        )
        envelope = await SignatureEnvelopeDocument.find_one(
            SignatureEnvelopeDocument.user_id == actor.id
        )
        if envelope is None:
            raise HTTPException(status_code=409, detail="SIGNATURE_LOCKED")
        if (
            version is None
            or version.status != "ready"
            or document.current_version != version.id
            or document.draft_revision < 1
            or not hmac.compare_digest(document.source_hash, payload.source_hash)
            or not hmac.compare_digest(version.source_hash, payload.source_hash)
        ):
            raise HTTPException(status_code=409, detail="CONFLICT")

        token = secrets.token_urlsafe(32)
        expires_at = now + timedelta(seconds=SIGNING_AUTHORIZATION_SECONDS)
        authorization = SigningAuthorizationDocument(
            token_hash=hash_signing_token(token),
            user_id=actor.id,
            credential_revision=actor.credential_revision,
            document_id=document.id,
            version_id=version.id,
            source_hash=version.source_hash,
            draft_revision=document.draft_revision,
            expires_at=expires_at,
        )
        await authorization.insert()
        return SigningAuthorizationResponse(
            authorization_token=token,
            expires_at=expires_at,
        )

    async def render_signed(
        self,
        document_id: UUID,
        version_id: UUID,
        token: str,
        signature_png: bytes,
        content_type: str,
        actor: UserDocument,
        client: AsyncMongoClient,
    ) -> SignedVersionResponse:
        if content_type != "image/png" or not signature_png:
            raise HTTPException(status_code=415, detail="VALIDATION_ERROR")
        if len(signature_png) > MAX_SIGNATURE_BYTES:
            raise HTTPException(status_code=413, detail="VALIDATION_ERROR")
        self._validate_png(signature_png)

        now = datetime.now(UTC)
        token_hash = hash_signing_token(token)
        try:
            async with transaction(client) as session:
                authorizations = SigningAuthorizationDocument.get_pymongo_collection()
                authorization = await authorizations.find_one_and_update(
                    {
                        "token_hash": token_hash,
                        "user_id": actor.id,
                        "document_id": document_id,
                        "version_id": version_id,
                        "expires_at": {"$gt": now},
                        "consumed_at": None,
                    },
                    {"$set": {"consumed_at": now}},
                    return_document=ReturnDocument.BEFORE,
                    session=session,
                )
                if authorization is None:
                    raise HTTPException(status_code=409, detail="SIGNATURE_LOCKED")

                current_actor = await UserDocument.find_one(
                    UserDocument.id == actor.id,
                    UserDocument.active == True,
                    UserDocument.credential_revision
                    == authorization["credential_revision"],
                    session=session,
                )

                document = await LetterDocument.find_one(
                    LetterDocument.id == document_id,
                    session=session,
                )
                version = await DocumentVersionDocument.find_one(
                    DocumentVersionDocument.document_id == document_id,
                    DocumentVersionDocument.id == version_id,
                    session=session,
                )
                if (
                    document is None
                    or current_actor is None
                    or not self._is_signer(document, actor)
                    or version is None
                    or version.status != "ready"
                    or document.current_version != version.id
                    or document.draft_revision != authorization["draft_revision"]
                    or not hmac.compare_digest(
                        document.source_hash, authorization["source_hash"]
                    )
                    or not hmac.compare_digest(
                        version.source_hash, authorization["source_hash"]
                    )
                ):
                    raise HTTPException(status_code=409, detail="CONFLICT")

                template = await self._templates.get_revision(version.template_revision)
                if template is None:
                    raise HTTPException(status_code=503, detail="INTERNAL_ERROR")
                letter = parse_markdown_source(version.markdown_snapshot)
                try:
                    pdf_bytes = await asyncio.wait_for(
                        asyncio.to_thread(
                            self._renderer.render,
                            letter,
                            template.settings,
                            version.created_at,
                            signature_png,
                        ),
                        timeout=MAX_SIGNED_RENDER_SECONDS,
                    )
                except SignatureDoesNotFit as error:
                    raise HTTPException(
                        status_code=422, detail="SIGNATURE_DOES_NOT_FIT"
                    ) from error
                except RenderLimitExceeded as error:
                    raise HTTPException(status_code=413, detail="VALIDATION_ERROR") from error
                except TimeoutError as error:
                    raise HTTPException(status_code=503, detail="RENDER_TIMEOUT") from error
                finally:
                    del signature_png

                pdf_hash = hashlib.sha256(pdf_bytes).hexdigest()
                markdown_bytes = version.markdown_snapshot.encode("utf-8")
                signed_version = DocumentVersionDocument(
                    document_id=document.id,
                    version_number=document.latest_version_number + 1,
                    metadata_snapshot=version.metadata_snapshot,
                    body_snapshot=version.body_snapshot,
                    markdown_snapshot=version.markdown_snapshot,
                    template_revision=version.template_revision,
                    source_hash=version.source_hash,
                    md_hash=version.md_hash,
                    pdf_hash=pdf_hash,
                    status="ready",
                    finalized_at=now,
                    signature_owner_id=actor.id,
                    created_by=actor.id,
                    created_at=now,
                )
                self._store.write_immutable(
                    document.id,
                    signed_version.id,
                    "letter.md",
                    markdown_bytes,
                    signed_version.md_hash,
                )
                self._store.write_immutable(
                    document.id,
                    signed_version.id,
                    "letter.pdf",
                    pdf_bytes,
                    pdf_hash,
                )
                await signed_version.insert(session=session)
                document.latest_version_number = signed_version.version_number
                document.current_version = signed_version.id
                document.finalized_version_id = signed_version.id
                document.updated_at = now
                await document.save(session=session)
                return SignedVersionResponse(
                    document_id=document.id,
                    version_id=signed_version.id,
                    version_number=signed_version.version_number,
                    source_hash=signed_version.source_hash,
                    pdf_hash=pdf_hash,
                    finalized_at=now,
                )
        except HTTPException:
            raise
        except PyMongoError as error:
            if error.code == 112 or error.has_error_label("TransientTransactionError"):
                raise HTTPException(status_code=409, detail="CONFLICT") from error
            raise

    @staticmethod
    def _is_signer(document: LetterDocument, actor: UserDocument) -> bool:
        return document.owner_id == actor.id or actor.id in document.participant_ids

    @staticmethod
    def _validate_png(content: bytes) -> None:
        try:
            with Image.open(BytesIO(content)) as image:
                if image.format != "PNG" or getattr(image, "n_frames", 1) != 1:
                    raise ValueError("PNG required")
                width, height = image.size
                if width <= 0 or height <= 0 or width * height > 4_000_000:
                    raise ValueError("Image dimensions exceed limit")
                image.verify()
        except Exception as error:
            raise HTTPException(status_code=422, detail="VALIDATION_ERROR") from error
