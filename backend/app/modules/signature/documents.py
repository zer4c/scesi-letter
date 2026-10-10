from datetime import datetime
from uuid import UUID, uuid4

from beanie import Document
from pydantic import ConfigDict, Field
from pymongo import ASCENDING, IndexModel


class SigningAuthorizationDocument(Document):
    model_config = ConfigDict(extra="forbid")

    id: UUID = Field(default_factory=uuid4)
    token_hash: str = Field(min_length=64, max_length=64)
    user_id: UUID
    credential_revision: int = Field(ge=1)
    document_id: UUID
    version_id: UUID
    source_hash: str = Field(min_length=64, max_length=64)
    draft_revision: int = Field(ge=1)
    expires_at: datetime
    consumed_at: datetime | None = None

    class Settings:
        name = "signing_authorizations"
        indexes = [
            IndexModel(
                [("token_hash", ASCENDING)],
                unique=True,
                name="uq_signing_authorization_token",
            ),
            IndexModel(
                [("expires_at", ASCENDING)],
                expireAfterSeconds=0,
                name="ttl_signing_authorization_expiry",
            ),
        ]
