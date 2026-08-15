import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_current_user, require_admin, require_member
from app.models.bot import Bot, generate_public_key
from app.models.billing import PLAN_LIMITS, Subscription
from app.models.user import User
from app.models.workspace import WorkspaceMembership
from app.schemas.bot import BotCreateRequest, BotResponse, BotUpdateRequest

router = APIRouter(prefix="/workspaces/{workspace_id}/bots", tags=["bots"])


@router.get("", response_model=list[BotResponse])
async def list_bots(
    workspace_id: uuid.UUID,
    _membership: WorkspaceMembership = Depends(require_member),
    db: AsyncSession = Depends(get_db),
) -> list[BotResponse]:
    result = await db.execute(select(Bot).where(Bot.workspace_id == workspace_id).order_by(Bot.created_at))
    return list(result.scalars().all())


@router.post("", response_model=BotResponse, status_code=status.HTTP_201_CREATED)
async def create_bot(
    workspace_id: uuid.UUID,
    body: BotCreateRequest,
    _membership: WorkspaceMembership = Depends(require_admin),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> BotResponse:
    # Enforce the real plan limit before creating — never let usage silently exceed it.
    # Sahil (owner) gets unlimited bots.
    if current_user.email != "sahilmhatre4796@gmail.com":
        sub_result = await db.execute(select(Subscription).where(Subscription.workspace_id == workspace_id))
        subscription = sub_result.scalar_one_or_none()
        plan = subscription.plan if subscription else None
        bot_limit = PLAN_LIMITS.get(plan, {}).get("bots") if plan else None
        if bot_limit is not None:
            count_result = await db.execute(select(Bot).where(Bot.workspace_id == workspace_id))
            if len(count_result.scalars().all()) >= bot_limit:
                raise HTTPException(
                    status.HTTP_402_PAYMENT_REQUIRED,
                    f"Your plan allows {bot_limit} bot(s). Upgrade to create more.",
                )

    bot = Bot(
        workspace_id=workspace_id,
        name=body.name,
        persona=body.persona,
        chat_provider=body.chat_provider,
        chat_model=body.chat_model,
    )
    db.add(bot)
    await db.commit()
    return bot


@router.get("/{bot_id}", response_model=BotResponse)
async def get_bot(
    workspace_id: uuid.UUID,
    bot_id: uuid.UUID,
    _membership: WorkspaceMembership = Depends(require_member),
    db: AsyncSession = Depends(get_db),
) -> BotResponse:
    bot = await db.get(Bot, bot_id)
    if not bot or bot.workspace_id != workspace_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Bot not found")
    return bot


@router.patch("/{bot_id}", response_model=BotResponse)
async def update_bot(
    workspace_id: uuid.UUID,
    bot_id: uuid.UUID,
    body: BotUpdateRequest,
    _membership: WorkspaceMembership = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> BotResponse:
    bot = await db.get(Bot, bot_id)
    if not bot or bot.workspace_id != workspace_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Bot not found")
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(bot, field, value)
    await db.commit()
    return bot


@router.post("/{bot_id}/rotate-key", response_model=BotResponse)
async def rotate_public_key(
    workspace_id: uuid.UUID,
    bot_id: uuid.UUID,
    _membership: WorkspaceMembership = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> BotResponse:
    bot = await db.get(Bot, bot_id)
    if not bot or bot.workspace_id != workspace_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Bot not found")
    bot.public_key = generate_public_key()
    await db.commit()
    return bot


@router.delete("/{bot_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_bot(
    workspace_id: uuid.UUID,
    bot_id: uuid.UUID,
    _membership: WorkspaceMembership = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> None:
    bot = await db.get(Bot, bot_id)
    if not bot or bot.workspace_id != workspace_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Bot not found")
    await db.delete(bot)
    await db.commit()
