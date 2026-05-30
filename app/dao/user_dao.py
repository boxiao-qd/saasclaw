from __future__ import annotations

import uuid
from sqlalchemy import select, func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import async_sessionmaker, AsyncSession
from app.models.user import User


class UserDAO:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]):
        self._session_factory = session_factory

    def _session(self) -> AsyncSession:
        return self._session_factory()

    async def create(self, username: str, hashed_password: str) -> User | None:
        """Return the created User, or None if username already exists (race condition)."""
        session = self._session()
        try:
            max_id = await session.scalar(select(func.max(User.employee_id))) or 0
            obj = User(
                id=str(uuid.uuid4()),
                employee_id=max_id + 1,
                username=username,
                hashed_password=hashed_password,
            )
            session.add(obj)
            await session.commit()
            await session.refresh(obj)
            return obj
        except IntegrityError:
            await session.rollback()
            return None
        finally:
            await session.close()

    async def get_by_username(self, username: str) -> User | None:
        session = self._session()
        try:
            return await session.scalar(
                select(User).where(User.username == username)
            )
        finally:
            await session.close()
