from datetime import UTC, datetime
from typing import Literal
from uuid import UUID, uuid4

from beanie import Document
from pydantic import ConfigDict, Field
from pymongo import ASCENDING, IndexModel


class LetterSuggestionDocument(Document):
    model_config = ConfigDict(extra="forbid")

    id: UUID = Field(default_factory=uuid4)
    document_id: UUID
    source_hash: str = Field(min_length=64, max_length=64)
    kind: Literal[
        "grammar", "style", "reference", "document_type", "topic", "recipient_role"
    ]
    original: str | None = None
    replacement: str | None = None
    field: Literal["document_type", "topic", "recipient_role"] | None = None
    start: int | None = Field(default=None, ge=0)
    end: int | None = Field(default=None, ge=0)
    reason: str = Field(min_length=1, max_length=500)
    status: Literal["proposed", "accepted", "rejected", "stale"] = "proposed"
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    class Settings:
        name = "letter_suggestions"
        indexes = [
            IndexModel(
                [
                    ("document_id", ASCENDING),
                    ("source_hash", ASCENDING),
                    ("status", ASCENDING),
                ],
                name="ix_suggestions_source",
            ),
        ]


class LLMQuotaGateDocument(Document):
    model_config = ConfigDict(extra="forbid")

    id: UUID = Field(default_factory=uuid4)
    model: str
    revision: int = Field(default=0, ge=0)
    header_rpd_remaining: int | None = Field(default=None, ge=0)
    header_rpd_observed_at: datetime | None = None
    header_rpd_reset_at: datetime | None = None
    header_tpm_remaining: int | None = Field(default=None, ge=0)
    header_tpm_observed_at: datetime | None = None
    header_tpm_reset_at: datetime | None = None

    class Settings:
        name = "llm_quota_gates"
        indexes = [
            IndexModel([("model", ASCENDING)], unique=True, name="uq_llm_quota_model")
        ]


class LLMQuotaReservationDocument(Document):
    model_config = ConfigDict(extra="forbid")

    id: UUID = Field(default_factory=uuid4)
    model: str
    status: Literal["reserved", "settled", "uncertain"] = "reserved"
    estimated_input_tokens: int = Field(ge=0)
    estimated_output_tokens: int = Field(ge=0)
    actual_input_tokens: int | None = Field(default=None, ge=0)
    actual_output_tokens: int | None = Field(default=None, ge=0)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    settled_at: datetime | None = None

    class Settings:
        name = "llm_quota_reservations"
        indexes = [
            IndexModel(
                [("model", ASCENDING), ("created_at", ASCENDING)],
                name="ix_llm_reservations_window",
            ),
            IndexModel(
                [("created_at", ASCENDING)],
                expireAfterSeconds=172800,
                name="ttl_llm_reservations_cleanup",
            ),
        ]
