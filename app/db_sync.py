"""
Synchronous engine/session used exclusively by Celery workers (app/tasks/*).
Background jobs (parsing, chunking, embedding, email) run outside any
asyncio event loop, so they use plain psycopg2 + sync SQLAlchemy sessions.
"""
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.config import get_settings

settings = get_settings()

sync_engine = create_engine(
    settings.SYNC_DATABASE_URL,
    pool_size=settings.DB_POOL_SIZE,
    max_overflow=settings.DB_MAX_OVERFLOW,
    pool_pre_ping=True,
)

SyncSessionLocal = sessionmaker(bind=sync_engine, autoflush=False, expire_on_commit=False)


def get_sync_db() -> Session:
    db = SyncSessionLocal()
    try:
        return db
    except Exception:
        db.close()
        raise
