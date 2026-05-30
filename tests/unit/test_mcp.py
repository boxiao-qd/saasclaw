"""Unit tests for MCP configuration validator, tool registry bridge, and connection manager."""

import json
import pytest
import asyncio
import os
import tempfile
from pathlib import Path

from app.agent.mcp.config_validator import (
    validate_server_name,
    validate_stdio_command,
    validate_stdio_args,
    validate_sse_url,
    validate_mcp_config,
    redact_sensitive_values,
)
from app.agent.mcp.tool_registry_bridge import (
    build_mcp_tool_def,
    _MCP_PREFIX,
)
from app.agent.mcp.connection_manager import MCPConnectionManager, MCPConnection


# ─── Config Validator Tests ────────────────────────────────────

class TestServerNameValidation:
    def test_valid_names(self):
        assert validate_server_name("weather") == []
        assert validate_server_name("my_db_tool") == []
        assert validate_server_name("a123") == []

    def test_invalid_names(self):
        assert len(validate_server_name("Bad-Name")) > 0
        assert len(validate_server_name("UPPER")) > 0
        assert len(validate_server_name("123abc")) > 0
        assert len(validate_server_name("")) > 0


class TestStdioCommandValidation:
    def test_absolute_path_in_allowed_dir(self):
        errors = validate_stdio_command("/usr/bin/python3")
        path_errors = [e for e in errors if "absolute path" in e]
        assert len(path_errors) == 0

    def test_relative_path_rejected(self):
        errors = validate_stdio_command("python3")
        assert any("absolute path" in e for e in errors)

    def test_disallowed_directory_rejected(self):
        errors = validate_stdio_command("/tmp/malicious")
        assert any("allowed directories" in e for e in errors)

    def test_nonexistent_path_rejected(self):
        errors = validate_stdio_command("/usr/bin/nonexistent_binary")
        assert any("not exist" in e or "not a file" in e for e in errors)


class TestStdioArgsValidation:
    def test_clean_args_pass(self):
        assert validate_stdio_args(["--port", "8080", "--verbose"]) == []

    def test_shell_metacharacters_rejected(self):
        assert len(validate_stdio_args([";rm -rf /"])) > 0
        assert len(validate_stdio_args(["$(cat /etc/passwd)"])) > 0
        assert len(validate_stdio_args(["`whoami`"])) > 0

    def test_pipe_and_redirect_rejected(self):
        assert len(validate_stdio_args(["|grep secret"])) > 0
        assert len(validate_stdio_args([">output.txt"])) > 0


class TestSseUrlValidation:
    def test_valid_urls(self):
        assert validate_sse_url("https://example.com/mcp") == []
        assert validate_sse_url("http://localhost:8080/mcp/sse") == []

    def test_invalid_urls(self):
        assert len(validate_sse_url("ftp://bad.com")) > 0
        assert len(validate_sse_url("example.com/mcp")) > 0


class TestFullConfigValidation:
    def test_valid_stdio_config(self):
        errors = validate_mcp_config({
            "name": "my_tool",
            "transport_type": "stdio",
            "command": "/usr/bin/python3",
            "args": ["-m", "mcp_server"],
            "env": {"API_KEY": "test"},
        })
        structural_errors = [e for e in errors if "requires" in e or "must match" in e or "must be" in e]
        assert len(structural_errors) == 0

    def test_valid_sse_config(self):
        errors = validate_mcp_config({
            "name": "remote_api",
            "transport_type": "sse",
            "url": "https://api.example.com/mcp",
            "headers": {"Authorization": "Bearer test"},
        })
        assert len(errors) == 0

    def test_invalid_transport_type(self):
        errors = validate_mcp_config({"name": "bad", "transport_type": "websocket"})
        assert any("must be 'stdio' or 'sse'" in e for e in errors)

    def test_stdio_missing_command(self):
        errors = validate_mcp_config({"name": "test", "transport_type": "stdio"})
        assert any("requires 'command'" in e for e in errors)

    def test_sse_missing_url(self):
        errors = validate_mcp_config({"name": "test", "transport_type": "sse"})
        assert any("requires 'url'" in e for e in errors)


