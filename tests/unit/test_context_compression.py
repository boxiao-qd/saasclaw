"""Unit tests for context compression enhancement.

Covers:
- Settings.context_compression_threshold validator
- SSEEventType.context_compression + ContextCompressionData schema
- compress_if_needed threshold logic and SSE push (mocked DAOs)
"""

import pytest
import pytest_asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from app.config import Settings
from app.sse.event_types import SSEEventType, ContextCompressionData


# ─────────────────────────────────────────────────────────────────────────────
# 1. Config validator
# ─────────────────────────────────────────────────────────────────────────────

class TestCompressionThresholdConfig:
    def test_default_is_0_8(self):
        s = Settings()
        assert s.context_compression_threshold == 0.8

    def test_valid_custom_value(self):
        s = Settings(context_compression_threshold=0.6)
        assert s.context_compression_threshold == 0.6

    def test_boundary_exactly_1_0(self):
        s = Settings(context_compression_threshold=1.0)
        assert s.context_compression_threshold == 1.0

    def test_low_boundary_just_above_0(self):
        s = Settings(context_compression_threshold=0.1)
        assert s.context_compression_threshold == 0.1

    def test_zero_falls_back_to_default(self):
        # 0.0 is out of range (0.0, 1.0], should fall back to 0.8
        s = Settings(context_compression_threshold=0.0)
        assert s.context_compression_threshold == 0.8

    def test_greater_than_1_falls_back_to_default(self):
        s = Settings(context_compression_threshold=1.5)
        assert s.context_compression_threshold == 0.8

    def test_negative_falls_back_to_default(self):
        s = Settings(context_compression_threshold=-0.1)
        assert s.context_compression_threshold == 0.8

    def test_string_value_is_parsed(self):
        # Env vars arrive as strings
        s = Settings(context_compression_threshold="0.75")
        assert s.context_compression_threshold == 0.75

    def test_string_invalid_falls_back_to_default(self):
        s = Settings(context_compression_threshold="1.5")
        assert s.context_compression_threshold == 0.8


# ─────────────────────────────────────────────────────────────────────────────
# 2. SSE event type and data schema
# ─────────────────────────────────────────────────────────────────────────────

class TestContextCompressionSSE:
    def test_enum_value_exists(self):
        assert SSEEventType.context_compression == "context_compression"
        assert SSEEventType("context_compression") is SSEEventType.context_compression

    def test_data_schema_valid(self):
        data = ContextCompressionData(
            tokens_before=80000,
            tokens_after=30000,
            compressed_count=15,
            summary_preview="User discussed project requirements...",
        )
        assert data.tokens_before == 80000
        assert data.tokens_after == 30000
        assert data.compressed_count == 15
        assert data.summary_preview == "User discussed project requirements..."

    def test_data_schema_missing_field(self):
        from pydantic import ValidationError
        with pytest.raises(ValidationError):
            ContextCompressionData(tokens_before=100, tokens_after=50)  # missing compressed_count, summary_preview

    def test_data_schema_serializable(self):
        data = ContextCompressionData(
            tokens_before=1000, tokens_after=500, compressed_count=5, summary_preview="test"
        )
        d = data.model_dump()
        assert set(d.keys()) == {"tokens_before", "tokens_after", "compressed_count", "summary_preview"}


# ─────────────────────────────────────────────────────────────────────────────
# 3. compress_if_needed threshold logic
# ─────────────────────────────────────────────────────────────────────────────

def _make_session(token_count: int, max_tokens: int):
    s = MagicMock()
    s.token_count = token_count
    s.max_tokens = max_tokens
    return s


def _make_msg(id: str, role: str, content: str, token_count: int, is_compressed: bool = False):
    m = MagicMock()
    m.id = id
    m.role = role
    m.content = content
    m.token_count = token_count
    m.is_compressed = is_compressed
    return m


@pytest.fixture
def mock_history():
    """Six messages so we have enough to compress (history[2:-2] = 2 messages)."""
    return [
        _make_msg("m1", "user", "Hello", 100),
        _make_msg("m2", "assistant", "Hi there", 100),
        _make_msg("m3", "user", "What is X?", 200),
        _make_msg("m4", "assistant", "X is Y", 200),
        _make_msg("m5", "user", "Thanks", 50),
        _make_msg("m6", "assistant", "You're welcome", 50),
    ]


@pytest.mark.asyncio
async def test_skip_when_max_tokens_zero():
    """Guard: max_tokens=0 must return False without any DB calls."""
    session = _make_session(token_count=50000, max_tokens=0)
    session_dao = AsyncMock()
    session_dao.get_by_id.return_value = session

    with patch("app.agent.context_compressor.SessionDAO", return_value=session_dao), \
         patch("app.agent.context_compressor.MessageDAO"), \
         patch("app.agent.context_compressor.get_session_factory"):
        from app.agent.context_compressor import compress_if_needed
        result = await compress_if_needed(employee_id=1, session_id="sess1")

    assert result is False


