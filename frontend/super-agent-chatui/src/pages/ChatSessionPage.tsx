import { useEffect, useLayoutEffect, useRef, useState, useCallback } from "react";
import { useParams } from "react-router-dom";
import { useMessageStore } from "@/store/message-store";
import { useSessionStore } from "@/store/session-store";
import { useSSEStore } from "@/store/sse-store";
import { useUIStore } from "@/store/ui-store";
import { SSEManager } from "@/services/sse-manager";
import { apiGet } from "@/services/api-client";
import { ChatInputSection } from "@/components/section/ChatInputSection";
import { MessageFlow } from "@/components/section/MessageFlow";
import type { MessageItem } from "@/types/api-types";

export function ChatSessionPage() {
  const { sessionId } = useParams<{ sessionId: string }>();
  const {
    setMessages, messages, appendMessage, appendDelta, setStreaming,
    streamingDelta, streamingMessageId, userAckMessage,
    thinkingBlocks, toolCallBlocks, delegationBlocks, compressionEvents,
    startThinking, appendThinkingDelta, endThinking, collapseThinking,
    startToolCall, updateToolCallArgs, setToolResult,
    loadHistoricalToolCalls, prependMessages,
    startDelegation, updateDelegation, endDelegation,
    rekeyMessageBlocks,
    appendCompressionEvent,
    setUserAck, clearUserAck,
    setPlan, updatePlanStep, clearPlan, plan,
  } = useMessageStore();
  const { activeSessionId } = useSessionStore();
  const { setConnected, pushEvent } = useSSEStore();
  const setAutoScroll = useUIStore((s) => s.setAutoScroll);
  const [loading, setLoading] = useState(true);
  const [hasMore, setHasMore] = useState(false);
  const [beforeCursor, setBeforeCursor] = useState<string | null>(null);
  const [isLoadingMore, setIsLoadingMore] = useState(false);
  const scrollRef = useRef<HTMLDivElement | null>(null);
  // Tracks saved scrollHeight before prepend so we can restore position after layout
  const savedScrollHeightRef = useRef<number | null>(null);
  // Synchronous guard to prevent concurrent load-more fetches (state updates are async)
  const loadingMoreRef = useRef(false);
  const sseRef = useRef<SSEManager | null>(null);
  // Use ref to read streamingMessageId inside SSE callback without re-creating the connection
  const streamingMessageIdRef = useRef(streamingMessageId);
  useEffect(() => {
    streamingMessageIdRef.current = streamingMessageId;
  }, [streamingMessageId]);

  // Load messages on mount; reset auto-scroll so history always opens at bottom
  useEffect(() => {
    if (!sessionId) return;
    setAutoScroll(true);
    setLoading(true);
    apiGet<{ messages: MessageItem[]; has_more: boolean }>(`/messages/${sessionId}`)
      .then((data) => {
        setMessages(sessionId, data.messages);
        setHasMore(data.has_more);
        if (data.has_more && data.messages.length > 0) {
          setBeforeCursor(data.messages[0].id);
        }
        // Rebuild tool call blocks from history.
        // Intermediate assistant messages (empty content + tool_calls) are filtered out of
        // visibleMessages, so we attach their tool calls to the next final assistant message
        // (the one with actual content), mirroring what rekeyMessageBlocks does during streaming.
        const toolResultsByCallId: Record<string, { result: string; isError: boolean }> = {};
        for (const m of data.messages) {
          if (m.role === "tool" && m.tool_call_id && m.content != null) {
            const isError = m.content.trim().startsWith('{"error"');
            toolResultsByCallId[m.tool_call_id] = { result: m.content, isError };
          }
        }
        // Collect pending tool calls from intermediate messages, attach to next final message
        const pendingToolCalls: Array<{ id: string; name: string; arguments: string }> = [];
        for (const m of data.messages) {
          if (m.role === "assistant" && m.tool_calls && m.tool_calls.length > 0) {
            pendingToolCalls.push(...m.tool_calls);
          }
          // Final assistant message: has content and no tool_calls in DB
          if (m.role === "assistant" && m.content?.trim() && pendingToolCalls.length > 0) {
            loadHistoricalToolCalls(m.id, pendingToolCalls.splice(0), toolResultsByCallId);
          }
        }
        setLoading(false);
      })
      .catch(() => setLoading(false));
  }, [sessionId, setMessages, setAutoScroll, loadHistoricalToolCalls]);

  // Restore scroll position after older messages are prepended
  useLayoutEffect(() => {
    const el = scrollRef.current;
    if (!el || savedScrollHeightRef.current === null) return;
    el.scrollTop += el.scrollHeight - savedScrollHeightRef.current;
    savedScrollHeightRef.current = null;
  });

  const loadMoreHistory = useCallback(() => {
    if (!sessionId || !hasMore || loadingMoreRef.current || !beforeCursor) return;
    loadingMoreRef.current = true;
    setIsLoadingMore(true);
    // Save scroll height before prepend so useLayoutEffect can restore position
    if (scrollRef.current) {
      savedScrollHeightRef.current = scrollRef.current.scrollHeight;
    }
    apiGet<{ messages: MessageItem[]; has_more: boolean }>(`/messages/${sessionId}?before=${beforeCursor}`)
      .then((data) => {
        if (data.messages.length > 0) {
          prependMessages(sessionId, data.messages);
          setHasMore(data.has_more);
          setBeforeCursor(data.has_more ? data.messages[0].id : null);
        } else {
          setHasMore(false);
        }
      })
      .catch(() => {
        savedScrollHeightRef.current = null;
      })
      .finally(() => {
        loadingMoreRef.current = false;
        setIsLoadingMore(false);
      });
  }, [sessionId, hasMore, beforeCursor, prependMessages]);

  // Connect SSE — deps intentionally exclude streamingMessageId (use ref instead)
  useEffect(() => {
    if (!sessionId) return;
    // Reset streaming state from previous session to prevent cross-session leak
    setStreaming(null);
    clearUserAck();
    clearPlan();
    setHasMore(false);
    setBeforeCursor(null);

    const manager = new SSEManager(
      sessionId,
      (event) => {
        // Guard: ignore events from a different session (race condition during switch)
        if (event.session_id !== sessionId) return;

        pushEvent(event);

        if (event.type === "stream_start" && event.data) {
          const data = event.data as { message_id: string };
          setStreaming(data.message_id);
        }

        if (event.type === "user_ack" && event.data) {
          const data = event.data as { message_id: string; message: string };
          setUserAck(data.message);
        }

        if (event.type === "text_delta" && event.data) {
          const data = event.data as { message_id: string; delta: string };
          if (!streamingMessageIdRef.current) setStreaming(data.message_id);
          appendDelta(data.delta);
        }

        if (event.type === "thinking_start" && event.data) {
          const data = event.data as { message_id: string };
          startThinking(data.message_id);
        }

        if (event.type === "thinking_delta" && event.data) {
          const data = event.data as { message_id: string; delta: string };
          appendThinkingDelta(data.message_id, data.delta);
        }

        if (event.type === "thinking_end" && event.data) {
          const data = event.data as { message_id: string };
          endThinking(data.message_id);
        }

        if (event.type === "tool_call_start" && event.data) {
          const data = event.data as { tool_call_id: string; tool_name: string };
          startToolCall(data.tool_call_id, data.tool_name);
        }

        if (event.type === "tool_call_end" && event.data) {
          const data = event.data as { tool_call_id: string; tool_name: string; args: string };
          updateToolCallArgs(data.tool_call_id, data.args);
        }

        if (event.type === "tool_result" && event.data) {
          const data = event.data as { tool_call_id: string; tool_name: string; result: string; is_error: boolean };
          setToolResult(data.tool_call_id, data.result, data.is_error);
        }

        if (event.type === "delegation_start" && event.data) {
          const data = event.data as { child_session_id: string; subagent_name: string; goal: string; context?: string };
          startDelegation(data.child_session_id, data.subagent_name, data.goal, data.context);
        }

        if (event.type === "delegation_update" && event.data) {
          const data = event.data as { child_session_id: string; status: string; progress_note?: string; elapsed_seconds?: number };
          updateDelegation(data.child_session_id, data.status, data.progress_note, data.elapsed_seconds);
        }

        if (event.type === "delegation_end" && event.data) {
          const data = event.data as { child_session_id: string; subagent_name: string; summary: string; is_error: boolean };
          endDelegation(data.child_session_id, data.summary, data.is_error);
        }

        if (event.type === "context_compression" && event.data) {
          const data = event.data as { tokens_before: number; tokens_after: number; compressed_count: number; summary_preview: string };
          appendCompressionEvent(sessionId!, data);
        }

        // ── TodoWrite task list events ──────────────────────────────
        if (event.type === "plan_created" && event.data) {
          const data = event.data as { plan_id: string; steps: Array<{ id: string; content: string; status: "pending" | "in_progress" | "completed"; level: number; activeForm?: string }> };
          setPlan({
            planId: data.plan_id,
            steps: data.steps,
            status: "executing",
          });
        }

        if (event.type === "plan_adjusted" && event.data) {
          const data = event.data as { plan_id: string; steps: Array<{ id: string; content: string; status: "pending" | "in_progress" | "completed"; level: number; activeForm?: string }> };
          setPlan({
            planId: data.plan_id,
            steps: data.steps,
            status: "executing",
          });
        }

        if (event.type === "plan_step_start" && event.data) {
          const data = event.data as { plan_id: string; step_index: number; activeForm: string };
          updatePlanStep(data.step_index, "in_progress");
        }

        if (event.type === "plan_step_complete" && event.data) {
          const data = event.data as { plan_id: string; step_index: number };
          updatePlanStep(data.step_index, "completed");
        }

        if (event.type === "plan_complete" && event.data) {
          const currentPlan = useMessageStore.getState().plan;
          if (currentPlan) {
            setPlan({ ...currentPlan, status: "completed" });
          }
        }

        if (event.type === "message_done") {
          const data = event.data as {
            message_id: string;
            streaming_message_id?: string;
            content?: string;
            role: string;
            token_count: number;
          };
          if (data.role === "assistant") {
            const state = useMessageStore.getState();
            const delta = state.streamingDelta;
            const sId = data.streaming_message_id || data.message_id;
            const thinkingBlock = state.thinkingBlocks[sId];
            collapseThinking(data.message_id);
            collapseThinking(sId);
            rekeyMessageBlocks(sId, data.message_id);
            appendMessage(sessionId!, {
              id: data.message_id,
              session_id: sessionId!,
              role: "assistant",
              // Prefer streamed delta; fall back to content from server payload
              content: delta || data.content || "",
              reasoning_content: thinkingBlock?.content || undefined,
              token_count: data.token_count,
              is_compressed: false,
              created_at: new Date().toISOString(),
            });
          }
          setStreaming(null);
          clearUserAck();
        }
      },
      () => setConnected(true),
      () => setConnected(false),
    );
    sseRef.current = manager;
    manager.connect();
    return () => {
      manager.disconnect();
      sseRef.current = null;
    };
  }, [sessionId, pushEvent, setConnected, appendDelta, setStreaming, appendMessage, startThinking, appendThinkingDelta, endThinking, collapseThinking, startToolCall, updateToolCallArgs, setToolResult, startDelegation, updateDelegation, endDelegation, rekeyMessageBlocks, appendCompressionEvent]);

  if (loading) {
    return (
      <div className="flex-1 flex items-center justify-center">
        <div className="text-center">
          <div className="w-2 h-2 rounded-full bg-[var(--color-primary)] animate-pulse-cyan mx-auto" />
          <p className="text-[var(--color-text-tertiary)] font-mono text-xs mt-3">LOADING</p>
        </div>
      </div>
    );
  }

  const sessionMessages = messages[sessionId!] || [];

  return (
    <div className="flex-1 flex flex-col min-h-0">
      <MessageFlow
        messages={sessionMessages}
        streamingDelta={streamingDelta}
        streamingMessageId={streamingMessageId}
        userAckMessage={userAckMessage}
        thinkingBlocks={thinkingBlocks}
        toolCallBlocks={toolCallBlocks}
        delegationBlocks={delegationBlocks}
        compressionEvents={compressionEvents[sessionId!] || []}
        plan={plan}
        isLoadingMore={isLoadingMore}
        onScrollNearTop={hasMore ? loadMoreHistory : undefined}
        scrollRef={scrollRef}
      />
      <ChatInputSection sessionId={sessionId!} />
    </div>
  );
}