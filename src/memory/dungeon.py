"""
Dungeon memory for tracking explored areas.

Maintains a map of the dungeon, tracking explored tiles,
special features, and level-specific information.
"""

import json
import zlib
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional


class TileType(Enum):
    """Types of dungeon tiles."""

    UNKNOWN = "unknown"
    FLOOR = "floor"
    CORRIDOR = "corridor"
    WALL = "wall"
    DOOR_OPEN = "door_open"
    DOOR_CLOSED = "door_closed"
    STAIRS_UP = "stairs_up"
    STAIRS_DOWN = "stairs_down"
    ALTAR = "altar"
    FOUNTAIN = "fountain"
    SINK = "sink"
    THRONE = "throne"
    GRAVE = "grave"
    TRAP = "trap"
    WATER = "water"
    LAVA = "lava"
    ICE = "ice"
    POOL = "pool"
    DRAWBRIDGE = "drawbridge"


@dataclass
class TileMemory:
    """Memory of a single tile."""

    tile_type: TileType = TileType.UNKNOWN
    glyph: int = 0
    char: str = " "
    explored: bool = False
    walkable: bool = False
    last_seen_turn: int = 0
    times_visited: int = 0
    trap_type: Optional[str] = None
    feature_info: Optional[str] = None  # e.g., altar alignment
    stepped: bool = False  # Has player physically walked on this tile?
    has_invis: bool = False  # Remembered invisible monster encounter
    was_doorway: bool = False  # Was this tile ever observed as a door?
    seen_walkable: bool = False  # Has this tile ever been observed as walkable?

    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "type": self.tile_type.value,
            "glyph": self.glyph,
            "char": self.char,
            "explored": self.explored,
            "walkable": self.walkable,
            "last_seen": self.last_seen_turn,
            "visits": self.times_visited,
            "trap": self.trap_type,
            "feature": self.feature_info,
            "stepped": self.stepped,
            "has_invis": self.has_invis,
            "was_doorway": self.was_doorway,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "TileMemory":
        """Create from dictionary."""
        return cls(
            tile_type=TileType(data.get("type", "unknown")),
            glyph=data.get("glyph", 0),
            char=data.get("char", " "),
            explored=data.get("explored", False),
            walkable=data.get("walkable", False),
            last_seen_turn=data.get("last_seen", 0),
            times_visited=data.get("visits", 0),
            trap_type=data.get("trap"),
            feature_info=data.get("feature"),
            stepped=data.get("stepped", False),
            has_invis=data.get("has_invis", False),
        )


