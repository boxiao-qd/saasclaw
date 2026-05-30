import { useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { useAuthStore } from "@/store/auth-store";
import { useSessionStore } from "@/store/session-store";
import { useUIStore } from "@/store/ui-store";
import { useNotificationStore } from "@/store/notification-store";
import { useSessions } from "@/hooks/useSessions";
import { ChatSidebar } from "@/components/section/ChatSidebar";
import { SSEStatusBar } from "@/components/section/SSEStatusBar";
import { NotificationBell } from "@/components/ui/NotificationBell";
import { NotificationSSEListener } from "@/components/ui/NotificationSSEListener";
import type { SessionItem } from "@/types/api-types";

interface ChatLayoutProps {
  children: React.ReactNode;
}

export function ChatLayout({ children }: ChatLayoutProps) {
  const navigate = useNavigate();
  const { sidebarOpen, setSidebarOpen } = useUIStore();
  const { sessions, setActiveSession, activeSessionId } = useSessionStore();
  const fetchUnreadCount = useNotificationStore((s) => s.fetchUnreadCount);
  const { username, logout } = useAuthStore();

  const handleLogout = () => {
    logout();
    navigate("/login", { replace: true });
  };

  // Trigger session list fetch on mount
  useSessions();

  useEffect(() => {
    fetchUnreadCount();
    // Auto-hide sidebar on small screens
    const mql = window.matchMedia("(max-width: 768px)");
    setSidebarOpen(!mql.matches);
    const handler = (e: MediaQueryListEvent) => setSidebarOpen(!e.matches);
    mql.addEventListener("change", handler);
    return () => mql.removeEventListener("change", handler);
  }, []);

  const handleSelectSession = (session: SessionItem) => {
    setActiveSession(session.session_id);
    navigate(`/chat/${session.session_id}`);
    // Auto-close sidebar on mobile after selection
    if (window.innerWidth < 768) setSidebarOpen(false);
  };

  return (
    <div className="flex h-screen bg-[var(--color-surface)]">
      {/* ── Mobile sidebar overlay ─────────────────────────────────── */}
      {sidebarOpen && (
        <div
          className="fixed inset-0 bg-black/50 z-40 md:hidden"
          onClick={() => setSidebarOpen(false)}
        />
      )}

      {/* ── Sidebar ────────────────────────────────────────────────── */}
      <aside
        className={`bg-[var(--color-surface-dark)] border-r border-[var(--color-border-dim)]
                     flex flex-col transition-transform duration-200 z-50
                     ${sidebarOpen ? "translate-x-0" : "-translate-x-full"}
                     fixed md:relative md:translate-x-0
                     w-[var(--sidebar-width)] h-full`}
      >
        <ChatSidebar
          sessions={sessions}
          activeSessionId={useSessionStore.getState().activeSessionId}
          onSelect={handleSelectSession}
          onNewChat={() => { setActiveSession(null); navigate("/chat/new"); }}
        />
      </aside>

      <main className="flex-1 flex flex-col min-w-0 min-h-0 bg-[var(--color-surface)]">
        {/* ── Top bar with menu toggle ─────────────────────────────── */}
        <div className="flex items-center justify-between h-8 px-2 border-b border-[var(--color-border-dim)] md:hidden">
          <div className="flex items-center">
            <button
              onClick={() => setSidebarOpen(!sidebarOpen)}
              className="p-1.5 text-[var(--color-primary)] hover:bg-[var(--color-primary-dim)] rounded-md transition-colors"
              aria-label="Toggle sidebar"
            >
              <svg className="w-4 h-4" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5">
                <path d="M2 4h12M2 8h12M2 12h12" strokeLinecap="round" />
              </svg>
            </button>
            <span className="ml-2 text-xs font-mono text-[var(--color-text-tertiary)]">SUPER-AGENT</span>
          </div>
          <div className="flex items-center gap-2">
            <button
              onClick={handleLogout}
              className="text-xs font-mono text-[var(--color-text-tertiary)] hover:text-[var(--color-primary)] transition-colors"
            >
              退出
            </button>
            <NotificationBell />
          </div>
        </div>
        {activeSessionId && <SSEStatusBar />}
        <NotificationSSEListener />
        <div className="hidden md:flex items-center justify-end gap-3 px-2 py-0.5">
          <span className="text-xs font-mono text-[var(--color-text-tertiary)]">{username}</span>
          <button
            onClick={handleLogout}
            className="text-xs font-mono text-[var(--color-text-tertiary)] hover:text-[var(--color-primary)] transition-colors"
          >
            退出
          </button>
          <NotificationBell />
        </div>
        {children}
      </main>
    </div>
  );
}