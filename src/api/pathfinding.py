"""
Pathfinding for NetHack.

Implements A* pathfinding over the dungeon map, respecting walkability
and avoiding known dangers.

Follows NetHack4 conventions:
- Pathfinding refuses to run when hostile monsters are visible
- Returns PathResult with reason for success/failure
"""

import heapq
import logging
from dataclasses import dataclass
from enum import Enum
from typing import Callable, Optional, TYPE_CHECKING

from nle import nethack

if TYPE_CHECKING:
    from src.memory.dungeon import LevelMemory

logger = logging.getLogger(__name__)

from .environment import Observation
from .glyphs import is_walkable_glyph, is_dangerous_terrain_glyph, is_boulder_glyph, is_closed_door_glyph
from .models import Direction, DungeonLevel, Position, Tile
from .queries import (
    get_current_level,
    get_position,
    get_hostile_monsters,
    can_fly,
    is_near_shopkeeper,
    is_grid_bug_form,
)


class PathStopReason(Enum):
    """Reasons why pathfinding stopped or couldn't start."""
    SUCCESS = "success"
    ALREADY_AT_TARGET = "already_at_target"
    HOSTILE_IN_VIEW = "hostile_in_view"
    TARGET_UNWALKABLE = "target_unwalkable"
    TARGET_OUT_OF_BOUNDS = "target_out_of_bounds"
    NO_PATH_EXISTS = "no_path_exists"
    NO_TARGET_FOUND = "no_target_found"
    NO_OBSERVATION = "no_observation"


@dataclass
class PathResult:
    """Result of a pathfinding operation."""
    path: list[Direction]
    reason: PathStopReason
    message: str = ""

    @property
    def success(self) -> bool:
        """Whether pathfinding succeeded."""
        return self.reason == PathStopReason.SUCCESS

    def __bool__(self) -> bool:
        """Allow `if result:` to check for success."""
        return self.success and len(self.path) > 0

    def __iter__(self):
        """Allow `for direction in result:` to iterate path."""
        return iter(self.path)

    def __len__(self) -> int:
        """Return path length."""
        return len(self.path)

    def __repr__(self) -> str:
        if self.success:
            return f"PathResult(path=[{len(self.path)} steps], reason=SUCCESS)"
        return f"PathResult(path=[], reason={self.reason.value}, message='{self.message}')"


@dataclass
class TargetResult:
    """Result of a target-finding operation (find_unexplored, find_stairs, etc.)."""
    position: Optional[Position]
    reason: PathStopReason
    message: str = ""

    @property
    def success(self) -> bool:
        """Whether a target was found."""
        return self.position is not None

    def __bool__(self) -> bool:
        """Allow `if result:` to check for success."""
        return self.success

    def __repr__(self) -> str:
        if self.success:
            return f"TargetResult(position={self.position}, reason=SUCCESS)"
        return f"TargetResult(position=None, reason={self.reason.value}, message='{self.message}')"


# =============================================================================
# Movement Helper Functions
# =============================================================================
# These helpers consolidate movement logic used by BFS, A*, and autoexplore.
# Single source of truth for diagonal checks, doorway restrictions, etc.


def _is_diagonal_move(from_pos: Position, to_pos: Position) -> bool:
    """Check if movement between two adjacent positions is diagonal."""
    dx = abs(to_pos.x - from_pos.x)
    dy = abs(to_pos.y - from_pos.y)
    return dx + dy == 2


def _can_move_to_neighbor(
    from_pos: Position,
    to_pos: Position,
    doorways: list[list[bool]],
    cardinal_only: bool = False,
) -> bool:
    """
    Check if movement from one position to an adjacent position is allowed.

    Combines all movement restriction checks:
    - Grid bug form (cardinal only)
    - Doorway diagonal restriction

    Args:
        from_pos: Current position
        to_pos: Target adjacent position
        doorways: 2D grid of doorway tiles
        cardinal_only: If True, only cardinal moves allowed (grid bug form)

    Returns:
        True if the move is allowed by movement rules
    """
    is_diagonal = _is_diagonal_move(from_pos, to_pos)

    # Grid bug form: can only move in cardinal directions
    if cardinal_only and is_diagonal:
        return False

    # NetHack rule: Cannot move diagonally into or out of a doorway
    if is_diagonal:
        if doorways[from_pos.y][from_pos.x] or doorways[to_pos.y][to_pos.x]:
            return False

    return True


