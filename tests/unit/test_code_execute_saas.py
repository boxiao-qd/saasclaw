"""Tests for code_execute.py — SaaS mode guard verification."""

import json
import pytest
from app.config import settings


class TestCodeExecuteSaasGuard:
    @pytest.mark.asyncio
    async def test_blocked_in_saas_mode(self):
        """code_execute should be blocked in SaaS mode."""
        from app.agent.tools.code_execute import execute

        original = settings.saas_mode
        settings.saas_mode = True
        result = json.loads(await execute(
            json.dumps({"language": "python", "code": "print('hello')"}),
            "test_user",
        ))
        assert result["exit_code"] == -1
        assert "blocked in SaaS mode" in result["error"]
        settings.saas_mode = original

    @pytest.mark.asyncio
    async def test_allowed_in_non_saas_mode(self):
        """code_execute should work in non-SaaS mode (runs actual code)."""
        from app.agent.tools.code_execute import execute

        original = settings.saas_mode
        settings.saas_mode = False
        result = json.loads(await execute(
            json.dumps({"language": "python", "code": "print('hello')"}),
            "test_user",
        ))
        assert result["exit_code"] == 0
        assert "hello" in result["output"]
        settings.saas_mode = original