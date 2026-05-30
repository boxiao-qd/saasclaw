"""CronRun DAO — execution history for scheduled tasks."""

import uuid
from datetime import datetime
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, AsyncSession

from app.models.models import CronRun


class CronRunDAO:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession], employee_id: int):
        self._sf = session_factory
        self._employee_id = employee_id

    async def create(self, cron_job_id: str, session_id: str | None = None) -> CronRun:
        run_id = str(uuid.uuid4())
        now = datetime.utcnow().isoformat()
        async with self._sf() as session:
            run = CronRun(
                id=run_id,
                employee_id=self._employee_id,
                cron_job_id=cron_job_id,
                session_id=session_id,
                status="running",
                started_at=now,
            )
            session.add(run)
            await session.commit()
            await session.refresh(run)
            return run

    async def mark_success(self, run_id: str, result_summary: str | None = None, file_id: str | None = None) -> CronRun:
        now = datetime.utcnow().isoformat()
        async with self._sf() as session:
            result = await session.execute(
                select(CronRun).where(CronRun.id == run_id)
            )
            run = result.scalar_one_or_none()
            if not run:
                raise ValueError(f"CronRun '{run_id}' not found")
            run.status = "success"
            run.result_summary = result_summary
            run.finished_at = now
            if run.started_at:
                started = datetime.fromisoformat(run.started_at)
                run.duration_seconds = int((datetime.utcnow() - started).total_seconds())
            if file_id:
                run.file_id = file_id
            await session.commit()
            await session.refresh(run)
            return run

    async def mark_failed(self, run_id: str, error_message: str | None = None) -> CronRun:
        now = datetime.utcnow().isoformat()
        async with self._sf() as session:
            result = await session.execute(
                select(CronRun).where(CronRun.id == run_id)
            )
            run = result.scalar_one_or_none()
            if not run:
                raise ValueError(f"CronRun '{run_id}' not found")
            run.status = "failed"
            run.error_message = error_message
            run.finished_at = now
            if run.started_at:
                started = datetime.fromisoformat(run.started_at)
                run.duration_seconds = int((datetime.utcnow() - started).total_seconds())
            await session.commit()
            await session.refresh(run)
            return run

    async def list_runs(self, cron_job_id: str, limit: int = 20, offset: int = 0) -> list[CronRun]:
        async with self._sf() as session:
            result = await session.execute(
                select(CronRun)
                .where(CronRun.cron_job_id == cron_job_id)
                .order_by(CronRun.created_at.desc())
                .limit(limit)
                .offset(offset)
            )
            return list(result.scalars().all())

    async def get_by_id(self, run_id: str) -> CronRun | None:
        async with self._sf() as session:
            result = await session.execute(
                select(CronRun).where(CronRun.id == run_id)
            )
            return result.scalar_one_or_none()