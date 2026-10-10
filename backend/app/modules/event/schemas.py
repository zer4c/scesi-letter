from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class EventCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=140)
    year: int = Field(ge=2000, le=9999)


class EventResponse(BaseModel):
    id: UUID
    slug: str
    name: str
    year: int
    created_by: UUID
    created_at: datetime


class EventPage(BaseModel):
    items: list[EventResponse]
    page: int
    page_size: int
    total: int
