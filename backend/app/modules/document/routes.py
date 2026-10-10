from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from pymongo import AsyncMongoClient

from app.core.config import Settings, get_settings
from app.core.database import get_mongo_client
from app.modules.auth.documents import UserDocument
from app.modules.auth.routes import auth_service, require_current_user
from app.modules.auth.services import AuthService
from app.modules.document.markdown_source import InvalidMarkdownSource
from app.modules.document.pdf_renderer import InvalidMarkdown, RenderLimitExceeded
from app.modules.document.schemas import (
    DocumentCreate,
    DocumentPage,
    DocumentSave,
    DocumentSaveResponse,
    DocumentSummary,
    DocumentVersionDetail,
    DocumentVersionSummary,
    RenderRequest,
)
from app.modules.document.services import DocumentService
from app.modules.document.services import DocumentRenderService
from app.modules.template.services import TemplateService


router = APIRouter(prefix="/documents", tags=["document rendering"])


def document_service() -> DocumentService:
    return DocumentService()


@router.post("", response_model=DocumentSummary, status_code=status.HTTP_201_CREATED)
async def create_document(
    payload: DocumentCreate,
    request: Request,
    actor: UserDocument = Depends(require_current_user),
    service: DocumentService = Depends(document_service),
    auth: AuthService = Depends(auth_service),
) -> DocumentSummary:
    auth.require_csrf_header(request)
    return await service.create_draft(payload, actor)


@router.get("", response_model=DocumentPage)
async def list_documents(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=25, ge=1, le=100),
    actor: UserDocument = Depends(require_current_user),
    service: DocumentService = Depends(document_service),
) -> DocumentPage:
    return await service.list_documents(actor, page, page_size)


@router.get("/{document_id}", response_model=DocumentSummary)
async def get_document(
    document_id: UUID,
    actor: UserDocument = Depends(require_current_user),
    service: DocumentService = Depends(document_service),
) -> DocumentSummary:
    return await service.get_document(document_id, actor)


@router.post("/{document_id}/save", response_model=DocumentSaveResponse)
async def save_document(
    document_id: UUID,
    payload: DocumentSave,
    request: Request,
    actor: UserDocument = Depends(require_current_user),
    service: DocumentService = Depends(document_service),
    auth: AuthService = Depends(auth_service),
    client: AsyncMongoClient = Depends(get_mongo_client),
) -> DocumentSaveResponse:
    auth.require_csrf_header(request)
    return await service.save(document_id, payload, actor, client)


@router.get("/{document_id}/versions", response_model=list[DocumentVersionSummary])
async def list_document_versions(
    document_id: UUID,
    actor: UserDocument = Depends(require_current_user),
    service: DocumentService = Depends(document_service),
) -> list[DocumentVersionSummary]:
    return await service.get_versions(document_id, actor)


@router.get(
    "/{document_id}/versions/{version_id}", response_model=DocumentVersionDetail
)
async def get_document_version(
    document_id: UUID,
    version_id: UUID,
    actor: UserDocument = Depends(require_current_user),
    service: DocumentService = Depends(document_service),
) -> DocumentVersionDetail:
    return await service.get_version(document_id, version_id, actor)


@router.post("/preview", response_class=Response)
async def render_preview(
    payload: RenderRequest,
    _actor: UserDocument = Depends(require_current_user),
    settings: Settings = Depends(get_settings),
) -> Response:
    try:
        template = await TemplateService().get_current()
        content, content_hash = DocumentRenderService(settings).preview(
            payload.markdown,
            template.settings,
        )
    except (InvalidMarkdownSource, InvalidMarkdown, RecursionError) as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="VALIDATION_ERROR",
        ) from error
    except RenderLimitExceeded as error:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="VALIDATION_ERROR",
        ) from error
    return Response(
        content=content,
        media_type="application/pdf",
        headers={
            "Cache-Control": "no-store",
            "Content-Disposition": 'inline; filename="preview.pdf"',
            "X-Content-SHA256": content_hash,
        },
    )
