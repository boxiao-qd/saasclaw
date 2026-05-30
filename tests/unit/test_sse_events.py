"""Tests for SSE event type enums and data schemas."""

import pytest
from app.sse.event_types import SSEEventType, SSEEventEnvelope, TextDeltaData, MessageDoneData, ErrorData


class TestSSEEventType:
    def test_all_event_types_defined(self):
        expected = [
            "text_delta", "thinking_start", "thinking_delta", "thinking_end",
            "tool_call_start", "tool_call_delta", "tool_call_end", "tool_result",
            "delegation_start", "delegation_update", "delegation_end",
            "message_done", "notification_new", "context_compression", "error",
        ]
        for name in expected:
            assert SSEEventType(name) is not None

    def test_text_delta_data_schema(self):
        data = TextDeltaData(message_id="msg1", delta="hello")
        assert data.message_id == "msg1"
        assert data.delta == "hello"

    def test_message_done_data_schema(self):
        data = MessageDoneData(message_id="msg1", role="assistant", token_count=50, stop_reason="end_turn")
        assert data.stop_reason == "end_turn"

    def test_error_data_schema(self):
        data = ErrorData(error_code="BX_1001", message="Unauthorized", recoverable=False)
        assert not data.recoverable

    def test_sse_event_envelope(self):
        envelope = SSEEventEnvelope(
            type=SSEEventType.text_delta,
            session_id="sess1",
            timestamp=1234567890.0,
            data={"message_id": "msg1", "delta": "hi"},
        )
        assert envelope.type == SSEEventType.text_delta