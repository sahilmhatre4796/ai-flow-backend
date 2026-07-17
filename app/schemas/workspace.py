from datetime import datetime

from pydantic import BaseModel, EmailStr, Field

from app.models.workspace import MembershipStatus, WorkspaceRole


class WorkspaceCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=200)


class WorkspaceResponse(BaseModel):
    id: str
    name: str
    slug: str
    created_at: datetime
    role: WorkspaceRole  # the requesting user's role in this workspace

    class Config:
        from_attributes = True


class InviteMemberRequest(BaseModel):
    email: EmailStr
    role: WorkspaceRole = WorkspaceRole.AGENT


class MemberResponse(BaseModel):
    id: str
    user_id: str | None
    name: str
    email: str
    role: WorkspaceRole
    status: MembershipStatus

    class Config:
        from_attributes = True
