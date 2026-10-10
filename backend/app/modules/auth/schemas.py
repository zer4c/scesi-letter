from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field, model_validator


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=1024)


class InvitationCreate(BaseModel):
    email: EmailStr


class InvitationRedeem(BaseModel):
    token: str = Field(min_length=32, max_length=256)
    display_name: str = Field(min_length=1, max_length=120)
    password: str = Field(min_length=12, max_length=1024)


class PublicUser(BaseModel):
    id: UUID
    email: EmailStr
    display_name: str
    role: Literal["admin", "user"]


class AuthResponse(BaseModel):
    user: PublicUser
    csrf_token: str


class InvitationResponse(BaseModel):
    email: EmailStr
    invitation_url: str
    expires_at: datetime


class InvitationSummary(BaseModel):
    id: UUID
    email: EmailStr
    created_at: datetime
    expires_at: datetime
    status: Literal["pending", "redeemed", "revoked", "expired"]


class InvitationRedeemResponse(BaseModel):
    id: UUID
    email: EmailStr
    status: Literal["created"]


class UserSummary(BaseModel):
    id: UUID
    email: EmailStr
    display_name: str
    role: Literal["admin", "user"]
    active: bool
    revision: int
    created_at: datetime


class UserPage(BaseModel):
    items: list[UserSummary]
    page: int
    page_size: int
    total: int


class UserUpdate(BaseModel):
    expected_revision: int = Field(ge=1)
    active: bool | None = None
    role: Literal["admin", "user"] | None = None

    @model_validator(mode="after")
    def require_change(self) -> "UserUpdate":
        if self.active is None and self.role is None:
            raise ValueError("At least one membership field is required")
        return self