def _check_hostiles(
    obs: Observation,
    allow_with_hostiles: bool = False,
) -> tuple[bool, str]:
    """
    Check for hostile monsters in view.

    Args:
        obs: Current observation
        allow_with_hostiles: If True, skip the check

    Returns:
        Tuple of (has_hostiles, message). If has_hostiles is True,
        the operation should be blocked and message explains why.
    """
    if allow_with_hostiles:
        return (False, "")

    hostiles = get_hostile_monsters(obs)
    if hostiles:
        names = [m.name for m in hostiles[:3]]
        msg = f"Hostile monsters in view: {', '.join(names)}"
        if len(hostiles) > 3:
            msg += f" (+{len(hostiles) - 3} more)"
        return (True, msg)

    return (False, "")


def _is_walked_past(
    x: int,
    y: int,
    stepped_memory: Optional["LevelMemory"],
) -> bool:
    """
    Check if an unexplored tile has been "walked past".

    A tile is walked past if any of its 8 neighbors have been stepped on.
    This is used to avoid re-exploring areas the player has already passed.

    Args:
        x, y: Coordinates of the unexplored tile
        stepped_memory: Level memory with stepped tracking

    Returns:
        True if any adjacent tile has been stepped on
    """
    if not stepped_memory:
        return False

    for dx in [-1, 0, 1]:
        for dy in [-1, 0, 1]:
            if dx == 0 and dy == 0:
                continue
            if stepped_memory.is_stepped(x + dx, y + dy):
                return True

    return False


def find_path(
    obs: Observation,
    target: Position,
    avoid_monsters: bool = True,
    avoid_traps: bool = True,
    allow_with_hostiles: bool = False,
    player_can_fly: Optional[bool] = None,
    cardinal_only: Optional[bool] = None,
    level_memory: Optional["LevelMemory"] = None,
) -> PathResult:
    """
    Find a path from current position to target using A*.

    Following NetHack4 conventions, pathfinding refuses to run when hostile
    monsters are visible (unless allow_with_hostiles=True).

    Args:
        obs: Current observation
        target: Target position
        avoid_monsters: Whether to avoid tiles with monsters
        avoid_traps: Whether to avoid known traps
        allow_with_hostiles: Override hostile check (use with caution)
        player_can_fly: If None, auto-detect from observation. If False, avoid water/lava.
        cardinal_only: If None, auto-detect grid bug form. If True, only cardinal moves.
        level_memory: Optional level memory for remembering doorway positions.

    Returns:
        PathResult with path (list of directions) and reason for success/failure
    """
    # Check for hostile monsters first (NetHack4 convention)
    has_hostiles, hostile_msg = _check_hostiles(obs, allow_with_hostiles)
    if has_hostiles:
        return PathResult([], PathStopReason.HOSTILE_IN_VIEW, hostile_msg)

    start = get_position(obs)

    if start == target:
        return PathResult([], PathStopReason.ALREADY_AT_TARGET, "Already at target position")

    # Check bounds
    if not _is_valid_position(target):
        return PathResult([], PathStopReason.TARGET_OUT_OF_BOUNDS, f"Target {target} is out of map bounds")

    # Auto-detect player flight status if not specified
    if player_can_fly is None:
        player_can_fly = can_fly(obs)

    # Auto-detect grid bug form if not specified
    if cardinal_only is None:
        cardinal_only = is_grid_bug_form(obs)

    # Build walkability and doorway grids from observation
    walkable, doorways = _build_walkability_grid(obs, avoid_monsters, avoid_traps, player_can_fly, level_memory)

    # Check if target is walkable
    if not walkable[target.y][target.x]:
        # Provide specific feedback for closed doors
        target_glyph = int(obs.glyphs[target.y, target.x])
        if is_closed_door_glyph(target_glyph):
            logger.debug(f"find_path: target {target} is a closed door (glyph={target_glyph})")
            return PathResult(
                [],
                PathStopReason.TARGET_UNWALKABLE,
                f"Target {target} is a closed door. Move to an adjacent tile and use open_door() first."
            )
        logger.debug(f"find_path: target {target} is unwalkable (glyph={target_glyph})")
        return PathResult([], PathStopReason.TARGET_UNWALKABLE, f"Target {target} is not walkable (wall, monster, etc.)")

    # A* search (doorways grid prevents diagonal movement through doors)
    path = _astar(start, target, walkable, doorways, cardinal_only)

    if not path:
        # Debug: sample walkable tiles to understand why A* failed
        walkable_around_start = []
        walkable_around_target = []
        for dx in [-1, 0, 1]:
            for dy in [-1, 0, 1]:
                sx, sy = start.x + dx, start.y + dy
                tx, ty = target.x + dx, target.y + dy
                if 0 <= sx < 79 and 0 <= sy < 21 and walkable[sy][sx]:
                    walkable_around_start.append((sx, sy))
                if 0 <= tx < 79 and 0 <= ty < 21 and walkable[ty][tx]:
                    walkable_around_target.append((tx, ty))
        logger.debug(f"find_path: A* found no path from {start} to {target}, doorway_at_target={doorways[target.y][target.x]}")
        logger.debug(f"find_path: walkable around start {start}: {walkable_around_start[:5]}")
        logger.debug(f"find_path: walkable around target {target}: {walkable_around_target[:5]}")
        return PathResult([], PathStopReason.NO_PATH_EXISTS, f"No path through explored territory from {start} to {target}. Try exploring corridors between these areas first.")

    # Convert path of positions to directions
    directions = []
    current = start
    for next_pos in path:
        direction = current.direction_to(next_pos)
        if direction and direction != Direction.SELF:
            directions.append(direction)
        current = next_pos

    return PathResult(directions, PathStopReason.SUCCESS)


