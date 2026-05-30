from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime


class MemoryItem(BaseModel):
    id: str
    key: str
    value: str
    source: str
    created_at: datetime


class MemoryListResponse(BaseModel):
    memories: list[MemoryItem]


class CreateMemoryRequest(BaseModel):
    key: str = Field(..., min_length=1, max_length=256)
    value: str = Field(..., min_length=1)


class CreateMemoryResponse(BaseModel):
    id: str
    key: str
    created_at: datetime