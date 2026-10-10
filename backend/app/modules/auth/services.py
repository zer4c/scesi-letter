from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
import hashlib
import secrets
from urllib.parse import quote
from uuid import UUID

from fastapi import HTTPException, Request, status
from pymongo import AsyncMongoClient
from pymongo.errors import DuplicateKeyError, PyMongoError

from app.core.config import Settings
from app.core.database import transaction
from app.modules.auth.documents import InvitationDocument, SessionDocument, UserDocument
from app.modules.auth.passwords import hash_password, password_hasher, verify_password
from app.modules.auth.rate_limit import LoginRateLimiter
from app.modules.auth.repositories import InvitationRepository, UserRepository
from app.modules.auth.schemas import (
    InvitationSummary,
    PublicUser,
    UserSummary,
    UserUpdate,
)


SESSION_COOKIE = "scesi_session"
CSRF_COOKIE = "scesi_csrf"
IDLE_SESSION_MINUTES = 30
ABSOLUTE_SESSION_HOURS = 12
SESSION_REFRESH_MINUTES = 5
INVITATION_HOURS = 72


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def public_user(user: UserDocument) -> PublicUser:
    return PublicUser(
        id=user.id,
        email=user.normalized_email,
        display_name=user.display_name,
        role=user.role,
    )


@dataclass(frozen=True)
class IssuedSession:
    user: PublicUser
    session_token: str
    csrf_token: str


