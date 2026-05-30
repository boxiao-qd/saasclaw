import { useEffect, useState } from "react";
import { apiGet, apiDelete, getAccessToken } from "@/services/api-client";

interface FileItem {
  id: string;
  file_name: string;
  file_size: number | null;
  source_type: string;
  source_name: string | null;
  session_id: string | null;
  created_at: string;
}

function formatBytes(bytes: number | null): string {
  if (bytes == null) return "—";
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}

function formatDate(iso: string): string {
  const d = new Date(iso);
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

function fileIcon(name: string): string {
  const ext = name.split(".").pop()?.toLowerCase() ?? "";
  if (ext === "pptx" || ext === "ppt") return "📊";
  if (ext === "pdf") return "📄";
  if (ext === "docx" || ext === "doc") return "📝";
  if (ext === "xlsx" || ext === "xls") return "📋";
  if (["png", "jpg", "jpeg", "gif", "webp"].includes(ext)) return "🖼";
  if (ext === "zip" || ext === "gz" || ext === "tar") return "📦";
  return "📁";
}

export function FilesPage() {
  const [files, setFiles] = useState<FileItem[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [deletingId, setDeletingId] = useState<string | null>(null);
  const [confirmId, setConfirmId] = useState<string | null>(null);
  const [downloadingId, setDownloadingId] = useState<string | null>(null);

  const loadFiles = async () => {
    setLoading(true);
    setError("");
    try {
      const res = await apiGet<{ files: FileItem[]; total: number }>("/files");
      setFiles(res.files);
      setTotal(res.total);
    } catch (e: any) {
      setError(e?.message ?? "加载失败");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadFiles();
  }, []);

  const handleDownload = async (file: FileItem) => {
    setDownloadingId(file.id);
    try {
      const token = getAccessToken();
      const res = await fetch(`/bx/api/v1/files/${file.id}/download`, {
        headers: token ? { Authorization: `Bearer ${token}` } : {},
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = file.file_name;
      a.click();
      URL.revokeObjectURL(url);
    } catch (e: any) {
      alert(`下载失败: ${e?.message ?? "未知错误"}`);
    } finally {
      setDownloadingId(null);
    }
  };

  const handleDelete = async (id: string) => {
    setDeletingId(id);
    try {
      await apiDelete(`/files/${id}`);
      setFiles((prev) => prev.filter((f) => f.id !== id));
      setTotal((t) => t - 1);
    } catch (e: any) {
      alert(`删除失败: ${e?.message ?? "未知错误"}`);
    } finally {
      setDeletingId(null);
      setConfirmId(null);
    }
  };

  return (
    <div className="flex flex-col h-full bg-[var(--color-surface)] font-mono">
      {/* Header */}
      <div className="flex items-center justify-between px-6 py-4 border-b border-[var(--color-border)]">
        <div>
          <h1 className="text-[var(--color-text)] text-sm font-bold tracking-widest uppercase">
            MY FILES
          </h1>
          {!loading && (
            <p className="text-[var(--color-text-tertiary)] text-xs mt-0.5">
              {total} 个文件
            </p>
          )}
        </div>
        <button
          onClick={loadFiles}
          className="text-xs text-[var(--color-text-secondary)] hover:text-[var(--color-primary)] transition-colors"
        >
          刷新
        </button>
      </div>

      {/* Content */}
      <div className="flex-1 overflow-y-auto px-6 py-4">
        {loading && (
          <p className="text-[var(--color-text-tertiary)] text-xs text-center py-12">
            加载中...
          </p>
        )}

        {!loading && error && (
          <p className="text-red-400 text-xs text-center py-12">{error}</p>
        )}

        {!loading && !error && files.length === 0 && (
          <div className="flex flex-col items-center justify-center py-24 gap-3">
            <span className="text-4xl opacity-30">📂</span>
            <p className="text-[var(--color-text-tertiary)] text-xs">
              暂无文件。智能体生成的文件会出现在这里。
            </p>
          </div>
        )}

        {!loading && !error && files.length > 0 && (
          <ul className="flex flex-col gap-2">
            {files.map((file) => (
              <li
                key={file.id}
                className="flex items-center gap-4 px-4 py-3 rounded-lg border border-[var(--color-border)] bg-[var(--color-surface-alt)] hover:border-[var(--color-border-focus)] transition-colors"
              >
                {/* Icon */}
                <span className="text-xl flex-shrink-0">{fileIcon(file.file_name)}</span>

                {/* Info */}
                <div className="flex-1 min-w-0">
                  <p
                    className="text-[var(--color-text)] text-sm truncate"
                    title={file.file_name}
                  >
                    {file.file_name}
                  </p>
                  <p className="text-[var(--color-text-tertiary)] text-xs mt-0.5 flex gap-3 flex-wrap">
                    <span>{formatBytes(file.file_size)}</span>
                    {file.source_name && (
                      <span className="text-[var(--color-primary)] opacity-70">
                        {file.source_type}: {file.source_name}
                      </span>
                    )}
                    <span>{formatDate(file.created_at)}</span>
                  </p>
                </div>

                {/* Actions */}
                <div className="flex items-center gap-2 flex-shrink-0">
                  <button
                    onClick={() => handleDownload(file)}
                    disabled={downloadingId === file.id}
                    className="px-3 py-1 text-xs rounded border border-[var(--color-border)] text-[var(--color-text-secondary)] hover:text-[var(--color-primary)] hover:border-[var(--color-primary)] transition-colors disabled:opacity-40"
                  >
                    {downloadingId === file.id ? "下载中..." : "下载"}
                  </button>

                  {confirmId === file.id ? (
                    <div className="flex items-center gap-1">
                      <button
                        onClick={() => handleDelete(file.id)}
                        disabled={deletingId === file.id}
                        className="px-3 py-1 text-xs rounded border border-red-500/50 text-red-400 hover:bg-red-500/10 transition-colors disabled:opacity-40"
                      >
                        {deletingId === file.id ? "删除中..." : "确认删除"}
                      </button>
                      <button
                        onClick={() => setConfirmId(null)}
                        className="px-2 py-1 text-xs text-[var(--color-text-tertiary)] hover:text-[var(--color-text-secondary)] transition-colors"
                      >
                        取消
                      </button>
                    </div>
                  ) : (
                    <button
                      onClick={() => setConfirmId(file.id)}
                      className="px-3 py-1 text-xs rounded border border-[var(--color-border)] text-[var(--color-text-tertiary)] hover:text-red-400 hover:border-red-500/50 transition-colors"
                    >
                      删除
                    </button>
                  )}
                </div>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}
