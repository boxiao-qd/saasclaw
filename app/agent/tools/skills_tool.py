"""skills tool — list, view, and manage skills (aligns with Hermes skills_list/skill_view/skill_manage)."""

import json

from app.db.database import get_session_factory
from app.dao.skill_dao import SkillDAO
from app.storage.sys_infra import list_system_skills, get_system_skill_md


TOOL_DEFS = [
    {
        "type": "function",
        "function": {
            "name": "skills_list",
            "description": (
                "List available skills (name + description). Use skill_view(name) to load full content. "
                "Skills are reusable instruction documents that give the agent specialized knowledge."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "scope": {
                        "type": "string",
                        "enum": ["all", "global", "personal"],
                        "default": "all",
                        "description": "Filter by scope: 'global' (shared), 'personal' (user-specific), or 'all'",
                    },
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "skill_view",
            "description": (
                "Load a skill's full content by name. Returns the skill's markdown content "
                "which can be applied as specialized instructions. Progressive disclosure: "
                "use skills_list first, then skill_view for detailed content."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {
                        "type": "string",
                        "description": "Skill name to load",
                    },
                },
                "required": ["name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "skill_manage",
            "description": (
                "Create, update, or delete a PERSONAL skill. Users can only manage their own personal skills — "
                "global/system skills are read-only and cannot be created, updated, or deleted by non-admin users. "
                "Skills store reusable instruction documents for specialized knowledge."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "enum": ["create", "update", "delete"],
                        "description": "Action to perform",
                    },
                    "name": {
                        "type": "string",
                        "description": "Skill name (1-64 chars, required for create; identifier for update/delete)",
                    },
                    "content_md": {
                        "type": "string",
                        "description": "Skill content in markdown format (required for create, optional for update)",
                    },
                    "is_global": {
                        "type": "boolean",
                        "default": False,
                        "description": "Whether this skill is shared globally. ALWAYS false for regular users — only admins can create global skills.",
                    },
                },
                "required": ["action", "name"],
            },
        },
    },
]


async def skills_list(args_str: str, employee_id: int) -> str:
    args = json.loads(args_str)
    scope = args.get("scope", "all")

    # System skills from container filesystem
    sys_skills = list_system_skills()  # [{name, description, is_global: True}]
    sys_names = {s["name"] for s in sys_skills}

    # User custom skills from DB (exclude names already covered by sys-infra)
    session_factory = get_session_factory()
    dao = SkillDAO(session_factory, employee_id)
    try:
        db_index = await dao.get_index()
    except Exception as e:
        return json.dumps({"error": f"Failed to list skills: {e}"}, ensure_ascii=False)

    user_skills = [s for s in db_index if s["name"] not in sys_names and not s["is_global"]]

    all_skills = sys_skills + user_skills

    if scope == "global":
        all_skills = [s for s in all_skills if s["is_global"]]
    elif scope == "personal":
        all_skills = [s for s in all_skills if not s["is_global"]]

    return json.dumps({
        "skills": [{"name": s["name"], "description": s["description"], "is_global": bool(s["is_global"])} for s in all_skills],
        "count": len(all_skills),
        "scope": scope,
        "hint": "Use skill_view(name) to load full content.",
    }, ensure_ascii=False)


async def skill_view(args_str: str, employee_id: int) -> str:
    args = json.loads(args_str)
    name = args.get("name", "")

    # Check sys-infra first (system skills take precedence)
    sys_md = get_system_skill_md(name)
    if sys_md is not None:
        return json.dumps({
            "name": name,
            "content_md": sys_md,
            "is_global": True,
        }, ensure_ascii=False)

    session_factory = get_session_factory()
    dao = SkillDAO(session_factory, employee_id)

    try:
        skill = await dao.get_by_name(name)
        if not skill:
            return json.dumps({"error": f"Skill '{name}' not found"}, ensure_ascii=False)

        # L2: load full SKILL.md via cache → object storage → content_md fallback
        content_md = await dao.get_skill_md(name)
        await dao.increment_usage(skill.id)

        return json.dumps({
            "name": skill.name,
            "content_md": content_md or "",
            "is_global": bool(skill.is_global),
        }, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"error": f"Failed to view skill: {e}"}, ensure_ascii=False)


async def skill_manage(args_str: str, employee_id: int) -> str:
    args = json.loads(args_str)
    action = args.get("action", "")
    name = args.get("name", "")
    content_md = args.get("content_md", "")
    is_global = args.get("is_global", False)

    session_factory = get_session_factory()
    dao = SkillDAO(session_factory, employee_id)

    try:
        if action == "create":
            if not content_md:
                return json.dumps({"error": "content_md is required for create"}, ensure_ascii=False)
            if is_global:
                return json.dumps({"error": "Non-admin users cannot create global skills. Users can only create personal skills (is_global=false)."}, ensure_ascii=False)
            skill = await dao.create(name=name, content_md=content_md, is_global=False)
            return json.dumps({
                "id": skill.id,
                "name": skill.name,
                "is_global": bool(skill.is_global),
                "created_at": skill.created_at,
                "message": f"Skill '{name}' created",
            }, ensure_ascii=False)

        elif action == "update":
            skill = await dao.get_by_name(name)
            if not skill:
                return json.dumps({"error": f"Skill '{name}' not found"}, ensure_ascii=False)
            update_data = {}
            if content_md:
                update_data["content_md"] = content_md
            if args.get("new_name"):
                update_data["name"] = args.get("new_name")
            updated = await dao.update(skill.id, **update_data)
            return json.dumps({
                "id": updated.id,
                "name": updated.name,
                "is_global": bool(updated.is_global),
                "message": f"Skill '{name}' updated",
            }, ensure_ascii=False)

        elif action == "delete":
            skill = await dao.get_by_name(name)
            if not skill:
                return json.dumps({"error": f"Skill '{name}' not found"}, ensure_ascii=False)
            await dao.soft_delete(skill.id)
            return json.dumps({
                "name": name,
                "message": f"Skill '{name}' deleted",
            }, ensure_ascii=False)

        else:
            return json.dumps({"error": f"Unknown action: {action}"}, ensure_ascii=False)

    except Exception as e:
        error_msg = str(e)
        if "BX_SKILL_1002" in error_msg:
            return json.dumps({"error": f"Skill name '{name}' already exists"}, ensure_ascii=False)
        if "BX_SKILL_1003" in error_msg:
            return json.dumps({"error": "Non-admin users cannot modify global skills"}, ensure_ascii=False)
        return json.dumps({"error": f"Skill management failed: {e}"}, ensure_ascii=False)