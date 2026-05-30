"""
Celery app for the cron scheduler (standalone, deployed independently from super-agent).

Architecture:
  celery-beat → scan_due_jobs (every 30s, queries MySQL, dispatches due jobs)
  celery-worker → execute_cron_job (HTTP POST to super-agent internal API)
"""

import os
import sys

# Ensure the scheduler directory is on Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from celery import Celery

REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379/0")

app = Celery(
    "super_agent_scheduler",
    broker=REDIS_URL,
    backend=REDIS_URL,
)

app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="Asia/Shanghai",
    enable_utc=True,
    task_track_started=True,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    broker_connection_retry_on_startup=True,
    beat_schedule={
        "scan-due-jobs": {
            "task": "celery_tasks.scan_due_jobs",
            "schedule": 30.0,
        },
    },
)

app.autodiscover_tasks(["celery_tasks"])