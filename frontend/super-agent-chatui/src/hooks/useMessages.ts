
import { useEffect, useCallback, useRef } from "react";
import { useMessageStore } from "@/store/message-store";
import { useSSEStore } from "@/store/sse-store";
import { apiGet } from "@/services/api-client";
import {
  isTextDelta,
  isMessageDone,
  isThinkingStart,
  isThinkingDelta,
  isThinkingEnd,
  isToolCallStart,
  isToolCallEnd,
  isToolResult,
  isDelegationStart,
  isDelegationEnd,
  isError,
} from "@/services/event-mapper";
import type { MessageItem, PaginationMeta } from "@/types/api-types";
import type { SSEEventEnvelope } from "@/types/sse-events";

interface UseMessagesOptions {
  sessionId: string;
}

interface UseMessagesReturn {
  messages: MessageItem[];
  streamingDelta: string;
  streamingMessageId: string | null;
  loading: boolean;
  loadMore: () => Promise<void>;
}

interface MessagesResponse {
  messages: MessageItem[];
  pagination: PaginationMeta;
}

export function useMessages({ sessionId }: UseMessagesOptions): UseMessagesReturn {
  const loadingRef = useRef(false);
  const pageRef = useRef(1);
  const hasMoreRef = useRef(true);

  const messages = useMessageStore((s) => s.messages[sessionId] || []);
  const streamingDelta = useMessageStore((s) => s.streamingDelta);
  const streamingMessageId = useMessageStore((s) => s.streamingMessageId);

  const setMessages = useMessageStore((s) => s.setMessages);
  const appendMessage = useMessageStore((s) => s.appendMessage);
  const appendDelta = useMessageStore((s) => s.appendDelta);
  const resetDelta = useMessageStore((s) => s.resetDelta);
  const setStreaming = useMessageStore((s) => s.setStreaming);

  const lastEvent = useSSEStore((s) => s.lastEvent);

  useEffect(() => {
    let cancelled = false;

    async function loadInitial() {
      if (loadingRef.current) return;
      loadingRef.current = true;
      pageRef.current = 1;
      hasMoreRef.current = true;

      try {
        const resp = await apiGet<MessagesResponse>(
          `/messages/${sessionId}?page=1&page_size=50`,
        );
        if (!cancelled) {
          setMessages(sessionId, resp.messages);
          hasMoreRef.current =
            resp.pagination.page * resp.pagination.page_size < resp.pagination.total;
        }
      } catch {
        // Initial load failure — store remains empty, UI shows empty/error state
      } finally {
        loadingRef.current = false;
      }
    }

    loadInitial();

    return () => {
      cancelled = true;
    };
  }, [sessionId, setMessages]);

  // Process SSE events from the store
  useEffect(() => {
    if (!lastEvent || lastEvent.session_id !== sessionId) return;

    const { type, data } = lastEvent;

    if (type === "text_delta" && isTextDelta(data)) {
      setStreaming(data.message_id);
      appendDelta(data.delta);
    }

    if (type === "message_done" && isMessageDone(data)) {
      resetDelta();
      setStreaming(null);
      appendMessage(sessionId, {
        id: data.message_id,
        session_id: sessionId,
        role: data.role,
        token_count: data.token_count,
        is_compressed: false,
        created_at: new Date().toISOString(),
      });
    }

    // Thinking events are handled by dedicated store fields (thinkingBlocks)
    // via ChatSessionPage SSE callback, NOT through text_delta channel

    if (type === "thinking_start" && isThinkingStart(data)) {
      // Delegated to message-store startThinking via SSE handler
    }

    if (type === "thinking_delta" && isThinkingDelta(data)) {
      // Delegated to message-store appendThinkingDelta via SSE handler
    }

    if (type === "thinking_end" && isThinkingEnd(data)) {
      // Delegated to message-store endThinking via SSE handler
    }

    // Tool call, delegation, and error events are dispatched to the store
    // for UI components that subscribe to specific event types via lastEvent
    // No additional message-store mutation needed for these event categories

    if (type === "tool_call_start" && isToolCallStart(data)) {
      // Tool call metadata attached to streaming message; no store mutation
    }

    if (type === "tool_call_end" && isToolCallEnd(data)) {
      // Tool call completed; no message-store mutation
    }

    if (type === "tool_result" && isToolResult(data)) {
      // Tool result available; no message-store mutation
    }

    if (type === "delegation_start" && isDelegationStart(data)) {
      // Delegation started; no message-store mutation
    }

    if (type === "delegation_end" && isDelegationEnd(data)) {
      // Delegation ended; no message-store mutation
    }

    if (type === "error" && isError(data)) {
      // Error event; no message-store mutation — UI reads from sse-store
    }
  }, [lastEvent, sessionId, setStreaming, appendDelta, resetDelta, appendMessage]);

  const loadMore = useCallback(async () => {
    if (loadingRef.current || !hasMoreRef.current) return;

    loadingRef.current = true;
    pageRef.current += 1;

    try {
      const resp = await apiGet<MessagesResponse>(
        `/messages/${sessionId}?page=${pageRef.current}&page_size=50`,
      );
      const currentMessages = useMessageStore.getState().messages[sessionId] || [];
      setMessages(sessionId, [...currentMessages, ...resp.messages]);
      hasMoreRef.current =
        resp.pagination.page * resp.pagination.page_size < resp.pagination.total;
    } catch {
      // Pagination failure — keep existing messages, user can retry
    } finally {
      loadingRef.current = false;
    }
  }, [sessionId, setMessages]);

  return {
    messages,
    streamingDelta,
    streamingMessageId,
    loading: loadingRef.current,
    loadMore,
  };
}