import { useParams } from "react-router-dom";
import { PageShell } from "../components/layout/PageShell";
import { Header } from "../components/layout/Header";
import { RunTable } from "../components/runs/RunTable";
import { useRuns } from "../hooks/useRuns";

export function UserProfilePage() {
  const { userId } = useParams<{ userId: string }>();
  const numericUserId = userId ? parseInt(userId, 10) : undefined;

  const { runs, loading, error } = useRuns({
    userId: numericUserId,
  });

  const username =
    runs.length > 0 && runs[0].username ? runs[0].username : `User ${userId}`;

  return (
    <PageShell>
      <Header />
      <h2 className="mb-4 font-mono text-lg font-medium text-text-primary">
        {loading ? "Loading..." : username}
      </h2>
      <RunTable runs={runs} loading={loading} error={error} />
    </PageShell>
  );
}
