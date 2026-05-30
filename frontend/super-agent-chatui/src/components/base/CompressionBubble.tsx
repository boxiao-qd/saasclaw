import { useState } from "react";

interface CompressionBubbleProps {
  tokensBefore?: number;
  tokensAfter?: number;
  compressedCount?: number;
  summaryPreview?: string;
}

export function CompressionBubble({ tokensBefore, tokensAfter, compressedCount, summaryPreview }: CompressionBubbleProps) {
  const [expanded, setExpanded] = useState(false);

  return (
    <div className="flex justify-center my-3">
      <div className="max-w-lg w-full mx-4">
        <div className="border border-[var(--color-primary)]/30 rounded bg-[var(--color-primary)]/5 px-4 py-2.5">
          <div className="flex items-center gap-2">
            <svg
              className="w-3.5 h-3.5 text-[var(--color-primary)] shrink-0"
              viewBox="0 0 16 16"
              fill="currentColor"
              aria-hidden="true"
            >
              <path d="M8 1a7 7 0 1 0 0 14A7 7 0 0 0 8 1zm0 1.5a5.5 5.5 0 1 1 0 11 5.5 5.5 0 0 1 0-11zm0 2a.75.75 0 0 0-.75.75v3.19l-1.72 1.72a.75.75 0 1 0 1.06 1.06l2-2A.75.75 0 0 0 8.75 9.5V5.25A.75.75 0 0 0 8 4.5z"/>
            </svg>
            <span className="text-[var(--color-primary)] font-mono text-xs tracking-wide">
              上下文已压缩
              {tokensBefore != null && tokensAfter != null && (
                <span className="text-[var(--color-text-secondary)] ml-2">
                  {tokensBefore.toLocaleString()} → {tokensAfter.toLocaleString()} tokens
                  {compressedCount != null && `，${compressedCount} 条消息已归纳`}
                </span>
              )}
            </span>
            {summaryPreview && (
              <button
                onClick={() => setExpanded((e) => !e)}
                className="ml-auto text-[var(--color-text-tertiary)] hover:text-[var(--color-primary)] transition-colors text-xs font-mono"
                aria-expanded={expanded}
                aria-label={expanded ? "收起摘要" : "展开摘要"}
              >
                {expanded ? "收起" : "详情"}
              </button>
            )}
          </div>
          {expanded && summaryPreview && (
            <p className="mt-2 text-[var(--color-text-secondary)] text-xs font-mono leading-relaxed border-t border-[var(--color-primary)]/20 pt-2">
              {summaryPreview}
            </p>
          )}
        </div>
      </div>
    </div>
  );
}
