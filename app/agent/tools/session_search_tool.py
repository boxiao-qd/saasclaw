"""session_search tool — search past conversation sessions and messages."""

import json
from pathlib import Path

from app.db.database import get_session_factory
from app.models.models import Session as SessionModel, Message as MessageModel
from sqlalchemy import select, func, or_, and_
from sqlalchemy.orm import selectinload


TOOL_DEF = {
    "type": "function",
    "function": {
        "name": "session_search",
        "description": (
            "Search past conversation sessions and messages. Three modes: "
            "DISCOVERY (pass query to search sessions by title or message content), "
            "SCROLL (pass session_id to read messages from a specific session), "
            "BROWSE (omit all args to list recent sessions). "
            "Helps recall information from previous conversations."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Search query for finding sessions by title or message content",
                },
                "session_id": {
                    "type": "string",
                    "description": "Session ID to read messages from (scroll mode)",
                },
                "limit": {
                    "type": "integer",
                    "description": "Max sessions to return (discovery/browse mode, max 10)",
                    "default": 3,
                },
                "message_limit": {
                    "type": "integer",
                    "description": "Max messages to return per session (scroll mode)",
                    "default": 10,
                },
                "sort": {
                    "type": "string",
                    "enum": ["newest", "oldest"],
                    "default": "newest",
                    "description": "Sort order for session listing",
                },
            },
        },
    },
}


async def execute(args_str: str, employee_id: int) -> str:
    args = json.loads(args_str)
    query = args.get("query", "")
    session_id = args.get("session_id", "")
    limit = min(args.get("limit", 3), 10)
    message_limit = min(args.get("message_limit", 10), 50)
    sort = args.get("sort", "newest")

    session_factory = get_session_factory()

    async with session_factory() as db:
        # ── SCROLL mode: read messages from a specific session ──────────
        if session_id:
            stmt = (
                select(MessageModel)
                .where(
                    MessageModel.session_id == session_id,
                    MessageModel.employee_id == employee_id,
                )
                .order_by(MessageModel.created_at)
                .limit(message_limit)
            )
            result = await db.execute(stmt)
            messages = result.scalars().all()

            # Also get session info
            sess_stmt = select(SessionModel).where(
                SessionModel.id == session_id,
                SessionModel.employee_id == employee_id,
                SessionModel.is_deleted == 0,
            )
            sess_result = await db.execute(sess_stmt)
            session = sess_result.scalar_one_or_none()

            if not session:
                return json.dumps({
                    "error": f"Session '{session_id}' not found",
                }, ensure_ascii=False)

            msg_list = []
            for m in messages:
                entry = {
                    "role": m.role,
                    "content": (m.content or "")[:500],
                    "created_at": m.created_at,
                }
                if m.tool_calls:
                    entry["tool_calls"] = True  # brief indicator
                if m.tool_name:
                    entry["tool_name"] = m.tool_name
                msg_list.append(entry)

            return json.dumps({
                "mode": "scroll",
                "session_id": session_id,
                "title": session.title,
                "messages": msg_list,
                "total_messages": len(msg_list),
            }, ensure_ascii=False)

        # ── DISCOVERY mode: search sessions by query ────────────────────
        if query:
            stmt = (
                select(SessionModel)
                .where(
                    SessionModel.employee_id == employee_id,
                    SessionModel.is_deleted == 0,
                    or_(
                        SessionModel.title.ilike(f"%{query}%"),
                        SessionModel.system_prompt.ilike(f"%{query}%"),
                    ),
                )
            )
            if sort == "newest":
                stmt = stmt.order_by(SessionModel.updated_at.desc())
            else:
                stmt = stmt.order_by(SessionModel.updated_at.asc())
            stmt = stmt.limit(limit)

            result = await db.execute(stmt)
            sessions = result.scalars().all()

            # Also search message content
            msg_stmt = (
                select(MessageModel.session_id)
                .where(
                    MessageModel.employee_id == employee_id,
                    MessageModel.content.ilike(f"%{query}%"),
                )
                .distinct()
                .limit(limit)
            )
            msg_result = await db.execute(msg_stmt)
            session_ids_from_msgs = [row[0] for row in msg_result.all()]

            # Combine: get sessions from message matches
            combined_ids = {s.id for s in sessions}
            combined_ids.update(session_ids_from_msgs)

            if combined_ids:
                combined_stmt = (
                    select(SessionModel)
                    .where(
                        SessionModel.id.in_(combined_ids),
                        SessionModel.employee_id == employee_id,
                        SessionModel.is_deleted == 0,
                    )
                )
                if sort == "newest":
                    combined_stmt = combined_stmt.order_by(SessionModel.updated_at.desc())
                else:
                    combined_stmt = combined_stmt.order_by(SessionModel.updated_at.asc())
                combined_stmt = combined_stmt.limit(limit)
                combined_result = await db.execute(combined_stmt)
                sessions = combined_result.scalars().all()

            session_list = []
            for s in sessions:
                # Get snippet from first message
                snippet_stmt = (
                    select(MessageModel.content)
                    .where(
                        MessageModel.session_id == s.id,
                        MessageModel.role == "user",
                    )
                    .order_by(MessageModel.created_at)
                    .limit(1)
                )
                snippet_result = await db.execute(snippet_stmt)
                snippet_row = snippet_result.first()
                snippet = (snippet_row[0] or "")[:200] if snippet_row else ""

                session_list.append({
                    "session_id": s.id,
                    "title": s.title or "(untitled)",
                    "snippet": snippet,
                    "model": s.model,
                    "updated_at": s.updated_at,
                })

            return json.dumps({
                "mode": "discovery",
                "query": query,
                "sessions": session_list,
                "total": len(session_list),
            }, ensure_ascii=False)

        # ── BROWSE mode: list recent sessions ───────────────────────────
        stmt = (
            select(SessionModel)
            .where(
                SessionModel.employee_id == employee_id,
                SessionModel.is_deleted == 0,
                SessionModel.parent_session_id.is_(None),  # Only top-level sessions
            )
        )
        if sort == "newest":
            stmt = stmt.order_by(SessionModel.updated_at.desc())
        else:
            stmt = stmt.order_by(SessionModel.updated_at.asc())
        stmt = stmt.limit(limit)

        result = await db.execute(stmt)
        sessions = result.scalars().all()

        session_list = []
        for s in sessions:
            # Count messages
            count_stmt = select(func.count()).where(MessageModel.session_id == s.id)
            count_result = await db.execute(count_stmt)
            msg_count = count_result.scalar() or 0

            session_list.append({
                "session_id": s.id,
                "title": s.title or "(untitled)",
                "model": s.model,
                "message_count": msg_count,
                "updated_at": s.updated_at,
            })

        return json.dumps({
            "mode": "browse",
            "sessions": session_list,
            "total": len(session_list),
        }, ensure_ascii=False)