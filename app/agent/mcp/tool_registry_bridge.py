"""MCP tool registry bridge — dynamically register/unregister MCP tools
in the global tool _registry so the agent loop can discover and call them.

Tool naming: mcp__<server_name>__<tool_name>

Each MCP tool gets a TOOL_DEF (OpenAI function schema) built from the
MCP tool's name, description, and inputSchema, and an executor that
routes through MCPConnectionManager.call_tool().
"""

import json
import logging

from app.agent.tools import register_tool, unregister_tools_by_prefix

log = logging.getLogger(__name__)

_MCP_PREFIX = "mcp__"


def build_mcp_tool_def(server_name: str, tool_info: dict) -> dict:
    """Build an OpenAI-compatible TOOL_DEF from MCP tool metadata.

    tool_info: {"name": str, "description": str, "inputSchema": dict}
    Returns: {"type": "function", "function": {"name": ..., "description": ..., "parameters": ...}}
    """
    mcp_tool_name = tool_info["name"]
    full_name = f"{_MCP_PREFIX}{server_name}__{mcp_tool_name}"

    description = tool_info.get("description") or f"MCP tool '{mcp_tool_name}' from server '{server_name}'"

    # MCP inputSchema is already JSON Schema format — use it directly as parameters
    parameters = tool_info.get("inputSchema") or {"type": "object", "properties": {}}

    # Ensure parameters has the minimum required structure
    if "type" not in parameters:
        parameters["type"] = "object"

    return {
        "type": "function",
        "function": {
            "name": full_name,
            "description": description,
            "parameters": parameters,
        },
    }


def register_mcp_tools(server_name: str, tools: list[dict], connection_manager) -> int:
    """Register all MCP tools from a server into the global tool registry.

    connection_manager: MCPConnectionManager instance — used by executor to route calls.

    Returns: count of successfully registered tools.
    """
    count = 0
    for tool_info in tools:
        tool_def = build_mcp_tool_def(server_name, tool_info)
        full_name = tool_def["function"]["name"]

        # Build executor that routes through connection manager
        async def mcp_executor(args_str: str, employee_id: int) -> str:
            arguments = json.loads(args_str) if args_str else {}
            return await connection_manager.call_tool(server_name, tool_info["name"], arguments)

        register_tool(full_name, tool_def, mcp_executor)
        count += 1
        log.info("Registered MCP tool: %s", full_name)

    return count


def unregister_mcp_tools(server_name: str) -> int:
    """Unregister all MCP tools from a server by prefix."""
    prefix = f"{_MCP_PREFIX}{server_name}__"
    removed = unregister_tools_by_prefix(prefix)
    log.info("Unregistered %d MCP tools from server '%s'", removed, server_name)
    return removed