def find_nearest(
    obs: Observation,
    predicate: Callable[[Tile], bool],
    max_distance: int = 100,
) -> Optional[Position]:
    """
    Find the nearest tile matching a predicate.

    Uses unified BFS with proper movement restrictions (doorway diagonal,
    grid bug form, water/lava avoidance).

    Args:
        obs: Current observation
        predicate: Function that returns True for matching tiles
        max_distance: Maximum search distance

    Returns:
        Position of nearest matching tile, or None if not found
    """
    start = get_position(obs)
    level = get_current_level(obs)

    # Build walkability and doorway grids (avoid monsters=False for finding features)
    player_can_fly_status = can_fly(obs)
    walkable, doorways = _build_walkability_grid(
        obs, avoid_monsters=False, avoid_traps=True,
        player_can_fly=player_can_fly_status
    )
    cardinal_only = is_grid_bug_form(obs)

    # Use unified BFS to find nearest matching tile
    for dist, pos in _bfs_reachable(start, walkable, doorways, cardinal_only, max_distance):
        tile = level.get_tile(pos)
        if tile and predicate(tile):
            return pos

    return None


def _is_tile_unexplored(
    x: int,
    y: int,
    obs_level: DungeonLevel,
    stepped_memory: Optional["LevelMemory"],
    obs: Optional["Observation"] = None,
) -> bool:
    """
    Check if a tile is worth exploring (NetHack4's unexplored() algorithm).

    A tile is interesting if:
    1. It hasn't been stepped on
    2. It's not blocked (locked door, trap, boulder, shop item)
    3. It doesn't have a remembered invisible monster
    4. It has items or features (altar, stairs, etc.), OR
    5. It's adjacent to unexplored stone that isn't adjacent to any stepped tile

    Args:
        x, y: Tile coordinates
        obs_level: Current dungeon level from observation
        stepped_memory: Level memory with stepped tracking (optional)
        obs: Full observation for shop detection (optional)

    Returns:
        True if tile is worth exploring
    """
    pos = Position(x, y)
    obs_tile = obs_level.get_tile(pos)

    if not obs_tile:
        return False

    # Already stepped on - not interesting
    if stepped_memory and stepped_memory.is_stepped(x, y):
        return False

    # Check for remembered invisible monster - don't repeatedly search
    if stepped_memory and stepped_memory.has_invis_at(x, y):
        return False

    # Reject obstacles
    if obs_tile.char == '+' and obs_tile.description and "locked" in obs_tile.description.lower():
        return False  # Locked door

    # Trap check with vibrating square exception
    if obs_tile.has_trap:
        trap_name = (obs_tile.trap_type or "").lower()
        if "vibrating" not in trap_name:
            return False  # Known trap (but vibrating square is OK)

    # Never target boulder squares (use glyph-based detection)
    if is_boulder_glyph(obs_tile.glyph):
        return False

    # Never target shop items to prevent accidental theft
    if obs is not None:
        from .glyphs import is_item_glyph
        if is_near_shopkeeper(x, y, obs) and is_item_glyph(obs_tile.glyph):
            return False

    # Accept special features
    if obs_tile.feature in ('altar', 'throne', 'sink', 'fountain', 'stairs'):
        return True
    if obs_tile.is_stairs_up or obs_tile.is_stairs_down:
        return True

    # Check frontier: adjacent to unexplored stone that isn't adjacent to stepped
    is_corridor = obs_tile.is_corridor if hasattr(obs_tile, 'is_corridor') else obs_tile.char == '#'

    for dx in [-1, 0, 1]:
        for dy in [-1, 0, 1]:
            if dx == 0 and dy == 0:
                continue

            # Skip diagonals for corridors (NetHack4 convention)
            if is_corridor and dx != 0 and dy != 0:
                continue

            nx, ny = x + dx, y + dy
            if not _is_valid_position(Position(nx, ny)):
                continue

            neighbor = obs_level.get_tile(Position(nx, ny))
            if not neighbor:
                continue

            # Check if neighbor is unexplored and hasn't been walked past
            if not neighbor.is_explored and not _is_walked_past(nx, ny, stepped_memory):
                return True  # Genuine frontier

    return False


