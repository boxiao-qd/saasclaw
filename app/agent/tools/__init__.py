"""Tool discovery — scan app/agent/tools/*.py, collect TOOL_DEF / TOOL_DEFS and execute functions.

The registry also supports dynamic registration/unregistration for MCP tools
at runtime via register_tool() / unregister_tools_by_prefix().
"""

import importlib
import logging
import os
from pathlib import Path

log = logging.getLogger(__name__)

_TOOLS_DIR = Path(__file__).parent
_registry: dict[str, dict] = {}  # {tool_name: {"def": TOOL_DEF, "executor": execute_fn}}
_discovered = False


def discover_tools() -> dict[str, dict]:
    """Scan tools/ directory, import each .py module, collect TOOL_DEF(s) and execute functions."""
    global _registry, _discovered
    if _discovered:
        return _registry

    for filename in sorted(os.listdir(_TOOLS_DIR)):
        if filename.startswith("_") or not filename.endswith(".py"):
            continue
        module_name = filename[:-3]
        try:
            module = importlib.import_module(f"app.agent.tools.{module_name}")
        except Exception as e:
            log.warning(f"Failed to import tool module '{module_name}': {e}")
            continue

        # Single-tool module: TOOL_DEF + execute
        if hasattr(module, "TOOL_DEF") and hasattr(module, "execute"):
            name = module.TOOL_DEF["function"]["name"]
            _registry[name] = {"def": module.TOOL_DEF, "executor": module.execute}

        # Multi-tool module: TOOL_DEFS list + named execute functions
        if hasattr(module, "TOOL_DEFS"):
            for tool_def in module.TOOL_DEFS:
                name = tool_def["function"]["name"]
                executor = getattr(module, name, None) or getattr(module, f"execute_{name}", None)
                if executor:
                    _registry[name] = {"def": tool_def, "executor": executor}

    _discovered = True
    return _registry


def register_tool(name: str, tool_def: dict, executor) -> None:
    """Dynamically register a tool (used for MCP tools at runtime)."""
    discover_tools()  # ensure base tools are loaded first
    if name in _registry:
        log.warning("Tool '%s' already registered, overwriting", name)
    _registry[name] = {"def": tool_def, "executor": executor}
    log.info("Dynamically registered tool: %s", name)


def unregister_tools_by_prefix(prefix: str) -> int:
    """Remove all tools whose name starts with prefix (e.g. 'mcp__svc__').

    Returns count of removed tools.
    """
    to_remove = [name for name in _registry if name.startswith(prefix)]
    for name in to_remove:
        del _registry[name]
        log.info("Unregistered tool: %s", name)
    return len(to_remove)


def get_tool_definitions(session_type: str = "full") -> list[dict]:
    """Return TOOL_DEF list for a session type.

    session_type: "full" (top-level, includes spawn_subagent)
                  "child" (delegated, excludes spawn_subagent)
    """
    registry = discover_tools()
    defs = [entry["def"] for entry in registry.values()]
    if session_type == "child":
        defs = [d for d in defs if d["function"]["name"] != "spawn_subagent"]
    return defs


def get_tool_executor(tool_name: str):
    """Return the async executor function for a tool."""
    registry = discover_tools()
    entry = registry.get(tool_name)
    return entry["executor"] if entry else None