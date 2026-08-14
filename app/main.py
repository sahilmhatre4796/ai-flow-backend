
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from app.config import get_settings
from app.routers import analytics, auth, billing, bots, knowledge, leads, marketplace, team, websocket, workspaces, widget
from app.routers import conversations as conversations_router

settings = get_settings()

app = FastAPI(title="AI FLOW API", version="1.0.0")

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
    return {"status": "ok"}
