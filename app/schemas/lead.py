from datetime import datetime

from pydantic import BaseModel, EmailStr

from app.schemas import ResponseBase


class LeadCreateRequest(BaseModel):
    bot_id: str
    conversation_id: str | None = None
    name: str
    email: EmailStr
    phone: str | None = None
    company: str | None = None


class LeadResponse(ResponseBase):
    id: str
    bot_id: str
    name: str
    email: EmailStr
    phone: str | None
    company: str | None
    captured_at: datetime
