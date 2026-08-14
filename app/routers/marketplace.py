import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import require_admin
from app.models.bot import Bot, ChatProviderName
from app.models.billing import PLAN_LIMITS, Subscription
from app.models.template import Template, TemplateInstall
from app.models.workspace import WorkspaceMembership
from app.schemas.bot import BotResponse
from app.schemas.template import TemplateResponse

router = APIRouter(tags=["marketplace"])


@router.get("/templates", response_model=list[TemplateResponse])
async def list_templates(db: AsyncSession = Depends(get_db)) -> list[TemplateResponse]:
    result = await db.execute(
        select(Template, func.count(TemplateInstall.id))
        .outerjoin(TemplateInstall, TemplateInstall.template_id == Template.id)
        .where(Template.is_public.is_(True))
        .group_by(Template.id)
        .order_by(Template.name)
    )
    return [
        TemplateResponse(
            id=str(t.id), name=t.name, description=t.description, category=t.category, install_count=count
        )
        for t, count in result.all()
    ]


@router.post(
    "/workspaces/{workspace_id}/templates/{template_id}/install",
    response_model=BotResponse,
    status_code=status.HTTP_201_CREATED,
)
async def install_template(
    workspace_id: uuid.UUID,
    template_id: uuid.UUID,
    _membership: WorkspaceMembership = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> BotResponse:
    template = await db.get(Template, template_id)
    if not template or not template.is_public:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Template not found")

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
        name=template.name,
        persona=template.persona,
        chat_provider=ChatProviderName.ANTHROPIC,
        chat_model="claude-sonnet-4-6",
    )
    db.add(bot)
    await db.flush()

    db.add(TemplateInstall(template_id=template.id, workspace_id=workspace_id, bot_id=bot.id))
    await db.commit()
    return bot
