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


class AnalyzeRequest(BaseModel):
    expected_source_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    kinds: list[SuggestionKind] = Field(min_length=1, max_length=6)
    preview_token: str = Field(min_length=32, max_length=2048)

    @field_validator("kinds")
    @classmethod
    def unique_kinds(cls, value: list[SuggestionKind]) -> list[SuggestionKind]:
        if len(set(value)) != len(value):
            raise ValueError("Suggestion kinds must be unique")
        return value


class AnalyzePreviewRequest(BaseModel):
    expected_source_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    kinds: list[SuggestionKind] = Field(min_length=1, max_length=6)

    @field_validator("kinds")
    @classmethod
    def unique_kinds(cls, value: list[SuggestionKind]) -> list[SuggestionKind]:
        if len(set(value)) != len(value):
            raise ValueError("Suggestion kinds must be unique")
        return value


class AnalyzePreviewResponse(BaseModel):
    source_hash: str
    redacted_body: str
    redaction_count: int = Field(ge=0)
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