def _autotravel_weighting(x: int, y: int, distance: int, obs_tile: Tile) -> int:
    """
    Calculate exploration priority weight (lower = higher priority).

    Based on NetHack4's autotravel_weighting():
    - Items and features: raw distance (highest priority)
    - Room tiles: distance * 2
    - Corridor tiles: distance * 10 (explore last)

    Args:
        x, y: Tile coordinates
        distance: BFS distance from player
        obs_tile: Tile at this position

    Returns:
        Weight value (lower = explore first)
    """
    # Features - high priority
    if obs_tile.feature in ('altar', 'throne', 'sink', 'fountain', 'stairs'):
        return distance
    if obs_tile.is_stairs_up or obs_tile.is_stairs_down:
        return distance

    # Room tiles - medium priority (floor)
    is_corridor = obs_tile.is_corridor if hasattr(obs_tile, 'is_corridor') else obs_tile.char == '#'
    if not is_corridor and obs_tile.char == '.':
        return distance * 2

    # Corridors - low priority (explore last)
    return distance * 10


def _is_at_frontier(
    start: Position,
    level: DungeonLevel,
    stepped_memory: Optional["LevelMemory"],
    cardinal_only: bool,
    doorway_grid: list[list[bool]],
) -> bool:
    """
    Check if the starting position is at a frontier (adjacent to unexplored).

    A position is at a frontier if it's adjacent to unexplored tiles that
    haven't been "walked past" (i.e., no stepped tiles are adjacent to the
    unexplored tile).

    Args:
        start: Starting position
        level: Current dungeon level
        stepped_memory: Level memory with stepped tracking
        cardinal_only: If True, only consider cardinal neighbors
        doorway_grid: Grid of doorway positions (for diagonal restriction)

    Returns:
        True if at a valid frontier
    """
    start_tile = level.get_tile(start)
    if not start_tile:
        return False

    for neighbor in start.adjacent():
        if not _is_valid_position(neighbor):
            continue

        # Check movement restrictions (diagonal doorway, grid bug)
        if not _can_move_to_neighbor(start, neighbor, doorway_grid, cardinal_only):
            continue

        neighbor_tile = level.get_tile(neighbor)
        if neighbor_tile and not neighbor_tile.is_explored:
            # Check if this unexplored isn't walked past
            if not _is_walked_past(neighbor.x, neighbor.y, stepped_memory):
                return True

    return False


