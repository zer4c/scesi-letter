from datetime import datetime
from typing import Literal

from pydantic import AnyHttpUrl, BaseModel, ConfigDict, EmailStr, Field, field_validator


class TemplateSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    university_name: str = Field(min_length=1, max_length=160)
    faculty_name: str = Field(min_length=1, max_length=160)
    organization_name: str = Field(min_length=1, max_length=160)
    footer_phones: list[str] = Field(default_factory=list, max_length=5)
    footer_url: AnyHttpUrl
    qr_destination: AnyHttpUrl
    footer_email: EmailStr
    footer_address: str = Field(min_length=1, max_length=240)
    city: str | None = Field(default=None, max_length=100)
    date_format: Literal["long_es", "short_es"] = "long_es"
    body_font: Literal["charis", "liberation_serif"] = "charis"
    body_font_size: float = Field(default=11, ge=9, le=14)
    margin_left_mm: float = Field(default=30, ge=15, le=35)
    margin_right_mm: float = Field(default=30, ge=15, le=35)
    margin_top_mm: float = Field(default=36.8, ge=30, le=45)
    margin_bottom_mm: float = Field(default=28.3, ge=20, le=35)

    @field_validator("university_name", "faculty_name", "organization_name", "footer_address", "city")
    @classmethod
    def normalize_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = " ".join(value.split())
        if not normalized:
            raise ValueError("Value cannot be blank")
        return normalized

    @field_validator("footer_phones")
    @classmethod
    def validate_phones(cls, values: list[str]) -> list[str]:
        normalized = [" ".join(value.split()) for value in values]
        if any(
            len(value) < 5
            or len(value) > 24
            or any(character not in "+0123456789 ()-" for character in value)
            for value in normalized
        ):
            raise ValueError("Footer phone numbers contain unsupported characters")
        if len(set(normalized)) != len(normalized):
            raise ValueError("Footer phone numbers must be unique")
        return normalized


class TemplateUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_revision: int = Field(ge=1)
    settings: TemplateSettings


class TemplateResponse(BaseModel):
    template_id: str
    revision: int
    settings: TemplateSettings
    created_at: datetime
