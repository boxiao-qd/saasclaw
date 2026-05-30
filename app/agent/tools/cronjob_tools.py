"""cronjob tool — Agent tool for managing cron jobs."""

import json

from app.db.database import get_session_factory
from app.dao.cron_dao import CronDAO

TOOL_DEFS = [
    {
        "type": "function",
        "function": {
            "name": "cronjob",
            "description": (
                "Manage scheduled (cron) tasks. Create, list, pause, resume, or remove jobs that "
                "run automatically on a cron schedule. Results are delivered as in-app notifications (站内信). "
                "Use 'create' to set up a recurring task, 'list' to view all jobs, and 'pause/resume/remove' to manage them."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "enum": ["create", "list", "pause", "resume", "remove", "update"],
                        "description": "Action to perform on cron jobs",
                    },
                    "name": {
                        "type": "string",
                        "description": "Job name (required for create; identifier for update/remove/pause/resume)",
                    },
                    "prompt": {
                        "type": "string",
                        "description": "The prompt/instruction the agent will execute when the cron job runs (required for create)",
                    },
                    "cron_expr": {
                        "type": "string",
                        "description": (
                            "Cron expression for scheduling. Format: 'min hour day month weekday'. "
                            "Examples: '0 9 * * *' (daily 9am), '*/30 * * * *' (every 30 min), "
                            "'0 9 * * 1-5' (9am weekdays)"
                        ),
                    },
                },
                "required": ["action"],
            },
        },
    },
]


async def cronjob(args_str: str, employee_id: int) -> str:
    args = json.loads(args_str)
    action = args.get("action", "")
    name = args.get("name", "")
    prompt = args.get("prompt", "")
    cron_expr = args.get("cron_expr", "")

    dao = CronDAO(get_session_factory(), employee_id)

    try:
        if action == "create":
            if not prompt:
                return json.dumps({"error": "prompt is required for create"}, ensure_ascii=False)
            if not cron_expr:
                return json.dumps({"error": "cron_expr is required for create"}, ensure_ascii=False)
            # Validate cron expression
            from croniter import croniter
            try:
                croniter(cron_expr)
            except ValueError as e:
                return json.dumps({"error": f"Invalid cron expression: {e}"}, ensure_ascii=False)

            job = await dao.create(name=name, prompt=prompt, cron_expr=cron_expr)
            return json.dumps({
                "id": job.id,
                "name": job.name,
                "cron_expr": job.cron_expr,
                "next_run_at": job.next_run_at,
                "message": f"Cron job '{job.name}' created. Results will be delivered as notifications (站内信).",
            }, ensure_ascii=False)

        elif action == "list":
            jobs = await dao.list_jobs()
            job_list = [
                {
                    "id": j.id,
                    "name": j.name,
                    "cron_expr": j.cron_expr,
                    "is_active": j.is_active,
                    "next_run_at": j.next_run_at,
                    "run_count": j.run_count,
                }
                for j in jobs
            ]
            return json.dumps({"jobs": job_list, "count": len(job_list)}, ensure_ascii=False)

        elif action == "pause":
            job = await dao.get_by_id(name) if name else None
            if not job:
                return json.dumps({"error": f"Job '{name}' not found"}, ensure_ascii=False)
            paused = await dao.pause(job.id)
            return json.dumps({"id": paused.id, "is_active": paused.is_active, "message": f"Job '{paused.name}' paused"}, ensure_ascii=False)

        elif action == "resume":
            job = await dao.get_by_id(name) if name else None
            if not job:
                return json.dumps({"error": f"Job '{name}' not found"}, ensure_ascii=False)
            resumed = await dao.resume(job.id)
            return json.dumps({"id": resumed.id, "is_active": resumed.is_active, "next_run_at": resumed.next_run_at, "message": f"Job '{resumed.name}' resumed"}, ensure_ascii=False)

        elif action == "remove":
            job = await dao.get_by_id(name) if name else None
            if not job:
                return json.dumps({"error": f"Job '{name}' not found"}, ensure_ascii=False)
            await dao.soft_delete(job.id)
            return json.dumps({"id": job.id, "message": f"Job '{job.name}' removed"}, ensure_ascii=False)

        elif action == "update":
            job = await dao.get_by_id(name) if name else None
            if not job:
                return json.dumps({"error": f"Job '{name}' not found"}, ensure_ascii=False)
            kwargs = {}
            if prompt:
                kwargs["prompt"] = prompt
            if cron_expr:
                from croniter import croniter
                try:
                    croniter(cron_expr)
                except ValueError as e:
                    return json.dumps({"error": f"Invalid cron expression: {e}"}, ensure_ascii=False)
                kwargs["cron_expr"] = cron_expr
            if args.get("new_name"):
                kwargs["name"] = args.get("new_name")
            if not kwargs:
                return json.dumps({"error": "No fields to update"}, ensure_ascii=False)
            updated = await dao.update(job.id, **kwargs)
            return json.dumps({"id": updated.id, "name": updated.name, "cron_expr": updated.cron_expr, "message": f"Job '{updated.name}' updated"}, ensure_ascii=False)

        else:
            return json.dumps({"error": f"Unknown action: {action}"}, ensure_ascii=False)

    except Exception as e:
        return json.dumps({"error": f"Cron job operation failed: {e}"}, ensure_ascii=False)