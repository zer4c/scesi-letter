from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

DocumentType = Literal["INV", "SOL", "MEM", "ACT", "PRES", "CIRC", "NOT", "GEN"]
SuggestionKind = Literal[
    "grammar", "style", "reference", "document_type", "topic", "recipient_role"
]


class ListDocumentTypesInput(BaseModel):
    model_config = ConfigDict(extra="forbid")


class RoleLookupInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    role_key: str = Field(
        min_length=2, max_length=80, pattern=r"^[a-z0-9]+(?:_[a-z0-9]+)*$"
    )


class RedactionRange(BaseModel):
    model_config = ConfigDict(extra="forbid")

    start: int = Field(ge=0)
    end: int = Field(gt=0)

    @field_validator("end")
    @classmethod
    def positive_range(cls, value: int, info):
        start = info.data.get("start")
        if start is not None and value <= start:
            raise ValueError("Redaction ranges must be non-empty")
        return value


def validate_redaction_ranges(value: list[RedactionRange]) -> list[RedactionRange]:
    ordered = sorted(value, key=lambda item: (item.start, item.end))
    if len(ordered) != len(value):
        raise ValueError("Redaction ranges must be unique")
    for previous, current in zip(ordered, ordered[1:]):
        if previous.end > current.start:
            raise ValueError("Redaction ranges cannot overlap")
    return ordered


class AnalyzeRequest(BaseModel):
    expected_source_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    kinds: list[SuggestionKind] = Field(min_length=1, max_length=6)
    preview_token: str = Field(min_length=32, max_length=2048)
    manual_redactions: list[RedactionRange] = Field(default_factory=list, max_length=20)

    @field_validator("kinds")
    @classmethod
    def unique_kinds(cls, value: list[SuggestionKind]) -> list[SuggestionKind]:
        if len(set(value)) != len(value):
            raise ValueError("Suggestion kinds must be unique")
        return value

    @field_validator("manual_redactions")
    @classmethod
    def unique_redactions(cls, value: list[RedactionRange]) -> list[RedactionRange]:
        return validate_redaction_ranges(value)


class AnalyzePreviewRequest(BaseModel):
    expected_source_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    kinds: list[SuggestionKind] = Field(min_length=1, max_length=6)
    manual_redactions: list[RedactionRange] = Field(default_factory=list, max_length=20)

    @field_validator("kinds")
    @classmethod
    def unique_kinds(cls, value: list[SuggestionKind]) -> list[SuggestionKind]:
        if len(set(value)) != len(value):
            raise ValueError("Suggestion kinds must be unique")
        return value

    @field_validator("manual_redactions")
    @classmethod
    def unique_redactions(cls, value: list[RedactionRange]) -> list[RedactionRange]:
        return validate_redaction_ranges(value)


class AnalyzePreviewResponse(BaseModel):
    source_hash: str
    redacted_body: str
    redaction_count: int = Field(ge=0)
    manual_redactions: list[RedactionRange]
    analysis_available: bool
    preview_token: str
    expires_at: datetime


class SuggestionDraft(BaseModel):
    kind: SuggestionKind
    original: str | None = Field(default=None, max_length=2000)
    replacement: str | None = Field(default=None, max_length=2000)
    field: Literal["document_type", "topic", "recipient_role"] | None = None
    start: int | None = Field(default=None, ge=0)
    end: int | None = Field(default=None, ge=0)
    reason: str = Field(min_length=1, max_length=500)


class SuggestionResponse(SuggestionDraft):
    id: UUID
    source_hash: str
    status: Literal["proposed", "accepted", "rejected", "stale"]
    created_at: datetime


class AnalyzeResponse(BaseModel):
    source_hash: str
    suggestions: list[SuggestionResponse]
    status: Literal["completed", "no_suggestions"]


class SuggestionDecisionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_source_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    contact_id: UUID | None = None


class ModelSuggestionOutput(BaseModel):
    model_config = {"extra": "forbid"}

    kind: SuggestionKind
    original: str | None = Field(default=None, max_length=2000)
    replacement: str | None = Field(default=None, max_length=2000)
    field: Literal["document_type", "topic", "recipient_role"] | None = None
    start: int | None = Field(default=None, ge=0)
    end: int | None = Field(default=None, ge=0)
    reason: str = Field(min_length=1, max_length=500)


class ModelOutput(BaseModel):
    model_config = {"extra": "forbid"}

    suggestions: list[ModelSuggestionOutput] = Field(max_length=20)
