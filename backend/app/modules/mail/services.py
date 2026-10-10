import hashlib
import hmac
import json
from datetime import UTC, datetime, timedelta
from uuid import UUID

from fastapi import HTTPException
from pymongo.errors import DuplicateKeyError

from app.core.config import Settings
from app.core.database import transaction
from app.modules.auth.documents import UserDocument
from app.modules.document.documents import DocumentVersionDocument, LetterDocument
from app.modules.document.services import DocumentService
from app.modules.integration.crypto import EncryptionKeyUnavailable, encrypt_secret
from app.modules.integration.documents import (
    DriveArchiveMappingDocument,
    IntegrationConnectionDocument,
)
from app.modules.mail.documents import (
    MailDispatchJobDocument,
    MailDispatchPayloadDocument,
)
from app.modules.mail.schemas import MailDispatchRequest, MailJobResponse

MAIL_SCOPE = "https://www.googleapis.com/auth/gmail.send"
PAYLOAD_RETENTION = timedelta(hours=24)


class MailDispatchService:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    async def enqueue(
        self,
        payload: MailDispatchRequest,
        idempotency_key: str,
        actor: UserDocument,
        client,
    ) -> MailJobResponse:
        payload_values = payload.model_dump(mode="json")
        encoded_payload = json.dumps(
            payload_values, ensure_ascii=False, separators=(",", ":"), sort_keys=True
        ).encode("utf-8")
        fingerprint = hmac.new(
            self._settings.APP_RATE_LIMIT_KEY.get_secret_value().encode("utf-8"),
            encoded_payload,
            hashlib.sha256,
        ).hexdigest()
        collection = MailDispatchJobDocument.get_pymongo_collection()
        existing = await collection.find_one(
            {"user_id": actor.id, "kind": "mail_dispatch", "idempotency_key": idempotency_key}
        )
        if existing:
            return self._existing(existing, fingerprint)

        document = await LetterDocument.find_one(LetterDocument.id == payload.document_id)
        version = await DocumentVersionDocument.find_one(
            DocumentVersionDocument.id == payload.version_id,
            DocumentVersionDocument.document_id == payload.document_id,
        )
        if document is None or version is None:
            raise HTTPException(status_code=404, detail="NOT_FOUND")
        DocumentService._authorize(document, actor)
        mapping = await DriveArchiveMappingDocument.find_one(
            DriveArchiveMappingDocument.version_id == version.id,
            DriveArchiveMappingDocument.status == "archived",
        )
        if (
            document.finalized_version_id != version.id
            or version.finalized_at is None
            or version.status != "archived"
            or version.pdf_hash is None
            or mapping is None
            or mapping.document_id != document.id
            or mapping.pdf_hash != version.pdf_hash
            or not mapping.pdf_file_id
        ):
            raise HTTPException(status_code=409, detail="VERSION_NOT_SENDABLE")

        connection = await IntegrationConnectionDocument.find_one(
            IntegrationConnectionDocument.id == payload.connection_id,
            IntegrationConnectionDocument.kind == "gmail",
            IntegrationConnectionDocument.status == "active",
        )
        if connection is None:
            raise HTTPException(status_code=404, detail="NOT_FOUND")
        if connection.mode == "personal":
            if connection.owner_user_id != actor.id:
                raise HTTPException(status_code=404, detail="NOT_FOUND")
        elif connection.mode == "institutional":
            if actor.role not in {"admin", "user"} or connection.owner_user_id is not None:
                raise HTTPException(status_code=404, detail="NOT_FOUND")
        else:
            raise HTTPException(status_code=404, detail="NOT_FOUND")
        if MAIL_SCOPE not in connection.scopes:
            raise HTTPException(status_code=403, detail="GOOGLE_SCOPE_MISMATCH")

        now = datetime.now(UTC)
        job = MailDispatchJobDocument(
            document_id=document.id,
            version_id=version.id,
            connection_id=connection.id,
            user_id=actor.id,
            idempotency_key=idempotency_key,
            request_fingerprint=fingerprint,
            pdf_hash=version.pdf_hash,
            created_at=now,
            updated_at=now,
        )
        aad = self._payload_aad(job.id, actor.id)
        try:
            encrypted = encrypt_secret(encoded_payload, aad, self._settings)
        except EncryptionKeyUnavailable as error:
            raise HTTPException(status_code=503, detail="INTEGRATION_KEY_UNAVAILABLE") from error
        dispatch_payload = MailDispatchPayloadDocument(
            job_id=job.id,
            user_id=actor.id,
            encrypted_payload=encrypted,
            expires_at=now + PAYLOAD_RETENTION,
            created_at=now,
        )
        try:
            async with transaction(client) as session:
                current_actor = await UserDocument.find_one(
                    UserDocument.id == actor.id,
                    UserDocument.active == True,
                    session=session,
                )
                if current_actor is None:
                    raise HTTPException(status_code=403, detail="FORBIDDEN")
                await job.insert(session=session)
                await dispatch_payload.insert(session=session)
        except DuplicateKeyError:
            existing = await collection.find_one(
                {"user_id": actor.id, "kind": "mail_dispatch", "idempotency_key": idempotency_key}
            )
            if existing is None:
                raise HTTPException(status_code=409, detail="CONFLICT")
            return self._existing(existing, fingerprint)
        return self._response(job)

    async def get_job(self, job_id: UUID, actor: UserDocument) -> MailJobResponse:
        job = await MailDispatchJobDocument.find_one(
            MailDispatchJobDocument.id == job_id,
            MailDispatchJobDocument.user_id == actor.id,
        )
        if job is None:
            raise HTTPException(status_code=404, detail="NOT_FOUND")
        return self._response(job)

    @classmethod
    def _existing(cls, raw: dict, fingerprint: str) -> MailJobResponse:
        job = MailDispatchJobDocument.model_validate(raw)
        if not hmac.compare_digest(job.request_fingerprint, fingerprint):
            raise HTTPException(status_code=409, detail="IDEMPOTENCY_KEY_REUSED")
        return cls._response(job)

    @staticmethod
    def _response(job: MailDispatchJobDocument) -> MailJobResponse:
        return MailJobResponse(
            job_id=job.id,
            status=job.status,
            attempt=job.attempt,
            error_code=job.error_code,
            updated_at=job.updated_at,
        )

    @staticmethod
    def _payload_aad(job_id: UUID, user_id: UUID) -> bytes:
        return f"mail-dispatch-payload:v1:{job_id}:{user_id}".encode("ascii")
