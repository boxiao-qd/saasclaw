"""Pydantic schemas for MCP server configuration API."""

from pydantic import BaseModel, Field
from typing import Optional


class McpServerCreateRequest(BaseModel):
    name: str = Field(..., pattern=r"^[a-z][a-z0-9_]{1,63}$", description="Server name in slug format")
    transport_type: str = Field(..., pattern=r"^(stdio|sse)$", description="Transport protocol type")
    command: Optional[str] = Field(None, description="Absolute path command for stdio transport")
    args: Optional[list[str]] = Field(None, description="Command arguments for stdio transport")
    env: Optional[dict[str, str]] = Field(None, description="Environment variables (sensitive values redacted in DB)")
    url: Optional[str] = Field(None, description="SSE/HTTP endpoint URL")
    headers: Optional[dict[str, str]] = Field(None, description="HTTP headers for SSE transport")
    is_enabled: bool = Field(True, description="Whether the server is enabled on startup")


class McpServerUpdateRequest(BaseModel):
    transport_type: Optional[str] = Field(None, pattern=r"^(stdio|sse)$")
    command: Optional[str] = None
    args: Optional[list[str]] = None
    env: Optional[dict[str, str]] = None
    url: Optional[str] = None
    headers: Optional[dict[str, str]] = None
    is_enabled: Optional[bool] = None


class McpServerToolInfo(BaseModel):
    name: str
    description: Optional[str] = None
    input_schema: Optional[dict] = None


class McpServerResponse(BaseModel):
    id: str
    name: str
    transport_type: str
    command: Optional[str] = None
    args: Optional[list[str]] = None
    env: Optional[dict[str, str]] = None
    url: Optional[str] = None
    headers: Optional[dict[str, str]] = None
    is_enabled: bool
    status: str
    last_error: Optional[str] = None
    tools: Optional[list[McpServerToolInfo]] = None


class McpServerListResponse(BaseModel):
    servers: list[McpServerResponse]