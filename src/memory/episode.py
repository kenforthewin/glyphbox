"""
Episode memory for tracking game session state.

Coordinates all memory systems for a single game episode,
providing a unified interface for recording and querying
game history.
"""

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Optional

from .dungeon import DungeonMemory
from .manager import MemoryManager
from .working import WorkingMemory


@dataclass
class EpisodeEvent:
    """A significant event during an episode."""

    turn: int
    event_type: str
    description: str
    level_number: Optional[int] = None
    branch: Optional[str] = None
    position: Optional[tuple[int, int]] = None
    data: dict = field(default_factory=dict)


@dataclass
class EpisodeStatistics:
    """Statistics for a game episode."""

    episode_id: str
    started_at: datetime
    ended_at: Optional[datetime] = None
    end_reason: Optional[str] = None

    # Game stats
    final_score: int = 0
    final_turns: int = 0
    final_depth: int = 0
    final_xp_level: int = 1  # NetHack characters start at level 1
    death_reason: Optional[str] = None

    # Agent stats
    skills_used: int = 0
    skills_created: int = 0
    total_actions: int = 0

    # Combat stats
    monsters_killed: int = 0
    damage_dealt: int = 0
    damage_taken: int = 0

    # Exploration stats
    levels_visited: int = 0
    tiles_explored: int = 0

    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "episode_id": self.episode_id,
            "started_at": self.started_at.isoformat(),
            "ended_at": self.ended_at.isoformat() if self.ended_at else None,
            "end_reason": self.end_reason,
            "final_score": self.final_score,
            "final_turns": self.final_turns,
            "final_depth": self.final_depth,
            "final_xp_level": self.final_xp_level,
            "death_reason": self.death_reason,
            "skills_used": self.skills_used,
            "skills_created": self.skills_created,
            "total_actions": self.total_actions,
            "monsters_killed": self.monsters_killed,
            "damage_dealt": self.damage_dealt,
            "damage_taken": self.damage_taken,
            "levels_visited": self.levels_visited,
            "tiles_explored": self.tiles_explored,
        }


