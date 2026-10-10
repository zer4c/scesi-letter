from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, model_validator


ArchiveCategory = Literal[
    "classrooms",
    "furniture",
    "requests",
    "invitations",
    "notifications",
    "permissions",
    "presentations",
    "activities",
    "miscellaneous",
]


class ArchiveRetryRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    topic_category: ArchiveCategory | None = None
    confirm_miscellaneous: bool = False

    @model_validator(mode="after")
    def require_miscellaneous_confirmation(self) -> "ArchiveRetryRequest":
        if self.topic_category == "miscellaneous" and not self.confirm_miscellaneous:
            raise ValueError("Miscellaneous archiving requires explicit confirmation")
        return self


class ArchiveStatusResponse(BaseModel):
    job_id: UUID
    document_id: UUID
    version_id: UUID
    status: Literal[
        "queued",
        "running",
        "retry_wait",
        "waiting_connection",
        "needs_classification",
        "succeeded",
        "failed",
    ]
    attempt: int
    error_code: str | None
    root_folder_id: str | None
    markdown_file_id: str | None
    pdf_file_id: str | None
    updated_at: datetime


class ArchiveRetryResponse(BaseModel):
    job_id: UUID
    status: str
    updated_at: datetime
