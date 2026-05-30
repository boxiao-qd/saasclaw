"""Unit tests for UserDAO — create/get_by_username and session lifecycle."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from sqlalchemy.exc import IntegrityError

from app.dao.user_dao import UserDAO
from app.models.user import User


def _factory(session: AsyncMock) -> MagicMock:
    session.add = MagicMock()  # add() is sync in SQLAlchemy
    f = MagicMock()
    f.return_value = session
    return f


class TestUserDAOCreate:
    @pytest.mark.asyncio
    async def test_returns_user_on_success(self):
        session = AsyncMock()

        async def fake_refresh(obj):
            obj.id = "some-uuid"

        session.refresh.side_effect = fake_refresh

        dao = UserDAO(_factory(session))
        result = await dao.create("alice", "hashed")

        assert result is not None
        assert result.username == "alice"
        session.add.assert_called_once()
        session.commit.assert_awaited_once()
        session.close.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_returns_none_on_integrity_error(self):
        session = AsyncMock()
        session.commit.side_effect = IntegrityError("stmt", {}, Exception("UNIQUE"))

        dao = UserDAO(_factory(session))
        result = await dao.create("alice", "hashed")

        assert result is None
        session.rollback.assert_awaited_once()
        session.close.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_closes_session_on_unexpected_error(self):
        session = AsyncMock()
        session.commit.side_effect = RuntimeError("unexpected DB error")

        dao = UserDAO(_factory(session))
        with pytest.raises(RuntimeError):
            await dao.create("alice", "hashed")

        session.close.assert_awaited_once()


class TestUserDAOGetByUsername:
    @pytest.mark.asyncio
    async def test_returns_user_when_found(self):
        mock_user = User(id="1", username="alice", hashed_password="hash")
        session = AsyncMock()
        session.scalar.return_value = mock_user

        dao = UserDAO(_factory(session))
        result = await dao.get_by_username("alice")

        assert result is mock_user
        session.close.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_returns_none_when_not_found(self):
        session = AsyncMock()
        session.scalar.return_value = None

        dao = UserDAO(_factory(session))
        result = await dao.get_by_username("nobody")

        assert result is None
        session.close.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_closes_session_on_error(self):
        session = AsyncMock()
        session.scalar.side_effect = RuntimeError("DB error")

        dao = UserDAO(_factory(session))
        with pytest.raises(RuntimeError):
            await dao.get_by_username("alice")

        session.close.assert_awaited_once()
