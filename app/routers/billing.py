import uuid
from datetime import datetime, timedelta, timezone

import stripe
from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.database import get_db
from app.dependencies import require_member, require_owner
from app.models.billing import PLAN_LIMITS, PlanName, Subscription, SubscriptionStatus
from app.models.bot import Bot
from app.models.conversation import Conversation, Message
from app.models.knowledge import Document
from app.models.workspace import WorkspaceMembership
from app.schemas.billing import CheckoutSessionRequest, CheckoutSessionResponse, UsageResponse

router = APIRouter(tags=["billing"])
settings = get_settings()


@router.post("/workspaces/{workspace_id}/billing/checkout-session", response_model=CheckoutSessionResponse)
async def create_checkout_session(
    workspace_id: uuid.UUID,
    body: CheckoutSessionRequest,
    _membership: WorkspaceMembership = Depends(require_owner),
    db: AsyncSession = Depends(get_db),
) -> CheckoutSessionResponse:
    if not settings.STRIPE_SECRET_KEY:
        # Never fabricate a checkout URL — fail loudly so the gap is obvious in dev.
        raise HTTPException(status.HTTP_501_NOT_IMPLEMENTED, "Stripe is not configured on this server yet")

    price_id = {
        PlanName.PRO: settings.STRIPE_PRICE_ID_PRO,
        PlanName.BUSINESS: settings.STRIPE_PRICE_ID_BUSINESS,
    }.get(body.plan)
    if not price_id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "No Stripe price configured for this plan")

    stripe.api_key = settings.STRIPE_SECRET_KEY
    session = stripe.checkout.Session.create(
        mode="subscription",
        line_items=[{"price": price_id, "quantity": 1}],
        success_url=f"{settings.PUBLIC_BASE_URL}/billing?checkout=success",
        cancel_url=f"{settings.PUBLIC_BASE_URL}/billing?checkout=canceled",
        client_reference_id=str(workspace_id),
    )
    return CheckoutSessionResponse(checkout_url=session.url)


@router.post("/billing/webhook", status_code=status.HTTP_204_NO_CONTENT)
async def stripe_webhook(request: Request, db: AsyncSession = Depends(get_db)) -> None:
    if not settings.STRIPE_WEBHOOK_SECRET:
        raise HTTPException(status.HTTP_501_NOT_IMPLEMENTED, "Stripe webhook secret is not configured")

    payload = await request.body()
    sig_header = request.headers.get("stripe-signature", "")
    try:
        event = stripe.Webhook.construct_event(payload, sig_header, settings.STRIPE_WEBHOOK_SECRET)
    except (stripe.error.SignatureVerificationError, ValueError):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid Stripe signature")

    data = event["data"]["object"]
    event_type = event["type"]

    if event_type == "checkout.session.completed":
        workspace_id = uuid.UUID(data["client_reference_id"])
        result = await db.execute(select(Subscription).where(Subscription.workspace_id == workspace_id))
        subscription = result.scalar_one_or_none()
        if subscription:
            subscription.stripe_customer_id = data.get("customer")
            subscription.stripe_subscription_id = data.get("subscription")
            subscription.status = SubscriptionStatus.ACTIVE
            await db.commit()

    elif event_type in ("customer.subscription.updated", "customer.subscription.deleted"):
        result = await db.execute(
            select(Subscription).where(Subscription.stripe_subscription_id == data["id"])
        )
        subscription = result.scalar_one_or_none()
        if subscription:
            status_map = {
                "active": SubscriptionStatus.ACTIVE,
                "trialing": SubscriptionStatus.TRIALING,
                "past_due": SubscriptionStatus.PAST_DUE,
                "canceled": SubscriptionStatus.CANCELED,
            }
            subscription.status = status_map.get(data.get("status"), subscription.status)
            if data.get("current_period_end"):
                subscription.current_period_end = datetime.fromtimestamp(data["current_period_end"], tz=timezone.utc)
            await db.commit()


@router.get("/workspaces/{workspace_id}/billing/usage", response_model=UsageResponse)
async def get_usage(
    workspace_id: uuid.UUID,
    _membership: WorkspaceMembership = Depends(require_member),
    db: AsyncSession = Depends(get_db),
) -> UsageResponse:
    sub_result = await db.execute(select(Subscription).where(Subscription.workspace_id == workspace_id))
    subscription = sub_result.scalar_one_or_none()
    plan = subscription.plan if subscription else PlanName.FREE
    limits = PLAN_LIMITS[plan]

    bots_count = (await db.execute(select(func.count(Bot.id)).where(Bot.workspace_id == workspace_id))).scalar_one()
    docs_count = (
        await db.execute(select(func.count(Document.id)).where(Document.workspace_id == workspace_id))
    ).scalar_one()

    period_start = (subscription.current_period_end - timedelta(days=30)) if (
        subscription and subscription.current_period_end
    ) else None
    messages_query = (
        select(func.count(Message.id))
        .join(Conversation, Conversation.id == Message.conversation_id)
        .where(Conversation.workspace_id == workspace_id)
    )
    if period_start:
        messages_query = messages_query.where(Message.created_at >= period_start)
    messages_count = (await db.execute(messages_query)).scalar_one()

    members_count = (
        await db.execute(
            select(func.count(WorkspaceMembership.id)).where(WorkspaceMembership.workspace_id == workspace_id)
        )
    ).scalar_one()

    return UsageResponse(
        plan=plan,
        bots_used=bots_count,
        bots_limit=limits["bots"],
        messages_used_this_period=messages_count,
        messages_limit=limits["messages_per_month"],
        documents_uploaded=docs_count,
        team_members=members_count,
    )
