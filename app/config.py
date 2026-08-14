"""
Centralized configuration. Every secret and connection string is read from
the environment — nothing is hardcoded, and no provider key ever ships in
frontend code (the frontend only ever talks to *this* backend).
"""
from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # --- App ---
    ENV: str = "development"
    SECRET_KEY: str
    BACKEND_CORS_ORIGINS: str = "http://localhost:5173"
    PUBLIC_BASE_URL: str = "http://localhost:8000"

    # --- Database ---
    DATABASE_URL: str
    SYNC_DATABASE_URL: str
    DB_POOL_SIZE: int = 10
    DB_MAX_OVERFLOW: int = 20

    # --- Redis ---
    REDIS_URL: str = "redis://redis:6379/0"

    # --- Auth ---
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 15
    REFRESH_TOKEN_EXPIRE_DAYS: int = 30
    EMAIL_VERIFICATION_EXPIRE_HOURS: int = 48
    PASSWORD_RESET_EXPIRE_MINUTES: int = 30

    # --- Rate limiting ---
    RATE_LIMIT_LOGIN_PER_MINUTE: int = 5
    RATE_LIMIT_API_PER_MINUTE: int = 120

    # --- S3 ---
    S3_ENDPOINT_URL: str = "http://minio:9000"
    S3_REGION: str = "us-east-1"
    S3_ACCESS_KEY_ID: str
    S3_SECRET_ACCESS_KEY: str
    S3_BUCKET: str = "aiflow-documents"
    S3_USE_PATH_STYLE: bool = True

    # --- AI providers ---
    OPENAI_API_KEY: str | None = None
    OPENAI_BASE_URL: str | None = None
    ANTHROPIC_API_KEY: str | None = None
    OLLAMA_BASE_URL: str = "http://ollama:11434"
    DEFAULT_CHAT_PROVIDER: str = "anthropic"
    DEFAULT_CHAT_MODEL: str = "claude-sonnet-4-6"
    DEFAULT_EMBEDDING_PROVIDER: str = "openai"
    DEFAULT_EMBEDDING_MODEL: str = "text-embedding-3-small"
    EMBEDDING_DIM: int = 1536
    EMBEDDING_BASE_URL: str | None = None
    EMBEDDING_API_KEY: str | None = None

    # --- Billing ---
    STRIPE_SECRET_KEY: str | None = None
    STRIPE_WEBHOOK_SECRET: str | None = None
    STRIPE_PRICE_ID_PRO: str | None = None
    STRIPE_PRICE_ID_BUSINESS: str | None = None

    # --- Email ---
    SMTP_HOST: str | None = None
    SMTP_PORT: int = 587
    SMTP_USERNAME: str | None = None
    SMTP_PASSWORD: str | None = None
    SMTP_FROM_ADDRESS: str = "no-reply@aiflow.io"

    def cors_origins(self) -> list[str]:
        raw = self.BACKEND_CORS_ORIGINS.strip()
        if raw == "*":
            return ["*"]
        return [o.strip() for o in raw.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
