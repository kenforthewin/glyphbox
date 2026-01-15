"""
Data models for the skill system.

These dataclasses represent skills, their execution history,
and performance statistics.
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Optional


class SkillCategory(Enum):
    """Categories for organizing skills."""

    EXPLORATION = "exploration"
    COMBAT = "combat"
    RESOURCE = "resource"
    NAVIGATION = "navigation"
    INTERACTION = "interaction"
    UTILITY = "utility"
    CUSTOM = "custom"

    @classmethod
    def from_string(cls, value: str) -> "SkillCategory":
        """Convert string to SkillCategory."""
        try:
            return cls(value.lower())
        except ValueError:
            return cls.CUSTOM


@dataclass
class SkillMetadata:
    """Metadata about a skill."""

    description: str = ""
    category: SkillCategory = SkillCategory.CUSTOM
    stops_when: list[str] = field(default_factory=list)
    author: str = "agent"  # "agent" for generated, "human" for hand-written
    version: int = 1
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    tags: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        """Convert to dictionary for serialization."""
        return {
            "description": self.description,
            "category": self.category.value,
            "stops_when": self.stops_when,
            "author": self.author,
            "version": self.version,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "tags": self.tags,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "SkillMetadata":
        """Create from dictionary."""
        return cls(
            description=data.get("description", ""),
            category=SkillCategory.from_string(data.get("category", "custom")),
            stops_when=data.get("stops_when", []),
            author=data.get("author", "agent"),
            version=data.get("version", 1),
            created_at=datetime.fromisoformat(data["created_at"]) if data.get("created_at") else None,
            updated_at=datetime.fromisoformat(data["updated_at"]) if data.get("updated_at") else None,
            tags=data.get("tags", []),
        )


@dataclass
class Skill:
    """A skill definition."""

    name: str
    code: str
    metadata: SkillMetadata = field(default_factory=SkillMetadata)
    file_path: Optional[str] = None  # Path if loaded from file

    @property
    def category(self) -> SkillCategory:
        """Get skill category."""
        return self.metadata.category

    @property
    def description(self) -> str:
        """Get skill description."""
        return self.metadata.description

    def to_dict(self) -> dict:
        """Convert to dictionary for serialization."""
        return {
            "name": self.name,
            "code": self.code,
            "metadata": self.metadata.to_dict(),
            "file_path": self.file_path,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Skill":
        """Create from dictionary."""
        return cls(
            name=data["name"],
            code=data["code"],
            metadata=SkillMetadata.from_dict(data.get("metadata", {})),
            file_path=data.get("file_path"),
        )


@dataclass
class GameStateSnapshot:
    """Snapshot of game state at a point in time."""

    turn: int
    hp: int
    max_hp: int
    dungeon_level: int
    position_x: int
    position_y: int
    gold: int
    xp_level: int
    monsters_visible: int = 0
    monsters_adjacent: int = 0

    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "turn": self.turn,
            "hp": self.hp,
            "max_hp": self.max_hp,
            "dungeon_level": self.dungeon_level,
            "position_x": self.position_x,
            "position_y": self.position_y,
            "gold": self.gold,
            "xp_level": self.xp_level,
            "monsters_visible": self.monsters_visible,
            "monsters_adjacent": self.monsters_adjacent,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "GameStateSnapshot":
        """Create from dictionary."""
        return cls(**data)

    @classmethod
    def from_api(cls, api: Any) -> "GameStateSnapshot":
        """Create snapshot from NetHackAPI instance."""
        stats = api.get_stats()
        monsters = api.get_visible_monsters()
        adjacent = api.get_adjacent_monsters()

        return cls(
            turn=stats.turn,
            hp=stats.hp,
            max_hp=stats.max_hp,
            dungeon_level=stats.dungeon_level,
            position_x=stats.position.x,
            position_y=stats.position.y,
            gold=stats.gold,
            xp_level=stats.xp_level,
            monsters_visible=len(monsters),
            monsters_adjacent=len(adjacent),
        )


@dataclass
class SkillExecution:
    """Record of a skill execution."""

    skill_name: str
    params: dict[str, Any]
    started_at: datetime
    ended_at: Optional[datetime] = None
    success: bool = False
    stopped_reason: str = ""
    result_data: dict[str, Any] = field(default_factory=dict)
    actions_taken: int = 0
    turns_elapsed: int = 0
    error: Optional[str] = None
    state_before: Optional[GameStateSnapshot] = None
    state_after: Optional[GameStateSnapshot] = None

    @property
    def duration_seconds(self) -> float:
        """Get execution duration in seconds."""
        if self.ended_at and self.started_at:
            return (self.ended_at - self.started_at).total_seconds()
        return 0.0

    def to_dict(self) -> dict:
        """Convert to dictionary for storage."""
        return {
            "skill_name": self.skill_name,
            "params": self.params,
            "started_at": self.started_at.isoformat(),
            "ended_at": self.ended_at.isoformat() if self.ended_at else None,
            "success": self.success,
            "stopped_reason": self.stopped_reason,
            "result_data": self.result_data,
            "actions_taken": self.actions_taken,
            "turns_elapsed": self.turns_elapsed,
            "error": self.error,
            "state_before": self.state_before.to_dict() if self.state_before else None,
            "state_after": self.state_after.to_dict() if self.state_after else None,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "SkillExecution":
        """Create from dictionary."""
        return cls(
            skill_name=data["skill_name"],
            params=data.get("params", {}),
            started_at=datetime.fromisoformat(data["started_at"]),
            ended_at=datetime.fromisoformat(data["ended_at"]) if data.get("ended_at") else None,
            success=data.get("success", False),
            stopped_reason=data.get("stopped_reason", ""),
            result_data=data.get("result_data", {}),
            actions_taken=data.get("actions_taken", 0),
            turns_elapsed=data.get("turns_elapsed", 0),
            error=data.get("error"),
            state_before=GameStateSnapshot.from_dict(data["state_before"]) if data.get("state_before") else None,
            state_after=GameStateSnapshot.from_dict(data["state_after"]) if data.get("state_after") else None,
        )


@dataclass
class SkillStatistics:
    """Statistics for a skill's performance."""

    skill_name: str
    total_executions: int = 0
    successful_executions: int = 0
    failed_executions: int = 0
    total_actions: int = 0
    total_turns: int = 0
    stop_reasons: dict[str, int] = field(default_factory=dict)
    avg_actions_per_execution: float = 0.0
    avg_turns_per_execution: float = 0.0
    last_executed: Optional[datetime] = None

    @property
    def success_rate(self) -> float:
        """Get success rate as fraction (0.0 to 1.0)."""
        if self.total_executions == 0:
            return 0.0
        return self.successful_executions / self.total_executions

    def record_execution(self, execution: SkillExecution) -> None:
        """Update statistics with a new execution."""
        self.total_executions += 1
        self.total_actions += execution.actions_taken
        self.total_turns += execution.turns_elapsed
        self.last_executed = execution.ended_at or datetime.now()

        if execution.success:
            self.successful_executions += 1
        else:
            self.failed_executions += 1

        # Track stop reasons
        if execution.stopped_reason:
            self.stop_reasons[execution.stopped_reason] = (
                self.stop_reasons.get(execution.stopped_reason, 0) + 1
            )

        # Update averages
        if self.total_executions > 0:
            self.avg_actions_per_execution = self.total_actions / self.total_executions
            self.avg_turns_per_execution = self.total_turns / self.total_executions

    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "skill_name": self.skill_name,
            "total_executions": self.total_executions,
            "successful_executions": self.successful_executions,
            "failed_executions": self.failed_executions,
            "total_actions": self.total_actions,
            "total_turns": self.total_turns,
            "stop_reasons": self.stop_reasons,
            "avg_actions_per_execution": self.avg_actions_per_execution,
            "avg_turns_per_execution": self.avg_turns_per_execution,
            "last_executed": self.last_executed.isoformat() if self.last_executed else None,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "SkillStatistics":
        """Create from dictionary."""
        stats = cls(
            skill_name=data["skill_name"],
            total_executions=data.get("total_executions", 0),
            successful_executions=data.get("successful_executions", 0),
            failed_executions=data.get("failed_executions", 0),
            total_actions=data.get("total_actions", 0),
            total_turns=data.get("total_turns", 0),
            stop_reasons=data.get("stop_reasons", {}),
            avg_actions_per_execution=data.get("avg_actions_per_execution", 0.0),
            avg_turns_per_execution=data.get("avg_turns_per_execution", 0.0),
        )
        if data.get("last_executed"):
            stats.last_executed = datetime.fromisoformat(data["last_executed"])
        return stats
