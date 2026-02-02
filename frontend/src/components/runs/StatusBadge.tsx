import type { RunRecord } from "../../types/api";

const STATUS_STYLES: Record<RunRecord["status"], string> = {
  running: "bg-accent-amber/15 text-accent-amber border-accent-amber/30",
  stopped: "bg-accent-green/15 text-accent-green border-accent-green/30",
  error: "bg-accent-red/15 text-accent-red border-accent-red/30",
};

const STATUS_LABELS: Record<RunRecord["status"], string> = {
  running: "Running",
  stopped: "Stopped",
  error: "Error",
};

interface StatusBadgeProps {
  status: RunRecord["status"];
}

export function StatusBadge({ status }: StatusBadgeProps) {
  return (
    <span
      className={`inline-block rounded border px-1.5 py-0.5 text-xs font-medium ${STATUS_STYLES[status]}`}
    >
      {STATUS_LABELS[status]}
    </span>
  );
}
