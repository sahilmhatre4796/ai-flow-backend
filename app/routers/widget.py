from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select

from app.database import AsyncSessionLocal
from app.models.bot import Bot

router = APIRouter(prefix="/widget", tags=["widget"])


class WidgetConfigResponse(BaseModel):
    bot_name: str
    color: str
    position: str


@router.get("/{public_key}/config", response_model=WidgetConfigResponse)
async def widget_config(public_key: str) -> WidgetConfigResponse:
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(Bot).where(Bot.public_key == public_key, Bot.is_active.is_(True)))
        bot = result.scalar_one_or_none()
        if not bot:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Bot not found or inactive")
        return WidgetConfigResponse(bot_name=bot.name, color=bot.widget_color, position=bot.widget_position)
