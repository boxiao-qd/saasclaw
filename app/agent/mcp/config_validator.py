"""MCP server configuration validation — stdio command whitelist, SSE URL format, naming rules."""

import logging
import os
import re

log = logging.getLogger(__name__)

# Allowed directories for stdio commands (configurable via env var)
_ALLOWED_DIR_ENV = "MCP_STDO_ALLOWED_DIRS"
_DEFAULT_ALLOWED_DIRS = ("/usr/bin", "/usr/local/bin", "/opt/homebrew/bin")

# Shell metacharacters forbidden in args
_SHELL_METACHAR_RE = re.compile(r"[;&|`$(){}!<>]")

# Slug pattern for server names
_NAME_SLUG_RE = re.compile(r"^^[a-z][a-z0-9_]{1,63}$")


def get_allowed_dirs() -> tuple[str, ...]:
    env_val = os.getenv(_ALLOWED_DIR_ENV, "")
    if env_val:
        return tuple(d.strip() for d in env_val.split(",") if d.strip())
    return _DEFAULT_ALLOWED_DIRS


def validate_server_name(name: str) -> list[str]:
    errors = []
    if not _NAME_SLUG_RE.match(name):
        errors.append(f"name must match slug pattern [a-z][a-z0-9_] (1-64 chars), got: '{name}'")
    return errors


def validate_stdio_command(command: str) -> list[str]:
    errors = []
    if not os.path.isabs(command):
        errors.append(f"stdio command must be an absolute path, got: '{command}'")
        return errors

    allowed_dirs = get_allowed_dirs()
    if not any(command.startswith(d) for d in allowed_dirs):
        errors.append(
            f"stdio command must reside under allowed directories ({', '.join(allowed_dirs)}), "
            f"got: '{command}'"
        )

    if not os.path.isfile(command):
        errors.append(f"stdio command path does not exist or is not a file: '{command}'")

    return errors


def validate_stdio_args(args: list[str]) -> list[str]:
    errors = []
    for i, arg in enumerate(args):
        if _SHELL_METACHAR_RE.search(arg):
            errors.append(f"args[{i}] contains shell metacharacters, forbidden: '{arg}'")
    return errors


def validate_sse_url(url: str) -> list[str]:
    errors = []
    if not url.startswith(("http://", "https://")):
        errors.append(f"sse url must start with http:// or https://, got: '{url}'")
    return errors


def validate_mcp_config(data: dict) -> list[str]:
    """Validate full MCP server config dict. Returns list of error strings."""
    errors = []

    name = data.get("name", "")
    errors.extend(validate_server_name(name))

    transport_type = data.get("transport_type", "")
    if transport_type not in ("stdio", "sse"):
        errors.append(f"transport_type must be 'stdio' or 'sse', got: '{transport_type}'")
        return errors

    if transport_type == "stdio":
        command = data.get("command", "")
        if not command:
            errors.append("stdio transport requires 'command' field")
        else:
            errors.extend(validate_stdio_command(command))

        args = data.get("args") or []
        if not isinstance(args, list):
            errors.append("'args' must be a list of strings")
        else:
            errors.extend(validate_stdio_args(args))

        env = data.get("env") or {}
        if not isinstance(env, dict):
            errors.append("'env' must be a dict of string values")
        else:
            for key, val in env.items():
                if not isinstance(val, str):
                    errors.append(f"env[{key}] value must be a string")

    elif transport_type == "sse":
        url = data.get("url", "")
        if not url:
            errors.append("sse transport requires 'url' field")
        else:
            errors.extend(validate_sse_url(url))

        headers = data.get("headers") or {}
        if not isinstance(headers, dict):
            errors.append("'headers' must be a dict of string values")

    return errors


def redact_sensitive_values(data: dict, sensitive_keys: set[str] | None = None) -> dict:
    """Replace sensitive values in env/headers with ***REDACTED***.

    Default sensitive keys: anything containing 'key', 'token', 'secret', 'password', 'auth', 'credential'.
    """
    if sensitive_keys is None:
        sensitive_keys = {"key", "token", "secret", "password", "auth", "credential"}

    result = dict(data)

    for field in ("env", "headers"):
        obj = result.get(field)
        if not isinstance(obj, dict):
            continue
        redacted = {}
        for k, v in obj.items():
            if any(s in k.lower() for s in sensitive_keys):
                redacted[k] = "***REDACTED***"
            else:
                redacted[k] = v
        result[field] = redacted

    return result