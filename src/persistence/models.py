"""Data models for agent turn and run persistence."""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass
class UserRecord:
    """A registered user (via OpenRouter OAuth)."""

    openrouter_id: str
    display_name: str = ""
    email: str | None = None
    avatar_url: str | None = None
    encrypted_openrouter_key: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
    id: int | None = None

    def to_public_dict(self) -> dict[str, Any]:
        """Public-safe representation (no encrypted key)."""
        return {
            "id": self.id,
            "openrouter_id": self.openrouter_id,
            "display_name": self.display_name,
            "avatar_url": self.avatar_url,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


@dataclass
class TurnRecord:
    """Complete record of a single agent turn.

    Contains everything needed to replay what happened:
    what the agent saw, what it thought, what it did, and what resulted.
    """

    # Identity
    run_id: str
    turn_number: int  # Agent decision counter (sequential)
    game_turn: int  # NLE game turn (from Stats.turn)
    timestamp: datetime

    # Game state (pre-decision snapshot)
    game_screen: str  # Full 24x80 ASCII screen
    player_x: int
    player_y: int
    hp: int
    max_hp: int
    dungeon_level: int
    depth: int
    xp_level: int
    score: int
    hunger: str
    game_message: str

    # LLM interaction
    llm_reasoning: str
    llm_model: str

    # Decision
    action_type: str  # ActionType.value

    # LLM token usage (nullable)
    llm_prompt_tokens: int | None = None
    llm_completion_tokens: int | None = None
    llm_total_tokens: int | None = None
    llm_finish_reason: str | None = None

    code: str | None = None
    skill_name: str | None = None

    # Execution result
    execution_success: bool = True
    execution_error: str | None = None
    execution_time_ms: int | None = None
    game_messages: list[str] = field(default_factory=list)
    api_calls: list[dict] = field(default_factory=list)

    # Extended game state (captured per-turn for web UI)
    inventory: list[dict] | None = None
    dungeon_overview: str | None = None

    # Storage identity (set by repository)
    id: int | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "run_id": self.run_id,
            "turn_number": self.turn_number,
            "game_turn": self.game_turn,
            "timestamp": self.timestamp.isoformat(),
            "game_screen": self.game_screen,
            "player_x": self.player_x,
            "player_y": self.player_y,
            "hp": self.hp,
            "max_hp": self.max_hp,
            "dungeon_level": self.dungeon_level,
            "depth": self.depth,
            "xp_level": self.xp_level,
            "score": self.score,
            "hunger": self.hunger,
            "game_message": self.game_message,
            "llm_reasoning": self.llm_reasoning,
            "llm_model": self.llm_model,
            "llm_prompt_tokens": self.llm_prompt_tokens,
            "llm_completion_tokens": self.llm_completion_tokens,
            "llm_total_tokens": self.llm_total_tokens,
            "llm_finish_reason": self.llm_finish_reason,
            "action_type": self.action_type,
            "code": self.code,
            "skill_name": self.skill_name,
            "execution_success": self.execution_success,
            "execution_error": self.execution_error,
            "execution_time_ms": self.execution_time_ms,
            "game_messages": self.game_messages,
            "api_calls": self.api_calls,
            "inventory": self.inventory,
            "dungeon_overview": self.dungeon_overview,
        }


@dataclass
class RunRecord:
    """Metadata for a complete agent run (episode)."""

    # Identity
    run_id: str
    started_at: datetime
    ended_at: datetime | None = None

    # Configuration snapshot
    model: str = ""
    provider: str = ""
    config_snapshot: dict | None = None

    # Outcome
    end_reason: str = ""
    final_score: int = 0
    final_game_turns: int = 0
    final_depth: int = 0
    final_xp_level: int = 0
    total_agent_turns: int = 0
    total_llm_tokens: int = 0

    # Live tracking
    status: str = "running"

    # Multi-user
    user_id: int | None = None
    visibility: str = "public"

    # Populated from JOIN with users table (not stored in runs)
    username: str = ""

    # Storage identity (set by repository)
    id: int | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "run_id": self.run_id,
            "started_at": self.started_at.isoformat(),
            "ended_at": self.ended_at.isoformat() if self.ended_at else None,
            "model": self.model,
            "provider": self.provider,
            "config_snapshot": self.config_snapshot,
            "end_reason": self.end_reason,
            "final_score": self.final_score,
            "final_game_turns": self.final_game_turns,
            "final_depth": self.final_depth,
            "final_xp_level": self.final_xp_level,
            "total_agent_turns": self.total_agent_turns,
            "total_llm_tokens": self.total_llm_tokens,
            "status": self.status,
            "user_id": self.user_id,
            "visibility": self.visibility,
            "username": self.username,
        }
