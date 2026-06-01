import { memo, useCallback, useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import rehypeHighlight from "rehype-highlight";
import "highlight.js/styles/atom-one-dark.css";
import type { MessageItem } from "@/types/api-types";
import type { ThinkingBlockState, ToolCallBlockState } from "@/store/message-store";
import { useMessageStore } from "@/store/message-store";
import { ThinkingBlock } from "@/components/base/ThinkingBlock";
import { ToolCallBlock } from "@/components/base/ToolCallBlock";

const remarkPlugins = [remarkGfm];
const rehypePlugins = [rehypeHighlight];

interface MessageBubbleProps {
  message: MessageItem;
  thinkingBlock?: ThinkingBlockState;
  toolCallBlocks?: ToolCallBlockState[];
}

export const MessageBubble = memo(function MessageBubble({ message, thinkingBlock, toolCallBlocks }: MessageBubbleProps) {
  const isUser = message.role === "user";
  const isTool = message.role === "tool";
  const toggleThinking = useMessageStore((s) => s.toggleThinking);
  const toggleToolCall = useMessageStore((s) => s.toggleToolCall);

  const [staticThinkingExpanded, setStaticThinkingExpanded] = useState(false);

  const effectiveThinkingBlock = thinkingBlock ?? (
    message.reasoning_content
      ? {
          messageId: message.id,
          phase: staticThinkingExpanded ? ("expanded" as const) : ("collapsed" as const),
          content: message.reasoning_content,
        }
      : undefined
  );

  const handleThinkingToggle = useCallback(() => {
    if (thinkingBlock) {
      toggleThinking(thinkingBlock.messageId);
    } else {
      setStaticThinkingExpanded((v) => !v);
    }
  }, [thinkingBlock, toggleThinking]);

  /* ── User message: bold accent bubble ──────────────────────────── */
  if (isUser) {
    return (
      <div className="flex justify-end" role="article" aria-label="用户消息">
        <div className="rounded-lg px-4 py-3 max-w-[80%] md:max-w-[80%] text-sm
                       bg-[var(--color-primary)] text-[var(--color-surface-dark)]
                       shadow-[var(--glow-primary)]">
          <p className="leading-relaxed">{message.content}</p>
        </div>
      </div>
    );
  }

  /* ── Tool message: dim mono card ────────────────────────────────── */
  if (isTool) {
    return (
      <div className="flex justify-start" role="article" aria-label="工具消息">
        <div className="rounded-lg px-4 py-3 max-w-[80%] text-xs font-mono
                       bg-[var(--color-surface-dark)] text-[var(--color-text-secondary)]
                       border border-[var(--color-border-dim)]">
          <p>{message.content}</p>
        </div>
      </div>
    );
  }

  /* ── Assistant message: glass card with markdown ─────────────────── */
  return (
    <div className="flex justify-start" role="article" aria-label="助手消息">
      <div className="rounded-lg px-4 py-3 max-w-[95%] md:max-w-[85%] text-sm glass glow-primary">
        {/* Thinking block */}
        {effectiveThinkingBlock && (
          <ThinkingBlock
            messageId={effectiveThinkingBlock.messageId}
            phase={effectiveThinkingBlock.phase}
            content={effectiveThinkingBlock.content}
            onToggle={handleThinkingToggle}
          />
        )}

        {/* Tool call blocks */}
        {toolCallBlocks && toolCallBlocks.length > 0 && (
          <div className="space-y-1">
            {toolCallBlocks.map((block) => (
              <ToolCallBlock
                key={block.toolCallId}
                toolCallId={block.toolCallId}
                toolName={block.toolName}
                phase={block.phase}
                args={block.args}
                result={block.result}
                isError={block.isError}
                onToggle={() => toggleToolCall(block.toolCallId)}
              />
            ))}
          </div>
        )}

        {/* Markdown content */}
        {message.content && (
          <div className="md-content">
            <ReactMarkdown remarkPlugins={remarkPlugins} rehypePlugins={rehypePlugins}>
              {message.content}
            </ReactMarkdown>
          </div>
        )}
      </div>
    </div>
  );
});