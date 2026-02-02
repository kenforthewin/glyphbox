import { useState } from "react";
import { Link } from "react-router-dom";
import { PageShell } from "../components/layout/PageShell";
import { Header } from "../components/layout/Header";
import { RunTable } from "../components/runs/RunTable";
import { RunFilterBar } from "../components/runs/RunFilterBar";
import { useRuns } from "../hooks/useRuns";
import { useAuth } from "../hooks/useAuth";

export function RunListPage() {
  const { isAuthenticated } = useAuth();
  const [sortBy, setSortBy] = useState<"recent" | "score" | "depth">("recent");
  const [model, setModel] = useState("");

  const { runs, loading, error } = useRuns({
    sortBy,
    model: model || undefined,
  });

  return (
    <PageShell>
      <Header>
        {isAuthenticated && (
          <Link
            to="/new"
            className="rounded bg-accent-green px-2 py-1 text-xs font-medium text-bg-primary hover:bg-accent-green/80"
          >
            New Run
          </Link>
        )}
      </Header>
      <RunFilterBar
        sortBy={sortBy}
        model={model}
        onSortChange={setSortBy}
        onModelChange={setModel}
      />
      <RunTable runs={runs} loading={loading} error={error} />
    </PageShell>
  );
}
