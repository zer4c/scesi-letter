from datetime import UTC, datetime
from typing import Literal
from uuid import UUID, uuid4

from beanie import Document
from pydantic import ConfigDict, Field
from pymongo import ASCENDING, IndexModel


class StrictDocument(Document):
    model_config = ConfigDict(extra="forbid")


class UserDocument(StrictDocument):
    id: UUID = Field(default_factory=uuid4)
    normalized_email: str = Field(min_length=3, max_length=254)
    display_name: str = Field(min_length=1, max_length=120)
    password_hash: str = Field(min_length=1, max_length=512)
    role: Literal["admin", "user"] = "user"
    active: bool = True
    revision: int = Field(default=1, ge=1)
    credential_revision: int = Field(default=1, ge=1)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    class Settings:
        name = "users"
        indexes = [
            IndexModel(
                [("normalized_email", ASCENDING)],
                unique=True,
                name="uq_users_normalized_email",
            ),
            IndexModel(
                [("role", ASCENDING)],
                unique=True,
                partialFilterExpression={"role": "admin"},
                name="uq_single_admin",
            ),
        ]


class InvitationDocument(StrictDocument):
    id: UUID = Field(default_factory=uuid4)
    token_hash: str = Field(min_length=64, max_length=64)
    intended_email: str = Field(min_length=3, max_length=254)
    expires_at: datetime
    redeemed_at: datetime | None = None
    revoked_at: datetime | None = None
    created_by: UUID
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    class Settings:
        name = "invitations"
        indexes = [
            IndexModel(
                [("token_hash", ASCENDING)],
                unique=True,
                name="uq_invitations_token_hash",
            ),
            IndexModel(
                [("expires_at", ASCENDING)],
                expireAfterSeconds=0,
                name="ttl_invitations_expiry",
            ),
        ]


class SessionDocument(StrictDocument):
    id: UUID = Field(default_factory=uuid4)
    token_hash: str = Field(min_length=64, max_length=64)
    user_id: UUID
    csrf_token_hash: str = Field(min_length=64, max_length=64)
    expires_at: datetime
    idle_expires_at: datetime
    last_seen_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    revoked_at: datetime | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    class Settings:
        name = "sessions"
        indexes = [
            IndexModel(
                [("token_hash", ASCENDING)],
                unique=True,
                name="uq_sessions_token_hash",
            ),
            IndexModel(
                [("user_id", ASCENDING), ("expires_at", ASCENDING)],
                name="ix_sessions_user_expiry",
            ),
            IndexModel(
                [("expires_at", ASCENDING)],
                expireAfterSeconds=0,
                name="ttl_sessions_expiry",
            ),
            IndexModel(
                [("idle_expires_at", ASCENDING)],
                expireAfterSeconds=0,
                name="ttl_sessions_idle_expiry",
            ),
        ]


class LoginAttemptDocument(StrictDocument):
    key_hash: str = Field(min_length=64, max_length=64)
    window_start: int = Field(ge=0)
    failures: int = Field(default=0, ge=0)
    expires_at: datetime

    class Settings:
        name = "login_attempts"
        indexes = [
            IndexModel(
                [("key_hash", ASCENDING), ("window_start", ASCENDING)],
                unique=True,
                name="uq_login_attempt_window",
            ),
            IndexModel(
                [("expires_at", ASCENDING)],
                expireAfterSeconds=0,
                name="ttl_login_attempt_expiry",
            ),
        ]


class SignatureEnvelopeDocument(StrictDocument):
    user_id: UUID
    envelope_version: int = Field(ge=1, le=1)
    kdf: str = Field(pattern="^argon2id$")
    memory_kib: int = Field(ge=65536, le=65536)
    iterations: int = Field(ge=3, le=3)
    parallelism: int = Field(ge=1, le=1)
    salt: str = Field(min_length=24, max_length=24)
    wrapped_dek: str = Field(min_length=64, max_length=64)
    wrapping_iv: str = Field(min_length=16, max_length=16)
    ciphertext: str = Field(min_length=24, max_length=2796204)
    image_iv: str = Field(min_length=16, max_length=16)
    mime: str = Field(pattern="^image/png$")
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    class Settings:
        name = "signature_envelopes"
        indexes = [
            IndexModel(
                [("user_id", ASCENDING)],
                unique=True,
                name="uq_signature_envelope_owner",
            )
        ]


class SchemaMigrationDocument(Document):
    version: int = Field(ge=1)
    name: str = Field(min_length=1, max_length=120)
    applied_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    class Settings:
        name = "schema_migrations"
        indexes = [
            IndexModel(
                [("version", ASCENDING)],
                unique=True,
                name="uq_schema_migration_version",
            )
        ]
