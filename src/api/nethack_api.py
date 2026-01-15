"""
Unified NetHack API.

Provides a high-level interface for interacting with NetHack,
combining environment management, state queries, actions, and pathfinding.
"""

import logging
from typing import Callable, Optional

from src.memory.dungeon import DungeonMemory, LevelMemory

from .actions import ActionExecutor
from .environment import NLEWrapper, Observation
from .knowledge import (
    MonsterInfo,
    elbereth_effective_against,
    estimate_monster_difficulty,
    get_corpse_effects,
    is_corpse_safe,
    is_dangerous_melee,
    is_prayer_safe,
    lookup_monster,
)
from .models import (
    ALL_DIRECTIONS,
    ActionResult,
    AutoexploreResult,
    CARDINAL_DIRECTIONS,
    DIAGONAL_DIRECTIONS,
    Direction,
    DungeonLevel,
    Item,
    Monster,
    Position,
    Stats,
    Tile,
)
from .pathfinding import (
    PathResult,
    PathStopReason,
    TargetResult,
    find_nearest,
    find_nearest_monster,
    find_path,
    find_stairs_down,
    find_stairs_up,
    find_unexplored,
    is_doorway_glyph,
)
from .queries import (
    find_doors,
    find_items_on_map,
    find_stairs,
    get_adjacent_monsters,
    get_current_level,
    get_food_in_inventory,
    get_hostile_monsters,
    get_inventory,
    get_items_at,
    get_items_here,
    get_message,
    get_position,
    get_screen,
    get_stats,
    get_visible_monsters,
    get_weapons_in_inventory,
    # Player condition checks
    is_blind,
    is_confused,
    is_stunned,
    in_sokoban,
)

logger = logging.getLogger(__name__)


