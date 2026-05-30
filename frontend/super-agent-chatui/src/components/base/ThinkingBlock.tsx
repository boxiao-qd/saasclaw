import { useRef, useEffect } from "react";
import type { ThinkingBlockState } from "@/store/message-store";

interface ThinkingBlockProps {
  messageId: string;
  phase: ThinkingBlockState["phase"];
  content: string;
  onToggle?: () => void;
}

const panelId = (messageId: string) => `thinking-panel-${messageId}`;

export function ThinkingBlock({ messageId, phase, content, onToggle }: ThinkingBlockProps) {
  const contentRef = useRef<HTMLDivElement>(null);

  // Auto-scroll to bottom while streaming so latest tokens stay visible
  useEffect(() => {
    if (phase === "streaming" && contentRef.current) {
      contentRef.current.scrollTop = contentRef.current.scrollHeight;
    }
  }, [content, phase]);

  if (!content && phase !== "streaming") return null;

  const isOpen = phase === "streaming" || phase === "expanded";

  return (
    <div className="my-2" data-message-id={messageId}>
      {/* ── Toggle button with neural icon ────────────────────────── */}
      <button
        onClick={onToggle}
        onKeyDown={(e) => {
          if (e.key === "Enter" || e.key === " ") {
            e.preventDefault();
            onToggle?.();
          }
        }}
        className="text-xs text-[var(--color-text-secondary)] flex items-center gap-1.5
                   hover:text-[var(--color-primary)] transition-colors group
                   focus-visible:outline-2 focus-visible:outline-offset-2
                   focus-visible:outline-[var(--color-primary)]"
        aria-expanded={phase === "expanded"}
        aria-controls={panelId(messageId)}
        aria-label={phase === "expanded" ? "收起推理" : "展开推理"}
        type="button"
      >
        {/* Neural network / brain icon */}
        <svg className="w-3.5 h-3.5 text-[var(--color-primary)] opacity-60 group-hover:opacity-100 transition-opacity" viewBox="0 0 16 16" fill="none">
          <circle cx="8" cy="3" r="1.5" stroke="currentColor" strokeWidth="1" />
          <circle cx="3" cy="8" r="1.5" stroke="currentColor" strokeWidth="1" />
          <circle cx="13" cy="8" r="1.5" stroke="currentColor" strokeWidth="1" />
          <circle cx="5" cy="13" r="1.5" stroke="currentColor" strokeWidth="1" />
          <circle cx="11" cy="13" r="1.5" stroke="currentColor" strokeWidth="1" />
          <line x1="8" y1="4.5" x2="3" y2="6.5" stroke="currentColor" strokeWidth="0.6" />
          <line x1="8" y1="4.5" x2="13" y2="6.5" stroke="currentColor" strokeWidth="0.6" />
          <line x1="3" y1="9.5" x2="5" y2="11.5" stroke="currentColor" strokeWidth="0.6" />
          <line x1="13" y1="9.5" x2="11" y2="11.5" stroke="currentColor" strokeWidth="0.6" />
          <line x1="8" y1="4.5" x2="8" y2="6" stroke="currentColor" strokeWidth="0.6" opacity="0.4" />
        </svg>
        <span className="font-mono tracking-wide">REASONING</span>
        {/* Chevron */}
        <svg
          className="w-3 h-3 transition-transform text-[var(--color-text-tertiary)] group-hover:text-[var(--color-primary)]"
          viewBox="0 0 12 12" fill="none"
          style={{ transform: isOpen ? "rotate(90deg)" : "rotate(0deg)" }}
        >
          <path d="M4 2L8 6L4 10" stroke="currentColor" strokeWidth="1.5" />
        </svg>
        {phase === "streaming" && (
          <span className="ml-1.5 inline-flex items-center gap-1">
            <span className="w-1.5 h-1.5 rounded-full bg-[var(--color-primary)] animate-pulse-cyan" />
            <span className="text-[var(--color-primary)] font-mono">streaming</span>
          </span>
        )}
      </button>

      {/* ── Collapsible content panel ────────────────────────────── */}
      <div className="collapse-wrapper" style={{ gridTemplateRows: isOpen ? "1fr" : "0fr" }}>
        <div className="collapse-inner">
          <div
            ref={contentRef}
            id={panelId(messageId)}
            aria-hidden={!isOpen}
            className={`mt-1.5 glass rounded-lg p-3 text-xs whitespace-pre-wrap text-[var(--color-text-secondary)] font-mono leading-relaxed glow-primary${phase === "streaming" ? " max-h-40 overflow-y-auto" : ""}`}
          >
            {content}
            {phase === "streaming" && (
              <span className="animate-blink text-[var(--color-primary)] ml-0.5">█</span>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}