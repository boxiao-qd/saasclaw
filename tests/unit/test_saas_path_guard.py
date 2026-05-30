"""Tests for saas_path_guard.py — SaaS path whitelist validation."""

import os
import pytest
from app.agent.tools.saas_path_guard import (
    _is_under_dir,
    _saas_read_allowed,
    _saas_write_allowed,
    _saas_search_allowed,
    SAAS_READ_DENIED_MSG,
    SAAS_WRITE_DENIED_MSG,
    SAAS_SEARCH_DENIED_MSG,
)


class TestIsUnderDir:
    def test_exact_match(self):
        assert _is_under_dir("/data/system-config", "/data/system-config")

    def test_subdirectory(self):
        assert _is_under_dir("/data/system-config/skills/foo", "/data/system-config")

    def test_subdirectory_file(self):
        assert _is_under_dir("/data/system-config/hooks/hook.json", "/data/system-config")

    def test_prefix_collision_rejected(self):
        # /data/system-config-data should NOT match /data/system-config
        assert not _is_under_dir("/data/system-config-data", "/data/system-config")

    def test_prefix_collision_rejected_2(self):
        # /data/uc-data should NOT match /data/uc
        assert not _is_under_dir("/data/uc-data", "/data/uc")

    def test_different_path_rejected(self):
        assert not _is_under_dir("/tmp/other", "/data/system-config")

    def test_parent_path_rejected(self):
        assert not _is_under_dir("/data", "/data/system-config")


class TestSaasPathGuardIntegration:
    """Test the SaaS path guard functions with actual settings values."""

    def test_read_allowed_system_config_dir(self):
        # In SaaS mode, system-config dir is readable
        from app.config import settings
        if not settings.saas_mode:
            pytest.skip("SaaS mode not enabled")
        assert _saas_read_allowed(settings.saas_system_config_dir)

    def test_read_allowed_user_config_dir(self):
        from app.config import settings
        if not settings.saas_mode:
            pytest.skip("SaaS mode not enabled")
        assert _saas_read_allowed(settings.saas_user_config_dir)

    def test_write_allowed_user_config_dir(self):
        from app.config import settings
        if not settings.saas_mode:
            pytest.skip("SaaS mode not enabled")
        assert _saas_write_allowed(settings.saas_user_config_dir)

    def test_write_denied_system_config_dir(self):
        from app.config import settings
        if not settings.saas_mode:
            pytest.skip("SaaS mode not enabled")
        assert not _saas_write_allowed(settings.saas_system_config_dir)

    def test_read_denied_other_path(self):
        from app.config import settings
        if not settings.saas_mode:
            pytest.skip("SaaS mode not enabled")
        assert not _saas_read_allowed("/tmp/some_random_path")

    def test_write_denied_other_path(self):
        from app.config import settings
        if not settings.saas_mode:
            pytest.skip("SaaS mode not enabled")
        assert not _saas_write_allowed("/tmp/some_random_path")

    def test_search_denied_other_path(self):
        from app.config import settings
        if not settings.saas_mode:
            pytest.skip("SaaS mode not enabled")
        assert not _saas_search_allowed("/tmp/some_random_path")

    def test_non_saas_mode_allows_all(self):
        """When SaaS mode is off, all paths should be allowed."""
        # Temporarily disable SaaS mode for this test
        from app.config import settings
        original = settings.saas_mode
        settings.saas_mode = False
        assert _saas_read_allowed("/tmp/any_path")
        assert _saas_write_allowed("/tmp/any_path")
        assert _saas_search_allowed("/tmp/any_path")
        settings.saas_mode = original