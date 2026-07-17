from datetime import datetime

from pydantic import BaseModel, Field

from app.models.knowledge import DocumentSourceType, DocumentStatus


class DocumentCreateFromTextRequest(BaseModel):
    name: str = Field(min_length=1, max_length=300)
    text: str = Field(min_length=1)


class DocumentCreateFromUrlRequest(BaseModel):
    name: str = Field(min_length=1, max_length=300)
    url: str
    is_sitemap: bool = False


class DocumentResponse(BaseModel):
    id: str
    name: str
    source_type: DocumentSourceType
    status: DocumentStatus
    char_count: int | None
    error_message: str | None
    created_at: datetime

    class Config:
        from_attributes = True


class ChunkResponse(BaseModel):
    id: str
    chunk_index: int
    content: str

    class Config:
        from_attributes = True
