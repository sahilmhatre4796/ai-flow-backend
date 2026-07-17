from datetime import datetime

from pydantic import BaseModel

from app.models.billing import PlanName, SubscriptionStatus


class SubscriptionResponse(BaseModel):
    plan: PlanName
    status: SubscriptionStatus
    current_period_end: datetime | None

    class Config:
        from_attributes = True


class UsageResponse(BaseModel):
    plan: PlanName
    bots_used: int
    bots_limit: int | None  # None == unlimited
    messages_used_this_period: int
    messages_limit: int | None
    documents_uploaded: int
    team_members: int


class CheckoutSessionRequest(BaseModel):
    plan: PlanName


class CheckoutSessionResponse(BaseModel):
    checkout_url: str
