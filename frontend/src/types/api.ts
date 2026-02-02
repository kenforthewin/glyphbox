export interface UserRecord {
  id: number;
  openrouter_id: string;
  display_name: string;
  avatar_url: string | null;
  created_at: string | null;
}

export interface RunRecord {
  id: number;
  run_id: string;
  started_at: string;
  ended_at: string | null;
  model: string;
  provider: string;
  config_snapshot: Record<string, unknown> | null;
  end_reason: string;
  final_score: number;
  final_game_turns: number;
  final_depth: number;
  final_xp_level: number;
  total_agent_turns: number;
  total_llm_tokens: number;
  status: "running" | "stopped" | "error";
  user_id: number | null;
  visibility: string;
  username: string;
}

export interface ApiCall {
  method: string;
  args: unknown[] | string;
  success: boolean;
  error?: string;
}

export interface TurnRecord {
  id: number;
  run_id: string;
  turn_number: number;
  game_turn: number;
  timestamp: string;
  game_screen: string;
  player_x: number;
  player_y: number;
  hp: number;
  max_hp: number;
  dungeon_level: number;
  depth: number;
  xp_level: number;
  score: number;
  hunger: string;
  game_message: string;
  llm_reasoning: string;
  llm_model: string;
  llm_prompt_tokens: number | null;
  llm_completion_tokens: number | null;
  llm_total_tokens: number | null;
  llm_finish_reason: string | null;
  action_type: string;
  code: string | null;
  skill_name: string | null;
  execution_success: boolean;
  execution_error: string | null;
  execution_time_ms: number | null;
  game_messages: string[];
  api_calls: ApiCall[];
  inventory: { slot: string; name: string; quantity: number }[] | null;
  dungeon_overview: string | null;
}

export interface TurnsResponse {
  run_id: string;
  turns: TurnRecord[];
  total: number;
}

export interface StartRunRequest {
  model: string;
  character: string;
  temperature: number;
  reasoning: string;
  max_turns: number;
}

export interface StartRunResponse {
  run_id: string;
  status: string;
}

export interface ModelInfo {
  id: string;
  name: string;
  context_length: number;
  pricing: {
    prompt: string;
    completion: string;
  };
}

export interface ListRunsParams {
  limit?: number;
  offset?: number;
  sort_by?: "recent" | "score" | "depth";
  model?: string;
  user_id?: number;
}

export type WsMessage =
  | { type: "turn"; data: TurnRecord }
  | { type: "run_ended"; data: RunRecord }
  | { type: "error"; message: string };
