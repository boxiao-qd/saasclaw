from pydantic import BaseModel, Field
from typing import Optional


class SubagentItem(BaseModel):
    id: str
    name: str
    definition_md: str
    header_description: Optional[str] = None
    object_key: Optional[str] = None
    tools: list[str]
    constraints: list[str]
    is_global: bool = False
    created_at: str


class SubagentListResponse(BaseModel):
    subagents: list[SubagentItem]


class CreateSubagentRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=64)
    definition_md: str = Field(..., min_length=1)
    header_description: Optional[str] = Field(None, max_length=500)
    tools: list[str]
    constraints: list[str]
    is_global: bool = False


class CreateSubagentResponse(BaseModel):
    id: str
    name: str
    created_at: str


class UpdateSubagentRequest(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=64)
    definition_md: Optional[str] = Field(None, min_length=1)
    header_description: Optional[str] = Field(None, max_length=500)
    tools: Optional[list[str]] = None
    constraints: Optional[list[str]] = None


class UpdateSubagentResponse(BaseModel):
    id: str
    name: str
    definition_md: str
    header_description: Optional[str] = None
    object_key: Optional[str] = None
    tools: list[str]
    constraints: list[str]
    is_global: bool = False
    updated_at: str


class UploadSubagentContentResponse(BaseModel):
    id: str
    name: str
    object_key: str
    header_description: Optional[str] = None
    message: str
