from datetime import datetime

from pydantic import BaseModel, Field

from app.models.knowledge import DocumentSourceType, DocumentStatus
from app.schemas import ResponseBase


class DocumentCreateFromTextRequest(BaseModel):
    name: str = Field(min_length=1, max_length=300)
    text: str = Field(min_length=1)


class DocumentCreateFromUrlRequest(BaseModel):
    name: str = Field(min_length=1, max_length=300)
    url: str
    is_sitemap: bool = False


class DocumentResponse(ResponseBase):
    id: str
    name: str
    source_type: DocumentSourceType
    status: DocumentStatus
    char_count: int | None
    error_message: str | None
    created_at: datetime


class ChunkResponse(ResponseBase):
    id: str
    chunk_index: int
    content: str
