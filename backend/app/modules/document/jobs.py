from datetime import UTC, datetime, timedelta
import hashlib
import logging
from uuid import UUID, uuid4

from fastapi import HTTPException
from pymongo import AsyncMongoClient, ReturnDocument

from app.core.config import Settings
from app.core.database import transaction
from app.modules.document.documents import (
    DocumentVersionDocument,
    ExportJobDocument,
    LetterDocument,
)
from app.modules.document.markdown_source import parse_markdown_source
from app.modules.document.pdf_renderer import MarkdownPDFRenderer
from app.modules.template.repositories import TemplateRepository
from app.modules.document.storage import ArtifactConflict, ArtifactStore
from app.modules.document.services import DocumentService
from app.modules.auth.documents import UserDocument
from app.modules.document.repositories import LetterRepository, VersionRepository
from app.modules.document.schemas import JobStatusResponse
from app.modules.integration.repositories import DriveArchiveJobRepository


LOGGER = logging.getLogger(__name__)
LEASE_DURATION = timedelta(minutes=5)
MAX_ATTEMPTS = 3
MAX_RETRY_DELAY_SECONDS = 60


class RenderWorker:
    def __init__(self, settings: Settings, client: AsyncMongoClient) -> None:
        self._settings = settings
        self._client = client
        self._worker_id = uuid4().hex
        self._store = ArtifactStore(settings.ARTIFACT_ROOT)
        self._renderer = MarkdownPDFRenderer(settings)
        self._templates = TemplateRepository()

    async def run_once(self) -> bool:
        job = await self._claim_job()
        if job is None:
            return False
        try:
            await self._render_job(job)
        except Exception as error:
            error_code = "ARTIFACT_CONFLICT" if isinstance(error, ArtifactConflict) else "RENDER_FAILED"
            terminal = (
                job.attempt >= MAX_ATTEMPTS
                or isinstance(error, (ValueError, FileNotFoundError))
                or isinstance(error, ArtifactConflict)
            )
            await self._record_failure(job, terminal, error_code)
            LOGGER.warning("Document export failed job_id=%s code=%s", job.id, error_code)
        return True

    async def _claim_job(self) -> ExportJobDocument | None:
        now = datetime.now(UTC)
        collection = ExportJobDocument.get_pymongo_collection()
        raw_job = await collection.find_one_and_update(
            {
                "$or": [
                    {"status": "queued"},
                    {
                        "status": "retry_wait",
                        "$or": [
                            {"next_attempt_at": None},
                            {"next_attempt_at": {"$lte": now}},
                        ],
                    },
                    {"status": "running", "lease_until": {"$lte": now}},
                ]
            },
            {
                "$set": {
                    "status": "running",
                    "lease_owner": self._worker_id,
                    "lease_until": now + LEASE_DURATION,
                    "next_attempt_at": None,
                    "error_code": None,
                    "updated_at": now,
                },
                "$inc": {"attempt": 1},
            },
            sort=[("created_at", 1)],
            return_document=ReturnDocument.AFTER,
        )
        return ExportJobDocument.model_validate(raw_job) if raw_job else None

    async def _render_job(self, job: ExportJobDocument) -> None:
        version = await DocumentVersionDocument.find_one(
            DocumentVersionDocument.id == job.version_id
        )
        if version is None:
            raise FileNotFoundError("Version snapshot is missing")
        document = await LetterDocument.find_one(
            LetterDocument.id == version.document_id
        )
        if document is None or document.identifier is None:
            raise ValueError("Only numbered versions can be exported")
        markdown_bytes = version.markdown_snapshot.encode("utf-8")
        markdown_hash = hashlib.sha256(markdown_bytes).hexdigest()
        if markdown_hash != version.md_hash or markdown_hash != version.source_hash:
            raise ValueError("Markdown snapshot integrity check failed")

        letter = parse_markdown_source(version.markdown_snapshot)
        if (
            letter.metadata.identifier != document.identifier
            or letter.metadata.template_revision != version.template_revision
        ):
            raise ValueError("Version metadata does not match its document")
        template = await self._templates.get_revision(version.template_revision)
        if template is None:
            raise FileNotFoundError("Template revision is missing")
        pdf_bytes = self._renderer.render(
            letter,
            template.settings,
            created_at=version.created_at,
        )
        pdf_hash = hashlib.sha256(pdf_bytes).hexdigest()
        self._store.write_immutable(
            document.id,
            version.id,
            "letter.md",
            markdown_bytes,
            version.md_hash,
        )
        self._store.write_immutable(
            document.id,
            version.id,
            "letter.pdf",
            pdf_bytes,
            pdf_hash,
        )
        await self._mark_succeeded(job, version, pdf_hash)

    async def _mark_succeeded(
        self,
        job: ExportJobDocument,
        version: DocumentVersionDocument,
        pdf_hash: str,
    ) -> None:
        now = datetime.now(UTC)
        async with transaction(self._client) as session:
            current_job = await ExportJobDocument.find_one(
                ExportJobDocument.id == job.id,
                session=session,
            )
            if (
                current_job is None
                or current_job.status != "running"
                or current_job.lease_owner != self._worker_id
                or current_job.lease_until is None
                or current_job.lease_until <= now
            ):
                return
            current_version = await DocumentVersionDocument.find_one(
                DocumentVersionDocument.id == version.id,
                session=session,
            )
            if current_version is None:
                raise FileNotFoundError("Version snapshot is missing")
            current_version.status = "ready"
            current_version.pdf_hash = pdf_hash
            await current_version.save(session=session)
            await DriveArchiveJobRepository().enqueue(
                current_version.document_id,
                current_version.id,
                current_version.created_by,
                session,
            )

            current_job.status = "succeeded"
            current_job.lease_owner = None
            current_job.lease_until = None
            current_job.error_code = None
            current_job.updated_at = now
            await current_job.save(session=session)

    async def _record_failure(
        self,
        job: ExportJobDocument,
        terminal: bool,
        error_code: str,
    ) -> None:
        now = datetime.now(UTC)
        async with transaction(self._client) as session:
            current_job = await ExportJobDocument.find_one(
                ExportJobDocument.id == job.id,
                session=session,
            )
            if (
                current_job is None
                or current_job.status != "running"
                or current_job.lease_owner != self._worker_id
            ):
                return
            current_job.status = "failed" if terminal else "retry_wait"
            current_job.error_code = error_code
            current_job.lease_owner = None
            current_job.lease_until = None
            if not terminal:
                delay = min(5 * (2 ** (current_job.attempt - 1)), MAX_RETRY_DELAY_SECONDS)
                current_job.next_attempt_at = now + timedelta(seconds=delay)
            current_job.updated_at = now
            await current_job.save(session=session)

            version = await DocumentVersionDocument.find_one(
                DocumentVersionDocument.id == current_job.version_id,
                session=session,
            )
            if version is not None and version.status not in {"ready", "archived"}:
                version.status = "render_failed"
                await version.save(session=session)


