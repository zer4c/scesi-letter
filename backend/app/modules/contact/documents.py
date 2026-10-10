from datetime import UTC, datetime
from uuid import UUID, uuid4

from beanie import Document
from pydantic import ConfigDict, Field
from pymongo import ASCENDING, IndexModel


class ContactDocument(Document):
    model_config = ConfigDict(extra="forbid")

    id: UUID = Field(default_factory=uuid4)
    name: str = Field(min_length=1, max_length=160)
    role_key: str = Field(min_length=2, max_length=80)
    role_label: str = Field(min_length=1, max_length=120)
    institution: str = Field(min_length=1, max_length=160)
    career: str | None = Field(default=None, max_length=120)
    emails: list[str] = Field(default_factory=list, max_length=5)
    normalized_emails: list[str] | None = None
    active: bool = True
    revision: int = Field(default=1, ge=1)
    created_by: UUID
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    class Settings:
        name = "contacts"
        indexes = [
            IndexModel(
                [("role_key", ASCENDING), ("institution", ASCENDING), ("career", ASCENDING)],
                name="ix_contacts_role_institution_career",
            ),
            IndexModel(
                [("normalized_emails", ASCENDING)],
                unique=True,
                partialFilterExpression={"normalized_emails": {"$type": "array"}},
                name="uq_contacts_normalized_email",
            ),
            IndexModel(
                [("active", ASCENDING), ("name", ASCENDING)],
                name="ix_contacts_active_name",
            ),
        ]
