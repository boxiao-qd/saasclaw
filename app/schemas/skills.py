from pydantic import BaseModel, Field
from typing import Literal, Optional


class SkillItem(BaseModel):
    id: str
    name: str
    content_md: str
    header_description: Optional[str] = None
    object_key: Optional[str] = None
    is_global: bool = False
    usage_count: int = 0
    created_at: str
    source: Literal["user", "sys_infra"] = "user"
    version: Optional[str] = None
    slug: Optional[str] = None
    frontmatter: Optional[dict] = None


class SkillListResponse(BaseModel):
    skills: list[SkillItem]


class CreateSkillRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=64)
    content_md: str = Field(..., min_length=1)
    header_description: Optional[str] = Field(None, max_length=500)
    is_global: bool = False
    frontmatter: Optional[dict] = None


class CreateSkillResponse(BaseModel):
    id: str
    name: str
    created_at: str


class UpdateSkillRequest(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=64)
    content_md: Optional[str] = Field(None, min_length=1)
    header_description: Optional[str] = Field(None, max_length=500)
    frontmatter: Optional[dict] = None


class UpdateSkillResponse(BaseModel):
    id: str
    name: str
    content_md: str
    header_description: Optional[str] = None
    object_key: Optional[str] = None
    is_global: bool = False
    usage_count: int = 0
    updated_at: str


class UploadSkillContentResponse(BaseModel):
    id: str
    name: str
    object_key: str
    header_description: Optional[str] = None
    message: str