class AuthService:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._users = UserRepository()
        self._invitations = InvitationRepository()
        self._rate_limiter = LoginRateLimiter(settings)

    async def login(
        self,
        email: str,
        password: str,
        network_address: str,
        client: AsyncMongoClient,
    ) -> IssuedSession:
        normalized_email = email.strip().casefold()
        await self._rate_limiter.ensure_allowed(normalized_email, network_address)
        user = await self._users.get_by_email(normalized_email)

        if user is None:
            hash_password(password)
            valid_password = False
        else:
            valid_password = verify_password(user.password_hash, password)

        if user is None or not valid_password or not user.active:
            await self._rate_limiter.record_failure(normalized_email, network_address)
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="UNAUTHENTICATED",
            )

        now = datetime.now(UTC)
        session_token = secrets.token_urlsafe(32)
        csrf_token = secrets.token_urlsafe(32)
        absolute_expiry = now + timedelta(hours=ABSOLUTE_SESSION_HOURS)
        session_document = SessionDocument(
            token_hash=hash_token(session_token),
            user_id=user.id,
            csrf_token_hash=hash_token(csrf_token),
            expires_at=absolute_expiry,
            idle_expires_at=min(
                now + timedelta(minutes=IDLE_SESSION_MINUTES), absolute_expiry
            ),
            last_seen_at=now,
        )
        await session_document.insert()

        if password_hasher.check_needs_rehash(user.password_hash):
            user.password_hash = hash_password(password)
            user.revision += 1
            await user.save()

        return IssuedSession(
            user=public_user(user),
            session_token=session_token,
            csrf_token=csrf_token,
        )

    async def create_invitation(
        self, email: str, actor: UserDocument
    ) -> tuple[str, datetime]:
        normalized_email = email.strip().casefold()
        if await self._users.get_by_email(normalized_email) is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="CONFLICT",
            )

        token = secrets.token_urlsafe(32)
        now = datetime.now(UTC)
        expires_at = now + timedelta(hours=INVITATION_HOURS)
        invitation = InvitationDocument(
            token_hash=hash_token(token),
            intended_email=normalized_email,
            expires_at=expires_at,
            created_by=actor.id,
            created_at=now,
        )
        try:
            await self._invitations.insert(invitation)
        except DuplicateKeyError as error:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="CONFLICT",
            ) from error

        return token, expires_at

    async def list_invitations(self) -> list[InvitationSummary]:
        now = datetime.now(UTC)
        summaries = []
        for invitation in await self._invitations.list_all():
            if invitation.revoked_at is not None:
                state = "revoked"
            elif invitation.redeemed_at is not None:
                state = "redeemed"
            elif invitation.expires_at <= now:
                state = "expired"
            else:
                state = "pending"
            summaries.append(
                InvitationSummary(
                    id=invitation.id,
                    email=invitation.intended_email,
                    created_at=invitation.created_at,
                    expires_at=invitation.expires_at,
                    status=state,
                )
            )
        return summaries

    async def revoke_invitation(
        self, invitation_id: UUID, client: AsyncMongoClient
    ) -> None:
        now = datetime.now(UTC)
        async with transaction(client) as session:
            invitation = await self._invitations.get_by_id(
                invitation_id, session=session
            )
            if (
                invitation is None
                or invitation.redeemed_at is not None
                or invitation.revoked_at is not None
                or invitation.expires_at <= now
            ):
                raise HTTPException(status_code=404, detail="NOT_FOUND")
            invitation.revoked_at = now
            await invitation.save(session=session)

    async def redeem_invitation(
        self,
        token: str,
        display_name: str,
        password: str,
        client: AsyncMongoClient,
    ) -> UserDocument:
        now = datetime.now(UTC)
        token_hash = hash_token(token)
        password_hash = hash_password(password)
        try:
            async with transaction(client) as session:
                invitation = await self._invitations.get_by_token_hash(
                    token_hash, session=session
                )
                if (
                    invitation is None
                    or invitation.redeemed_at is not None
                    or invitation.revoked_at is not None
                    or invitation.expires_at <= now
                ):
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail="VALIDATION_ERROR",
                    )

                if await self._users.get_by_email(
                    invitation.intended_email, session=session
                ) is not None:
                    raise HTTPException(
                        status_code=status.HTTP_409_CONFLICT,
                        detail="CONFLICT",
                    )

                invitation.redeemed_at = now
                await invitation.save(session=session)
                user = UserDocument(
                    normalized_email=invitation.intended_email,
                    display_name=display_name.strip(),
                    password_hash=password_hash,
                    role="user",
                    created_at=now,
                )
                await user.insert(session=session)
                return user
        except DuplicateKeyError as error:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="CONFLICT",
            ) from error

    async def list_users(
        self, page: int, page_size: int
    ) -> tuple[list[UserSummary], int]:
        users, total = await self._users.list_page(page, page_size)
        return [
            UserSummary(
                id=user.id,
                email=user.normalized_email,
                display_name=user.display_name,
                role=user.role,
                active=user.active,
                revision=user.revision,
                created_at=user.created_at,
            )
            for user in users
        ], total

    async def update_user(
        self,
        actor_id: UUID,
        target_id: UUID,
        update: UserUpdate,
        client: AsyncMongoClient,
    ) -> UserSummary:
        now = datetime.now(UTC)
        try:
            async with transaction(client) as session:
                actor = await self._users.get_by_id(actor_id, session=session)
                target = await self._users.get_by_id(target_id, session=session)
                if actor is None or actor.role != "admin" or not actor.active:
                    raise HTTPException(status_code=403, detail="FORBIDDEN")
                if target is None:
                    raise HTTPException(status_code=404, detail="NOT_FOUND")
                if target.revision != update.expected_revision:
                    raise HTTPException(status_code=409, detail="CONFLICT")

                new_active = target.active if update.active is None else update.active
                new_role = target.role if update.role is None else update.role
                if new_role == "admin" and not new_active:
                    raise HTTPException(status_code=400, detail="VALIDATION_ERROR")

                if target.role == "admin" and (new_role != "admin" or not new_active):
                    active_admin_count = await UserDocument.find(
                        UserDocument.role == "admin", UserDocument.active == True,
                        session=session,
                    ).count()
                    if active_admin_count <= 1:
                        raise HTTPException(status_code=409, detail="CONFLICT")

                if new_role == "admin" and target.role != "admin":
                    current_admin = await UserDocument.find_one(
                        UserDocument.role == "admin", session=session
                    )
                    if current_admin is not None and current_admin.id != target.id:
                        current_admin.role = "user"
                        current_admin.revision += 1
                        await self._users.save(current_admin, session)

                target.active = new_active
                target.role = new_role
                target.revision += 1
                await self._users.save(target, session)

                if not new_active:
                    await SessionDocument.get_pymongo_collection().update_many(
                        {"user_id": target.id, "revoked_at": None},
                        {"$set": {"revoked_at": now}},
                        session=session,
                    )

                return UserSummary(
                    id=target.id,
                    email=target.normalized_email,
                    display_name=target.display_name,
                    role=target.role,
                    active=target.active,
                    revision=target.revision,
                    created_at=target.created_at,
                )
        except DuplicateKeyError as error:
            raise HTTPException(status_code=409, detail="CONFLICT") from error
        except PyMongoError as error:
            if error.code == 112 or error.has_error_label("TransientTransactionError"):
                raise HTTPException(status_code=409, detail="CONFLICT") from error
            raise

    async def authenticate_request(self, request: Request) -> UserDocument:
        raw_token = request.cookies.get(SESSION_COOKIE)
        if not raw_token:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="UNAUTHENTICATED",
            )

        now = datetime.now(UTC)
        session_document = await SessionDocument.find_one(
            SessionDocument.token_hash == hash_token(raw_token)
        )
        if (
            session_document is None
            or session_document.revoked_at is not None
            or session_document.expires_at <= now
            or session_document.idle_expires_at <= now
        ):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="UNAUTHENTICATED",
            )

        user = await self._users.get_by_id(session_document.user_id)
        if user is None or not user.active:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="UNAUTHENTICATED",
            )

        request.state.auth_session = session_document
        if now - session_document.last_seen_at >= timedelta(
            minutes=SESSION_REFRESH_MINUTES
        ):
            session_document.last_seen_at = now
            session_document.idle_expires_at = min(
                now + timedelta(minutes=IDLE_SESSION_MINUTES),
                session_document.expires_at,
            )
            await session_document.save()
        return user

    def csrf_token(self, request: Request) -> str:
        token = request.cookies.get(CSRF_COOKIE)
        session_document: SessionDocument = request.state.auth_session
        if not token or not secrets.compare_digest(
            hash_token(token), session_document.csrf_token_hash
        ):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="FORBIDDEN",
            )
        return token

    def require_csrf_header(self, request: Request) -> None:
        token = self.csrf_token(request)
        header = request.headers.get("X-CSRF-Token", "")
        if not secrets.compare_digest(header, token):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="FORBIDDEN",
            )

    @staticmethod
    async def revoke_session(request: Request) -> None:
        session_document: SessionDocument = request.state.auth_session
        session_document.revoked_at = datetime.now(UTC)
        await session_document.save()


def get_auth_service(settings: Settings) -> AuthService:
    return AuthService(settings)


def invitation_url(settings: Settings, token: str) -> str:
    base_url = settings.APP_PUBLIC_URL.rstrip("/")
    return f"{base_url}/invite/{quote(token, safe='')}"
