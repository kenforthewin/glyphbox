import { useState, useEffect, useCallback } from "react";
import type { RunRecord, ListRunsParams } from "../types/api";
import { api } from "../api/client";

interface UseRunsOptions {
  limit?: number;
  pollInterval?: number;
  sortBy?: "recent" | "score" | "depth";
  model?: string;
  userId?: number;
}

export function useRuns(options: UseRunsOptions = {}) {
  const { limit = 50, pollInterval = 5000, sortBy, model, userId } = options;
  const [runs, setRuns] = useState<RunRecord[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<Error | null>(null);

  const refresh = useCallback(async () => {
    try {
      const params: ListRunsParams = { limit };
      if (sortBy) params.sort_by = sortBy;
      if (model) params.model = model;
      if (userId !== undefined) params.user_id = userId;
      const data = await api.listRuns(params);
      setRuns(data);
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e : new Error(String(e)));
    } finally {
      setLoading(false);
    }
  }, [limit, sortBy, model, userId]);

  useEffect(() => {
    refresh();
    if (pollInterval > 0) {
      const id = setInterval(refresh, pollInterval);
      return () => clearInterval(id);
    }
  }, [refresh, pollInterval]);

  return { runs, loading, error, refresh };
}
