from enum import Enum
from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime


class RoleEnum(str, Enum):
    user = "user"
    assistant = "assistant"
    system = "system"
    tool = "tool"


class SuccessResponse(BaseModel):
    success: bool = True


class ErrorResponse(BaseModel):
    error_code: str
    message: str
    detail: Optional[dict] = None


class PaginationMeta(BaseModel):
    total: int
    page: int = 1
    page_size: int = 20