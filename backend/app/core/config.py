from functools import lru_cache
from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit

from pydantic import SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


REPOSITORY_ROOT = Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=REPOSITORY_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    APP_ENV: Literal["development", "test", "production"] = "development"
    APP_TIMEZONE: str = "America/La_Paz"
    APP_PUBLIC_URL: str = "http://localhost:8080"
    API_PREFIX: str = "/api"
    COOKIE_SECURE: bool = False
    ALLOWED_ORIGINS: str = "http://localhost:8080,http://localhost:5173"

    MONGODB_URI: SecretStr = SecretStr("mongodb://localhost:27017/?replicaSet=rs0")
    MONGODB_DATABASE: str = "scesi_automation"
    MONGODB_REPLICA_SET: str = "rs0"

    INTEGRATION_ENCRYPTION_KEY: SecretStr | None = None
    INTEGRATION_KEY_ID: str = "local-v1"
    BOOTSTRAP_ADMIN_EMAIL: str | None = None
    BOOTSTRAP_ADMIN_PASSWORD: SecretStr | None = None
    GOOGLE_CLIENT_ID: str | None = None
    GOOGLE_CLIENT_SECRET: SecretStr | None = None
    GOOGLE_REDIRECT_URI: str = "http://localhost:8080/api/integrations/google/callback"
    GOOGLE_DRIVE_ROOT_ID: str | None = None

    LLM_PROVIDER: Literal["groq", "disabled"] = "disabled"
    GROQ_API_KEY: SecretStr | None = None
    GROQ_MODEL: str = "openai/gpt-oss-20b"
    GROQ_REASONING_EFFORT: Literal["low", "medium", "high"] = "low"
    GROQ_INCLUDE_REASONING: bool = False
    GROQ_LIMIT_RPM: int = 30
    GROQ_LIMIT_RPD: int = 1000
    GROQ_LIMIT_TPM: int = 8000
    GROQ_LIMIT_TPD: int = 200000
    GROQ_LIMIT_ITPM: int | None = None
    GROQ_LIMIT_OTPM: int | None = None
    LLM_REQUEST_TIMEOUT_SECONDS: int = 30
    LLM_MAX_INPUT_TOKENS: int = 2000
    LLM_MAX_OUTPUT_TOKENS: int = 750
    LLM_MAX_PASSES: int = 2
    LLM_MAX_ANALYSIS_TOKENS: int = 6000
    LLM_MAX_RETRIES: int = 2

    ARTIFACT_ROOT: Path = Path("/var/lib/scesi/artifacts")
    TEMPLATE_FOOTER_PHONES: str = "[]"
    TEMPLATE_FOOTER_URL: str = "https://scesi.org"
    TEMPLATE_QR_URL: str = "https://scesi.org"
    TEMPLATE_FOOTER_EMAIL: str = "contacto@scesi.org"
    TEMPLATE_FOOTER_ADDRESS: str = "Bloque central de la FCyT, último piso, UMSS"
    EMAIL_LOGO_URL: str = "https://i.imgur.com/npTbdR8.png"

    @field_validator("API_PREFIX")
    @classmethod
    def validate_api_prefix(cls, value: str) -> str:
        if not value.startswith("/") or value.endswith("/"):
            raise ValueError("API_PREFIX must start with / and not end with /")
        return value

    @field_validator("MONGODB_URI")
    @classmethod
    def validate_mongodb_uri(cls, value: SecretStr) -> SecretStr:
        parsed = urlsplit(value.get_secret_value())
        if parsed.scheme not in {"mongodb", "mongodb+srv"} or not parsed.hostname:
            raise ValueError("MONGODB_URI must be a valid MongoDB connection URI")
        return value

    @field_validator("MONGODB_DATABASE")
    @classmethod
    def validate_database_name(cls, value: str) -> str:
        if not value or any(character in value for character in '/\\."$*<>:|?'):
            raise ValueError("MONGODB_DATABASE contains unsupported characters")
        return value

    @field_validator("ALLOWED_ORIGINS")
    @classmethod
    def validate_allowed_origins(cls, value: str) -> str:
        origins = [origin.strip() for origin in value.split(",") if origin.strip()]
        if not origins or "*" in origins:
            raise ValueError("ALLOWED_ORIGINS must list explicit origins")
        for origin in origins:
            parsed = urlsplit(origin)
            if parsed.scheme not in {"http", "https"} or not parsed.hostname:
                raise ValueError("ALLOWED_ORIGINS contains an invalid origin")
            if parsed.path or parsed.query or parsed.fragment:
                raise ValueError("ALLOWED_ORIGINS entries must contain only an origin")
        return ",".join(origins)

    @field_validator(
        "INTEGRATION_ENCRYPTION_KEY",
        "BOOTSTRAP_ADMIN_EMAIL",
        "BOOTSTRAP_ADMIN_PASSWORD",
        "GOOGLE_CLIENT_ID",
        "GOOGLE_CLIENT_SECRET",
        "GOOGLE_DRIVE_ROOT_ID",
        "GROQ_API_KEY",
        "GROQ_LIMIT_ITPM",
        "GROQ_LIMIT_OTPM",
        mode="before",
    )
    @classmethod
    def normalize_empty_optional(cls, value: object) -> object:
        return None if value == "" else value

    @field_validator("GROQ_LIMIT_RPM", "GROQ_LIMIT_RPD", "GROQ_LIMIT_TPM", "GROQ_LIMIT_TPD")
    @classmethod
    def validate_positive_quota(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("Groq quota limits must be positive")
        return value

    @model_validator(mode="after")
    def validate_runtime_security(self) -> "Settings":
        if self.APP_ENV == "production" and not self.COOKIE_SECURE:
            raise ValueError("COOKIE_SECURE must be enabled in production")
        if self.LLM_MAX_PASSES <= 0 or self.LLM_MAX_RETRIES < 0:
            raise ValueError("LLM pass and retry limits are invalid")
        if min(
            self.LLM_MAX_INPUT_TOKENS,
            self.LLM_MAX_OUTPUT_TOKENS,
            self.LLM_MAX_ANALYSIS_TOKENS,
            self.LLM_REQUEST_TIMEOUT_SECONDS,
        ) <= 0:
            raise ValueError("LLM token and timeout limits must be positive")
        return self

    @property
    def cors_origins(self) -> list[str]:
        return self.ALLOWED_ORIGINS.split(",")


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
API_PREFIX = settings.API_PREFIX
