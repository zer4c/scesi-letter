import base64
import hashlib
import json
import secrets
from datetime import UTC, datetime, timedelta
from urllib.parse import urlencode
from uuid import UUID, uuid4

import httpx
from fastapi import HTTPException
from pydantic import EmailStr, TypeAdapter
from pymongo import AsyncMongoClient, ReturnDocument

from app.core.config import Settings
from app.core.database import transaction
from app.modules.auth.documents import UserDocument
from app.modules.integration.crypto import (
    EncryptedValueInvalid,
    EncryptionKeyUnavailable,
    decrypt_secret,
    encrypt_secret,
)
from app.modules.integration.documents import (
    EncryptedValue,
    IntegrationConnectionDocument,
    OAuthStateDocument,
)
from app.modules.integration.schemas import (
    ConnectionMutationResponse,
    DriveRootRequest,
    GoogleAuthorizationResponse,
    GoogleConnectionRequest,
    IntegrationConnectionsResponse,
    IntegrationConnectionStatus,
)

GOOGLE_AUTHORIZATION_ENDPOINT = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_ENDPOINT = "https://oauth2.googleapis.com/token"
GOOGLE_USERINFO_ENDPOINT = "https://openidconnect.googleapis.com/v1/userinfo"
GOOGLE_REVOKE_ENDPOINT = "https://oauth2.googleapis.com/revoke"
GOOGLE_DRIVE_FILES_ENDPOINT = "https://www.googleapis.com/drive/v3/files"
OAUTH_STATE_TTL = timedelta(minutes=10)
HTTP_TIMEOUT_SECONDS = 10
IDENTITY_SCOPES = {
    "email",
    "openid",
}
PROVIDER_SCOPES = {
    "gmail": "https://www.googleapis.com/auth/gmail.send",
    "drive": "https://www.googleapis.com/auth/drive.file",
}
GMAIL_SEND_SCOPE = "https://www.googleapis.com/auth/gmail.send"
EMAIL_ADAPTER = TypeAdapter(EmailStr)


