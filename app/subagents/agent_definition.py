"""AgentDefinition Pydantic model — aligned with cc-source BaseAgentDefinition."""

from __future__ import annotations
from enum import Enum
from pydantic import BaseModel, Field


class AgentSource(str, Enum):
    BUILTIN = "builtin"
    DATABASE = "database"


class PermissionMode(str, Enum):
    DEFAULT = "default"
    ACCEPT_EDITS = "acceptEdits"
    PLAN = "plan"
    BYPASS_PERMISSIONS = "bypassPermissions"


class AgentDefinition(BaseModel):
    agent_type: str = Field(..., description="Agent type identifier, e.g. 'Explore', 'Plan'")
    when_to_use: str = Field(..., description="Description of when to use this agent")
    source: AgentSource = AgentSource.BUILTIN
    system_prompt: str = Field(..., description="Full AGENT.md body as system prompt")
    tools: list[str] | None = Field(None, description="Allowlist; None = all tools available")
    disallowed_tools: list[str] | None = Field(None, description="Denylist of tools to exclude")
    max_turns: int = Field(10, description="Maximum agentic turns before forced stop")
    model: str | None = Field(None, description="Model override; 'inherit' = use parent model")
    permission_mode: PermissionMode | None = None
    skills: list[str] | None = Field(None, description="Skill names to preload")
    color: str | None = Field(None, description="Display color for agent identification")
    background: bool = Field(False, description="Always run as background task")
    filename: str | None = Field(None, description="Original filename without .md extension")
    resource_dir: str | None = Field(None, description="Absolute path to the agent's directory for ${AGENT_DIR} resolution")


class AgentDefinitionSummary(BaseModel):
    agent_type: str
    when_to_use: str
    source: AgentSource
    tools: list[str] | None = None
    disallowed_tools: list[str] | None = None
    color: str | None = None
    model: str | None = None


class AgentDefinitionListResponse(BaseModel):
    agents: list[AgentDefinitionSummary]