from abc import ABC
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from elasticsearch import AsyncElasticsearch
from app.models.base import GLOBAL_EMPLOYEE_ID


class BaseDAO(ABC):
    """All DAOs inherit from this. SQLAlchemy ORM filter injection for employee_id.

    - SELECT: always apply Model.employee_id == employee_id filter
    - INSERT: auto-fill employee_id field
    - UPDATE/DELETE: scoped by employee_id filter, no unconditional ops
    - Shared queries (skills/subagents): WHERE employee_id=? OR employee_id=0 (global)
    """

    def __init__(self, session_factory: async_sessionmaker[AsyncSession], employee_id: int):
        self._session_factory = session_factory
        self._employee_id = employee_id

    @property
    def employee_id(self) -> int:
        return self._employee_id

    def _filter_by_user(self, model):
        return model.employee_id == self._employee_id

    def _filter_user_or_global(self, model):
        from sqlalchemy import or_
        return or_(model.employee_id == self._employee_id, model.employee_id == GLOBAL_EMPLOYEE_ID)

    def _session(self) -> AsyncSession:
        return self._session_factory()


class BaseESDAO(ABC):
    """ES DAO base class. All queries must include employee_id term filter."""

    def __init__(self, es_client: AsyncElasticsearch, employee_id: int):
        self._es_client = es_client
        self._employee_id = employee_id

    def _user_filter(self) -> dict:
        return {"term": {"employee_id": self._employee_id}}