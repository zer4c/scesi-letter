from datetime import UTC, datetime
from typing import Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator
from pymongo import ASCENDING, IndexModel

from app.modules.auth.documents import StrictDocument


class EncryptedValue(BaseModel):
    model_config = ConfigDict(extra="forbid")

    key_id: str = Field(min_length=1, max_length=64)
    nonce: str = Field(min_length=16, max_length=16)
    ciphertext: str = Field(min_length=24, max_length=16384)


class IntegrationConnectionDocument(StrictDocument):
    id: UUID = Field(default_factory=uuid4)
    kind: Literal["gmail", "drive"]
    mode: Literal["personal", "institutional"]
    owner_user_id: UUID | None = None
    google_account: EmailStr
    encrypted_tokens: EncryptedValue
    scopes: list[str] = Field(min_length=1, max_length=8)
    status: Literal["active", "reauthorization_required"] = "active"
    root_folder_id: str | None = Field(default=None, min_length=1, max_length=256)
    expires_at: datetime
    connected_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    @field_validator("google_account")
    @classmethod
    def normalize_account_email(cls, value: EmailStr) -> str:
        return str(value).casefold()

    class Settings:
        name = "integration_connections"
        indexes = [
            IndexModel(
                [("kind", ASCENDING), ("mode", ASCENDING), ("owner_user_id", ASCENDING)],
                unique=True,
                name="uq_integration_connection_owner_mode",
            ),
            IndexModel(
                [("google_account", ASCENDING), ("kind", ASCENDING)],
                name="ix_integration_connection_account",
            ),
        ]


class OAuthStateDocument(StrictDocument):
    id: UUID = Field(default_factory=uuid4)
    state_hash: str = Field(min_length=64, max_length=64)
    user_id: UUID
    kind: Literal["gmail", "drive"]
    mode: Literal["personal", "institutional"]
    scopes: list[str] = Field(min_length=1, max_length=8)
    encrypted_code_verifier: EncryptedValue
    expires_at: datetime
    used_at: datetime | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    class Settings:
        name = "oauth_states"
        indexes = [
            IndexModel(
                [("state_hash", ASCENDING)],
                unique=True,
                name="uq_oauth_state_hash",
            ),
            IndexModel(
                [("expires_at", ASCENDING)],
                expireAfterSeconds=0,
                name="ttl_oauth_state_expiry",
            ),
        ]
