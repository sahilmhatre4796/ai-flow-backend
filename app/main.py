
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
    tb = traceback.format_exc()
    logger.error("Unhandled error on %s: %s\n%s", request.url.path, exc, tb)
    return JSONResponse(status_code=500, content={"detail": str(exc), "type": type(exc).__name__, "traceback": tb})

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


@app.post("/fix-enum-data")
async def fix_enum_data():
    """One-time endpoint: lowercase all enum column values that are UPPERCASE."""
    from app.database import AsyncSessionLocal
    from sqlalchemy import text

    fixes = [
        ("subscriptions", "plan", [("FREE", "free"), ("PRO", "pro"), ("BUSINESS", "business")]),
        ("subscriptions", "status", [("ACTIVE", "active"), ("TRIALING", "trialing"), ("PAST_DUE", "past_due"), ("CANCELED", "canceled")]),
        ("workspace_memberships", "role", [("OWNER", "owner"), ("ADMIN", "admin"), ("AGENT", "agent"), ("VIEWER", "viewer")]),
        ("workspace_memberships", "status", [("ACTIVE", "active"), ("INVITED", "invited")]),
        ("conversations", "channel", [("WIDGET", "widget"), ("SANDBOX", "sandbox"), ("API", "api")]),
        ("conversations", "status", [("OPEN", "open"), ("RESOLVED", "resolved"), ("UNRESOLVED", "unresolved")]),
        ("messages", "role", [("USER", "user"), ("ASSISTANT", "assistant"), ("AGENT", "agent"), ("SYSTEM", "system")]),
        ("bots", "chat_provider", [("OPENAI", "openai"), ("ANTHROPIC", "anthropic"), ("OLLAMA", "ollama")]),
        ("documents", "source_type", [("FILE", "file"), ("URL", "url"), ("SITEMAP", "sitemap"), ("FAQ", "faq"), ("PASTED_TEXT", "pasted_text")]),
        ("documents", "status", [("PENDING", "pending"), ("PARSING", "parsing"), ("CHUNKING", "chunking"), ("EMBEDDING", "embedding"), ("READY", "ready"), ("ERROR", "error")]),
    ]

    results = []
    enum_info = {}
    async with AsyncSessionLocal() as db:
        # First: check what the enum types actually contain
        for table, column, mappings in fixes:
            enum_name = mappings[0][1]  # derive from first mapping
            check = await db.execute(
                text("SELECT e.enumlabel FROM pg_enum e JOIN pg_type t ON e.enumtypid = t.oid WHERE t.typname = :ename"),
                {"ename": column.replace("_status", "_name").replace("_role", "_role")},
            )
            # just check each table's column type
        # Check actual enum type values
        for _, _, mappings in fixes:
            pass
        
        # Check all enum types
        r = await db.execute(text("SELECT t.typname, e.enumlabel FROM pg_enum e JOIN pg_type t ON e.enumtypid = t.oid ORDER BY t.typname, e.enumsortorder"))
        all_enums = {}
        for row in r.fetchall():
            all_enums.setdefault(row[0], []).append(row[1])

        for table, column, mappings in fixes:
            for old_val, new_val in mappings:
                r2 = await db.execute(
                    text(f"UPDATE {table} SET {column} = :new_val WHERE {column}::text = :old_val"),
                    {"new_val": new_val, "old_val": old_val},
                )
                if r2.rowcount > 0:
                    results.append(f"{table}.{column}: {old_val} -> {new_val} ({r2.rowcount} rows)")
        await db.commit()

    return {"enum_types": all_enums, "fixed": results} if results else {"enum_types": all_enums, "message": "No uppercase values found"}
