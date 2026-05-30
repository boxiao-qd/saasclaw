import { useNavigate, useLocation } from "react-router-dom";
import type { SessionItem } from "@/types/api-types";

const formatTime = (iso: string) => {
  const d = new Date(iso);
  const pad = (n: number) => String(n).padStart(2, "0");
  return `此会话由${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}创建`;
};

interface ChatSidebarProps {
  sessions: SessionItem[];
  activeSessionId: string | null;
  onSelect: (session: SessionItem) => void;
  onNewChat: () => void;
}

const NAV_ITEMS = [
  { label: "SKILLS", path: "/skills" },
  { label: "SUBAGENTS", path: "/subagents" },
  { label: "MY FILES", path: "/files" },
  { label: "CRON", path: "/cron" },
  { label: "NOTIFICATIONS", path: "/notifications" },
] as const;

export function ChatSidebar({ sessions, activeSessionId, onSelect, onNewChat }: ChatSidebarProps) {
  const navigate = useNavigate();
  const location = useLocation();
  return (
    <nav className="flex flex-col h-full" aria-label="会话侧栏">
      {/* ── New chat button ─────────────────────────────────────────── */}
      <div className="p-2">
        <button
          onClick={onNewChat}
          className="w-full rounded-md border border-[var(--color-border)] px-3 py-2 text-sm
                     text-[var(--color-primary)] font-mono
                     hover:bg-[var(--color-primary-dim)] hover:border-[var(--color-primary)]
                     transition-colors"
          aria-label="新建对话"
        >
          + NEW SESSION
        </button>
      </div>

      {/* ── Session list ─────────────────────────────────────────────── */}
      <ul className="flex-1 overflow-y-auto p-2 space-y-2">
        {sessions.length === 0 && (
          <li className="text-[var(--color-text-tertiary)] text-sm text-center py-8 font-mono">
            NO SESSIONS
          </li>
        )}
        {sessions.map((s) => (
          <li key={s.session_id}>
            <div
              className={`rounded-lg border p-3 transition-colors cursor-pointer ${
                s.session_id === activeSessionId
                  ? "bg-[var(--color-primary-dim)] border-[var(--color-primary)] glow-primary"
                  : "bg-[var(--color-surface)] border-[var(--color-border-dim)] hover:border-[var(--color-border)] hover:bg-[var(--color-primary-dim)]"
              }`}
              onClick={() => onSelect(s)}
              role="button"
              tabIndex={0}
              onKeyDown={(e) => { if (e.key === "Enter") onSelect(s); }}
              aria-label={`切换到对话: ${s.title || "未命名"}`}
            >
              <div className="flex items-center gap-2">
                <span className={`inline-block w-2 h-2 rounded-full shrink-0 ${
                  s.session_id === activeSessionId ? 'bg-[var(--color-primary)]' : 'bg-[var(--color-text-tertiary)]'
                }`} />
                <span className="truncate text-sm font-medium">{s.title || "UNTITLED"}</span>
              </div>
              <div className="text-[0.6rem] text-[var(--color-text-tertiary)] mt-2 font-mono">
                {formatTime(s.created_at)}
              </div>
            </div>
          </li>
        ))}
      </ul>

      {/* ── Nav links ────────────────────────────────────────────────── */}
      <div className="border-t border-[var(--color-border-dim)] p-2 space-y-0.5">
        {NAV_ITEMS.map(({ label, path }) => {
          const active = location.pathname.startsWith(path);
          return (
            <button
              key={path}
              onClick={() => navigate(path)}
              className={`w-full text-left rounded px-3 py-1.5 text-xs font-mono transition-colors ${
                active
                  ? "bg-[var(--color-primary-dim)] text-[var(--color-primary)]"
                  : "text-[var(--color-text-tertiary)] hover:text-[var(--color-text)] hover:bg-[var(--color-primary-dim)]"
              }`}
              aria-label={label}
              aria-current={active ? "page" : undefined}
            >
              {label}
            </button>
          );
        })}
      </div>

      {/* ── Bottom branding ─────────────────────────────────────────── */}
      <div className="p-3 text-[0.65rem] text-[var(--color-text-tertiary)] font-mono text-center border-t border-[var(--color-border-dim)]">
        SUPER-AGENT v0.1
      </div>
    </nav>
  );
}