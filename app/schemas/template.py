from pydantic import BaseModel

from app.schemas import ResponseBase


class TemplateResponse(ResponseBase):
    id: str
    name: str
    description: str
    category: str
    install_count: int  # COUNT(*) from template_installs — never fabricated


class InstallTemplateRequest(BaseModel):
    workspace_id: str
