import base64
from datetime import UTC, datetime
from types import SimpleNamespace

from fastapi import HTTPException
import pytest
from pydantic import SecretStr, ValidationError

from app.core.config import Settings
from app.modules.integration.crypto import (
    EncryptedValueInvalid,
    EncryptionKeyUnavailable,
    decrypt_secret,
    encrypt_secret,
)
from app.modules.integration.services import GoogleConnectionService


def test_google_tokens_are_aead_encrypted_and_bound_to_connection() -> None:
    settings = Settings(
        INTEGRATION_ENCRYPTION_KEY=SecretStr(base64.b64encode(b"k" * 32).decode())
    )
    plaintext = b"synthetic-refresh-token"
    aad = b"connection:synthetic"

    encrypted = encrypt_secret(plaintext, aad, settings)

    assert plaintext not in base64.b64decode(encrypted.ciphertext)
    assert decrypt_secret(encrypted, aad, settings) == plaintext
    with pytest.raises(EncryptedValueInvalid):
        decrypt_secret(encrypted, b"connection:other", settings)


def test_google_encryption_fails_closed_without_key_or_matching_key_id() -> None:
    key = base64.b64encode(b"k" * 32).decode()
    settings = Settings(INTEGRATION_ENCRYPTION_KEY=SecretStr(key))
    encrypted = encrypt_secret(b"token", b"aad", settings)

    with pytest.raises(EncryptionKeyUnavailable):
        encrypt_secret(b"token", b"aad", Settings())
    with pytest.raises(EncryptionKeyUnavailable):
        decrypt_secret(
            encrypted.model_copy(update={"key_id": "retired-key"}), b"aad", settings
        )


def test_integration_key_requires_canonical_base64_for_32_bytes() -> None:
    with pytest.raises(ValidationError):
        Settings(INTEGRATION_ENCRYPTION_KEY=SecretStr("not-a-key"))


def test_google_redirect_requires_trusted_callback_origin_and_path() -> None:
    with pytest.raises(ValidationError):
        Settings(GOOGLE_REDIRECT_URI="http://example.com/api/integrations/google/callback")
    with pytest.raises(ValidationError):
        Settings(GOOGLE_REDIRECT_URI="https://localhost/api/other/callback")


def test_google_connection_policy_separates_personal_and_institutional() -> None:
    admin = SimpleNamespace(id="admin-id", role="admin")
    user = SimpleNamespace(id="user-id", role="user")
    service = GoogleConnectionService(Settings())

    assert service._connection_owner("gmail", "personal", user) == user.id
    assert service._connection_owner("gmail", "institutional", admin) is None
    assert service._connection_owner("drive", "institutional", admin) is None
    with pytest.raises(HTTPException) as error:
        service._connection_owner("gmail", "institutional", user)
    assert error.value.status_code == 403
    with pytest.raises(HTTPException) as error:
        service._connection_owner("drive", "personal", user)
    assert error.value.status_code == 422


def test_google_scope_parser_and_expiry_bounds() -> None:
    assert GoogleConnectionService._parse_scopes("openid email scope-a") == {
        "openid",
        "email",
        "scope-a",
    }
    assert GoogleConnectionService._parse_scopes(None) == set()
    assert GoogleConnectionService._token_expiry({"expires_in": 60}) > datetime.now(UTC)
    with pytest.raises(HTTPException):
        GoogleConnectionService._token_expiry({"expires_in": 0})
