from datetime import UTC, datetime
from typing import Literal
from uuid import UUID, uuid4

from beanie import Document
from pydantic import ConfigDict, Field
from pymongo import ASCENDING, IndexModel

from app.modules.document.schemas import LetterMetadata


class StrictDocument(Document):
    model_config = ConfigDict(extra="forbid")


class LetterDocument(StrictDocument):
    id: UUID = Field(default_factory=uuid4)
    owner_id: UUID
    participant_ids: list[UUID] = Field(default_factory=list)
    document_type: str
    identifier: str | None = None
    identifier_year: int | None = None
    metadata: LetterMetadata
    body: str = Field(min_length=1, max_length=100_000)
    draft_revision: int = Field(default=1, ge=1)
    source_hash: str = Field(min_length=64, max_length=64)
    current_version: UUID | None = None
    latest_version_number: int = Field(default=0, ge=0)
    finalized_version_id: UUID | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    class Settings:
        name = "documents"
        indexes = [
            IndexModel([("owner_id", ASCENDING), ("updated_at", -1)], name="ix_documents_owner_updated"),
            IndexModel([("participant_ids", ASCENDING), ("updated_at", -1)], name="ix_documents_participants_updated"),
            IndexModel(
                [("identifier", ASCENDING)],
                unique=True,
                partialFilterExpression={"identifier": {"$type": "string"}},
                name="uq_documents_identifier",
            ),
        ]


class DocumentVersionDocument(StrictDocument):
    id: UUID = Field(default_factory=uuid4)
    document_id: UUID
    version_number: int = Field(ge=1)
    metadata_snapshot: LetterMetadata
    body_snapshot: str = Field(min_length=1, max_length=100_000)
    markdown_snapshot: str = Field(min_length=1, max_length=120_000)
    template_revision: int = Field(ge=1)
    source_hash: str = Field(min_length=64, max_length=64)
    md_hash: str = Field(min_length=64, max_length=64)
    pdf_hash: str | None = None
    status: Literal[
        "queued",
        "rendering",
        "ready",
        "archived",
        "render_failed",
        "sync_failed",
    ] = "queued"
    finalized_at: datetime | None = None
    created_by: UUID
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    class Settings:
        name = "document_versions"
        indexes = [
            IndexModel(
                [("document_id", ASCENDING), ("version_number", ASCENDING)],
                unique=True,
                name="uq_document_version_number",
            ),
            IndexModel([("document_id", ASCENDING), ("created_at", -1)], name="ix_document_versions_history"),
        ]


class LetterCounterDocument(StrictDocument):
    id: UUID = Field(default_factory=uuid4)
    organization: str = Field(min_length=1, max_length=80)
    document_type: str = Field(min_length=2, max_length=8)
    year: int = Field(ge=2000, le=9999)
    value: int = Field(ge=1)

    class Settings:
        name = "letter_counters"
        indexes = [
            IndexModel(
                [("organization", ASCENDING), ("document_type", ASCENDING), ("year", ASCENDING)],
                unique=True,
                name="uq_letter_counter_scope",
            )
        ]


class ExportJobDocument(StrictDocument):
    id: UUID = Field(default_factory=uuid4)
    kind: Literal["render_export"] = "render_export"
    version_id: UUID
    user_id: UUID
    idempotency_key: str = Field(min_length=1, max_length=120)
    status: Literal["queued", "running", "succeeded", "retry_wait", "failed"] = "queued"
    attempt: int = Field(default=0, ge=0)
    lease_until: datetime | None = None
    next_attempt_at: datetime | None = None
    error_code: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    class Settings:
        name = "jobs"
        indexes = [
            IndexModel(
                [("user_id", ASCENDING), ("kind", ASCENDING), ("idempotency_key", ASCENDING)],
                unique=True,
                name="uq_job_idempotency",
            ),
            IndexModel([("status", ASCENDING), ("lease_until", ASCENDING)], name="ix_jobs_lease"),
        ]
