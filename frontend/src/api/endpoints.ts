const API_BASE = "/api";

export const ENDPOINTS = {
  runs: `${API_BASE}/runs`,
  run: (runId: string) => `${API_BASE}/runs/${runId}`,
  stopRun: (runId: string) => `${API_BASE}/runs/${runId}/stop`,
  turns: (runId: string) => `${API_BASE}/runs/${runId}/turns`,
  turn: (runId: string, turnNumber: number) =>
    `${API_BASE}/runs/${runId}/turns/${turnNumber}`,
  latestTurn: (runId: string) => `${API_BASE}/runs/${runId}/turns/latest`,
  models: `${API_BASE}/models`,
  runModels: `${API_BASE}/runs/models`,
  leaderboard: `${API_BASE}/leaderboard`,
  wsLive: (runId: string) => {
    const proto = location.protocol === "https:" ? "wss:" : "ws:";
    return `${proto}//${location.host}/ws/runs/${runId}/live`;
  },
} as const;