@pytest.mark.asyncio
async def test_skip_when_below_threshold():
    """token_count/max_tokens = 0.75 < threshold=0.8 → skip."""
    session = _make_session(token_count=75000, max_tokens=100000)
    session_dao = AsyncMock()
    session_dao.get_by_id.return_value = session

    with patch("app.agent.context_compressor.SessionDAO", return_value=session_dao), \
         patch("app.agent.context_compressor.MessageDAO"), \
         patch("app.agent.context_compressor.get_session_factory"), \
         patch("app.agent.context_compressor.settings") as mock_settings:
        mock_settings.memory_distill_enabled = False
        mock_settings.context_compression_threshold = 0.8

        from importlib import reload
        import app.agent.context_compressor as cc
        result = await cc.compress_if_needed(employee_id=1, session_id="sess1")

    assert result is False


@pytest.mark.asyncio
async def test_skip_when_exactly_below_threshold():
    """Boundary: 79999/100000 = 0.79999 < 0.8 → skip."""
    session = _make_session(token_count=79999, max_tokens=100000)
    session_dao = AsyncMock()
    session_dao.get_by_id.return_value = session

    with patch("app.agent.context_compressor.SessionDAO", return_value=session_dao), \
         patch("app.agent.context_compressor.MessageDAO"), \
         patch("app.agent.context_compressor.get_session_factory"), \
         patch("app.agent.context_compressor.settings") as mock_settings:
        mock_settings.memory_distill_enabled = False
        mock_settings.context_compression_threshold = 0.8

        import app.agent.context_compressor as cc
        result = await cc.compress_if_needed(employee_id=1, session_id="sess1")

    assert result is False


@pytest.mark.asyncio
async def test_trigger_at_threshold(mock_history):
    """token_count/max_tokens = 0.80 >= threshold=0.8 → proceeds to compress."""
    session = _make_session(token_count=80000, max_tokens=100000)
    session_dao = AsyncMock()
    session_dao.get_by_id.return_value = session

    msg_dao = AsyncMock()
    msg_dao.get_history.return_value = (mock_history, False)
    msg_dao.update = AsyncMock()
    msg_dao.create = AsyncMock()

    mock_response = MagicMock()
    mock_response.choices[0].message.content = "Summary of the conversation."

    with patch("app.agent.context_compressor.SessionDAO", return_value=session_dao), \
         patch("app.agent.context_compressor.MessageDAO", return_value=msg_dao), \
         patch("app.agent.context_compressor.get_session_factory"), \
         patch("app.agent.context_compressor.settings") as mock_settings, \
         patch("app.agent.context_compressor.LLMRouter") as MockRouter, \
         patch("app.api.v1.stream.push_event", new_callable=AsyncMock) as mock_push:
        mock_settings.memory_distill_enabled = False
        mock_settings.context_compression_threshold = 0.8
        mock_settings.compress_model = "test-model"
        router_instance = AsyncMock()
        router_instance.chat.return_value = mock_response
        MockRouter.return_value = router_instance

        import app.agent.context_compressor as cc
        result = await cc.compress_if_needed(employee_id=1, session_id="sess1")

    assert result is True


@pytest.mark.asyncio
async def test_trigger_above_threshold(mock_history):
    """token_count/max_tokens = 0.90 > threshold=0.8 → compresses."""
    session = _make_session(token_count=90000, max_tokens=100000)
    session_dao = AsyncMock()
    session_dao.get_by_id.return_value = session

    msg_dao = AsyncMock()
    msg_dao.get_history.return_value = (mock_history, False)
    msg_dao.update = AsyncMock()
    msg_dao.create = AsyncMock()

    mock_response = MagicMock()
    mock_response.choices[0].message.content = "Summary text here."

    with patch("app.agent.context_compressor.SessionDAO", return_value=session_dao), \
         patch("app.agent.context_compressor.MessageDAO", return_value=msg_dao), \
         patch("app.agent.context_compressor.get_session_factory"), \
         patch("app.agent.context_compressor.settings") as mock_settings, \
         patch("app.agent.context_compressor.LLMRouter") as MockRouter, \
         patch("app.api.v1.stream.push_event", new_callable=AsyncMock):
        mock_settings.memory_distill_enabled = False
        mock_settings.context_compression_threshold = 0.8
        mock_settings.compress_model = "test-model"
        router_instance = AsyncMock()
        router_instance.chat.return_value = mock_response
        MockRouter.return_value = router_instance

        import app.agent.context_compressor as cc
        result = await cc.compress_if_needed(employee_id=1, session_id="sess1")

    assert result is True


