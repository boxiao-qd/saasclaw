from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime
from app.schemas.common import PaginationMeta


class SearchResultItem(BaseModel):
    session_id: str
    session_title: Optional[str] = None
    snippet: str
    message_id: Optional[str] = None
    timestamp: Optional[datetime] = None


class SearchResponse(BaseModel):
    results: list[SearchResultItem]
    pagination: PaginationMeta