import re

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from pymongo import AsyncMongoClient

from app.core.config import Settings, get_settings
from app.core.database import get_mongo_client
from app.modules.auth.documents import UserDocument
from app.modules.auth.routes import auth_service, require_current_user
from app.modules.auth.services import AuthService
from app.modules.mail.schemas import MailDispatchRequest, MailJobResponse
from app.modules.mail.services import MailDispatchService

router = APIRouter(prefix="/mail", tags=["mail"])


def mail_service(settings: Settings = Depends(get_settings)) -> MailDispatchService:
    return MailDispatchService(settings)


@router.post("/send", response_model=MailJobResponse, status_code=202)
async def enqueue_mail_dispatch(
    payload: MailDispatchRequest,
    request: Request,
    idempotency_key: str = Header(
        alias="Idempotency-Key", min_length=1, max_length=120
    ),
    actor: UserDocument = Depends(require_current_user),
    auth: AuthService = Depends(auth_service),
    service: MailDispatchService = Depends(mail_service),
    client: AsyncMongoClient = Depends(get_mongo_client),
) -> MailJobResponse:
    auth.require_csrf_header(request)
    if not re.fullmatch(r"[A-Za-z0-9._:-]{1,120}", idempotency_key):
        raise HTTPException(status_code=422, detail="VALIDATION_ERROR")
    return await service.enqueue(payload, idempotency_key, actor, client)
