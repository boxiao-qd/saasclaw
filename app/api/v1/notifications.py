"""Notification REST API — 站内信 list/read/count/mark-read."""

from fastapi import APIRouter, Depends, HTTPException

from app.db.database import get_session_factory
from app.dao.notification_dao import NotificationDAO
from app.dependencies import get_employee_id

router = APIRouter(prefix="/notifications", tags=["notifications"])


_get_employee_id = get_employee_id


@router.get("")
async def list_notifications(
    limit: int = 50,
    offset: int = 0,
    employee_id: int = Depends(_get_employee_id),
):
    """List notifications (站内信) for current user."""
    dao = NotificationDAO(get_session_factory(), employee_id)
    notifs = await dao.list_notifications(limit=limit, offset=offset)
    unread = await dao.unread_count()
    return {
        "notifications": [
            {
                "id": n.id,
                "title": n.title,
                "content": n.content,
                "source": n.source,
                "cron_job_id": n.cron_job_id,
                "is_read": n.is_read,
                "created_at": n.created_at,
            }
            for n in notifs
        ],
        "count": len(notifs),
        "unread_count": unread,
    }


@router.get("/unread-count")
async def unread_count(employee_id: int = Depends(_get_employee_id)):
    """Get unread notification count (for badge dot)."""
    dao = NotificationDAO(get_session_factory(), employee_id)
    count = await dao.unread_count()
    return {"unread_count": count}


@router.get("/{notif_id}")
async def get_notification(notif_id: str, employee_id: int = Depends(_get_employee_id)):
    """Get a single notification detail."""
    dao = NotificationDAO(get_session_factory(), employee_id)
    notif = await dao.get_by_id(notif_id)
    if not notif:
        raise HTTPException(status_code=404, detail="Notification not found")
    return {
        "id": notif.id,
        "title": notif.title,
        "content": notif.content,
        "source": notif.source,
        "cron_job_id": notif.cron_job_id,
        "is_read": notif.is_read,
        "created_at": notif.created_at,
    }


@router.post("/{notif_id}/read")
async def mark_read(notif_id: str, employee_id: int = Depends(_get_employee_id)):
    """Mark a notification as read."""
    dao = NotificationDAO(get_session_factory(), employee_id)
    notif = await dao.mark_read(notif_id)
    return {"id": notif.id, "is_read": notif.is_read}


@router.post("/mark-all-read")
async def mark_all_read(employee_id: int = Depends(_get_employee_id)):
    """Mark all notifications as read."""
    dao = NotificationDAO(get_session_factory(), employee_id)
    count = await dao.mark_all_read()
    return {"marked_count": count}


@router.delete("/{notif_id}")
async def delete_notification(notif_id: str, employee_id: int = Depends(_get_employee_id)):
    """Delete a notification."""
    dao = NotificationDAO(get_session_factory(), employee_id)
    await dao.soft_delete(notif_id)
    return {"id": notif_id, "deleted": True}