from datetime import datetime

from pydantic import BaseModel, Field

from app.models.bot import ChatProviderName


class BotCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    persona: str = Field(min_length=1)
    chat_provider: ChatProviderName = ChatProviderName.ANTHROPIC
    chat_model: str = "claude-sonnet-4-6"


class BotUpdateRequest(BaseModel):
    name: str | None = None
    persona: str | None = None
    chat_provider: ChatProviderName | None = None
    chat_model: str | None = None
    is_active: bool | None = None
    widget_color: str | None = None
    widget_position: str | None = None


class BotResponse(BaseModel):
    id: str
    name: str
    persona: str
    chat_provider: ChatProviderName
    chat_model: str
    is_active: bool
    public_key: str
    widget_color: str
    widget_position: str
    created_at: datetime

    class Config:
        from_attributes = True
