import { useState, useEffect, useRef } from "react";
import type { RunRecord } from "../types/api";
import { api } from "../api/client";

const TERMINAL_STATUSES = new Set(["stopped", "error", "completed"]);

export function useRun(runId: string) {
  const [run, setRun] = useState<RunRecord | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<Error | null>(null);
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(() => {
    setLoading(true);
    api
      .getRun(runId)
      .then((data) => {
        setRun(data);
        setError(null);
      })
      .catch((e) => setError(e instanceof Error ? e : new Error(String(e))))
      .finally(() => setLoading(false));
  }, [runId]);

  // Poll while run is in a non-terminal status (e.g. "starting" -> "running")
  useEffect(() => {
    if (!run || TERMINAL_STATUSES.has(run.status)) {
      return;
    }

    intervalRef.current = setInterval(() => {
      api
        .getRun(runId)
        .then((data) => setRun(data))
        .catch(() => {});
    }, 3000);

    return () => {
      if (intervalRef.current) clearInterval(intervalRef.current);
    };
  }, [runId, run?.status]);

  return { run, loading, error, setRun };
}
