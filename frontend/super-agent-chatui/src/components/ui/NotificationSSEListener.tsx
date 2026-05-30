import { useEffect, useRef } from "react";
import { fetchEventSource } from "@microsoft/fetch-event-source";
import { getAccessToken } from "@/services/api-client";
import { useNotificationStore } from "@/store/notification-store";

/**
 * Global SSE listener for notification events.
 * Connects once on mount, stays connected across page navigations.
 * On "notification_new" event → increments the unread badge counter.
 */
export function NotificationSSEListener() {
  const ctrlRef = useRef<AbortController | null>(null);
  const incrementUnread = useNotificationStore((s) => s.incrementUnread);

  useEffect(() => {
    const token = getAccessToken();
    if (!token) return;

    const ctrl = new AbortController();
    ctrlRef.current = ctrl;

    fetchEventSource("/bx/api/v1/stream/notifications", {
      method: "GET",
      headers: { Authorization: `Bearer ${token}` },
      signal: ctrl.signal,
      onmessage: (ev) => {
        if (ev.event === "notification_new") {
          incrementUnread();
        }
      },
      onerror: () => {
        // auto-reconnect, silent
      },
      openWhenHidden: true,
    });

    return () => ctrl.abort();
  }, [incrementUnread]);

  return null; // no UI, just a persistent connection
}