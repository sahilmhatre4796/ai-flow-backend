import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import require_admin, require_member
from app.models.user import User
from app.models.workspace import MembershipStatus, Workspace, WorkspaceMembership
from app.schemas.workspace import InviteMemberRequest, MemberResponse
from app.tasks.email_tasks import send_invitation_email_task

router = APIRouter(prefix="/workspaces/{workspace_id}/members", tags=["team"])


@router.get("", response_model=list[MemberResponse])
async def list_members(
    workspace_id: uuid.UUID,
    _membership: WorkspaceMembership = Depends(require_member),
    db: AsyncSession = Depends(get_db),
) -> list[MemberResponse]:
    result = await db.execute(
        select(WorkspaceMembership, User)
        .outerjoin(User, User.id == WorkspaceMembership.user_id)
        .where(WorkspaceMembership.workspace_id == workspace_id)
    )
    members = []
    for membership, user in result.all():
        if user:
            name, email = user.full_name or user.email.split("@")[0], user.email
        else:
            name, email = (membership.invited_email or "").split("@")[0], membership.invited_email or ""
        members.append(
            MemberResponse(
                id=str(membership.id),
                user_id=str(membership.user_id) if membership.user_id else None,
                name=name,
                email=email,
                role=membership.role,
                status=membership.status,
            )
        )
    return members


@router.post("/invitations", response_model=MemberResponse, status_code=status.HTTP_201_CREATED)
async def invite_member(
    workspace_id: uuid.UUID,
    body: InviteMemberRequest,
    _membership: WorkspaceMembership = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> MemberResponse:
    existing_user_result = await db.execute(select(User).where(User.email == body.email))
    existing_user = existing_user_result.scalar_one_or_none()

    if existing_user:
        dup_clause = WorkspaceMembership.user_id == existing_user.id
    else:
        dup_clause = WorkspaceMembership.invited_email == body.email
    duplicate_check = await db.execute(
        select(WorkspaceMembership).where(WorkspaceMembership.workspace_id == workspace_id, dup_clause)
    )
    if duplicate_check.scalar_one_or_none():
        raise HTTPException(status.HTTP_409_CONFLICT, "This person is already a member or has a pending invite")

    membership = WorkspaceMembership(
        workspace_id=workspace_id,
        user_id=existing_user.id if existing_user else None,
        invited_email=None if existing_user else body.email,
        role=body.role,
        status=MembershipStatus.ACTIVE if existing_user else MembershipStatus.INVITED,
    )
    db.add(membership)
    await db.flush()

    workspace = await db.get(Workspace, workspace_id)
    send_invitation_email_task.delay(body.email, workspace.name if workspace else "AI FLOW")
    await db.commit()

    return MemberResponse(
        id=str(membership.id),
        user_id=str(membership.user_id) if membership.user_id else None,
        name=(existing_user.full_name if existing_user else body.email.split("@")[0]),
        email=body.email,
        role=membership.role,
        status=membership.status,
    )


@router.delete("/{membership_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_member(
    workspace_id: uuid.UUID,
    membership_id: uuid.UUID,
    _membership: WorkspaceMembership = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> None:
    target = await db.get(WorkspaceMembership, membership_id)
    if not target or target.workspace_id != workspace_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Member not found")
    if target.role.value == "owner":
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "The workspace owner can't be removed")
    await db.delete(target)
    await db.commit()
