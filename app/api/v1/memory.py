from fastapi import APIRouter, Depends
from app.dependencies import get_employee_id, get_db_session
from app.db.database import get_session_factory
from app.dao.memory_dao import MemoryDAO
from app.schemas.memory import MemoryListResponse, MemoryItem, CreateMemoryRequest, CreateMemoryResponse
from app.schemas.common import SuccessResponse

router = APIRouter()


@router.get("/memory", response_model=MemoryListResponse)
async def list_memory(
    employee_id: int = Depends(get_employee_id),
):
    dao = MemoryDAO(get_session_factory(), employee_id)
    items = await dao.list_memories()
    return MemoryListResponse(memories=[
        MemoryItem(id=m.id, key=m.key, value=m.value, source=m.source, created_at=m.created_at)
        for m in items
    ])


@router.post("/memory", response_model=CreateMemoryResponse)
async def create_memory(
    req: CreateMemoryRequest,
    employee_id: int = Depends(get_employee_id),
):
    dao = MemoryDAO(get_session_factory(), employee_id)
    memory = await dao.create(key=req.key, value=req.value)
    return CreateMemoryResponse(id=memory.id, key=memory.key, created_at=memory.created_at)