def find_unexplored(
    obs: Observation,
    stepped_memory: Optional["LevelMemory"] = None,
    max_distance: int = 100,
    allow_with_hostiles: bool = False,
    excluded_positions: Optional[set[Position]] = None,
) -> TargetResult:
    """
    Find the best unexplored tile using NetHack4's algorithm.

    Following NetHack4 conventions:
    - Refuses to search when hostiles visible
    - Uses stepped tracking to avoid revisiting tiles
    - Weights destinations: items > features > rooms > corridors
    - Smart frontier detection prevents exploring "walked past" areas

    Args:
        obs: Current observation
        stepped_memory: Level memory with stepped tracking (optional but recommended)
        max_distance: Maximum search distance
        allow_with_hostiles: Override hostile check
        excluded_positions: Set of positions to exclude (e.g., previously abandoned targets)

    Returns:
        TargetResult with position and reason
    """
    # Check for hostile monsters first
    has_hostiles, hostile_msg = _check_hostiles(obs, allow_with_hostiles)
    if has_hostiles:
        return TargetResult(None, PathStopReason.HOSTILE_IN_VIEW, hostile_msg)

    start = get_position(obs)
    level = get_current_level(obs)

    # Build walkability grid with same logic as find_path (includes water/lava avoidance)
    player_can_fly_status = can_fly(obs)
    walkable_grid, doorway_grid = _build_walkability_grid(obs, avoid_monsters=True, avoid_traps=True, player_can_fly=player_can_fly_status, level_memory=stepped_memory)

    # Check if player is in grid bug form (cardinal only movement)
    cardinal_only = is_grid_bug_form(obs)

    # Track if starting position is a valid exploration target (adjacent to unexplored)
    start_is_frontier = _is_at_frontier(start, level, stepped_memory, cardinal_only, doorway_grid)

    # Use unified BFS to find all unexplored candidates (explored_only=True)
    candidates: list[tuple[int, int, Position]] = []
    excluded = excluded_positions or set()
    for dist, pos in _bfs_reachable(
        start, walkable_grid, doorway_grid, cardinal_only, max_distance,
        explored_only=True, level=level
    ):
        # Skip start position - we check it separately
        if pos == start:
            continue

        # Skip explicitly excluded positions (abandoned targets)
        if pos in excluded:
            continue

        tile = level.get_tile(pos)
        if tile and _is_tile_unexplored(pos.x, pos.y, level, stepped_memory, obs):
            weight = _autotravel_weighting(pos.x, pos.y, dist, tile)
            candidates.append((weight, dist, pos))

    # Pick best candidate by weight
    if candidates:
        candidates.sort(key=lambda c: (c[0], c[1]))  # Sort by weight, then distance
        best_weight, best_dist, best_pos = candidates[0]
        # Debug: verify target is walkable and count reachable tiles
        target_walkable = walkable_grid[best_pos.y][best_pos.x]
        total_walkable = sum(1 for y in range(21) for x in range(79) if walkable_grid[y][x])
        reachable_count = sum(1 for _ in _bfs_reachable(start, walkable_grid, doorway_grid, cardinal_only, max_distance))
        logger.debug(f"find_unexplored: from {start}, selected target {best_pos} (weight={best_weight}, dist={best_dist}) from {len(candidates)} candidates")
        logger.debug(f"find_unexplored: target_walkable={target_walkable}, total_walkable={total_walkable}, reachable={reachable_count}")
        return TargetResult(best_pos, PathStopReason.SUCCESS)

    # If no candidates but start position is at frontier, return it
    if start_is_frontier:
        logger.debug(f"find_unexplored: at frontier position {start}")
        return TargetResult(start, PathStopReason.ALREADY_AT_TARGET,
                          "Already at position bordering unexplored - move into unexplored direction")

    logger.debug(f"find_unexplored: no unexplored areas reachable from {start}")
    return TargetResult(None, PathStopReason.NO_TARGET_FOUND, "No unexplored areas reachable")