class TestRedaction:
    def test_env_redaction(self):
        data = {"env": {"API_KEY": "secret123", "PATH": "/usr/bin"}, "headers": {}}
        redacted = redact_sensitive_values(data)
        assert redacted["env"]["API_KEY"] == "***REDACTED***"
        assert redacted["env"]["PATH"] == "/usr/bin"

    def test_headers_redaction(self):
        data = {"env": {}, "headers": {"Authorization": "Bearer xyz", "X-Custom": "value"}}
        redacted = redact_sensitive_values(data)
        assert redacted["headers"]["Authorization"] == "***REDACTED***"
        assert redacted["headers"]["X-Custom"] == "value"

    def test_no_env_or_headers(self):
        data = {"name": "test"}
        redacted = redact_sensitive_values(data)
        assert redacted == {"name": "test"}


# ─── Tool Registry Bridge Tests ─────────────────────────────────

class TestBuildMcpToolDef:
    def test_basic_tool(self):
        tool_def = build_mcp_tool_def("weather", {
            "name": "get_forecast",
            "description": "Get weather forecast",
            "inputSchema": {"type": "object", "properties": {"city": {"type": "string"}}},
        })
        assert tool_def["function"]["name"] == "mcp__weather__get_forecast"
        assert tool_def["function"]["description"] == "Get weather forecast"
        assert tool_def["function"]["parameters"]["type"] == "object"

    def test_missing_schema_defaults(self):
        tool_def = build_mcp_tool_def("svc", {"name": "tool1", "description": "A tool"})
        assert tool_def["function"]["name"] == "mcp__svc__tool1"
        assert tool_def["function"]["parameters"]["type"] == "object"


# ─── Dynamic Registry Tests ─────────────────────────────────────

class TestDynamicRegistry:
    def test_register_and_unregister(self):
        from app.agent.tools import discover_tools, register_tool, unregister_tools_by_prefix, get_tool_definitions

        discover_tools()
        base_count = len(get_tool_definitions())

        tool_def = {
            "type": "function",
            "function": {
                "name": "mcp__testsvc__mock_tool",
                "description": "Mock tool for testing",
                "parameters": {"type": "object", "properties": {}},
            },
        }
        async def mock_executor(args_str, employee_id):
            return "mock result"

        register_tool("mcp__testsvc__mock_tool", tool_def, mock_executor)
        assert len(get_tool_definitions()) == base_count + 1

        removed = unregister_tools_by_prefix("mcp__testsvc__")
        assert removed == 1
        assert len(get_tool_definitions()) == base_count

    def test_unregister_no_match(self):
        from app.agent.tools import discover_tools, unregister_tools_by_prefix
        discover_tools()
        removed = unregister_tools_by_prefix("mcp__nonexistent__")
        assert removed == 0


# ─── Connection Manager Config File Tests ──────────────────────────

