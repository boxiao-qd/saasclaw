"""MCP connection manager — singleton managing all MCP server connections.

Config source: single global JSON file (data/mcp_servers.json).
Runtime state (status, discovered tools, errors) held in memory only.

Lifecycle: load config → connect → discover tools → register → health check → reconnect → disconnect.
Uses Python MCP SDK (mcp >= 1.27) for transport and client sessions.

Connection pattern: each MCP server runs in a background asyncio Task that holds
the transport context manager open. Other code calls session methods via stored reference.
"""

import asyncio
import json
import logging
import os
from pathlib import Path

from mcp import ClientSession
from mcp.client.stdio import stdio_client, StdioServerParameters
from mcp.client.sse import sse_client

from app.agent.mcp.config_validator import validate_mcp_config, redact_sensitive_values
from app.agent.mcp.tool_registry_bridge import register_mcp_tools, unregister_mcp_tools
from app.config import settings

log = logging.getLogger(__name__)

_MAX_TOOLS_PER_SERVER = 20
_MAX_MCP_TOOLS_GLOBAL = 100
_RECONNECT_MAX_ATTEMPTS = 5
_RECONNECT_BASE_DELAY = 1.0
_RECONNECT_MAX_DELAY = 30.0
_HEALTH_CHECK_INTERVAL = 30
_CALL_TOOL_TIMEOUT = 30.0


class MCPConnection:
    """Represents a single MCP server connection."""

    def __init__(self, name: str, config: dict):
        self.name = name
        self.config = config
        self.status: str = "disconnected"
        self.last_error: str | None = None
        self.session: ClientSession | None = None
        self._bg_task: asyncio.Task | None = None
        self._reconnect_attempts = 0
        self._call_lock = asyncio.Lock()
        self._tools: list[dict] = []
        self._init_event = asyncio.Event()

    @property
    def is_connected(self) -> bool:
        return self.status == "connected" and self.session is not None