def find_stairs_up(obs: Observation, allow_with_hostiles: bool = False) -> TargetResult:
    """Find position of stairs up (<)."""
    has_hostiles, hostile_msg = _check_hostiles(obs, allow_with_hostiles)
    if has_hostiles:
        return TargetResult(None, PathStopReason.HOSTILE_IN_VIEW, hostile_msg)

    result = find_nearest(obs, lambda t: t.is_stairs_up)
    if result:
        return TargetResult(result, PathStopReason.SUCCESS)
    return TargetResult(None, PathStopReason.NO_TARGET_FOUND, "No stairs up found on this level")


def find_stairs_down(obs: Observation, allow_with_hostiles: bool = False) -> TargetResult:
    """Find position of stairs down (>)."""
    has_hostiles, hostile_msg = _check_hostiles(obs, allow_with_hostiles)
    if has_hostiles:
        return TargetResult(None, PathStopReason.HOSTILE_IN_VIEW, hostile_msg)

    result = find_nearest(obs, lambda t: t.is_stairs_down)
    if result:
        return TargetResult(result, PathStopReason.SUCCESS)
    return TargetResult(None, PathStopReason.NO_TARGET_FOUND, "No stairs down found on this level")


def find_nearest_monster(obs: Observation) -> Optional[Position]:
    """Find position of nearest hostile monster."""
    from .queries import get_hostile_monsters

    monsters = get_hostile_monsters(obs)
    if not monsters:
        return None

    player_pos = get_position(obs)
    monsters.sort(key=lambda m: player_pos.chebyshev_distance(m.position))
    return monsters[0].position if monsters else None


def path_distance(obs: Observation, target: Position) -> int:
    """
    Calculate path distance to target (or -1 if unreachable).

    Note: This ignores hostile monster checks to provide distance info.

    Args:
        obs: Current observation
        target: Target position

    Returns:
        Number of steps in path, or -1 if unreachable
    """
    start = get_position(obs)

    # Already at target - distance is 0
    if start == target:
        return 0

    # Allow with hostiles since this is just for distance calculation
    result = find_path(obs, target, allow_with_hostiles=True)
    return len(result.path) if result.success else -1


def is_doorway_glyph(glyph: int) -> bool:
    """
    Check if glyph is a doorway that restricts diagonal movement.

    In NetHack, you cannot move diagonally into or out of a doorway
    that has a door (closed or open). Broken doors and doorless
    doorways allow diagonal movement.

    Glyph values (from CMAP):
      15 = closed door (no diagonal)
      16 = open door (no diagonal)
      17 = broken door (diagonal OK)

    This function is used by both pathfinding and autoexplore to determine
    whether diagonal movement is allowed from/to a position.
    """
    try:
        from nle import nethack
        # Use NLE's glyph functions
        if not nethack.glyph_is_cmap(glyph):
            return False
        cmap_idx = nethack.glyph_to_cmap(glyph)
    except ImportError:
        # Fallback for testing without NLE
        # GLYPH_CMAP_OFF is typically 2359 in NLE
        cmap_offset = 2359
        if glyph < cmap_offset or glyph >= cmap_offset + 100:
            return False
        cmap_idx = glyph - cmap_offset

    # 15 = closed door, 16 = open door (both block diagonal movement)
    # 17 = broken door (allows diagonal movement)
    return cmap_idx in (15, 16)


