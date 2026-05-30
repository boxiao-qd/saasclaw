
interface ModelSelectorProps {
  models: { model_id: string; name: string; description?: string }[];
  currentModel?: string;
  onChange: (modelId: string) => void;
}

export function ModelSelector({ models, currentModel, onChange }: ModelSelectorProps) {
  return (
    <select
      value={currentModel || ""}
      onChange={(e) => onChange(e.target.value)}
      className="rounded-md border border-border px-3 py-2 text-sm w-full"
      aria-label="选择模型"
    >
      <option value="">默认模型</option>
      {models.map((m) => (
        <option key={m.model_id} value={m.model_id}>{m.name}</option>
      ))}
    </select>
  );
}