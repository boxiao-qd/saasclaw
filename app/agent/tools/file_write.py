"""file_write tool — write content to file with path enforcement."""

import json
import os
from pathlib import Path

from app.agent.tools.saas_path_guard import _saas_write_allowed, SAAS_WRITE_DENIED_MSG

# Derived from this file's location: app/agent/tools/ → 3 levels up → project root.
_PROJECT_ROOT = Path(__file__).resolve().parents[3]
_TMP_DOC_DIR  = _PROJECT_ROOT / "tmp-doc"

_TMP_PREFIXES = ("/tmp/", "/var/tmp/", "/dev/shm/")


def _validate_write_path(path: str) -> Path:
    real = os.path.realpath(path)
    return Path(real)


def _check_write_allowed(path: str) -> str | None:
    """Return an error message if the path is not an allowed write destination, else None."""
    real = Path(os.path.realpath(path))

    # 1. Always block /tmp/ family.
    if any(str(real).startswith(p) for p in _TMP_PREFIXES):
        return (
            f"Writing to '{path}' is FORBIDDEN. "
            "Use the work directory under tmp-doc/ instead. "
            "Run: python3 <SKILL_DIR>/scripts/minio_project.py create-workdir "
            "to get $WORK_DIR, then write to $WORK_DIR/<rel_path>."
        )

    # 2. When SA_PROJECT_ROOT is injected (always true in agent context), enforce
    #    that writes go to {project_root}/tmp-doc/ or {project_root}/user-config/.
    #    This catches agents inventing arbitrary paths like /app/dataflow_usr/ppt_outputs/.
    project_root = os.environ.get("SA_PROJECT_ROOT")
    if project_root:
        pr = Path(project_root).resolve()
        allowed_roots = [pr / "tmp-doc", pr / "user-config"]
        # Also allow the saas_user_config_dir if configured differently
        try:
            from app.config import settings
            if settings.saas_user_config_dir:
                allowed_roots.append(Path(settings.saas_user_config_dir).resolve())
        except Exception:
            pass

        if not any(_is_under(real, root) for root in allowed_roots):
            return (
                f"Writing to '{path}' is FORBIDDEN. "
                "Skill/subagent output files MUST go inside the task work directory "
                "(tmp-doc/{{employee_id}}_{{uuid}}/) or user-config/. "
                "Call minio_project.py create-workdir to get $WORK_DIR first, "
                "then use file_write with path=\"$WORK_DIR/<rel_path>\"."
            )

    return None


def _is_under(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
        return True
    except ValueError:
        return False


TOOL_DEF = {
    "type": "function",
    "function": {
        "name": "file_write",
        "description": (
            "Write content to a file inside the task work directory ($WORK_DIR) or user-config/. "
            "Always use the absolute path returned by minio_project.py create-workdir. "
            "Writing to /tmp/ or arbitrary paths outside tmp-doc/ is blocked."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Absolute file path inside $WORK_DIR or user-config/"},
                "content": {"type": "string", "description": "Content to write"},
            },
            "required": ["path", "content"],
        },
    },
}


async def execute(args_str: str, employee_id: int) -> str:
    args = json.loads(args_str)
    path = args.get("path", "")
    content = args.get("content", "")

    # Enforce allowed write locations.
    err = _check_write_allowed(path)
    if err:
        return json.dumps({"error": err, "tool_name": "file_write"}, ensure_ascii=False)

    # SaaS path whitelist check
    if not _saas_write_allowed(path):
        return json.dumps({
            "error": SAAS_WRITE_DENIED_MSG.format(path=path),
            "tool_name": "file_write",
            "saas_mode": True,
        }, ensure_ascii=False)

    resolved = _validate_write_path(path)

    # Auto-create parent directories
    if not resolved.exists():
        resolved.parent.mkdir(parents=True, exist_ok=True)

    try:
        with open(resolved, "w", encoding="utf-8") as f:
            f.write(content)
    except PermissionError:
        return json.dumps({"error": f"Permission denied: {path}"}, ensure_ascii=False)

    return json.dumps({
        "path": str(resolved),
        "bytes_written": len(content.encode("utf-8")),
        "status": "written",
    }, ensure_ascii=False)