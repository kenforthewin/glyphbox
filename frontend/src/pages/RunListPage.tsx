import { useState } from "react";
import { useSearchParams } from "react-router-dom";
import { PageShell } from "../components/layout/PageShell";
import { Header } from "../components/layout/Header";
import { RunTable } from "../components/runs/RunTable";
import { RunFilterBar } from "../components/runs/RunFilterBar";
import { useRuns } from "../hooks/useRuns";

export function RunListPage() {
  const [searchParams] = useSearchParams();
  const [sortBy, setSortBy] = useState<"recent" | "score" | "depth">("recent");
  const [model, setModel] = useState(searchParams.get("model") ?? "");

  const { runs, loading, error } = useRuns({
    sortBy,
    model: model || undefined,
  });

  return (
    <PageShell>
      <Header />
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
