import { useNavigate } from "react-router-dom";
import { useNotificationStore } from "@/store/notification-store";

export function NotificationBell() {
  const unreadCount = useNotificationStore((s) => s.unreadCount);
  const navigate = useNavigate();

  return (
    <button
      onClick={() => navigate("/notifications")}
      className="relative p-2 rounded-md hover:bg-[var(--color-primary-dim)] transition-colors"
      aria-label={`Notifications (${unreadCount} unread)`}
    >
      {/* Mail icon */}
      <svg className="w-5 h-5 text-[var(--color-text)]" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
        <path d="M4 4h16c1.1 0 2 .9 2 2v12c0 1.1-.9 2-2 2H4c-1.1 0-2-.9-2-2V6c0-1.1.9-2 2-2z" />
        <polyline points="22,6 12,13 2,6" />
      </svg>
      {/* Red badge dot */}
      {unreadCount > 0 && (
        <span className="absolute -top-1 -right-1 w-4 h-4 rounded-full bg-red-500 text-white text-[10px] font-bold flex items-center justify-center">
          {unreadCount > 9 ? "9+" : unreadCount}
        </span>
      )}
    </button>
  );
}