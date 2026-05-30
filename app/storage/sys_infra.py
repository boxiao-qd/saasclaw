"""sys-infra reader — load system pre-built skills and subagents from the container filesystem.

System skills/subagents are baked into the image at build time under sys_infra_path:
  sys-infra/skills/{name}/SKILL.md
  sys-infra/subagents/{name}/AGENT.md

User custom skills/subagents remain in the database.
"""

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from app.config import settings

log = logging.getLogger(__name__)


def _infra_root() -> Path:
    return Path(settings.sys_infra_path)


def _read_meta(skill_dir: Path) -> dict:
    """Read _meta.json for a skill dir. Returns empty dict on any failure."""
    meta_file = skill_dir / "_meta.json"
    if not meta_file.exists():
        return {}
    try:
        return json.loads(meta_file.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _extract_skill_description(content: str) -> str:
    """Extract a one-line description from SKILL.md content.

    Tries in order:
    1. YAML frontmatter 'description' field (supports block scalars like '>').
    2. First non-empty, non-separator, non-heading body line.
    """
    lines = content.splitlines()
    body_start = 0
    if lines and lines[0].strip() == "---":
        end = 1
        while end < len(lines) and lines[end].strip() != "---":
            end += 1
        fm_text = "\n".join(lines[1:end])
        body_start = end + 1
        try:
            import yaml
            fm = yaml.safe_load(fm_text) or {}
            desc = fm.get("description", "")
            if isinstance(desc, str):
                desc = " ".join(desc.split())  # normalize whitespace from block scalars
                if desc:
                    return desc[:500]
        except Exception:
            pass
    for line in lines[body_start:]:
        stripped = line.strip().lstrip("#").strip()
        if stripped and stripped != "---":
            return stripped[:500]
    return ""


def _enumerate_sys_infra_skills() -> list[dict]:
    """Enumerate sys-infra skills and return SkillItem-compatible dicts. Synchronous."""
    skills_dir = _infra_root() / "skills"
    if not skills_dir.is_dir():
        return []

    result = []
    for skill_dir in sorted(skills_dir.iterdir()):
        if not skill_dir.is_dir():
            continue
        skill_md = skill_dir / "SKILL.md"
        if not skill_md.exists():
            continue

        meta = _read_meta(skill_dir)
        dir_name = skill_dir.name
        display_name = meta.get("displayName") or dir_name
        slug = meta.get("slug") or dir_name
        latest = meta.get("latest") or {}
        version = latest.get("version")
        published_ms = latest.get("publishedAt")

        try:
            content = skill_md.read_text(encoding="utf-8")
            first = _extract_skill_description(content) or display_name
        except Exception:
            content = ""
            first = display_name

        if published_ms:
            try:
                created_at = datetime.fromtimestamp(published_ms / 1000, tz=timezone.utc).isoformat()
            except Exception:
                created_at = datetime.now(tz=timezone.utc).isoformat()
        else:
            created_at = datetime.now(tz=timezone.utc).isoformat()

        result.append({
            "id": f"sys_infra::{dir_name}",
            "name": display_name,
            "content_md": content,
            "header_description": first,
            "object_key": None,
            "is_global": True,
            "usage_count": 0,
            "created_at": created_at,
            "source": "sys_infra",
            "version": version,
            "slug": slug,
        })

    return result


async def list_sys_infra_skill_items(include_content: bool = False) -> list[dict]:
    """Async wrapper: enumerate sys-infra skills off the event loop thread.

    Args:
        include_content: If False (default), clears content_md to save bandwidth.
    """
    import asyncio
    items = await asyncio.to_thread(_enumerate_sys_infra_skills)
    if not include_content:
        for item in items:
            item["content_md"] = ""
    return items


def list_system_skills() -> list[dict]:
    """Return compact index of all system skills (name + first-line description).

    Returns list of {"name": str, "description": str, "is_global": True}.
    Returns empty list if sys-infra directory does not exist.
    """
    skills_dir = _infra_root() / "skills"
    if not skills_dir.is_dir():
        return []

    result = []
    for skill_dir in sorted(skills_dir.iterdir()):
        if not skill_dir.is_dir():
            continue
        skill_md = skill_dir / "SKILL.md"
        if not skill_md.exists():
            continue
        name = skill_dir.name
        try:
            first_line = _extract_skill_description(skill_md.read_text(encoding="utf-8")) or name
        except Exception:
            first_line = name
        result.append({"name": name, "description": first_line, "is_global": True})

    return result


def get_system_skill_md(name: str) -> str | None:
    """Read SKILL.md content for a system skill by directory name. Returns None if not found."""
    skill_dir = _infra_root() / "skills" / name
    skill_md = skill_dir / "SKILL.md"
    if not skill_md.exists():
        return None
    try:
        content = skill_md.read_text(encoding="utf-8")
        return content.replace("${SKILL_DIR}", str(skill_dir))
    except Exception as e:
        log.warning("Failed to read system skill '%s': %s", name, e)
        return None


def get_system_skill_name_map() -> dict[str, str]:
    """Return {display_name: dir_name} for all sys-infra skills. Synchronous."""
    skills_dir = _infra_root() / "skills"
    if not skills_dir.is_dir():
        return {}
    result = {}
    for skill_dir in sorted(skills_dir.iterdir()):
        if not skill_dir.is_dir():
            continue
        if not (skill_dir / "SKILL.md").exists():
            continue
        meta = _read_meta(skill_dir)
        dir_name = skill_dir.name
        display_name = meta.get("displayName") or dir_name
        result[display_name] = dir_name
    return result


def get_system_skill_md_by_display_name(display_name: str) -> str | None:
    """Read SKILL.md content for a system skill by display name (case-insensitive).

    Looks up the directory name via _meta.json displayName, then reads SKILL.md.
    Returns None if not found.
    """
    name_map = get_system_skill_name_map()
    display_lower = display_name.lower()
    for dname, dir_name in name_map.items():
        if dname.lower() == display_lower:
            return get_system_skill_md(dir_name)
    return None


def list_system_subagents() -> list[dict]:
    """Return compact index of all system subagents (name + first-line description).

    Returns list of {"name": str, "description": str, "is_global": True}.
    Returns empty list if sys-infra directory does not exist.
    """
    subagents_dir = _infra_root() / "subagents"
    if not subagents_dir.is_dir():
        return []

    result = []
    for sa_dir in sorted(subagents_dir.iterdir()):
        if not sa_dir.is_dir():
            continue
        agent_md = sa_dir / "AGENT.md"
        if not agent_md.exists():
            continue
        name = sa_dir.name
        try:
            first_line = agent_md.read_text(encoding="utf-8").strip().splitlines()[0].lstrip("# ").strip()
        except Exception:
            first_line = name
        result.append({"name": name, "description": first_line, "is_global": True})

    return result


def get_system_subagent_md(name: str) -> str | None:
    """Read AGENT.md content for a system subagent. Returns None if not found."""
    agent_md = _infra_root() / "subagents" / name / "AGENT.md"
    if not agent_md.exists():
        return None
    try:
        return agent_md.read_text(encoding="utf-8")
    except Exception as e:
        log.warning("Failed to read system subagent '%s': %s", name, e)
        return None