class MCPConnectionManager:
    """Singleton managing all MCP server connections. Config from JSON file."""

    _instance: "MCPConnectionManager | None" = None

    def __init__(self):
        self._connections: dict[str, MCPConnection] = {}
        self._health_task: asyncio.Task | None = None
        self._stopping = False
        self._config_path = Path(settings.mcp_config_path)

    @classmethod
    def get_instance(cls) -> "MCPConnectionManager":
        if cls._instance is None:
            cls._instance = MCPConnectionManager()
        return cls._instance

    @classmethod
    def reset_instance(cls) -> None:
        if cls._instance:
            cls._instance._stopping = True
            if cls._instance._health_task and not cls._instance._health_task.done():
                cls._instance._health_task.cancel()
            cls._instance = None

    # ─── Config file I/O ──────────────────────────────────────────

    def load_config(self) -> dict[str, dict]:
        """Load MCP server configs from JSON file. Returns {name: config_dict}."""
        if not self._config_path.exists():
            return {}
        try:
            data = json.loads(self._config_path.read_text(encoding="utf-8"))
            return data.get("mcpServers", {})
        except Exception as e:
            log.error("Failed to load MCP config from %s: %s", self._config_path, e)
            return {}

    def save_config(self, servers: dict[str, dict]) -> None:
        """Save MCP server configs to JSON file."""
        self._config_path.parent.mkdir(parents=True, exist_ok=True)
        data = {"mcpServers": servers}
        self._config_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        log.info("Saved MCP config to %s (%d servers)", self._config_path, len(servers))

    def add_server_config(self, name: str, config: dict) -> None:
        """Add a single server config to file."""
        servers = self.load_config()
        servers[name] = config
        self.save_config(servers)

    def remove_server_config(self, name: str) -> None:
        """Remove a single server config from file."""
        servers = self.load_config()
        if name in servers:
            del servers[name]
            self.save_config(servers)

    def update_server_config(self, name: str, updates: dict) -> dict:
        """Merge updates into existing server config and save."""
        servers = self.load_config()
        if name not in servers:
            raise ValueError(f"Server '{name}' not found in config")
        servers[name].update(updates)
        self.save_config(servers)
        return servers[name]

    # ─── Connection lifecycle ──────────────────────────────────────

    async def connect_server(self, name: str, config: dict) -> MCPConnection:
        """Connect to an MCP server by starting a background connection task."""
        conn = MCPConnection(name, config)
        self._connections[name] = conn

        conn._bg_task = asyncio.create_task(self._connection_loop(conn))
        try:
            await asyncio.wait_for(conn._init_event.wait(), timeout=10.0)
        except asyncio.TimeoutError:
            log.warning("MCP server '%s' init timed out, status=%s", name, conn.status)

        return conn

    async def _connection_loop(self, conn: MCPConnection) -> None:
        conn.status = "connecting"
        try:
            if conn.config.get("type") == "sse":
                await self._run_sse(conn)
            else:
                await self._run_stdio(conn)
        except asyncio.CancelledError:
            log.info("MCP server '%s' connection task cancelled", conn.name)
        except Exception as e:
            conn.status = "error"
            conn.last_error = str(e)
            conn._init_event.set()
            log.error("MCP server '%s' connection failed: %s", conn.name, e)

    async def _run_stdio(self, conn: MCPConnection) -> None:
        env_resolved = self._resolve_env(conn.config.get("env") or {})
        server_params = StdioServerParameters(
            command=conn.config["command"],
            args=conn.config.get("args") or [],
            env=env_resolved if env_resolved else None,
        )

        async with stdio_client(server_params) as (read_stream, write_stream):
            async with ClientSession(read_stream, write_stream) as session:
                await session.initialize()
                conn.session = session
                conn.status = "connected"
                conn.last_error = None
                conn._reconnect_attempts = 0
                conn._init_event.set()
                log.info("MCP server '%s' (stdio) connected", conn.name)
                await self._discover_and_register(conn)
                while not self._stopping:
                    await asyncio.sleep(1)

    async def _run_sse(self, conn: MCPConnection) -> None:
        headers_resolved = self._resolve_headers(conn.config.get("headers") or {})

        async with sse_client(conn.config["url"], headers=headers_resolved) as (read_stream, write_stream):
            async with ClientSession(read_stream, write_stream) as session:
                await session.initialize()
                conn.session = session
                conn.status = "connected"
                conn.last_error = None
                conn._reconnect_attempts = 0
                conn._init_event.set()
                log.info("MCP server '%s' (sse) connected", conn.name)
                await self._discover_and_register(conn)
                while not self._stopping:
                    await asyncio.sleep(1)

    async def _discover_and_register(self, conn: MCPConnection) -> None:
        try:
            result = await conn.session.list_tools()
            raw_tools = result.tools or []

            if len(raw_tools) > _MAX_TOOLS_PER_SERVER:
                log.warning("MCP server '%s': %d tools, limiting to %d",
                            conn.name, len(raw_tools), _MAX_TOOLS_PER_SERVER)
                raw_tools = raw_tools[:_MAX_TOOLS_PER_SERVER]

            current_mcp_count = sum(len(c._tools) for c in self._connections.values() if c.name != conn.name)
            remaining = _MAX_MCP_TOOLS_GLOBAL - current_mcp_count
            if len(raw_tools) > remaining:
                raw_tools = raw_tools[:remaining]

            conn._tools = [
                {"name": t.name, "description": t.description[:2048], "inputSchema": t.inputSchema}
                for t in raw_tools if t.name and t.description
            ]
            register_mcp_tools(conn.name, conn._tools, self)
            log.info("MCP server '%s': registered %d tools", conn.name, len(conn._tools))
        except Exception as e:
            log.error("MCP server '%s' tool discovery failed: %s", conn.name, e)
            conn.last_error = f"Tool discovery failed: {e}"

    async def call_tool(self, server_name: str, tool_name: str, arguments: dict) -> str:
        """Call an MCP tool through the connected server."""
        conn = self._connections.get(server_name)
        if not conn or not conn.is_connected:
            return json.dumps({"error": f"MCP server '{server_name}' not connected"}, ensure_ascii=False)

        async with conn._call_lock:
            try:
                result = await asyncio.wait_for(
                    conn.session.call_tool(name=tool_name, arguments=arguments),
                    timeout=_CALL_TOOL_TIMEOUT,
                )
                parts = []
                for content in (result.content or []):
                    if hasattr(content, "text"):
                        parts.append(content.text)
                    else:
                        parts.append(str(content))
                output = "\n".join(parts) if parts else ""
                if result.isError:
                    return json.dumps({"error": output}, ensure_ascii=False)
                return output
            except asyncio.TimeoutError:
                return json.dumps({"error": f"MCP tool call timed out ({_CALL_TOOL_TIMEOUT}s)"}, ensure_ascii=False)
            except Exception as e:
                return json.dumps({"error": f"MCP tool call failed: {e}"}, ensure_ascii=False)

    async def disconnect_server(self, name: str) -> None:
        """Disconnect: cancel background task, unregister tools."""
        conn = self._connections.get(name)
        if not conn:
            return
        if conn._bg_task and not conn._bg_task.done():
            conn._bg_task.cancel()
            try:
                await conn._bg_task
            except asyncio.CancelledError:
                pass
        conn.session = None
        conn.status = "disconnected"
        conn.last_error = None
        unregister_mcp_tools(name)
        log.info("MCP server '%s' disconnected", name)

    async def reconnect_server(self, name: str) -> MCPConnection | None:
        conn = self._connections.get(name)
        if not conn:
            return None
        await self.disconnect_server(name)

        for attempt in range(_RECONNECT_MAX_ATTEMPTS):
            delay = min(_RECONNECT_BASE_DELAY * (2 ** attempt), _RECONNECT_MAX_DELAY)
            log.info("MCP server '%s' reconnect attempt %d/%d (delay=%.1fs)",
                     name, attempt + 1, _RECONNECT_MAX_ATTEMPTS, delay)
            await asyncio.sleep(delay)
            try:
                conn._init_event.clear()
                conn._bg_task = asyncio.create_task(self._connection_loop(conn))
                await asyncio.wait_for(conn._init_event.wait(), timeout=10.0)
                if conn.is_connected:
                    return conn
            except Exception as e:
                log.warning("MCP server '%s' reconnect %d failed: %s", name, attempt + 1, e)

        log.error("MCP server '%s' reconnect exhausted", name)
        conn.status = "error"
        conn.last_error = f"Reconnect failed after {_RECONNECT_MAX_ATTEMPTS} attempts"
        return conn

    async def start_health_check(self) -> None:
        if self._health_task and not self._health_task.done():
            return
        self._health_task = asyncio.create_task(self._health_check_loop())

    async def _health_check_loop(self) -> None:
        while not self._stopping:
            await asyncio.sleep(_HEALTH_CHECK_INTERVAL)
            for name, conn in list(self._connections.items()):
                if not conn.is_connected:
                    continue
                try:
                    await asyncio.wait_for(conn.session.list_tools(), timeout=5.0)
                except Exception as e:
                    log.warning("MCP server '%s' health check failed: %s", name, e)
                    conn.status = "error"
                    conn.last_error = f"Health check failed: {e}"
                    asyncio.create_task(self.reconnect_server(name))

    async def startup_from_config(self) -> None:
        """Load config file and auto-connect enabled servers."""
        servers = self.load_config()
        for name, config in servers.items():
            if config.get("disabled"):
                log.info("MCP server '%s' is disabled, skipping", name)
                continue
            log.info("Auto-connecting MCP server '%s' (%s)", name, config.get("type", "stdio"))
            try:
                conn = await self.connect_server(name, config)
                if conn.is_connected:
                    log.info("MCP server '%s' connected with %d tools", name, len(conn._tools))
                else:
                    log.warning("MCP server '%s' status=%s error=%s", name, conn.status, conn.last_error)
            except Exception as e:
                log.error("MCP server '%s' auto-connect failed: %s", name, e)
        await self.start_health_check()

    async def shutdown_all(self) -> None:
        self._stopping = True
        if self._health_task and not self._health_task.done():
            self._health_task.cancel()
            try:
                await self._health_task
            except asyncio.CancelledError:
                pass
        for name in list(self._connections.keys()):
            await self.disconnect_server(name)
        log.info("MCPConnectionManager shutdown complete")

    # ─── Env/Header resolution ──────────────────────────────────────

    def _resolve_env(self, env_stored: dict) -> dict[str, str]:
        resolved = {}
        for key, val in env_stored.items():
            if val == "***REDACTED***":
                resolved[key] = os.getenv(key, "")
            else:
                resolved[key] = val
        return resolved

    def _resolve_headers(self, headers_stored: dict) -> dict[str, str]:
        resolved = {}
        for key, val in headers_stored.items():
            if val == "***REDACTED***":
                env_key = f"MCP_HEADER_{key.upper().replace('-', '_')}"
                resolved[key] = os.getenv(env_key, "")
            else:
                resolved[key] = val
        return resolved

    # ─── Status queries ──────────────────────────────────────────────

    def get_server_status(self, name: str) -> dict | None:
        conn = self._connections.get(name)
        if not conn:
            return None
        return {
            "name": conn.name,
            "type": conn.config.get("type", "stdio"),
            "status": conn.status,
            "last_error": conn.last_error,
            "tools_count": len(conn._tools),
            "tools": conn._tools,
        }

    def get_all_statuses(self) -> list[dict]:
        return [self.get_server_status(name) for name in self._connections]