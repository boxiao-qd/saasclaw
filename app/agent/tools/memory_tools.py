"""memory tools — query, store, and delete memories via MemoryDAO."""

import json

from app.dao.memory_dao import MemoryDAO
from app.db.database import get_session_factory


TOOL_DEFS = [
    {
        "type": "function",
        "function": {
            "name": "memory_query",
            "description": "Query stored memories by key. Returns the value if found, or empty if not.",
            "parameters": {
                "type": "object",
                "properties": {
                    "key": {"type": "string", "description": "Memory key to look up"},
                },
                "required": ["key"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "memory_store",
            "description": "Store or update a memory entry. Key-value pairs are persisted to the database.",
            "parameters": {
                "type": "object",
                "properties": {
                    "key": {"type": "string", "description": "Memory key"},
                    "value": {"type": "string", "description": "Memory value to store"},
                    "source": {"type": "string", "description": "Source of the memory", "default": "agent"},
                },
                "required": ["key", "value"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "memory_delete",
            "description": "Delete a stored memory entry by key.",
            "parameters": {
                "type": "object",
                "properties": {
                    "key": {"type": "string", "description": "Memory key to delete"},
                },
                "required": ["key"],
            },
        },
    },
]


async def memory_query(args_str: str, employee_id: int) -> str:
    args = json.loads(args_str)
    key = args.get("key", "")

    session_factory = get_session_factory()
    dao = MemoryDAO(session_factory, employee_id)

    try:
        mem = await dao.get_by_key(key)
        if mem:
            return json.dumps({"key": key, "value": mem.value, "source": mem.source, "found": True}, ensure_ascii=False)
        return json.dumps({"key": key, "value": "", "found": False}, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"error": f"Memory query failed: {e}", "key": key}, ensure_ascii=False)


async def memory_store(args_str: str, employee_id: int) -> str:
    args = json.loads(args_str)
    key = args.get("key", "")
    value = args.get("value", "")
    source = args.get("source", "agent")

    session_factory = get_session_factory()
    dao = MemoryDAO(session_factory, employee_id)

    try:
        # Try update first, create if not exists
        updated = await dao.update(key=key, value=value, source=source)
        if updated:
            return json.dumps({"key": key, "value": value, "source": source, "stored": True, "updated": True}, ensure_ascii=False)
        # Create new
        await dao.create(key=key, value=value, source=source)
        return json.dumps({"key": key, "value": value, "source": source, "stored": True, "updated": False}, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"error": f"Memory store failed: {e}", "key": key}, ensure_ascii=False)


async def memory_delete(args_str: str, employee_id: int) -> str:
    args = json.loads(args_str)
    key = args.get("key", "")

    session_factory = get_session_factory()
    dao = MemoryDAO(session_factory, employee_id)

    try:
        deleted = await dao.soft_delete(key)
        return json.dumps({"key": key, "deleted": deleted, "found": deleted}, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"error": f"Memory delete failed: {e}", "key": key}, ensure_ascii=False)