# AI FLOW — Backend

Production-grade FastAPI + PostgreSQL backend for the AI FLOW no-code chatbot
builder. Built against the mandatory architecture spec: Postgres-only
primary datastore, pgvector for retrieval, real multi-tenant isolation,
Celery/Redis background processing, FastAPI WebSockets for live chat, and a
swappable AI provider layer (OpenAI / Anthropic / Ollama).

## Local development

```bash
cp .env.example .env          # fill in OPENAI_API_KEY / ANTHROPIC_API_KEY at minimum
docker-compose up -d postgres redis minio
docker-compose run --rm backend alembic upgrade head
docker-compose up -d backend worker nginx
```

The API is then reachable at `http://localhost:8000` (or via Nginx on
`http://localhost:80`). Interactive docs: `http://localhost:8000/docs`.

To run a fresh migration after changing a model:

```bash
docker-compose run --rm backend alembic revision --autogenerate -m "describe change"
docker-compose run --rm backend alembic upgrade head
```

## Architecture decisions worth knowing

**Two database engines, on purpose.** `app/database.py` holds an async
engine (asyncpg) used by FastAPI request handlers and the WebSocket routes.
`app/db_sync.py` holds a separate synchronous engine (psycopg2) used only by
Celery workers. Celery's worker model is synchronous; sharing an async
engine across that boundary is a well-known source of event-loop and
connection-pool bugs, so the two are kept fully separate.

**Embeddings vs. chat are different provider abstractions.** Anthropic does
not expose a public embeddings endpoint. Rather than inventing one,
`app/services/ai_providers.py` defines two separate interfaces:
`ChatProvider` (OpenAI / Anthropic / Ollama, async, used for generation) and
`EmbeddingProvider` (OpenAI / Ollama, sync, used by the Celery ingestion
pipeline). A bot's `chat_provider` is swappable per-bot; the embedding
provider is a workspace-wide default since changing it would orphan
previously generated vectors.

**Tenant isolation has one checkpoint.** Every workspace-scoped router
depends on `CurrentMembership` (`app/dependencies.py`), which checks
`workspace_id` + `user_id` + active status before any handler runs, and
returns 404 (not 403) for non-members so workspace existence isn't leaked.
There's no code path that queries a Bot/Document/Conversation/Lead without
going through this.

**Analytics is computed, not stored.** There's no `analytics` table that
needs syncing and can drift from reality. `app/routers/analytics.py` runs
real aggregate SQL against Conversation/Message/Lead on every request, and
returns `null` for rate/average fields when there isn't enough data yet —
the same "don't fabricate, show an honest empty state" rule the frontend
already follows for its own in-memory mock, now enforced at the database
layer too.

**Marketplace install counts are `COUNT(*)`, not a stored counter.**
`TemplateInstall` has one row per install; `app/routers/marketplace.py`
joins and counts rather than incrementing a number anywhere.

**The WebSocket layer uses Redis pub/sub, not an in-process dict.** A plain
`dict[str, set[WebSocket]]` only works with exactly one backend process. The
moment you run more than one uvicorn worker (which any real deployment
will), a visitor on worker A and an agent on worker B would never see each
other's messages. `app/websocket_manager.py` broadcasts through Redis
instead, so it's correct regardless of how many processes are running.

**Document status reflects real pipeline state.** `app/tasks/document_tasks.py`
moves a `Document` through `pending → parsing → chunking → embedding → ready`
(or `error`, with the real exception message attached) as each step
actually completes. Nothing reports `ready` before chunks and embeddings
exist in Postgres.

## RAG pipeline (per `app/services/rag.py` and `app/tasks/document_tasks.py`)

```
Upload/URL/sitemap → S3/MinIO (raw bytes, never in Postgres)
   → Celery: parse (pypdf / python-docx / csv / BeautifulSoup)
   → chunk (app/services/chunking.py — sentence-boundary split with a
       hard-wrap fallback for unpunctuated text)
   → embed (OpenAI or Ollama embeddings) → Chunk rows with pgvector vectors
   → retrieval: cosine-distance ORDER BY against the bot's ready chunks
   → context assembly (honest "nothing relevant found" fallback if empty)
   → chat provider generates the reply, grounded in the retrieved excerpts
   → Message persisted with retrieved_chunk_ids for auditability
```

## Deployment

- **Frontend:** Vercel.
- **Backend + Postgres:** Railway (use Railway's managed Postgres with the
  pgvector extension enabled, or any Postgres host that supports it).
- **Redis:** Railway's managed Redis, or any managed Redis.
- **Storage:** swap MinIO for real AWS S3 — only `S3_ENDPOINT_URL`,
  `S3_USE_PATH_STYLE=false`, and IAM credentials need to change; the storage
  service code is identical.
- **Reverse proxy:** the included `nginx/nginx.conf` forwards WebSocket
  upgrade headers correctly for `/ws/*` — required for live conversations to
  work behind a proxy at all.

Deliberately **not** used: Kubernetes, Kafka, a microservices split. A
single FastAPI service + one Celery worker pool + managed Postgres/Redis/S3
comfortably covers the 100 → 10,000 user range named in the brief; revisit
only if a specific bottleneck shows up in practice.

## What's not wired up yet

The existing frontend artifact (`ai-flow.jsx`) currently keeps its own
in-memory React state and calls the Anthropic API directly from the browser.
Pointing it at this backend instead — real login, real workspace creation,
real document upload, and a real WebSocket connection for the widget/test
bot — is a frontend integration pass that hasn't been done yet. The REST and
WebSocket contracts above are stable enough to build that against.
