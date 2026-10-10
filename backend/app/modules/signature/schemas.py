import base64
import binascii
from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


def validate_base64(value: str, minimum: int, maximum: int) -> str:
    try:
        decoded = base64.b64decode(value, validate=True)
    except (binascii.Error, ValueError, UnicodeError) as error:
        raise ValueError("Value must be valid base64") from error
    if base64.b64encode(decoded).decode("ascii") != value:
        raise ValueError("Value must use canonical base64 encoding")
    if not minimum <= len(decoded) <= maximum:
        raise ValueError("Decoded value has an invalid size")
    return value


class SignatureEnvelopeInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    envelope_version: Literal[1]
    kdf: Literal["argon2id"]
    memory_kib: Literal[65536]
    iterations: Literal[3]
    parallelism: Literal[1]
    salt: str = Field(min_length=24, max_length=24)
    wrapped_dek: str = Field(min_length=64, max_length=64)
    wrapping_iv: str = Field(min_length=16, max_length=16)
    ciphertext: str = Field(min_length=24, max_length=2796204)
    image_iv: str = Field(min_length=16, max_length=16)
    mime: Literal["image/png"]

    @field_validator("salt")
    @classmethod
    def validate_salt(cls, value: str) -> str:
        return validate_base64(value, 16, 16)

    @field_validator("wrapped_dek")
    @classmethod
    def validate_wrapped_key(cls, value: str) -> str:
        return validate_base64(value, 48, 48)

    @field_validator("wrapping_iv", "image_iv")
    @classmethod
    def validate_nonce(cls, value: str) -> str:
        return validate_base64(value, 12, 12)

    @field_validator("ciphertext")
    @classmethod
    def validate_ciphertext(cls, value: str) -> str:
        return validate_base64(value, 17, 2 * 1024 * 1024 + 16)

    @model_validator(mode="after")
    def require_distinct_nonces(self) -> "SignatureEnvelopeInput":
        if self.wrapping_iv == self.image_iv:
            raise ValueError("AES-GCM nonces must be distinct")
        return self


class SignatureEnvelopeResponse(SignatureEnvelopeInput):
    user_id: UUID
    updated_at: datetime


class SignatureUploadRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    password: str = Field(min_length=1, max_length=1024)
    envelope: SignatureEnvelopeInput


class SignaturePasswordChangeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    current_password: str = Field(min_length=1, max_length=1024)
    new_password: str = Field(min_length=12, max_length=1024)
    expected_envelope_updated_at: datetime | None = Field(...)
    replacement_envelope: SignatureEnvelopeInput | None = None


class SignaturePasswordChangeResponse(BaseModel):
    status: Literal["updated"]
    envelope_updated_at: datetime | None


class SigningAuthorizationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    password: str = Field(min_length=1, max_length=1024)
    document_id: UUID
    source_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    version_id: UUID


class SigningAuthorizationResponse(BaseModel):
    authorization_token: str = Field(min_length=40, max_length=128)
    expires_at: datetime


class SignedVersionResponse(BaseModel):
    document_id: UUID
    version_id: UUID
    version_number: int
    source_hash: str
    pdf_hash: str
    finalized_at: datetime
