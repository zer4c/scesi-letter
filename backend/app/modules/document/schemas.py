from datetime import date
from typing import Literal

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
    sender: PartySnapshot | None = None
    topic: str | None = Field(default=None, max_length=200)
    signoff: str | None = Field(default=None, max_length=300)
    template_revision: int | None = Field(default=None, ge=1)


class RenderRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    markdown: str = Field(min_length=1, max_length=100_000)
