import { useState } from "react";
import { Link } from "react-router-dom";
import type { RunRecord } from "../../types/api";
import { useAuth } from "../../hooks/useAuth";
import { api } from "../../api/client";
import { StatusBadge } from "./StatusBadge";

interface RunRowProps {
  run: RunRecord;
}

function formatTime(iso: string): string {
  return new Date(iso).toLocaleString(undefined, {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

export function RunRow({ run }: RunRowProps) {
  const { user } = useAuth();
  const [stopping, setStopping] = useState(false);
  const isActive = run.status === "running";
  const isOwner = user !== null && run.user_id === user.id;

  const handleStop = async (e: React.MouseEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setStopping(true);
    try {
      await api.stopRun(run.run_id);
    } catch {
      // ignore — next poll will reflect status
    } finally {
      setStopping(false);
    }
  };

  return (
    <Link
      to={`/runs/${run.run_id}`}
      className={`grid grid-cols-[80px_100px_1fr_140px_60px_60px_60px_50px] items-center gap-2 border-b border-border-dim px-3 py-2 text-sm hover:bg-bg-tertiary ${
        isActive ? "border-l-2 border-l-accent-amber bg-bg-secondary" : ""
      }`}
    >
      <StatusBadge status={run.status} />
      <span className="truncate text-xs text-text-secondary">
        {run.username && run.user_id ? (
          <span
            onClick={(e) => {
              e.preventDefault();
              e.stopPropagation();
              window.location.href = `/users/${run.user_id}`;
            }}
            className="cursor-pointer hover:text-text-primary"
          >
            {run.username}
          </span>
        ) : (
          <span className="text-text-muted">--</span>
        )}
      </span>
      <span className="truncate text-text-secondary">{run.model}</span>
      <span className="text-text-muted">{formatTime(run.started_at)}</span>
      <span className="text-right font-mono text-text-primary">
        {run.final_score}
      </span>
      <span className="text-right font-mono text-text-secondary">
        D:{run.final_depth}
      </span>
      <span className="text-right font-mono text-text-muted">
        {run.total_agent_turns}
      </span>
      <span className="text-right">
        {isActive && isOwner && (
          <button
            onClick={handleStop}
            disabled={stopping}
            className="rounded border border-accent-red/50 px-1.5 py-0.5 text-[10px] text-accent-red hover:bg-accent-red/10 disabled:opacity-50"
          >
            {stopping ? "..." : "Stop"}
          </button>
        )}
      </span>
    </Link>
  );
}
