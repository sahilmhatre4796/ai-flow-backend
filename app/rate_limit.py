"""
Simple, correct fixed-window rate limiter backed by Redis (INCR + EXPIRE).
Shared across all uvicorn worker processes/instances, unlike an in-memory
counter, which is what makes this safe for a horizontally scaled deployment.
"""
import redis.asyncio as aioredis
from fastapi import HTTPException, Request, status

from app.config import get_settings

settings = get_settings()
_redis = aioredis.from_url(settings.REDIS_URL, decode_responses=True)


async def enforce_rate_limit(key: str, limit: int, window_seconds: int = 60) -> None:
    redis_key = f"ratelimit:{key}"
    current = await _redis.incr(redis_key)
    if current == 1:
        await _redis.expire(redis_key, window_seconds)
    if current > limit:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many requests. Please slow down and try again shortly.",
        )


def client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


async def rate_limit_login(request: Request) -> None:
    await enforce_rate_limit(f"login:{client_ip(request)}", settings.RATE_LIMIT_LOGIN_PER_MINUTE)


async def rate_limit_api(request: Request) -> None:
    await enforce_rate_limit(f"api:{client_ip(request)}", settings.RATE_LIMIT_API_PER_MINUTE)
