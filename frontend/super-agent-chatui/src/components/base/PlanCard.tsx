import type { PlanState } from "@/store/message-store";

interface PlanCardProps {
  plan: PlanState;
}

const statusIcon: Record<string, string> = {
  pending: "○",
  in_progress: "◉",
  completed: "●",
};

const statusLabel: Record<string, string> = {
  pending: "待执行",
  in_progress: "执行中",
  completed: "已完成",
};

const statusColor: Record<string, string> = {
  pending: "text-[var(--color-text-tertiary)]",
  in_progress: "text-[var(--color-primary)]",
  completed: "text-green-400",
};

const levelIndent: Record<number, string> = {
  1: "",
  2: "ml-4",
  3: "ml-8",
};

export function PlanCard({ plan }: PlanCardProps) {
  const completedCount = plan.steps.filter((s) => s.status === "completed").length;
  // Count only level-1 steps for the progress bar to reflect major milestones
  const topLevelSteps = plan.steps.filter((s) => s.level === 1);
  const topLevelDone = topLevelSteps.filter((s) => s.status === "completed").length;

  return (
    <div className="flex justify-start" role="article" aria-label="执行计划">
      <div className="rounded-lg glass glow-primary px-4 py-3 max-w-[95%] md:max-w-[85%] text-sm w-full">
        {/* Header */}
        <div className="flex items-center gap-2 mb-3">
          <svg className="w-4 h-4 text-[var(--color-primary)]" viewBox="0 0 16 16" fill="none">
            <rect x="2" y="2" width="5" height="5" rx="1" stroke="currentColor" strokeWidth="1.2" />
            <rect x="9" y="2" width="5" height="5" rx="1" stroke="currentColor" strokeWidth="1.2" />
            <rect x="2" y="9" width="5" height="5" rx="1" stroke="currentColor" strokeWidth="1.2" />
            <rect x="9" y="9" width="5" height="5" rx="1" stroke="currentColor" strokeWidth="1.2" />
          </svg>
          <span className="font-mono text-xs tracking-widest text-[var(--color-primary)]">
            EXECUTION PLAN
          </span>
          {plan.status === "completed" && (
            <span className="font-mono text-[10px] text-green-400 ml-auto">DONE</span>
          )}
        </div>

        {/* Steps */}
        <div className="space-y-0.5">
          {plan.steps.map((step) => (
            <div
              key={step.id}
              className={`flex items-start gap-2 text-xs py-1 px-2 rounded transition-colors ${levelIndent[step.level] ?? ""} ${
                step.status === "in_progress" ? "bg-[var(--color-primary)]/10" : ""
              }`}
            >
              <span className={`font-mono mt-0.5 shrink-0 ${statusColor[step.status]}`}>
                {statusIcon[step.status]}
              </span>
              <span
                className={`flex-1 ${
                  step.status === "completed"
                    ? "text-[var(--color-text-tertiary)] line-through"
                    : step.status === "in_progress"
                    ? "text-[var(--color-text-primary)]"
                    : "text-[var(--color-text-secondary)]"
                } ${step.level > 1 ? "text-[11px] opacity-90" : ""}`}
              >
                {step.status === "in_progress" && step.activeForm ? step.activeForm : step.content}
              </span>
              <span className={`font-mono text-[10px] shrink-0 ${statusColor[step.status]}`}>
                {statusLabel[step.status]}
              </span>
            </div>
          ))}
        </div>

        {/* Progress bar */}
        <div className="mt-2 flex items-center gap-2">
          <div className="flex-1 h-1 bg-[var(--color-surface-dark)] rounded-full overflow-hidden">
            <div
              className="h-full bg-[var(--color-primary)] rounded-full transition-all duration-300"
              style={{
                width: `${topLevelSteps.length > 0 ? (topLevelDone / topLevelSteps.length) * 100 : 0}%`,
              }}
            />
          </div>
          <span className="font-mono text-[10px] text-[var(--color-text-tertiary)]">
            {completedCount}/{plan.steps.length}
          </span>
        </div>
      </div>
    </div>
  );
}
