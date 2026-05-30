"""Tests for session CRUD endpoints — auth middleware and validation."""

import pytest
from fastapi.testclient import TestClient
from app.main import app


@pytest.fixture
def client():
    return TestClient(app, raise_server_exceptions=False)


class TestSessionEndpoints:
    def test_create_session_missing_header(self, client):
        resp = client.post("/v1/sessions", json={"title": "test"})
        assert resp.status_code == 422
        assert resp.json()["error_code"] == "BX_1002"

    def test_create_session_with_header_no_db(self, client):
        """Without DB, server returns 500 — integration test covers the happy path."""
        resp = client.post(
            "/v1/sessions",
            json={"title": "test session", "model": "gpt-4o"},
            headers={"X-User-Account": "user001"},
        )
        assert resp.status_code == 500