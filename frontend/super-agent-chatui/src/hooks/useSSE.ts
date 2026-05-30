
import { useEffect, useRef, useCallback } from "react";
import { SSEManager } from "@/services/sse-manager";
import { useSSEStore } from "@/store/sse-store";
import { useMessageStore } from "@/store/message-store";
import { isTextDelta, isMessageDone } from "@/services/event-mapper";
import type { SSEEventEnvelope } from "@/types/sse-events";

interface UseSSEOptions {
  sessionId: string;
}

interface UseSSEReturn {
  connected: boolean;
  reconnecting: boolean;
  errorCount: number;
}

export function useSSE({ sessionId }: UseSSEOptions): UseSSEReturn {
  const managerRef = useRef<SSEManager | null>(null);
  const sessionIdRef = useRef(sessionId);

  const setConnected = useSSEStore((s) => s.setConnected);
  const setReconnecting = useSSEStore((s) => s.setReconnecting);
  const pushEvent = useSSEStore((s) => s.pushEvent);
  const incrementError = useSSEStore((s) => s.incrementError);

  const setStreaming = useMessageStore((s) => s.setStreaming);
  const appendDelta = useMessageStore((s) => s.appendDelta);
  const resetDelta = useMessageStore((s) => s.resetDelta);
  const appendMessage = useMessageStore((s) => s.appendMessage);

  const handleEvent = useCallback(
    (event: SSEEventEnvelope) => {
      pushEvent(event);

      const { data } = event;

      if (event.type === "text_delta" && isTextDelta(data)) {
        setStreaming(data.message_id);
        appendDelta(data.delta);
      }

      if (event.type === "message_done" && isMessageDone(data)) {
        resetDelta();
        setStreaming(null);
        appendMessage(sessionIdRef.current, {
          id: data.message_id,
          session_id: sessionIdRef.current,
          role: data.role,
          token_count: data.token_count,
          is_compressed: false,
          created_at: new Date().toISOString(),
        });
      }
    },
    [pushEvent, setStreaming, appendDelta, resetDelta, appendMessage],
  );

  const handleOpen = useCallback(() => {
    setConnected(true);
    setReconnecting(false);
  }, [setConnected, setReconnecting]);

  const handleError = useCallback(
    (err: Error) => {
      incrementError();
      if (err.message.includes("max reconnects")) {
        setConnected(false);
        setReconnecting(false);
      }
    },
    [incrementError, setConnected, setReconnecting],
  );

  useEffect(() => {
    sessionIdRef.current = sessionId;
  }, [sessionId]);

  useEffect(() => {
    const manager = new SSEManager(
      sessionId,
      handleEvent,
      handleOpen,
      handleError,
    );
    managerRef.current = manager;
    manager.connect();

    return () => {
      manager.disconnect();
      managerRef.current = null;
      setConnected(false);
      setReconnecting(false);
    };
  }, [sessionId, handleEvent, handleOpen, handleError, setConnected, setReconnecting]);

  const connected = useSSEStore((s) => s.connected);
  const reconnecting = useSSEStore((s) => s.reconnecting);
  const errorCount = useSSEStore((s) => s.errorCount);

  return { connected, reconnecting, errorCount };
}
