"""Tests for middleware auth and error handler."""

import pytest
from app.middleware.auth import AuthMiddleware
from app.middleware.error_handler import AppError


class TestAppError:
    def test_app_error_fields(self):
        err = AppError(error_code="BX_1001", message="Unauthorized", status_code=401)
        assert err.error_code == "BX_1001"
        assert err.status_code == 401
        assert err.detail is None

    def test_app_error_with_detail(self):
        err = AppError(error_code="BX_1002", message="Validation", status_code=422, detail={"field": "x"})
        assert err.detail == {"field": "x"}