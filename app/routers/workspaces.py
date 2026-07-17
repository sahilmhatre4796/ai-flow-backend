import re
import secrets

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_current_user
from app.models.billing import Subscription
from app.models.user import User
from app.models.workspace import MembershipStatus, Workspace, WorkspaceMembership, WorkspaceRole
from app.schemas.workspace import WorkspaceCreateRequest, WorkspaceResponse

router = APIRouter(prefix="/workspaces", tags=["workspaces"])


def _slugify(name: str) -> str:
    base = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-") or "workspace"
    return f"{base}-{secrets.token_hex(3)}"


@router.post("", response_model=WorkspaceResponse, status_code=201)
async def create_workspace(
    body: WorkspaceCreateRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> WorkspaceResponse:
    workspace = Workspace(name=body.name, slug=_slugify(body.name), owner_id=current_user.id)
    db.add(workspace)
    await db.flush()

    db.add(
        WorkspaceMembership(
            workspace_id=workspace.id,
            user_id=current_user.id,
            role=WorkspaceRole.OWNER,
            status=MembershipStatus.ACTIVE,
        )
    )
    db.add(Subscription(workspace_id=workspace.id))  # defaults to FREE/ACTIVE
    await db.commit()

    return WorkspaceResponse(
        id=str(workspace.id), name=workspace.name, slug=workspace.slug,
        created_at=workspace.created_at, role=WorkspaceRole.OWNER,
    )


@router.get("/me", response_model=list[WorkspaceResponse])
async def my_workspaces(
    current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
) -> list[WorkspaceResponse]:
    result = await db.execute(
        select(WorkspaceMembership, Workspace)
        .join(Workspace, Workspace.id == WorkspaceMembership.workspace_id)
        .where(WorkspaceMembership.user_id == current_user.id, WorkspaceMembership.status == MembershipStatus.ACTIVE)
    )
    return [
        WorkspaceResponse(id=str(ws.id), name=ws.name, slug=ws.slug, created_at=ws.created_at, role=membership.role)
        for membership, ws in result.all()
    ]
