import { Navigate } from "react-router-dom";
import { PageShell } from "../components/layout/PageShell";
import { Header } from "../components/layout/Header";
import { useRuns } from "../hooks/useRuns";

export function FeaturedPage() {
  const { runs, loading } = useRuns({ limit: 50, pollInterval: 0 });

  if (loading) {
    return (
      <PageShell>
        <Header />
        <div className="py-12 text-center text-text-muted">Loading...</div>
      </PageShell>
    );
  }

  if (runs.length === 0) {
    return <Navigate to="/runs" replace />;
  }

  // Prefer most recent running run, fall back to most recent overall
  const byRecent = [...runs].sort(
    (a, b) =>
      new Date(b.started_at).getTime() - new Date(a.started_at).getTime(),
  );
  const running = byRecent.find(
    (r) => r.status === "running" || r.status === "starting",
  );
  const featured = running ?? byRecent[0];

  return <Navigate to={`/runs/${featured.run_id}`} replace />;
}
