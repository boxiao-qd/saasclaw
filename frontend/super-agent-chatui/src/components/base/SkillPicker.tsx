import { useEffect, useRef } from "react";
import type { SkillItem } from "@/types/api-types";

interface SkillPickerProps {
  skills: SkillItem[];
  query: string;
  highlightIndex: number;
  onSelect: (skill: SkillItem) => void;
  onClose: () => void;
}

function highlightMatch(text: string, query: string): React.ReactNode {
  if (!query) return text;
  const idx = text.toLowerCase().indexOf(query.toLowerCase());
  if (idx === -1) return text;
  return (
    <>
      {text.slice(0, idx)}
      <span className="text-[var(--color-primary)]">{text.slice(idx, idx + query.length)}</span>
      {text.slice(idx + query.length)}
    </>
  );
}

export function SkillPicker({ skills, query, highlightIndex, onSelect, onClose }: SkillPickerProps) {
  const listRef = useRef<HTMLDivElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);

  // Scroll highlighted item into view
  useEffect(() => {
    const list = listRef.current;
    if (!list) return;
    const item = list.children[highlightIndex] as HTMLElement | undefined;
    item?.scrollIntoView({ block: "nearest" });
  }, [highlightIndex]);

  // Close on outside click
  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
        onClose();
      }
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, [onClose]);

  return (
    <div
      ref={containerRef}
      className="absolute bottom-full left-0 right-0 mb-2 z-50 glass rounded-xl overflow-hidden glow-primary"
      role="listbox"
      aria-label="技能选择"
    >
      <div ref={listRef} className="max-h-60 overflow-y-auto">
        {skills.length === 0 ? (
          <div className="px-4 py-3 text-xs text-[var(--color-text-tertiary)] font-mono">
            无匹配技能
          </div>
        ) : (
          skills.map((skill, i) => (
            <div
              key={skill.id}
              role="option"
              aria-selected={i === highlightIndex}
              onMouseDown={(e) => {
                e.preventDefault(); // prevent textarea blur
                onSelect(skill);
              }}
              className={`flex items-start gap-3 px-4 py-2.5 cursor-pointer transition-colors text-xs ${
                i === highlightIndex
                  ? "bg-[var(--color-primary)]/10 border-l-2 border-[var(--color-primary)]"
                  : "border-l-2 border-transparent hover:bg-[var(--color-primary)]/5"
              }`}
            >
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2">
                  <span className="text-[var(--color-text-primary)] font-medium truncate">
                    {highlightMatch(skill.name, query)}
                  </span>
                  {skill.source === "sys_infra" && (
                    <span className="shrink-0 font-mono text-[10px] px-1.5 py-0.5 rounded bg-[var(--color-primary)]/10 text-[var(--color-primary)]">
                      系统
                    </span>
                  )}
                </div>
                {skill.header_description && (
                  <div className="text-[var(--color-text-tertiary)] truncate mt-0.5">
                    {highlightMatch(skill.header_description, query)}
                  </div>
                )}
              </div>
            </div>
          ))
        )}
      </div>
      <div className="px-4 py-1.5 border-t border-[var(--color-border-dim)]">
        <span className="font-mono text-[10px] text-[var(--color-text-tertiary)]">
          ↑↓ 导航 &nbsp; Enter 确认 &nbsp; Esc 关闭
        </span>
      </div>
    </div>
  );
}
