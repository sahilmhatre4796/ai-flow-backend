import uuid

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import require_admin, require_member
from app.models.bot import Bot
from app.models.knowledge import Chunk, Document, DocumentSourceType, DocumentStatus
from app.models.workspace import WorkspaceMembership
from app.schemas.knowledge import ChunkResponse, DocumentCreateFromTextRequest, DocumentCreateFromUrlRequest, DocumentResponse
from app.services import storage
from app.tasks.document_tasks import process_document, process_sitemap

router = APIRouter(prefix="/workspaces/{workspace_id}/bots/{bot_id}/documents", tags=["knowledge"])


async def _get_bot_or_404(db: AsyncSession, workspace_id: uuid.UUID, bot_id: uuid.UUID) -> Bot:
    bot = await db.get(Bot, bot_id)
    if not bot or bot.workspace_id != workspace_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Bot not found")
    return bot


@router.get("", response_model=list[DocumentResponse])
async def list_documents(
    workspace_id: uuid.UUID,
    bot_id: uuid.UUID,
    _membership: WorkspaceMembership = Depends(require_member),
    db: AsyncSession = Depends(get_db),
) -> list[DocumentResponse]:
    await _get_bot_or_404(db, workspace_id, bot_id)
    result = await db.execute(select(Document).where(Document.bot_id == bot_id).order_by(Document.created_at.desc()))
    return list(result.scalars().all())


@router.post("/upload", response_model=DocumentResponse, status_code=status.HTTP_201_CREATED)
async def upload_document(
    workspace_id: uuid.UUID,
    bot_id: uuid.UUID,
    file: UploadFile = File(...),
    _membership: WorkspaceMembership = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> DocumentResponse:
    await _get_bot_or_404(db, workspace_id, bot_id)
    raw_bytes = await file.read()
    object_key = storage.build_object_key(workspace_id, bot_id, file.filename or "upload")
    storage.upload_bytes(object_key, raw_bytes, content_type=file.content_type)

    document = Document(
        workspace_id=workspace_id,
        bot_id=bot_id,
        name=file.filename or "Uploaded document",
        source_type=DocumentSourceType.file,
        storage_key=object_key,
        original_filename=file.filename,
        mime_type=file.content_type,
        status=DocumentStatus.pending,
    )
    db.add(document)
    await db.flush()
    document_id = str(document.id)
    await db.commit()

    process_document.delay(document_id)
    return document


@router.post("/from-text", response_model=DocumentResponse, status_code=status.HTTP_201_CREATED)
async def create_from_text(
    workspace_id: uuid.UUID,
    bot_id: uuid.UUID,
    body: DocumentCreateFromTextRequest,
    _membership: WorkspaceMembership = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> DocumentResponse:
    await _get_bot_or_404(db, workspace_id, bot_id)
    object_key = storage.build_object_key(workspace_id, bot_id, f"{body.name}.txt")
    storage.upload_bytes(object_key, body.text.encode("utf-8"), content_type="text/plain")

    document = Document(
        workspace_id=workspace_id,
        bot_id=bot_id,
        name=body.name,
        source_type=DocumentSourceType.pasted_text,
        storage_key=object_key,
        mime_type="text/plain",
        status=DocumentStatus.pending,
    )
    db.add(document)
    await db.flush()
    document_id = str(document.id)
    await db.commit()

    process_document.delay(document_id)
    return document


@router.post("/from-url", response_model=DocumentResponse, status_code=status.HTTP_201_CREATED)
async def create_from_url(
    workspace_id: uuid.UUID,
    bot_id: uuid.UUID,
    body: DocumentCreateFromUrlRequest,
    _membership: WorkspaceMembership = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> DocumentResponse:
    await _get_bot_or_404(db, workspace_id, bot_id)

    document = Document(
        workspace_id=workspace_id,
        bot_id=bot_id,
        name=body.name,
        source_type=DocumentSourceType.sitemap if body.is_sitemap else DocumentSourceType.url,
        source_url=body.url,
        status=DocumentStatus.pending,
    )
    db.add(document)
    await db.flush()
    document_id = str(document.id)
    await db.commit()

    if body.is_sitemap:
        process_sitemap.delay(document_id)
    else:
        process_document.delay(document_id)
    return document


@router.get("/{document_id}/chunks", response_model=list[ChunkResponse])
async def list_chunks(
    workspace_id: uuid.UUID,
    bot_id: uuid.UUID,
    document_id: uuid.UUID,
    _membership: WorkspaceMembership = Depends(require_member),
    db: AsyncSession = Depends(get_db),
) -> list[ChunkResponse]:
    await _get_bot_or_404(db, workspace_id, bot_id)
    result = await db.execute(
        select(Chunk).where(Chunk.document_id == document_id).order_by(Chunk.chunk_index)
    )
    return list(result.scalars().all())


@router.delete("/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_document(
    workspace_id: uuid.UUID,
    bot_id: uuid.UUID,
    document_id: uuid.UUID,
    _membership: WorkspaceMembership = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> None:
    await _get_bot_or_404(db, workspace_id, bot_id)
    document = await db.get(Document, document_id)
    if not document or document.bot_id != bot_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Document not found")
    if document.storage_key:
        storage.delete_object(document.storage_key)
    await db.delete(document)
    await db.commit()
