from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request
from pymongo import AsyncMongoClient

from app.core.config import Settings, get_settings
from app.core.database import get_mongo_client
from app.modules.auth.documents import UserDocument
from app.modules.auth.routes import auth_service, require_current_user
from app.modules.auth.services import AuthService
from app.modules.integration.schemas import (
    ConnectionMutationResponse,
    DriveRootRequest,
    GoogleAuthorizationResponse,
    GoogleConnectionRequest,
    IntegrationConnectionsResponse,
    IntegrationConnectionStatus,
)
from app.modules.integration.services import GoogleConnectionService


router = APIRouter(prefix="/integrations", tags=["integrations"])


def integration_service(
    settings: Settings = Depends(get_settings),
) -> GoogleConnectionService:
    return GoogleConnectionService(settings)


@router.get("", response_model=IntegrationConnectionsResponse)
async def list_connections(
    actor: UserDocument = Depends(require_current_user),
    service: GoogleConnectionService = Depends(integration_service),
) -> IntegrationConnectionsResponse:
    return await service.list_connections(actor)


@router.post("/google/connect", response_model=GoogleAuthorizationResponse)
async def create_google_authorization(
    payload: GoogleConnectionRequest,
    request: Request,
    actor: UserDocument = Depends(require_current_user),
    auth: AuthService = Depends(auth_service),
    service: GoogleConnectionService = Depends(integration_service),
) -> GoogleAuthorizationResponse:
    auth.require_csrf_header(request)
    return await service.create_authorization(payload, actor)


@router.get("/google/callback", response_model=IntegrationConnectionStatus)
async def google_callback(
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
    actor: UserDocument = Depends(require_current_user),
    service: GoogleConnectionService = Depends(integration_service),
    client: AsyncMongoClient = Depends(get_mongo_client),
) -> IntegrationConnectionStatus:
    if error is not None:
        raise HTTPException(status_code=400, detail="GOOGLE_CONSENT_DENIED")
    if code is None or state is None:
        raise HTTPException(status_code=400, detail="VALIDATION_ERROR")
    return await service.complete_authorization(code, state, actor, client)


@router.put("/{connection_id}/root", response_model=ConnectionMutationResponse)
async def select_drive_root(
    connection_id: UUID,
    payload: DriveRootRequest,
    request: Request,
    actor: UserDocument = Depends(require_current_user),
    auth: AuthService = Depends(auth_service),
    service: GoogleConnectionService = Depends(integration_service),
    client: AsyncMongoClient = Depends(get_mongo_client),
) -> ConnectionMutationResponse:
    auth.require_csrf_header(request)
    return await service.select_drive_root(connection_id, payload, actor, client)


@router.post("/{connection_id}/disconnect", response_model=ConnectionMutationResponse)
async def disconnect_google(
    connection_id: UUID,
    request: Request,
    actor: UserDocument = Depends(require_current_user),
    auth: AuthService = Depends(auth_service),
    service: GoogleConnectionService = Depends(integration_service),
    client: AsyncMongoClient = Depends(get_mongo_client),
) -> ConnectionMutationResponse:
    auth.require_csrf_header(request)
    return await service.disconnect(connection_id, actor, client)
