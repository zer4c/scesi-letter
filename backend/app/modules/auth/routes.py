from datetime import timedelta
from ipaddress import ip_address
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pymongo import AsyncMongoClient

from app.core.config import Settings, get_settings
from app.core.database import get_mongo_client
from app.modules.auth.documents import UserDocument
from app.modules.auth.schemas import (
    AuthResponse,
    InvitationCreate,
    InvitationRedeem,
    InvitationRedeemResponse,
    InvitationResponse,
    InvitationSummary,
    LoginRequest,
    UserPage,
    UserSummary,
    UserUpdate,
)
from app.modules.auth.services import (
    ABSOLUTE_SESSION_HOURS,
    CSRF_COOKIE,
    SESSION_COOKIE,
    AuthService,
    get_auth_service,
    invitation_url,
    public_user,
)


router = APIRouter(prefix="/auth", tags=["authentication"])
membership_router = APIRouter(prefix="/users", tags=["membership"])


def auth_service(settings: Settings = Depends(get_settings)) -> AuthService:
    return get_auth_service(settings)


async def require_current_user(
    request: Request,
    service: AuthService = Depends(auth_service),
) -> UserDocument:
    return await service.authenticate_request(request)


def set_session_cookies(
    response: Response,
    settings: Settings,
    session_token: str,
    csrf_token: str,
) -> None:
    max_age = int(timedelta(hours=ABSOLUTE_SESSION_HOURS).total_seconds())
    response.set_cookie(
        key=SESSION_COOKIE,
        value=session_token,
        max_age=max_age,
        httponly=True,
        secure=settings.COOKIE_SECURE,
        samesite="lax",
        path="/",
    )
    response.set_cookie(
        key=CSRF_COOKIE,
        value=csrf_token,
        max_age=max_age,
        httponly=False,
        secure=settings.COOKIE_SECURE,
        samesite="strict",
        path="/",
    )


@router.post("/login", response_model=AuthResponse)
async def login(
    payload: LoginRequest,
    request: Request,
    response: Response,
    settings: Settings = Depends(get_settings),
    service: AuthService = Depends(auth_service),
    client: AsyncMongoClient = Depends(get_mongo_client),
) -> AuthResponse:
    peer_address = request.client.host if request.client is not None else "unknown"
    forwarded_address = request.headers.get("x-real-ip", "")
    try:
        network_address = str(ip_address(forwarded_address))
    except ValueError:
        network_address = peer_address
    issued = await service.login(
        str(payload.email), payload.password, network_address, client
    )
    set_session_cookies(
        response, settings, issued.session_token, issued.csrf_token
    )
    return AuthResponse(user=issued.user, csrf_token=issued.csrf_token)


@router.get("/session", response_model=AuthResponse)
async def get_session(
    request: Request,
    user: UserDocument = Depends(require_current_user),
    service: AuthService = Depends(auth_service),
) -> AuthResponse:
    csrf_token = service.csrf_token(request)
    return AuthResponse(user=public_user(user), csrf_token=csrf_token)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(
    request: Request,
    settings: Settings = Depends(get_settings),
    _user: UserDocument = Depends(require_current_user),
    service: AuthService = Depends(auth_service),
) -> Response:
    service.require_csrf_header(request)
    await service.revoke_session(request)
    response = Response(status_code=status.HTTP_204_NO_CONTENT)
    response.delete_cookie(
        SESSION_COOKIE, path="/", secure=settings.COOKIE_SECURE, samesite="lax"
    )
    response.delete_cookie(
        CSRF_COOKIE, path="/", secure=settings.COOKIE_SECURE, samesite="strict"
    )
    return response


@router.post("/invitations", response_model=InvitationResponse)
async def create_invitation(
    payload: InvitationCreate,
    request: Request,
    actor: UserDocument = Depends(require_current_user),
    settings: Settings = Depends(get_settings),
    service: AuthService = Depends(auth_service),
) -> InvitationResponse:
    service.require_csrf_header(request)
    if actor.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="FORBIDDEN",
        )
    token, expires_at = await service.create_invitation(
        str(payload.email), actor
    )
    return InvitationResponse(
        email=payload.email,
        invitation_url=invitation_url(settings, token),
        expires_at=expires_at,
    )


@router.get("/invitations", response_model=list[InvitationSummary])
async def list_invitations(
    actor: UserDocument = Depends(require_current_user),
    service: AuthService = Depends(auth_service),
) -> list[InvitationSummary]:
    if actor.role != "admin":
        raise HTTPException(status_code=403, detail="FORBIDDEN")
    return await service.list_invitations()


@router.delete("/invitations/{invitation_id}", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_invitation(
    invitation_id: UUID,
    request: Request,
    client: AsyncMongoClient = Depends(get_mongo_client),
    actor: UserDocument = Depends(require_current_user),
    service: AuthService = Depends(auth_service),
) -> Response:
    service.require_csrf_header(request)
    if actor.role != "admin":
        raise HTTPException(status_code=403, detail="FORBIDDEN")
    await service.revoke_invitation(invitation_id, client)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/invitations/redeem",
    response_model=InvitationRedeemResponse,
    status_code=status.HTTP_201_CREATED,
)
async def redeem_invitation(
    payload: InvitationRedeem,
    client: AsyncMongoClient = Depends(get_mongo_client),
    service: AuthService = Depends(auth_service),
) -> InvitationRedeemResponse:
    user = await service.redeem_invitation(
        payload.token,
        payload.display_name,
        payload.password,
        client,
    )
    return InvitationRedeemResponse(
        id=user.id,
        email=user.normalized_email,
        status="created",
    )


@membership_router.get("", response_model=UserPage)
async def list_users(
    page: int = 1,
    page_size: int = 25,
    actor: UserDocument = Depends(require_current_user),
    service: AuthService = Depends(auth_service),
) -> UserPage:
    if actor.role != "admin":
        raise HTTPException(status_code=403, detail="FORBIDDEN")
    if page < 1 or page_size < 1 or page_size > 100:
        raise HTTPException(status_code=400, detail="VALIDATION_ERROR")
    items, total = await service.list_users(page, page_size)
    return UserPage(items=items, page=page, page_size=page_size, total=total)


@membership_router.patch("/{user_id}")
async def update_user(
    user_id: UUID,
    payload: UserUpdate,
    request: Request,
    actor: UserDocument = Depends(require_current_user),
    service: AuthService = Depends(auth_service),
    client: AsyncMongoClient = Depends(get_mongo_client),
) -> UserSummary:
    service.require_csrf_header(request)
    if actor.role != "admin":
        raise HTTPException(status_code=403, detail="FORBIDDEN")
    return await service.update_user(actor.id, user_id, payload, client)
