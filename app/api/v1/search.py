from fastapi import APIRouter, Depends, Query
from app.dependencies import get_employee_id
from app.db.elasticsearch import get_es_client
from app.dao.search_dao import SearchDAO
from app.schemas.search import SearchResponse

router = APIRouter()


@router.get("/search", response_model=SearchResponse)
async def search(
    q: str = Query(..., min_length=1),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    employee_id: int = Depends(get_employee_id),
):
    dao = SearchDAO(get_es_client(), employee_id)
    return await dao.search(query=q, page=page, page_size=page_size)