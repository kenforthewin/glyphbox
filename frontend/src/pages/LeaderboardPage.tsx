import { useState, useEffect } from "react";
import { Link } from "react-router-dom";
import { PageShell } from "../components/layout/PageShell";
import { Header } from "../components/layout/Header";
import type { ModelLeaderboardEntry } from "../types/api";
import { api } from "../api/client";

type SortBy = "best_score" | "avg_score" | "best_depth";

const SORT_OPTIONS: { key: SortBy; label: string }[] = [
  { key: "best_score", label: "Best Score" },
  { key: "avg_score", label: "Avg Score" },
  { key: "best_depth", label: "Best Depth" },
];

export function LeaderboardPage() {
  const [sortBy, setSortBy] = useState<SortBy>("best_score");
  const [entries, setEntries] = useState<ModelLeaderboardEntry[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setLoading(true);
    api
      .getLeaderboard(sortBy, 50)
      .then(setEntries)
      .catch(() => {})
      .finally(() => setLoading(false));
  }, [sortBy]);

  return (
    <PageShell>
      <Header />
      <h2 className="mb-4 font-mono text-lg font-medium text-text-primary">
        Leaderboard
      </h2>

      <div className="mb-4 flex gap-1">
        {SORT_OPTIONS.map((opt) => (
          <button
            key={opt.key}
            onClick={() => setSortBy(opt.key)}
            className={`rounded px-3 py-1.5 text-xs font-medium ${
              sortBy === opt.key
                ? "bg-bg-tertiary text-text-primary border border-border-bright"
                : "bg-bg-secondary text-text-muted border border-transparent hover:text-text-secondary"
            }`}
          >
            {opt.label}
          </button>
        ))}
      </div>

      {loading ? (
        <div className="py-12 text-center text-text-muted">Loading...</div>
      ) : entries.length === 0 ? (
        <div className="py-12 text-center text-text-muted">
          No completed runs yet.
        </div>
      ) : (
        <div className="panel overflow-hidden">
          <div className="grid grid-cols-[40px_1fr_90px_90px_90px_60px] gap-2 border-b border-border-bright px-3 py-2 text-xs font-medium uppercase tracking-wider text-text-muted">
            <span>#</span>
            <span>Model</span>
            <span className="text-right">Best Score</span>
            <span className="text-right">Avg Score</span>
            <span className="text-right">Best Depth</span>
            <span className="text-right">Runs</span>
          </div>
          {entries.map((entry, i) => (
            <Link
              key={entry.model}
              to={`/runs?model=${encodeURIComponent(entry.model)}`}
              className="grid grid-cols-[40px_1fr_90px_90px_90px_60px] items-center gap-2 border-b border-border-dim px-3 py-2 text-sm hover:bg-bg-tertiary"
            >
              <span className="font-mono text-text-muted">{i + 1}</span>
              <span className="truncate text-text-secondary">
                {entry.model}
              </span>
              <span
                className={`text-right font-mono ${sortBy === "best_score" ? "text-text-primary font-medium" : "text-text-muted"}`}
              >
                {entry.best_score}
              </span>
              <span
                className={`text-right font-mono ${sortBy === "avg_score" ? "text-text-primary font-medium" : "text-text-muted"}`}
              >
                {entry.avg_score}
              </span>
              <span
                className={`text-right font-mono ${sortBy === "best_depth" ? "text-text-primary font-medium" : "text-text-muted"}`}
              >
                D:{entry.best_depth}
              </span>
              <span className="text-right font-mono text-text-muted">
                {entry.run_count}
              </span>
            </Link>
          ))}
        </div>
      )}
    </PageShell>
  );
}
