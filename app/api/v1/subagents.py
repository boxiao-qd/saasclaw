import hashlib
import json
from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from app.dependencies import get_employee_id
from app.db.database import get_session_factory
from app.dao.subagent_dao import SubagentDAO
from app.subagents.agent_loader import SubagentLoader
from app.subagents.agent_definition import AgentDefinitionListResponse, AgentDefinitionSummary
from app.schemas.subagents import (
    SubagentListResponse, SubagentItem,
    CreateSubagentRequest, CreateSubagentResponse,
    UpdateSubagentRequest, UpdateSubagentResponse,
    UploadSubagentContentResponse,
)
from app.schemas.common import SuccessResponse

router = APIRouter()


@router.get("/agents", response_model=AgentDefinitionListResponse)
async def list_agents():
    """List all available agents — builtin (sys-infra) + DB, builtin priority."""
    loader = SubagentLoader.get_instance()
    agents = await loader.list_agents()
    return AgentDefinitionListResponse(agents=[
        AgentDefinitionSummary(
            agent_type=a.agent_type,
            when_to_use=a.when_to_use,
            source=a.source,
            tools=a.tools,
            disallowed_tools=a.disallowed_tools,
            color=a.color,
            model=a.model,
        )
        for a in agents
    ])


def _extract_header(content_md: str) -> str:
    for line in content_md.splitlines():
        line = line.strip().lstrip("#").strip()
        if line:
            return line[:500]
    return ""


def _parse_json_field(value: str | None, default: list) -> list:
    if not value:
        return default
    try:
        return json.loads(value)
    except Exception:
        return default


@router.get("/subagents", response_model=SubagentListResponse)
async def list_subagents(
    scope: str = Query("all", pattern="^(all|global|personal)$"),
    employee_id: int = Depends(get_employee_id),
):
    dao = SubagentDAO(get_session_factory(), employee_id)
    items = await dao.list_subagents()
    if scope == "global":
        items = [s for s in items if s.employee_id == 0]
    elif scope == "personal":
        items = [s for s in items if s.employee_id != 0]
    return SubagentListResponse(subagents=[
        SubagentItem(
            id=s.id, name=s.name, definition_md=s.definition_md,
            header_description=s.header_description, object_key=s.object_key,
            tools=_parse_json_field(s.tools, []),
            constraints=_parse_json_field(s.constraints, []),
            is_global=bool(s.is_global), created_at=s.created_at,
        )
        for s in items
    ])


@router.get("/subagents/{subagent_id}", response_model=SubagentItem)
async def get_subagent(
    subagent_id: str,
    employee_id: int = Depends(get_employee_id),
):
    dao = SubagentDAO(get_session_factory(), employee_id)
    s = await dao.get_by_id(subagent_id)
    return SubagentItem(
        id=s.id, name=s.name, definition_md=s.definition_md,
        header_description=s.header_description, object_key=s.object_key,
        tools=_parse_json_field(s.tools, []),
        constraints=_parse_json_field(s.constraints, []),
        is_global=bool(s.is_global), created_at=s.created_at,
    )


@router.post("/subagents", response_model=CreateSubagentResponse)
async def create_subagent(
    req: CreateSubagentRequest,
    employee_id: int = Depends(get_employee_id),
):
    dao = SubagentDAO(get_session_factory(), employee_id)
    header = req.header_description or _extract_header(req.definition_md)
    subagent = await dao.create(
        name=req.name, definition_md=req.definition_md,
        tools=req.tools, constraints=req.constraints, is_global=req.is_global,
    )
    if header:
        await dao.update(subagent.id, header_description=header)
    return CreateSubagentResponse(id=subagent.id, name=subagent.name, created_at=subagent.created_at)


@router.put("/subagents/{subagent_id}", response_model=UpdateSubagentResponse)
async def update_subagent(
    subagent_id: str,
    req: UpdateSubagentRequest,
    employee_id: int = Depends(get_employee_id),
):
    dao = SubagentDAO(get_session_factory(), employee_id)
    update_kwargs = {}
    if req.name is not None:
        update_kwargs["name"] = req.name
    if req.definition_md is not None:
        update_kwargs["definition_md"] = req.definition_md
    if req.header_description is not None:
        update_kwargs["header_description"] = req.header_description
    if req.tools is not None:
        update_kwargs["tools"] = req.tools
    if req.constraints is not None:
        update_kwargs["constraints"] = req.constraints
    s = await dao.update(subagent_id, **update_kwargs)
    return UpdateSubagentResponse(
        id=s.id, name=s.name, definition_md=s.definition_md,
        header_description=s.header_description, object_key=s.object_key,
        tools=_parse_json_field(s.tools, []),
        constraints=_parse_json_field(s.constraints, []),
        is_global=bool(s.is_global), updated_at=s.updated_at,
    )


@router.delete("/subagents/{subagent_id}", response_model=SuccessResponse)
async def delete_subagent(
    subagent_id: str,
    employee_id: int = Depends(get_employee_id),
):
    dao = SubagentDAO(get_session_factory(), employee_id)
    await dao.soft_delete(subagent_id)
    return SuccessResponse()


class _UploadContentRequest(BaseModel):
    agent_md: str = Field(..., min_length=1)


@router.put("/subagents/{subagent_id}/content", response_model=UploadSubagentContentResponse)
async def upload_subagent_content(
    subagent_id: str,
    req: _UploadContentRequest,
    employee_id: int = Depends(get_employee_id),
):
    """Upload AGENT.md content to object storage and update object_key.

    Saves to user-config/{user_id}/subagents/{slug}/AGENT.md.
    Updates header_description from the first meaningful line.
    """
    from app.storage.object_storage import create_object_storage

    dao = SubagentDAO(get_session_factory(), employee_id)
    subagent = await dao.get_by_id(subagent_id)

    # Use subagent UUID as the unique directory name under user-subagent/ (flat layout).
    object_key_prefix = f"user-subagent/{subagent.id}"
    agentmd_key = f"{object_key_prefix}/AGENT.md"

    storage = create_object_storage()
    await storage.put(employee_id, agentmd_key, req.agent_md, content_type="text/markdown")

    content_hash = hashlib.md5(req.agent_md.encode()).hexdigest()
    header = _extract_header(req.agent_md)
    await dao.update_object_key(subagent_id, object_key_prefix, header_description=header)

    return UploadSubagentContentResponse(
        id=subagent.id,
        name=subagent.name,
        object_key=object_key_prefix,
        header_description=header,
        message=f"AGENT.md uploaded to {agentmd_key}",
    )
