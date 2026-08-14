
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


@app.exception_handler(Exception)
async def general_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    import logging, traceback
    logger = logging.getLogger("aiflow.error")
    logger.error("Unhandled error on %s: %s\n%s", request.url.path, exc, traceback.format_exc())
    return JSONResponse(status_code=500, content={"detail": "Internal server error"})

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


@app.post("/test-ws-create")
async def test_ws_create():
    """Test workspace creation with actual DB user."""
    import traceback
    try:
        from app.database import AsyncSessionLocal
        from app.models.workspace import Workspace, WorkspaceMembership, WorkspaceRole, MembershipStatus
        from app.models.billing import Subscription
        from app.models.user import User
        from sqlalchemy import select
        import re, secrets
        
        async with AsyncSessionLocal() as db:
            # Find an existing user
            result = await db.execute(select(User).limit(1))
            user = result.scalar_one_or_none()
            if not user:
                return {"status": "error", "error": "No users in DB"}
            
            def slugify(name):
                base = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-") or "workspace"
                return f"{base}-{secrets.token_hex(3)}"
            
            ws = Workspace(name="Test WS", slug=slugify("Test WS"), owner_id=user.id)
            db.add(ws)
            await db.flush()
            
            mem = WorkspaceMembership(workspace_id=ws.id, user_id=user.id, role=WorkspaceRole.OWNER, status=MembershipStatus.ACTIVE)
            db.add(mem)
            sub = Subscription(workspace_id=ws.id)
            db.add(sub)
            await db.commit()
            
            return {"status": "ok", "workspace_id": str(ws.id), "user_id": str(user.id)}
    except Exception as e:
        return {"status": "error", "error": str(e), "traceback": traceback.format_exc()}
