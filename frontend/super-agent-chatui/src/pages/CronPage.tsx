import { useEffect, useState } from "react";
import { apiGet, apiPost, apiPut, apiDelete } from "@/services/api-client";
import type { CronJobItem, CronRunItem } from "@/types/api-types";

type Mode = "list" | "create" | "edit";

const inputCls = "w-full rounded border border-[var(--color-border)] bg-[var(--color-surface)] px-3 py-2 text-sm font-mono text-[var(--color-text)] focus:outline-none focus:border-[var(--color-primary)]";
const labelCls = "text-xs font-mono text-[var(--color-text-secondary)] uppercase mb-1 block";

const CRON_HELP = [
  { expr: "0 9 * * *", desc: "每天 9:00" },
  { expr: "0 9 * * 1-5", desc: "工作日 9:00" },
  { expr: "0 */2 * * *", desc: "每 2 小时" },
  { expr: "30 8 1 * *", desc: "每月 1 号 8:30" },
  { expr: "0 0 * * 0", desc: "每周日 0:00" },
];

export function CronPage() {
  const [jobs, setJobs] = useState<CronJobItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [mode, setMode] = useState<Mode>("list");
  const [selectedJob, setSelectedJob] = useState<CronJobItem | null>(null);
  const [form, setForm] = useState({ name: "", prompt: "", cron_expr: "" });
  const [runs, setRuns] = useState<CronRunItem[]>([]);
  const [viewingRuns, setViewingRuns] = useState<string | null>(null);

  const fetchJobs = async () => {
    setLoading(true);
    try {
      const result = await apiGet<{ jobs: CronJobItem[] }>("/cron/jobs");
      setJobs(result.jobs);
    } catch { /* ignore */ }
    setLoading(false);
  };

  useEffect(() => { fetchJobs(); }, []);

  const fetchRuns = async (jobId: string) => {
    try {
      const result = await apiGet<{ runs: CronRunItem[] }>(`/cron/jobs/${jobId}/runs`);
      setRuns(result.runs);
      setViewingRuns(jobId);
    } catch { /* ignore */ }
  };

  const openCreate = () => {
    setForm({ name: "", prompt: "", cron_expr: "" });
    setMode("create");
  };

  const openEdit = (job: CronJobItem) => {
    setSelectedJob(job);
    setForm({ name: job.name ?? "", prompt: job.prompt, cron_expr: job.cron_expr });
    setMode("edit");
  };

  const handleCreate = async () => {
    try {
      await apiPost("/cron/jobs", { name: form.name, prompt: form.prompt, cron_expr: form.cron_expr });
      setMode("list");
      fetchJobs();
    } catch (e) { alert(`创建失败: ${e}`); }
  };

  const handleUpdate = async () => {
    if (!selectedJob) return;
    const body: Record<string, string> = {};
    if (form.name !== (selectedJob.name ?? "")) body.name = form.name;
    if (form.prompt !== selectedJob.prompt) body.prompt = form.prompt;
    if (form.cron_expr !== selectedJob.cron_expr) body.cron_expr = form.cron_expr;
    if (!Object.keys(body).length) { setMode("list"); return; }
    try {
      await apiPut(`/cron/jobs/${selectedJob.id}`, body);
      setMode("list");
      fetchJobs();
    } catch (e) { alert(`更新失败: ${e}`); }
  };

  const pauseJob = async (id: string) => {
    try { await apiPost(`/cron/jobs/${id}/pause`, {}); fetchJobs(); } catch { /* ignore */ }
  };

  const resumeJob = async (id: string) => {
    try { await apiPost(`/cron/jobs/${id}/resume`, {}); fetchJobs(); } catch { /* ignore */ }
  };

  const deleteJob = async (id: string) => {
    if (!confirm("确认删除该定时任务？")) return;
    try { await apiDelete(`/cron/jobs/${id}`); fetchJobs(); } catch { /* ignore */ }
  };

  const back = () => { setMode("list"); setViewingRuns(null); };

  // ── Create / Edit form ──────────────────────────────────────────────────
  if (mode === "create" || mode === "edit") {
    const title = mode === "create" ? "新建定时任务" : `编辑 — ${selectedJob?.name}`;
    const submitLabel = mode === "create" ? "创建" : "保存";
    const onSubmit = mode === "create" ? handleCreate : handleUpdate;
    return (
      <div className="p-6 max-w-2xl" role="main">
        <div className="flex items-center gap-3 mb-6">
          <button onClick={back} className="text-[var(--color-text-secondary)] hover:text-[var(--color-text)] text-sm font-mono">← 返回</button>
          <h1 className="text-lg font-semibold font-mono">{title}</h1>
        </div>
        <div className="space-y-4">
          <label className="block"><span className={labelCls}>名称</span>
            <input className={inputCls} value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} placeholder="每日早报" maxLength={128} aria-label="任务名称" />
          </label>
          <label className="block"><span className={labelCls}>执行指令 (prompt)</span>
            <textarea className={`${inputCls} h-24 resize-y`} value={form.prompt} onChange={(e) => setForm({ ...form, prompt: e.target.value })} placeholder="帮我总结昨天的对话内容" aria-label="执行指令" />
          </label>
          <label className="block"><span className={labelCls}>Cron 表达式</span>
            <input className={inputCls} value={form.cron_expr} onChange={(e) => setForm({ ...form, cron_expr: e.target.value })} placeholder="0 9 * * *" maxLength={128} aria-label="Cron 表达式" />
            <div className="mt-2 text-[0.65rem] text-[var(--color-text-tertiary)] font-mono space-y-0.5">
              {CRON_HELP.map(({ expr, desc }) => (
                <button key={expr} onClick={() => setForm({ ...form, cron_expr: expr })} className="hover:text-[var(--color-text)] cursor-pointer">{expr} — {desc}</button>
              ))}
            </div>
          </label>
          <div className="flex gap-3">
            <button onClick={onSubmit} className="px-4 py-2 text-sm font-mono rounded bg-[var(--color-primary)] text-black hover:opacity-90" aria-label={submitLabel}>{submitLabel}</button>
            <button onClick={back} className="px-4 py-2 text-sm font-mono rounded border border-[var(--color-border)] text-[var(--color-text-secondary)]">取消</button>
          </div>
        </div>
      </div>
    );
  }

  // ── Run history ─────────────────────────────────────────────────────────
  if (viewingRuns) {
    const job = jobs.find((j) => j.id === viewingRuns);
    return (
      <div className="p-6 max-w-3xl" role="main">
        <div className="flex items-center gap-3 mb-6">
          <button onClick={back} className="text-[var(--color-text-secondary)] hover:text-[var(--color-text)] text-sm font-mono">← 返回</button>
          <h1 className="text-lg font-semibold font-mono">执行历史 — {job?.name}</h1>
        </div>
        {runs.length === 0 && <p className="text-sm font-mono text-[var(--color-text-secondary)]">暂无执行记录</p>}
        <ul className="space-y-2">
          {runs.map((r) => (
            <li key={r.id} className="rounded border border-[var(--color-border)] p-3 bg-[var(--color-surface-alt)]">
              <div className="flex items-center gap-2 mb-1">
                <span className={`text-xs font-mono px-1.5 py-0.5 rounded ${
                  r.status === "success" ? "bg-green-900/30 text-green-400" :
                  r.status === "failed" ? "bg-red-900/30 text-red-400" :
                  "bg-[var(--color-primary-dim)] text-[var(--color-primary)]"
                }`}>{r.status}</span>
                <span className="text-[0.65rem] font-mono text-[var(--color-text-tertiary)]">
                  {r.started_at?.slice(0, 19)}
                  {r.duration_seconds != null && ` · ${r.duration_seconds}s`}
                </span>
              </div>
              {r.result_summary && (
                <p className="text-xs text-[var(--color-text-secondary)] line-clamp-3">{r.result_summary}</p>
              )}
              {r.error_message && (
                <p className="text-xs text-red-400 line-clamp-2">{r.error_message}</p>
              )}
            </li>
          ))}
        </ul>
      </div>
    );
  }

  // ── Job list ────────────────────────────────────────────────────────────
  return (
    <div className="p-6 max-w-3xl" role="main" aria-label="定时任务管理">
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-lg font-semibold font-mono">定时任务</h1>
        <button onClick={openCreate} className="px-3 py-1.5 text-sm font-mono rounded border border-[var(--color-primary)] text-[var(--color-primary)] hover:bg-[var(--color-primary-dim)]" aria-label="新建定时任务">+ 新建</button>
      </div>

      {loading && <p className="text-sm font-mono text-[var(--color-text-secondary)]">加载中...</p>}
      {!loading && jobs.length === 0 && (
        <p className="text-sm font-mono text-[var(--color-text-secondary)]">暂无定时任务，点击「新建」开始。</p>
      )}

      <ul className="space-y-3">
        {jobs.map((j) => (
          <li key={j.id} className="rounded-md border border-[var(--color-border)] p-4 bg-[var(--color-surface-alt)]">
            <div className="flex items-start justify-between gap-3">
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2 mb-1">
                  <span className="font-medium font-mono text-sm">{j.name}</span>
                  <span className={`text-[0.65rem] font-mono px-1.5 py-0.5 rounded ${
                    j.is_active ? "bg-[var(--color-primary-dim)] text-[var(--color-primary)]" : "bg-[var(--color-surface)] text-[var(--color-text-tertiary)] border border-[var(--color-border)]"
                  }`}>{j.is_active ? "活跃" : "暂停"}</span>
                  {j.is_running && (
                    <span className="text-[0.65rem] font-mono px-1.5 py-0.5 rounded bg-yellow-900/30 text-yellow-400">执行中</span>
                  )}
                </div>
                <p className="text-xs text-[var(--color-text-secondary)] line-clamp-2">{j.prompt}</p>
                <p className="text-[0.65rem] text-[var(--color-text-tertiary)] font-mono mt-1">
                  {j.cron_expr} · 执行 {j.run_count} 次
                </p>
                {j.next_run_at && (
                  <p className="text-[0.65rem] text-[var(--color-text-tertiary)] font-mono">
                    下次: {new Date(j.next_run_at).toLocaleString()}
                  </p>
                )}
                {j.consecutive_errors > 0 && (
                  <p className="text-[0.65rem] text-yellow-400 font-mono">连续失败 {j.consecutive_errors} 次</p>
                )}
                {j.last_error && (
                  <p className="text-[0.65rem] text-red-400 font-mono line-clamp-1">{j.last_error}</p>
                )}
              </div>
              <div className="flex gap-2 shrink-0">
                <button onClick={() => fetchRuns(j.id)} className="text-xs font-mono px-2 py-1 rounded border border-[var(--color-border)] text-[var(--color-text-secondary)] hover:text-[var(--color-text)]" aria-label="查看执行历史">历史</button>
                <button onClick={() => openEdit(j)} className="text-xs font-mono px-2 py-1 rounded border border-[var(--color-border)] text-[var(--color-text-secondary)] hover:text-[var(--color-text)]" aria-label="编辑任务">编辑</button>
                {j.is_active ? (
                  <button onClick={() => pauseJob(j.id)} className="text-xs font-mono px-2 py-1 rounded border border-[var(--color-border)] text-[var(--color-text-secondary)]" aria-label="暂停任务">暂停</button>
                ) : (
                  <button onClick={() => resumeJob(j.id)} className="text-xs font-mono px-2 py-1 rounded border border-[var(--color-primary)] text-[var(--color-primary)] hover:bg-[var(--color-primary-dim)]" aria-label="恢复任务">恢复</button>
                )}
                <button onClick={() => deleteJob(j.id)} className="text-xs font-mono px-2 py-1 rounded border border-[var(--color-border)] text-red-400 hover:bg-red-400/10" aria-label="删除任务">删除</button>
              </div>
            </div>
          </li>
        ))}
      </ul>
    </div>
  );
}