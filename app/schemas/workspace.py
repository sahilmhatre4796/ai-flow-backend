from datetime import datetime

from pydantic import BaseModel, EmailStr, Field

from app.models.workspace import MembershipStatus, WorkspaceRole
from app.schemas import ResponseBase


class WorkspaceCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=200)


class WorkspaceResponse(ResponseBase):
    id: str
    name: str
    slug: str
    created_at: datetime
    role: WorkspaceRole  # the requesting user's role in this workspace


class InviteMemberRequest(BaseModel):
    email: EmailStr
    role: WorkspaceRole = WorkspaceRole.agent


class MemberResponse(ResponseBase):
    id: str
    user_id: str | None
    name: str
    email: str
    role: WorkspaceRole
    status: MembershipStatus
