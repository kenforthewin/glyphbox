"""
Working memory for per-turn state caching.

Maintains short-term memory of recent game state, entities,
and pending decisions for the current game session.
"""

from collections import deque
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Optional


@dataclass
class EntitySighting:
    """Record of seeing an entity (monster or item)."""

    name: str
    position_x: int
    position_y: int
    turn_seen: int
    entity_type: str  # 'monster', 'item'
    is_hostile: bool = False
    additional_info: dict = field(default_factory=dict)


@dataclass
class PendingGoal:
    """A goal or intention queued for execution."""

    goal_type: str  # 'explore', 'fight', 'pickup', 'descend', etc.
    priority: int = 5  # 1 (highest) to 10 (lowest)
    target: Optional[Any] = None  # Position, item name, monster, etc.
    reason: str = ""
    created_turn: int = 0
    expires_turn: Optional[int] = None  # Goal expires after this turn

    def is_expired(self, current_turn: int) -> bool:
        """Check if goal has expired."""
        if self.expires_turn is None:
            return False
        return current_turn > self.expires_turn


@dataclass
class TurnSnapshot:
    """Snapshot of game state at a specific turn."""

    turn: int
    hp: int
    max_hp: int
    position_x: int
    position_y: int
    dungeon_level: int
    monsters_visible: int
    items_here: int
    hunger_state: str = "not hungry"
    message: str = ""


