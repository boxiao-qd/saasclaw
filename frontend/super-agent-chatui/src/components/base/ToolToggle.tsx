
interface ToolToggleProps {
  toolName: string;
  displayName: string;
  description?: string;
  enabled: boolean;
  onToggle: (enabled: boolean) => void;
}

export function ToolToggle({ toolName, displayName, description, enabled, onToggle }: ToolToggleProps) {
  return (
    <label className="flex items-center gap-3 py-1" data-tool-name={toolName}>
      <input
        type="checkbox"
        checked={enabled}
        onChange={(e) => onToggle(e.target.checked)}
        className="rounded border-border"
        aria-label={`${enabled ? "禁用" : "启用"} ${displayName}`}
      />
      <div>
        <span className="text-sm">{displayName}</span>
        {description && <span className="text-xs text-secondary ml-2">{description}</span>}
      </div>
    </label>
  );
}