import csv
import io
import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import require_member
from app.models.bot import Bot
from app.models.lead import Lead
from app.models.workspace import WorkspaceMembership
from app.schemas.lead import LeadCreateRequest, LeadResponse

router = APIRouter(prefix="/workspaces/{workspace_id}/leads", tags=["leads"])


@router.get("", response_model=list[LeadResponse])
async def list_leads(
    workspace_id: uuid.UUID,
    bot_id: uuid.UUID | None = None,
    _membership: WorkspaceMembership = Depends(require_member),
    db: AsyncSession = Depends(get_db),
) -> list[LeadResponse]:
    query = select(Lead).where(Lead.workspace_id == workspace_id)
    if bot_id:
        query = query.where(Lead.bot_id == bot_id)
    result = await db.execute(query.order_by(Lead.captured_at.desc()))
    return list(result.scalars().all())


@router.post("", response_model=LeadResponse, status_code=status.HTTP_201_CREATED)
async def create_lead(
    workspace_id: uuid.UUID,
    body: LeadCreateRequest,
    _membership: WorkspaceMembership = Depends(require_member),
    db: AsyncSession = Depends(get_db),
) -> LeadResponse:
    bot = await db.get(Bot, uuid.UUID(body.bot_id))
    if not bot or bot.workspace_id != workspace_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Bot not found")

    lead = Lead(
        workspace_id=workspace_id,
        bot_id=bot.id,
        conversation_id=uuid.UUID(body.conversation_id) if body.conversation_id else None,
        name=body.name, email=body.email, phone=body.phone, company=body.company,
    )
    db.add(lead)
    await db.commit()
    return lead


@router.get("/export.csv")
async def export_leads_csv(
    workspace_id: uuid.UUID,
    _membership: WorkspaceMembership = Depends(require_member),
    db: AsyncSession = Depends(get_db),
) -> StreamingResponse:
    result = await db.execute(select(Lead).where(Lead.workspace_id == workspace_id).order_by(Lead.captured_at.desc()))
    leads = result.scalars().all()

    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(["Name", "Email", "Phone", "Company", "Captured At"])
    for lead in leads:
        writer.writerow([lead.name, lead.email, lead.phone or "", lead.company or "", lead.captured_at.isoformat()])
    buffer.seek(0)

    return StreamingResponse(
        iter([buffer.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=leads.csv"},
    )
