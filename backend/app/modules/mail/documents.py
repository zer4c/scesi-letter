from datetime import UTC, datetime
from typing import Literal
from uuid import UUID, uuid4

from pydantic import Field
from pymongo import ASCENDING, IndexModel

from app.modules.auth.documents import StrictDocument
from app.modules.integration.documents import EncryptedValue


class MailDispatchJobDocument(StrictDocument):
    id: UUID = Field(default_factory=uuid4)
    kind: Literal["mail_dispatch"] = "mail_dispatch"
    document_id: UUID
    version_id: UUID
    connection_id: UUID
    user_id: UUID
    idempotency_key: str
    request_fingerprint: str
    pdf_hash: str
    status: Literal["queued", "running", "succeeded", "failed", "unknown"] = "queued"
    attempt: int = 0
    lease_owner: str | None = None
    lease_until: datetime | None = None
    submission_started_at: datetime | None = None
    error_code: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    class Settings:
        name = "mail_dispatch_jobs"
        indexes = [
            IndexModel(
                [("user_id", ASCENDING), ("kind", ASCENDING), ("idempotency_key", ASCENDING)],
                unique=True,
                name="uq_mail_dispatch_idempotency",
            ),
            IndexModel(
                [("status", ASCENDING), ("created_at", ASCENDING)],
                name="ix_mail_dispatch_queue",
            ),
            IndexModel([("created_at", ASCENDING)], expireAfterSeconds=604800, name="ttl_mail_dispatch_7d"),
        ]


class MailDispatchPayloadDocument(StrictDocument):
    id: UUID = Field(default_factory=uuid4)
    job_id: UUID
    user_id: UUID
    encrypted_payload: EncryptedValue
    expires_at: datetime
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    class Settings:
        name = "mail_dispatch_payloads"
        indexes = [
            IndexModel([("job_id", ASCENDING)], unique=True, name="uq_mail_payload_job"),
            IndexModel([("expires_at", ASCENDING)], expireAfterSeconds=0, name="ttl_mail_payload_expiry"),
        ]
