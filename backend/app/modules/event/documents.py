from datetime import UTC, datetime
from uuid import UUID, uuid4

from beanie import Document
from pydantic import ConfigDict, Field
from pymongo import ASCENDING, IndexModel


class EventDocument(Document):
    model_config = ConfigDict(extra="forbid")

    id: UUID = Field(default_factory=uuid4)
    slug: str = Field(min_length=1, max_length=140)
    name: str = Field(min_length=1, max_length=140)
    year: int = Field(ge=2000, le=9999)
    created_by: UUID
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    class Settings:
        name = "events"
        indexes = [
            IndexModel(
                [("year", ASCENDING), ("slug", ASCENDING)],
                unique=True,
                name="uq_events_year_slug",
            ),
            IndexModel([("year", ASCENDING), ("name", ASCENDING)], name="ix_events_year_name"),
        ]
