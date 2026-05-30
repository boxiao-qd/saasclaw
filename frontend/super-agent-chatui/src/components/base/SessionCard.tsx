
interface SessionCardProps {
  sessionId: string;
  title?: string;
  model?: string;
  isActive: boolean;
  onClick: () => void;
}

export function SessionCard({ sessionId, title, model, isActive, onClick }: SessionCardProps) {
  return (
    <button
      onClick={onClick}
      className={`w-full rounded-md px-3 py-2 text-sm text-left truncate transition-colors ${
        isActive
          ? "bg-primary-light text-primary"
          : "hover:bg-surface-alt text-text"
      }`}
      aria-label={`切换到对话: ${title || "未命名"}`}
      aria-current={isActive ? "page" : undefined}
    >
      <span className="block truncate">{title || "未命名对话"}</span>
      {model && <span className="block text-xs text-secondary mt-0.5">{model}</span>}
    </button>
  );
}