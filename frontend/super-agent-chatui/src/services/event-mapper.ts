import type { SSEEventEnvelope, SSEEventType } from "@/types/sse-events";
import type {
  TextDeltaData, ThinkingStartData, ThinkingData, ThinkingEndData, MessageDoneData, ErrorData,
  ToolCallStartData, ToolCallEndData, ToolResultData,
  DelegationStartData, DelegationEndData,
} from "@/types/sse-events";

export function mapSSEEvent(event: SSEEventEnvelope): { type: SSEEventType; data: Record<string, unknown> } {
  return { type: event.type, data: event.data };
}

export function isTextDelta(data: Record<string, unknown>): data is TextDeltaData {
  return "message_id" in data && "delta" in data;
}

export function isThinking(data: Record<string, unknown>): data is ThinkingData {
  return "message_id" in data && "delta" in data;
}

export function isThinkingStart(data: Record<string, unknown>): data is ThinkingStartData {
  return "message_id" in data;
}

export function isThinkingDelta(data: Record<string, unknown>): data is ThinkingData {
  return "message_id" in data && "delta" in data;
}

export function isThinkingEnd(data: Record<string, unknown>): data is ThinkingEndData {
  return "message_id" in data;
}

export function isMessageDone(data: Record<string, unknown>): data is MessageDoneData {
  return "message_id" in data && "role" in data && "token_count" in data;
}

export function isError(data: Record<string, unknown>): data is ErrorData {
  return "error_code" in data && "message" in data && "recoverable" in data;
}

export function isToolCallStart(data: Record<string, unknown>): data is ToolCallStartData {
  return "tool_call_id" in data && "tool_name" in data;
}

export function isToolCallEnd(data: Record<string, unknown>): data is ToolCallEndData {
  return "tool_call_id" in data && "tool_name" in data && "args" in data;
}

export function isToolResult(data: Record<string, unknown>): data is ToolResultData {
  return "tool_call_id" in data && "tool_name" in data && "result" in data;
}

export function isDelegationStart(data: Record<string, unknown>): data is DelegationStartData {
  return "child_session_id" in data && "subagent_name" in data;
}

export function isDelegationEnd(data: Record<string, unknown>): data is DelegationEndData {
  return "child_session_id" in data && "summary" in data;
}