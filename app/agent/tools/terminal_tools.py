"""terminal + process tools — execute shell commands and manage background processes."""

import asyncio
import json
import os
import re
import time
from pathlib import Path

from app.config import settings
from app.agent.tools.command_filter import filter_command

# Detect shell commands that create or write files under /tmp/ or /var/tmp/.
# minio_project.py creates its own /dev/shm scratchpad internally (not via terminal),
# so this pattern does NOT block legitimate internal usage.
_TMP_WRITE_RE = re.compile(
    r"""
    (?:
        \bmkdir\b[^|&;\n]*?/(?:tmp|var/tmp)/   # mkdir /tmp/... or mkdir -p /tmp/...
      | \btouch\b[^|&;\n]*?/(?:tmp|var/tmp)/   # touch /tmp/...
      | \bcp\b[^|&;\n]*?/(?:tmp|var/tmp)/      # cp ... /tmp/...
      | \bmv\b[^|&;\n]*?/(?:tmp|var/tmp)/      # mv ... /tmp/...
      | >[^>]?[^|&;\n]*?/(?:tmp|var/tmp)/      # > /tmp/... or >> /tmp/...
      | \btee\b[^|&;\n]*?/(?:tmp|var/tmp)/     # tee /tmp/...
    )
    """,
    re.VERBOSE | re.IGNORECASE,
)

_TMP_WRITE_DENIAL = (
    "Writing to /tmp/ or /var/tmp/ is FORBIDDEN. "
    "All project files must be stored in MinIO. "
    "Use: python3 ${SKILL_DIR}/scripts/minio_project.py write-file "
    '--prefix "$PROJECT_PREFIX" <rel_path> (with heredoc for large content). '
    "If MinIO is unreachable, report the error to the user and stop the task."
)


_PROJECT_ROOT   = str(Path(__file__).resolve().parents[3])
_UPLOAD_SCRIPT  = str(Path(__file__).resolve().parents[3] / "scripts" / "upload_artifact.py")
_WORKDIR_SCRIPT = str(Path(__file__).resolve().parents[3] / "scripts" / "workdir.py")


def _subprocess_env(employee_id: int) -> dict[str, str]:
    """Build subprocess environment: inherit os.environ + inject settings values.

    Pydantic Settings reads .env into the settings object but does NOT write
    back to os.environ. Scripts running as subprocesses need these values
    explicitly injected so they can reach MinIO, DB, etc.
    """
    env = dict(os.environ)
    overrides = {
        "OBJECT_STORAGE_ENDPOINT":   settings.object_storage_endpoint,
        "OBJECT_STORAGE_ACCESS_KEY": settings.object_storage_access_key,
        "OBJECT_STORAGE_SECRET_KEY": settings.object_storage_secret_key,
        "OBJECT_STORAGE_BUCKET":     settings.object_storage_bucket,
        "OBJECT_STORAGE_REGION":     settings.object_storage_region,
        "OBJECT_STORAGE_PREFIX":     settings.object_storage_prefix,
        "SA_EMPLOYEE_ID":            str(employee_id),
        "SA_PROJECT_ROOT":           _PROJECT_ROOT,
        "SA_UPLOAD_SCRIPT":          _UPLOAD_SCRIPT,
        "SA_WORKDIR_SCRIPT":         _WORKDIR_SCRIPT,
    }
    if settings.db_url:
        overrides["DB_URL"] = settings.db_url
    env.update({k: v for k, v in overrides.items() if v})
    return env


# ── Background process registry ──────────────────────────────────────────

_bg_processes: dict[str, dict] = {}  # session_id → {proc, cwd, started_at, name}


# ── terminal tool ──────────────────────────────────────────────────────────

TOOL_DEF = {
    "type": "function",
    "function": {
        "name": "terminal",
        "description": (
            "Execute a shell command on the server. Returns exit code, stdout, and stderr. "
            "Use `background=true` for long-running processes (servers, builds); use `process` tool "
            "to manage background sessions. Do NOT use terminal for reading/editing files — use "
            "file_read / file_write / patch instead. Prefer foreground for short commands. "
            "In SaaS mode, terminal is restricted to a whitelist of read-only, non-file-operation "
            "commands only. File-writing commands (rm, cp, mv, cat, tee, touch, mkdir, chmod, "
            "editors, output redirects > / >>) are blocked."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "command": {"type": "string", "description": "Shell command to execute"},
                "background": {"type": "boolean", "default": False, "description": "Run in background; returns a session_id for process tool"},
                "timeout": {"type": "integer", "minimum": 1, "description": "Max seconds to wait (foreground only, max 600)", "default": 180},
                "workdir": {"type": "string", "description": "Working directory (absolute path)"},
            },
            "required": ["command"],
        },
    },
}


