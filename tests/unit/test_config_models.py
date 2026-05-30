"""Tests for config and model definitions."""

import pytest
from app.config import Settings
from app.models.base import GLOBAL_SENTINEL, Base, TimestampMixin, UserAccountMixin


class TestConfig:
    def test_default_root_path(self):
        s = Settings()
        assert s.root_path == "/bx/api"

    def test_default_sse_keepalive(self):
        s = Settings()
        assert s.sse_keepalive_interval_seconds == 15


class TestModels:
    def test_global_sentinel_value(self):
        assert GLOBAL_SENTINEL == "__global__"

    def test_base_declarative(self):
        assert Base is not None