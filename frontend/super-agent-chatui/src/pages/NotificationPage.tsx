import { useEffect } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import rehypeHighlight from "rehype-highlight";
import { useNotificationStore } from "@/store/notification-store";

export function NotificationPage() {
  const { notifications, loading, selectedId, fetchNotifications, markRead, markAllRead, deleteNotification, select } = useNotificationStore();

  useEffect(() => {
    fetchNotifications();
  }, []);

  const selectedNotif = notifications.find((n) => n.id === selectedId);

  return (
    <div className="flex h-full bg-[var(--color-surface)]">
      {/* ── List panel ───────────────────────────────────────────────── */}
      <div className="w-[320px] md:w-[360px] border-r border-[var(--color-border-dim)] flex flex-col">
        {/* Header */}
        <div className="flex items-center justify-between p-4 border-b border-[var(--color-border-dim)]">
          <h2 className="text-lg font-mono font-semibold text-[var(--color-text)]">
            Notifications
          </h2>
          {notifications.some((n) => n.is_read === 0) && (
            <button
              onClick={markAllRead}
              className="text-xs text-[var(--color-primary)] hover:underline font-mono"
            >
              Mark all read
            </button>
          )}
        </div>

        {/* List */}
        <div className="flex-1 overflow-y-auto">
          {loading && <p className="p-4 text-sm text-[var(--color-text-dim)] font-mono">Loading...</p>}
          {!loading && notifications.length === 0 && (
            <p className="p-4 text-sm text-[var(--color-text-dim)] font-mono">No notifications yet</p>
          )}
          {notifications.map((n) => (
            <button
              key={n.id}
              onClick={() => {
                select(n.id);
                if (n.is_read === 0) markRead(n.id);
              }}
              className={`w-full text-left p-3 border-b border-[var(--color-border-dim)]
                         hover:bg-[var(--color-surface-dark)] transition-colors
                         ${selectedId === n.id ? "bg-[var(--color-primary-dim)]" : ""}
                         ${n.is_read === 0 ? "font-semibold" : "opacity-70"}`}
            >
              <div className="flex items-start gap-2">
                {/* Unread dot */}
                {n.is_read === 0 && (
                  <span className="w-2 h-2 mt-1.5 rounded-full bg-[var(--color-primary)] shrink-0" />
                )}
                <div className="flex-1 min-w-0">
                  <p className="text-sm font-mono text-[var(--color-text)] truncate">{n.title}</p>
                  <p className="text-xs text-[var(--color-text-dim)] font-mono mt-0.5">
                    {n.source === "cron" ? "Cron" : n.source} &middot; {new Date(n.created_at).toLocaleString()}
                  </p>
                </div>
              </div>
            </button>
          ))}
        </div>
      </div>

      {/* ── Detail panel ───────────────────────────────────────────── */}
      <div className="flex-1 flex flex-col">
        {selectedNotif ? (
          <>
            <div className="flex items-center justify-between p-4 border-b border-[var(--color-border-dim)]">
              <h3 className="text-base font-mono font-semibold text-[var(--color-text)]">
                {selectedNotif.title}
              </h3>
              <button
                onClick={() => deleteNotification(selectedNotif.id)}
                className="text-xs text-red-400 hover:text-red-300 font-mono"
              >
                Delete
              </button>
            </div>
            <div className="flex-1 overflow-y-auto p-4">
              <div className="text-sm text-[var(--color-text)] leading-relaxed prose prose-sm prose-invert max-w-none">
                <ReactMarkdown remarkPlugins={[remarkGfm]} rehypePlugins={[rehypeHighlight]}>
                  {selectedNotif.content}
                </ReactMarkdown>
              </div>
            </div>
          </>
        ) : (
          <div className="flex-1 flex items-center justify-center">
            <p className="text-sm text-[var(--color-text-dim)] font-mono">Select a notification to view</p>
          </div>
        )}
      </div>
    </div>
  );
}