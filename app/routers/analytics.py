import uuid

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import require_member
from app.models.conversation import Conversation, ConversationStatus, Message, MessageRole
from app.models.lead import Lead
from app.models.workspace import WorkspaceMembership
from app.schemas.analytics import AnalyticsResponse, RecentQuestion

router = APIRouter(prefix="/workspaces/{workspace_id}/analytics", tags=["analytics"])


@router.get("", response_model=AnalyticsResponse)
async def get_analytics(
    workspace_id: uuid.UUID,
    _membership: WorkspaceMembership = Depends(require_member),
    db: AsyncSession = Depends(get_db),
) -> AnalyticsResponse:
    status_counts_result = await db.execute(
        select(Conversation.status, func.count(Conversation.id))
        .where(Conversation.workspace_id == workspace_id)
        .group_by(Conversation.status)
    )
    counts = {status: count for status, count in status_counts_result.all()}
    resolved = counts.get(ConversationStatus.RESOLVED, 0)
    unresolved = counts.get(ConversationStatus.UNRESOLVED, 0)
    open_count = counts.get(ConversationStatus.OPEN, 0)
    total_conversations = resolved + unresolved + open_count

    leads_total_result = await db.execute(select(func.count(Lead.id)).where(Lead.workspace_id == workspace_id))
    leads_total = leads_total_result.scalar_one()

    leads_from_conv_result = await db.execute(
        select(func.count(Lead.id)).where(Lead.workspace_id == workspace_id, Lead.conversation_id.isnot(None))
    )
    leads_from_conversations = leads_from_conv_result.scalar_one()

    total_messages_result = await db.execute(
        select(func.count(Message.id))
        .join(Conversation, Conversation.id == Message.conversation_id)
        .where(Conversation.workspace_id == workspace_id)
    )
    total_messages = total_messages_result.scalar_one()

    recent_result = await db.execute(
        select(Message.content, Message.created_at)
        .join(Conversation, Conversation.id == Message.conversation_id)
        .where(Conversation.workspace_id == workspace_id, Message.role == MessageRole.USER)
        .order_by(Message.created_at.desc())
        .limit(10)
    )
    recent_questions = [RecentQuestion(text=content, asked_at=created_at.isoformat()) for content, created_at in recent_result.all()]

    return AnalyticsResponse(
        total_conversations=total_conversations,
        resolved_count=resolved,
        unresolved_count=unresolved,
        open_count=open_count,
        resolution_rate=(resolved / total_conversations) if total_conversations > 0 else None,
        total_leads=leads_total,
        leads_from_conversations=leads_from_conversations,
        total_messages=total_messages,
        avg_messages_per_conversation=(total_messages / total_conversations) if total_conversations > 0 else None,
        recent_questions=recent_questions,
    )
