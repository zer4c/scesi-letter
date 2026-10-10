from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status

from app.modules.auth.documents import UserDocument
from app.modules.auth.routes import auth_service, require_current_user
from app.modules.auth.services import AuthService
from app.modules.contact.documents import ContactDocument
from app.modules.contact.schemas import (
    ContactCreate,
    ContactPage,
    ContactResponse,
    ContactUpdate,
    GoogleContactImportRequest,
    GoogleContactImportResponse,
    GoogleContactPreviewPage,
)
from app.modules.contact.services import ContactService
from app.modules.integration.dependencies import google_connection_service
from app.modules.integration.services import GoogleConnectionService


router = APIRouter(prefix="/contacts", tags=["contacts"])


def contact_service() -> ContactService:
    return ContactService()


@router.get("", response_model=ContactPage)
async def search_contacts(
    q: str | None = Query(default=None, max_length=120),
    role: str | None = Query(default=None, max_length=80),
    institution: str | None = Query(default=None, max_length=160),
    career: str | None = Query(default=None, max_length=120),
    include_inactive: bool = False,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=25, ge=1, le=100),
    _actor: UserDocument = Depends(require_current_user),
    service: ContactService = Depends(contact_service),
) -> ContactPage:
    return await service.search(
        page,
        page_size,
        q,
        role,
        institution,
        career,
        include_inactive,
    )


@router.get("/{contact_id}", response_model=ContactResponse)
async def get_contact(
    contact_id: UUID,
    _actor: UserDocument = Depends(require_current_user),
    service: ContactService = Depends(contact_service),
) -> ContactResponse:
    return await service.get(contact_id)


@router.post("", response_model=ContactResponse, status_code=status.HTTP_201_CREATED)
async def create_contact(
    payload: ContactCreate,
    request: Request,
    actor: UserDocument = Depends(require_current_user),
    service: ContactService = Depends(contact_service),
    auth: AuthService = Depends(auth_service),
) -> ContactResponse:
    auth.require_csrf_header(request)
    return await service.create(payload, actor)


@router.patch("/{contact_id}", response_model=ContactResponse)
async def update_contact(
    contact_id: UUID,
    payload: ContactUpdate,
    request: Request,
    _actor: UserDocument = Depends(require_current_user),
    service: ContactService = Depends(contact_service),
    auth: AuthService = Depends(auth_service),
) -> ContactResponse:
    auth.require_csrf_header(request)
    return await service.update(contact_id, payload)


@router.get("/google/other-contacts", response_model=GoogleContactPreviewPage)
async def preview_google_other_contacts(
    connection_id: UUID,
    page_token: str | None = Query(default=None, max_length=2048),
    actor: UserDocument = Depends(require_current_user),
    integrations: GoogleConnectionService = Depends(google_connection_service),
) -> GoogleContactPreviewPage:
    page = await integrations.list_other_contacts(connection_id, actor, page_token)
    emails = [str(item["email"]).casefold() for item in page["items"]]
    existing = ContactDocument.get_pymongo_collection().find(
        {"normalized_emails": {"$in": emails}}, {"normalized_emails": 1}
    )
    duplicates = set()
    async for contact in existing:
        duplicates.update(contact.get("normalized_emails", []))
    items = [
        {**item, "already_imported": str(item["email"]).casefold() in duplicates}
        for item in page["items"]
    ]
    return GoogleContactPreviewPage(
        items=items, next_page_token=page["next_page_token"]
    )


@router.post("/google/other-contacts/import", response_model=GoogleContactImportResponse)
async def import_google_other_contacts(
    payload: GoogleContactImportRequest,
    request: Request,
    actor: UserDocument = Depends(require_current_user),
    service: ContactService = Depends(contact_service),
    auth: AuthService = Depends(auth_service),
) -> GoogleContactImportResponse:
    auth.require_csrf_header(request)
    if payload.confirmed is not True:
        raise HTTPException(status_code=422, detail="CONFIRMATION_REQUIRED")
    return await service.import_google_contacts(payload.contacts, actor)