@pytest.mark.asyncio
async def test_sse_event_pushed_on_compress(mock_history):
    """After compression, push_event must be called with correct fields."""
    session = _make_session(token_count=90000, max_tokens=100000)
    session_dao = AsyncMock()
    session_dao.get_by_id.return_value = session

    msg_dao = AsyncMock()
    msg_dao.get_history.return_value = (mock_history, False)
    msg_dao.update = AsyncMock()
    msg_dao.create = AsyncMock()

    mock_response = MagicMock()
    mock_response.choices[0].message.content = "A" * 200  # longer than 100 chars

    with patch("app.agent.context_compressor.SessionDAO", return_value=session_dao), \
         patch("app.agent.context_compressor.MessageDAO", return_value=msg_dao), \
         patch("app.agent.context_compressor.get_session_factory"), \
         patch("app.agent.context_compressor.settings") as mock_settings, \
         patch("app.agent.context_compressor.LLMRouter") as MockRouter, \
         patch("app.api.v1.stream.push_event", new_callable=AsyncMock) as mock_push:
        mock_settings.memory_distill_enabled = False
        mock_settings.context_compression_threshold = 0.8
        mock_settings.compress_model = "test-model"
        router_instance = AsyncMock()
        router_instance.chat.return_value = mock_response
        MockRouter.return_value = router_instance

        import app.agent.context_compressor as cc
        await cc.compress_if_needed(employee_id=1, session_id="sess1")

        mock_push.assert_called_once()
        call_kwargs = mock_push.call_args
        _, event_type, payload = call_kwargs[0]
        assert event_type == SSEEventType.context_compression
        assert payload["tokens_before"] == 90000
        assert "tokens_after" in payload
        # compressed_count = len(history[2:-2]) = 2
        assert payload["compressed_count"] == 2
        # summary_preview must be truncated to 100 chars
        assert len(payload["summary_preview"]) <= 100


@pytest.mark.asyncio
async def test_sse_push_failure_does_not_abort_compression(mock_history):
    """push_event raising an exception should not cause compress_if_needed to return False."""
    session = _make_session(token_count=90000, max_tokens=100000)
    session_dao = AsyncMock()
    session_dao.get_by_id.return_value = session

    msg_dao = AsyncMock()
    msg_dao.get_history.return_value = (mock_history, False)
    msg_dao.update = AsyncMock()
    msg_dao.create = AsyncMock()

    mock_response = MagicMock()
    mock_response.choices[0].message.content = "Summary."

    with patch("app.agent.context_compressor.SessionDAO", return_value=session_dao), \
         patch("app.agent.context_compressor.MessageDAO", return_value=msg_dao), \
         patch("app.agent.context_compressor.get_session_factory"), \
         patch("app.agent.context_compressor.settings") as mock_settings, \
         patch("app.agent.context_compressor.LLMRouter") as MockRouter, \
         patch("app.api.v1.stream.push_event", new_callable=AsyncMock, side_effect=RuntimeError("SSE closed")):
        mock_settings.memory_distill_enabled = False
        mock_settings.context_compression_threshold = 0.8
        mock_settings.compress_model = "test-model"
        router_instance = AsyncMock()
        router_instance.chat.return_value = mock_response
        MockRouter.return_value = router_instance

        import app.agent.context_compressor as cc
        result = await cc.compress_if_needed(employee_id=1, session_id="sess1")

    # Compression succeeded even though SSE push failed
    assert result is True


@pytest.mark.asyncio
async def test_skip_when_too_few_messages():
    """If history has < 5 messages after threshold passes, return False."""
    session = _make_session(token_count=90000, max_tokens=100000)
    session_dao = AsyncMock()
    session_dao.get_by_id.return_value = session

    short_history = [
        _make_msg("m1", "user", "A", 100),
        _make_msg("m2", "assistant", "B", 100),
        _make_msg("m3", "user", "C", 100),
    ]
    msg_dao = AsyncMock()
    msg_dao.get_history.return_value = (short_history, False)

    with patch("app.agent.context_compressor.SessionDAO", return_value=session_dao), \
         patch("app.agent.context_compressor.MessageDAO", return_value=msg_dao), \
         patch("app.agent.context_compressor.get_session_factory"), \
         patch("app.agent.context_compressor.settings") as mock_settings:
        mock_settings.memory_distill_enabled = False
        mock_settings.context_compression_threshold = 0.8

        import app.agent.context_compressor as cc
        result = await cc.compress_if_needed(employee_id=1, session_id="sess1")

    assert result is False
