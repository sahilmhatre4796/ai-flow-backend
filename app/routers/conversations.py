import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import require_admin, require_member
from app.models.bot import Bot
from app.models.conversation import Conversation, ConversationChannel, Message, MessageRole
from app.models.workspace import WorkspaceMembership
from app.schemas.conversation import (
    ConversationDetailResponse,
    ConversationResponse,
    ConversationUpdateRequest,
    MessageResponse,
    SendMessageRequest,
    SendMessageResponse,
)
from app.services.rag import generate_bot_response

router = APIRouter(prefix="/workspaces/{workspace_id}", tags=["conversations"])


async def _to_response(db: AsyncSession, conv: Conversation) -> ConversationResponse:
    count_result = await db.execute(select(func.count(Message.id)).where(Message.conversation_id == conv.id))
    return ConversationResponse(
        id=str(conv.id), bot_id=str(conv.bot_id), status=conv.status,
        started_at=conv.started_at, last_message_at=conv.last_message_at,
        message_count=count_result.scalar_one(),
    )


@router.get("/conversations", response_model=list[ConversationResponse])
async def list_conversations(
    workspace_id: uuid.UUID,
    bot_id: uuid.UUID | None = None,
    _membership: WorkspaceMembership = Depends(require_member),
    db: AsyncSession = Depends(get_db),
) -> list[ConversationResponse]:
    query = select(Conversation).where(Conversation.workspace_id == workspace_id)
    if bot_id:
        query = query.where(Conversation.bot_id == bot_id)
    result = await db.execute(query.order_by(Conversation.last_message_at.desc()))
    return [await _to_response(db, c) for c in result.scalars().all()]


@router.get("/conversations/{conversation_id}", response_model=ConversationDetailResponse)
async def get_conversation(
    workspace_id: uuid.UUID,
    conversation_id: uuid.UUID,
    _membership: WorkspaceMembership = Depends(require_member),
    db: AsyncSession = Depends(get_db),
) -> ConversationDetailResponse:
    conv = await db.get(Conversation, conversation_id)
    if not conv or conv.workspace_id != workspace_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Conversation not found")
    base = await _to_response(db, conv)
    return ConversationDetailResponse(**base.model_dump(), messages=[MessageResponse.model_validate(m) for m in conv.messages])


@router.patch("/conversations/{conversation_id}", response_model=ConversationResponse)
async def update_conversation(
    workspace_id: uuid.UUID,
    conversation_id: uuid.UUID,
    body: ConversationUpdateRequest,
    _membership: WorkspaceMembership = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> ConversationResponse:
    conv = await db.get(Conversation, conversation_id)
    if not conv or conv.workspace_id != workspace_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Conversation not found")
    if body.status is not None:
        conv.status = body.status
    if body.assigned_agent_id is not None:
        conv.assigned_agent_id = uuid.UUID(body.assigned_agent_id)
    await db.commit()
    return await _to_response(db, conv)


@router.post("/bots/{bot_id}/sandbox/messages", response_model=SendMessageResponse)
async def send_sandbox_message(
    workspace_id: uuid.UUID,
    bot_id: uuid.UUID,
    body: SendMessageRequest,
    conversation_id: uuid.UUID | None = None,
    _membership: WorkspaceMembership = Depends(require_member),
    db: AsyncSession = Depends(get_db),
) -> SendMessageResponse:
    """Used by the dashboard's 'Test bot' sandbox — same RAG pipeline as the
    public widget, just tagged with channel=SANDBOX and requiring auth."""
    bot = await db.get(Bot, bot_id)
    if not bot or bot.workspace_id != workspace_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Bot not found")

    conv = await db.get(Conversation, conversation_id) if conversation_id else None
    if not conv:
        conv = Conversation(workspace_id=workspace_id, bot_id=bot_id, channel=ConversationChannel.SANDBOX)
        db.add(conv)
        await db.flush()

    user_message = Message(conversation_id=conv.id, role=MessageRole.USER, content=body.text)
    db.add(user_message)

    reply_text, used_chunks = await generate_bot_response(db, bot, body.text)
    assistant_message = Message(
        conversation_id=conv.id,
        role=MessageRole.ASSISTANT,
        content=reply_text,
        retrieved_chunk_ids=[str(c.id) for c in used_chunks],
    )
    db.add(assistant_message)
    conv.last_message_at = datetime.now(timezone.utc)
    await db.commit()

    return SendMessageResponse(
        conversation_id=str(conv.id),
        user_message=MessageResponse.model_validate(user_message),
        assistant_message=MessageResponse.model_validate(assistant_message),
    )
