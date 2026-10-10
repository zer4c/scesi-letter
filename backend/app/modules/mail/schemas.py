from datetime import datetime
from typing import Annotated
from uuid import UUID

from pydantic import (
    BaseModel,
    ConfigDict,
    EmailStr,
    Field,
    ValidationInfo,
    field_validator,
    model_validator,
)

EmailAddress = Annotated[EmailStr, Field(max_length=254)]


class MailDispatchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    document_id: UUID
    version_id: UUID
    connection_id: UUID
    to: list[EmailAddress] = Field(min_length=1, max_length=5)
    cc: list[EmailAddress] = Field(default_factory=list, max_length=5)
    bcc: list[EmailAddress] = Field(default_factory=list, max_length=5)
    subject: str = Field(min_length=1, max_length=200)
    body: str = Field(min_length=1, max_length=1000)
    confirmed: bool

    @field_validator("subject", "body")
    @classmethod
    def normalize_text(cls, value: str, info: ValidationInfo) -> str:
        normalized = value.strip()
        if info.field_name == "body":
            normalized = normalized.replace("\r\n", "\n").replace("\r", "\n")
        if (
            not normalized
            or "\x00" in normalized
            or (info.field_name == "subject" and ("\r" in normalized or "\n" in normalized))
        ):
            raise ValueError("Invalid mail text")
        return normalized

    @model_validator(mode="after")
    def validate_dispatch(self) -> "MailDispatchRequest":
        if not self.confirmed:
            raise ValueError("Explicit send confirmation is required")
        normalized = [str(email).casefold() for email in [*self.to, *self.cc, *self.bcc]]
        if len(set(normalized)) != len(normalized):
            raise ValueError("Recipients must be unique across To, CC, and BCC")
        return self


class MailJobResponse(BaseModel):
    job_id: UUID
    status: str
    attempt: int
    error_code: str | None
    updated_at: datetime
