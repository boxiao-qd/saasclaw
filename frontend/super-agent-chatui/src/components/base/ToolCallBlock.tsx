import { useRef, useEffect } from "react";
import type { ToolCallBlockState } from "@/store/message-store";

interface ToolCallBlockProps {
  toolCallId: string;
  toolName: string;
  phase: ToolCallBlockState["phase"];
  args?: string;
  result?: string;
  isError?: boolean;
  onToggle?: () => void;
}

const panelId = (toolCallId: string) => `toolcall-panel-${toolCallId}`;

/* ── Tool category icon mapping ──────────────────────────────────── */
function ToolIcon({ name }: { name: string }) {
  const category = (() => {
    if (["terminal", "process", "code_execute"].includes(name)) return "terminal";
    if (["file_read", "file_write", "file_search", "patch"].includes(name)) return "file";
    if (["web_search", "web_fetch"].includes(name)) return "web";
    if (["memory_query", "memory_store", "memory_delete"].includes(name)) return "memory";
    if (["delegate_task"].includes(name)) return "delegation";
    if (["todo"].includes(name)) return "todo";
    if (["clarify"].includes(name)) return "clarify";
    if (["session_search"].includes(name)) return "search";
    if (["skills_list", "skill_view", "skill_manage"].includes(name)) return "skill";
    return "default";
  })();

  const iconPaths: Record<string, string> = {
    terminal: "M4 3h8M4 7h8M4 11h4",
    file: "M4 2h6l2 2v10H4V2zM10 2v2h2",
    web: "M2 8a6 6 0 0 1 12 0 6 6 0 0 1-12 0M8 2v14M2 8h14",
    memory: "M3 4h10v8H3V4zM6 6v4M9 6v4",
    delegation: "M4 4l8 4-8 4V4z",
    todo: "M3 6l2 2 4-4M3 10l2 2 4-4",
    clarify: "M8 1v2M8 13v2M1 8h2M13 8h2M4 4l1.5 1.5M11.5 4l1.5 1.5M4 12l1.5-1.5M11.5 12l-1.5-1.5",
    search: "M2 8a5 5 0 1 0 10 0 5 5 0 0 0-10 0M13 13l-3-3",
    skill: "M4 2v12l4-3 4 3V2",
    default: "M4 4h8v8H4V4z",
  };

  return (
    <svg className="w-3.5 h-3.5" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.2" strokeLinecap="round" strokeLinejoin="round">
      <path d={iconPaths[category] || iconPaths.default} />
    </svg>
  );
}

/* ── Tool name display with category color ──────────────────────── */
function toolAccent(name: string): string {
  if (["terminal", "process", "code_execute"].includes(name)) return "text-[var(--color-success)]";
  if (["file_read", "file_write", "file_search", "patch"].includes(name)) return "text-[var(--color-warning)]";
  if (["web_search", "web_fetch"].includes(name)) return "text-[#7c83ff]";
  if (["memory_query", "memory_store", "memory_delete"].includes(name)) return "text-[var(--color-primary)]";
  if (["delegate_task"].includes(name)) return "text-[var(--color-warning)]";
  return "text-[var(--color-primary)]";
}

/* ── Human-readable tool display name ─────────────────────────────── */
const TOOL_DISPLAY_NAMES: Record<string, string> = {
  terminal: "终端执行",
  process: "进程管理",
  code_execute: "代码执行",
  file_read: "文件读取",
  file_write: "文件写入",
  file_search: "文件搜索",
  patch: "文件修补",
  web_search: "网络搜索",
  web_fetch: "网页抓取",
  memory_query: "记忆查询",
  memory_store: "记忆存储",
  memory_delete: "记忆删除",
  delegate_task: "任务委派",
  todo: "任务清单",
  clarify: "追问澄清",
  session_search: "会话搜索",
  skills_list: "技能列表",
  skill_view: "技能查看",
  skill_manage: "技能管理",
};