def _build_walkability_grid(
    obs: Observation,
    avoid_monsters: bool = True,
    avoid_traps: bool = True,
    player_can_fly: bool = False,
    level_memory: Optional["LevelMemory"] = None,
) -> tuple[list[list[bool]], list[list[bool]]]:
    """
    Build 2D grids for pathfinding.

    Args:
        obs: Current observation
        avoid_monsters: Mark monster tiles as unwalkable
        avoid_traps: (Currently unused, traps are walkable)
        player_can_fly: If False, water/lava tiles are unwalkable
        level_memory: Optional level memory to track/recall doorway positions

    Returns:
        Tuple of (walkable_grid, doorway_grid)
        - walkable_grid: True if tile can be walked on
        - doorway_grid: True if tile is a doorway (blocks diagonal movement)
    """
    walkable_grid = []
    doorway_grid = []

    for y in range(21):
        walkable_row = []
        doorway_row = []
        for x in range(79):
            glyph = int(obs.glyphs[y, x])
            walkable = is_walkable_glyph(glyph)

            # If tile shows as "stone" (out of line of sight, cmap 0),
            # check level memory for tiles we've seen or walked on.
            # ONLY do this for stone - don't override visible obstacles like boulders!
            if not walkable and level_memory:
                # Check if this is "stone" (unexplored/out of sight) vs a visible obstacle
                is_stone = nethack.glyph_is_cmap(glyph) and nethack.glyph_to_cmap(glyph) == 0
                if is_stone:
                    # Trust tiles we've stepped on
                    if level_memory.is_stepped(x, y):
                        walkable = True
                        logger.debug(f"walkability: ({x}, {y}) marked walkable via is_stepped (glyph={glyph})")
                    # Trust tiles we've SEEN as walkable (even if not stepped on)
                    elif level_memory.is_seen_walkable(x, y):
                        walkable = True
                        logger.debug(f"walkability: ({x}, {y}) marked walkable via is_seen_walkable (glyph={glyph})")
                    # Also trust tiles marked walkable via update_tile (legacy)
                    elif level_memory.is_walkable(x, y):
                        walkable = True
                        logger.debug(f"walkability: ({x}, {y}) marked walkable via is_walkable (glyph={glyph})")

            # Check for monsters
            if avoid_monsters and walkable:
                from .glyphs import is_hostile_glyph

                if is_hostile_glyph(glyph):
                    walkable = False

            # Avoid water/lava when grounded (not flying/levitating)
            if walkable and not player_can_fly:
                if is_dangerous_terrain_glyph(glyph, can_fly=False):
                    walkable = False

            # Check for traps (we can still walk on them, but maybe avoid)
            # For now, allow walking on traps but could make this configurable

            # Check if current glyph is a doorway
            is_doorway = is_doorway_glyph(glyph)

            # Record doorways in level memory (so we remember them when player stands on them)
            if is_doorway and level_memory:
                level_memory.mark_doorway(x, y)

            # Also check level memory for remembered doorways (player glyph overwrites door glyph)
            if not is_doorway and level_memory and level_memory.is_doorway(x, y):
                is_doorway = True

            walkable_row.append(walkable)
            doorway_row.append(is_doorway)
        walkable_grid.append(walkable_row)
        doorway_grid.append(doorway_row)

    # Debug: log grid fingerprint to detect differences between calls
    walkable_count = sum(1 for row in walkable_grid for v in row if v)
    # Simple position-weighted hash to detect spatial differences
    grid_hash = sum(x * 100 + y for y, row in enumerate(walkable_grid) for x, v in enumerate(row) if v) % 1000000
    logger.debug(f"walkability_grid: count={walkable_count}, hash={grid_hash}")

    return walkable_grid, doorway_grid


def _is_valid_position(pos: Position) -> bool:
    """Check if position is within map bounds."""
    return 0 <= pos.x < 79 and 0 <= pos.y < 21


