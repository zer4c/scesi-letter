from datetime import date, datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class PartySnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=160)
    role: str | None = Field(default=None, max_length=120)
    institution: str | None = Field(default=None, max_length=160)
    career: str | None = Field(default=None, max_length=120)
    email: str | None = Field(default=None, max_length=254)


class LetterMetadata(BaseModel):
    model_config = ConfigDict(extra="forbid")

    identifier: str | None = Field(
        default=None,
        pattern=r"^(INV|SOL|MEM|ACT|PRES|CIRC|NOT|GEN)-SCESI-\d{4}-\d{3,}$",
        max_length=64,
    )
    document_type: Literal["INV", "SOL", "MEM", "ACT", "PRES", "CIRC", "NOT", "GEN"]
    date: date
    reference: str | None = Field(default=None, max_length=300)
    salutation: str | None = Field(default=None, max_length=300)
    recipient: PartySnapshot | None = None
    recipient_contact_id: UUID | None = None
    sender: PartySnapshot | None = None
    topic: str | None = Field(default=None, max_length=200)
    signoff: str | None = Field(default=None, max_length=300)
    event_id: UUID | None = None
    template_revision: int | None = Field(default=None, ge=1)


class LetterFields(BaseModel):
    model_config = ConfigDict(extra="forbid")

    document_type: Literal["INV", "SOL", "MEM", "ACT", "PRES", "CIRC", "NOT", "GEN"]
    date: date
    reference: str | None = Field(default=None, max_length=300)
    salutation: str | None = Field(default=None, max_length=300)
    recipient: PartySnapshot | None = None
    recipient_contact_id: UUID | None = None
    sender: PartySnapshot | None = None
    topic: str | None = Field(default=None, max_length=200)
    signoff: str | None = Field(default=None, max_length=300)
    event_id: UUID | None = None


class DocumentCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    metadata: LetterFields
    body: str = Field(min_length=1, max_length=100_000)


class DocumentSave(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_revision: int = Field(ge=1)
    expected_source_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    metadata: LetterFields
    body: str = Field(min_length=1, max_length=100_000)


class DocumentSummary(BaseModel):
    id: UUID
    owner_id: UUID
    participant_ids: list[UUID]
    metadata: LetterMetadata
    body: str
    draft_revision: int
    source_hash: str
    current_version: UUID | None
    identifier_year: int | None
    created_at: datetime


class DocumentListItem(BaseModel):
    id: UUID
    owner_id: UUID
    document_type: str
    identifier: str | None
    topic: str | None
    recipient_name: str | None
    current_version: UUID | None
    draft_revision: int
    updated_at: datetime


class DocumentPage(BaseModel):
    items: list[DocumentListItem]
    page: int
    page_size: int
    total: int


class DocumentVersionSummary(BaseModel):
    id: UUID
    document_id: UUID
    version_number: int
    source_hash: str
    template_revision: int
    status: str
    created_by: UUID
    created_at: datetime


class DocumentVersionDetail(DocumentVersionSummary):
    metadata_snapshot: LetterMetadata
    body_snapshot: str
    markdown_snapshot: str
    md_hash: str
    pdf_hash: str | None
    finalized_at: datetime | None


class DocumentSaveResponse(BaseModel):
    document: DocumentSummary
    version: DocumentVersionSummary
    changed: bool


class RenderRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    markdown: str = Field(min_length=1, max_length=120_000)
