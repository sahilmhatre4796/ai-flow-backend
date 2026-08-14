from datetime import datetime

from pydantic import BaseModel

from app.models.conversation import ConversationStatus, MessageRole
from app.schemas import ResponseBase


class MessageResponse(ResponseBase):
    id: str
    role: MessageRole
    content: str
    created_at: datetime


class ConversationResponse(ResponseBase):
    id: str
    bot_id: str
    status: ConversationStatus
    started_at: datetime
    last_message_at: datetime
    message_count: int


class ConversationDetailResponse(ConversationResponse):
    messages: list[MessageResponse]


class ConversationUpdateRequest(BaseModel):
    status: ConversationStatus | None = None
    assigned_agent_id: str | None = None


class SendMessageRequest(BaseModel):
    text: str


class SendMessageResponse(ResponseBase):
    conversation_id: str
    user_message: MessageResponse
    assistant_message: MessageResponse
