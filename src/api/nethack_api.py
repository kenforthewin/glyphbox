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
    find_path,
    find_unexplored,
    is_doorway_glyph,
)
from .queries import (
    find_altars,
    find_doors,
    find_items_on_map,
    find_stairs,
    get_adjacent_hostiles,
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
        character: str = "val-hum-fem-law",
    ):
        """
        Initialize the NetHack API.

        Args:
            env_name: Gymnasium environment name
            max_episode_steps: Maximum steps per episode
            render_mode: Render mode ("human", "ansi", or None)
            dungeon_memory: Optional dungeon memory for exploration tracking
            character: NetHack character spec (e.g. "random", "val-hum-fem-law")
        """
        self._env = NLEWrapper(
            env_name=env_name,
            max_episode_steps=max_episode_steps,
            render_mode=render_mode,
            character=character,
        )
        self._actions: Optional[ActionExecutor] = None
        self._last_prayer_turn = 0
        self._message_history: list[str] = []
        self._dungeon_memory = dungeon_memory or DungeonMemory()
        # Reminders and notes for agent context
        self._reminders: list[tuple[int, str]] = []  # (fire_turn, message)
        self._notes: dict[int, tuple[int, str]] = {}  # {note_id: (expire_turn, message)}
        self._next_note_id: int = 1

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
        self._reminders = []
        self._notes = {}
        self._next_note_id = 1
        # Record initial position and visible tiles for pathfinding
        self._mark_current_position_stepped()
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

    def sync_level_memory(self) -> None:
        """
        Sync level memory with current observation.

        Call this at the start of each agent turn to ensure pathfinding has
        accurate information. The map can change between turns due to:
        - Monsters dying (corpses appear)
        - Doors opening/closing
        - Items being picked up or dropped
        - Pet movement revealing new areas
        - etc.

        This ensures level memory always matches what the agent sees on screen.
        """
        if not self.observation:
            return
        dungeon_level = int(self.observation.blstats[12])  # BL_DEPTH
        level = self._dungeon_memory.get_level(dungeon_level, create=True)
        self._update_visible_walkable_tiles(level)

    def _get_blocking_info(self) -> tuple[bool, str]:
        """
        Check if there are areas we can see but can't reach, and explain why.

        This detects when:
        1. There are closed doors we can't path to or open
        2. There are visible floor tiles we haven't stepped on and can't reach

        Used to distinguish between "fully explored" (everything reachable visited)
        and "blocked" (visible areas exist but aren't reachable).

        Returns:
            Tuple of (is_blocked, explanation_message)
        """
        if not self.observation:
            return (False, "")

        # Are there visible floor tiles we haven't stepped on and can't reach?
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
            tile_positions = [f"({t.x}, {t.y})" for t in unreachable_tiles[:3]]
            logger.debug(f"_get_blocking_info: Found {len(unreachable_tiles)} unreachable walkable tile(s), e.g. {unreachable_tiles[:3]}")
            return (True, f"Visible areas at {', '.join(tile_positions)} are unreachable.")

        return (False, "")

    def _has_unreachable_areas(self) -> bool:
        """Check if there are areas we can see but can't reach."""
        is_blocked, _ = self._get_blocking_info()
        return is_blocked

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
    def role(self) -> str:
        """Get the player's role (class) name, e.g. 'Valkyrie', 'Barbarian'."""
        return self._env.role

    @property
    def position(self) -> Position:
        """Get player's current position."""
        if self.observation:
            return get_position(self.observation)
        return Position(0, 0)

    @property
    def hp(self) -> int:
        """Get current HP. Use in conditionals: `if nh.hp < 10:`"""
        if self.observation:
            return get_stats(self.observation).hp
        return 0

    @property
    def max_hp(self) -> int:
        """Get maximum HP. Use in conditionals: `if nh.hp < nh.max_hp * 0.3:`"""
        if self.observation:
            return get_stats(self.observation).max_hp
        return 0

    @property
    def dungeon_level(self) -> int:
        """Get current dungeon level."""
        if self.observation:
            return get_stats(self.observation).dungeon_level
        return 0

    @property
    def is_hungry(self) -> bool:
        """True if hunger is Hungry, Weak, or Fainting. Use for food decisions."""
        if self.observation:
            stats = get_stats(self.observation)
            from .models import HungerState
            return stats.hunger in (HungerState.HUNGRY, HungerState.WEAK, HungerState.FAINTING)
        return False

    @property
    def is_weak(self) -> bool:
        """True if hunger is Weak or Fainting. CRITICAL - eat immediately!"""
        if self.observation:
            stats = get_stats(self.observation)
            from .models import HungerState
            return stats.hunger in (HungerState.WEAK, HungerState.FAINTING)
        return False

    @property
    def has_adjacent_hostile(self) -> bool:
        """True if there's a hostile monster in any adjacent tile. Use in combat loops."""
        if self.observation:
            return len(get_adjacent_hostiles(self.observation)) > 0
        return False

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

    def get_screen_colors(self) -> str:
        """Get screen color data as base64-encoded string."""
        if not self.observation:
            return ""
        return self.observation.get_screen_colors_base64()

    def get_local_map(self, radius: int = 7) -> str:
        """
        Get an LLM-optimized local map centered on the player.

        Shows only tiles within `radius` of the player position,
        with coordinate guides on the edges for spatial reasoning.
        Includes the status bar (last 2 rows) for HP/stats info.

        Args:
            radius: Number of tiles in each direction from player

        Returns:
            Formatted local map string with coordinate guides and status bar
        """
        if not self.observation:
            return ""

        obs = self.observation
        player_x = obs.player_x
        player_y = obs.player_y

        # Calculate view bounds (map area is rows 1-21, cols 0-78)
        # Row 0 is message line, rows 22-23 are status bar
        x_min = max(0, player_x - radius)
        x_max = min(78, player_x + radius)
        y_min = max(1, player_y - radius)  # Start at row 1 (skip message line)
        y_max = min(20, player_y + radius)  # Max row is 20 (0-indexed, 21 rows total)

        lines = []

        # Header
        lines.append(f"LOCAL VIEW (radius={radius} around you, N=up):")

        # Build column header (x coordinates)
        # Use 4-char wide cells for better visual alignment
        row_label_width = 6  # "   XX:" = 6 chars
        col_header = " " * row_label_width
        for x in range(x_min, x_max + 1):
            col_header += f"{x:^4d}"  # Center the number in 4 chars
        lines.append(col_header)

        # Build map rows with row labels (y coordinates)
        for y in range(y_min, y_max + 1):
            row_label = f"{y:5d}:"
            row_chars = ""
            for x in range(x_min, x_max + 1):
                char = chr(obs.chars[y, x])
                row_chars += f" {char}  "  # Center char in 4 chars (1 space + char + 2 spaces)
            lines.append(row_label + row_chars)

        # Add blank line separator
        lines.append("")

        # Append status bar (last 2 rows from tty_chars - rows 22 and 23)
        for row_idx in [22, 23]:
            status_line = bytes(obs.tty_chars[row_idx]).decode("latin-1", errors="replace").rstrip()
            lines.append(status_line)

        return "\n".join(lines)

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

    def get_adjacent_hostiles(self) -> list[Monster]:
        """Get hostile monsters in the 8 adjacent tiles (for combat)."""
        if not self.observation:
            return []
        return get_adjacent_hostiles(self.observation)

    def get_hostile_monsters(self) -> list[Monster]:
        """Get only hostile (non-pet) monsters."""
        if not self.observation:
            return []
        return get_hostile_monsters(self.observation)

    def get_adjacent_tiles(self) -> dict[str, str]:
        """
        Get descriptions of tiles in the 8 adjacent directions.

        Returns a dict mapping direction names (N, NE, E, SE, S, SW, W, NW)
        to brief tile descriptions using the existing parse_glyph() logic.
        """
        if not self.observation:
            return {}

        from .glyphs import parse_glyph, GlyphType

        pos = self.position
        obs = self.observation
        result = {}

        # Direction offsets: (dx, dy)
        directions = {
            "N": (0, -1),
            "NE": (1, -1),
            "E": (1, 0),
            "SE": (1, 1),
            "S": (0, 1),
            "SW": (-1, 1),
            "W": (-1, 0),
            "NW": (-1, -1),
        }

        for dir_name, (dx, dy) in directions.items():
            x, y = pos.x + dx, pos.y + dy

            # Bounds check
            if not (0 <= x < 79 and 0 <= y < 21):
                result[dir_name] = "out of bounds"
                continue

            glyph = int(obs.glyphs[y, x])
            char = chr(obs.chars[y, x])

            # Get screen description (authoritative for monster/item names)
            description = ""
            if obs.screen_descriptions is not None:
                desc_bytes = bytes(obs.screen_descriptions[y, x])
                description = desc_bytes.decode("latin-1", errors="replace").rstrip("\x00")

            # Use parse_glyph - it already has all the logic
            info = parse_glyph(glyph, char, description)
            # Include character for monsters/pets so agent can match with map
            # e.g. "kitten 'f'" helps distinguish from "fox 'd'"
            if info.glyph_type in (GlyphType.MONSTER, GlyphType.PET):
                result[dir_name] = f"{info.name} '{char}'"
            else:
                result[dir_name] = info.name

        return result

    def get_items_at(self, pos: Position) -> list[Item]:
        """Get items at a specific position."""
        if not self.observation:
            return []
        return get_items_at(self.observation, pos)

    def get_items_here_glyphs(self) -> list[Item]:
        """Get items at player's position using glyph data only (no commands sent).

        Note: Returns empty when standing on items since the player glyph
        obscures item glyphs. Use get_items_here() for reliable results.
        """
        if not self.observation:
            return []
        return get_items_here(self.observation)

    def get_items_here(self) -> list[Item]:
        """
        Get items at player's current position.

        Uses the look command (:) which is a free action (costs no turns).
        This is necessary because when standing on items, the player glyph
        obscures the item glyph in the observation.
        """
        if not self._actions:
            return []

        pos = self.get_position()

        # Send : (look) without prompt handling so we can read the screen
        result = self._actions._execute_single(ord(":"), handle_prompts=False)
        obs = self._env.last_observation
        if not obs:
            return []

        items: list[Item] = []

        # Case 1: Single item — appears in message buffer as "You see here a X."
        msg = obs.get_message()
        if "You see here" in msg:
            # Extract item name from "You see here a/an <name>."
            # Handle compound messages like "There is a staircase up here.  You see here a sword."
            for part in msg.split("."):
                part = part.strip()
                if "You see here" in part:
                    name = part.replace("You see here ", "").rstrip(".")
                    # Strip leading article
                    for article in ("a ", "an ", "the "):
                        if name.startswith(article):
                            name = name[len(article):]
                            break
                    items.append(Item(glyph=0, name=name, position=pos))

        # Case 2: Multiple items — shown on TTY screen as "Things that are here:"
        # followed by item lines, then "--More--"
        elif obs.in_more_prompt:
            screen_lines = obs.get_screen_lines()
            in_list = False
            for line in screen_lines:
                stripped = line.strip()
                if "Things that are here:" in stripped or "Things that you feel here:" in stripped:
                    in_list = True
                    continue
                if in_list:
                    if stripped == "--More--" or stripped == "":
                        break
                    name = stripped
                    for article in ("a ", "an ", "the "):
                        if name.startswith(article):
                            name = name[len(article):]
                            break
                    items.append(Item(glyph=0, name=name, position=pos))

        # Dismiss any remaining --More-- prompts so game state is clean
        self._actions._handle_all_prompts()

        return items

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
        """
        Find stairs up and down positions.

        Uses both current observation AND level memory, so stairs are found
        even if the player is standing on them (which hides the stair character).
        """
        if not self.observation:
            return None, None

        # First check current observation
        stairs_up, stairs_down = find_stairs(self.observation)

        # If not found, check level memory (stairs may be hidden because player is on them)
        if self._dungeon_memory:
            dungeon_level = int(self.observation.blstats[12])  # BL_DEPTH
            level = self._dungeon_memory.get_level(dungeon_level)
            if level:
                if stairs_up is None and level.upstairs_pos:
                    stairs_up = Position(level.upstairs_pos[0], level.upstairs_pos[1])
                if stairs_down is None and level.downstairs_pos:
                    stairs_down = Position(level.downstairs_pos[0], level.downstairs_pos[1])

        return stairs_up, stairs_down

    def find_doors(self) -> list[tuple[Position, bool]]:
        """Find all doors (position, is_open)."""
        if not self.observation:
            return []
        return find_doors(self.observation)

    def find_altars(self) -> list[Position]:
        """Find all altars on current level."""
        if not self.observation:
            return []
        return find_altars(self.observation)

    def get_overview(self) -> str:
        """
        Get dungeon overview (#overview command output).

        Executes the #overview extended command and captures the screen text.
        This is a free action that doesn't consume a game turn.
        Returns empty string if unavailable.
        """
        if not self._actions or not self.observation:
            return ""
        return self._actions.get_overview_screen()

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

    def move(self, direction: Direction, count: int = 1) -> ActionResult:
        """
        Move in a direction.

        Args:
            direction: Direction to move (N, S, E, W, NE, NW, SE, SW)
            count: Number of tiles to move (default 1). Higher counts use NetHack's
                   count prefix (e.g., 5l) which auto-stops at walls/monsters.

        Returns:
            ActionResult indicating success/failure
        """
        if not self._actions:
            return ActionResult.failure("Environment not initialized")
        result = self._actions.move(direction, count)
        self._record_messages(result.messages)
        if result.success:
            self._mark_current_position_stepped()
        return result

    def run(self, direction: Direction) -> ActionResult:
        """
        Run in a direction until interrupted.

        Runs until hitting a wall, reaching an intersection/doorway, seeing a monster,
        or taking damage. Faster than move() for long corridors, and NetHack handles
        all safety interrupts automatically.

        Args:
            direction: Direction to run (N, S, E, W, NE, NW, SE, SW)

        Returns:
            ActionResult indicating success/failure
        """
        if not self._actions:
            return ActionResult.failure("Environment not initialized")
        result = self._actions.run(direction)
        self._record_messages(result.messages)
        if result.success:
            self._mark_current_position_stepped()
        return result

    def move_to(self, target, pass_through_doors: bool = False) -> ActionResult:
        """
        Move to a target position by pathfinding and following the path.

        This is a convenience method that combines find_path + move loop.
        Stops early if movement fails (blocked, combat, etc.) or if the
        player becomes hungry or drops below 30% HP during travel.

        If the target is unwalkable (monster, closed door, wall), automatically
        moves to the nearest adjacent tile instead.

        Args:
            target: Position object or (x, y) tuple
            pass_through_doors: If True, treat closed doors as passable (like NetHack travel)

        Returns:
            ActionResult with success/failure and messages from the journey.
            - success: True if reached target position (or adjacent if target unwalkable)
            - messages: All game messages encountered during movement
        """
        target = self._to_position(target)

        # Find path to target (always allow with hostiles - agent made conscious decision)
        path_result = self._find_path(target, allow_with_hostiles=True, pass_through_doors=pass_through_doors)

        # If target is unwalkable, try to path to an adjacent tile instead
        if not path_result.success and path_result.reason == PathStopReason.TARGET_UNWALKABLE:
            # Find best adjacent tile to path to
            adjacent_path = self._find_path_to_adjacent(target, allow_with_hostiles=True)
            # Note: use 'is not None' because empty path with SUCCESS still needs to be used
            if adjacent_path is not None and adjacent_path.success:
                path_result = adjacent_path
            elif adjacent_path is None:
                # No path to ANY adjacent tile - areas are disconnected
                return ActionResult.failure(
                    f"No path to {target} - area appears disconnected."
                )

        if not path_result.success:
            return ActionResult.failure(f"No path: {path_result.message}")

        # Follow the path
        # Track hunger state to detect transitions (not-hungry→hungry, hungry→weak).
        # We only interrupt on transitions, not on current state, so the agent
        # can still use move_to() to walk to food while already hungry.
        all_messages = []
        prev_hunger = None
        if self.observation:
            prev_hunger = get_stats(self.observation).hunger
        prev_hp_frac = None
        if self.observation:
            s = get_stats(self.observation)
            prev_hp_frac = s.hp / max(s.max_hp, 1)

        for direction in path_result:
            result = self.move(direction)
            all_messages.extend(result.messages)

            if not result.success:
                # If move failed and we're passing through doors, try opening the door
                if pass_through_doors:
                    open_result = self.open_door(direction)
                    all_messages.extend(open_result.messages)
                    if open_result.success:
                        # Door opened, retry the move
                        result = self.move(direction)
                        all_messages.extend(result.messages)

                if not result.success:
                    # If we're adjacent to target, consider it success
                    # (we got as close as possible - target may be unwalkable)
                    if self.position.chebyshev_distance(target) == 1:
                        return ActionResult(success=True, messages=all_messages, turn_elapsed=result.turn_elapsed)
                    return ActionResult(
                        success=False,
                        messages=all_messages,
                        turn_elapsed=result.turn_elapsed,
                    )

            # Safety checks: interrupt on state TRANSITIONS, not current state.
            # This prevents loot sweeps from starving the player while still
            # allowing move_to() to work when already hungry (e.g. walking to food).
            if self.observation:
                stats = get_stats(self.observation)

                # Hunger transition: not-hungry→hungry, or hungry→weak/fainting
                from .models import HungerState
                cur_hunger = stats.hunger
                if prev_hunger is not None and cur_hunger != prev_hunger:
                    worsened = (
                        (prev_hunger == HungerState.NOT_HUNGRY and cur_hunger in (HungerState.HUNGRY, HungerState.WEAK, HungerState.FAINTING)) or
                        (prev_hunger == HungerState.SATIATED and cur_hunger in (HungerState.HUNGRY, HungerState.WEAK, HungerState.FAINTING)) or
                        (prev_hunger == HungerState.HUNGRY and cur_hunger in (HungerState.WEAK, HungerState.FAINTING)) or
                        (prev_hunger == HungerState.WEAK and cur_hunger == HungerState.FAINTING)
                    )
                    if worsened:
                        all_messages.append(f"Interrupted: hunger worsened to {cur_hunger.value} at {self.position}")
                        logger.debug(f"move_to: hunger transition {prev_hunger.value}->{cur_hunger.value} at {self.position} (target was {target})")
                        return ActionResult(success=False, messages=all_messages, turn_elapsed=True)
                prev_hunger = cur_hunger

                # HP transition: crossed below 30%
                cur_hp_frac = stats.hp / max(stats.max_hp, 1)
                if prev_hp_frac is not None and prev_hp_frac >= 0.3 and cur_hp_frac < 0.3:
                    all_messages.append(f"Interrupted: HP dropped to {stats.hp}/{stats.max_hp} at {self.position}")
                    logger.debug(f"move_to: HP transition {prev_hp_frac:.0%}->{cur_hp_frac:.0%} at {self.position} (target was {target})")
                    return ActionResult(success=False, messages=all_messages, turn_elapsed=True)
                prev_hp_frac = cur_hp_frac

            # Note: We don't interrupt for hostiles - agent made conscious decision to travel.
            # If a hostile blocks the path, the move() will fail naturally.

        # Verify we reached the target (or adjacent if target is unwalkable)
        if self.position == target:
            return ActionResult(success=True, messages=all_messages, turn_elapsed=True)
        elif self.position.chebyshev_distance(target) == 1:
            # Successfully moved adjacent to target (close enough)
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

    def wait(self, count: int = 1) -> ActionResult:
        """
        Wait/rest in place.

        Args:
            count: Number of turns to wait (default 1). Uses NetHack's count prefix
                   which auto-interrupts if a monster appears or attacks.

        Returns:
            ActionResult with messages from the wait period.
        """
        if not self._actions:
            return ActionResult.failure("Environment not initialized")
        result = self._actions.wait(count)
        self._record_messages(result.messages)
        return result

    def search(self, count: int = 1) -> ActionResult:
        """
        Search adjacent tiles for secret doors and traps.

        Args:
            count: Number of times to search (default 1). Use count=20 to thoroughly
                   search an area. NetHack auto-interrupts if a monster appears.

        Returns:
            ActionResult with messages (e.g., "You find a hidden door!")
        """
        if not self._actions:
            return ActionResult.failure("Environment not initialized")
        result = self._actions.search(count)
        self._record_messages(result.messages)
        return result

    def pickup(self, item_letter: Optional[str] = None) -> ActionResult:
        """
        Pick up items from the ground.

        With no arguments, picks up all items on the tile.
        With a letter, picks up just that item from a multi-item pile.

        Args:
            item_letter: Pick up a specific item by its menu letter (a, b, c...).
                        If omitted, picks up everything.

        Returns:
            ActionResult
        """
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

    def pay(self) -> ActionResult:
        """Pay a shopkeeper for items you've picked up."""
        if not self._actions:
            return ActionResult.failure("Environment not initialized")
        result = self._actions.pay()
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
        pass_through_doors: bool = False,
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
            allow_with_hostiles, cardinal_only=cardinal_only, level_memory=level_memory,
            pass_through_doors=pass_through_doors
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

    def autoexplore(self, max_steps: int = 500, ignore_monsters: bool = False) -> AutoexploreResult:
        """
        Explore automatically until interrupted (NetHack4-style).

        Runs exploration as a loop, moving toward unexplored areas and
        stopping only for critical conditions:
        - No unexplored areas reachable (fully_explored)
        - Nearby hostile chasing monster (within 5 tiles) (hostile) [unless ignore_monsters]
        - HP drops below 30% (low_hp)
        - Hungry or weaker (hungry)
        - Attacked / HP decreased (attacked) [only when ignore_monsters]
        - max_steps reached (max_steps)
        - Blind, confused, or stunned (blocked)
        - In Sokoban (sokoban)

        Does NOT stop for: items, stairs, altars, fountains, distant hostiles.
        The agent can check for these after exploration completes.

        Args:
            max_steps: Maximum exploration steps before stopping.
            ignore_monsters: If True, ignore nearby hostiles and only stop
                if actually attacked (HP decreases) or hunger state changes.

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
        initial_hunger = self.get_stats().hunger
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
            hp_before = stats.hp  # Track for attacked detection
            if stats.hp / max(stats.max_hp, 1) < 0.3:
                steps_msg = f" after {steps_taken} steps" if steps_taken > 0 else ""
                return AutoexploreResult(
                    stop_reason="low_hp",
                    steps_taken=steps_taken,
                    turns_elapsed=self.turn - turns_start,
                    position=self.position,
                    message=f"HP low: {stats.hp}/{stats.max_hp}{steps_msg}",
                )

            # Stop when hunger state worsens during exploration
            if stats.hunger != initial_hunger and stats.is_hungry:
                steps_msg = f" after {steps_taken} steps" if steps_taken > 0 else ""
                hunger_msg = "Weak - need food urgently" if stats.is_weak else "Hungry - need food"
                return AutoexploreResult(
                    stop_reason="hungry",
                    steps_taken=steps_taken,
                    turns_elapsed=self.turn - turns_start,
                    position=self.position,
                    message=f"{hunger_msg}{steps_msg}",
                )

            # Check for NEARBY hostile monsters that will chase (not sessile monsters like molds)
            # Only stop if hostile is within 5 tiles - distant hostiles don't interrupt exploration
            current_pos = self.position
            if not ignore_monsters:
                hostiles = self.get_hostile_monsters()
                nearby_chasing = [
                    m for m in hostiles
                    if m.is_chasing and current_pos.chebyshev_distance(m.position) <= 5
                ]
                if nearby_chasing:
                    steps_msg = f" after {steps_taken} steps" if steps_taken > 0 else ""
                    return AutoexploreResult(
                        stop_reason="hostile",
                        steps_taken=steps_taken,
                        turns_elapsed=self.turn - turns_start,
                        position=self.position,
                        message=f"Hostile nearby: {nearby_chasing[0].name}{steps_msg}",
                    )
                # Note: sessile monsters (molds, fungi) and distant hostiles don't interrupt

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
                target_result = self.find_unexplored(
                    allow_with_hostiles=ignore_monsters,
                    excluded_positions=excluded,
                )

                # If no targets found but we have recently abandoned ones, DON'T clear and retry.
                # This would cause an infinite loop if all targets are truly unreachable (e.g., blocked by boulder).
                # Instead, return "blocked" - the agent needs to handle this situation manually.
                if not target_result and recently_abandoned:
                    logger.debug(f"autoexplore: all {len(recently_abandoned)} targets abandoned and unreachable")
                    return AutoexploreResult(
                        stop_reason="blocked",
                        steps_taken=steps_taken,
                        turns_elapsed=self.turn - turns_start,
                        position=self.position,
                        message=f"All exploration targets unreachable (blocked by obstacles). Abandoned targets: {recently_abandoned}",
                    )
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
                        is_blocked, blocking_msg = self._get_blocking_info()
                        if is_blocked:
                            # There ARE visible areas we can't reach
                            # Could be: closed door we can't path to, or disconnected area
                            return AutoexploreResult(
                                stop_reason="blocked",
                                steps_taken=steps_taken,
                                turns_elapsed=self.turn - turns_start,
                                position=self.position,
                                message=blocking_msg,
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
                    is_blocked, blocking_msg = self._get_blocking_info()
                    if is_blocked:
                        return AutoexploreResult(
                            stop_reason="blocked",
                            steps_taken=steps_taken,
                            turns_elapsed=self.turn - turns_start,
                            position=self.position,
                            message=blocking_msg,
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
                # Path failed - this could be because:
                # 1. Target was cached from previous iteration and map changed
                # 2. Monster blocking path
                # 3. Door closed
                # Instead of blindly retrying, immediately invalidate the cached target
                # so next iteration will find a fresh target with current observation.
                logger.debug(f"autoexplore: path to {target} failed, invalidating cached target")
                current_target = None  # Force find_unexplored on next iteration
                failed_attempts += 1
                target_attempts += 1

                # Try opening a door as a recovery action
                door_opened = self._try_open_nearest_closed_door()
                if door_opened:
                    steps_taken += 1
                    failed_attempts = 0
                    continue

                if failed_attempts >= max_failed_attempts:
                    steps_msg = f" after {steps_taken} steps" if steps_taken > 0 else ""
                    _, blocking_msg = self._get_blocking_info()
                    if blocking_msg:
                        return AutoexploreResult(
                            stop_reason="blocked",
                            steps_taken=steps_taken,
                            turns_elapsed=self.turn - turns_start,
                            position=self.position,
                            message=blocking_msg,
                        )
                    return AutoexploreResult(
                        stop_reason="blocked",
                        steps_taken=steps_taken,
                        turns_elapsed=self.turn - turns_start,
                        position=self.position,
                        message=f"Too many pathfinding failures{steps_msg}. Try searching for secret doors or moving manually.",
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

                # Note: We no longer stop for engravings/graffiti - they're just flavor text
                # and stopping causes loops when the agent walks back through the same tile.

                # When ignoring monsters, detect if we were attacked (HP decreased)
                if ignore_monsters:
                    current_hp = self.get_stats().hp
                    if current_hp < hp_before:
                        return AutoexploreResult(
                            stop_reason="attacked",
                            steps_taken=steps_taken,
                            turns_elapsed=self.turn - turns_start,
                            position=self.position,
                            message=f"Took damage: HP {hp_before} -> {current_hp}",
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
                        _, blocking_msg = self._get_blocking_info()
                        if blocking_msg:
                            return AutoexploreResult(
                                stop_reason="blocked",
                                steps_taken=steps_taken,
                                turns_elapsed=self.turn - turns_start,
                                position=self.position,
                                message=blocking_msg,
                            )
                        return AutoexploreResult(
                            stop_reason="blocked",
                            steps_taken=steps_taken,
                            turns_elapsed=self.turn - turns_start,
                            position=self.position,
                            message=f"Too many movement failures{steps_msg}. Try searching for secret doors or moving manually.",
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

    def travel_to(self, char: str) -> ActionResult:
        """
        Travel to the nearest tile with the given character (NetHack-style travel).

        This is the equivalent of NetHack's `_` travel command with a symbol shortcut.
        For example, `travel_to('>')` is like pressing `_>.` in NetHack.

        Common characters:
        - '>' - stairs down
        - '<' - stairs up
        - '{' - fountain
        - '_' - altar (use the string, not the method name)
        - '#' - sink
        - '$' - gold
        - '%' - food
        - ')' - weapon
        - '[' - armor

        Args:
            char: Single character to search for on the map

        Returns:
            ActionResult with success/failure. If successful, player is now
            at (or adjacent to, if unwalkable) the target tile.
        """
        if not self.observation:
            return ActionResult.failure("No observation available")

        if len(char) != 1:
            return ActionResult.failure(f"Expected single character, got '{char}'")

        # Scan the map for matching tiles
        level = self.get_current_level()
        player_pos = self.position
        candidates: list[tuple[Position, int]] = []  # (position, distance)

        for y in range(21):
            for x in range(79):
                pos = Position(x, y)
                tile = level.get_tile(pos)
                if tile and tile.char == char:
                    # Use Chebyshev distance for initial sorting
                    dist = player_pos.chebyshev_distance(pos)
                    candidates.append((pos, dist))

        if not candidates:
            return ActionResult.failure(f"No '{char}' found on this level")

        # Sort by distance to find nearest
        candidates.sort(key=lambda x: x[1])

        # Try candidates in order (nearest first) until we find one we can reach
        last_failure_reason = ""
        for target_pos, dist in candidates:
            if target_pos == player_pos:
                # Already there
                return ActionResult(success=True, messages=[f"Already at '{char}'"], turn_elapsed=False)

            # Use move_to with pass_through_doors=True (like NetHack's travel command)
            logger.debug(f"travel_to: trying candidate '{char}' at {target_pos} (dist={dist})")
            result = self.move_to(target_pos, pass_through_doors=True)
            if result.success:
                return result
            # Log why this candidate failed
            last_failure_reason = result.messages[0] if result.messages else "unknown"
            logger.debug(f"travel_to: candidate {target_pos} failed: {last_failure_reason}")

        # None of the candidates were reachable
        return ActionResult.failure(f"Found '{char}' but cannot reach it: {last_failure_reason}")

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

    # ==================== Prayer Tracking ====================

    @property
    def turns_since_last_prayer(self) -> int:
        """Turns elapsed since last prayer. Use to check prayer timeout (~500 turns needed)."""
        return self.turn - self._last_prayer_turn

    # ==================== Reminders and Notes ====================

    def add_reminder(self, turns: int, message: str) -> None:
        """
        Add a reminder that fires after N turns.

        The reminder will appear once in the agent context when the specified
        number of turns have passed, then be automatically removed.

        Example: After picking up a corpse, remind in 50 turns that it may be rotten.

        Args:
            turns: Number of turns until the reminder fires
            message: The reminder message
        """
        fire_turn = self.turn + turns
        self._reminders.append((fire_turn, message))

    def add_note(self, turns: int, message: str) -> int:
        """
        Add a note that persists for N turns, or permanently if turns=0.

        The note will appear in the agent context every turn until the specified
        number of turns have elapsed (or until manually removed if turns=0).

        Examples:
            nh.add_note(10, "Wand may be running low")  # Expires in 10 turns
            note_id = nh.add_note(0, "Have wand of death")  # Persistent until removed

        Args:
            turns: Number of turns the note should persist (0 = permanent)
            message: The note message

        Returns:
            The note ID (use with remove_note() to remove persistent notes)
        """
        note_id = self._next_note_id
        self._next_note_id += 1
        expire_turn = 0 if turns == 0 else self.turn + turns
        self._notes[note_id] = (expire_turn, message)
        return note_id

    def remove_note(self, note_id: int) -> bool:
        """
        Remove a note by its ID.

        Useful for removing persistent notes (turns=0) when they're no longer relevant.

        Args:
            note_id: The ID returned by add_note()

        Returns:
            True if the note was removed, False if it didn't exist
        """
        if note_id in self._notes:
            del self._notes[note_id]
            return True
        return False

    def get_fired_reminders(self) -> list[str]:
        """
        Get reminders that have fired (current turn >= fire turn).

        Fired reminders are removed from the list after being returned.

        Returns:
            List of reminder messages that have fired
        """
        current = self.turn
        fired = [msg for fire_turn, msg in self._reminders if current >= fire_turn]
        self._reminders = [(t, m) for t, m in self._reminders if current < t]
        return fired

    def get_active_notes(self) -> list[tuple[int, str]]:
        """
        Get notes that are still active (not expired).

        Expired notes (expire_turn > 0 and current turn >= expire_turn) are removed.
        Persistent notes (expire_turn = 0) are never automatically removed.

        Returns:
            List of (note_id, message) tuples for active notes
        """
        current = self.turn
        # Remove expired notes (but not persistent ones where expire_turn=0)
        expired_ids = [
            nid for nid, (expire_turn, _) in self._notes.items()
            if expire_turn > 0 and current >= expire_turn
        ]
        for nid in expired_ids:
            del self._notes[nid]
        # Return active notes as (id, message) tuples
        return [(nid, msg) for nid, (_, msg) in sorted(self._notes.items())]
