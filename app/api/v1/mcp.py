"""MCP server configuration API — CRUD endpoints + connect/disconnect/tools actions.

Config source: single global JSON file (data/mcp_servers.json).
Runtime state held in MCPConnectionManager memory.
"""

import json
import logging

from fastapi import APIRouter, Depends, HTTPException

from app.dependencies import get_employee_id
from app.agent.mcp.config_validator import validate_mcp_config, redact_sensitive_values
from app.agent.mcp.connection_manager import MCPConnectionManager
from app.schemas.mcp_server_schema import (
    McpServerCreateRequest,
    McpServerUpdateRequest,
    McpServerResponse,
    McpServerListResponse,
    McpServerToolInfo,
)
from app.schemas.common import SuccessResponse

log = logging.getLogger(__name__)

router = APIRouter()


def _config_to_response(name: str, config: dict, conn_status: dict | None = None) -> McpServerResponse:
    """Merge file config + runtime status into API response."""
    status = conn_status.get("status", "disconnected") if conn_status else "disconnected"
    last_error = (conn_status.get("last_error")) if conn_status else None
    tools = None
    if conn_status and conn_status.get("tools"):
        tools = [McpServerToolInfo(**t) for t in conn_status["tools"]]

    is_enabled = not config.get("disabled", False)

    return McpServerResponse(
        id=name,  # name serves as identifier in file-based config
        name=name,
        transport_type=config.get("type", "stdio"),
        command=config.get("command"),
        args=config.get("args"),
        env=config.get("env"),
        url=config.get("url"),
        headers=config.get("headers"),
        is_enabled=is_enabled,
        status=status,
        last_error=last_error,
        tools=tools,
    )


@router.get("/mcp/servers", response_model=McpServerListResponse)
async def list_mcp_servers(employee_id: int = Depends(get_employee_id)):
    cm = MCPConnectionManager.get_instance()
    servers = cm.load_config()
    responses = []
    for name, config in servers.items():
        conn_status = cm.get_server_status(name)
        responses.append(_config_to_response(name, config, conn_status))
    return McpServerListResponse(servers=responses)


@router.get("/mcp/servers/{name}", response_model=McpServerResponse)
async def get_mcp_server(name: str, employee_id: int = Depends(get_employee_id)):
    cm = MCPConnectionManager.get_instance()
    servers = cm.load_config()
    if name not in servers:
        raise HTTPException(status_code=404, detail=f"MCP server '{name}' not found")
    return _config_to_response(name, servers[name], cm.get_server_status(name))


@router.post("/mcp/servers", response_model=McpServerResponse, status_code=201)
async def create_mcp_server(
    req: McpServerCreateRequest,
    employee_id: int = Depends(get_employee_id),
):
    data = req.model_dump()
    errors = validate_mcp_config(data)
    if errors:
        raise HTTPException(status_code=400, detail={"validation_errors": errors})

    # Convert API fields to config file format
    name = data["name"]
    config = {
        "type": data["transport_type"],
    }
    if data.get("command"):
        config["command"] = data["command"]
    if data.get("args"):
        config["args"] = data["args"]
    if data.get("env"):
        config["env"] = redact_sensitive_values({"env": data["env"]})["env"]
    if data.get("url"):
        config["url"] = data["url"]
    if data.get("headers"):
        config["headers"] = redact_sensitive_values({"headers": data["headers"]})["headers"]
    if not data.get("is_enabled", True):
        config["disabled"] = True

    # Check duplicate
    cm = MCPConnectionManager.get_instance()
    existing = cm.load_config()
    if name in existing:
        raise HTTPException(status_code=409, detail=f"MCP server '{name}' already exists")

    cm.add_server_config(name, config)

    # Auto-connect if enabled
    conn_status = None
    if not config.get("disabled"):
        try:
            conn = await cm.connect_server(name, config)
            conn_status = cm.get_server_status(name)
        except Exception as e:
            log.error("MCP server '%s' auto-connect failed: %s", name, e)

    return _config_to_response(name, config, conn_status)


@router.patch("/mcp/servers/{name}", response_model=McpServerResponse)
async def update_mcp_server(
    name: str,
    req: McpServerUpdateRequest,
    employee_id: int = Depends(get_employee_id),
):
    cm = MCPConnectionManager.get_instance()
    servers = cm.load_config()
    if name not in servers:
        raise HTTPException(status_code=404, detail=f"MCP server '{name}' not found")

    data = req.model_dump(exclude_unset=True)
    if not data:
        return _config_to_response(name, servers[name], cm.get_server_status(name))

    # Validate merged config
    merged_config = dict(servers[name])
    merged_config["name"] = name
    if "transport_type" in data:
        merged_config["type"] = data["transport_type"]
    for field in ("command", "url"):
        if field in data:
            merged_config[field] = data[field]
    if "args" in data:
        merged_config["args"] = data["args"]
    if "env" in data:
        merged_config["env"] = redact_sensitive_values({"env": data["env"]})["env"]
    if "headers" in data:
        merged_config["headers"] = redact_sensitive_values({"headers": data["headers"]})["headers"]
    if "is_enabled" in data:
        merged_config["disabled"] = not data["is_enabled"]

    errors = validate_mcp_config(merged_config)
    if errors:
        raise HTTPException(status_code=400, detail={"validation_errors": errors})

    # Disconnect old connection before config change
    await cm.disconnect_server(name)

    # Save updated config
    updated = cm.update_server_config(name, {
        k: v for k, v in merged_config.items() if k != "name"
    })

    # Re-connect if enabled
    conn_status = None
    if not updated.get("disabled"):
        try:
            conn = await cm.connect_server(name, updated)
            conn_status = cm.get_server_status(name)
        except Exception as e:
            log.error("MCP server '%s' re-connect failed: %s", name, e)

    return _config_to_response(name, updated, conn_status)


@router.delete("/mcp/servers/{name}", response_model=SuccessResponse)
async def delete_mcp_server(name: str, employee_id: int = Depends(get_employee_id)):
    cm = MCPConnectionManager.get_instance()
    servers = cm.load_config()
    if name not in servers:
        raise HTTPException(status_code=404, detail=f"MCP server '{name}' not found")

    await cm.disconnect_server(name)
    cm.remove_server_config(name)
    return SuccessResponse()


@router.post("/mcp/servers/{name}/connect", response_model=McpServerResponse)
async def connect_mcp_server(name: str, employee_id: int = Depends(get_employee_id)):
    cm = MCPConnectionManager.get_instance()
    servers = cm.load_config()
    if name not in servers:
        raise HTTPException(status_code=404, detail=f"MCP server '{name}' not found")

    config = servers[name]
    try:
        conn = await cm.connect_server(name, config)
        conn_status = cm.get_server_status(name)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    return _config_to_response(name, config, conn_status)


@router.post("/mcp/servers/{name}/disconnect", response_model=McpServerResponse)
async def disconnect_mcp_server(name: str, employee_id: int = Depends(get_employee_id)):
    cm = MCPConnectionManager.get_instance()
    servers = cm.load_config()
    if name not in servers:
        raise HTTPException(status_code=404, detail=f"MCP server '{name}' not found")

    await cm.disconnect_server(name)
    return _config_to_response(name, servers[name])


@router.get("/mcp/servers/{name}/tools", response_model=list[McpServerToolInfo])
async def get_mcp_server_tools(name: str, employee_id: int = Depends(get_employee_id)):
    cm = MCPConnectionManager.get_instance()
    conn_status = cm.get_server_status(name)
    if conn_status and conn_status.get("tools"):
        return [McpServerToolInfo(**t) for t in conn_status["tools"]]
    return []