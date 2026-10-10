from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field


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


class InvitationRedeemResponse(BaseModel):
    id: UUID
    email: EmailStr
    status: Literal["created"]
