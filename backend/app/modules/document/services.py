import asyncio
from datetime import UTC, datetime
import hashlib
import hmac
from zoneinfo import ZoneInfo
from uuid import UUID

import yaml
from fastapi import HTTPException
from pymongo import AsyncMongoClient
from pymongo.errors import DuplicateKeyError, PyMongoError

from app.core.config import Settings
from app.core.database import transaction
from app.modules.auth.documents import UserDocument
from app.modules.document.documents import (
    DocumentVersionDocument,
    ExportJobDocument,
    LetterDocument,
)
from app.modules.document.markdown_source import parse_markdown_source
from app.modules.document.pdf_renderer import MarkdownPDFRenderer
from app.modules.document.repositories import (
    ExportJobRepository,
    LetterCounterRepository,
    LetterRepository,
    VersionRepository,
)
from app.modules.document.schemas import (
    DocumentCreate,
    DocumentListItem,
    DocumentPage,
    DocumentSave,
    DocumentSaveResponse,
    DocumentSummary,
    DocumentVersionDetail,
    DocumentVersionSummary,
    LetterFields,
    LetterMetadata,
)
from app.modules.template.repositories import TemplateRepository
from app.modules.template.schemas import TemplateSettings


LETTER_ORGANIZATION = "SCESI"
LETTER_TIMEZONE = ZoneInfo("America/La_Paz")
MAX_SAVE_RETRIES = 5


class DocumentRenderService:
    def __init__(self, settings: Settings) -> None:
        self._renderer = MarkdownPDFRenderer(settings)

    def preview(
        self,
        markdown: str,
        template: TemplateSettings,
    ) -> tuple[bytes, str]:
        letter = parse_markdown_source(markdown)
        content = self._renderer.render(letter, template)
        return content, hashlib.sha256(content).hexdigest()


def build_markdown(metadata: LetterMetadata, body: str) -> str:
    front_matter = yaml.safe_dump(
        metadata.model_dump(mode="json", exclude_none=True),
        allow_unicode=True,
        sort_keys=True,
        default_flow_style=False,
    )
    return f"---\n{front_matter}---\n\n{body.strip()}\n"


def calculate_source_hash(metadata: LetterMetadata, body: str) -> tuple[str, str]:
    markdown = build_markdown(metadata, body)
    source_hash = hashlib.sha256(markdown.encode("utf-8")).hexdigest()
    return markdown, source_hash


