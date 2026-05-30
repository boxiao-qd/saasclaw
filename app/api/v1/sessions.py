from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from app.dependencies import get_employee_id, get_db_session
from app.db.database import get_session_factory
from app.dao.session_dao import SessionDAO
from app.schemas.sessions import (
    CreateSessionRequest, CreateSessionResponse, SessionListResponse, SessionItem, SuccessResponse,
)
from app.schemas.common import PaginationMeta
from app.middleware.error_handler import AppError

router = APIRouter()


@router.get("/sessions", response_model=SessionListResponse)
async def list_sessions(
    page: int = 1,
    page_size: int = 20,
    employee_id: int = Depends(get_employee_id),
    db: AsyncSession = Depends(get_db_session),
):
    dao = SessionDAO(get_session_factory(), employee_id)
    items, total = await dao.list_sessions(page, page_size)
    return SessionListResponse(
        sessions=[SessionItem(session_id=s.id, title=s.title, model=s.model, created_at=s.created_at, updated_at=s.updated_at) for s in items],
        pagination=PaginationMeta(total=total, page=page, page_size=page_size),
    )


@router.post("/sessions", response_model=CreateSessionResponse)
async def create_session(
    req: CreateSessionRequest,
    employee_id: int = Depends(get_employee_id),
    db: AsyncSession = Depends(get_db_session),
):
    dao = SessionDAO(get_session_factory(), employee_id)
    session = await dao.create(title=req.title, model=req.model, system_prompt=req.system_prompt)
    return CreateSessionResponse(session_id=session.id, title=session.title, model=session.model or "", created_at=session.created_at)


@router.delete("/sessions/{session_id}", response_model=SuccessResponse)
async def delete_session(
    session_id: str,
    employee_id: int = Depends(get_employee_id),
    db: AsyncSession = Depends(get_db_session),
):
    dao = SessionDAO(get_session_factory(), employee_id)
    await dao.soft_delete(session_id)
    return SuccessResponse()