class WorkingMemory:
    """
    Short-term memory for the current game session.

    Caches recent game state, tracks visible entities, and
    maintains a queue of pending goals/intentions.

    Example usage:
        memory = WorkingMemory()

        # Update each turn
        memory.update_turn(turn=100, hp=20, max_hp=20, ...)

        # Track entities
        memory.record_sighting("grid bug", 10, 15, turn=100, entity_type="monster")

        # Manage goals
        memory.add_goal("explore", priority=5, reason="Find stairs")
        goal = memory.get_top_goal()

        # Query recent state
        recent = memory.get_recent_turns(5)
    """

    def __init__(
        self,
        max_turn_history: int = 100,
        max_sightings: int = 200,
        sighting_expiry_turns: int = 50,
    ):
        """
        Initialize working memory.

        Args:
            max_turn_history: Maximum turns to remember
            max_sightings: Maximum entity sightings to track
            sighting_expiry_turns: Turns after which sightings are forgotten
        """
        self.max_turn_history = max_turn_history
        self.max_sightings = max_sightings
        self.sighting_expiry_turns = sighting_expiry_turns

        # Turn history (most recent first)
        self._turn_history: deque[TurnSnapshot] = deque(maxlen=max_turn_history)

        # Entity sightings by type
        self._monster_sightings: deque[EntitySighting] = deque(maxlen=max_sightings)
        self._item_sightings: deque[EntitySighting] = deque(maxlen=max_sightings)

        # Pending goals (priority queue behavior via sorting)
        self._goals: list[PendingGoal] = []

        # Current turn tracking
        self._current_turn: int = 0
        self._current_level: int = 1

        # Recent messages
        self._recent_messages: deque[tuple[int, str]] = deque(maxlen=50)

        # Flags and state
        self._in_combat: bool = False
        self._last_action: Optional[str] = None
        self._last_action_result: Optional[str] = None

    # ==================== Turn State ====================

    def update_turn(
        self,
        turn: int,
        hp: int,
        max_hp: int,
        position_x: int,
        position_y: int,
        dungeon_level: int,
        monsters_visible: int = 0,
        hostile_monsters_visible: int = 0,
        items_here: int = 0,
        hunger_state: str = "not hungry",
        message: str = "",
    ) -> None:
        """
        Update working memory with current turn state.

        Args:
            turn: Current game turn
            hp: Current HP
            max_hp: Maximum HP
            position_x: Player X position
            position_y: Player Y position
            dungeon_level: Current dungeon level
            monsters_visible: Number of visible monsters (including pets)
            hostile_monsters_visible: Number of hostile monsters visible
            items_here: Number of items at player position
            hunger_state: Current hunger state
            message: Current game message
        """
        self._current_turn = turn
        self._current_level = dungeon_level

        snapshot = TurnSnapshot(
            turn=turn,
            hp=hp,
            max_hp=max_hp,
            position_x=position_x,
            position_y=position_y,
            dungeon_level=dungeon_level,
            monsters_visible=monsters_visible,
            items_here=items_here,
            hunger_state=hunger_state,
            message=message,
        )
        self._turn_history.appendleft(snapshot)

        if message:
            self._recent_messages.appendleft((turn, message))

        # Update combat state (only hostile monsters count)
        self._in_combat = hostile_monsters_visible > 0

        # Clean up expired sightings
        self._cleanup_expired_sightings()

    def get_current_state(self) -> Optional[TurnSnapshot]:
        """Get the most recent turn snapshot."""
        return self._turn_history[0] if self._turn_history else None

    def get_recent_turns(self, count: int = 10) -> list[TurnSnapshot]:
        """Get the most recent turn snapshots."""
        return list(self._turn_history)[:count]

    def get_hp_trend(self, turns: int = 10) -> str:
        """
        Analyze HP trend over recent turns.

        Returns:
            'stable', 'increasing', 'decreasing', or 'critical'
        """
        recent = self.get_recent_turns(turns)
        if len(recent) < 2:
            return "stable"

        current_hp = recent[0].hp
        max_hp = recent[0].max_hp

        # Check for critical HP
        if current_hp / max_hp < 0.2:
            return "critical"

        # Calculate trend
        hp_values = [s.hp for s in recent]
        if hp_values[0] > hp_values[-1] + 2:
            return "increasing"
        elif hp_values[0] < hp_values[-1] - 2:
            return "decreasing"
        return "stable"

    # ==================== Entity Tracking ====================

    def record_sighting(
        self,
        name: str,
        position_x: int,
        position_y: int,
        turn: int,
        entity_type: str,
        is_hostile: bool = False,
        **kwargs,
    ) -> None:
        """
        Record seeing an entity.

        Args:
            name: Entity name
            position_x: X position
            position_y: Y position
            turn: Turn when seen
            entity_type: 'monster' or 'item'
            is_hostile: Whether monster is hostile
            **kwargs: Additional info to store
        """
        sighting = EntitySighting(
            name=name,
            position_x=position_x,
            position_y=position_y,
            turn_seen=turn,
            entity_type=entity_type,
            is_hostile=is_hostile,
            additional_info=kwargs,
        )

        if entity_type == "monster":
            self._monster_sightings.appendleft(sighting)
        else:
            self._item_sightings.appendleft(sighting)

    def get_recent_monsters(
        self,
        max_age_turns: Optional[int] = None,
        hostile_only: bool = False,
    ) -> list[EntitySighting]:
        """
        Get recently seen monsters.

        Args:
            max_age_turns: Only return sightings within this many turns
            hostile_only: Only return hostile monsters

        Returns:
            List of monster sightings
        """
        max_age = max_age_turns or self.sighting_expiry_turns
        cutoff = self._current_turn - max_age

        results = []
        for sighting in self._monster_sightings:
            if sighting.turn_seen < cutoff:
                continue
            if hostile_only and not sighting.is_hostile:
                continue
            results.append(sighting)

        return results

    def get_recent_items(
        self,
        max_age_turns: Optional[int] = None,
    ) -> list[EntitySighting]:
        """Get recently seen items."""
        max_age = max_age_turns or self.sighting_expiry_turns
        cutoff = self._current_turn - max_age

        return [s for s in self._item_sightings if s.turn_seen >= cutoff]

    def get_monster_at(
        self,
        position_x: int,
        position_y: int,
        max_age_turns: int = 5,
    ) -> Optional[EntitySighting]:
        """Get monster last seen at a specific position."""
        cutoff = self._current_turn - max_age_turns

        for sighting in self._monster_sightings:
            if sighting.turn_seen < cutoff:
                continue
            if sighting.position_x == position_x and sighting.position_y == position_y:
                return sighting
        return None

    def _cleanup_expired_sightings(self) -> None:
        """Remove old sightings."""
        cutoff = self._current_turn - self.sighting_expiry_turns

        # Filter monster sightings
        self._monster_sightings = deque(
            [s for s in self._monster_sightings if s.turn_seen >= cutoff],
            maxlen=self.max_sightings,
        )

        # Filter item sightings
        self._item_sightings = deque(
            [s for s in self._item_sightings if s.turn_seen >= cutoff],
            maxlen=self.max_sightings,
        )

    # ==================== Goal Management ====================

    def add_goal(
        self,
        goal_type: str,
        priority: int = 5,
        target: Optional[Any] = None,
        reason: str = "",
        expires_in_turns: Optional[int] = None,
    ) -> None:
        """
        Add a pending goal.

        Args:
            goal_type: Type of goal ('explore', 'fight', 'pickup', etc.)
            priority: Priority 1 (highest) to 10 (lowest)
            target: Target of the goal (position, item, etc.)
            reason: Why this goal was created
            expires_in_turns: Goal expires after this many turns
        """
        expires_turn = None
        if expires_in_turns is not None:
            expires_turn = self._current_turn + expires_in_turns

        goal = PendingGoal(
            goal_type=goal_type,
            priority=priority,
            target=target,
            reason=reason,
            created_turn=self._current_turn,
            expires_turn=expires_turn,
        )
        self._goals.append(goal)
        self._goals.sort(key=lambda g: g.priority)

    def get_top_goal(self) -> Optional[PendingGoal]:
        """Get the highest priority non-expired goal."""
        self._cleanup_expired_goals()
        return self._goals[0] if self._goals else None

    def get_goals(self, goal_type: Optional[str] = None) -> list[PendingGoal]:
        """Get all goals, optionally filtered by type."""
        self._cleanup_expired_goals()
        if goal_type:
            return [g for g in self._goals if g.goal_type == goal_type]
        return self._goals.copy()

    def complete_goal(self, goal: PendingGoal) -> None:
        """Mark a goal as completed (remove it)."""
        if goal in self._goals:
            self._goals.remove(goal)

    def clear_goals(self, goal_type: Optional[str] = None) -> None:
        """Clear goals, optionally filtered by type."""
        if goal_type:
            self._goals = [g for g in self._goals if g.goal_type != goal_type]
        else:
            self._goals.clear()

    def _cleanup_expired_goals(self) -> None:
        """Remove expired goals."""
        self._goals = [g for g in self._goals if not g.is_expired(self._current_turn)]

    # ==================== Action Tracking ====================

    def record_action(self, action: str, result: Optional[str] = None) -> None:
        """Record the last action taken."""
        self._last_action = action
        self._last_action_result = result

    def get_last_action(self) -> tuple[Optional[str], Optional[str]]:
        """Get the last action and its result."""
        return self._last_action, self._last_action_result

    # ==================== Message Analysis ====================

    def get_recent_messages(self, count: int = 10) -> list[tuple[int, str]]:
        """Get recent game messages with their turns."""
        return list(self._recent_messages)[:count]

    def search_messages(self, keyword: str, count: int = 50) -> list[tuple[int, str]]:
        """Search recent messages for a keyword."""
        keyword_lower = keyword.lower()
        return [
            (turn, msg)
            for turn, msg in list(self._recent_messages)[:count]
            if keyword_lower in msg.lower()
        ]

    # ==================== State Queries ====================

    @property
    def current_turn(self) -> int:
        """Get current turn number."""
        return self._current_turn

    @property
    def current_level(self) -> int:
        """Get current dungeon level."""
        return self._current_level

    @property
    def in_combat(self) -> bool:
        """Check if currently in combat (monsters visible)."""
        return self._in_combat

    def get_summary(self) -> dict:
        """Get a summary of working memory state."""
        current = self.get_current_state()
        return {
            "current_turn": self._current_turn,
            "current_level": self._current_level,
            "hp": current.hp if current else 0,
            "max_hp": current.max_hp if current else 0,
            "hp_trend": self.get_hp_trend(),
            "in_combat": self._in_combat,
            "recent_monsters": len(self.get_recent_monsters(max_age_turns=10)),
            "recent_items": len(self.get_recent_items(max_age_turns=10)),
            "pending_goals": len(self._goals),
            "top_goal": self._goals[0].goal_type if self._goals else None,
        }

    def clear(self) -> None:
        """Clear all working memory."""
        self._turn_history.clear()
        self._monster_sightings.clear()
        self._item_sightings.clear()
        self._goals.clear()
        self._recent_messages.clear()
        self._current_turn = 0
        self._current_level = 1
        self._in_combat = False
        self._last_action = None
        self._last_action_result = None
