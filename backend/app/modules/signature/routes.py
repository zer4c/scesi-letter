from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Request
from pymongo import AsyncMongoClient

from app.core.database import get_mongo_client, transaction
from app.modules.auth.documents import (
    SessionDocument,
    SignatureEnvelopeDocument,
    UserDocument,
)
from app.modules.auth.routes import auth_service, require_current_user
from app.modules.auth.passwords import hash_password, verify_password
from app.modules.auth.services import AuthService, hash_token
from app.modules.signature.schemas import (
    SignatureEnvelopeResponse,
    SignaturePasswordChangeRequest,
    SignaturePasswordChangeResponse,
    SignatureUploadRequest,
)


router = APIRouter(prefix="/signature", tags=["signature"])
password_router = APIRouter(prefix="/auth/password", tags=["authentication"])


def utc_now_milliseconds() -> datetime:
    now = datetime.now(UTC)
    return now.replace(microsecond=(now.microsecond // 1000) * 1000)


def envelope_response(envelope: SignatureEnvelopeDocument) -> SignatureEnvelopeResponse:
    fields = (
        "envelope_version",
        "kdf",
        "memory_kib",
        "iterations",
        "parallelism",
        "salt",
        "wrapped_dek",
        "wrapping_iv",
        "ciphertext",
        "image_iv",
        "mime",
    )
    values = {name: getattr(envelope, name) for name in fields}
    values.update(user_id=envelope.user_id, updated_at=envelope.updated_at)
    return SignatureEnvelopeResponse.model_validate(values)


@router.get("", response_model=SignatureEnvelopeResponse)
async def get_signature(
    user: UserDocument = Depends(require_current_user),
) -> SignatureEnvelopeResponse:
    envelope = await SignatureEnvelopeDocument.find_one(
        SignatureEnvelopeDocument.user_id == user.id
    )
    if envelope is None:
        raise HTTPException(status_code=404, detail="NOT_FOUND")
    return envelope_response(envelope)


@router.put("", response_model=SignatureEnvelopeResponse)
async def put_signature(
    payload: SignatureUploadRequest,
    request: Request,
    user: UserDocument = Depends(require_current_user),
    service: AuthService = Depends(auth_service),
    client: AsyncMongoClient = Depends(get_mongo_client),
) -> SignatureEnvelopeResponse:
    service.require_csrf_header(request)
    if not verify_password(user.password_hash, payload.password):
        raise HTTPException(status_code=401, detail="UNAUTHENTICATED")
    envelope = SignatureEnvelopeDocument(
        user_id=user.id,
        **payload.envelope.model_dump(),
        updated_at=utc_now_milliseconds(),
    )
    async with transaction(client) as session:
        user_update = await UserDocument.get_pymongo_collection().update_one(
            {
                "_id": user.id,
                "active": True,
                "credential_revision": user.credential_revision,
                "password_hash": user.password_hash,
            },
            {"$inc": {"credential_revision": 1}},
            session=session,
        )
        if user_update.matched_count != 1:
            raise HTTPException(status_code=409, detail="REVISION_CONFLICT")
        await SignatureEnvelopeDocument.get_pymongo_collection().replace_one(
            {"user_id": user.id},
            envelope.model_dump(by_alias=True),
            upsert=True,
            session=session,
        )
    return envelope_response(envelope)


@password_router.post("/change", response_model=SignaturePasswordChangeResponse)
async def change_password(
    payload: SignaturePasswordChangeRequest,
    request: Request,
    user: UserDocument = Depends(require_current_user),
    service: AuthService = Depends(auth_service),
    client: AsyncMongoClient = Depends(get_mongo_client),
) -> SignaturePasswordChangeResponse:
    service.require_csrf_header(request)
    if not verify_password(user.password_hash, payload.current_password):
        raise HTTPException(status_code=401, detail="UNAUTHENTICATED")

    envelope_collection = SignatureEnvelopeDocument.get_pymongo_collection()
    now = utc_now_milliseconds()
    async with transaction(client) as session:
        existing_envelope = await envelope_collection.find_one(
            {"user_id": user.id}, session=session
        )
        envelope_updated_at = (
            existing_envelope.get("updated_at") if existing_envelope else None
        )
        if envelope_updated_at != payload.expected_envelope_updated_at:
            raise HTTPException(status_code=409, detail="REVISION_CONFLICT")
        if existing_envelope and payload.replacement_envelope is None:
            raise HTTPException(status_code=409, detail="SIGNATURE_REWRAP_REQUIRED")
        users = UserDocument.get_pymongo_collection()
        sessions = SessionDocument.get_pymongo_collection()
        user_update = await users.update_one(
            {
                "_id": user.id,
                "active": True,
                "credential_revision": user.credential_revision,
                "password_hash": user.password_hash,
            },
            {
                "$set": {"password_hash": hash_password(payload.new_password)},
                "$inc": {"credential_revision": 1},
            },
            session=session,
        )
        if user_update.matched_count != 1:
            raise HTTPException(status_code=409, detail="REVISION_CONFLICT")
        if payload.replacement_envelope is not None:
            replacement = SignatureEnvelopeDocument(
                user_id=user.id,
                **payload.replacement_envelope.model_dump(),
                updated_at=now,
            )
            await envelope_collection.replace_one(
                {"user_id": user.id}, replacement.model_dump(by_alias=True),
                upsert=True,
                session=session,
            )
        session_token = request.cookies.get("scesi_session", "")
        await sessions.update_many(
            {"user_id": user.id, "token_hash": {"$ne": hash_token(session_token)}},
            {"$set": {"revoked_at": now}},
            session=session,
        )
    return SignaturePasswordChangeResponse(
        status="updated",
        envelope_updated_at=now if payload.replacement_envelope is not None else None,
    )
