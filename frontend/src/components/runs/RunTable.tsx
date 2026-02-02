import type { RunRecord } from "../../types/api";
import { RunRow } from "./RunRow";

interface RunTableProps {
  runs: RunRecord[];
  loading: boolean;
  error: Error | null;
}

export function RunTable({ runs, loading, error }: RunTableProps) {
  if (loading && runs.length === 0) {
    return (
      <div className="py-12 text-center text-text-muted">Loading runs...</div>
    );
  }

  if (error) {
    return (
      <div className="py-12 text-center text-accent-red">
        Error: {error.message}
      </div>
    );
  }

  if (runs.length === 0) {
    return (
      <div className="py-12 text-center text-text-muted">No runs found.</div>
    );
  }

  return (
    <div className="panel overflow-hidden">
      <div className="grid grid-cols-[80px_100px_1fr_140px_60px_60px_60px_50px] gap-2 border-b border-border-bright px-3 py-2 text-xs font-medium uppercase tracking-wider text-text-muted">
        <span>Status</span>
        <span>User</span>
        <span>Model</span>
        <span>Started</span>
        <span className="text-right">Score</span>
        <span className="text-right">Depth</span>
        <span className="text-right">Turns</span>
        <span></span>
      </div>
      {runs.map((run) => (
        <RunRow key={run.run_id} run={run} />
      ))}
    </div>
  );
}
