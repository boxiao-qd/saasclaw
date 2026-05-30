import { useEffect, useState } from "react";
import { apiGet } from "@/services/api-client";
import type { AgentDefinitionSummary } from "@/types/api-types";

export function SubagentsPage() {
  const [agents, setAgents] = useState<AgentDefinitionSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    (async () => {
      setLoading(true);
      try {
        const result = await apiGet<{ agents: AgentDefinitionSummary[] }>("/agents");
        setAgents(result.agents.filter((a) => a.source === "builtin"));
      } catch {
        setError("加载失败");
      }
      setLoading(false);
    })();
  }, []);

  return (
    <div className="p-6 max-w-3xl" role="main" aria-label="内置子代理">
      <h1 className="text-lg font-semibold font-mono mb-6">内置子代理</h1>

      {loading && (
        <p className="text-[var(--color-text-secondary)] text-sm font-mono">加载中...</p>
      )}
      {!loading && error && (
        <p className="text-[var(--color-error)] text-sm font-mono">{error}</p>
      )}
      {!loading && !error && agents.length === 0 && (
        <p className="text-[var(--color-text-secondary)] text-sm font-mono">暂无内置子代理。</p>
      )}

      <ul className="space-y-3">
        {agents.map((a) => (
          <li key={a.agent_type} className="rounded-md border border-[var(--color-border)] p-4 bg-[var(--color-surface-alt)]">
            <div className="flex items-center gap-2 mb-1">
              {a.color && (
                <span
                  className="inline-block w-3 h-3 rounded-full shrink-0"
                  style={{ backgroundColor: a.color }}
                />
              )}
              <span className="font-medium font-mono text-sm">{a.agent_type}</span>
              <span className="text-[0.65rem] font-mono px-1.5 py-0.5 rounded bg-[var(--color-primary-dim)] text-[var(--color-primary)] shrink-0">内置</span>
            </div>
            {a.when_to_use && (
              <p className="text-xs text-[var(--color-text-secondary)]">{a.when_to_use}</p>
            )}
            {a.tools && a.tools.length > 0 && (
              <p className="text-[0.65rem] text-[var(--color-text-tertiary)] font-mono mt-1">
                工具: {a.tools.join(", ")}
              </p>
            )}
            {a.disallowed_tools && a.disallowed_tools.length > 0 && (
              <p className="text-[0.65rem] text-[var(--color-text-tertiary)] font-mono mt-0.5">
                禁用: {a.disallowed_tools.join(", ")}
              </p>
            )}
            {a.model && (
              <p className="text-[0.65rem] text-[var(--color-text-tertiary)] font-mono mt-0.5">
                模型: {a.model}
              </p>
            )}
          </li>
        ))}
      </ul>
    </div>
  );
}