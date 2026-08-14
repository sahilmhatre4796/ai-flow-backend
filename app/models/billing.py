import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin


class PlanName(str, enum.Enum):
    free = "free"
    pro = "pro"
    business = "business"


class SubscriptionStatus(str, enum.Enum):
    active = "active"
    trialing = "trialing"
    past_due = "past_due"
    canceled = "canceled"


PLAN_LIMITS = {
    PlanName.free: {"bots": 1, "messages_per_month": 100},
    PlanName.pro: {"bots": 10, "messages_per_month": 10_000},
    PlanName.business: {"bots": None, "messages_per_month": None},  # None == unlimited
}


class Subscription(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "subscriptions"

    workspace_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"), unique=True, index=True, nullable=False
    )
    plan: Mapped[PlanName] = mapped_column(Enum(PlanName, name="plan_name"), default=PlanName.free, nullable=False)
    status: Mapped[SubscriptionStatus] = mapped_column(
        Enum(SubscriptionStatus, name="subscription_status"), default=SubscriptionStatus.active, nullable=False
    )
    stripe_customer_id: Mapped[str | None] = mapped_column(String(120), nullable=True)
    stripe_subscription_id: Mapped[str | None] = mapped_column(String(120), unique=True, nullable=True)
    current_period_end: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    workspace: Mapped["Workspace"] = relationship(back_populates="subscription")  # noqa: F821
