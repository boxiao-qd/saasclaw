"""Unit tests for auth API endpoints — Pydantic validation and endpoint logic."""
import pytest
from pydantic import ValidationError
from unittest.mock import AsyncMock, MagicMock, patch

from app.api.auth import RegisterRequest


class TestRegisterRequestValidation:
    def test_valid_request(self):
        req = RegisterRequest(username="alice", password="password123")
        assert req.username == "alice"

    def test_username_too_short_raises(self):
        with pytest.raises(ValidationError):
            RegisterRequest(username="ab", password="password123")

    def test_username_too_long_raises(self):
        with pytest.raises(ValidationError):
            RegisterRequest(username="a" * 33, password="password123")

    def test_username_with_at_sign_raises(self):
        with pytest.raises(ValidationError):
            RegisterRequest(username="alice@domain", password="password123")

    def test_username_with_hyphen_raises(self):
        with pytest.raises(ValidationError):
            RegisterRequest(username="alice-bob", password="password123")

    def test_username_with_underscore_allowed(self):
        req = RegisterRequest(username="alice_bob", password="password123")
        assert req.username == "alice_bob"

    def test_username_strips_surrounding_whitespace(self):
        req = RegisterRequest(username="  alice  ", password="password123")
        assert req.username == "alice"

    def test_password_too_short_raises(self):
        with pytest.raises(ValidationError):
            RegisterRequest(username="alice", password="12345")

    def test_password_exactly_6_chars_accepted(self):
        req = RegisterRequest(username="alice", password="123456")
        assert req.password == "123456"


@pytest.fixture
def client():
    from fastapi.testclient import TestClient
    from app.main import app
    return TestClient(app, raise_server_exceptions=False)


def _mock_dao(MockDAO, instance):
    """Wire up a mock session factory so get_session_factory() doesn't hit the real DB."""
    MockDAO.return_value = instance


class TestRegisterEndpoint:
    def test_duplicate_username_returns_409(self, client):
        mock_user = MagicMock()
        mock_user.username = "alice"
        with patch("app.api.auth.get_session_factory", return_value=MagicMock()), \
             patch("app.api.auth.UserDAO") as MockDAO:
            instance = AsyncMock()
            _mock_dao(MockDAO, instance)
            instance.get_by_username.return_value = mock_user

            resp = client.post("/auth/register", json={"username": "alice", "password": "password123"})

        assert resp.status_code == 409

    def test_race_condition_returns_409(self, client):
        """DAO.create() returning None (IntegrityError race) must produce 409, not 500."""
        with patch("app.api.auth.get_session_factory", return_value=MagicMock()), \
             patch("app.api.auth.UserDAO") as MockDAO:
            instance = AsyncMock()
            _mock_dao(MockDAO, instance)
            instance.get_by_username.return_value = None
            instance.create.return_value = None  # race

            resp = client.post("/auth/register", json={"username": "alice", "password": "password123"})

        assert resp.status_code == 409

    def test_success_returns_201_with_token(self, client):
        from app.models.user import User
        mock_user = User(id="uuid-1", username="alice", hashed_password="hash")
        with patch("app.api.auth.get_session_factory", return_value=MagicMock()), \
             patch("app.api.auth.UserDAO") as MockDAO:
            instance = AsyncMock()
            _mock_dao(MockDAO, instance)
            instance.get_by_username.return_value = None
            instance.create.return_value = mock_user

            resp = client.post("/auth/register", json={"username": "alice", "password": "password123"})

        assert resp.status_code == 201
        data = resp.json()
        assert "access_token" in data
        assert data["username"] == "alice"
        assert data["token_type"] == "bearer"

    def test_short_username_returns_422(self, client):
        resp = client.post("/auth/register", json={"username": "ab", "password": "password123"})
        assert resp.status_code == 422

    def test_short_password_returns_422(self, client):
        resp = client.post("/auth/register", json={"username": "alice", "password": "12345"})
        assert resp.status_code == 422


class TestLoginEndpoint:
    def test_success_returns_200_with_token(self, client):
        from app.models.user import User
        from app.auth.jwt_utils import hash_password
        hashed = hash_password("password123")
        mock_user = User(id="uuid-1", username="alice", hashed_password=hashed)
        with patch("app.api.auth.get_session_factory", return_value=MagicMock()), \
             patch("app.api.auth.UserDAO") as MockDAO:
            instance = AsyncMock()
            _mock_dao(MockDAO, instance)
            instance.get_by_username.return_value = mock_user

            resp = client.post("/auth/login", json={"username": "alice", "password": "password123"})

        assert resp.status_code == 200
        data = resp.json()
        assert "access_token" in data
        assert data["username"] == "alice"

    def test_wrong_password_returns_401(self, client):
        from app.models.user import User
        from app.auth.jwt_utils import hash_password
        mock_user = User(id="uuid-1", username="alice", hashed_password=hash_password("correct"))
        with patch("app.api.auth.get_session_factory", return_value=MagicMock()), \
             patch("app.api.auth.UserDAO") as MockDAO:
            instance = AsyncMock()
            _mock_dao(MockDAO, instance)
            instance.get_by_username.return_value = mock_user

            resp = client.post("/auth/login", json={"username": "alice", "password": "wrong"})

        assert resp.status_code == 401

    def test_nonexistent_user_returns_401(self, client):
        with patch("app.api.auth.get_session_factory", return_value=MagicMock()), \
             patch("app.api.auth.UserDAO") as MockDAO:
            instance = AsyncMock()
            _mock_dao(MockDAO, instance)
            instance.get_by_username.return_value = None

            resp = client.post("/auth/login", json={"username": "ghost", "password": "password123"})

        assert resp.status_code == 401


class TestAuthMiddleware:
    def test_protected_endpoint_without_token_returns_401(self, client):
        resp = client.get("/v1/sessions")
        assert resp.status_code == 401
        assert resp.json()["error_code"] == "BX_AUTH_1001"

    def test_protected_endpoint_with_invalid_token_returns_401(self, client):
        resp = client.get(
            "/v1/sessions",
            headers={"Authorization": "Bearer not.a.real.token"},
        )
        assert resp.status_code == 401
        assert resp.json()["error_code"] == "BX_AUTH_1002"

    def test_auth_endpoints_bypass_middleware(self, client):
        """POST /auth/login should never return 401 from middleware (may 422 for bad body)."""
        resp = client.post("/auth/login", json={})
        assert resp.status_code != 401 or resp.json().get("error_code") not in ("BX_AUTH_1001", "BX_AUTH_1002")