export function ToolCallBlock({
  toolCallId,
  toolName,
  phase,
  args,
  result,
  isError,
  onToggle,
}: ToolCallBlockProps) {
  const argsRef = useRef<HTMLPreElement>(null);

  // Auto-scroll args to bottom while tool is executing
  useEffect(() => {
    if (phase === "loading" && argsRef.current) {
      argsRef.current.scrollTop = argsRef.current.scrollHeight;
    }
  }, [args, phase]);

  // During loading: always expanded to show live args stream
  // After completion: collapsed by default, user can toggle
  const isExpanded = phase === "loading" || phase === "completed_expanded" || phase === "error";
  const isCompleted = phase === "completed_collapsed" || phase === "completed_expanded";

  /* ── Outer container ────────────────────────────────────────────── */
  const containerClass = (() => {
    if (phase === "error") return "border-[var(--color-error)] glow-error";
    if (phase === "loading") return "border-gradient";
    if (isCompleted && !isError) return "border-[var(--color-success)] glow-success";
    return "border-[var(--color-border)]";
  })();

  return (
    <div
      className={`my-2 rounded-lg border ${containerClass} glass p-2.5`}
      data-tool-call-id={toolCallId}
    >
      {/* ── Header row ─────────────────────────────────────────────── */}
      <div className="flex items-center gap-2 text-xs">

        {/* Status icon */}
        {phase === "loading" && (
          <span className="relative flex w-3.5 h-3.5">
            <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-[var(--color-primary)] opacity-30" />
            <span className="relative inline-flex rounded-full h-3.5 w-3.5 bg-[var(--color-primary)]" />
          </span>
        )}
        {isCompleted && !isError && (
          <span className="inline-flex items-center justify-center w-3.5 h-3.5 rounded-full bg-[var(--color-success)]/20 text-[var(--color-success)]">
            <svg className="w-2.5 h-2.5" viewBox="0 0 12 12" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M2 6l3 3 5-5" strokeLinecap="round" strokeLinejoin="round" />
            </svg>
          </span>
        )}
        {isError && (
          <span className="inline-flex items-center justify-center w-3.5 h-3.5 rounded-full bg-[var(--color-error)]/20 text-[var(--color-error)]">
            <svg className="w-2.5 h-2.5" viewBox="0 0 12 12" fill="none" stroke="currentColor" strokeWidth="2.5">
              <path d="M6 3v4M6 8.5v0.5" strokeLinecap="round" />
            </svg>
          </span>
        )}

        {/* Tool icon + name */}
        <span className={toolAccent(toolName)}>
          <ToolIcon name={toolName} />
        </span>
        <span className={`font-mono font-semibold tracking-wide ${toolAccent(toolName)}`}>
          {TOOL_DISPLAY_NAMES[toolName] || toolName}
        </span>

        {/* Status label */}
        {phase === "loading" && (
          <span className="text-[var(--color-text-tertiary)] font-mono text-[0.7rem] animate-pulse-cyan">
            executing
          </span>
        )}
        {isCompleted && !isError && (
          <span className="text-[var(--color-success)] font-mono text-[0.7rem]">
            done
          </span>
        )}
        {isError && (
          <span className="text-[var(--color-error)] font-mono text-[0.7rem]">
            error
          </span>
        )}

        {/* Expand toggle — only shown after completion */}
        {(isCompleted || phase === "error") && (
          <button
            onClick={onToggle}
            onKeyDown={(e) => {
              if (e.key === "Enter" || e.key === " ") { e.preventDefault(); onToggle?.(); }
            }}
            className="ml-auto text-[var(--color-text-tertiary)] hover:text-[var(--color-primary)]
                       focus-visible:outline-2 focus-visible:outline-offset-2
                       focus-visible:outline-[var(--color-primary)] transition-colors"
            aria-expanded={isExpanded}
            aria-controls={panelId(toolCallId)}
            aria-label={isExpanded ? "收起详情" : "展开详情"}
            type="button"
          >
            <svg
              className="w-3 h-3 transition-transform"
              viewBox="0 0 12 12" fill="none"
              style={{ transform: isExpanded ? "rotate(90deg)" : "rotate(0deg)" }}
            >
              <path d="M4 2L8 6L4 10" stroke="currentColor" strokeWidth="1.5" />
            </svg>
          </button>
        )}
      </div>

      {/* ── Collapsible detail panel ────────────────────────────────── */}
      <div className="collapse-wrapper" style={{ gridTemplateRows: isExpanded ? "1fr" : "0fr" }}>
        <div className="collapse-inner">
          <div id={panelId(toolCallId)} aria-hidden={!isExpanded} className="mt-2 space-y-2">

            {/* Args — live stream during loading, static after completion */}
            {(args || phase === "loading") && (
              <div>
                <div className="text-[0.7rem] font-mono text-[var(--color-text-tertiary)] mb-1 flex items-center gap-1">
                  <span className="text-[var(--color-warning)]">&#9670;</span> ARGS
                </div>
                <pre
                  ref={argsRef}
                  className={`text-xs font-mono whitespace-pre-wrap text-[var(--color-text-secondary)] bg-[var(--color-surface-dark)] rounded-md p-2 border border-[var(--color-border-dim)]${phase === "loading" ? " max-h-32 overflow-y-auto overflow-x-auto" : " overflow-x-auto"}`}
                >
                  {args || ""}
                  {phase === "loading" && (
                    <span className="animate-blink text-[var(--color-primary)] ml-0.5">█</span>
                  )}
                </pre>
              </div>
            )}

            {/* Result — only available after completion */}
            {result && (
              <div>
                <div className="text-[0.7rem] font-mono text-[var(--color-text-tertiary)] mb-1 flex items-center gap-1">
                  <span className={isError ? "text-[var(--color-error)]" : "text-[var(--color-success)]"}>
                    &#9670;
                  </span>
                  {isError ? "ERROR" : "RESULT"}
                </div>
                <pre className={`text-xs font-mono whitespace-pre-wrap overflow-x-auto
                                bg-[var(--color-surface-dark)] rounded-md p-2
                                border border-[var(--color-border-dim)]
                                ${isError ? "text-[var(--color-error)]" : "text-[var(--color-text-secondary)]"}`}>
                  {result}
                </pre>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}