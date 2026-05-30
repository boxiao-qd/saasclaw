from pydantic import BaseModel, Field
from typing import Optional


class ModelOption(BaseModel):
    model_id: str
    name: str
    description: Optional[str] = None


class ToolOption(BaseModel):
    tool_name: str
    display_name: str
    description: Optional[str] = None
    category: str


class SettingsResponse(BaseModel):
    models: list[ModelOption]
    current_model: Optional[str] = None
    enabled_tools: list[str]
    available_tools: list[ToolOption]


class UpdateSettingsRequest(BaseModel):
    model: Optional[str] = None
    tools: Optional[list[str]] = None