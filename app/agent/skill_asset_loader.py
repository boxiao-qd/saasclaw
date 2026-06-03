"""Skill/Subagent L3 asset loader — fetch scripts/references/assets into /tmp per session."""

from __future__ import annotations

import logging
import shutil
from pathlib import Path

log = logging.getLogger(__name__)

_TMP_BASE = Path("/tmp/bx-skill-assets")


def _session_dir(session_id: str) -> Path:
    return _TMP_BASE / session_id


def cleanup_session_assets(session_id: str) -> None:
    """Remove all L3 cached assets for a session. Call on session end."""
    d = _session_dir(session_id)
    if d.exists():
        shutil.rmtree(d, ignore_errors=True)
        log.debug("Cleaned up L3 assets for session %s", session_id[:8])


async def skill_has_scripts(employee_id: int, skill_name: str) -> bool:
    """Check if a skill has a scripts/ directory (indicating file-output capability).

    Returns True if the skill has at least one file under scripts/ in object storage.
    """
    from app.dao.skill_dao import SkillDAO
    from app.storage.object_storage import create_object_storage
    from app.db.database import get_session_factory

    session_factory = get_session_factory()
    dao = SkillDAO(session_factory, employee_id)
    obj = await dao.get_by_name(skill_name)
    if not obj or not obj.object_key:
        return False

    try:
        storage = create_object_storage()
        files = await storage.get_directory(employee_id, f"{obj.object_key}/scripts")
        return bool(files)
    except Exception:
        return False


async def fetch_skill_script(
    session_id: str,
    employee_id: int,
    skill_name: str,
    filename: str,
) -> Path | None:
    """Fetch a script file from skill/scripts/ to /tmp cache. Returns local path or None."""
    return await _fetch_asset(session_id, employee_id, "skills", skill_name, f"scripts/{filename}")


async def fetch_skill_reference(
    session_id: str,
    employee_id: int,
    skill_name: str,
    filename: str,
) -> str | None:
    """Fetch a reference file from skill/references/ and return text content."""
    path = await _fetch_asset(session_id, employee_id, "skills", skill_name, f"references/{filename}")
    if path and path.exists():
        return path.read_text(encoding="utf-8", errors="replace")
    return None


async def fetch_subagent_script(
    session_id: str,
    employee_id: int,
    subagent_name: str,
    filename: str,
) -> Path | None:
    return await _fetch_asset(session_id, employee_id, "subagents", subagent_name, f"tools/{filename}")


async def _fetch_asset(
    session_id: str,
    employee_id: int,
    kind: str,         # "skills" | "subagents"
    name: str,
    sub_path: str,
) -> Path | None:
    from app.dao.skill_dao import SkillDAO
    from app.dao.subagent_dao import SubagentDAO
    from app.storage.object_storage import create_object_storage
    from app.db.database import get_session_factory

    local_path = _session_dir(session_id) / kind / name / sub_path
    if local_path.exists():
        return local_path

    session_factory = get_session_factory()

    # Resolve object_key
    if kind == "skills":
        dao = SkillDAO(session_factory, employee_id)
        obj = await dao.get_by_name(name)
    else:
        dao = SubagentDAO(session_factory, employee_id)
        obj = await dao.get_by_name(name)

    if not obj or not obj.object_key:
        return None

    object_key = f"{obj.object_key}/{sub_path}"
    try:
        storage = create_object_storage()
        data = await storage.get(employee_id, object_key)
        if data is None:
            return None
        local_path.parent.mkdir(parents=True, exist_ok=True)
        local_path.write_bytes(data)
        return local_path
    except Exception as e:
        log.warning("L3 asset fetch failed (%s/%s/%s): %s", kind, name, sub_path, e)
        return None
