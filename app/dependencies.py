from fastapi import Request, HTTPException, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.database import get_session_factory


async def get_employee_id(request: Request) -> int:
    employee_id = getattr(request.state, "employee_id", 0)
    if not employee_id:
        raise HTTPException(status_code=401, detail="Authentication required")
    return employee_id


async def get_db_session(
    employee_id: int = Depends(get_employee_id),
) -> AsyncSession:
    session_factory = get_session_factory()
    session = session_factory()
    try:
        yield session
    finally:
        await session.close()
