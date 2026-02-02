import { useState, useEffect } from "react";
import { Link } from "react-router-dom";
import { PageShell } from "../components/layout/PageShell";
import { Header } from "../components/layout/Header";
import type { RunRecord } from "../types/api";
import { api } from "../api/client";

type Metric = "score" | "depth";

function formatTime(iso: string): string {
  return new Date(iso).toLocaleString(undefined, {
    month: "short",
    day: "numeric",
    year: "numeric",
  });
}

export function LeaderboardPage() {
  const [metric, setMetric] = useState<Metric>("score");
  const [runs, setRuns] = useState<RunRecord[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setLoading(true);
    api
      .getLeaderboard(metric, 50)
      .then(setRuns)
      .catch(() => {})
      .finally(() => setLoading(false));
  }, [metric]);

  return (
    <PageShell>
      <Header />
      <h2 className="mb-4 font-mono text-lg font-medium text-text-primary">
        Leaderboard
      </h2>

      <div className="mb-4 flex gap-1">
        {(["score", "depth"] as Metric[]).map((m) => (
          <button
            key={m}
            onClick={() => setMetric(m)}
            className={`rounded px-3 py-1.5 text-xs font-medium ${
              metric === m
                ? "bg-bg-tertiary text-text-primary border border-border-bright"
                : "bg-bg-secondary text-text-muted border border-transparent hover:text-text-secondary"
            }`}
          >
            {m === "score" ? "Highest Score" : "Deepest Descent"}
          </button>
        ))}
      </div>

      {loading ? (
        <div className="py-12 text-center text-text-muted">Loading...</div>
      ) : runs.length === 0 ? (
        <div className="py-12 text-center text-text-muted">
          No completed runs yet.
        </div>
      ) : (
        <div className="panel overflow-hidden">
          <div className="grid grid-cols-[50px_100px_1fr_70px_70px_70px_100px] gap-2 border-b border-border-bright px-3 py-2 text-xs font-medium uppercase tracking-wider text-text-muted">
            <span>#</span>
            <span>User</span>
            <span>Model</span>
            <span className="text-right">Score</span>
            <span className="text-right">Depth</span>
            <span className="text-right">Turns</span>
            <span>Date</span>
          </div>
          {runs.map((run, i) => (
            <Link
              key={run.run_id}
              to={`/runs/${run.run_id}`}
              className="grid grid-cols-[50px_100px_1fr_70px_70px_70px_100px] items-center gap-2 border-b border-border-dim px-3 py-2 text-sm hover:bg-bg-tertiary"
            >
              <span className="font-mono text-text-muted">{i + 1}</span>
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
              <span
                className={`text-right font-mono ${metric === "score" ? "text-text-primary font-medium" : "text-text-secondary"}`}
              >
                {run.final_score}
              </span>
              <span
                className={`text-right font-mono ${metric === "depth" ? "text-text-primary font-medium" : "text-text-secondary"}`}
              >
                D:{run.final_depth}
              </span>
              <span className="text-right font-mono text-text-muted">
                {run.total_agent_turns}
              </span>
              <span className="text-xs text-text-muted">
                {formatTime(run.started_at)}
              </span>
            </Link>
          ))}
        </div>
      )}
    </PageShell>
  );
}
