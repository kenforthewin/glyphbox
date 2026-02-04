import type {
  ListRunsParams,
  ModelInfo,
  ModelLeaderboardEntry,
  RunRecord,
  StartRunRequest,
  StartRunResponse,
  TurnRecord,
  TurnsResponse,
  UserRecord,
} from "../types/api";
import { ENDPOINTS } from "./endpoints";

async function fetchJson<T>(
  url: string,
  params?: Record<string, string | number>,
  init?: RequestInit,
): Promise<T> {
  const searchParams = new URLSearchParams();
  if (params) {
    for (const [k, v] of Object.entries(params)) {
      if (v !== undefined && v !== null && v !== "") {
        searchParams.set(k, String(v));
      }
    }
  }
  const fullUrl = searchParams.toString() ? `${url}?${searchParams}` : url;
  const res = await fetch(fullUrl, { credentials: "include", ...init });
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
  return res.json();
}

export const api = {
  // Runs
  listRuns: (params: ListRunsParams = {}) =>
    fetchJson<RunRecord[]>(ENDPOINTS.runs, {
      limit: params.limit ?? 50,
      offset: params.offset ?? 0,
      ...(params.sort_by ? { sort_by: params.sort_by } : {}),
      ...(params.model ? { model: params.model } : {}),
      ...(params.user_id !== undefined ? { user_id: params.user_id } : {}),
    } as Record<string, string | number>),

  getRun: (runId: string) => fetchJson<RunRecord>(ENDPOINTS.run(runId)),

  startRun: (config: StartRunRequest) =>
    fetchJson<StartRunResponse>(ENDPOINTS.runs, undefined, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(config),
    }),

  stopRun: (runId: string) =>
    fetchJson<{ ok: boolean }>(ENDPOINTS.stopRun(runId), undefined, {
      method: "POST",
    }),

  // Turns
  getTurns: (runId: string, after = 0, limit = 500) =>
    fetchJson<TurnsResponse>(ENDPOINTS.turns(runId), { after, limit }),

  getTurn: (runId: string, turnNumber: number) =>
    fetchJson<TurnRecord>(ENDPOINTS.turn(runId, turnNumber)),

  getLatestTurn: (runId: string) =>
    fetchJson<TurnRecord>(ENDPOINTS.latestTurn(runId)),

  // Models (OpenRouter - requires auth)
  listModels: () => fetchJson<ModelInfo[]>(ENDPOINTS.models),

  // Run models (distinct models from existing runs - no auth)
  getRunModels: () => fetchJson<string[]>(ENDPOINTS.runModels),

  // Leaderboard
  getLeaderboard: (sortBy: "best_score" | "avg_score" | "best_depth" = "best_score", limit = 50) =>
    fetchJson<ModelLeaderboardEntry[]>(ENDPOINTS.leaderboard, { sort_by: sortBy, limit }),

  // Auth
  getMe: () => fetchJson<UserRecord>("/api/auth/me"),

  logout: () =>
    fetchJson<{ ok: boolean }>("/api/auth/logout", undefined, {
      method: "POST",
    }),

  updateProfile: (data: { display_name: string }) =>
    fetchJson<UserRecord>("/api/auth/me", undefined, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(data),
    }),
};
