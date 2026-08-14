
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from app.config import get_settings
from app.routers import analytics, auth, billing, bots, knowledge, leads, marketplace, team, websocket, workspaces, widget
from app.routers import conversations as conversations_router

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: ensure S3 bucket exists
    from app.services.storage import ensure_bucket_exists
    try:
        ensure_bucket_exists()
    except Exception:
        pass  # non-fatal in dev; will fail on first upload if bucket missing
    yield


app = FastAPI(title="AI FLOW API", version="1.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins(),
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})

app.include_router(auth.router)
app.include_router(workspaces.router)
app.include_router(team.router)
app.include_router(bots.router)
app.include_router(knowledge.router)
app.include_router(conversations_router.router)
app.include_router(websocket.router)
app.include_router(leads.router)
app.include_router(analytics.router)
app.include_router(marketplace.router)
app.include_router(billing.router)
app.include_router(widget.router)

@app.get("/health")
async def health() -> dict:
    checks = {}
    # Check database connectivity
    try:
        from app.database import AsyncSessionLocal
        from sqlalchemy import text
        async with AsyncSessionLocal() as db:
            await db.execute(text("SELECT 1"))
        checks["database"] = "ok"
    except Exception:
        checks["database"] = "error"

    # Check Redis connectivity
    try:
        import redis.asyncio as aioredis
        r = aioredis.from_url(settings.REDIS_URL)
        await r.ping()
        await r.aclose()
        checks["redis"] = "ok"
    except Exception:
        checks["redis"] = "error"

    all_ok = all(v == "ok" for v in checks.values())
    return {"status": "ok" if all_ok else "degraded", "checks": checks}


@app.post("/test-register")
async def test_register():
    """Temporary debug endpoint to test registration flow."""
    import traceback
    try:
        from app.database import AsyncSessionLocal
        from app.models.user import User, EmailVerificationToken
        from app.security import hash_password, generate_opaque_token
        from datetime import datetime, timedelta, timezone
        
        async with AsyncSessionLocal() as db:
            from sqlalchemy import select
            result = await db.execute(select(User).where(User.email == "debug@test.com"))
            existing = result.scalar_one_or_none()
            if existing:
                return {"status": "user_exists", "user_id": str(existing.id)}
            
            user = User(email="debug@test.com", hashed_password=hash_password("Debug1234!"), full_name="Debug User")
            db.add(user)
            await db.flush()
            user_id = user.id
            
            plaintext, hashed = generate_opaque_token()
            db.add(EmailVerificationToken(
                user_id=user.id, hashed_token=hashed,
                expires_at=datetime.now(timezone.utc) + timedelta(hours=48),
            ))
            await db.commit()
            return {"status": "ok", "user_id": str(user_id), "token": plaintext}
    except Exception as e:
        return {"status": "error", "error": str(e), "traceback": traceback.format_exc()}