class TestConfigFileIO:
    def test_load_empty_file(self):
        cm = MCPConnectionManager.__new__(MCPConnectionManager)
        with tempfile.NamedTemporaryFile(suffix=".json", mode="w", delete=False) as f:
            json.dump({"mcpServers": {}}, f)
            cm._config_path = Path(f.name)
        servers = cm.load_config()
        assert servers == {}
        os.unlink(f.name)

    def test_load_with_servers(self):
        cm = MCPConnectionManager.__new__(MCPConnectionManager)
        with tempfile.NamedTemporaryFile(suffix=".json", mode="w", delete=False) as f:
            json.dump({
                "mcpServers": {
                    "weather": {"type": "stdio", "command": "/usr/bin/mcp-weather"},
                    "remote": {"type": "sse", "url": "https://api.example.com/mcp"},
                }
            }, f)
            cm._config_path = Path(f.name)
        servers = cm.load_config()
        assert "weather" in servers
        assert servers["weather"]["type"] == "stdio"
        assert "remote" in servers
        os.unlink(f.name)

    def test_load_missing_file(self):
        cm = MCPConnectionManager.__new__(MCPConnectionManager)
        cm._config_path = Path("/tmp/nonexistent_mcp_config.json")
        servers = cm.load_config()
        assert servers == {}

    def test_save_and_reload(self):
        cm = MCPConnectionManager.__new__(MCPConnectionManager)
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            cm._config_path = Path(f.name)
        os.unlink(f.name)  # let CM create it fresh

        servers = {"weather": {"type": "stdio", "command": "/usr/bin/mcp-weather"}}
        cm.save_config(servers)

        loaded = cm.load_config()
        assert loaded == servers
        os.unlink(str(cm._config_path))

    def test_add_server_config(self):
        cm = MCPConnectionManager.__new__(MCPConnectionManager)
        with tempfile.NamedTemporaryFile(suffix=".json", mode="w", delete=False) as f:
            json.dump({"mcpServers": {}}, f)
            cm._config_path = Path(f.name)

        cm.add_server_config("weather", {"type": "stdio", "command": "/usr/bin/mcp-weather"})
        loaded = cm.load_config()
        assert "weather" in loaded
        os.unlink(f.name)

    def test_remove_server_config(self):
        cm = MCPConnectionManager.__new__(MCPConnectionManager)
        with tempfile.NamedTemporaryFile(suffix=".json", mode="w", delete=False) as f:
            json.dump({
                "mcpServers": {"weather": {"type": "stdio", "command": "/usr/bin/mcp-weather"}}
            }, f)
            cm._config_path = Path(f.name)

        cm.remove_server_config("weather")
        loaded = cm.load_config()
        assert "weather" not in loaded
        os.unlink(f.name)

    def test_update_server_config(self):
        cm = MCPConnectionManager.__new__(MCPConnectionManager)
        with tempfile.NamedTemporaryFile(suffix=".json", mode="w", delete=False) as f:
            json.dump({
                "mcpServers": {"weather": {"type": "stdio", "command": "/usr/bin/old"}}
            }, f)
            cm._config_path = Path(f.name)

        updated = cm.update_server_config("weather", {"command": "/usr/bin/new"})
        assert updated["command"] == "/usr/bin/new"
        os.unlink(f.name)

    def test_update_nonexistent_raises(self):
        cm = MCPConnectionManager.__new__(MCPConnectionManager)
        with tempfile.NamedTemporaryFile(suffix=".json", mode="w", delete=False) as f:
            json.dump({"mcpServers": {}}, f)
            cm._config_path = Path(f.name)
        with pytest.raises(ValueError, match="not found"):
            cm.update_server_config("nonexistent", {"command": "/usr/bin/test"})
        os.unlink(f.name)


class TestEnvResolution:
    def test_resolve_env_with_redacted(self):
        cm = MCPConnectionManager.__new__(MCPConnectionManager)
        os.environ["MY_SECRET_KEY"] = "real_secret_value"
        resolved = cm._resolve_env({"MY_SECRET_KEY": "***REDACTED***", "NORMAL_VAR": "normal_value"})
        assert resolved["MY_SECRET_KEY"] == "real_secret_value"
        assert resolved["NORMAL_VAR"] == "normal_value"

    def test_resolve_headers_with_redacted(self):
        cm = MCPConnectionManager.__new__(MCPConnectionManager)
        os.environ["MCP_HEADER_AUTHORIZATION"] = "Bearer real_token"
        resolved = cm._resolve_headers({"Authorization": "***REDACTED***", "X-Custom": "value"})
        assert resolved["Authorization"] == "Bearer real_token"
        assert resolved["X-Custom"] == "value"


class TestConnectionManagerSingleton:
    def test_get_instance(self):
        MCPConnectionManager._instance = None
        cm = MCPConnectionManager.get_instance()
        assert cm is not None

    def test_reset_instance(self):
        MCPConnectionManager._instance = None
        MCPConnectionManager.get_instance()
        MCPConnectionManager.reset_instance()
        assert MCPConnectionManager._instance is None


class TestMcpConnection:
    def test_initial_state(self):
        from app.agent.mcp.connection_manager import MCPConnection
        conn = MCPConnection("test", {"type": "stdio", "command": "/usr/bin/test"})
        assert conn.status == "disconnected"
        assert conn.last_error is None
        assert conn.session is None
        assert not conn.is_connected

    def test_is_connected_check(self):
        from app.agent.mcp.connection_manager import MCPConnection
        conn = MCPConnection("test", {})
        conn.status = "connected"
        assert not conn.is_connected  # session still None
        conn.session = object()
        assert conn.is_connected