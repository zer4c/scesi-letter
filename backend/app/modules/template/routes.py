from fastapi import APIRouter, Depends, HTTPException, Request
from pymongo import AsyncMongoClient

from app.core.database import get_mongo_client
from app.modules.auth.documents import UserDocument
from app.modules.auth.routes import auth_service, require_current_user
from app.modules.auth.services import AuthService
from app.modules.template.schemas import TemplateResponse, TemplateUpdate
from app.modules.template.services import TemplateService


router = APIRouter(prefix="/template", tags=["template"])


def template_service() -> TemplateService:
    return TemplateService()


@router.get("", response_model=TemplateResponse)
async def get_template(
    _actor: UserDocument = Depends(require_current_user),
    service: TemplateService = Depends(template_service),
) -> TemplateResponse:
    return await service.get_current()


@router.patch("", response_model=TemplateResponse)
async def update_template(
    payload: TemplateUpdate,
    request: Request,
    actor: UserDocument = Depends(require_current_user),
    service: TemplateService = Depends(template_service),
    auth: AuthService = Depends(auth_service),
    client: AsyncMongoClient = Depends(get_mongo_client),
) -> TemplateResponse:
    auth.require_csrf_header(request)
    if actor.role != "admin":
        raise HTTPException(status_code=403, detail="FORBIDDEN")
    return await service.update(
        payload.expected_revision,
        payload.settings,
        str(actor.id),
        client,
    )
