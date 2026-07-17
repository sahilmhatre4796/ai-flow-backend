from datetime import datetime

from pydantic import BaseModel, EmailStr


class LeadCreateRequest(BaseModel):
    bot_id: str
    conversation_id: str | None = None
    name: str
    email: EmailStr
    phone: str | None = None
    company: str | None = None


class LeadResponse(BaseModel):
    id: str
    bot_id: str
    name: str
    email: EmailStr
    phone: str | None
    company: str | None
    captured_at: datetime

    class Config:
        from_attributes = True
