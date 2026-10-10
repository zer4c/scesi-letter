from datetime import UTC, datetime
from uuid import UUID

from beanie import Document
from pydantic import ConfigDict, Field
from pymongo import ASCENDING, IndexModel


class StrictDocument(Document):
    model_config = ConfigDict(extra="forbid")


class DocumentStateDocument(StrictDocument):
    document_id: UUID
    crdt_snapshot: bytes
    state_vector: bytes
    server_revision: int = Field(default=0, ge=0)
    checkpoint_hash: str = Field(min_length=64, max_length=64)
    snapshot_sequence: int = Field(default=0, ge=0)
    last_sequence: int = Field(default=0, ge=0)
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    class Settings:
        name = "document_states"
        indexes = [
            IndexModel(
                [("document_id", ASCENDING)],
                unique=True,
                name="uq_document_state_document",
            )
        ]


class CollaborationUpdateDocument(StrictDocument):
    document_id: UUID
    sequence: int = Field(ge=1)
    binary_update: bytes
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    class Settings:
        name = "collaboration_updates"
        indexes = [
            IndexModel(
                [("document_id", ASCENDING), ("sequence", ASCENDING)],
                unique=True,
                name="uq_collaboration_update_sequence",
            )
        ]
