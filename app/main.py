"""
FastAPI app entrypoint.
CORS needs two different policies, not one global `allow_origins=["*"]`:
  - The authenticated dashboard API must only be callable from our own
    frontend origin(s) — credentials are involved, so a wildcard would be
    a real vulnerability.
  - The embeddable widget (`/widget/*`, `/ws/widget/*`) is, by design,
    loaded on arbitrary customer domains we can't know in advance, and
    carries no cookies/credentials — so it needs to allow any origin.
`DualOriginCORSMiddleware` below applies the right policy per path prefix
instead of relaxing CORS globally.
"""
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse, Response
from starlette.datastructures import Headers

from app.config import get_settings
from app.routers import (
    analytics,
    auth,
    billing,
    bots,
    knowledge,
    leads,
    marketplace,
    team,
    websocket,
    workspaces,
    widget,
)
from app.routers import conversations as conversations_router

settings = get_settings()

PUBLIC_PREFIXES = ("/widget", "/ws/widget")


class DualOriginCORSMiddleware:
    def __init__(self, app, allowed_origins: list[str]):
        self.app = app
        self.allowed_origins = set(allowed_origins)
        self.allow_all = "*" in allowed_origins

    async def __call__(self, scope, receive, send):
        if scope["type"] not in ("http", "websocket"):
            await self.app(scope, receive, send)
            return

        path = scope.get("path", "")
        headers = Headers(scope=scope)
        origin = headers.get("origin")
        is_public_path = any(path.startswith(p) for p in PUBLIC_PREFIXES)

        if is_public_path or self.allow_all:
            allow_origin = origin or "*"
            allow_credentials = False
        else:
            allow_origin = origin if origin in self.allowed_origins else None
            allow_credentials = True

        if scope["type"] == "http" and scope.get("method") == "OPTIONS":
            response_headers = {
                "Access-Control-Allow-Methods": "GET, POST, PATCH, DELETE, OPTIONS",
                "Access-Control-Allow-Headers": "Authorization, Content-Type",
            }
            if allow_origin:
                response_headers["Access-Control-Allow-Origin"] = allow_origin
                if allow_credentials:
                    response_headers["Access-Control-Allow-Credentials"] = "true"
            response = Response(status_code=200, headers=response_headers)
            await response(scope, receive, send)
            return

        async def send_with_cors(message):
            if message["type"] == "http.response.start" and allow_origin:
                headers_list = list(message.get("headers", []))
                headers_list.append(
                    (b"access-control-allow-origin", allow_origin.encode())
                )
                if allow_credentials:
                    headers_list.append(
                        (b"access-control-allow-credentials", b"true")
                    )
                message["headers"] = headers_list
            await send(message)

        await self.app(scope, receive, send_with_cors)


app = FastAPI(title="AI FLOW API", version="1.0.0")

app.add_middleware(DualOriginCORSMiddleware, allowed_origins=settings.cors_origins())


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
    return {"status": "ok"}
