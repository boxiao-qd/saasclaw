import { useEffect, useState } from "react";
import { apiGet, apiPost, apiPut, apiDelete } from "@/services/api-client";
import type { SkillItem } from "@/types/api-types";

type Mode = "list" | "create" | "edit" | "upload";

interface CreateForm {
  name: string;
  content_md: string;
  header_description: string;
}

interface EditForm {
  name: string;
  content_md: string;
  header_description: string;
}

const emptyCreate = (): CreateForm => ({ name: "", content_md: "", header_description: "" });

export function SkillsPage() {
  const [skills, setSkills] = useState<SkillItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [mode, setMode] = useState<Mode>("list");
  const [selected, setSelected] = useState<SkillItem | null>(null);
  const [createForm, setCreateForm] = useState<CreateForm>(emptyCreate());
  const [editForm, setEditForm] = useState<EditForm>({ name: "", content_md: "", header_description: "" });
  const [uploadMd, setUploadMd] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const fetchSkills = async () => {
    setLoading(true);
    try {
      const result = await apiGet<{ skills: SkillItem[] }>("/skills");
      setSkills(result.skills);
    } catch { setError("加载失败"); }
    setLoading(false);
  };

  useEffect(() => { fetchSkills(); }, []);

  const openEdit = (s: SkillItem) => {
    setSelected(s);
    setEditForm({
      name: s.name,
      content_md: s.content_md,
      header_description: s.header_description ?? "",
    });
    setError("");
    setMode("edit");
  };

  const openUpload = (s: SkillItem) => {
    setSelected(s);
    setUploadMd(s.content_md);
    setError("");
    setMode("upload");
  };

  const handleCreate = async () => {
    if (!createForm.name.trim() || !createForm.content_md.trim()) {
      setError("名称和内容不能为空");
      return;
    }
    setBusy(true);
    setError("");
    try {
      await apiPost("/skills", {
        name: createForm.name.trim(),
        content_md: createForm.content_md,
        header_description: createForm.header_description || undefined,
        is_global: false,
      } as Record<string, unknown>);
      setCreateForm(emptyCreate());
      setMode("list");
      fetchSkills();
    } catch (e) {
      setError(`创建失败: ${e}`);
    }
    setBusy(false);
  };

  const handleUpdate = async () => {
    if (!selected) return;
    setBusy(true);
    setError("");
    try {
      await apiPut(`/skills/${selected.id}`, {
        name: editForm.name || undefined,
        content_md: editForm.content_md || undefined,
        header_description: editForm.header_description || undefined,
      } as Record<string, unknown>);
      setMode("list");
      fetchSkills();
    } catch (e) {
      setError(`更新失败: ${e}`);
    }
    setBusy(false);
  };

  const handleUpload = async () => {
    if (!selected || !uploadMd.trim()) {
      setError("内容不能为空");
      return;
    }
    setBusy(true);
    setError("");
    try {
      await apiPut(`/skills/${selected.id}/content`, { skill_md: uploadMd } as Record<string, unknown>);
      setMode("list");
      fetchSkills();
    } catch (e) {
      setError(`上传失败: ${e}`);
    }
    setBusy(false);
  };

  const handleDelete = async (s: SkillItem) => {
    if (!confirm(`确认删除技能「${s.name}」？`)) return;
    try {
      await apiDelete(`/skills/${s.id}`);
      fetchSkills();
    } catch (e) {
      alert(`删除失败: ${e}`);
    }
  };

  const back = () => { setMode("list"); setError(""); };

  // ── Create / Edit / Upload form ──────────────────────────────────────────
  if (mode === "create") {
    return (
      <div className="p-6 max-w-2xl" role="main">
        <div className="flex items-center gap-3 mb-6">
          <button onClick={back} className="text-[var(--color-text-secondary)] hover:text-[var(--color-text)] text-sm font-mono">← 返回</button>
          <h1 className="text-lg font-semibold font-mono">新建技能</h1>
        </div>
        {error && <p className="text-[var(--color-error)] text-sm mb-4">{error}</p>}
        <div className="space-y-4">
          <label className="block">
            <span className="text-xs font-mono text-[var(--color-text-secondary)] uppercase mb-1 block">名称 *</span>
            <input
              className="w-full rounded border border-[var(--color-border)] bg-[var(--color-surface-alt)] px-3 py-2 text-sm font-mono focus:outline-none focus:border-[var(--color-primary)]"
              value={createForm.name}
              onChange={(e) => setCreateForm((f) => ({ ...f, name: e.target.value }))}
              placeholder="skill-name"
              maxLength={64}
              aria-label="技能名称"
            />
          </label>
          <label className="block">
            <span className="text-xs font-mono text-[var(--color-text-secondary)] uppercase mb-1 block">简介 (可选)</span>
            <input
              className="w-full rounded border border-[var(--color-border)] bg-[var(--color-surface-alt)] px-3 py-2 text-sm font-mono focus:outline-none focus:border-[var(--color-primary)]"
              value={createForm.header_description}
              onChange={(e) => setCreateForm((f) => ({ ...f, header_description: e.target.value }))}
              placeholder="一句话描述"
              maxLength={500}
              aria-label="技能简介"
            />
          </label>
          <label className="block">
            <span className="text-xs font-mono text-[var(--color-text-secondary)] uppercase mb-1 block">SKILL.md 内容 *</span>
            <textarea
              className="w-full rounded border border-[var(--color-border)] bg-[var(--color-surface-alt)] px-3 py-2 text-sm font-mono focus:outline-none focus:border-[var(--color-primary)] h-48 resize-y"
              value={createForm.content_md}
              onChange={(e) => setCreateForm((f) => ({ ...f, content_md: e.target.value }))}
              placeholder="# Skill Name&#10;&#10;## 用途&#10;..."
              aria-label="技能内容"
            />
          </label>
          <div className="flex gap-3">
            <button
              onClick={handleCreate}
              disabled={busy}
              className="px-4 py-2 text-sm font-mono rounded bg-[var(--color-primary)] text-black hover:opacity-90 disabled:opacity-50"
              aria-label="创建技能"
            >
              {busy ? "创建中..." : "创建"}
            </button>
            <button onClick={back} className="px-4 py-2 text-sm font-mono rounded border border-[var(--color-border)] text-[var(--color-text-secondary)] hover:text-[var(--color-text)]">
              取消
            </button>
          </div>
        </div>
      </div>
    );
  }

  if (mode === "edit" && selected) {
    return (
      <div className="p-6 max-w-2xl" role="main">
        <div className="flex items-center gap-3 mb-6">
          <button onClick={back} className="text-[var(--color-text-secondary)] hover:text-[var(--color-text)] text-sm font-mono">← 返回</button>
          <h1 className="text-lg font-semibold font-mono">编辑技能 — {selected.name}</h1>
        </div>
        {error && <p className="text-[var(--color-error)] text-sm mb-4">{error}</p>}
        <div className="space-y-4">
          <label className="block">
            <span className="text-xs font-mono text-[var(--color-text-secondary)] uppercase mb-1 block">名称</span>
            <input
              className="w-full rounded border border-[var(--color-border)] bg-[var(--color-surface-alt)] px-3 py-2 text-sm font-mono focus:outline-none focus:border-[var(--color-primary)]"
              value={editForm.name}
              onChange={(e) => setEditForm((f) => ({ ...f, name: e.target.value }))}
              maxLength={64}
              aria-label="技能名称"
            />
          </label>
          <label className="block">
            <span className="text-xs font-mono text-[var(--color-text-secondary)] uppercase mb-1 block">简介</span>
            <input
              className="w-full rounded border border-[var(--color-border)] bg-[var(--color-surface-alt)] px-3 py-2 text-sm font-mono focus:outline-none focus:border-[var(--color-primary)]"
              value={editForm.header_description}
              onChange={(e) => setEditForm((f) => ({ ...f, header_description: e.target.value }))}
              maxLength={500}
              aria-label="技能简介"
            />
          </label>
          <label className="block">
            <span className="text-xs font-mono text-[var(--color-text-secondary)] uppercase mb-1 block">SKILL.md 内容</span>
            <textarea
              className="w-full rounded border border-[var(--color-border)] bg-[var(--color-surface-alt)] px-3 py-2 text-sm font-mono focus:outline-none focus:border-[var(--color-primary)] h-48 resize-y"
              value={editForm.content_md}
              onChange={(e) => setEditForm((f) => ({ ...f, content_md: e.target.value }))}
              aria-label="技能内容"
            />
          </label>
          <div className="flex gap-3">
            <button onClick={handleUpdate} disabled={busy} className="px-4 py-2 text-sm font-mono rounded bg-[var(--color-primary)] text-black hover:opacity-90 disabled:opacity-50" aria-label="保存更改">
              {busy ? "保存中..." : "保存"}
            </button>
            <button onClick={back} className="px-4 py-2 text-sm font-mono rounded border border-[var(--color-border)] text-[var(--color-text-secondary)] hover:text-[var(--color-text)]">
              取消
            </button>
          </div>
        </div>
      </div>
    );
  }

  if (mode === "upload" && selected) {
    return (
      <div className="p-6 max-w-2xl" role="main">
        <div className="flex items-center gap-3 mb-6">
          <button onClick={back} className="text-[var(--color-text-secondary)] hover:text-[var(--color-text)] text-sm font-mono">← 返回</button>
          <h1 className="text-lg font-semibold font-mono">上传 SKILL.md — {selected.name}</h1>
        </div>
        <p className="text-xs text-[var(--color-text-secondary)] font-mono mb-4">
          内容将同步到对象存储，并更新缓存和简介。
        </p>
        {error && <p className="text-[var(--color-error)] text-sm mb-4">{error}</p>}
        <textarea
          className="w-full rounded border border-[var(--color-border)] bg-[var(--color-surface-alt)] px-3 py-2 text-sm font-mono focus:outline-none focus:border-[var(--color-primary)] h-64 resize-y mb-4"
          value={uploadMd}
          onChange={(e) => setUploadMd(e.target.value)}
          aria-label="SKILL.md 内容"
        />
        <div className="flex gap-3">
          <button onClick={handleUpload} disabled={busy} className="px-4 py-2 text-sm font-mono rounded bg-[var(--color-primary)] text-black hover:opacity-90 disabled:opacity-50" aria-label="上传内容">
            {busy ? "上传中..." : "上传"}
          </button>
          <button onClick={back} className="px-4 py-2 text-sm font-mono rounded border border-[var(--color-border)] text-[var(--color-text-secondary)] hover:text-[var(--color-text)]">
            取消
          </button>
        </div>
      </div>
    );
  }

  // ── List view ─────────────────────────────────────────────────────────────
  return (
    <div className="p-6 max-w-3xl" role="main" aria-label="技能管理">
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-lg font-semibold font-mono">技能管理</h1>
        <button
          onClick={() => { setCreateForm(emptyCreate()); setError(""); setMode("create"); }}
          className="px-3 py-1.5 text-sm font-mono rounded border border-[var(--color-primary)] text-[var(--color-primary)] hover:bg-[var(--color-primary-dim)] transition-colors"
          aria-label="新建技能"
        >
          + 新建技能
        </button>
      </div>

      {loading && <p className="text-[var(--color-text-secondary)] text-sm font-mono">加载中...</p>}
      {!loading && skills.length === 0 && (
        <p className="text-[var(--color-text-secondary)] text-sm font-mono">暂无技能，点击「新建技能」开始。</p>
      )}

      <ul className="space-y-3">
        {skills.map((s) => (
          <li key={s.id} className="rounded-md border border-[var(--color-border)] p-4 bg-[var(--color-surface-alt)]">
            <div className="flex items-start justify-between gap-3">
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2 mb-1">
                  <span className="font-medium font-mono text-sm truncate">{s.name}</span>
                  {s.is_global && (
                    <span className="text-[0.65rem] font-mono px-1.5 py-0.5 rounded bg-[var(--color-primary-dim)] text-[var(--color-primary)] shrink-0">
                      全局
                    </span>
                  )}
                  {s.object_key && (
                    <span className="text-[0.65rem] font-mono px-1.5 py-0.5 rounded bg-[var(--color-surface)] text-[var(--color-text-tertiary)] border border-[var(--color-border)] shrink-0">
                      OS
                    </span>
                  )}
                </div>
                {s.header_description && (
                  <p className="text-xs text-[var(--color-text-secondary)] truncate">{s.header_description}</p>
                )}
                <p className="text-[0.65rem] text-[var(--color-text-tertiary)] font-mono mt-1">
                  使用 {s.usage_count} 次 · {s.created_at.slice(0, 10)}
                </p>
              </div>
              {!s.is_global && (
                <div className="flex gap-2 shrink-0">
                  <button
                    onClick={() => openUpload(s)}
                    className="text-xs font-mono px-2 py-1 rounded border border-[var(--color-border)] text-[var(--color-text-secondary)] hover:text-[var(--color-text)] hover:border-[var(--color-primary)] transition-colors"
                    aria-label={`上传 ${s.name} 的内容`}
                  >
                    上传
                  </button>
                  <button
                    onClick={() => openEdit(s)}
                    className="text-xs font-mono px-2 py-1 rounded border border-[var(--color-border)] text-[var(--color-text-secondary)] hover:text-[var(--color-text)] transition-colors"
                    aria-label={`编辑 ${s.name}`}
                  >
                    编辑
                  </button>
                  <button
                    onClick={() => handleDelete(s)}
                    className="text-xs font-mono px-2 py-1 rounded border border-[var(--color-border)] text-[var(--color-error)] hover:bg-[var(--color-error)]/10 transition-colors"
                    aria-label={`删除 ${s.name}`}
                  >
                    删除
                  </button>
                </div>
              )}
            </div>
          </li>
        ))}
      </ul>
    </div>
  );
}
