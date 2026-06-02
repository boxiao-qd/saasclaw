"""CronJob DAO — CRUD for scheduled tasks with error backoff and concurrency control. All times are Beijing time (UTC+8)."""

import uuid
from datetime import datetime, timezone, timedelta
from sqlalchemy import select, update, func
from sqlalchemy.ext.asyncio import async_sessionmaker, AsyncSession

from app.models.models import CronJob

BEIJING_TZ = timezone(timedelta(hours=8))
ERROR_BACKOFF_SECONDS = [30, 60, 300, 900, 3600]


def _now() -> datetime:
    return datetime.now(BEIJING_TZ)


class CronDAO:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession], employee_id: int):
        self._sf = session_factory
        self._employee_id = employee_id

    async def create(self, name: str | None, prompt: str, cron_expr: str) -> CronJob:
        job_id = str(uuid.uuid4())
        effective_name = name or f"cron-{job_id[:8]}"

        from croniter import croniter
        now = _now()
        next_run = croniter(cron_expr, now).get_next(datetime)

        # Validate minimum frequency (at least 5 minutes between runs)
        prev_run = croniter(cron_expr, now).get_prev(datetime)
        diff_seconds = (next_run - prev_run).total_seconds()
        if abs(diff_seconds) < 300:
            raise ValueError("Cron expression too frequent — minimum interval is 5 minutes")

        # Enforce per-user job count cap (max 20 active jobs)
        async with self._sf() as session:
            # Reject duplicate names
            if name:
                existing = await session.execute(
                    select(CronJob.id).where(
                        CronJob.employee_id == self._employee_id,
                        CronJob.name == name,
                        CronJob.is_deleted == 0,
                    )
                )
                if existing.scalar_one_or_none():
                    raise ValueError(f"Cron job name '{name}' already exists")
            count_result = await session.execute(
                select(func.count(CronJob.id)).where(
                    CronJob.employee_id == self._employee_id,
                    CronJob.is_active == 1,
                    CronJob.is_deleted == 0,
                )
            )
            active_count = count_result.scalar_one()
            if active_count >= 20:
                raise ValueError("Maximum active cron jobs reached (20 per user)")

            job = CronJob(
                id=job_id,
                employee_id=self._employee_id,
                name=effective_name,
                prompt=prompt,
                cron_expr=cron_expr,
                next_run_at=next_run.isoformat(),
            )
            session.add(job)
            await session.commit()
            await session.refresh(job)
            return job

    async def get_by_id(self, job_id: str) -> CronJob | None:
        async with self._sf() as session:
            result = await session.execute(
                select(CronJob).where(
                    CronJob.id == job_id,
                    CronJob.employee_id == self._employee_id,
                    CronJob.is_deleted == 0,
                )
            )
            return result.scalar_one_or_none()

    async def get_by_name(self, name: str) -> CronJob | None:
        async with self._sf() as session:
            result = await session.execute(
                select(CronJob).where(
                    CronJob.name == name,
                    CronJob.employee_id == self._employee_id,
                    CronJob.is_deleted == 0,
                )
            )
            return result.scalar_one_or_none()

    async def list_jobs(self) -> list[CronJob]:
        async with self._sf() as session:
            result = await session.execute(
                select(CronJob)
                .where(CronJob.employee_id == self._employee_id, CronJob.is_deleted == 0)
                .order_by(CronJob.created_at.desc())
            )
            return list(result.scalars().all())

    async def get_active(self, limit: int | None = None) -> list[CronJob]:
        """Get active cron jobs for the user (used by context loader)."""
        stmt = (
            select(CronJob)
            .where(
                CronJob.employee_id == self._employee_id,
                CronJob.is_active == 1,
                CronJob.is_deleted == 0,
            )
            .order_by(CronJob.next_run_at.asc())
        )
        if limit is not None:
            stmt = stmt.limit(limit)
        async with self._sf() as session:
            result = await session.execute(stmt)
            return list(result.scalars().all())

    async def update(self, job_id: str, **kwargs) -> CronJob:
        async with self._sf() as session:
            result = await session.execute(
                select(CronJob).where(
                    CronJob.id == job_id,
                    CronJob.employee_id == self._employee_id,
                    CronJob.is_deleted == 0,
                )
            )
            job_obj = result.scalar_one_or_none()
            if not job_obj:
                raise ValueError(f"CronJob '{job_id}' not found")
            # Reject duplicate names when renaming
            if "name" in kwargs and kwargs["name"] != job_obj.name:
                existing = await session.execute(
                    select(CronJob.id).where(
                        CronJob.employee_id == self._employee_id,
                        CronJob.name == kwargs["name"],
                        CronJob.is_deleted == 0,
                        CronJob.id != job_id,
                    )
                )
                if existing.scalar_one_or_none():
                    raise ValueError(f"Cron job name '{kwargs['name']}' already exists")
            for key, value in kwargs.items():
                setattr(job_obj, key, value)
            # If cron_expr changed, recalculate next_run_at
            if "cron_expr" in kwargs and job_obj.is_active:
                from croniter import croniter
                next_run = croniter(kwargs["cron_expr"], _now()).get_next(datetime)
                job_obj.next_run_at = next_run.isoformat()
            await session.commit()
            await session.refresh(job_obj)
            return job_obj

    async def pause(self, job_id: str) -> CronJob:
        return await self.update(job_id, is_active=0)

    async def resume(self, job_id: str) -> CronJob:
        from croniter import croniter
        job = await self.get_by_id(job_id)
        if not job:
            raise ValueError(f"CronJob '{job_id}' not found")
        next_run = croniter(job.cron_expr, _now()).get_next(datetime)
        return await self.update(job_id, is_active=1, next_run_at=next_run.isoformat())

    async def soft_delete(self, job_id: str) -> None:
        async with self._sf() as session:
            await session.execute(
                update(CronJob).where(
                    CronJob.id == job_id,
                    CronJob.employee_id == self._employee_id,
                ).values(is_deleted=1)
            )
            await session.commit()

    async def get_due_jobs(self) -> list[CronJob]:
        """Get all active, not-running jobs whose next_run_at <= now, across all users."""
        now_iso = _now().isoformat()
        async with self._sf() as session:
            result = await session.execute(
                select(CronJob)
                .where(
                    CronJob.is_active == 1,
                    CronJob.is_deleted == 0,
                    CronJob.is_running == 0,
                    CronJob.next_run_at <= now_iso,
                )
            )
            return list(result.scalars().all())

    async def mark_running(self, job_id: str) -> None:
        """Mark job as currently running to prevent duplicate execution."""
        async with self._sf() as session:
            await session.execute(
                update(CronJob).where(CronJob.id == job_id).values(is_running=1)
            )
            await session.commit()

    async def mark_run(self, job_id: str, success: bool, error: str | None = None) -> CronJob:
        from croniter import croniter
        now = _now()

        # Get current job to determine next_run and consecutive_errors
        async with self._sf() as session:
            result = await session.execute(
                select(CronJob).where(CronJob.id == job_id)
            )
            job = result.scalar_one_or_none()
            if not job:
                raise ValueError(f"CronJob '{job_id}' not found")

            normal_next_run = croniter(job.cron_expr, now).get_next(datetime)

            if success:
                consecutive_errors = 0
                next_run_at = normal_next_run.isoformat()
            else:
                consecutive_errors = job.consecutive_errors + 1
                # Apply backoff
                backoff_idx = min(consecutive_errors - 1, len(ERROR_BACKOFF_SECONDS) - 1)
                backoff = ERROR_BACKOFF_SECONDS[backoff_idx]
                backoff_next = now + timedelta(seconds=backoff)
                next_run_at = max(normal_next_run, backoff_next).isoformat()

            await session.execute(
                update(CronJob).where(CronJob.id == job_id).values(
                    is_running=0,
                    last_run_at=now.isoformat(),
                    next_run_at=next_run_at,
                    last_error=error,
                    run_count=job.run_count + 1,
                    consecutive_errors=consecutive_errors,
                )
            )
            await session.commit()

        # Return updated job
        return await self.get_by_id(job_id) if self._employee_id != 0 else None