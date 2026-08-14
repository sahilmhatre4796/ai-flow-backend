import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

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


async def _list_with_counts(db: AsyncSession, conversations: list[Conversation]) -> list[ConversationResponse]:
    if not conversations:
        return []
    conv_ids = [c.id for c in conversations]
    count_rows = await db.execute(
        select(Message.conversation_id, func.count(Message.id))
        .where(Message.conversation_id.in_(conv_ids))
        .group_by(Message.conversation_id)
    )
    counts = {row[0]: row[1] for row in count_rows.all()}
    return [
        ConversationResponse(
            id=str(c.id), bot_id=str(c.bot_id), status=c.status,
            started_at=c.started_at, last_message_at=c.last_message_at,
            message_count=counts.get(c.id, 0),
        )
        for c in conversations
    ]


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
    conversations = result.scalars().all()
    return await _list_with_counts(db, conversations)


@router.get("/conversations/{conversation_id}", response_model=ConversationDetailResponse)
async def get_conversation(
    workspace_id: uuid.UUID,
    conversation_id: uuid.UUID,
    _membership: WorkspaceMembership = Depends(require_member),
    db: AsyncSession = Depends(get_db),
) -> ConversationDetailResponse:
    result = await db.execute(
        select(Conversation)
        .options(selectinload(Conversation.messages))
        .where(Conversation.id == conversation_id, Conversation.workspace_id == workspace_id)
    )
    conv = result.scalar_one_or_none()
    if not conv:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Conversation not found")
    count_result = await db.execute(select(func.count(Message.id)).where(Message.conversation_id == conv.id))
    return ConversationDetailResponse(
        id=str(conv.id), bot_id=str(conv.bot_id), status=conv.status,
        started_at=conv.started_at, last_message_at=conv.last_message_at,
        message_count=count_result.scalar_one(),
        messages=[MessageResponse.model_validate(m) for m in conv.messages],
    )


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
    count_result = await db.execute(select(func.count(Message.id)).where(Message.conversation_id == conv.id))
    return ConversationResponse(
        id=str(conv.id), bot_id=str(conv.bot_id), status=conv.status,
        started_at=conv.started_at, last_message_at=conv.last_message_at,
        message_count=count_result.scalar_one(),
    )


@router.post("/conversations/{conversation_id}/messages", response_model=MessageResponse)
async def send_agent_message(
    workspace_id: uuid.UUID,
    conversation_id: uuid.UUID,
    body: SendMessageRequest,
    _membership: WorkspaceMembership = Depends(require_member),
    db: AsyncSession = Depends(get_db),
) -> MessageResponse:
    """Allow a human agent to reply in a live conversation (agent takeover)."""
    conv = await db.get(Conversation, conversation_id)
    if not conv or conv.workspace_id != workspace_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Conversation not found")
    message = Message(conversation_id=conv.id, role=MessageRole.AGENT, content=body.text)
    db.add(message)
    conv.last_message_at = datetime.now(timezone.utc)
    await db.commit()
    return MessageResponse.model_validate(message)


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
