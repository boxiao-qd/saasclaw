import { useState } from "react";
import { apiGet } from "@/services/api-client";
import type { SearchResultItem } from "@/types/api-types";
import type { FourState } from "@/types/component-state";

export function SearchPage() {
  const [query, setQuery] = useState("");
  const [state, setState] = useState<FourState>("empty");
  const [results, setResults] = useState<SearchResultItem[]>([]);

  const handleSearch = async () => {
    if (!query.trim()) return;
    setState("loading");
    try {
      const data = await apiGet<{ results: SearchResultItem[] }>(`/search?q=${encodeURIComponent(query)}`);
      setResults(data.results);
      setState(data.results.length > 0 ? "success" : "empty");
    } catch {
      setState("error");
    }
  };

  return (
    <div className="p-8 max-w-2xl" role="main" aria-label="全局搜索">
      <h1 className="text-xl font-semibold mb-6">搜索</h1>
      <div className="flex gap-2 mb-6">
        <input
          type="search"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && handleSearch()}
          placeholder="搜索对话内容..."
          className="flex-1 rounded-md border border-border px-3 py-2"
          aria-label="搜索关键词"
        />
        <button
          onClick={handleSearch}
          className="rounded-md bg-primary px-4 py-2 text-sm text-white hover:bg-primary-hover"
          aria-label="搜索"
        >
          搜索
        </button>
      </div>
      {state === "loading" && <p className="text-secondary">搜索中...</p>}
      {state === "error" && <p className="text-error">搜索失败</p>}
      {state === "empty" && query && <p className="text-secondary">无搜索结果</p>}
      {state === "success" && (
        <ul className="space-y-3">
          {results.map((r, i) => (
            <li key={i} className="rounded-md border border-border p-4">
              <div className="font-medium mb-1">{r.session_title || "未命名对话"}</div>
              <p className="text-sm text-secondary">{r.snippet}</p>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}