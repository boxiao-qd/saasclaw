"""Tests for Pydantic schemas validation."""

import pytest
from app.schemas.common import RoleEnum, PaginationMeta, ErrorResponse
from app.schemas.messages import SendMessageRequest, SendMessageResponse
from app.schemas.sessions import CreateSessionRequest, SessionItem
from app.schemas.memory import CreateMemoryRequest
from app.schemas.skills import CreateSkillRequest
from app.schemas.subagents import CreateSubagentRequest


class TestCommonSchemas:
    def test_role_enum_values(self):
        assert RoleEnum.user == "user"
        assert RoleEnum.assistant == "assistant"

    def test_pagination_meta_defaults(self):
        meta = PaginationMeta(total=100)
        assert meta.page == 1
        assert meta.page_size == 20

    def test_error_response(self):
        err = ErrorResponse(error_code="BX_1001", message="Unauthorized")
        assert err.detail is None


class TestMessageSchemas:
    def test_send_message_request_defaults(self):
        req = SendMessageRequest(session_id="s1", content="hello")
        assert req.role == RoleEnum.user

    def test_send_message_request_validation(self):
        with pytest.raises(Exception):
            SendMessageRequest(session_id="", content="hello")


class TestSessionSchemas:
    def test_create_session_optional_fields(self):
        req = CreateSessionRequest()
        assert req.title is None
        assert req.model is None


class TestMemorySchemas:
    def test_create_memory_key_length_limit(self):
        with pytest.raises(Exception):
            CreateMemoryRequest(key="a" * 300, value="test")


class TestSkillSchemas:
    def test_create_skill_defaults(self):
        req = CreateSkillRequest(name="test", content_md="# Skill")
        assert req.is_global is False


class TestSubagentSchemas:
    def test_create_subagent_required_fields(self):
        req = CreateSubagentRequest(name="agent1", definition_md="# Agent", tools=["web_search"], constraints=[])
        assert req.name == "agent1"