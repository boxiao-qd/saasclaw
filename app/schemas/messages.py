from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime
from app.schemas.common import RoleEnum, PaginationMeta, SuccessResponse


class SendMessageRequest(BaseModel):
    session_id: str = Field(..., min_length=1, max_length=36)
    content: str = Field(..., min_length=1)
    role: RoleEnum = RoleEnum.user


class SendMessageResponse(BaseModel):
    message_id: str
    created_at: datetime


class MessageItem(BaseModel):
    id: str
    session_id: str
    role: str
    content: Optional[str] = None
    tool_calls: Optional[list] = None
    tool_name: Optional[str] = None
    tool_call_id: Optional[str] = None
    reasoning_content: Optional[str] = None
    token_count: int = 0
    is_compressed: bool = False
    created_at: datetime


class MessageHistoryResponse(BaseModel):
    messages: list[MessageItem]
    has_more: bool