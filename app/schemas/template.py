from pydantic import BaseModel


class TemplateResponse(BaseModel):
    id: str
    name: str
    description: str
    category: str
    install_count: int  # COUNT(*) from template_installs — never fabricated

    class Config:
        from_attributes = True


class InstallTemplateRequest(BaseModel):
    workspace_id: str
