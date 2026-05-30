import { useSSEStore } from "@/store/sse-store";

export function SSEStatusBar() {
  const { connected, reconnecting, errorCount } = useSSEStore();

  let statusText = "OFFLINE";
  let dotColor = "bg-[var(--color-text-tertiary)]";
  if (connected) {
    statusText = "CONNECTED";
    dotColor = "bg-[var(--color-success)]";
  } else if (reconnecting) {
    statusText = "RECONNECTING";
    dotColor = "bg-[var(--color-warning)] animate-pulse-cyan";
  } else if (errorCount > 0) {
    statusText = `ERROR (${errorCount})`;
    dotColor = "bg-[var(--color-error)]";
  }

  return (
    <div className="h-5 px-4 flex items-center justify-end text-[0.65rem] font-mono" role="status" aria-live="polite">
      <span className={`w-1.5 h-1.5 rounded-full ${dotColor} mr-1.5`} />
      <span className="text-[var(--color-text-tertiary)]">{statusText}</span>
    </div>
  );
}