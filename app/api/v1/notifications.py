"""Notification REST API — 站内信 list/read/count/mark-read."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select

from app.db.database import get_session_factory
from app.dao.notification_dao import NotificationDAO
from app.models.models import ArtifactFile
from app.dependencies import get_employee_id

router = APIRouter(prefix="/notifications", tags=["notifications"])


_get_employee_id = get_employee_id


async def _lookup_file_name(sf, employee_id: int, file_id: str | None) -> str | None:
    if not file_id:
        return None
    async with sf() as session:
        result = await session.execute(
            select(ArtifactFile.file_name).where(
                ArtifactFile.id == file_id,
                ArtifactFile.employee_id == employee_id,
            )
        )
        row = result.first()
        return row[0] if row else None


@router.get("")
async def list_notifications(
    limit: int = 50,
    offset: int = 0,
    employee_id: int = Depends(_get_employee_id),
):
    """List notifications (站内信) for current user."""
    sf = get_session_factory()
    dao = NotificationDAO(sf, employee_id)
    notifs = await dao.list_notifications(limit=limit, offset=offset)
    unread = await dao.unread_count()

    items = []
    for n in notifs:
        file_name = await _lookup_file_name(sf, employee_id, n.file_id)
        items.append({
            "id": n.id,
            "title": n.title,
            "content": n.content,
            "source": n.source,
            "cron_job_id": n.cron_job_id,
            "file_id": n.file_id,
            "file_name": file_name,
            "is_read": n.is_read,
            "created_at": n.created_at,
        })

    return {
        "notifications": items,
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
    sf = get_session_factory()
    dao = NotificationDAO(sf, employee_id)
    notif = await dao.get_by_id(notif_id)
    if not notif:
        raise HTTPException(status_code=404, detail="Notification not found")
    file_name = await _lookup_file_name(sf, employee_id, notif.file_id)
    return {
        "id": notif.id,
        "title": notif.title,
        "content": notif.content,
        "source": notif.source,
        "cron_job_id": notif.cron_job_id,
        "file_id": notif.file_id,
        "file_name": file_name,
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
