from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse
from pymongo import AsyncMongoClient

from app.core.config import Settings, get_settings
from app.core.database import get_mongo_client
from app.modules.auth.documents import UserDocument
from app.modules.auth.routes import auth_service, require_current_user
from app.modules.auth.services import AuthService
from app.modules.document.documents import DocumentVersionDocument, LetterDocument
from app.modules.document.services import DocumentService
from app.modules.integration.archive_schemas import (
    ArchiveRetryRequest,
    ArchiveRetryResponse,
    ArchiveStatusResponse,
)
from app.modules.integration.documents import (
    DriveArchiveJobDocument,
    DriveArchiveMappingDocument,
)
from app.modules.integration.repositories import DriveArchiveJobRepository
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
archive_router = APIRouter(prefix="/documents", tags=["document archive"])


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
    settings: Settings = Depends(get_settings),
    actor: UserDocument = Depends(require_current_user),
    service: GoogleConnectionService = Depends(integration_service),
    client: AsyncMongoClient = Depends(get_mongo_client),
) -> RedirectResponse:
    if error is not None:
        return RedirectResponse(
            f"{settings.APP_PUBLIC_URL.rstrip('/')}/settings/organization?connection=denied",
            status_code=303,
        )
    if code is None or state is None:
        raise HTTPException(status_code=400, detail="VALIDATION_ERROR")
    await service.complete_authorization(code, state, actor, client)
    return RedirectResponse(
        f"{settings.APP_PUBLIC_URL.rstrip('/')}/settings/organization?connection=connected",
        status_code=303,
    )


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


@archive_router.get("/{document_id}/versions/{version_id}/archive",
                    response_model=ArchiveStatusResponse)
async def get_archive_status(
    document_id: UUID,
    version_id: UUID,
    actor: UserDocument = Depends(require_current_user),
) -> ArchiveStatusResponse:
    document = await LetterDocument.find_one(LetterDocument.id == document_id)
    version = await DocumentVersionDocument.find_one(
        DocumentVersionDocument.id == version_id,
        DocumentVersionDocument.document_id == document_id,
    )
    if document is None or version is None:
        raise HTTPException(status_code=404, detail="NOT_FOUND")
    DocumentService._authorize(document, actor)
    job = await DriveArchiveJobDocument.find_one(
        DriveArchiveJobDocument.version_id == version_id
    )
    if job is None:
        raise HTTPException(status_code=404, detail="NOT_FOUND")
    mapping = await DriveArchiveMappingDocument.find_one(
        DriveArchiveMappingDocument.version_id == version_id
    )
    return ArchiveStatusResponse(
        job_id=job.id, document_id=document_id, version_id=version_id,
        status=job.status, attempt=job.attempt, error_code=job.error_code,
        root_folder_id=job.root_folder_id or (mapping.root_folder_id if mapping else None),
        markdown_file_id=mapping.markdown_file_id if mapping else None,
        pdf_file_id=mapping.pdf_file_id if mapping else None,
        updated_at=job.updated_at,
    )


@archive_router.post("/{document_id}/versions/{version_id}/sync",
                     response_model=ArchiveRetryResponse)
async def retry_archive(
    document_id: UUID,
    version_id: UUID,
    payload: ArchiveRetryRequest,
    request: Request,
    actor: UserDocument = Depends(require_current_user),
    auth: AuthService = Depends(auth_service),
) -> ArchiveRetryResponse:
    auth.require_csrf_header(request)
    document = await LetterDocument.find_one(LetterDocument.id == document_id)
    version = await DocumentVersionDocument.find_one(
        DocumentVersionDocument.id == version_id,
        DocumentVersionDocument.document_id == document_id,
    )
    if document is None or version is None:
        raise HTTPException(status_code=404, detail="NOT_FOUND")
    DocumentService._authorize(document, actor)
    job = await DriveArchiveJobDocument.find_one(
        DriveArchiveJobDocument.version_id == version_id
    )
    if job is None:
        raise HTTPException(status_code=409, detail="CONFLICT")
    job = await DriveArchiveJobRepository().request_retry(
        job, actor.id, payload.topic_category, payload.confirm_miscellaneous
    )
    return ArchiveRetryResponse(job_id=job.id, status=job.status, updated_at=job.updated_at)
