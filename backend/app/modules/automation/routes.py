from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request
from pymongo import AsyncMongoClient

from app.core.config import Settings, get_settings
from app.core.database import get_mongo_client
from app.modules.auth.documents import UserDocument
from app.modules.auth.routes import auth_service, require_current_user
from app.modules.auth.services import AuthService
from app.modules.automation.documents import LetterSuggestionDocument
from app.modules.automation.graph import LetterAssistanceService
from app.modules.automation.schemas import (
    AnalyzePreviewRequest,
    AnalyzePreviewResponse,
    AnalyzeRequest,
    AnalyzeResponse,
    SuggestionDecisionRequest,
    SuggestionResponse,
)
from app.modules.collaboration.services import CollaborationService
from app.modules.document.documents import LetterDocument
from app.modules.document.services import DocumentService

router = APIRouter(prefix="/documents", tags=["letter assistance"])


@router.post("/{document_id}/analyze/preview", response_model=AnalyzePreviewResponse)
async def preview_analysis(
    document_id: UUID,
    payload: AnalyzePreviewRequest,
    request: Request,
    actor: UserDocument = Depends(require_current_user),
    auth: AuthService = Depends(auth_service),
    settings: Settings = Depends(get_settings),
) -> AnalyzePreviewResponse:
    auth.require_csrf_header(request)
    collaboration: CollaborationService = request.app.state.collaboration_service
    await collaboration.checkpoint_now(document_id, actor)
    document = await _authorized_current_document(document_id, actor)
    if document.source_hash != payload.expected_source_hash:
        raise HTTPException(status_code=409, detail="STALE_SOURCE")
    preview = await LetterAssistanceService(settings, None).create_preview(
        document, actor.id, payload.kinds, payload.manual_redactions
    )
    return AnalyzePreviewResponse(**preview)


@router.post("/{document_id}/analyze", response_model=AnalyzeResponse)
async def analyze_document(
    document_id: UUID,
    payload: AnalyzeRequest,
    request: Request,
    actor: UserDocument = Depends(require_current_user),
    auth: AuthService = Depends(auth_service),
    settings: Settings = Depends(get_settings),
    client: AsyncMongoClient = Depends(get_mongo_client),
) -> AnalyzeResponse:
    auth.require_csrf_header(request)
    collaboration: CollaborationService = request.app.state.collaboration_service
    await collaboration.checkpoint_now(document_id, actor)
    document = await _authorized_current_document(document_id, actor)
    if document.source_hash != payload.expected_source_hash:
        raise HTTPException(status_code=409, detail="STALE_SOURCE")
    service = LetterAssistanceService(settings, client)
    suggestions = await service.analyze(
        document,
        actor.id,
        payload.kinds,
        payload.preview_token,
        payload.manual_redactions,
        collaboration,
        actor,
    )
    return AnalyzeResponse(
        source_hash=document.source_hash,
        suggestions=[
            SuggestionResponse.model_validate(item.model_dump()) for item in suggestions
        ],
        status="completed" if suggestions else "no_suggestions",
    )


@router.get("/{document_id}/suggestions", response_model=list[SuggestionResponse])
async def list_suggestions(
    document_id: UUID,
    source_hash: str,
    request: Request,
    actor: UserDocument = Depends(require_current_user),
) -> list[SuggestionResponse]:
    document = await _authorized_current_document(document_id, actor)
    collaboration: CollaborationService = request.app.state.collaboration_service
    await collaboration.checkpoint_now(document_id, actor)
    document = await _authorized_current_document(document_id, actor)
    if source_hash != document.source_hash:
        raise HTTPException(status_code=409, detail="STALE_SOURCE")
    collection = LetterSuggestionDocument.get_pymongo_collection()
    await collection.update_many(
        {
            "document_id": document_id,
            "source_hash": {"$ne": document.source_hash},
            "status": "proposed",
        },
        {"$set": {"status": "stale"}},
    )
    records = (
        await LetterSuggestionDocument.find(
            LetterSuggestionDocument.document_id == document_id,
            LetterSuggestionDocument.source_hash == source_hash,
        )
        .sort("created_at")
        .to_list()
    )
    return [
        SuggestionResponse.model_validate(record.model_dump()) for record in records
    ]


@router.post(
    "/{document_id}/suggestions/{suggestion_id}/accept",
    response_model=SuggestionResponse,
)
async def accept_suggestion(
    document_id: UUID,
    suggestion_id: UUID,
    payload: SuggestionDecisionRequest,
    request: Request,
    actor: UserDocument = Depends(require_current_user),
    auth: AuthService = Depends(auth_service),
) -> SuggestionResponse:
    auth.require_csrf_header(request)
    document = await _authorized_current_document(document_id, actor)
    collaboration: CollaborationService = request.app.state.collaboration_service
    await collaboration.checkpoint_now(document_id, actor)
    document = await _authorized_current_document(document_id, actor)
    if document.source_hash != payload.expected_source_hash:
        raise HTTPException(status_code=409, detail="STALE_SUGGESTION")
    suggestion = await LetterSuggestionDocument.find_one(
        LetterSuggestionDocument.id == suggestion_id,
        LetterSuggestionDocument.document_id == document_id,
    )
    if suggestion is None:
        raise HTTPException(status_code=404, detail="NOT_FOUND")
    await collaboration.apply_suggestion(
        document,
        suggestion,
        payload.expected_source_hash,
        payload.contact_id,
        actor,
    )
    accepted = await LetterSuggestionDocument.find_one(
        LetterSuggestionDocument.id == suggestion_id,
        LetterSuggestionDocument.document_id == document_id,
    )
    if accepted is None:
        raise HTTPException(status_code=404, detail="NOT_FOUND")
    return SuggestionResponse.model_validate(accepted.model_dump())


@router.post(
    "/{document_id}/suggestions/{suggestion_id}/reject",
    response_model=SuggestionResponse,
)
async def reject_suggestion(
    document_id: UUID,
    suggestion_id: UUID,
    request: Request,
    actor: UserDocument = Depends(require_current_user),
    auth: AuthService = Depends(auth_service),
) -> SuggestionResponse:
    auth.require_csrf_header(request)
    await _authorized_current_document(document_id, actor)
    result = await LetterSuggestionDocument.get_pymongo_collection().update_one(
        {
            "_id": suggestion_id,
            "document_id": document_id,
            "status": "proposed",
        },
        {"$set": {"status": "rejected"}},
    )
    if result.modified_count != 1:
        raise HTTPException(status_code=409, detail="SUGGESTION_ALREADY_DECIDED")
    rejected = await LetterSuggestionDocument.find_one(
        LetterSuggestionDocument.id == suggestion_id,
        LetterSuggestionDocument.document_id == document_id,
    )
    if rejected is None:
        raise HTTPException(status_code=404, detail="NOT_FOUND")
    return SuggestionResponse.model_validate(rejected.model_dump())


async def _authorized_current_document(
    document_id: UUID, actor: UserDocument
) -> LetterDocument:
    document = await LetterDocument.find_one(LetterDocument.id == document_id)
    if document is None:
        raise HTTPException(status_code=404, detail="NOT_FOUND")
    DocumentService._authorize(document, actor)
    return document