async def execute(args_str: str, employee_id: int) -> str:
    args = json.loads(args_str)
    command = args.get("command", "")
    background = args.get("background", False)
    timeout = min(args.get("timeout", 180), 600)
    workdir = args.get("workdir") or os.path.realpath(os.getcwd())

    if not command:
        return json.dumps({"error": "No command provided"}, ensure_ascii=False)

    # Block any command that writes files to /tmp/ or /var/tmp/ — always, not just SaaS mode.
    if _TMP_WRITE_RE.search(command):
        return json.dumps({"error": _TMP_WRITE_DENIAL, "blocked": True}, ensure_ascii=False)

    # SaaS mode command filtering
    if settings.saas_mode:
        result = filter_command(command)
        if not result["allowed"]:
            return json.dumps({
                "error": f"SaaS mode: command blocked. {result['reason']}. The terminal is restricted to read-only, non-file-operation commands only.",
                "command": command[:200],
                "saas_mode": True,
            }, ensure_ascii=False)

    try:
        if background:
            proc = await asyncio.create_subprocess_shell(
                command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=workdir,
                env=_subprocess_env(employee_id),
            )
            session_id = f"bg-{int(time.time_ns())}"
            _bg_processes[session_id] = {
                "proc": proc,
                "cwd": workdir,
                "started_at": time.time(),
                "command": command[:200],
            }
            return json.dumps({
                "session_id": session_id,
                "status": "running",
                "command_preview": command[:200],
            }, ensure_ascii=False)

        # Foreground execution
        proc = await asyncio.create_subprocess_shell(
            command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=workdir,
            env=_subprocess_env(employee_id),
        )
        try:
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        except asyncio.TimeoutError:
            proc.kill()
            stdout, stderr = await proc.communicate()
            return json.dumps({
                "exit_code": -1,
                "stdout": stdout.decode("utf-8", errors="replace")[:50000],
                "stderr": (stderr.decode("utf-8", errors="replace") + "\n[Timeout: killed after {}s]").format(timeout),
                "timed_out": True,
            }, ensure_ascii=False)

        out = stdout.decode("utf-8", errors="replace")
        err = stderr.decode("utf-8", errors="replace")
        combined = out
        if err:
            combined += "\n--- stderr ---\n" + err

        return json.dumps({
            "exit_code": proc.returncode or 0,
            "stdout": combined[:50000],
            "language": "shell",
        }, ensure_ascii=False)

    except Exception as e:
        return json.dumps({"error": f"Terminal execution failed: {e}", "exit_code": -1}, ensure_ascii=False)


# ── process tool ───────────────────────────────────────────────────────────

PROCESS_TOOL_DEF = {
    "type": "function",
    "function": {
        "name": "process",
        "description": (
            "Manage background terminal processes. Actions: list (all sessions), "
            "poll (check if still running), log (read output), wait (block until done), "
            "kill (terminate process), close (cleanup session)."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["list", "poll", "log", "wait", "kill", "close"],
                    "description": "Action to perform on background process",
                },
                "session_id": {"type": "string", "description": "Background process session_id (required for all actions except list)"},
                "timeout": {"type": "integer", "minimum": 1, "description": "Max seconds to block for 'wait' action", "default": 30},
            },
            "required": ["action"],
        },
    },
}


async def process(args_str: str, employee_id: int) -> str:
    args = json.loads(args_str)
    action = args.get("action", "list")
    sid = args.get("session_id", "")
    timeout = min(args.get("timeout", 30), 120)

    if action == "list":
        result = []
        for key, entry in _bg_processes.items():
            proc = entry["proc"]
            running = proc.returncode is None
            result.append({
                "session_id": key,
                "command": entry["command"],
                "running": running,
                "started_at": entry["started_at"],
                "cwd": entry["cwd"],
            })
        return json.dumps({"processes": result, "count": len(result)}, ensure_ascii=False)

    entry = _bg_processes.get(sid)
    if not entry:
        return json.dumps({"error": f"Session '{sid}' not found"}, ensure_ascii=False)

    proc = entry["proc"]

    if action == "poll":
        running = proc.returncode is None
        return json.dumps({
            "session_id": sid,
            "running": running,
            "exit_code": proc.returncode,
        }, ensure_ascii=False)

    elif action == "log":
        # Read current stdout/stderr without consuming the pipe
        # For background processes, output is buffered; we read what's available
        stdout_data = b""
        stderr_data = b""
        if proc.stdout:
            try:
                while True:
                    chunk = await asyncio.wait_for(proc.stdout.read(4096), timeout=0.5)
                    if not chunk:
                        break
                    stdout_data += chunk
            except asyncio.TimeoutError:
                pass
        if proc.stderr:
            try:
                while True:
                    chunk = await asyncio.wait_for(proc.stderr.read(4096), timeout=0.5)
                    if not chunk:
                        break
                    stderr_data += chunk
            except asyncio.TimeoutError:
                pass

        out = stdout_data.decode("utf-8", errors="replace")
        err = stderr_data.decode("utf-8", errors="replace")
        combined = out
        if err:
            combined += "\n--- stderr ---\n" + err

        return json.dumps({
            "session_id": sid,
            "output": combined[:50000],
            "running": proc.returncode is None,
        }, ensure_ascii=False)

    elif action == "wait":
        try:
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
            out = stdout.decode("utf-8", errors="replace")
            err = stderr.decode("utf-8", errors="replace")
            combined = out
            if err:
                combined += "\n--- stderr ---\n" + err
            _bg_processes.pop(sid, None)
            return json.dumps({
                "session_id": sid,
                "exit_code": proc.returncode or 0,
                "output": combined[:50000],
            }, ensure_ascii=False)
        except asyncio.TimeoutError:
            return json.dumps({
                "session_id": sid,
                "running": True,
                "error": f"Process still running after {timeout}s",
            }, ensure_ascii=False)

    elif action == "kill":
        proc.kill()
        await proc.wait()
        _bg_processes.pop(sid, None)
        return json.dumps({
            "session_id": sid,
            "status": "killed",
            "exit_code": proc.returncode,
        }, ensure_ascii=False)

    elif action == "close":
        # If still running, kill first
        if proc.returncode is None:
            proc.kill()
            await proc.wait()
        _bg_processes.pop(sid, None)
        return json.dumps({
            "session_id": sid,
            "status": "closed",
        }, ensure_ascii=False)

    else:
        return json.dumps({"error": f"Unknown action: {action}"}, ensure_ascii=False)


# ── Multi-tool registration ──────────────────────────────────────────────

TOOL_DEFS = [TOOL_DEF, PROCESS_TOOL_DEF]