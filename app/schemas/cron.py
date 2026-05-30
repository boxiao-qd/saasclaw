"""Pydantic schemas for cron job CRUD and execution history."""

from pydantic import BaseModel, Field
from typing import Optional


class CreateCronJobRequest(BaseModel):
    name: Optional[str] = Field(None, max_length=128)
    prompt: str = Field(..., min_length=1)
    cron_expr: str = Field(..., min_length=1, max_length=128)


class UpdateCronJobRequest(BaseModel):
    name: Optional[str] = Field(None, max_length=128)
    prompt: Optional[str] = Field(None, min_length=1)
    cron_expr: Optional[str] = Field(None, min_length=1, max_length=128)


class CronJobItem(BaseModel):
    id: str
    name: Optional[str] = None
    prompt: str
    cron_expr: str
    is_active: int
    is_running: int = 0
    last_run_at: Optional[str] = None
    next_run_at: Optional[str] = None
    last_error: Optional[str] = None
    run_count: int = 0
    consecutive_errors: int = 0


class CronJobListResponse(BaseModel):
    jobs: list[CronJobItem]
    count: int


class CronRunItem(BaseModel):
    id: str
    cron_job_id: str
    session_id: Optional[str] = None
    status: str
    result_summary: Optional[str] = None
    error_message: Optional[str] = None
    started_at: Optional[str] = None
    finished_at: Optional[str] = None
    duration_seconds: Optional[int] = None
    file_id: Optional[str] = None
    created_at: str


class CronRunListResponse(BaseModel):
    runs: list[CronRunItem]
    count: int