class ArtifactService:
    def __init__(self, settings: Settings) -> None:
        self._store = ArtifactStore(settings.ARTIFACT_ROOT)
        self._documents = LetterRepository()
        self._versions = VersionRepository()

    async def get_job_status(
        self,
        job_id: UUID,
        actor: UserDocument,
    ) -> JobStatusResponse:
        job = await ExportJobDocument.find_one(ExportJobDocument.id == job_id)
        if job is None:
            raise HTTPException(status_code=404, detail="NOT_FOUND")
        version = await DocumentVersionDocument.find_one(
            DocumentVersionDocument.id == job.version_id
        )
        document = await self._documents.get_by_id(version.document_id) if version else None
        if document is None:
            raise HTTPException(status_code=404, detail="NOT_FOUND")
        DocumentService._authorize(document, actor)
        return JobStatusResponse(
            job_id=job.id,
            status=job.status,
            attempt=job.attempt,
            error_code=job.error_code,
            updated_at=job.updated_at,
        )

    async def read_artifact(
        self,
        document_id: UUID,
        version_id: UUID,
        kind: str,
        actor: UserDocument,
    ) -> bytes:
        document = await self._documents.get_by_id(document_id)
        if document is None:
            raise HTTPException(status_code=404, detail="NOT_FOUND")
        DocumentService._authorize(document, actor)
        version = await self._versions.get_by_id(document_id, version_id)
        if version is None:
            raise HTTPException(status_code=404, detail="NOT_FOUND")
        if version.status not in {"ready", "archived", "sync_failed"}:
            raise HTTPException(status_code=409, detail="CONFLICT")
        filename, expected_hash, media_type = (
            ("letter.pdf", version.pdf_hash, "application/pdf")
            if kind == "pdf"
            else ("letter.md", version.md_hash, "text/markdown; charset=utf-8")
        )
        if expected_hash is None:
            raise HTTPException(status_code=503, detail="INTERNAL_ERROR")
        try:
            content = self._store.read_verified(
                document_id,
                version_id,
                filename,
                expected_hash,
            )
        except (OSError, ValueError) as error:
            raise HTTPException(status_code=503, detail="INTERNAL_ERROR") from error
        return content