class DocumentService:
    def __init__(self) -> None:
        self._documents = LetterRepository()
        self._versions = VersionRepository()
        self._counters = LetterCounterRepository()
        self._jobs = ExportJobRepository()
        self._templates = TemplateRepository()

    async def create_draft(
        self,
        payload: DocumentCreate,
        actor: UserDocument,
    ) -> DocumentSummary:
        template = await self._templates.get_active()
        if template is None:
            raise HTTPException(status_code=503, detail="INTERNAL_ERROR")
        if not payload.body.strip():
            raise HTTPException(status_code=422, detail="VALIDATION_ERROR")
        metadata = self._metadata(payload.metadata, None, template.revision)
        _, source_hash = calculate_source_hash(metadata, payload.body)
        document = LetterDocument(
            owner_id=actor.id,
            participant_ids=[],
            document_type=metadata.document_type,
            metadata=metadata,
            body=payload.body.strip(),
            source_hash=source_hash,
        )
        await self._documents.insert(document)
        return self._document_summary(document)

    async def list_documents(
        self,
        actor: UserDocument,
        page: int,
        page_size: int,
    ) -> DocumentPage:
        documents, total = await self._documents.list_page(
            actor.id, actor.role == "admin", page, page_size
        )
        return DocumentPage(
            items=[
                DocumentListItem(
                    id=document.id,
                    owner_id=document.owner_id,
                    document_type=document.document_type,
                    identifier=document.identifier,
                    topic=document.metadata.topic,
                    recipient_name=(
                        document.metadata.recipient.name
                        if document.metadata.recipient is not None
                        else None
                    ),
                    current_version=document.current_version,
                    draft_revision=document.draft_revision,
                    updated_at=document.updated_at,
                )
                for document in documents
            ],
            page=page,
            page_size=page_size,
            total=total,
        )

    async def get_document(
        self,
        document_id: UUID,
        actor: UserDocument,
    ) -> DocumentSummary:
        document = await self._documents.get_by_id(document_id)
        if document is None:
            raise HTTPException(status_code=404, detail="NOT_FOUND")
        self._authorize(document, actor)
        return self._document_summary(document)

    async def get_versions(
        self,
        document_id: UUID,
        actor: UserDocument,
    ) -> list[DocumentVersionSummary]:
        document = await self._documents.get_by_id(document_id)
        if document is None:
            raise HTTPException(status_code=404, detail="NOT_FOUND")
        self._authorize(document, actor)
        versions = await self._versions.list_for_document(document_id)
        return [self._version_summary(version) for version in versions]

    async def get_version(
        self,
        document_id: UUID,
        version_id: UUID,
        actor: UserDocument,
    ) -> DocumentVersionDetail:
        document = await self._documents.get_by_id(document_id)
        if document is None:
            raise HTTPException(status_code=404, detail="NOT_FOUND")
        self._authorize(document, actor)
        version = await self._versions.get_by_id(document_id, version_id)
        if version is None:
            raise HTTPException(status_code=404, detail="NOT_FOUND")
        return DocumentVersionDetail(
            **self._version_summary(version).model_dump(),
            metadata_snapshot=version.metadata_snapshot,
            body_snapshot=version.body_snapshot,
            markdown_snapshot=version.markdown_snapshot,
            md_hash=version.md_hash,
            pdf_hash=version.pdf_hash,
            finalized_at=version.finalized_at,
        )

    async def save(
        self,
        document_id: UUID,
        payload: DocumentSave,
        actor: UserDocument,
        client: AsyncMongoClient,
    ) -> DocumentSaveResponse:
        for attempt in range(MAX_SAVE_RETRIES):
            try:
                return await self._save_once(document_id, payload, actor, client)
            except (DuplicateKeyError, PyMongoError) as error:
                retryable = error.code == 11000 or error.code == 112 or error.has_error_label(
                    "TransientTransactionError"
                )
                if not retryable or attempt == MAX_SAVE_RETRIES - 1:
                    if retryable:
                        raise HTTPException(status_code=409, detail="CONFLICT") from error
                    raise
                await asyncio.sleep(0.01 * (attempt + 1))
        raise HTTPException(status_code=409, detail="CONFLICT")

    async def checkpoint_collaborative(
        self,
        document_id: UUID,
        metadata: LetterMetadata,
        body: str,
        actor: UserDocument,
        client: AsyncMongoClient,
    ) -> None:
        document = await self._documents.get_by_id(document_id)
        if document is None:
            raise HTTPException(status_code=404, detail="NOT_FOUND")
        self._authorize(document, actor)
        if not body.strip():
            raise HTTPException(status_code=422, detail="VALIDATION_ERROR")
        fields = LetterFields.model_validate(
            metadata.model_dump(mode="python", exclude={"identifier", "template_revision"})
        )
        canonical_metadata = self._metadata(
            fields,
            document.identifier,
            document.metadata.template_revision or 1,
        )
        _, source_hash = calculate_source_hash(canonical_metadata, body.strip())
        if source_hash == document.source_hash:
            return

        if document.identifier is not None:
            await self.save(
                document_id,
                DocumentSave(
                    expected_revision=document.draft_revision,
                    expected_source_hash=document.source_hash,
                    metadata=fields,
                    body=body.strip(),
                ),
                actor,
                client,
            )
            return

        async with transaction(client) as session:
            current = await self._documents.get_by_id(document_id, session=session)
            if current is None:
                raise HTTPException(status_code=404, detail="NOT_FOUND")
            self._authorize(current, actor)
            if (
                current.draft_revision != document.draft_revision
                or not hmac.compare_digest(current.source_hash, document.source_hash)
            ):
                raise HTTPException(status_code=409, detail="CONFLICT")
            current.document_type = canonical_metadata.document_type
            current.metadata = canonical_metadata
            current.body = body.strip()
            current.source_hash = source_hash
            current.draft_revision += 1
            current.updated_at = datetime.now(UTC)
            await self._documents.save(current, session)

    async def _save_once(
        self,
        document_id,
        payload: DocumentSave,
        actor: UserDocument,
        client: AsyncMongoClient,
    ) -> DocumentSaveResponse:
        now = datetime.now(UTC)
        async with transaction(client) as session:
            document = await self._documents.get_by_id(document_id, session=session)
            if document is None:
                raise HTTPException(status_code=404, detail="NOT_FOUND")
            self._authorize(document, actor)
            if (
                document.current_version is not None
                and self._same_editable_source(
                    document,
                    payload.metadata,
                    payload.body,
                )
            ):
                current_version = await self._versions.get_by_id(
                    document.id,
                    document.current_version,
                    session=session,
                )
                if current_version is None:
                    raise HTTPException(status_code=503, detail="INTERNAL_ERROR")
                return DocumentSaveResponse(
                    document=self._document_summary(document),
                    version=self._version_summary(current_version),
                    changed=False,
                )
            if document.draft_revision != payload.expected_revision:
                raise HTTPException(status_code=409, detail="CONFLICT")
            if not hmac.compare_digest(document.source_hash, payload.expected_source_hash):
                raise HTTPException(status_code=409, detail="CONFLICT")
            if not payload.body.strip():
                raise HTTPException(status_code=422, detail="VALIDATION_ERROR")
            if document.identifier and payload.metadata.document_type != document.document_type:
                raise HTTPException(status_code=409, detail="CONFLICT")

            identifier = document.identifier
            identifier_year = document.identifier_year
            if identifier is None:
                identifier_year = now.astimezone(LETTER_TIMEZONE).year
                sequence = await self._counters.allocate(
                    LETTER_ORGANIZATION,
                    payload.metadata.document_type,
                    identifier_year,
                    session,
                )
                identifier = (
                    f"{payload.metadata.document_type}-{LETTER_ORGANIZATION}-"
                    f"{identifier_year}-{sequence:03d}"
                )

            metadata = self._metadata(
                payload.metadata,
                identifier,
                document.metadata.template_revision,
            )
            markdown, source_hash = calculate_source_hash(metadata, payload.body)
            if document.current_version is not None and source_hash == document.source_hash:
                current_version = await self._versions.get_by_id(
                    document.id,
                    document.current_version,
                    session=session,
                )
                if current_version is None:
                    raise HTTPException(status_code=503, detail="INTERNAL_ERROR")
                return DocumentSaveResponse(
                    document=self._document_summary(document),
                    version=self._version_summary(current_version),
                    changed=False,
                )

            version_number = document.latest_version_number + 1
            version = DocumentVersionDocument(
                document_id=document.id,
                version_number=version_number,
                metadata_snapshot=metadata,
                body_snapshot=payload.body.strip(),
                markdown_snapshot=markdown,
                template_revision=metadata.template_revision,
                source_hash=source_hash,
                md_hash=hashlib.sha256(markdown.encode("utf-8")).hexdigest(),
                created_by=actor.id,
                created_at=now,
            )
            await self._versions.insert(version, session)
            job = ExportJobDocument(
                version_id=version.id,
                user_id=actor.id,
                idempotency_key=f"render:{version.id}",
                created_at=now,
            )
            await self._jobs.insert(job, session)

            document.document_type = metadata.document_type
            document.identifier = identifier
            document.identifier_year = identifier_year
            document.metadata = metadata
            document.body = payload.body.strip()
            document.source_hash = source_hash
            document.current_version = version.id
            document.latest_version_number = version_number
            document.draft_revision += 1
            document.updated_at = now
            await self._documents.save(document, session)
            return DocumentSaveResponse(
                document=self._document_summary(document),
                version=self._version_summary(version),
                changed=True,
            )

    @staticmethod
    def _metadata(
        fields: LetterFields,
        identifier: str | None,
        template_revision: int,
    ) -> LetterMetadata:
        return LetterMetadata(
            **fields.model_dump(mode="python", exclude_none=True),
            identifier=identifier,
            template_revision=template_revision,
        )

    @staticmethod
    def _same_editable_source(
        document: LetterDocument,
        fields: LetterFields,
        body: str,
    ) -> bool:
        current_fields = LetterFields(
            document_type=document.metadata.document_type,
            date=document.metadata.date,
            reference=document.metadata.reference,
            salutation=document.metadata.salutation,
            recipient=document.metadata.recipient,
            recipient_contact_id=document.metadata.recipient_contact_id,
            sender=document.metadata.sender,
            topic=document.metadata.topic,
            signoff=document.metadata.signoff,
            event_id=document.metadata.event_id,
        )
        return (
            current_fields.model_dump(mode="json", exclude_none=True)
            == fields.model_dump(mode="json", exclude_none=True)
            and document.body == body.strip()
        )

    @staticmethod
    def _document_summary(document: LetterDocument) -> DocumentSummary:
        return DocumentSummary(
            id=document.id,
            owner_id=document.owner_id,
            participant_ids=document.participant_ids,
            metadata=document.metadata,
            body=document.body,
            draft_revision=document.draft_revision,
            source_hash=document.source_hash,
            current_version=document.current_version,
            identifier_year=document.identifier_year,
            created_at=document.created_at,
        )

    @staticmethod
    def _version_summary(version: DocumentVersionDocument) -> DocumentVersionSummary:
        return DocumentVersionSummary(
            id=version.id,
            document_id=version.document_id,
            version_number=version.version_number,
            source_hash=version.source_hash,
            template_revision=version.template_revision,
            status=version.status,
            created_by=version.created_by,
            created_at=version.created_at,
        )

    @staticmethod
    def _authorize(document: LetterDocument, actor: UserDocument) -> None:
        if (
            actor.role != "admin"
            and document.owner_id != actor.id
            and actor.id not in document.participant_ids
        ):
            raise HTTPException(status_code=404, detail="NOT_FOUND")
