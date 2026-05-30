"""Cron REST API — CRUD for scheduled tasks + execution history."""

from fastapi import APIRouter, Depends, HTTPException, Query

from app.db.database import get_session_factory
from app.dao.cron_dao import CronDAO
from app.dao.cron_run_dao import CronRunDAO
from app.dependencies import get_employee_id
from app.schemas.cron import (
    CreateCronJobRequest, UpdateCronJobRequest,
    CronJobItem, CronJobListResponse,
    CronRunItem, CronRunListResponse,
)

router = APIRouter(prefix="/cron", tags=["cron"])


@router.post("/jobs", response_model=CronJobItem)
async def create_job(
    req: CreateCronJobRequest,
    employee_id: int = Depends(get_employee_id),
):
    try:
        from croniter import croniter
        croniter(req.cron_expr)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"Invalid cron expression: {e}")

    dao = CronDAO(get_session_factory(), employee_id)
    job = await dao.create(name=req.name, prompt=req.prompt, cron_expr=req.cron_expr)
    return _job_to_item(job)


@router.get("/jobs", response_model=CronJobListResponse)
async def list_jobs(employee_id: int = Depends(get_employee_id)):
    dao = CronDAO(get_session_factory(), employee_id)
    jobs = await dao.list_jobs()
    return CronJobListResponse(jobs=[_job_to_item(j) for j in jobs], count=len(jobs))


@router.get("/jobs/{job_id}", response_model=CronJobItem)
async def get_job(job_id: str, employee_id: int = Depends(get_employee_id)):
    dao = CronDAO(get_session_factory(), employee_id)
    job = await dao.get_by_id(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return _job_to_item(job)


@router.put("/jobs/{job_id}", response_model=CronJobItem)
async def update_job(
    job_id: str,
    req: UpdateCronJobRequest,
    employee_id: int = Depends(get_employee_id),
):
    dao = CronDAO(get_session_factory(), employee_id)
    kwargs = {}
    if req.name is not None:
        kwargs["name"] = req.name
    if req.prompt is not None:
        kwargs["prompt"] = req.prompt
    if req.cron_expr is not None:
        try:
            from croniter import croniter
            croniter(req.cron_expr)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=f"Invalid cron expression: {e}")
        kwargs["cron_expr"] = req.cron_expr
    if not kwargs:
        raise HTTPException(status_code=400, detail="No fields to update")
    job = await dao.update(job_id, **kwargs)
    return _job_to_item(job)


@router.post("/jobs/{job_id}/pause")
async def pause_job(job_id: str, employee_id: int = Depends(get_employee_id)):
    dao = CronDAO(get_session_factory(), employee_id)
    job = await dao.pause(job_id)
    return {"id": job.id, "is_active": job.is_active}


@router.post("/jobs/{job_id}/resume")
async def resume_job(job_id: str, employee_id: int = Depends(get_employee_id)):
    dao = CronDAO(get_session_factory(), employee_id)
    job = await dao.resume(job_id)
    return {"id": job.id, "is_active": job.is_active, "next_run_at": job.next_run_at}


@router.delete("/jobs/{job_id}")
async def delete_job(job_id: str, employee_id: int = Depends(get_employee_id)):
    dao = CronDAO(get_session_factory(), employee_id)
    await dao.soft_delete(job_id)
    return {"id": job_id, "deleted": True}


@router.get("/jobs/{job_id}/runs", response_model=CronRunListResponse)
async def list_runs(
    job_id: str,
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    employee_id: int = Depends(get_employee_id),
):
    # Verify job ownership first
    dao = CronDAO(get_session_factory(), employee_id)
    job = await dao.get_by_id(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    run_dao = CronRunDAO(get_session_factory(), employee_id)
    runs = await run_dao.list_runs(job_id, limit=limit, offset=offset)
    return CronRunListResponse(
        runs=[CronRunItem(
            id=r.id,
            cron_job_id=r.cron_job_id,
            session_id=r.session_id,
            status=r.status,
            result_summary=r.result_summary,
            error_message=r.error_message,
            started_at=r.started_at,
            finished_at=r.finished_at,
            duration_seconds=r.duration_seconds,
            file_id=r.file_id,
            created_at=r.created_at,
        ) for r in runs],
        count=len(runs),
    )


def _job_to_item(job) -> CronJobItem:
    return CronJobItem(
        id=job.id,
        name=job.name,
        prompt=job.prompt,
        cron_expr=job.cron_expr,
        is_active=job.is_active,
        is_running=job.is_running,
        last_run_at=job.last_run_at,
        next_run_at=job.next_run_at,
        last_error=job.last_error,
        run_count=job.run_count,
        consecutive_errors=job.consecutive_errors,
    )