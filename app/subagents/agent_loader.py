"""SubagentLoader — load built-in subagents from sys-infra and merge with DB subagents.

Resolution priority: sys-infra (built-in) > database (user custom). On name collision,
built-in wins. All built-in agents are managed purely in memory.
"""

from __future__ import annotations

import logging
from pathlib import Path

from app.config import settings
from app.subagents.agent_definition import (
    AgentDefinition,
    AgentSource,
    PermissionMode,
)

log = logging.getLogger(__name__)


class SubagentLoader:
    """Singleton. Pure in-memory subagent registry manager."""

    _instance: SubagentLoader | None = None
    _registry: dict[str, AgentDefinition]
    _loaded: bool

    def __init__(self):
        self._registry = {}
        self._loaded = False

    @classmethod
    def get_instance(cls) -> SubagentLoader:
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    async def initialize(self) -> None:
        if self._loaded:
            return
        builtin = self._load_builtin_agents()
        db_agents = await self._load_db_agents()
        self._registry = self._merge(builtin, db_agents)
        self._loaded = True
        log.info("SubagentLoader initialized: %d builtin + %d DB → %d total",
                 len(builtin), len(db_agents), len(self._registry))

    async def get_agent(self, name: str) -> AgentDefinition | None:
        await self.initialize()
        if name in self._registry:
            return self._registry[name]
        # Case-insensitive fallback — LLMs often miscase agent_type
        name_lower = name.lower()
        for key, agent_def in self._registry.items():
            if key.lower() == name_lower:
                return agent_def
        return None

    async def list_agents(self) -> list[AgentDefinition]:
        await self.initialize()
        return list(self._registry.values())

    async def refresh(self) -> None:
        self._loaded = False
        await self.initialize()

    # ── private ──────────────────────────────────────────────

    def _load_builtin_agents(self) -> list[AgentDefinition]:
        subagents_dir = Path(settings.sys_infra_path) / "subagents"
        if not subagents_dir.is_dir():
            return []

        result: list[AgentDefinition] = []
        for sa_dir in sorted(subagents_dir.iterdir()):
            if not sa_dir.is_dir():
                continue
            agent_md = sa_dir / "AGENT.md"
            if not agent_md.exists():
                continue
            agent_def = parse_agent_from_markdown(agent_md, sa_dir.name)
            if agent_def is None:
                log.warning("Failed to parse builtin agent from %s", agent_md)
                continue
            result.append(agent_def)
        return result

    async def _load_db_agents(self) -> list[AgentDefinition]:
        try:
            from app.dao.subagent_dao import SubagentDAO
            from app.db.database import get_session_factory

            dao = SubagentDAO(get_session_factory(), 0)
            db_subagents = await dao.list_subagents()
        except Exception as e:
            log.warning("Failed to load DB subagents: %s", e)
            return []

        result: list[AgentDefinition] = []
        import json as _json
        for sa in db_subagents:
            tools_raw = None
            try:
                tools_raw = _json.loads(sa.tools) if sa.tools else None
            except Exception:
                pass
            constraints_raw = None
            try:
                constraints_raw = _json.loads(sa.constraints) if sa.constraints else None
            except Exception:
                pass

            result.append(AgentDefinition(
                agent_type=sa.name,
                when_to_use=sa.header_description or sa.name,
                source=AgentSource.DATABASE,
                system_prompt=sa.definition_md or "",
                tools=tools_raw,
                disallowed_tools=constraints_raw,
            ))
        return result

    def _merge(
        self,
        builtin: list[AgentDefinition],
        db: list[AgentDefinition],
    ) -> dict[str, AgentDefinition]:
        merged: dict[str, AgentDefinition] = {}
        for agent in db:
            merged[agent.agent_type] = agent
        for agent in builtin:
            merged[agent.agent_type] = agent  # builtin overrides DB
        return merged


def parse_agent_from_markdown(file_path: Path, dir_name: str = "") -> AgentDefinition | None:
    """Parse an AGENT.md file into an AgentDefinition.

    Returns None if required fields are missing or the file is not a valid agent.
    """
    try:
        raw = file_path.read_text(encoding="utf-8")
    except Exception as e:
        log.warning("Failed to read AGENT.md %s: %s", file_path, e)
        return None

    # Split frontmatter and body
    lines = raw.splitlines()
    if not lines or lines[0].strip() != "---":
        return None

    end = 1
    while end < len(lines) and lines[end].strip() != "---":
        end += 1

    fm_text = "\n".join(lines[1:end])
    body = "\n".join(lines[end + 1:]).strip()

    try:
        import yaml
        fm = yaml.safe_load(fm_text) or {}
    except Exception:
        log.warning("Failed to parse YAML frontmatter in %s", file_path)
        return None

    agent_type = fm.get("name")
    if not agent_type or not isinstance(agent_type, str):
        return None

    when_to_use = fm.get("description", "")
    if not when_to_use or not isinstance(when_to_use, str):
        return None
    when_to_use = " ".join(when_to_use.replace("\\n", "\n").split())

    # Parse tools
    tools = _parse_string_list(fm.get("tools"))

    # Parse disallowedTools
    disallowed = _parse_string_list(fm.get("disallowedTools"))

    # Parse model
    model_raw = fm.get("model")
    model: str | None = None
    if isinstance(model_raw, str) and model_raw.strip():
        model = model_raw.strip()
        if model.lower() == "inherit":
            model = "inherit"

    # Parse permissionMode
    permission_mode = None
    pm_raw = fm.get("permissionMode")
    if isinstance(pm_raw, str) and pm_raw.strip():
        try:
            permission_mode = PermissionMode(pm_raw.strip())
        except ValueError:
            pass

    # Parse maxTurns
    max_turns = 10
    mt_raw = fm.get("maxTurns")
    if isinstance(mt_raw, int) and mt_raw > 0:
        max_turns = mt_raw

    # Parse color
    color = fm.get("color")
    if not isinstance(color, str):
        color = None

    # Parse skills
    skills = _parse_string_list(fm.get("skills"))

    # Parse background
    background = fm.get("background")
    if not isinstance(background, bool):
        background = False


    # Resolve ${AGENT_DIR} in body — replace with the directory containing AGENT.md
    resource_dir = str(file_path.parent.resolve())
    body = body.replace("${AGENT_DIR}", resource_dir)

    # Resolve ${SKILL_DIR} — same-named skill directory under sys-infra/skills/
    # Convention: sys-infra/subagents/<name>/AGENT.md → sys-infra/skills/<name>/
    from app.config import settings as _cfg
    from pathlib import Path as _Path
    _skill_dir = _Path(_cfg.sys_infra_path) / "skills" / (dir_name or file_path.parent.name)
    if _skill_dir.is_dir():
        body = body.replace("${SKILL_DIR}", str(_skill_dir.resolve()))

    return AgentDefinition(
        agent_type=agent_type,
        when_to_use=when_to_use,
        source=AgentSource.BUILTIN,
        system_prompt=body,
        tools=tools,
        disallowed_tools=disallowed,
        max_turns=max_turns,
        model=model,
        permission_mode=permission_mode,
        skills=skills,
        color=color,
        background=background,
        filename=dir_name or file_path.parent.name,
        resource_dir=resource_dir,
    )


def _parse_string_list(value: object) -> list[str] | None:
    """Normalize YAML list or comma-separated string to list[str]."""
    if value is None:
        return None
    if isinstance(value, list):
        return [str(v) for v in value]
    if isinstance(value, str):
        items = [v.strip() for v in value.split(",") if v.strip()]
        return items if items else None
    return None