def _bfs_reachable(
    start: Position,
    walkable: list[list[bool]],
    doorways: list[list[bool]],
    cardinal_only: bool = False,
    max_distance: int = 100,
    explored_only: bool = False,
    level: Optional[DungeonLevel] = None,
):
    """
    Generator that yields reachable positions via BFS.

    This is the unified BFS implementation used by find_nearest() and find_unexplored().
    It respects all movement restrictions that A* uses.

    Args:
        start: Starting position
        walkable: 2D grid of walkable tiles
        doorways: 2D grid of doorway tiles (blocks diagonal movement)
        cardinal_only: If True, only allow cardinal (N/S/E/W) movement (grid bug form)
        max_distance: Maximum BFS distance
        explored_only: If True, only traverse through explored tiles (requires level)
        level: DungeonLevel for checking explored status (required if explored_only=True)

    Yields:
        Tuple of (distance, position) for each reachable position in BFS order
    """
    visited = {start}
    queue = [(0, start)]

    # Yield start position first
    yield (0, start)

    while queue:
        dist, pos = heapq.heappop(queue)

        if dist >= max_distance:
            continue

        for neighbor in pos.adjacent():
            if neighbor in visited:
                continue
            if not _is_valid_position(neighbor):
                continue
            if not walkable[neighbor.y][neighbor.x]:
                continue

            # Check movement restrictions (diagonal doorway, grid bug)
            if not _can_move_to_neighbor(pos, neighbor, doorways, cardinal_only):
                continue

            # If explored_only, skip unexplored tiles
            if explored_only and level:
                neighbor_tile = level.get_tile(neighbor)
                if not neighbor_tile or not neighbor_tile.is_explored:
                    continue

            visited.add(neighbor)
            heapq.heappush(queue, (dist + 1, neighbor))
            yield (dist + 1, neighbor)


def _astar(
    start: Position,
    goal: Position,
    walkable: list[list[bool]],
    doorways: list[list[bool]],
    cardinal_only: bool = False,
) -> list[Position]:
    """
    A* pathfinding algorithm.

    Args:
        start: Starting position
        goal: Target position
        walkable: 2D grid of walkable tiles
        doorways: 2D grid of doorway tiles (diagonal movement restricted)
        cardinal_only: If True, only allow cardinal (N/S/E/W) movement (grid bug form)

    Returns:
        List of positions from start to goal (excluding start), or empty if no path
    """
    if not _is_valid_position(goal) or not walkable[goal.y][goal.x]:
        return []

    # Priority queue: (f_score, counter, position)
    # Counter ensures stable sorting when f_scores are equal
    counter = 0
    open_set = [(0, counter, start)]
    came_from: dict[Position, Position] = {}
    g_score: dict[Position, float] = {start: 0}
    f_score: dict[Position, float] = {start: _heuristic(start, goal)}

    while open_set:
        _, _, current = heapq.heappop(open_set)

        if current == goal:
            # Reconstruct path
            path = []
            while current in came_from:
                path.append(current)
                current = came_from[current]
            path.reverse()
            return path

        for neighbor in current.adjacent():
            if not _is_valid_position(neighbor):
                continue
            if not walkable[neighbor.y][neighbor.x]:
                continue

            # Check movement restrictions (diagonal doorway, grid bug)
            if not _can_move_to_neighbor(current, neighbor, doorways, cardinal_only):
                continue

            # Diagonal movement costs sqrt(2) ≈ 1.4, orthogonal costs 1
            is_diagonal = _is_diagonal_move(current, neighbor)
            move_cost = 1.4 if is_diagonal else 1.0

            tentative_g = g_score[current] + move_cost

            if neighbor not in g_score or tentative_g < g_score[neighbor]:
                came_from[neighbor] = current
                g_score[neighbor] = tentative_g
                f_score[neighbor] = tentative_g + _heuristic(neighbor, goal)
                counter += 1
                heapq.heappush(open_set, (f_score[neighbor], counter, neighbor))

    return []  # No path found


def _heuristic(a: Position, b: Position) -> float:
    """
    Heuristic for A* (Chebyshev distance, accounting for diagonal movement).

    This is admissible because diagonal moves cost ~1.4 and this returns
    the minimum possible distance.
    """
    dx = abs(a.x - b.x)
    dy = abs(a.y - b.y)
    # Chebyshev distance with diagonal cost adjustment
    return max(dx, dy) + 0.4 * min(dx, dy)
