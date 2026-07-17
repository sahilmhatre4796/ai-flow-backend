"""
Password hashing (bcrypt via passlib) and JWT access/refresh token helpers.

Refresh tokens are opaque random strings; only their SHA-256 hash is stored
in the database (see models/user.py:RefreshToken), so a stolen DB dump
cannot be used to mint sessions.
"""
import hashlib
import secrets
import uuid
from datetime import datetime, timedelta, timezone

from jose import JWTError, jwt
from passlib.context import CryptContext

from app.config import get_settings

settings = get_settings()
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)


def create_access_token(user_id: uuid.UUID) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user_id),
        "type": "access",
        "iat": now,
        "exp": now + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES),
    }
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def decode_access_token(token: str) -> uuid.UUID | None:
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
        if payload.get("type") != "access":
            return None
        return uuid.UUID(payload["sub"])
    except (JWTError, KeyError, ValueError):
        return None


def generate_opaque_token() -> tuple[str, str]:
    """Returns (plaintext, sha256_hash) for refresh / verification / reset tokens."""
    plaintext = secrets.token_urlsafe(48)
    hashed = hashlib.sha256(plaintext.encode()).hexdigest()
    return plaintext, hashed


def hash_opaque_token(plaintext: str) -> str:
    return hashlib.sha256(plaintext.encode()).hexdigest()
