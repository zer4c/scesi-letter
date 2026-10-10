from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator, model_validator


class ContactInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=160)
    role_key: str = Field(min_length=2, max_length=80, pattern=r"^[a-z0-9]+(?:_[a-z0-9]+)*$")
    role_label: str = Field(min_length=1, max_length=120)
    institution: str = Field(min_length=1, max_length=160)
    career: str | None = Field(default=None, max_length=120)
    emails: list[EmailStr] = Field(default_factory=list, max_length=5)
    active: bool = True

    @field_validator("name", "role_label", "institution", "career")
    @classmethod
    def trim_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = " ".join(value.split())
        if not normalized:
            raise ValueError("Value cannot be blank")
        return normalized

    @field_validator("role_key")
    @classmethod
    def normalize_role_key(cls, value: str) -> str:
        return value.strip().lower()

    @model_validator(mode="after")
    def normalize_emails(self) -> "ContactInput":
        emails = [str(email).strip().casefold() for email in self.emails]
        if len(set(emails)) != len(emails):
            raise ValueError("Email addresses must be unique")
        self.emails = emails
        return self


class ContactCreate(ContactInput):
    pass


class ContactUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_revision: int = Field(ge=1)
    name: str | None = Field(default=None, min_length=1, max_length=160)
    role_key: str | None = Field(
        default=None,
        min_length=2,
        max_length=80,
        pattern=r"^[a-z0-9]+(?:_[a-z0-9]+)*$",
    )
    role_label: str | None = Field(default=None, min_length=1, max_length=120)
    institution: str | None = Field(default=None, min_length=1, max_length=160)
    career: str | None = Field(default=None, max_length=120)
    emails: list[EmailStr] | None = Field(default=None, max_length=5)
    active: bool | None = None

    @field_validator("name", "role_label", "institution", "career")
    @classmethod
    def trim_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = " ".join(value.split())
        if not normalized:
            raise ValueError("Value cannot be blank")
        return normalized

    @field_validator("role_key")
    @classmethod
    def normalize_role_key(cls, value: str | None) -> str | None:
        return value.strip().lower() if value is not None else None

    @model_validator(mode="after")
    def validate_patch(self) -> "ContactUpdate":
        fields = self.model_fields_set - {"expected_revision"}
        if not fields:
            raise ValueError("At least one contact field is required")
        for field in fields - {"career"}:
            if getattr(self, field) is None:
                raise ValueError(f"{field} cannot be null")
        if self.emails is not None:
            emails = [str(email).strip().casefold() for email in self.emails]
            if len(set(emails)) != len(emails):
                raise ValueError("Email addresses must be unique")
            self.emails = emails
        return self


class ContactResponse(ContactInput):
    id: UUID
    revision: int
    created_by: UUID
    created_at: datetime
    updated_at: datetime


class ContactPage(BaseModel):
    items: list[ContactResponse]
    page: int
    page_size: int
    total: int
