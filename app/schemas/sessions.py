from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime
from app.schemas.common import PaginationMeta, SuccessResponse


class SessionItem(BaseModel):
    session_id: str
    title: Optional[str] = None
    model: Optional[str] = None
    created_at: datetime
    updated_at: Optional[datetime] = None
    message_count: int = 0
    is_active: bool = False


class SessionListResponse(BaseModel):
    sessions: list[SessionItem]
    pagination: PaginationMeta


class CreateSessionRequest(BaseModel):
    title: Optional[str] = None
    model: Optional[str] = None
    system_prompt: Optional[str] = None


class CreateSessionResponse(BaseModel):
    session_id: str
    title: Optional[str] = None
    model: str
    created_at: datetime