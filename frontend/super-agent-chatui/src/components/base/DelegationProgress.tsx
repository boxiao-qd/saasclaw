interface DelegationProgressProps {
  childSessionId: string;
  subagentName: string;
  goal: string;
  status?: string;
  progressNote?: string;
  elapsedSeconds?: number;
  summary?: string;
  isError?: boolean;
}

export function DelegationProgress({
  childSessionId, subagentName, goal, status, progressNote, elapsedSeconds, summary, isError,
}: DelegationProgressProps) {
  const isActive = !summary;

  /* ── Pipeline stage visualization ──────────────────────────────── */
  const stages = [
    { label: "DISPATCH", done: true },
    { label: "EXECUTE", done: isActive ? false : true },
    { label: "RETURN", done: summary ? true : false },
  ];

  return (
    <div
      className="my-2 rounded-lg glass glow-primary p-2.5"
      data-child-session={childSessionId}
    >
      {/* ── Header ──────────────────────────────────────────────────── */}
      <div className="flex items-center gap-2 text-sm">
        {/* Agent avatar dot */}
        <span className={`w-2.5 h-2.5 rounded-full ${
          isActive ? "bg-[var(--color-primary)] animate-pulse-cyan" :
          isError ? "bg-[var(--color-error)]" :
          "bg-[var(--color-success)]"
        }`} />

        <span className="font-mono font-semibold text-[var(--color-primary)] tracking-wide">
          {subagentName}
        </span>

        {isActive && (
          <span className="text-[0.7rem] font-mono text-[var(--color-primary)] animate-pulse-cyan">
            running
          </span>
        )}
        {!isActive && !isError && (
          <span className="text-[0.7rem] font-mono text-[var(--color-success)]">
            completed
          </span>
        )}
        {!isActive && isError && (
          <span className="text-[0.7rem] font-mono text-[var(--color-error)]">
            failed
          </span>
        )}

        {elapsedSeconds && (
          <span className="ml-auto text-[0.7rem] font-mono text-[var(--color-text-tertiary)]">
            {elapsedSeconds}s
          </span>
        )}
      </div>

      {/* ── Pipeline stages ─────────────────────────────────────────── */}
      <div className="flex items-center gap-1 mt-1.5">
        {stages.map((stage, i) => (
          <div key={i} className="flex items-center gap-1">
            <div className={`h-1 w-8 rounded-full transition-colors ${
              stage.done
                ? (isError ? "bg-[var(--color-error)]" : "bg-[var(--color-primary)]")
                : "bg-[var(--color-border-dim)] animate-pulse-cyan"
            }`} />
            <span className={`text-[0.6rem] font-mono ${
              stage.done ? "text-[var(--color-text-secondary)]" : "text-[var(--color-text-tertiary)]"
            }`}>
              {stage.label}
            </span>
          </div>
        ))}
      </div>

      {/* ── Goal ─────────────────────────────────────────────────────── */}
      <p className="text-xs text-[var(--color-text-secondary)] mt-2 font-mono leading-relaxed">
        <span className="text-[var(--color-primary)] opacity-60">&#9656;</span> {goal}
      </p>

      {/* ── Progress note ────────────────────────────────────────────── */}
      {isActive && progressNote && (
        <p className="text-xs text-[var(--color-text-tertiary)] mt-1 font-mono">
          {progressNote}
        </p>
      )}

      {/* ── Summary ──────────────────────────────────────────────────── */}
      {summary && (
        <div className={`mt-2 text-sm text-[var(--color-text)] leading-relaxed ${
          isError ? "text-[var(--color-error)]" : ""
        }`}>
          {summary}
        </div>
      )}
    </div>
  );
}