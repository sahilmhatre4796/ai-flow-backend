"""
The actual RAG ingestion pipeline. `Document.status` is updated at each real
stage transition — there is no shortcut that jumps straight to `ready`
without chunks and embeddings actually existing in Postgres.
"""
import uuid
from datetime import datetime, timezone

from app.db_sync import SyncSessionLocal
from app.models.knowledge import Chunk, Document, DocumentSourceType, DocumentStatus
from app.services import parsing, storage
from app.services.ai_providers import get_embedding_provider
from app.services.chunking import chunk_text
from app.tasks.celery_app import celery_app


def _extract_text(document: Document) -> str:
    if document.source_type in (DocumentSourceType.pasted_text, DocumentSourceType.faq, DocumentSourceType.file):
        if not document.storage_key:
            raise ValueError("Document has no stored content to read.")
        data = storage.download_bytes(document.storage_key)
        if document.source_type == DocumentSourceType.file:
            return parsing.parse_by_mime_or_extension(
                data, document.original_filename or document.name, document.mime_type
            )
        return data.decode("utf-8", errors="ignore")

    if document.source_type in (DocumentSourceType.url, DocumentSourceType.sitemap):
        if not document.source_url:
            raise ValueError("Document has no source URL to fetch.")
        return parsing.fetch_url_text(document.source_url)

    raise ValueError(f"Unsupported source type: {document.source_type}")


@celery_app.task(name="app.tasks.document_tasks.process_document")
def process_document(document_id: str) -> None:
    db = SyncSessionLocal()
    try:
        document = db.get(Document, uuid.UUID(document_id))
        if not document:
            return

        try:
            document.status = DocumentStatus.parsing
            db.commit()

            raw_text = _extract_text(document)
            if not raw_text.strip():
                raise ValueError("No extractable text was found in this document.")

            document.char_count = len(raw_text)
            document.status = DocumentStatus.chunking
            db.commit()

            pieces = chunk_text(raw_text)
            if not pieces:
                raise ValueError("Text was extracted but produced no usable chunks.")

            document.status = DocumentStatus.embedding
            db.commit()

            embedding_provider = get_embedding_provider()
            vectors = embedding_provider.embed_batch(pieces)

            for index, (content, vector) in enumerate(zip(pieces, vectors)):
                db.add(
                    Chunk(
                        document_id=document.id,
                        workspace_id=document.workspace_id,
                        bot_id=document.bot_id,
                        chunk_index=index,
                        content=content,
                        embedding=vector,
                        created_at=datetime.now(timezone.utc),
                    )
                )

            document.status = DocumentStatus.ready
            document.error_message = None
            db.commit()

        except Exception as exc:  # noqa: BLE001 — deliberately broad: any failure must be recorded, not swallowed
            db.rollback()
            document.status = DocumentStatus.error
            document.error_message = str(exc)[:2000]
            db.commit()
            raise
    finally:
        db.close()


@celery_app.task(name="app.tasks.document_tasks.process_sitemap")
def process_sitemap(parent_document_id: str) -> None:
    """Fetches the sitemap, creates one Document per page (capped inside
    parsing.fetch_sitemap_urls), and enqueues process_document for each."""
    db = SyncSessionLocal()
    try:
        parent = db.get(Document, uuid.UUID(parent_document_id))
        if not parent or not parent.source_url:
            return
        try:
            page_urls = parsing.fetch_sitemap_urls(parent.source_url)
            if not page_urls:
                raise ValueError("Sitemap contained no page URLs.")

            for page_url in page_urls:
                child = Document(
                    workspace_id=parent.workspace_id,
                    bot_id=parent.bot_id,
                    name=page_url,
                    source_type=DocumentSourceType.sitemap,
                    source_url=page_url,
                    status=DocumentStatus.pending,
                )
                db.add(child)
                db.flush()  # assign child.id before enqueueing
                process_document.delay(str(child.id))

            parent.status = DocumentStatus.ready  # the sitemap "index" itself has no chunks of its own
            parent.error_message = None
            db.commit()
        except Exception as exc:  # noqa: BLE001
            db.rollback()
            parent.status = DocumentStatus.error
            parent.error_message = str(exc)[:2000]
            db.commit()
            raise
    finally:
        db.close()
