import { useEffect, useRef } from "react";
import { fetchEventSource } from "@microsoft/fetch-event-source";
import { getAccessToken } from "@/services/api-client";
import { useNotificationStore } from "@/store/notification-store";

const MAX_RECONNECT_DELAY_MS = 30_000;

/**
 * Global SSE listener for notification events.
 * Connects once on mount, stays connected across page navigations.
 * Reconnects on error with exponential backoff up to 30s.
 */
export function NotificationSSEListener() {
  const ctrlRef = useRef<AbortController | null>(null);
  const retryDelayRef = useRef(1_000);
  const incrementUnread = useNotificationStore((s) => s.incrementUnread);

  useEffect(() => {
    const token = getAccessToken();
    if (!token) return;

    const ctrl = new AbortController();
    ctrlRef.current = ctrl;
    let running = true;

    fetchEventSource("/bx/api/v1/stream/notifications", {
      method: "GET",
      headers: { Authorization: `Bearer ${token}` },
      signal: ctrl.signal,
      openWhenHidden: true,
      onmessage: (ev) => {
        retryDelayRef.current = 1_000;
        if (ev.event === "notification_new") {
          incrementUnread();
        }
      },
      onerror: (err) => {
        if (!running) {
          throw err; // stop reconnecting after unmount
        }
        retryDelayRef.current = Math.min(retryDelayRef.current * 2, MAX_RECONNECT_DELAY_MS);
        return retryDelayRef.current;
      },
    });

    return () => {
      running = false;
      ctrl.abort();
    };
  }, [incrementUnread]);

  return null;
}
