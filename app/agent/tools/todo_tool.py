"""todo tool -- task planning and tracking for multi-step work."""

import json
from app.dao.todo_dao import TodoDAO
from app.db.database import get_session_factory

VALID_STATUSES = ("pending", "in_progress", "completed", "cancelled")


def _to_dict(todo) -> dict:
    return {
        "id": todo.id,
        "content": todo.title,
        "status": todo.status,
        "priority": todo.priority,
        "description": todo.description,
    }


def _summary(items: list[dict]) -> dict:
    counts = {s: 0 for s in VALID_STATUSES}
    for item in items:
        counts[item["status"]] = counts.get(item["status"], 0) + 1
    return {"total": len(items), **counts}


TOOL_DEF = {
    "type": "function",
    "function": {
        "name": "todo",
        "description": (
            "Plan and track tasks with a todo list. Use for complex tasks with 3+ steps. "
            "Only ONE item should be 'in_progress' at a time -- mark items 'completed' immediately "
            "when done. Returns the full current list on every call. "
            "Use merge=true to update existing items by id or add new ones; merge=false to replace the entire list."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "todos": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "id": {"type": "string", "description": "Unique identifier for this item"},
                            "content": {"type": "string", "description": "Task description"},
                            "status": {
                                "type": "string",
                                "enum": ["pending", "in_progress", "completed", "cancelled"],
                                "description": "Current status of this item",
                            },
                        },
                        "required": ["id", "content", "status"],
                    },
                    "description": "Todo items with id, content, and status",
                },
                "merge": {
                    "type": "boolean",
                    "default": False,
                    "description": "true=update existing items by id, add new ones; false=replace entire list",
                },
            },
        },
    },
}


async def execute(args_str: str, employee_id: int) -> str:
    args = json.loads(args_str)
    todos_input = args.get("todos", [])
    merge = args.get("merge", False)

    session_factory = get_session_factory()
    dao = TodoDAO(session_factory, employee_id)

    if not todos_input:
        current_todos = await dao.list_todos()
        items = [_to_dict(t) for t in current_todos]
        return json.dumps({
            "todos": items,
            "summary": _summary(items),
        }, ensure_ascii=False)

    if merge:
        existing_todos = await dao.list_todos()
        existing_map = {t.id: t for t in existing_todos}

        for item in todos_input:
            id_ = item.get("id", "")
            content = item.get("content")
            status = item.get("status")

            if id_ in existing_map:
                updates = {}
                if content is not None:
                    updates["title"] = content
                if status is not None:
                    if status in VALID_STATUSES:
                        updates["status"] = status
                if updates:
                    await dao.update(id_, **updates)
            else:
                title = content or "(no description)"
                await dao.create(title=title, priority=0)
    else:
        # merge=false: replace entire list, preserving IDs from input
        existing_todos = await dao.list_todos()
        for t in existing_todos:
            await dao.soft_delete(t.id)

        for item in todos_input:
            id_ = item.get("id", "")
            content = item.get("content", "(no description)")
            status = item.get("status", "pending")
            if status not in VALID_STATUSES:
                status = "pending"
            await dao.create(title=content, priority=0)

    current_todos = await dao.list_todos()
    items = [_to_dict(t) for t in current_todos]
    return json.dumps({
        "todos": items,
        "summary": _summary(items),
    }, ensure_ascii=False)