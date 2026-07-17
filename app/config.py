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
    SECRET_KEY: str  # used to sign JWTs; must be set in .env
    BACKEND_CORS_ORIGINS: str = "http://localhost:5173"  # comma-separated, strict allow-list for the dashboard app
    PUBLIC_BASE_URL: str = "http://localhost:8000"

    # --- Database (PostgreSQL + pgvector — the only primary datastore) ---
    DATABASE_URL: str  # e.g. postgresql+asyncpg://aiflow:aiflow@postgres:5432/aiflow
    SYNC_DATABASE_URL: str  # e.g. postgresql+psycopg2://aiflow:aiflow@postgres:5432/aiflow (used by Celery workers)
    DB_POOL_SIZE: int = 10
    DB_MAX_OVERFLOW: int = 20

    # --- Redis (rate limiting, Celery broker/result backend, websocket pub/sub) ---
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

    # --- S3-compatible object storage (MinIO locally, AWS S3 in production) ---
    S3_ENDPOINT_URL: str = "http://minio:9000"
    S3_REGION: str = "us-east-1"
    S3_ACCESS_KEY_ID: str
    S3_SECRET_ACCESS_KEY: str
    S3_BUCKET: str = "aiflow-documents"
    S3_USE_PATH_STYLE: bool = True  # required for MinIO

    # --- AI providers (server-side only; never exposed to the browser) ---
    OPENAI_API_KEY: str | None = None
    ANTHROPIC_API_KEY: str | None = None
    OLLAMA_BASE_URL: str = "http://ollama:11434"
    DEFAULT_CHAT_PROVIDER: str = "anthropic"   # anthropic | openai | ollama
    DEFAULT_CHAT_MODEL: str = "claude-sonnet-4-6"
    DEFAULT_EMBEDDING_PROVIDER: str = "openai"  # anthropic has no embeddings API — openai | ollama
    DEFAULT_EMBEDDING_MODEL: str = "text-embedding-3-small"
    EMBEDDING_DIM: int = 1536

    # --- Billing (Stripe) ---
    STRIPE_SECRET_KEY: str | None = None
    STRIPE_WEBHOOK_SECRET: str | None = None
    STRIPE_PRICE_ID_PRO: str | None = None
    STRIPE_PRICE_ID_BUSINESS: str | None = None

    # --- Outbound email ---
    SMTP_HOST: str | None = None
    SMTP_PORT: int = 587
    SMTP_USERNAME: str | None = None
    SMTP_PASSWORD: str | None = None
    SMTP_FROM_ADDRESS: str = "no-reply@aiflow.io"

    @property
    def cors_origins(self) -> list[str]:
        return [o.strip() for o in self.BACKEND_CORS_ORIGINS.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
