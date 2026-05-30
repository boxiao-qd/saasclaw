"""
Celery tasks for the standalone scheduler — fully synchronous, no asyncio.

scan_due_jobs  — runs every 30s via Celery Beat, queries MySQL for due jobs
execute_cron_job — HTTP POST to super-agent internal API to execute one cron job
"""

import logging
import os
from datetime import datetime, timezone, timedelta

import httpx
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker

from celery_app import app as celery_app

log = logging.getLogger(__name__)

BEIJING_TZ = timezone(timedelta(hours=8))

DB_URL = os.getenv("DB_URL", "mysql+pymysql://root:root123@mysql:3306/super_agent?charset=utf8mb4")
SUPER_AGENT_URL = os.getenv("SUPER_AGENT_URL", "http://host.docker.internal:8000")
INTERNAL_API_TOKEN = os.getenv("INTERNAL_API_TOKEN", "")

_engine = None
_SessionFactory = None
_config_logged = False


def _init_engine():
    global _engine, _SessionFactory, _config_logged
    if _SessionFactory is None:
        log.info("Init DB engine: %s", DB_URL)
        log.info("Super-agent URL: %s", SUPER_AGENT_URL)
        log.info("Internal API token: %s", "SET" if INTERNAL_API_TOKEN else "NOT SET")
        _engine = create_engine(DB_URL, pool_size=5, max_overflow=10, pool_pre_ping=True)
        _SessionFactory = sessionmaker(_engine, class_=Session, expire_on_commit=False)
        _config_logged = True
    return _SessionFactory


def _api_headers():
    if INTERNAL_API_TOKEN:
        return {"X-Internal-Token": INTERNAL_API_TOKEN}
    return {}


@celery_app.task(name="celery_tasks.scan_due_jobs")
def scan_due_jobs():
    """Scan cron_jobs table for due jobs, mark as running, dispatch each to worker."""
    sf = _init_engine()

    try:
        with sf() as session:
            total = session.execute(text("SELECT COUNT(*) FROM cron_jobs")).scalar()
            active = session.execute(
                text("SELECT COUNT(*) FROM cron_jobs WHERE is_active=1 AND is_deleted=0")
            ).scalar()

            now_bj = datetime.now(BEIJING_TZ).strftime("%Y-%m-%dT%H:%M:%S")

            # Debug: show next_run_at vs Beijing now
            sample = session.execute(
                text(
                    "SELECT id, name, next_run_at "
                    "FROM cron_jobs WHERE is_active=1 AND is_deleted=0 AND is_running=0"
                )
            ).fetchall()
            for row in sample:
                log.info(
                    "Job check: id=%s name=%s next_run_at=%s now_bj=%s",
                    row[0], row[1], row[2], now_bj,
                )

            # next_run_at stored as ISO format Beijing time, compare with current Beijing time
            result = session.execute(
                text(
                    "SELECT id, employee_id, name, next_run_at FROM cron_jobs "
                    "WHERE is_active = 1 AND is_deleted = 0 AND is_running = 0 "
                    "AND STR_TO_DATE(next_run_at, '%Y-%m-%dT%H:%i:%s') <= STR_TO_DATE(:now_bj, '%Y-%m-%dT%H:%i:%s')"
                ),
                {"now_bj": now_bj},
            )
            due_jobs = result.fetchall()

        log.info(
            "Scan: total=%s active=%s due=%s",
            total,
            active,
            len(due_jobs),
        )

        if not due_jobs:
            return

        for job_id, employee_id, name, next_run in due_jobs:
            log.info(
                "Dispatching job: id=%s name=%s employee=%s next_run=%s",
                job_id, name, employee_id, next_run,
            )
            with sf() as session:
                session.execute(
                    text("UPDATE cron_jobs SET is_running = 1 WHERE id = :id"),
                    {"id": job_id},
                )
                session.commit()

            execute_cron_job.delay(job_id, employee_id)

    except Exception as e:
        log.error("scan_due_jobs failed: %s", e, exc_info=True)


@celery_app.task(
    name="celery_tasks.execute_cron_job",
    bind=True,
    max_retries=3,
    default_retry_delay=30,
)
def execute_cron_job(self, job_id: str, employee_id: int):
    """HTTP POST to super-agent internal API to execute one cron job."""
    url = f"{SUPER_AGENT_URL}/v1/internal/cron/execute"

    sf = _init_engine()

    def _unmark_running():
        with sf() as session:
            session.execute(
                text("UPDATE cron_jobs SET is_running = 0 WHERE id = :id"),
                {"id": job_id},
            )
            session.commit()

    log.info("POST %s?job_id=%s&employee_id=%s", url, job_id, employee_id)

    try:
        resp = httpx.post(
            url,
            params={"job_id": job_id, "employee_id": employee_id},
            headers=_api_headers(),
            timeout=600,
        )
        log.info(
            "Response: status=%s body=%s",
            resp.status_code,
            resp.text[:500],
        )
        resp.raise_for_status()
        result = resp.json()
        log.info(
            "Cron job %s success: status=%s run_id=%s",
            job_id,
            result.get("status"),
            result.get("run_id"),
        )
        _unmark_running()

    except httpx.HTTPStatusError as e:
        log.error(
            "HTTP %s for job %s: %s",
            e.response.status_code,
            job_id,
            e.response.text[:500],
        )
        _unmark_running()
        if e.response.status_code >= 500:
            raise self.retry(exc=e)

    except Exception as e:
        log.error("Failed to dispatch job %s: %s", job_id, e, exc_info=True)
        _unmark_running()
        raise self.retry(exc=e)