class GoogleConnectionService:
    def __init__(
        self,
        settings: Settings,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._settings = settings
        self._transport = transport

    async def list_connections(self, actor: UserDocument) -> IntegrationConnectionsResponse:
        institutional_filter = (
            {"mode": "institutional"}
            if actor.role == "admin"
            else {"mode": "institutional", "kind": "gmail"}
        )
        query: dict[str, object] = {
            "$or": [
                {"mode": "personal", "owner_user_id": actor.id},
                institutional_filter,
            ]
        }
        cursor = IntegrationConnectionDocument.get_pymongo_collection().find(query).sort(
            [("mode", 1), ("kind", 1), ("google_account", 1)]
        )
        items = [
            IntegrationConnectionDocument.model_validate(raw) async for raw in cursor
        ]
        return IntegrationConnectionsResponse(
            connections=[self._status(item) for item in items]
        )

    async def create_authorization(
        self,
        request: GoogleConnectionRequest,
        actor: UserDocument,
    ) -> GoogleAuthorizationResponse:
        self._require_oauth_config()
        owner_user_id = self._connection_owner(request.kind, request.mode, actor)
        now = datetime.now(UTC)
        state = secrets.token_urlsafe(32)
        state_hash = self._hash(state)
        verifier = secrets.token_urlsafe(64)
        challenge = base64.urlsafe_b64encode(
            hashlib.sha256(verifier.encode("ascii")).digest()
        ).decode("ascii").rstrip("=")
        scopes = sorted({*IDENTITY_SCOPES, PROVIDER_SCOPES[request.kind]})
        encrypted_verifier = encrypt_secret(
            verifier.encode("ascii"),
            self._state_aad(state_hash, actor.id),
            self._settings,
        )
        expires_at = now + OAUTH_STATE_TTL
        await OAuthStateDocument(
            state_hash=state_hash,
            user_id=actor.id,
            kind=request.kind,
            mode=request.mode,
            scopes=scopes,
            encrypted_code_verifier=encrypted_verifier,
            expires_at=expires_at,
        ).insert()
        query = urlencode(
            {
                "client_id": self._settings.GOOGLE_CLIENT_ID,
                "redirect_uri": self._settings.GOOGLE_REDIRECT_URI,
                "response_type": "code",
                "scope": " ".join(scopes),
                "state": state,
                "code_challenge": challenge,
                "code_challenge_method": "S256",
                "access_type": "offline",
                "prompt": "consent",
                "include_granted_scopes": "false",
            }
        )
        return GoogleAuthorizationResponse(
            authorization_url=f"{GOOGLE_AUTHORIZATION_ENDPOINT}?{query}",
            expires_at=expires_at,
        )

    async def complete_authorization(
        self,
        code: str,
        state: str,
        actor: UserDocument,
        client: AsyncMongoClient,
    ) -> IntegrationConnectionStatus:
        self._require_oauth_config()
        if not code or len(code) > 4096 or not state or len(state) > 256:
            raise HTTPException(status_code=400, detail="VALIDATION_ERROR")
        state_hash = self._hash(state)
        now = datetime.now(UTC)
        async with transaction(client) as session:
            raw_state = await OAuthStateDocument.get_pymongo_collection().find_one_and_update(
                {
                    "state_hash": state_hash,
                    "user_id": actor.id,
                    "expires_at": {"$gt": now},
                    "used_at": None,
                },
                {"$set": {"used_at": now}},
                return_document=ReturnDocument.BEFORE,
                session=session,
            )
            if raw_state is None:
                raise HTTPException(status_code=400, detail="OAUTH_STATE_INVALID")
            oauth_state = OAuthStateDocument.model_validate(raw_state)
            owner_user_id = self._connection_owner(
                oauth_state.kind, oauth_state.mode, actor
            )
            try:
                verifier = decrypt_secret(
                    oauth_state.encrypted_code_verifier,
                    self._state_aad(oauth_state.state_hash, oauth_state.user_id),
                    self._settings,
                ).decode("ascii")
            except EncryptionKeyUnavailable as error:
                raise HTTPException(
                    status_code=503, detail="INTEGRATION_KEY_UNAVAILABLE"
                ) from error
            except (EncryptedValueInvalid, UnicodeDecodeError) as error:
                raise HTTPException(status_code=400, detail="OAUTH_STATE_INVALID") from error

        tokens = await self._exchange_code(code, verifier)
        returned_scopes = self._parse_scopes(tokens.get("scope"))
        if returned_scopes != set(oauth_state.scopes):
            raise HTTPException(status_code=403, detail="GOOGLE_SCOPE_MISMATCH")
        if not tokens.get("refresh_token"):
            raise HTTPException(status_code=502, detail="GOOGLE_REAUTH_REQUIRED")
        email = await self._get_google_account(tokens["access_token"])
        expires_at = self._token_expiry(tokens)

        selector = {
            "kind": oauth_state.kind,
            "mode": oauth_state.mode,
            "owner_user_id": owner_user_id,
        }
        async with transaction(client) as session:
            current_actor = await UserDocument.find_one(
                UserDocument.id == actor.id,
                UserDocument.active == True,
                session=session,
            )
            if current_actor is None:
                raise HTTPException(status_code=401, detail="UNAUTHENTICATED")
            owner_user_id = self._connection_owner(
                oauth_state.kind, oauth_state.mode, current_actor
            )
            selector["owner_user_id"] = owner_user_id
            connection_collection = IntegrationConnectionDocument.get_pymongo_collection()
            existing = await connection_collection.find_one(selector, session=session)
            connection_id = existing["_id"] if existing else uuid4()
            connection = IntegrationConnectionDocument(
                id=connection_id,
                kind=oauth_state.kind,
                mode=oauth_state.mode,
                owner_user_id=owner_user_id,
                google_account=email,
                encrypted_tokens=self._encrypt_tokens(
                    tokens,
                    connection_id,
                    oauth_state.kind,
                    oauth_state.mode,
                    owner_user_id,
                ),
                scopes=sorted(returned_scopes),
                status="active",
                root_folder_id=(existing.get("root_folder_id") if existing else None),
                expires_at=expires_at,
                connected_at=(existing.get("connected_at", now) if existing else now),
                updated_at=now,
            )
            await connection_collection.replace_one(
                selector,
                connection.model_dump(by_alias=True),
                upsert=True,
                session=session,
            )
        return self._status(connection)

    async def disconnect(
        self,
        connection_id: UUID,
        actor: UserDocument,
        client: AsyncMongoClient,
    ) -> ConnectionMutationResponse:
        connection = await self._get_authorized_connection(connection_id, actor)
        try:
            tokens = self._decrypt_tokens(connection)
            revoke_token = tokens.get("refresh_token") or tokens.get("access_token")
            if revoke_token:
                async with self._http_client() as http:
                    await http.post(
                        GOOGLE_REVOKE_ENDPOINT,
                        data={"token": revoke_token},
                        timeout=HTTP_TIMEOUT_SECONDS,
                    )
        except Exception:
            pass
        async with transaction(client) as session:
            current_actor = await UserDocument.find_one(
                UserDocument.id == actor.id,
                UserDocument.active == True,
                session=session,
            )
            if current_actor is None or not self._can_access(connection, current_actor):
                raise HTTPException(status_code=403, detail="FORBIDDEN")
            deleted = await IntegrationConnectionDocument.get_pymongo_collection().delete_one(
                {
                    "_id": connection.id,
                    "updated_at": connection.updated_at,
                    "encrypted_tokens": connection.encrypted_tokens.model_dump(),
                },
                session=session,
            )
            if deleted.deleted_count != 1:
                raise HTTPException(status_code=409, detail="CONFLICT")
        return ConnectionMutationResponse(
            status="disconnected", connection_id=connection_id
        )

    async def select_drive_root(
        self,
        connection_id: UUID,
        payload: DriveRootRequest,
        actor: UserDocument,
        client: AsyncMongoClient,
    ) -> ConnectionMutationResponse:
        connection = await self._get_authorized_connection(connection_id, actor)
        if connection.kind != "drive" or connection.mode != "institutional":
            raise HTTPException(status_code=409, detail="CONFLICT")
        access_token = await self.get_access_token(connection, actor)
        async with self._http_client() as http:
            try:
                response = await http.get(
                    f"{GOOGLE_DRIVE_FILES_ENDPOINT}/{payload.folder_id}",
                    headers={"Authorization": f"Bearer {access_token}"},
                    params={"fields": "id,mimeType,trashed", "supportsAllDrives": "true"},
                    timeout=HTTP_TIMEOUT_SECONDS,
                )
            except httpx.RequestError as error:
                raise HTTPException(status_code=503, detail="GOOGLE_UNAVAILABLE") from error
        if response.status_code == 401:
            raise HTTPException(status_code=403, detail="GOOGLE_SCOPE_MISMATCH")
        if response.status_code == 403:
            raise HTTPException(status_code=403, detail="GOOGLE_SCOPE_MISMATCH")
        if response.status_code == 404:
            raise HTTPException(status_code=404, detail="NOT_FOUND")
        if response.is_error:
            raise HTTPException(status_code=502, detail="GOOGLE_UNAVAILABLE")
        try:
            details = response.json()
        except ValueError as error:
            raise HTTPException(status_code=502, detail="GOOGLE_UNAVAILABLE") from error
        if (
            details.get("id") != payload.folder_id
            or details.get("mimeType") != "application/vnd.google-apps.folder"
            or details.get("trashed") is True
        ):
            raise HTTPException(status_code=422, detail="VALIDATION_ERROR")
        async with transaction(client) as session:
            current_admin = await UserDocument.find_one(
                UserDocument.id == actor.id,
                UserDocument.active == True,
                UserDocument.role == "admin",
                session=session,
            )
            if current_admin is None:
                raise HTTPException(status_code=403, detail="FORBIDDEN")
            saved_root = await IntegrationConnectionDocument.get_pymongo_collection().update_one(
                {
                    "_id": connection.id,
                    "kind": "drive",
                    "mode": "institutional",
                    "status": "active",
                },
                {
                    "$set": {
                        "root_folder_id": payload.folder_id,
                        "updated_at": datetime.now(UTC),
                    }
                },
                session=session,
            )
            if saved_root.matched_count != 1:
                raise HTTPException(status_code=409, detail="CONFLICT")
        return ConnectionMutationResponse(
            status="root_selected", connection_id=connection_id
        )

    async def get_access_token(
        self,
        connection: IntegrationConnectionDocument,
        actor: UserDocument | None,
    ) -> str:
        if actor is None and not (
            connection.mode == "institutional"
            and (
                connection.kind == "drive"
                or (connection.kind == "gmail" and GMAIL_SEND_SCOPE in connection.scopes)
            )
        ):
            raise HTTPException(status_code=404, detail="NOT_FOUND")
        if actor is not None and not self._can_access(connection, actor):
            raise HTTPException(status_code=404, detail="NOT_FOUND")
        if connection.status != "active":
            raise HTTPException(status_code=409, detail="GOOGLE_REAUTH_REQUIRED")
        tokens = self._decrypt_tokens(connection)
        if connection.expires_at > datetime.now(UTC) + timedelta(seconds=60):
            return tokens["access_token"]
        refresh_token = tokens.get("refresh_token")
        if not refresh_token:
            await self._mark_reauthorization(connection)
            raise HTTPException(status_code=409, detail="GOOGLE_REAUTH_REQUIRED")
        try:
            refreshed = await self._refresh_tokens(refresh_token)
        except HTTPException as error:
            if error.detail == "GOOGLE_REAUTH_REQUIRED":
                await self._mark_reauthorization(connection)
            raise
        if not refreshed.get("access_token"):
            await self._mark_reauthorization(connection)
            raise HTTPException(status_code=409, detail="GOOGLE_REAUTH_REQUIRED")
        refreshed["refresh_token"] = refreshed.get("refresh_token", refresh_token)
        refreshed.setdefault("token_type", "Bearer")
        refreshed.setdefault("scope", " ".join(connection.scopes))
        encrypted_tokens = self._encrypt_tokens(
            refreshed,
            connection.id,
            connection.kind,
            connection.mode,
            connection.owner_user_id,
        )
        updated_at = datetime.now(UTC)
        result = await IntegrationConnectionDocument.get_pymongo_collection().update_one(
            {
                "_id": connection.id,
                "status": "active",
                "updated_at": connection.updated_at,
                "encrypted_tokens": connection.encrypted_tokens.model_dump(),
            },
            {
                "$set": {
                    "encrypted_tokens": encrypted_tokens.model_dump(),
                    "expires_at": self._token_expiry(refreshed),
                    "updated_at": updated_at,
                }
            },
        )
        if result.matched_count != 1:
            latest = await IntegrationConnectionDocument.find_one(
                IntegrationConnectionDocument.id == connection.id
            )
            if (
                latest is not None
                and latest.status == "active"
                and latest.expires_at > datetime.now(UTC) + timedelta(seconds=60)
            ):
                return self._decrypt_tokens(latest)["access_token"]
            raise HTTPException(status_code=409, detail="CONFLICT")
        return refreshed["access_token"]

    async def _exchange_code(self, code: str, verifier: str) -> dict[str, object]:
        data = {
            "code": code,
            "client_id": self._settings.GOOGLE_CLIENT_ID,
            "client_secret": self._settings.GOOGLE_CLIENT_SECRET.get_secret_value(),
            "redirect_uri": self._settings.GOOGLE_REDIRECT_URI,
            "grant_type": "authorization_code",
            "code_verifier": verifier,
        }
        return await self._token_request(data)

    async def _refresh_tokens(self, refresh_token: str) -> dict[str, object]:
        data = {
            "refresh_token": refresh_token,
            "client_id": self._settings.GOOGLE_CLIENT_ID,
            "client_secret": self._settings.GOOGLE_CLIENT_SECRET.get_secret_value(),
            "grant_type": "refresh_token",
        }
        try:
            return await self._token_request(data)
        except HTTPException as error:
            if error.status_code in {400, 401}:
                raise HTTPException(status_code=409, detail="GOOGLE_REAUTH_REQUIRED") from error
            raise

    async def _token_request(self, data: dict[str, object]) -> dict[str, object]:
        async with self._http_client() as http:
            try:
                response = await http.post(
                    GOOGLE_TOKEN_ENDPOINT,
                    data=data,
                    timeout=HTTP_TIMEOUT_SECONDS,
                )
            except httpx.RequestError as error:
                raise HTTPException(status_code=503, detail="GOOGLE_UNAVAILABLE") from error
        if response.is_error:
            if response.status_code in {400, 401}:
                raise HTTPException(status_code=400, detail="GOOGLE_AUTHORIZATION_FAILED")
            raise HTTPException(status_code=502, detail="GOOGLE_TOKEN_FAILED")
        try:
            payload = response.json()
            if (
                not isinstance(payload, dict)
                or not isinstance(payload.get("access_token"), str)
                or not payload["access_token"]
                or len(payload["access_token"]) > 8192
                or str(payload.get("token_type", "Bearer")).casefold() != "bearer"
                or not isinstance(payload.get("expires_in"), int)
                or not 1 <= payload["expires_in"] <= 86400
            ):
                raise ValueError
            return payload
        except (ValueError, TypeError) as error:
            raise HTTPException(status_code=502, detail="GOOGLE_TOKEN_INVALID") from error

    async def _get_google_account(self, access_token: str) -> str:
        async with self._http_client() as http:
            try:
                response = await http.get(
                    GOOGLE_USERINFO_ENDPOINT,
                    headers={"Authorization": f"Bearer {access_token}"},
                    timeout=HTTP_TIMEOUT_SECONDS,
                )
            except httpx.RequestError as error:
                raise HTTPException(status_code=503, detail="GOOGLE_UNAVAILABLE") from error
        if response.is_error:
            raise HTTPException(status_code=502, detail="GOOGLE_IDENTITY_FAILED")
        try:
            profile = response.json()
            email = profile["email"]
            if (
                not isinstance(email, str)
                or len(email) > 254
                or profile.get("email_verified") is not True
                or not profile.get("sub")
            ):
                raise ValueError
            return str(EMAIL_ADAPTER.validate_python(email).casefold())
        except (KeyError, ValueError, TypeError) as error:
            raise HTTPException(status_code=502, detail="GOOGLE_IDENTITY_INVALID") from error

    async def _get_authorized_connection(
        self,
        connection_id: UUID,
        actor: UserDocument,
    ) -> IntegrationConnectionDocument:
        connection = await IntegrationConnectionDocument.find_one(
            IntegrationConnectionDocument.id == connection_id
        )
        if connection is None:
            raise HTTPException(status_code=404, detail="NOT_FOUND")
        if not self._can_access(connection, actor):
            raise HTTPException(status_code=404, detail="NOT_FOUND")
        return connection

    @staticmethod
    def _can_access(
        connection: IntegrationConnectionDocument,
        actor: UserDocument,
    ) -> bool:
        return (
            connection.mode == "personal"
            and connection.owner_user_id == actor.id
        ) or (connection.mode == "institutional" and actor.role == "admin")

    async def _mark_reauthorization(
        self,
        connection: IntegrationConnectionDocument,
    ) -> None:
        await IntegrationConnectionDocument.get_pymongo_collection().update_one(
            {
                "_id": connection.id,
                "status": "active",
                "updated_at": connection.updated_at,
            },
            {
                "$set": {
                    "status": "reauthorization_required",
                    "updated_at": datetime.now(UTC),
                }
            },
        )

    def _encrypt_tokens(
        self,
        tokens: dict[str, object],
        connection_id: UUID,
        kind: str,
        mode: str,
        owner_user_id: UUID | None,
    ) -> EncryptedValue:
        serialized = json.dumps(
            tokens, separators=(",", ":"), sort_keys=True
        ).encode("utf-8")
        return encrypt_secret(
            serialized,
            self._connection_aad(connection_id, kind, mode, owner_user_id),
            self._settings,
        )

    def _decrypt_tokens(self, connection: IntegrationConnectionDocument) -> dict[str, str]:
        try:
            raw = decrypt_secret(
                connection.encrypted_tokens,
                self._connection_aad(
                    connection.id,
                    connection.kind,
                    connection.mode,
                    connection.owner_user_id,
                ),
                self._settings,
            )
            tokens = json.loads(raw)
            if (
                not isinstance(tokens, dict)
                or not isinstance(tokens.get("access_token"), str)
                or not tokens["access_token"]
            ):
                raise ValueError
            return tokens
        except (EncryptedValueInvalid, EncryptionKeyUnavailable, ValueError, TypeError) as error:
            raise HTTPException(status_code=503, detail="INTEGRATION_KEY_UNAVAILABLE") from error

    def _http_client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(transport=self._transport, follow_redirects=False)

    def _require_oauth_config(self) -> None:
        if self._settings.INTEGRATION_ENCRYPTION_KEY is None:
            raise HTTPException(status_code=503, detail="INTEGRATION_KEY_UNAVAILABLE")
        if not self._settings.GOOGLE_CLIENT_ID or not self._settings.GOOGLE_CLIENT_SECRET:
            raise HTTPException(status_code=503, detail="INTEGRATION_UNAVAILABLE")

    @staticmethod
    def _connection_owner(
        kind: str,
        mode: str,
        actor: UserDocument,
    ) -> UUID | None:
        if mode == "institutional":
            if actor.role != "admin":
                raise HTTPException(status_code=403, detail="FORBIDDEN")
            return None
        if kind == "drive":
            raise HTTPException(status_code=422, detail="VALIDATION_ERROR")
        return actor.id

    @staticmethod
    def _status(
        connection: IntegrationConnectionDocument,
    ) -> IntegrationConnectionStatus:
        return IntegrationConnectionStatus(
            id=connection.id,
            kind=connection.kind,
            mode=connection.mode,
            google_account=connection.google_account,
            scopes=connection.scopes,
            status=connection.status,
            root_folder_id=connection.root_folder_id,
            expires_at=connection.expires_at,
            connected_at=connection.connected_at,
            updated_at=connection.updated_at,
        )

    @staticmethod
    def _state_aad(state_hash: str, user_id: UUID) -> bytes:
        return f"oauth-state:v1:{state_hash}:{user_id}".encode("ascii")

    @staticmethod
    def _connection_aad(
        connection_id: UUID,
        kind: str,
        mode: str,
        owner_user_id: UUID | None,
    ) -> bytes:
        owner = str(owner_user_id) if owner_user_id else "institutional"
        return f"google-connection:v1:{connection_id}:{kind}:{mode}:{owner}".encode(
            "ascii"
        )

    @staticmethod
    def _hash(value: str) -> str:
        return hashlib.sha256(value.encode("utf-8")).hexdigest()

    @staticmethod
    def _parse_scopes(value: object) -> set[str]:
        if not isinstance(value, str):
            return set()
        return {scope for scope in value.split() if scope}

    @staticmethod
    def _token_expiry(tokens: dict[str, object]) -> datetime:
        seconds = tokens.get("expires_in")
        if not isinstance(seconds, int) or not 1 <= seconds <= 86400:
            raise HTTPException(status_code=502, detail="GOOGLE_TOKEN_INVALID")
        return datetime.now(UTC) + timedelta(seconds=seconds)
