import uuid

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.user import User
from app.models.workspace import MembershipStatus, Workspace, WorkspaceMembership, WorkspaceRole
from app.security import decode_access_token

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login", auto_error=False)


async def get_current_user(
    token: str | None = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_db),
) -> User:
    if not token:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Not authenticated")
    user_id = decode_access_token(token)
    if not user_id:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid or expired token")
    user = await db.get(User, user_id)
    if not user or not user.is_active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "User not found or inactive")
    return user


class CurrentMembership:
    """Resolves and validates that `current_user` belongs to `workspace_id`.

    This is the single tenant-isolation checkpoint: every workspace-scoped
    router depends on this (directly or via `require_role`) so a user can
    never read or write another workspace's bots/documents/conversations/
    leads/analytics — there is no code path that skips this check.
    """

    def __init__(self, *allowed_roles: WorkspaceRole):
        self.allowed_roles = set(allowed_roles) if allowed_roles else None

    async def __call__(
        self,
        workspace_id: uuid.UUID,
        current_user: User = Depends(get_current_user),
        db: AsyncSession = Depends(get_db),
    ) -> WorkspaceMembership:
        result = await db.execute(
            select(WorkspaceMembership).where(
                WorkspaceMembership.workspace_id == workspace_id,
                WorkspaceMembership.user_id == current_user.id,
                WorkspaceMembership.status == MembershipStatus.ACTIVE,
            )
        )
        membership = result.scalar_one_or_none()
        if not membership:
            # 404, not 403 — don't reveal whether the workspace exists to a non-member
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Workspace not found")
        if self.allowed_roles and membership.role not in self.allowed_roles:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "You don't have permission to do this")
        return membership


# Convenience instances for common role requirements
require_member = CurrentMembership()  # any active role
require_admin = CurrentMembership(WorkspaceRole.OWNER, WorkspaceRole.ADMIN)
require_owner = CurrentMembership(WorkspaceRole.OWNER)


async def get_workspace_or_404(workspace_id: uuid.UUID, db: AsyncSession = Depends(get_db)) -> Workspace:
    workspace = await db.get(Workspace, workspace_id)
    if not workspace:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Workspace not found")
    return workspace
