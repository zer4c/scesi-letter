from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class GoogleConnectionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal["gmail", "drive"]
    mode: Literal["personal", "institutional"]


class GoogleAuthorizationResponse(BaseModel):
    authorization_url: str
    expires_at: datetime


class IntegrationConnectionStatus(BaseModel):
    id: UUID
    kind: Literal["gmail", "drive"]
    mode: Literal["personal", "institutional"]
    google_account: EmailStr
    scopes: list[str]
    status: Literal["active", "reauthorization_required"]
    root_folder_id: str | None
    expires_at: datetime
    connected_at: datetime
    updated_at: datetime


class IntegrationConnectionsResponse(BaseModel):
    connections: list[IntegrationConnectionStatus]


class ConnectionMutationResponse(BaseModel):
    status: Literal["disconnected", "root_selected"]
    connection_id: UUID


class DriveRootRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    folder_id: str = Field(min_length=1, max_length=256, pattern=r"^[A-Za-z0-9_-]+$")