@dataclass
class LevelFeature:
    """A special feature on a level."""

    feature_type: str  # 'altar', 'shop', 'fountain', 'stairs_up', etc.
    position_x: int
    position_y: int
    info: dict = field(default_factory=dict)  # Additional info

    def to_dict(self) -> dict:
        return {
            "type": self.feature_type,
            "x": self.position_x,
            "y": self.position_y,
            "info": self.info,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "LevelFeature":
        return cls(
            feature_type=data["type"],
            position_x=data["x"],
            position_y=data["y"],
            info=data.get("info", {}),
        )


class LevelMemory:
    """
    Memory for a single dungeon level.

    Tracks the tile grid, special features, and exploration state.
    """

    # Standard NetHack map dimensions
    WIDTH = 80
    HEIGHT = 21

    def __init__(
        self,
        level_number: int,
        branch: str = "main",
    ):
        """
        Initialize level memory.

        Args:
            level_number: Dungeon level number
            branch: Dungeon branch name
        """
        self.level_number = level_number
        self.branch = branch

        # Tile grid
        self._tiles: list[list[TileMemory]] = [
            [TileMemory() for _ in range(self.WIDTH)]
            for _ in range(self.HEIGHT)
        ]

        # Special features
        self._features: list[LevelFeature] = []

        # Statistics
        self.tiles_explored = 0
        self.first_visited_turn: Optional[int] = None
        self.last_visited_turn: Optional[int] = None

        # Key locations
        self.upstairs_pos: Optional[tuple[int, int]] = None
        self.downstairs_pos: Optional[tuple[int, int]] = None

    def update_tile(
        self,
        x: int,
        y: int,
        tile_type: TileType,
        glyph: int = 0,
        char: str = " ",
        walkable: bool = True,
        turn: int = 0,
        trap_type: Optional[str] = None,
        feature_info: Optional[str] = None,
    ) -> None:
        """
        Update a tile in memory.

        Args:
            x: X coordinate
            y: Y coordinate
            tile_type: Type of tile
            glyph: NLE glyph ID
            char: Display character
            walkable: Whether tile is walkable
            turn: Current game turn
            trap_type: Type of trap if any
            feature_info: Additional feature info
        """
        if not (0 <= x < self.WIDTH and 0 <= y < self.HEIGHT):
            return

        tile = self._tiles[y][x]
        was_explored = tile.explored

        tile.tile_type = tile_type
        tile.glyph = glyph
        tile.char = char
        tile.walkable = walkable
        tile.last_seen_turn = turn
        tile.explored = True
        tile.times_visited += 1

        if trap_type:
            tile.trap_type = trap_type
        if feature_info:
            tile.feature_info = feature_info

        if not was_explored:
            self.tiles_explored += 1

        # Track key locations
        if tile_type == TileType.STAIRS_UP:
            self.upstairs_pos = (x, y)
            self._add_feature("stairs_up", x, y)
        elif tile_type == TileType.STAIRS_DOWN:
            self.downstairs_pos = (x, y)
            self._add_feature("stairs_down", x, y)
        elif tile_type == TileType.ALTAR:
            self._add_feature("altar", x, y, {"alignment": feature_info})
        elif tile_type == TileType.FOUNTAIN:
            self._add_feature("fountain", x, y)
        elif tile_type == TileType.SINK:
            self._add_feature("sink", x, y)
        elif tile_type == TileType.TRAP and trap_type:
            self._add_feature("trap", x, y, {"trap_type": trap_type})

    def get_tile(self, x: int, y: int) -> Optional[TileMemory]:
        """Get tile at coordinates."""
        if 0 <= x < self.WIDTH and 0 <= y < self.HEIGHT:
            return self._tiles[y][x]
        return None

    def is_explored(self, x: int, y: int) -> bool:
        """Check if tile has been explored."""
        tile = self.get_tile(x, y)
        return tile.explored if tile else False

    def is_walkable(self, x: int, y: int) -> bool:
        """Check if tile is walkable."""
        tile = self.get_tile(x, y)
        return tile.walkable if tile else False

    def mark_stepped(self, x: int, y: int) -> None:
        """Mark a tile as having been stepped on by the player."""
        if 0 <= x < self.WIDTH and 0 <= y < self.HEIGHT:
            self._tiles[y][x].stepped = True

    def is_stepped(self, x: int, y: int) -> bool:
        """Check if tile has been stepped on."""
        tile = self.get_tile(x, y)
        return tile.stepped if tile else False

    def reset_stepped_at(self, x: int, y: int) -> None:
        """Reset stepped flag when terrain changes or item thrown here."""
        if 0 <= x < self.WIDTH and 0 <= y < self.HEIGHT:
            self._tiles[y][x].stepped = False

    def set_has_invis(self, x: int, y: int, has_invis: bool = True) -> None:
        """Mark/unmark a tile as having an invisible monster encounter."""
        if 0 <= x < self.WIDTH and 0 <= y < self.HEIGHT:
            self._tiles[y][x].has_invis = has_invis

    def has_invis_at(self, x: int, y: int) -> bool:
        """Check if tile has remembered invisible monster."""
        tile = self.get_tile(x, y)
        return tile.has_invis if tile else False

    def mark_doorway(self, x: int, y: int) -> None:
        """Mark a tile as having been observed as a doorway."""
        if 0 <= x < self.WIDTH and 0 <= y < self.HEIGHT:
            self._tiles[y][x].was_doorway = True

    def is_doorway(self, x: int, y: int) -> bool:
        """Check if tile was ever observed as a doorway."""
        tile = self.get_tile(x, y)
        return tile.was_doorway if tile else False

    def mark_seen_walkable(self, x: int, y: int) -> None:
        """Mark a tile as having been observed as walkable."""
        if 0 <= x < self.WIDTH and 0 <= y < self.HEIGHT:
            self._tiles[y][x].seen_walkable = True

    def is_seen_walkable(self, x: int, y: int) -> bool:
        """Check if tile was ever observed as walkable."""
        tile = self.get_tile(x, y)
        return tile.seen_walkable if tile else False

    def _add_feature(
        self,
        feature_type: str,
        x: int,
        y: int,
        info: Optional[dict] = None,
    ) -> None:
        """Add or update a feature at a location."""
        # Check if feature already exists at this location
        for feature in self._features:
            if feature.position_x == x and feature.position_y == y:
                if feature.feature_type == feature_type:
                    # Update existing
                    if info:
                        feature.info.update(info)
                    return

        # Add new feature
        self._features.append(LevelFeature(
            feature_type=feature_type,
            position_x=x,
            position_y=y,
            info=info or {},
        ))

    def get_features(self, feature_type: Optional[str] = None) -> list[LevelFeature]:
        """Get features, optionally filtered by type."""
        if feature_type:
            return [f for f in self._features if f.feature_type == feature_type]
        return self._features.copy()

    def find_unexplored(self) -> list[tuple[int, int]]:
        """Find coordinates of unexplored but reachable tiles."""
        unexplored = []
        for y in range(self.HEIGHT):
            for x in range(self.WIDTH):
                tile = self._tiles[y][x]
                if not tile.explored:
                    # Check if adjacent to explored walkable tile
                    for dx, dy in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
                        nx, ny = x + dx, y + dy
                        if 0 <= nx < self.WIDTH and 0 <= ny < self.HEIGHT:
                            neighbor = self._tiles[ny][nx]
                            if neighbor.explored and neighbor.walkable:
                                unexplored.append((x, y))
                                break
        return unexplored

    def get_exploration_percentage(self) -> float:
        """Get percentage of level explored."""
        # Estimate total explorable tiles (excluding solid rock)
        total_explored = self.tiles_explored
        if total_explored == 0:
            return 0.0
        # Rough estimate: assume ~30% of map is explorable
        estimated_total = self.WIDTH * self.HEIGHT * 0.3
        return min(1.0, total_explored / estimated_total)

    def serialize(self) -> bytes:
        """Serialize level memory to compressed bytes."""
        data = {
            "level": self.level_number,
            "branch": self.branch,
            "explored": self.tiles_explored,
            "first_visit": self.first_visited_turn,
            "last_visit": self.last_visited_turn,
            "upstairs": self.upstairs_pos,
            "downstairs": self.downstairs_pos,
            "features": [f.to_dict() for f in self._features],
            "tiles": [],
        }

        # Only serialize explored tiles to save space
        for y in range(self.HEIGHT):
            for x in range(self.WIDTH):
                tile = self._tiles[y][x]
                if tile.explored:
                    data["tiles"].append({
                        "x": x,
                        "y": y,
                        **tile.to_dict(),
                    })

        json_data = json.dumps(data)
        return zlib.compress(json_data.encode())

    @classmethod
    def deserialize(cls, data: bytes) -> "LevelMemory":
        """Deserialize level memory from compressed bytes."""
        json_data = zlib.decompress(data).decode()
        parsed = json.loads(json_data)

        level = cls(
            level_number=parsed["level"],
            branch=parsed["branch"],
        )
        level.tiles_explored = parsed["explored"]
        level.first_visited_turn = parsed.get("first_visit")
        level.last_visited_turn = parsed.get("last_visit")
        level.upstairs_pos = tuple(parsed["upstairs"]) if parsed.get("upstairs") else None
        level.downstairs_pos = tuple(parsed["downstairs"]) if parsed.get("downstairs") else None

        # Restore features
        for f_data in parsed.get("features", []):
            level._features.append(LevelFeature.from_dict(f_data))

        # Restore tiles
        for tile_data in parsed.get("tiles", []):
            x, y = tile_data["x"], tile_data["y"]
            level._tiles[y][x] = TileMemory.from_dict(tile_data)

        return level

    def to_ascii(self, player_pos: Optional[tuple[int, int]] = None) -> str:
        """
        Render level as ASCII art.

        Args:
            player_pos: Optional player position to mark with @

        Returns:
            ASCII representation of the level
        """
        lines = []
        for y in range(self.HEIGHT):
            line = []
            for x in range(self.WIDTH):
                if player_pos and (x, y) == player_pos:
                    line.append("@")
                elif self._tiles[y][x].explored:
                    line.append(self._tiles[y][x].char or ".")
                else:
                    line.append(" ")
            lines.append("".join(line))
        return "\n".join(lines)


class DungeonMemory:
    """
    Memory for the entire dungeon.

    Manages level memories across all dungeon branches.
    """

    def __init__(self):
        """Initialize dungeon memory."""
        # Levels indexed by (branch, level_number)
        self._levels: dict[tuple[str, int], LevelMemory] = {}

        # Current location
        self._current_branch = "main"
        self._current_level = 1

        # Deepest level reached per branch
        self._deepest: dict[str, int] = {"main": 1}

    def get_level(
        self,
        level_number: int,
        branch: str = "main",
        create: bool = True,
    ) -> Optional[LevelMemory]:
        """
        Get or create level memory.

        Args:
            level_number: Dungeon level number
            branch: Dungeon branch
            create: Create if doesn't exist

        Returns:
            LevelMemory or None
        """
        key = (branch, level_number)
        if key not in self._levels and create:
            self._levels[key] = LevelMemory(level_number, branch)
        return self._levels.get(key)

    def get_current_level(self) -> LevelMemory:
        """Get current level memory."""
        return self.get_level(self._current_level, self._current_branch, create=True)

    def set_current_level(self, level_number: int, branch: str = "main") -> None:
        """
        Set current level.

        Args:
            level_number: New level number
            branch: New branch
        """
        self._current_level = level_number
        self._current_branch = branch

        # Track deepest
        if branch not in self._deepest or level_number > self._deepest[branch]:
            self._deepest[branch] = level_number

    def update_tile(
        self,
        x: int,
        y: int,
        tile_type: TileType,
        turn: int,
        **kwargs,
    ) -> None:
        """
        Update a tile on the current level.

        Args:
            x: X coordinate
            y: Y coordinate
            tile_type: Type of tile
            turn: Current game turn
            **kwargs: Additional tile data
        """
        level = self.get_current_level()
        level.update_tile(x, y, tile_type, turn=turn, **kwargs)

        # Update visit timestamps
        if level.first_visited_turn is None:
            level.first_visited_turn = turn
        level.last_visited_turn = turn

    def get_all_levels(self) -> list[LevelMemory]:
        """Get all remembered levels."""
        return list(self._levels.values())

    def get_levels_by_branch(self, branch: str) -> list[LevelMemory]:
        """Get all levels in a branch."""
        return [
            level for (b, _), level in self._levels.items()
            if b == branch
        ]

    def find_feature(
        self,
        feature_type: str,
        branch: Optional[str] = None,
    ) -> list[tuple[int, str, int, int]]:
        """
        Find all instances of a feature across levels.

        Args:
            feature_type: Type of feature to find
            branch: Optional branch to search (None for all)

        Returns:
            List of (level_number, branch, x, y) tuples
        """
        results = []
        for (b, level_num), level in self._levels.items():
            if branch and b != branch:
                continue
            for feature in level.get_features(feature_type):
                results.append((level_num, b, feature.position_x, feature.position_y))
        return results

    def get_statistics(self) -> dict:
        """Get dungeon exploration statistics."""
        total_explored = sum(l.tiles_explored for l in self._levels.values())
        total_levels = len(self._levels)

        return {
            "total_levels_visited": total_levels,
            "total_tiles_explored": total_explored,
            "deepest_main": self._deepest.get("main", 1),
            "branches_visited": list(set(b for b, _ in self._levels.keys())),
            "current_level": self._current_level,
            "current_branch": self._current_branch,
        }

    @property
    def current_level_number(self) -> int:
        """Get current level number."""
        return self._current_level

    @property
    def current_branch(self) -> str:
        """Get current branch."""
        return self._current_branch

    @property
    def deepest_level(self) -> int:
        """Get deepest level reached in main branch."""
        return self._deepest.get("main", 1)

    def clear(self) -> None:
        """Clear all dungeon memory."""
        self._levels.clear()
        self._current_branch = "main"
        self._current_level = 1
        self._deepest = {"main": 1}
