"""Notification DAO — CRUD for in-app notifications (站内信)."""

import uuid
from sqlalchemy import select, update, func
from sqlalchemy.ext.asyncio import async_sessionmaker, AsyncSession

from app.models.models import Notification


class NotificationDAO:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession], employee_id: int):
        self._sf = session_factory
        self._employee_id = employee_id

    async def create(self, title: str, content: str, source: str = "cron", cron_job_id: str | None = None, file_id: str | None = None) -> Notification:
        nid = str(uuid.uuid4())
        async with self._sf() as session:
            notif = Notification(
                id=nid,
                employee_id=self._employee_id,
                title=title,
                content=content,
                source=source,
                cron_job_id=cron_job_id,
                file_id=file_id,
            )
            session.add(notif)
            await session.commit()
            await session.refresh(notif)
            return notif

    async def list_notifications(self, limit: int = 50, offset: int = 0) -> list[Notification]:
        async with self._sf() as session:
            result = await session.execute(
                select(Notification)
                .where(Notification.employee_id == self._employee_id, Notification.is_deleted == 0)
                .order_by(Notification.created_at.desc())
                .limit(limit)
                .offset(offset)
            )
            return list(result.scalars().all())

    async def get_by_id(self, notif_id: str) -> Notification | None:
        async with self._sf() as session:
            result = await session.execute(
                select(Notification).where(
                    Notification.id == notif_id,
                    Notification.employee_id == self._employee_id,
                    Notification.is_deleted == 0,
                )
            )
            return result.scalar_one_or_none()

    async def unread_count(self) -> int:
        async with self._sf() as session:
            result = await session.execute(
                select(func.count(Notification.id))
                .where(Notification.employee_id == self._employee_id, Notification.is_read == 0, Notification.is_deleted == 0)
            )
            return result.scalar_one()

    async def mark_read(self, notif_id: str) -> Notification:
        async with self._sf() as session:
            notif = await session.execute(
                select(Notification).where(
                    Notification.id == notif_id,
                    Notification.employee_id == self._employee_id,
                )
            )
            notif_obj = notif.scalar_one_or_none()
            if not notif_obj:
                raise ValueError(f"Notification '{notif_id}' not found")
            notif_obj.is_read = 1
            await session.commit()
            await session.refresh(notif_obj)
            return notif_obj

    async def mark_all_read(self) -> int:
        async with self._sf() as session:
            result = await session.execute(
                update(Notification)
                .where(Notification.employee_id == self._employee_id, Notification.is_read == 0, Notification.is_deleted == 0)
                .values(is_read=1)
            )
            await session.commit()
            return result.rowcount

    async def soft_delete(self, notif_id: str) -> None:
        async with self._sf() as session:
            await session.execute(
                update(Notification).where(
                    Notification.id == notif_id,
                    Notification.employee_id == self._employee_id,
                ).values(is_deleted=1)
            )
            await session.commit()