class EpisodeMemory:
    """
    Memory coordinator for a single game episode.

    Integrates working memory, dungeon memory, and persistent
    storage for comprehensive episode tracking.

    Example usage:
        episode = EpisodeMemory(db_path="data/memory.db")
        episode.start()

        # Each turn
        episode.update_state(stats, position, monsters, items)

        # Record events
        episode.record_event("levelup", "Reached level 2", turn=100)

        # Record skill usage
        episode.record_skill_execution("cautious_explore", success=True)

        # End episode
        episode.end("death", death_reason="killed by a grid bug")
    """

    def __init__(
        self,
        db_path: Optional[str] = None,
        episode_id: Optional[str] = None,
    ):
        """
        Initialize episode memory.

        Args:
            db_path: Path to SQLite database (uses default if not specified)
            episode_id: Optional episode ID (generated if not provided)
        """
        self.episode_id = episode_id or f"ep_{uuid.uuid4().hex[:12]}"

        # Memory systems
        self.working = WorkingMemory()
        self.dungeon = DungeonMemory()
        self._manager = MemoryManager(db_path) if db_path else None

        # Episode state
        self._started = False
        self._ended = False
        self._start_time: Optional[datetime] = None
        self._end_time: Optional[datetime] = None

        # Statistics tracking
        self._stats = EpisodeStatistics(
            episode_id=self.episode_id,
            started_at=datetime.now(),
        )

        # Event history (in-memory)
        self._events: list[EpisodeEvent] = []

        # Skill tracking
        self._skills_used: set[str] = set()
        self._skills_created: set[str] = set()
        self._skill_executions: int = 0

    def start(self) -> None:
        """Start the episode and create database record."""
        if self._started:
            return

        self._started = True
        self._start_time = datetime.now()
        self._stats.started_at = self._start_time

        # Create database record
        if self._manager:
            self._manager.initialize()
            self._manager.create_episode(
                self.episode_id,
                metadata={"start_time": self._start_time.isoformat()},
            )

        self.record_event("episode_start", "Episode started")

    def end(
        self,
        end_reason: str,
        final_score: int = 0,
        final_turns: int = 0,
        death_reason: Optional[str] = None,
    ) -> EpisodeStatistics:
        """
        End the episode.

        Args:
            end_reason: How episode ended ('death', 'ascension', 'quit', 'timeout')
            final_score: Final game score
            final_turns: Total turns played
            death_reason: Death message if applicable

        Returns:
            Final episode statistics
        """
        if self._ended:
            return self._stats

        self._ended = True
        self._end_time = datetime.now()

        # Update statistics
        self._stats.ended_at = self._end_time
        self._stats.end_reason = end_reason
        self._stats.final_score = final_score
        self._stats.final_turns = final_turns
        self._stats.death_reason = death_reason
        self._stats.skills_used = len(self._skills_used)
        self._stats.skills_created = len(self._skills_created)
        self._stats.total_actions = self._skill_executions

        # Get dungeon stats
        dungeon_stats = self.dungeon.get_statistics()
        self._stats.final_depth = dungeon_stats["deepest_main"]
        self._stats.levels_visited = dungeon_stats["total_levels_visited"]
        self._stats.tiles_explored = dungeon_stats["total_tiles_explored"]

        # Get final XP level from working memory
        current = self.working.get_current_state()
        if current:
            self._stats.final_xp_level = 1  # Would get from stats

        # Record end event
        self.record_event(
            "episode_end",
            f"Episode ended: {end_reason}",
            data={"score": final_score, "turns": final_turns},
        )

        # Persist to database
        if self._manager:
            self._manager.end_episode(
                self.episode_id,
                end_reason=end_reason,
                final_score=final_score,
                final_turns=final_turns,
                final_depth=self._stats.final_depth,
                final_xp_level=self._stats.final_xp_level,
                death_reason=death_reason,
                skills_used=self._stats.skills_used,
                skills_created=self._stats.skills_created,
            )

            # Save dungeon levels
            for level in self.dungeon.get_all_levels():
                self._save_level(level)

        return self._stats

    def update_state(
        self,
        turn: int,
        hp: int,
        max_hp: int,
        position_x: int,
        position_y: int,
        dungeon_level: int,
        branch: str = "main",
        monsters_visible: int = 0,
        hostile_monsters_visible: int = 0,
        items_here: int = 0,
        hunger_state: str = "not hungry",
        message: str = "",
        xp_level: int = 1,
        score: int = 0,
    ) -> None:
        """
        Update all memory systems with current state.

        This should be called each turn to keep memory in sync.
        """
        if not self._started:
            self.start()

        # Update working memory
        self.working.update_turn(
            turn=turn,
            hp=hp,
            max_hp=max_hp,
            position_x=position_x,
            position_y=position_y,
            dungeon_level=dungeon_level,
            monsters_visible=monsters_visible,
            hostile_monsters_visible=hostile_monsters_visible,
            items_here=items_here,
            hunger_state=hunger_state,
            message=message,
        )

        # Update dungeon level tracking
        self.dungeon.set_current_level(dungeon_level, branch)

        # Track XP level changes
        if xp_level > self._stats.final_xp_level:
            self._stats.final_xp_level = xp_level
            self.record_event(
                "levelup",
                f"Reached experience level {xp_level}",
                turn=turn,
                level_number=dungeon_level,
            )

    def record_event(
        self,
        event_type: str,
        description: str,
        turn: Optional[int] = None,
        level_number: Optional[int] = None,
        branch: Optional[str] = None,
        position: Optional[tuple[int, int]] = None,
        data: Optional[dict] = None,
    ) -> None:
        """Record a significant event."""
        if turn is None:
            turn = self.working.current_turn

        if level_number is None:
            level_number = self.dungeon.current_level_number

        if branch is None:
            branch = self.dungeon.current_branch

        event = EpisodeEvent(
            turn=turn,
            event_type=event_type,
            description=description,
            level_number=level_number,
            branch=branch,
            position=position,
            data=data or {},
        )
        self._events.append(event)

        # Persist to database
        if self._manager:
            pos_x, pos_y = position if position else (None, None)
            self._manager.record_event(
                self.episode_id,
                turn=turn,
                event_type=event_type,
                description=description,
                level_number=level_number,
                branch=branch,
                position_x=pos_x,
                position_y=pos_y,
                data=data,
            )

    def record_skill_execution(
        self,
        skill_name: str,
        success: bool,
        stopped_reason: Optional[str] = None,
        actions_taken: int = 0,
        turns_elapsed: int = 0,
        result_data: Optional[dict] = None,
    ) -> None:
        """Record a skill execution."""
        self._skills_used.add(skill_name)
        self._skill_executions += 1
        self._stats.total_actions += actions_taken

        # Build description with hint if available
        result_str = "success" if success else "failed"
        desc = f"Executed {skill_name}: {result_str}"
        if stopped_reason:
            desc += f" ({stopped_reason})"
        if result_data and result_data.get("hint"):
            desc += f" - {result_data['hint']}"

        event_data = {
            "skill": skill_name,
            "success": success,
            "stopped_reason": stopped_reason,
            "actions": actions_taken,
            "turns": turns_elapsed,
        }
        if result_data:
            event_data["result_data"] = result_data

        self.record_event(
            "skill_executed",
            desc,
            data=event_data,
        )

    def record_skill_created(self, skill_name: str) -> None:
        """Record creation of a new skill."""
        self._skills_created.add(skill_name)
        self.record_event(
            "skill_created",
            f"Created new skill: {skill_name}",
        )

    def record_monster_kill(
        self,
        monster_name: str,
        damage_dealt: int = 0,
    ) -> None:
        """Record killing a monster."""
        self._stats.monsters_killed += 1
        self._stats.damage_dealt += damage_dealt

        self.record_event(
            "monster_killed",
            f"Killed {monster_name}",
            data={"monster": monster_name, "damage": damage_dealt},
        )

        # Update cross-episode knowledge
        if self._manager:
            self._manager.update_monster_knowledge(
                monster_name,
                killed=True,
                damage_dealt=damage_dealt,
            )

    def record_damage_taken(self, amount: int, source: Optional[str] = None) -> None:
        """Record damage taken."""
        self._stats.damage_taken += amount

        if source:
            # Update cross-episode knowledge
            if self._manager:
                self._manager.update_monster_knowledge(
                    source,
                    damage_taken=amount,
                )

    def record_item_discovery(
        self,
        appearance: str,
        object_class: str,
        true_identity: Optional[str] = None,
        method: str = "use",
    ) -> None:
        """Record identifying an item."""
        if self._manager:
            self._manager.record_item_discovery(
                self.episode_id,
                appearance=appearance,
                object_class=object_class,
                true_identity=true_identity,
                turn_discovered=self.working.current_turn,
                discovery_method=method,
            )

        self.record_event(
            "item_identified",
            f"Identified {appearance} as {true_identity or 'unknown'}",
            data={
                "appearance": appearance,
                "identity": true_identity,
                "class": object_class,
            },
        )

    def record_stash(
        self,
        items: list[str],
        position: Optional[tuple[int, int]] = None,
    ) -> None:
        """Record finding a stash of items."""
        if position is None:
            current = self.working.get_current_state()
            if current:
                position = (current.position_x, current.position_y)

        if position and self._manager:
            self._manager.save_stash(
                self.episode_id,
                level_number=self.dungeon.current_level_number,
                position_x=position[0],
                position_y=position[1],
                items=items,
                branch=self.dungeon.current_branch,
                turn_discovered=self.working.current_turn,
            )

    def get_events(
        self,
        event_type: Optional[str] = None,
        limit: int = 50,
    ) -> list[EpisodeEvent]:
        """Get recorded events."""
        events = self._events
        if event_type:
            events = [e for e in events if e.event_type == event_type]
        return events[-limit:]

    def get_statistics(self) -> EpisodeStatistics:
        """Get current episode statistics."""
        # Update with current dungeon stats
        dungeon_stats = self.dungeon.get_statistics()
        self._stats.levels_visited = dungeon_stats["total_levels_visited"]
        self._stats.tiles_explored = dungeon_stats["total_tiles_explored"]
        self._stats.final_depth = dungeon_stats["deepest_main"]

        # Update skill counts
        self._stats.skills_used = len(self._skills_used)
        self._stats.skills_created = len(self._skills_created)

        return self._stats

    def get_summary(self) -> dict:
        """Get episode summary for LLM context."""
        working_summary = self.working.get_summary()
        dungeon_stats = self.dungeon.get_statistics()

        # Recent events
        recent_events = [
            {"type": e.event_type, "desc": e.description, "turn": e.turn}
            for e in self._events[-10:]
        ]

        return {
            "episode_id": self.episode_id,
            "started": self._started,
            "ended": self._ended,
            "current_turn": working_summary["current_turn"],
            "current_level": working_summary["current_level"],
            "hp": working_summary["hp"],
            "max_hp": working_summary["max_hp"],
            "position_x": working_summary["position_x"],
            "position_y": working_summary["position_y"],
            "hp_trend": working_summary["hp_trend"],
            "in_combat": working_summary["in_combat"],
            "deepest_level": dungeon_stats["deepest_main"],
            "levels_explored": dungeon_stats["total_levels_visited"],
            "skills_used": len(self._skills_used),
            "skills_created": len(self._skills_created),
            "monsters_killed": self._stats.monsters_killed,
            "recent_events": recent_events,
            "pending_goals": working_summary["pending_goals"],
        }

    def _save_level(self, level) -> None:
        """Save a dungeon level to the database."""
        if not self._manager:
            return

        features = [f.to_dict() for f in level.get_features()]

        self._manager.save_level(
            self.episode_id,
            level.level_number,
            branch=level.branch,
            tiles_explored=level.tiles_explored,
            first_visited_turn=level.first_visited_turn,
            last_visited_turn=level.last_visited_turn,
            upstairs_x=level.upstairs_pos[0] if level.upstairs_pos else None,
            upstairs_y=level.upstairs_pos[1] if level.upstairs_pos else None,
            downstairs_x=level.downstairs_pos[0] if level.downstairs_pos else None,
            downstairs_y=level.downstairs_pos[1] if level.downstairs_pos else None,
            has_altar=1 if level.get_features("altar") else 0,
            has_fountain=1 if level.get_features("fountain") else 0,
            has_sink=1 if level.get_features("sink") else 0,
            features=features,
            tile_data=level.serialize().hex(),  # Store as hex string
        )

    def close(self) -> None:
        """Clean up resources."""
        if self._manager:
            self._manager.close()

    def __enter__(self) -> "EpisodeMemory":
        self.start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        if not self._ended:
            self.end("quit", final_turns=self.working.current_turn)
        self.close()
