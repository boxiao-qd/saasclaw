import { useEffect, useState } from "react";
import { apiGet, apiPut } from "@/services/api-client";
import type { SettingsData } from "@/types/api-types";
import type { FourState } from "@/types/component-state";

export function SettingsPage() {
  const [state, setState] = useState<FourState>("loading");
  const [settings, setSettings] = useState<SettingsData | null>(null);

  useEffect(() => {
    apiGet<SettingsData>("/settings")
      .then((data) => {
        setSettings(data);
        setState("success");
      })
      .catch(() => setState("error"));
  }, []);

  if (state === "loading") return <div className="p-8 text-secondary">Loading...</div>;
  if (state === "error") return <div className="p-8 text-error">Failed to load settings</div>;
  if (!settings) return null;

  const handleSave = async () => {
    await apiPut("/settings", {
      model: settings.current_model,
      tools: settings.enabled_tools,
    });
  };

  return (
    <div className="p-8 max-w-2xl" role="main" aria-label="设置">
      <h1 className="text-xl font-semibold mb-6">设置</h1>
      <section className="mb-6">
        <h2 className="text-lg font-medium mb-3">模型选择</h2>
        <select
          value={settings.current_model || ""}
          onChange={(e) => setSettings({ ...settings, current_model: e.target.value })}
          className="rounded-md border border-border px-3 py-2 w-full"
          aria-label="选择模型"
        >
          <option value="">默认模型</option>
          {settings.models.map((m) => (
            <option key={m.model_id} value={m.model_id}>{m.name}</option>
          ))}
        </select>
      </section>
      <section className="mb-6">
        <h2 className="text-lg font-medium mb-3">工具开关</h2>
        <div className="space-y-2">
          {settings.available_tools.map((t) => (
            <label key={t.tool_name} className="flex items-center gap-2">
              <input
                type="checkbox"
                checked={settings.enabled_tools.includes(t.tool_name)}
                onChange={(e) => {
                  const tools = e.target.checked
                    ? [...settings.enabled_tools, t.tool_name]
                    : settings.enabled_tools.filter((x) => x !== t.tool_name);
                  setSettings({ ...settings, enabled_tools: tools });
                }}
              />
              <span className="text-sm">{t.display_name}</span>
              <span className="text-xs text-secondary">{t.description}</span>
            </label>
          ))}
        </div>
      </section>
      <button
        onClick={handleSave}
        className="rounded-md bg-primary px-4 py-2 text-sm text-white hover:bg-primary-hover"
        aria-label="保存设置"
      >
        保存
      </button>
    </div>
  );
}