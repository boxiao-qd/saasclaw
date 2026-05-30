import { useState, useRef, useCallback } from "react";
import { apiPost } from "@/services/api-client";
import { useMessageStore } from "@/store/message-store";
import { useSkillList } from "@/hooks/useSkillList";
import { useSkillPicker } from "@/hooks/useSkillPicker";
import { SkillPicker } from "@/components/base/SkillPicker";
import type { SkillItem } from "@/types/api-types";

interface ChatInputSectionProps {
  sessionId: string;
}

export function ChatInputSection({ sessionId }: ChatInputSectionProps) {
  const [input, setInput] = useState("");
  const composingRef = useRef(false);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const appendMessage = useMessageStore((s) => s.appendMessage);
  const clearPlan = useMessageStore((s) => s.clearPlan);
  const isStreaming = useMessageStore((s) => s.streamingMessageId !== null);

  const { skills } = useSkillList();
  const picker = useSkillPicker(skills);

  const handleSend = useCallback(async () => {
    if (!input.trim() || isStreaming) return;
    const content = input.trim();
    setInput("");
    if (textareaRef.current) textareaRef.current.style.height = "auto";

    clearPlan();
    appendMessage(sessionId, {
      id: `temp-${Date.now()}`,
      session_id: sessionId,
      role: "user",
      content,
      token_count: 0,
      is_compressed: false,
      created_at: new Date().toISOString(),
    });

    await apiPost("/messages", { session_id: sessionId, content });
  }, [input, sessionId, appendMessage, clearPlan, isStreaming]);

  const handleInput = useCallback((e: React.ChangeEvent<HTMLTextAreaElement>) => {
    const value = e.target.value;
    setInput(value);
    const el = e.target;
    el.style.height = "auto";
    el.style.height = Math.min(el.scrollHeight, 160) + "px";
    picker.onInputChange(value, el.selectionStart ?? value.length, composingRef.current);
  }, [picker]);

  const insertSkill = useCallback((skill: SkillItem) => {
    const textarea = textareaRef.current;
    if (!textarea) return;

    const cursorPos = textarea.selectionStart;
    const value = input;
    const textBefore = value.slice(0, cursorPos);

    // Safari-compatible: no lookbehind
    const match = /(^|\s)(\/\S*)$/.exec(textBefore);
    if (!match) {
      picker.close();
      return;
    }

    const slashStart = cursorPos - match[2].length;
    const insertion = `/${skill.name} `;
    const newValue = value.slice(0, slashStart) + insertion + value.slice(cursorPos);

    setInput(newValue);
    picker.close();

    // Set cursor after inserted text once DOM updates
    const newCursor = slashStart + insertion.length;
    requestAnimationFrame(() => {
      if (textareaRef.current) {
        textareaRef.current.selectionStart = newCursor;
        textareaRef.current.selectionEnd = newCursor;
        textareaRef.current.focus();
      }
    });
  }, [input, picker]);

  const hasContent = input.trim().length > 0;
  const canSend = hasContent && !isStreaming;

  return (
    <div className="px-4 pb-4 pt-2 relative" role="form" aria-label="消息输入">
      {picker.open && (
        <SkillPicker
          skills={picker.filteredSkills}
          query={picker.query}
          highlightIndex={picker.highlightIndex}
          onSelect={insertSkill}
          onClose={picker.close}
        />
      )}
      <div
        className="glass rounded-xl p-3 glow-primary flex items-end gap-3 transition-shadow"
        style={{ boxShadow: canSend ? "var(--glow-primary)" : "none" }}
      >
        <textarea
          ref={textareaRef}
          value={input}
          onChange={handleInput}
          onCompositionStart={() => { composingRef.current = true; }}
          onCompositionEnd={(e) => {
            composingRef.current = false;
            // Re-run slash detection after IME commit
            const el = e.currentTarget;
            picker.onInputChange(el.value, el.selectionStart ?? el.value.length, false);
          }}
          onKeyDown={(e) => {
            if (picker.open) {
              if (e.key === "ArrowDown") { e.preventDefault(); picker.moveDown(); return; }
              if (e.key === "ArrowUp") { e.preventDefault(); picker.moveUp(); return; }
              if (e.key === "Escape") { e.preventDefault(); picker.close(); return; }
              if (e.key === "Tab" || (e.key === "Enter" && !composingRef.current && !e.nativeEvent.isComposing)) {
                e.preventDefault();
                const selected = picker.filteredSkills[picker.highlightIndex];
                if (selected) insertSkill(selected);
                return;
              }
            }
            if (e.key === "Enter" && !e.shiftKey && !composingRef.current && !e.nativeEvent.isComposing) {
              e.preventDefault();
              handleSend();
            }
          }}
          placeholder="输入消息... Shift+Enter 换行，/ 选择技能"
          className="flex-1 bg-transparent text-[var(--color-text)] text-sm leading-relaxed
                     placeholder:text-[var(--color-text-tertiary)] resize-none outline-none
                     min-h-[24px] max-h-[160px]"
          rows={1}
          aria-label="消息输入框"
        />
        <button
          onClick={handleSend}
          disabled={!canSend}
          className={`flex items-center justify-center w-9 h-9 rounded-lg
                     transition-all duration-200
                     ${canSend
                       ? "bg-[var(--color-primary)] text-[var(--color-surface-dark)] shadow-[var(--glow-primary)] hover:bg-[var(--color-primary-hover)] active:scale-95"
                       : "bg-[var(--color-border-dim)] text-[var(--color-text-tertiary)] cursor-not-allowed"
                     }`}
          aria-label="发送"
          type="button"
        >
          <svg className="w-4 h-4" viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <path d="M3 10l7-7M10 3l7 7M10 3v14" />
          </svg>
        </button>
      </div>
    </div>
  );
}
