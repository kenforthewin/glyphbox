import { useState, useEffect, useCallback } from "react";
import type { TurnRecord } from "../types/api";
import { api } from "../api/client";

export function useTurns(runId: string) {
  const [turns, setTurns] = useState<TurnRecord[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<Error | null>(null);

  const fetchAll = useCallback(async () => {
    setLoading(true);
    try {
      let allTurns: TurnRecord[] = [];
      let after = 0;
      // eslint-disable-next-line no-constant-condition
      while (true) {
        const batch = await api.getTurns(runId, after, 500);
        allTurns = [...allTurns, ...batch.turns];
        setTotal(batch.total);
        if (batch.turns.length < 500) break;
        const lastTurn = batch.turns[batch.turns.length - 1];
        if (lastTurn) after = lastTurn.turn_number;
      }
      setTurns(allTurns);
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e : new Error(String(e)));
    } finally {
      setLoading(false);
    }
  }, [runId]);

  useEffect(() => {
    fetchAll();
  }, [fetchAll]);

  return { turns, total, loading, error, refetch: fetchAll };
}
