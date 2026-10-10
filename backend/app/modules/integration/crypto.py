import base64
import secrets
from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from app.core.config import Settings
from app.modules.integration.documents import EncryptedValue


class EncryptionKeyUnavailable(RuntimeError):
    pass


class EncryptedValueInvalid(RuntimeError):
    pass


def _key_bytes(settings: Settings) -> bytes:
    if settings.INTEGRATION_ENCRYPTION_KEY is None:
        raise EncryptionKeyUnavailable
    return base64.b64decode(
        settings.INTEGRATION_ENCRYPTION_KEY.get_secret_value(), validate=True
    )


def encrypt_secret(plaintext: bytes, aad: bytes, settings: Settings) -> EncryptedValue:
    nonce = secrets.token_bytes(12)
    ciphertext = AESGCM(_key_bytes(settings)).encrypt(nonce, plaintext, aad)
    return EncryptedValue(
        key_id=settings.INTEGRATION_KEY_ID,
        nonce=base64.b64encode(nonce).decode("ascii"),
        ciphertext=base64.b64encode(ciphertext).decode("ascii"),
    )


def decrypt_secret(value: EncryptedValue, aad: bytes, settings: Settings) -> bytes:
    if value.key_id != settings.INTEGRATION_KEY_ID:
        raise EncryptionKeyUnavailable
    try:
        nonce = base64.b64decode(value.nonce, validate=True)
        ciphertext = base64.b64decode(value.ciphertext, validate=True)
        return AESGCM(_key_bytes(settings)).decrypt(nonce, ciphertext, aad)
    except InvalidTag as error:
        raise EncryptedValueInvalid from error
    except (ValueError, TypeError) as error:
        raise EncryptedValueInvalid from error
