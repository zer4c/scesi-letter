from datetime import UTC, datetime
import hashlib
import hmac

from fastapi import HTTPException, status
from pymongo import ReturnDocument
from pymongo.errors import DuplicateKeyError

from app.core.config import Settings
from app.modules.auth.documents import LoginAttemptDocument


WINDOW_SECONDS = 15 * 60
ACCOUNT_FAILURE_LIMIT = 5
NETWORK_FAILURE_LIMIT = 30


class LoginRateLimiter:
    def __init__(self, settings: Settings) -> None:
        self._key = settings.APP_RATE_LIMIT_KEY.get_secret_value().encode("utf-8")

    def _digest(self, category: str, value: str) -> str:
        message = f"{category}:{value}".encode("utf-8")
        return hmac.new(self._key, message, hashlib.sha256).hexdigest()

    async def ensure_allowed(self, email: str, network_address: str) -> None:
        now = datetime.now(UTC)
        window_start = int(now.timestamp()) // WINDOW_SECONDS * WINDOW_SECONDS
        keys = (
            (self._digest("email", email.casefold()), ACCOUNT_FAILURE_LIMIT),
            (self._digest("network", network_address), NETWORK_FAILURE_LIMIT),
        )
        for key_hash, limit in keys:
            attempt = await LoginAttemptDocument.find_one(
                LoginAttemptDocument.key_hash == key_hash,
                LoginAttemptDocument.window_start == window_start,
            )
            if attempt is not None and attempt.failures >= limit:
                retry_after = window_start + WINDOW_SECONDS - int(now.timestamp())
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail="RATE_LIMITED",
                    headers={"Retry-After": str(max(retry_after, 1))},
                )

    async def record_failure(self, email: str, network_address: str) -> None:
        now = datetime.now(UTC)
        window_start = int(now.timestamp()) // WINDOW_SECONDS * WINDOW_SECONDS
        expires_at = datetime.fromtimestamp(
            window_start + (2 * WINDOW_SECONDS), tz=UTC
        )
        collection = LoginAttemptDocument.get_pymongo_collection()
        for category, value in (("email", email.casefold()), ("network", network_address)):
            key_hash = self._digest(category, value)
            selector = {"key_hash": key_hash, "window_start": window_start}
            update = {
                "$inc": {"failures": 1},
                "$setOnInsert": {"expires_at": expires_at},
            }
            try:
                await collection.find_one_and_update(
                    selector,
                    update,
                    upsert=True,
                    return_document=ReturnDocument.AFTER,
                )
            except DuplicateKeyError:
                await collection.find_one_and_update(selector, {"$inc": {"failures": 1}})
