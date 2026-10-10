from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request, status

from app.modules.auth.documents import UserDocument
from app.modules.auth.routes import auth_service, require_current_user
from app.modules.auth.services import AuthService
from app.modules.contact.schemas import ContactCreate, ContactPage, ContactResponse, ContactUpdate
from app.modules.contact.services import ContactService


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
