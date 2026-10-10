from datetime import UTC, datetime

from beanie import Document
from pydantic import ConfigDict, Field
from pymongo import ASCENDING, IndexModel

from app.modules.template.schemas import TemplateSettings


class TemplateDocument(Document):
    model_config = ConfigDict(extra="forbid")

    template_id: str = "default"
    revision: int = Field(ge=1)
    active: bool = True
    settings: TemplateSettings
    created_by: str = "system"
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    class Settings:
        name = "templates"
        indexes = [
            IndexModel(
                [("template_id", ASCENDING), ("revision", ASCENDING)],
                unique=True,
                name="uq_template_revision",
            ),
            IndexModel(
                [("template_id", ASCENDING)],
                unique=True,
                partialFilterExpression={"active": True},
                name="uq_template_active",
            ),
        ]