class NetHackAPI:
    """
    High-level API for interacting with NetHack.

    This class provides a unified interface that combines:
    - Environment management (reset, step)
    - State queries (stats, monsters, items, map)
    - Action execution (move, attack, use items)
    - Pathfinding (A*, nearest search)
    - Knowledge base (monster info, corpse safety)

    Example usage:
        with NetHackAPI() as nh:
            nh.reset()
            stats = nh.get_stats()
            monsters = nh.get_visible_monsters()
            if monsters:
                direction = nh.position.direction_to(monsters[0].position)
                nh.attack(direction)
    """

    def __init__(
        self,
        env_name: str = "NetHackChallenge-v0",
        max_episode_steps: int = 1_000_000,
        render_mode: Optional[str] = None,
        dungeon_memory: Optional[DungeonMemory] = None,
    ):
        """
        Initialize the NetHack API.

        Args:
            env_name: Gymnasium environment name
            max_episode_steps: Maximum steps per episode
            render_mode: Render mode ("human", "ansi", or None)
            dungeon_memory: Optional dungeon memory for exploration tracking
        """
        self._env = NLEWrapper(
            env_name=env_name,
            max_episode_steps=max_episode_steps,
            render_mode=render_mode,
        )
        self._actions: Optional[ActionExecutor] = None
        self._last_prayer_turn = 0
        self._message_history: list[str] = []
        self._dungeon_memory = dungeon_memory or DungeonMemory()

        logger.info(f"NetHackAPI initialized with env={env_name}")

    # ==================== Lifecycle ====================

    def reset(self) -> Observation:
        """
        Reset the environment and start a new episode.

        Returns:
            Initial observation
        """
        obs = self._env.reset()
        self._actions = ActionExecutor(self._env)
        self._last_prayer_turn = 0
        self._message_history = []
        self._dungeon_memory.clear()  # Reset exploration tracking for new game
        logger.info("Episode started")
        return obs

    def close(self) -> None:
        """Close the environment."""
        self._env.close()

    def __enter__(self) -> "NetHackAPI":
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.close()

    def _mark_current_position_stepped(self) -> None:
        """Mark current position as stepped in dungeon memory."""
        if self.observation:
            pos = get_position(self.observation)
            dungeon_level = int(self.observation.blstats[12])  # BL_DEPTH
            level = self._dungeon_memory.get_level(dungeon_level, create=True)
            level.mark_stepped(pos.x, pos.y)
            # Also mark visible walkable tiles in memory for future pathfinding
            self._update_visible_walkable_tiles(level)

    def _update_visible_walkable_tiles(self, level: "LevelMemory") -> None:
        """
        Mark currently visible walkable tiles in level memory.

        This allows A* pathfinding to traverse tiles we've seen but not stepped on
        when they go out of sight (and show as stone in the glyph array).
        """
        if not self.observation:
            return

        from .glyphs import is_walkable_glyph
        from nle import nethack

        for y in range(21):
            for x in range(79):
                glyph = int(self.observation.glyphs[y, x])
                # Skip stone tiles (unexplored/out of sight)
                if nethack.glyph_is_cmap(glyph) and nethack.glyph_to_cmap(glyph) == 0:
                    continue
                # If tile is currently visible and walkable, remember it
                if is_walkable_glyph(glyph):
                    level.mark_seen_walkable(x, y)

    def _has_unreachable_areas(self) -> bool:
        """
        Check if there are areas we can see but can't reach.

        This detects when:
        1. There are closed doors we can't path to or open
        2. There are visible floor tiles we haven't stepped on and can't reach

        Used to distinguish between "fully explored" (everything reachable visited)
        and "blocked" (visible areas exist but aren't reachable).

        Returns:
            True if there are unreachable visible areas, False otherwise.
        """
        if not self.observation:
            return False

        # Check 1: Are there closed doors we can't reach?
        doors = self.find_doors()
        closed_doors = [(pos, is_open) for pos, is_open in doors if not is_open]

        if closed_doors:
            # There are closed doors visible but we couldn't open them
            # (either couldn't path to them, or they were locked)
            logger.debug(f"_has_unreachable_areas: Found {len(closed_doors)} closed door(s) at {[d[0] for d in closed_doors]}")
            return True

        # Check 2: Are there visible floor tiles we haven't stepped on?
        # Get stepped memory for current level
        dungeon_level = int(self.observation.blstats[12])
        stepped_memory = self._dungeon_memory.get_level(dungeon_level, create=True)
        level = self.get_current_level()

        unreachable_tiles = []
        for y in range(21):
            for x in range(79):
                tile = level.get_tile(Position(x, y))
                # Look for walkable tiles we can see but haven't stepped on
                if tile and tile.is_explored and tile.is_walkable:
                    if not stepped_memory.is_stepped(x, y):
                        # Found a visible, walkable tile we haven't visited
                        # Try to path to it
                        path_result = self._find_path(Position(x, y))
                        if not path_result or not path_result.path:
                            # Can't reach it - we're blocked
                            unreachable_tiles.append(Position(x, y))
                            if len(unreachable_tiles) >= 5:
                                # Don't need to find all of them
                                break
            if len(unreachable_tiles) >= 5:
                break

        if unreachable_tiles:
            logger.debug(f"_has_unreachable_areas: Found {len(unreachable_tiles)} unreachable walkable tile(s), e.g. {unreachable_tiles[:3]}")
            return True

        return False

    def _try_open_nearest_closed_door(self) -> bool:
        """
        Try to reach and open the nearest closed door.

        Used by autoexplore when exploration is blocked by doors.
        Only attempts to open doors (not kick/force them).

        Returns:
            True if a door was successfully opened, False otherwise.
        """
        if not self.observation:
            return False

        # Find all closed doors
        doors = self.find_doors()
        closed_doors = [(pos, is_open) for pos, is_open in doors if not is_open]

        if not closed_doors:
            return False

        current_pos = self.position

        # Sort by distance
        closed_doors.sort(key=lambda d: current_pos.distance_to(d[0]))

        for door_pos, _ in closed_doors:
            # Find adjacent tiles to the door
            for direction in CARDINAL_DIRECTIONS:
                adj_pos = door_pos.move(direction)

                # Skip if out of bounds
                if not (0 <= adj_pos.x < 79 and 0 <= adj_pos.y < 21):
                    continue

                # Check if adjacent tile is walkable
                adj_tile = self.get_tile(adj_pos)
                if not adj_tile or not adj_tile.is_walkable:
                    continue

                # Try to path to the adjacent tile
                if current_pos == adj_pos:
                    # Already adjacent to this door
                    pass
                else:
                    # Try to reach the adjacent position
                    path_result = self._find_path(adj_pos)
                    if not path_result or not path_result.path:
                        continue

                    # Walk to the adjacent position
                    for dir_step in path_result.path:
                        move_result = self.move(dir_step)
                        if not move_result.success:
                            break
                        # Check for hostiles appearing
                        if self.get_hostile_monsters():
                            return False
                    else:
                        # Successfully reached adjacent position
                        pass

                    # Verify we're at the adjacent position
                    if self.position != adj_pos:
                        continue

                # Now try to open the door
                dir_to_door = self.position.direction_to(door_pos)
                if dir_to_door is None:
                    continue

                open_result = self.open_door(dir_to_door)

                # Check if door opened (not locked/resisted)
                messages = " ".join(open_result.messages).lower()
                if "opens" in messages:
                    return True
                elif "locked" in messages or "resists" in messages:
                    # Door is locked - don't try to force it, try next door
                    continue
                elif "no door" in messages:
                    # Already open or not a door
                    continue

        return False

    # ==================== Properties ====================

    @property
    def observation(self) -> Optional[Observation]:
        """Get the current observation."""
        return self._env.last_observation

    @property
    def is_done(self) -> bool:
        """Check if the episode has ended."""
        return self._env.is_done

    @property
    def turn(self) -> int:
        """Get the current game turn."""
        if self.observation:
            return self.observation.turn
        return 0

    @property
    def position(self) -> Position:
        """Get player's current position."""
        if self.observation:
            return get_position(self.observation)
        return Position(0, 0)

    # ==================== State Queries ====================

    def get_stats(self) -> Stats:
        """Get current player statistics."""
        if not self.observation:
            raise RuntimeError("No observation available. Call reset() first.")
        return get_stats(self.observation)

    def get_position(self) -> Position:
        """Get player's current position."""
        if not self.observation:
            raise RuntimeError("No observation available. Call reset() first.")
        return get_position(self.observation)

    def get_screen(self) -> str:
        """Get the raw ASCII screen as a single string (24 lines, 80 chars each)."""
        if not self.observation:
            return ""
        return get_screen(self.observation)

    def get_screen_lines(self) -> list[str]:
        """Get the ASCII screen as a list of 24 strings (one per row). Useful for parsing."""
        if not self.observation:
            return []
        return self.observation.get_screen_lines()

    def get_message(self) -> str:
        """Get the current game message."""
        if not self.observation:
            return ""
        return get_message(self.observation)

    def get_messages(self, n: int = 10) -> list[str]:
        """Get the last n game messages."""
        return self._message_history[-n:]

    def get_current_level(self) -> DungeonLevel:
        """Get parsed representation of current dungeon level."""
        if not self.observation:
            raise RuntimeError("No observation available. Call reset() first.")
        return get_current_level(self.observation)

    def get_visible_monsters(self) -> list[Monster]:
        """Get all monsters currently visible."""
        if not self.observation:
            return []
        return get_visible_monsters(self.observation)

    def get_adjacent_monsters(self) -> list[Monster]:
        """Get monsters in the 8 adjacent tiles."""
        if not self.observation:
            return []
        return get_adjacent_monsters(self.observation)

    def get_hostile_monsters(self) -> list[Monster]:
        """Get only hostile (non-pet) monsters."""
        if not self.observation:
            return []
        return get_hostile_monsters(self.observation)

    def get_items_at(self, pos: Position) -> list[Item]:
        """Get items at a specific position."""
        if not self.observation:
            return []
        return get_items_at(self.observation, pos)

    def get_items_here(self) -> list[Item]:
        """Get items at player's current position."""
        if not self.observation:
            return []
        return get_items_here(self.observation)

    def get_inventory(self) -> list[Item]:
        """Get current inventory."""
        if not self.observation:
            return []
        return get_inventory(self.observation)

    def get_food(self) -> list[Item]:
        """Get food items from inventory."""
        if not self.observation:
            return []
        return get_food_in_inventory(self.observation)

    def get_weapons(self) -> list[Item]:
        """Get weapons from inventory."""
        if not self.observation:
            return []
        return get_weapons_in_inventory(self.observation)

    def get_tile(self, pos: Position) -> Optional[Tile]:
        """Get tile at a position."""
        level = self.get_current_level()
        return level.get_tile(pos)

    def find_stairs(self) -> tuple[Optional[Position], Optional[Position]]:
        """Find stairs up and down positions."""
        if not self.observation:
            return None, None
        return find_stairs(self.observation)

    def find_doors(self) -> list[tuple[Position, bool]]:
        """Find all doors (position, is_open)."""
        if not self.observation:
            return []
        return find_doors(self.observation)

    # ==================== Actions ====================

    def _record_message(self) -> None:
        """Record current message to history."""
        msg = self.get_message()
        if msg and (not self._message_history or msg != self._message_history[-1]):
            self._message_history.append(msg)

    def _record_messages(self, messages: list[str]) -> None:
        """Record multiple messages to history (from ActionResult.messages)."""
        for msg in messages:
            if msg and (not self._message_history or msg != self._message_history[-1]):
                self._message_history.append(msg)

    def move(self, direction: Direction) -> ActionResult:
        """Move in a direction."""
        if not self._actions:
            return ActionResult.failure("Environment not initialized")
        result = self._actions.move(direction)
        self._record_messages(result.messages)
        if result.success:
            self._mark_current_position_stepped()
        return result

    def move_toward(self, target) -> ActionResult:
        """Move one step toward a target position (Position or (x,y) tuple)."""
        if not self._actions:
            return ActionResult.failure("Environment not initialized")
        target = self._to_position(target)
        result = self._actions.move_toward(target)
        self._record_messages(result.messages)
        if result.success:
            self._mark_current_position_stepped()
        return result

    def move_to(self, target, allow_with_hostiles: bool = False) -> ActionResult:
        """
        Move to a target position by pathfinding and following the path.

        This is a convenience method that combines find_path + move loop.
        Stops early if movement fails (blocked, combat, etc.).

        If the target is unwalkable (monster, closed door, wall), automatically
        moves to the nearest adjacent tile instead.

        Args:
            target: Position object or (x, y) tuple
            allow_with_hostiles: If True, allow pathfinding with hostiles in view

        Returns:
            ActionResult with success/failure and messages from the journey.
            - success: True if reached target position (or adjacent if target unwalkable)
            - messages: All game messages encountered during movement
        """
        target = self._to_position(target)

        # Find path to target
        path_result = self._find_path(target, allow_with_hostiles=allow_with_hostiles)

        # Track if we're using adjacent path strategy (target was unwalkable)
        used_adjacent_strategy = False

        # If target is unwalkable, try to path to an adjacent tile instead
        if not path_result.success and path_result.reason == PathStopReason.TARGET_UNWALKABLE:
            # Find best adjacent tile to path to
            adjacent_path = self._find_path_to_adjacent(target, allow_with_hostiles)
            if adjacent_path:
                path_result = adjacent_path
                used_adjacent_strategy = True

        # If pathfinding refused because hostiles are visible, and the target IS a hostile
        # monster position, retry with allow_with_hostiles=True. This handles the common
        # case of deliberately moving toward a monster to attack it.
        if not path_result.success and path_result.reason == PathStopReason.HOSTILE_IN_VIEW:
            # Check if target has a hostile monster
            from .glyphs import is_hostile_glyph
            if self.observation:
                target_glyph = int(self.observation.glyphs[target.y, target.x])
                if is_hostile_glyph(target_glyph):
                    # Target is a hostile - path to adjacent with hostiles allowed
                    adjacent_path = self._find_path_to_adjacent(target, allow_with_hostiles=True)
                    if adjacent_path:
                        path_result = adjacent_path
                        used_adjacent_strategy = True

        if not path_result.success:
            return ActionResult.failure(f"No path: {path_result.message}")

        # Follow the path
        all_messages = []
        for direction in path_result:
            result = self.move(direction)
            all_messages.extend(result.messages)

            if not result.success:
                return ActionResult(
                    success=False,
                    messages=all_messages,
                    turn_elapsed=result.turn_elapsed,
                )

            # Check if we've been interrupted by combat or other events
            # (monster appeared, took damage, etc.)
            if self.get_hostile_monsters():
                all_messages.append("Movement interrupted - hostile monster appeared")
                return ActionResult(
                    success=False,
                    messages=all_messages,
                    turn_elapsed=True,
                )

        # Verify we reached the target (or adjacent if target was unwalkable)
        if self.position == target:
            return ActionResult(success=True, messages=all_messages, turn_elapsed=True)
        elif used_adjacent_strategy and self.position.chebyshev_distance(target) == 1:
            # Successfully moved adjacent to unwalkable target
            return ActionResult(success=True, messages=all_messages, turn_elapsed=True)
        else:
            all_messages.append(f"Stopped at {self.position}, expected {target}")
            return ActionResult(success=False, messages=all_messages, turn_elapsed=True)

    def attack(self, direction: Direction) -> ActionResult:
        """Attack in a direction."""
        if not self._actions:
            return ActionResult.failure("Environment not initialized")
        result = self._actions.attack(direction)
        self._record_messages(result.messages)
        return result

    def kick(self, direction: Direction) -> ActionResult:
        """Kick in a direction."""
        if not self._actions:
            return ActionResult.failure("Environment not initialized")
        result = self._actions.kick(direction)
        self._record_messages(result.messages)
        return result

    def wait(self) -> ActionResult:
        """Wait one turn."""
        if not self._actions:
            return ActionResult.failure("Environment not initialized")
        result = self._actions.wait()
        self._record_messages(result.messages)
        return result

    def search(self) -> ActionResult:
        """Search adjacent tiles."""
        if not self._actions:
            return ActionResult.failure("Environment not initialized")
        result = self._actions.search()
        self._record_messages(result.messages)
        return result

    def pickup(self, item_letter: Optional[str] = None) -> ActionResult:
        """Pick up items."""
        if not self._actions:
            return ActionResult.failure("Environment not initialized")
        result = self._actions.pickup(item_letter)
        self._record_messages(result.messages)
        return result

    def drop(self, item_letter: str) -> ActionResult:
        """Drop an item."""
        if not self._actions:
            return ActionResult.failure("Environment not initialized")
        result = self._actions.drop(item_letter)
        self._record_messages(result.messages)
        return result

    def eat(self, item_letter: Optional[str] = None) -> ActionResult:
        """Eat food."""
        if not self._actions:
            return ActionResult.failure("Environment not initialized")
        result = self._actions.eat(item_letter)
        self._record_messages(result.messages)
        return result

    def quaff(self, item_letter: str) -> ActionResult:
        """Drink a potion."""
        if not self._actions:
            return ActionResult.failure("Environment not initialized")
        result = self._actions.quaff(item_letter)
        self._record_messages(result.messages)
        return result

    def read(self, item_letter: str) -> ActionResult:
        """Read a scroll or spellbook."""
        if not self._actions:
            return ActionResult.failure("Environment not initialized")
        result = self._actions.read(item_letter)
        self._record_messages(result.messages)
        return result

    def zap(self, item_letter: str, direction: Direction) -> ActionResult:
        """Zap a wand."""
        if not self._actions:
            return ActionResult.failure("Environment not initialized")
        result = self._actions.zap(item_letter, direction)
        self._record_messages(result.messages)
        return result

    def wear(self, item_letter: str) -> ActionResult:
        """Wear armor."""
        if not self._actions:
            return ActionResult.failure("Environment not initialized")
        result = self._actions.wear(item_letter)
        self._record_messages(result.messages)
        return result

    def wield(self, item_letter: str) -> ActionResult:
        """Wield a weapon."""
        if not self._actions:
            return ActionResult.failure("Environment not initialized")
        result = self._actions.wield(item_letter)
        self._record_messages(result.messages)
        return result

    def take_off(self, item_letter: str) -> ActionResult:
        """Remove worn armor."""
        if not self._actions:
            return ActionResult.failure("Environment not initialized")
        result = self._actions.take_off(item_letter)
        self._record_messages(result.messages)
        return result

    def open_door(self, direction: Direction) -> ActionResult:
        """Open a door."""
        if not self._actions:
            return ActionResult.failure("Environment not initialized")
        result = self._actions.open_door(direction)
        self._record_messages(result.messages)
        return result

    def go_up(self) -> ActionResult:
        """Ascend stairs."""
        if not self._actions:
            return ActionResult.failure("Environment not initialized")
        result = self._actions.go_up()
        self._record_messages(result.messages)
        return result

    def go_down(self) -> ActionResult:
        """Descend stairs."""
        if not self._actions:
            return ActionResult.failure("Environment not initialized")
        result = self._actions.go_down()
        self._record_messages(result.messages)
        return result

    def pray(self) -> ActionResult:
        """Pray to your deity."""
        if not self._actions:
            return ActionResult.failure("Environment not initialized")
        result = self._actions.pray()
        if result.success:
            self._last_prayer_turn = self.turn
        self._record_messages(result.messages)
        return result

    def engrave(self, text: str = "Elbereth") -> ActionResult:
        """Engrave text on the floor."""
        if not self._actions:
            return ActionResult.failure("Environment not initialized")
        result = self._actions.engrave(text)
        self._record_messages(result.messages)
        return result

    def send_keys(self, keys: str) -> ActionResult:
        """Send raw keystrokes."""
        if not self._actions:
            return ActionResult.failure("Environment not initialized")
        result = self._actions.send_keys(keys)
        self._record_messages(result.messages)
        return result

    def fire(self, direction: Direction) -> ActionResult:
        """Fire wielded ranged weapon in direction."""
        if not self._actions:
            return ActionResult.failure("Environment not initialized")
        result = self._actions.fire(direction)
        self._record_messages(result.messages)
        return result

    def throw(self, item_letter: str, direction: Direction) -> ActionResult:
        """Throw an item in direction."""
        if not self._actions:
            return ActionResult.failure("Environment not initialized")
        result = self._actions.throw(item_letter, direction)
        self._record_messages(result.messages)
        return result

    def apply(self, item_letter: str) -> ActionResult:
        """Apply/use a tool (pickaxe, key, horn, etc.)."""
        if not self._actions:
            return ActionResult.failure("Environment not initialized")
        result = self._actions.apply(item_letter)
        self._record_messages(result.messages)
        return result

    def close_door(self, direction: Direction) -> ActionResult:
        """Close a door in direction."""
        if not self._actions:
            return ActionResult.failure("Environment not initialized")
        result = self._actions.close_door(direction)
        self._record_messages(result.messages)
        return result

    def cast_spell(self, spell_letter: str, direction: Optional[Direction] = None) -> ActionResult:
        """Cast a memorized spell."""
        if not self._actions:
            return ActionResult.failure("Environment not initialized")
        result = self._actions.cast_spell(spell_letter, direction)
        self._record_messages(result.messages)
        return result

    def look(self) -> ActionResult:
        """Look at what's on current square."""
        if not self._actions:
            return ActionResult.failure("Environment not initialized")
        result = self._actions.look()
        self._record_messages(result.messages)
        return result

    # ==================== Prompt Responses ====================

    def confirm(self) -> ActionResult:
        """Send 'y' for yes confirmation (e.g., [ynq] prompts)."""
        if not self._actions:
            return ActionResult.failure("Environment not initialized")
        result = self._actions.confirm()
        self._record_messages(result.messages)
        return result

    def deny(self) -> ActionResult:
        """Send 'n' for no confirmation (e.g., [ynq] prompts)."""
        if not self._actions:
            return ActionResult.failure("Environment not initialized")
        result = self._actions.deny()
        self._record_messages(result.messages)
        return result

    def escape(self) -> ActionResult:
        """Send ESC to cancel current action/prompt."""
        if not self._actions:
            return ActionResult.failure("Environment not initialized")
        result = self._actions.escape()
        self._record_messages(result.messages)
        return result

    def space(self) -> ActionResult:
        """Send space to continue/dismiss message."""
        if not self._actions:
            return ActionResult.failure("Environment not initialized")
        result = self._actions.space()
        self._record_messages(result.messages)
        return result

    # ==================== Pathfinding ====================

    def _to_position(self, target) -> Position:
        """Convert tuple or Position to Position."""
        if isinstance(target, Position):
            return target
        if isinstance(target, (tuple, list)) and len(target) == 2:
            return Position(target[0], target[1])
        raise TypeError(f"Expected Position or (x, y) tuple, got {type(target)}")

    def _find_path(
        self,
        target,
        avoid_monsters: bool = True,
        avoid_traps: bool = True,
        allow_with_hostiles: bool = False,
        cardinal_only: Optional[bool] = None,
    ) -> PathResult:
        """
        Internal: Find path to a target position using A*.

        Use move_to() instead for actually moving to a position.
        """
        if not self.observation:
            return PathResult([], PathStopReason.NO_OBSERVATION, "No observation available")
        target = self._to_position(target)
        # Get level memory for doorway tracking
        dungeon_level = int(self.observation.blstats[12])
        level_memory = self._dungeon_memory.get_level(dungeon_level, create=True)
        return find_path(
            self.observation, target, avoid_monsters, avoid_traps,
            allow_with_hostiles, cardinal_only=cardinal_only, level_memory=level_memory
        )

    def _find_path_to_adjacent(
        self,
        target: Position,
        allow_with_hostiles: bool = False,
    ) -> Optional[PathResult]:
        """
        Find the best path to a tile adjacent to the target.

        Used when the target itself is unwalkable (monster, closed door, etc.).
        Tries all adjacent tiles and returns the shortest valid path.

        Args:
            target: The unwalkable target position
            allow_with_hostiles: If True, allow pathfinding with hostiles in view

        Returns:
            PathResult to best adjacent tile, or None if no adjacent tile is reachable
        """
        current_pos = self.position
        best_path = None
        best_distance = float('inf')

        # Try all 8 adjacent tiles
        for direction in [Direction.N, Direction.S, Direction.E, Direction.W,
                          Direction.NE, Direction.NW, Direction.SE, Direction.SW]:
            adj_pos = target.move(direction)

            # Skip out of bounds
            if not (0 <= adj_pos.x < 79 and 0 <= adj_pos.y < 21):
                logger.debug(f"_find_path_to_adjacent: {direction.value} {adj_pos} out of bounds")
                continue

            # Skip if we're already there
            if adj_pos == current_pos:
                # Already adjacent - return empty path (success)
                logger.debug(f"_find_path_to_adjacent: already at {adj_pos} (adjacent to target)")
                return PathResult([], PathStopReason.SUCCESS, f"Already adjacent to {target}")

            # Try to path to this adjacent tile
            path_result = self._find_path(adj_pos, allow_with_hostiles=allow_with_hostiles)
            logger.debug(f"_find_path_to_adjacent: {direction.value} {adj_pos} -> {path_result.reason.value} (path_len={len(path_result.path)})")

            if path_result.success and len(path_result.path) < best_distance:
                best_path = path_result
                best_distance = len(path_result.path)

        logger.debug(f"_find_path_to_adjacent: best_path={best_path}")
        return best_path

    def find_nearest(
        self,
        predicate: Callable[[Tile], bool],
        max_distance: int = 100,
    ) -> Optional[Position]:
        """Find nearest tile matching a predicate."""
        if not self.observation:
            return None
        return find_nearest(self.observation, predicate, max_distance)

    def find_unexplored(
        self,
        allow_with_hostiles: bool = False,
        excluded_positions: Optional[set[Position]] = None,
    ) -> TargetResult:
        """
        Find best unexplored tile using NetHack4's algorithm.

        Following NetHack4 conventions:
        - Refuses to search when hostiles visible
        - Uses stepped tracking to avoid revisiting tiles
        - Weights destinations: items > features > rooms > corridors

        Args:
            allow_with_hostiles: Override hostile check
            excluded_positions: Set of positions to exclude (e.g., abandoned targets)

        Returns TargetResult with:
        - position: Target Position or None
        - reason: PathStopReason (SUCCESS, HOSTILE_IN_VIEW, NO_TARGET_FOUND)
        - message: Human-readable explanation
        - Can check: `if result:` for success
        """
        if not self.observation:
            return TargetResult(None, PathStopReason.NO_OBSERVATION, "No observation available")

        # Get stepped memory for current level
        dungeon_level = int(self.observation.blstats[12])  # BL_DEPTH
        stepped_memory = self._dungeon_memory.get_level(dungeon_level, create=True)

        return find_unexplored(
            self.observation,
            stepped_memory=stepped_memory,
            allow_with_hostiles=allow_with_hostiles,
            excluded_positions=excluded_positions,
        )

    def autoexplore(self, max_steps: int = 500) -> AutoexploreResult:
        """
        Explore automatically until interrupted (NetHack4-style).

        Runs exploration as a loop, moving toward unexplored areas and
        stopping when:
        - No unexplored areas reachable (fully_explored)
        - Hostile monster appears (hostile)
        - HP drops below 30% (low_hp)
        - Found interesting feature - stairs, altar, etc. (feature)
        - Item found on ground (item)
        - Engraving found (engraving)
        - max_steps reached (max_steps)
        - Hunger >= WEAK (hungry)
        - Blind, confused, or stunned (blocked)
        - In Sokoban (sokoban)

        Returns:
            AutoexploreResult with stop_reason, steps_taken, position
        """
        if not self.observation:
            return AutoexploreResult(
                stop_reason="no_observation",
                steps_taken=0,
                turns_elapsed=0,
                position=Position(0, 0),
                message="No observation available",
            )

        # Pre-checks: conditions that block autoexplore entirely
        if is_blind(self.observation):
            return AutoexploreResult(
                stop_reason="blind",
                steps_taken=0,
                turns_elapsed=0,
                position=self.position,
                message="Cannot autoexplore while blind",
            )

        if is_confused(self.observation) or is_stunned(self.observation):
            return AutoexploreResult(
                stop_reason="confused",
                steps_taken=0,
                turns_elapsed=0,
                position=self.position,
                message="Cannot autoexplore while stunned/confused",
            )

        if in_sokoban(self.observation):
            return AutoexploreResult(
                stop_reason="sokoban",
                steps_taken=0,
                turns_elapsed=0,
                position=self.position,
                message="Sokoban layout is auto-mapped - explore manually",
            )

        steps_taken = 0
        turns_start = self.turn
        start_position = self.position
        failed_attempts = 0  # Safety counter for infinite loop prevention
        max_failed_attempts = 20  # Give up after this many consecutive failures

        # Track recent positions to detect oscillation (walking back and forth)
        recent_positions: list[Position] = []
        max_recent = 10  # How many positions to track
        oscillation_threshold = 3  # If we revisit same position this many times, we're stuck

        # Target stickiness: once we pick a target, continue toward it until we
        # reach it or it becomes invalid. This prevents oscillation where we keep
        # switching between two targets that trade places as "best" based on position.
        current_target: Optional[Position] = None
        target_attempts = 0  # Consecutive failed attempts to reach current target
        max_target_attempts = 5  # Pick new target after this many failures
        # Track recently abandoned targets to avoid re-selecting them immediately.
        # After abandoning a target, we skip it for a few iterations to try other areas first.
        recently_abandoned: list[Position] = []  # FIFO queue of recently abandoned targets
        max_recently_abandoned = 3  # Keep last N abandoned targets in the skip list

        # Track starting hunger state for conditional stopping:
        # - If started NOT hungry → stop when becomes HUNGRY
        # - If started HUNGRY → stop only when becomes WEAK
        starting_stats = self.get_stats()
        started_hungry = starting_stats.is_hungry

        while steps_taken < max_steps:
            # Check if game ended
            if self.is_done:
                return AutoexploreResult(
                    stop_reason="game_over",
                    steps_taken=steps_taken,
                    turns_elapsed=self.turn - turns_start,
                    position=self.position,
                    message="Game ended",
                )

            # Check HP
            stats = self.get_stats()
            if stats.hp / max(stats.max_hp, 1) < 0.3:
                steps_msg = f" after {steps_taken} steps" if steps_taken > 0 else ""
                return AutoexploreResult(
                    stop_reason="low_hp",
                    steps_taken=steps_taken,
                    turns_elapsed=self.turn - turns_start,
                    position=self.position,
                    message=f"HP low: {stats.hp}/{stats.max_hp}{steps_msg}",
                )

            # Check hunger - conditional based on starting state:
            # - If started NOT hungry → stop when becomes HUNGRY
            # - If started HUNGRY → stop only when becomes WEAK
            should_stop_hunger = False
            if started_hungry:
                # Started hungry - only stop if now WEAK
                if stats.is_weak:
                    should_stop_hunger = True
            else:
                # Started not hungry - stop if now HUNGRY
                if stats.is_hungry:
                    should_stop_hunger = True

            if should_stop_hunger:
                steps_msg = f" after {steps_taken} steps" if steps_taken > 0 else ""
                hunger_msg = "Weak - need food urgently" if stats.is_weak else "Hungry - need food"
                return AutoexploreResult(
                    stop_reason="hungry",
                    steps_taken=steps_taken,
                    turns_elapsed=self.turn - turns_start,
                    position=self.position,
                    message=f"{hunger_msg}{steps_msg}",
                )

            # Check for hostile monsters
            hostiles = self.get_hostile_monsters()
            if hostiles:
                steps_msg = f" after {steps_taken} steps" if steps_taken > 0 else ""
                return AutoexploreResult(
                    stop_reason="hostile",
                    steps_taken=steps_taken,
                    turns_elapsed=self.turn - turns_start,
                    position=self.position,
                    message=f"Hostile: {hostiles[0].name}{steps_msg}",
                )

            # Check for items on ground
            items_here = self.get_items_here()
            if items_here and steps_taken > 0:  # Don't stop immediately if starting on item
                return AutoexploreResult(
                    stop_reason="item",
                    steps_taken=steps_taken,
                    turns_elapsed=self.turn - turns_start,
                    position=self.position,
                    message=f"Found item: {items_here[0].name} after {steps_taken} steps",
                )

            # Note: We no longer stop at dead ends - let autoexplore continue until
            # there are no more reachable unexplored areas. The agent can decide
            # when to search for secret doors based on the visible map.

            # Check for unvisited interesting features
            current_pos = self.position
            current_tile = self.get_tile(current_pos)
            if current_tile and steps_taken > 0:
                if current_tile.is_stairs_up or current_tile.is_stairs_down:
                    return AutoexploreResult(
                        stop_reason="stairs",
                        steps_taken=steps_taken,
                        turns_elapsed=self.turn - turns_start,
                        position=self.position,
                        message=f"Found stairs after {steps_taken} steps",
                    )
                if current_tile.feature in ('altar', 'throne', 'fountain', 'sink'):
                    return AutoexploreResult(
                        stop_reason="feature",
                        steps_taken=steps_taken,
                        turns_elapsed=self.turn - turns_start,
                        position=self.position,
                        message=f"Found {current_tile.feature} after {steps_taken} steps",
                    )

            # Target stickiness: only find new target if we don't have one or current is invalid
            need_new_target = False
            if current_target is None:
                need_new_target = True
            elif self.position == current_target:
                # Reached current target
                need_new_target = True
            elif self._dungeon_memory and self.observation:
                # Check if target has been stepped on (no longer interesting)
                dungeon_lvl = int(self.observation.blstats[12])  # BL_DEPTH
                level_mem = self._dungeon_memory.get_level(dungeon_lvl)
                if level_mem and level_mem.is_stepped(current_target.x, current_target.y):
                    need_new_target = True
            if target_attempts >= max_target_attempts:
                # Too many failures reaching current target - try a different one
                logger.debug(f"autoexplore: abandoning target {current_target} after {target_attempts} failed attempts")
                if current_target:
                    recently_abandoned.append(current_target)
                    # Keep only the most recent N abandoned targets
                    if len(recently_abandoned) > max_recently_abandoned:
                        recently_abandoned.pop(0)
                need_new_target = True
                target_attempts = 0

            if need_new_target:
                # Try to find unexplored areas, skipping recently abandoned targets
                excluded = set(recently_abandoned)
                target_result = self.find_unexplored(excluded_positions=excluded)

                # If no targets found but we have recently abandoned ones, try again without exclusions
                if not target_result and recently_abandoned:
                    logger.debug(f"autoexplore: no targets found, clearing {len(recently_abandoned)} recently abandoned")
                    recently_abandoned.clear()
                    target_result = self.find_unexplored()
                current_target = None
                target_attempts = 0

                if not target_result:
                    # No unexplored areas found - but check for closed doors first
                    if target_result.reason == PathStopReason.NO_TARGET_FOUND:
                        # Try to open any closed doors before declaring fully explored
                        door_opened = self._try_open_nearest_closed_door()
                        if door_opened:
                            # Door was opened, continue exploring
                            steps_taken += 1
                            failed_attempts = 0
                            continue
                        # No doors to open - check if truly fully explored or just blocked
                        if self._has_unreachable_areas():
                            # There ARE visible areas we can't reach
                            # Could be: closed door we can't path to, or disconnected area
                            return AutoexploreResult(
                                stop_reason="blocked",
                                steps_taken=steps_taken,
                                turns_elapsed=self.turn - turns_start,
                                position=self.position,
                                message="Cannot reach visible areas - path may be blocked",
                            )
                        else:
                            # Truly fully explored
                            return AutoexploreResult(
                                stop_reason="fully_explored",
                                steps_taken=steps_taken,
                                turns_elapsed=self.turn - turns_start,
                                position=self.position,
                                message=f"Visible areas explored ({steps_taken} steps). Hidden rooms may exist behind secret doors.",
                            )
                    # Hostiles detected by find_unexplored
                    return AutoexploreResult(
                        stop_reason="hostile",
                        steps_taken=steps_taken,
                        turns_elapsed=self.turn - turns_start,
                        position=self.position,
                        message=target_result.message,
                    )

                current_target = target_result.position

            target = current_target

            # Handle ALREADY_AT_TARGET - move into unexplored direction
            if target_result.reason == PathStopReason.ALREADY_AT_TARGET:
                moved = False
                # Check if we're in a doorway (affects diagonal movement)
                current_tile = self.get_tile(current_pos)
                in_doorway = current_tile and is_doorway_glyph(current_tile.glyph)

                # Try cardinal directions first (required if in doorway)
                directions_to_try = list(CARDINAL_DIRECTIONS)
                if not in_doorway:
                    # Only add diagonals if not in doorway
                    directions_to_try.extend(DIAGONAL_DIRECTIONS)

                for direction in directions_to_try:
                    adj_pos = current_pos.move(direction)
                    adj_tile = self.get_tile(adj_pos)
                    # Must be unexplored AND potentially walkable (not a wall)
                    if adj_tile and not adj_tile.is_explored and adj_tile.char != ' ':
                        result = self.move(direction)
                        if result.success:
                            steps_taken += 1
                            failed_attempts = 0
                            moved = True
                            break
                if not moved:
                    # Can't move into unexplored - check if there are other visible unexplored areas
                    if self._has_unreachable_areas():
                        return AutoexploreResult(
                            stop_reason="blocked",
                            steps_taken=steps_taken,
                            turns_elapsed=self.turn - turns_start,
                            position=self.position,
                            message="Cannot reach visible areas - path may be blocked",
                        )
                    else:
                        return AutoexploreResult(
                            stop_reason="fully_explored",
                            steps_taken=steps_taken,
                            turns_elapsed=self.turn - turns_start,
                            position=self.position,
                            message="No visible unexplored areas. Hidden rooms may exist behind secret doors.",
                        )
                continue

            # Find path to target
            path_result = self._find_path(target)
            if not path_result or not path_result.path:
                # Path blocked - try opening a door before giving up
                failed_attempts += 1
                target_attempts += 1  # Track failures for current target
                if failed_attempts >= max_failed_attempts:
                    # Last resort: try to open any closed door
                    door_opened = self._try_open_nearest_closed_door()
                    if door_opened:
                        steps_taken += 1
                        failed_attempts = 0
                        continue
                    steps_msg = f" after {steps_taken} steps" if steps_taken > 0 else ""
                    return AutoexploreResult(
                        stop_reason="blocked",
                        steps_taken=steps_taken,
                        turns_elapsed=self.turn - turns_start,
                        position=self.position,
                        message=f"Too many pathfinding failures{steps_msg}",
                    )
                continue

            # Move one step along path
            direction = path_result.path[0]
            pos_before_move = self.position
            result = self.move(direction)

            if result.success:
                steps_taken += 1
                failed_attempts = 0  # Reset on successful move
                target_attempts = 0  # Reset target attempts on progress

                # Track position for oscillation detection
                current_pos = self.position
                visit_count = recent_positions.count(current_pos)
                if visit_count >= oscillation_threshold:
                    logger.debug(f"autoexplore: oscillation detected at {current_pos} (visited {visit_count + 1} times)")
                    return AutoexploreResult(
                        stop_reason="blocked",
                        steps_taken=steps_taken,
                        turns_elapsed=self.turn - turns_start,
                        position=self.position,
                        message=f"Oscillation detected - revisited {current_pos} too many times",
                    )
                recent_positions.append(current_pos)
                if len(recent_positions) > max_recent:
                    recent_positions.pop(0)  # Remove oldest

                # Check for engraving messages after move
                messages = result.messages
                for msg in messages:
                    msg_lower = msg.lower()
                    if "you read:" in msg_lower or "something is written" in msg_lower:
                        return AutoexploreResult(
                            stop_reason="engraving",
                            steps_taken=steps_taken,
                            turns_elapsed=self.turn - turns_start,
                            position=self.position,
                            message=f"Found engraving: {msg[:50]}",
                        )
            else:
                # Movement failed - check if this was a diagonal move
                # If so, try going around with cardinal moves (doorway restriction workaround)
                is_diagonal = direction in (Direction.NE, Direction.NW, Direction.SE, Direction.SW)
                if is_diagonal and self.position == pos_before_move:
                    # Try cardinal moves to go around (e.g., NE -> try N then E, or E then N)
                    cardinal_pairs = {
                        Direction.NE: [(Direction.N, Direction.E), (Direction.E, Direction.N)],
                        Direction.NW: [(Direction.N, Direction.W), (Direction.W, Direction.N)],
                        Direction.SE: [(Direction.S, Direction.E), (Direction.E, Direction.S)],
                        Direction.SW: [(Direction.S, Direction.W), (Direction.W, Direction.S)],
                    }
                    went_around = False
                    for first, second in cardinal_pairs[direction]:
                        r1 = self.move(first)
                        if r1.success:
                            r2 = self.move(second)
                            if r2.success:
                                steps_taken += 2
                                failed_attempts = 0
                                target_attempts = 0  # Made progress
                                went_around = True
                                break
                            else:
                                # First move worked but second didn't - still made progress
                                steps_taken += 1
                                failed_attempts = 0
                                target_attempts = 0  # Made progress
                                went_around = True
                                break
                    if went_around:
                        continue
                    # Couldn't go around either - fall through to failed_attempts

                # Cardinal movement failed - try opening door
                self.open_door(direction)
                result = self.move(direction)
                if result.success:
                    steps_taken += 1
                    failed_attempts = 0  # Reset on successful move
                    target_attempts = 0  # Made progress
                else:
                    # Still blocked, find new target
                    failed_attempts += 1
                    target_attempts += 1  # Track failures for current target
                    if failed_attempts >= max_failed_attempts:
                        steps_msg = f" after {steps_taken} steps" if steps_taken > 0 else ""
                        return AutoexploreResult(
                            stop_reason="blocked",
                            steps_taken=steps_taken,
                            turns_elapsed=self.turn - turns_start,
                            position=self.position,
                            message=f"Too many movement failures{steps_msg}",
                        )
                    continue

        # Max steps reached
        return AutoexploreResult(
            stop_reason="max_steps",
            steps_taken=steps_taken,
            turns_elapsed=self.turn - turns_start,
            position=self.position,
            message=f"Explored {steps_taken} steps, reached max ({max_steps})",
        )

    def find_stairs_up(self, allow_with_hostiles: bool = False) -> TargetResult:
        """
        Find stairs up position (<).

        Returns TargetResult with position and reason.
        """
        if not self.observation:
            return TargetResult(None, PathStopReason.NO_OBSERVATION, "No observation available")
        return find_stairs_up(self.observation, allow_with_hostiles=allow_with_hostiles)

    def find_stairs_down(self, allow_with_hostiles: bool = False) -> TargetResult:
        """
        Find stairs down position (>).

        Returns TargetResult with position and reason.
        """
        if not self.observation:
            return TargetResult(None, PathStopReason.NO_OBSERVATION, "No observation available")
        return find_stairs_down(self.observation, allow_with_hostiles=allow_with_hostiles)

    def find_nearest_monster(self) -> Optional[Position]:
        """Find nearest hostile monster."""
        if not self.observation:
            return None
        return find_nearest_monster(self.observation)

    def find_nearest_item(self) -> TargetResult:
        """
        Find nearest item on the map.

        Returns:
            TargetResult with position of nearest item, or failure if none found.
        """
        if not self.observation:
            return TargetResult(
                position=None,
                reason=PathStopReason.NO_OBSERVATION,
                message="No observation available",
            )

        items = find_items_on_map(self.observation)
        if not items:
            return TargetResult(
                position=None,
                reason=PathStopReason.NO_TARGET_FOUND,
                message="No items visible on map",
            )

        player_pos = self.position
        nearest = min(items, key=lambda item: player_pos.distance_to(item.position))
        return TargetResult(
            position=nearest.position,
            reason=PathStopReason.SUCCESS,
            message=f"Found {nearest.name}",
        )

    def get_items_on_map(self) -> list[Item]:
        """
        Get all visible items on the map (not inventory).

        Returns:
            List of Item objects for all visible items.
        """
        if not self.observation:
            return []
        return find_items_on_map(self.observation)

    # ==================== Knowledge Base ====================

    def lookup_monster(self, name: str) -> Optional[MonsterInfo]:
        """Look up monster information."""
        return lookup_monster(name)

    def is_dangerous_melee(self, monster_name: str) -> bool:
        """Check if monster is dangerous to attack in melee."""
        return is_dangerous_melee(monster_name)

    def is_corpse_safe(self, monster_name: str) -> bool:
        """Check if monster corpse is safe to eat."""
        return is_corpse_safe(monster_name)

    def get_corpse_effects(self, monster_name: str) -> list[str]:
        """Get effects of eating a monster's corpse."""
        return get_corpse_effects(monster_name)

    def is_prayer_safe(self) -> bool:
        """Check if prayer timeout has passed."""
        return is_prayer_safe(self._last_prayer_turn, self.turn)

    def elbereth_effective(self, monster_name: str) -> bool:
        """Check if Elbereth scares a monster."""
        return elbereth_effective_against(monster_name)

    def estimate_difficulty(self, monster_name: str) -> int:
        """Estimate monster difficulty (0-10)."""
        return estimate_monster_difficulty(monster_name)
