from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request, status

from app.modules.auth.documents import UserDocument
from app.modules.auth.routes import auth_service, require_current_user
from app.modules.auth.services import AuthService
from app.modules.event.schemas import EventCreate, EventPage, EventResponse
from app.modules.event.services import EventService


router = APIRouter(prefix="/events", tags=["events"])


@router.get("", response_model=EventPage)
async def list_events(
    year: int | None = Query(default=None, ge=2000, le=9999),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=25, ge=1, le=100),
    _actor: UserDocument = Depends(require_current_user),
) -> EventPage:
    return await EventService().list(year, page, page_size)


@router.post("", response_model=EventResponse, status_code=status.HTTP_201_CREATED)
async def create_event(
    payload: EventCreate,
    request: Request,
    actor: UserDocument = Depends(require_current_user),
    auth: AuthService = Depends(auth_service),
) -> EventResponse:
    auth.require_csrf_header(request)
    return await EventService().create(payload, actor)


@router.get("/{event_id}", response_model=EventResponse)
async def get_event(
    event_id: UUID,
    _actor: UserDocument = Depends(require_current_user),
) -> EventResponse:
    return await EventService().get(event_id)
