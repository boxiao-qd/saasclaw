import { fetchEventSource } from "@microsoft/fetch-event-source";
import type { SSEEventType, SSEEventEnvelope } from "@/types/sse-events";
import { getAccessToken } from "@/services/api-client";

const SSE_BASE = "/bx/api/v1";

export class SSEManager {
  private ctrl: AbortController | null = null;
  private sessionId: string;
  private onEvent: (event: SSEEventEnvelope) => void;
  private onOpen: () => void;
  private onError: (err: Error) => void;
  private reconnectAttempts = 0;
  private maxReconnects = 5;

  constructor(
    sessionId: string,
    onEvent: (event: SSEEventEnvelope) => void,
    onOpen: () => void,
    onError: (err: Error) => void,
  ) {
    this.sessionId = sessionId;
    this.onEvent = onEvent;
    this.onOpen = onOpen;
    this.onError = onError;
  }

  private authHeaders(): Record<string, string> {
    const token = getAccessToken();
    return token ? { Authorization: `Bearer ${token}` } : {};
  }

  async connect(): Promise<void> {
    this.ctrl = new AbortController();

    try {
      await fetchEventSource(`${SSE_BASE}/stream/${this.sessionId}`, {
        method: "GET",
        headers: this.authHeaders(),
        signal: this.ctrl.signal,
        onopen: async (response) => {
          if (response.ok) {
            this.reconnectAttempts = 0;
            this.onOpen();
          } else {
            throw new Error(`SSE connection failed: ${response.status}`);
          }
        },
        onmessage: (ev) => {
          const eventType = ev.event as SSEEventType;
          if (!eventType) return;
          try {
            const data = JSON.parse(ev.data);
            this.onEvent({
              type: eventType,
              session_id: this.sessionId,
              timestamp: Date.now() / 1000,
              data,
            });
          } catch {
            // Ignore malformed JSON
          }
        },
        onerror: (err) => {
          this.reconnectAttempts++;
          if (this.reconnectAttempts >= this.maxReconnects) {
            this.onError(err instanceof Error ? err : new Error("SSE max reconnects"));
            throw err;
          }
        },
        openWhenHidden: true,
      });
    } catch (err) {
      if (err instanceof Error && err.name !== "AbortError") {
        this.onError(err);
      }
    }
  }

  disconnect(): void {
    if (this.ctrl) {
      this.ctrl.abort();
      this.ctrl = null;
    }
  }

  async gapFill(afterMessageId: string): Promise<void> {
    const resp = await fetch(
      `${SSE_BASE}/messages/${this.sessionId}?after=${afterMessageId}&limit=50`,
      { headers: this.authHeaders() },
    );
    if (resp.ok) {
      const { messages } = await resp.json();
      for (const msg of messages) {
        this.onEvent({
          type: "message_done",
          session_id: this.sessionId,
          timestamp: Date.now() / 1000,
          data: msg,
        });
      }
    }
  }
}
