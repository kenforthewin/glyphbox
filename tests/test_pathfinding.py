"""Tests for pathfinding functions."""

import pytest
import numpy as np
from unittest.mock import MagicMock

from src.api.pathfinding import (
    find_path,
    find_nearest,
    find_unexplored,
    find_stairs_up,
    find_stairs_down,
    path_distance,
    _astar,
    _heuristic,
    _is_valid_position,
)
from src.api.models import Direction, Position
from src.api.queries import BL_X, BL_Y


def make_mock_observation(player_x=40, player_y=10, floor_tiles=None):
    """Create a mock observation with configurable floor."""
    obs = MagicMock()

    # Blstats
    blstats = np.zeros(27, dtype=np.int64)
    blstats[BL_X] = player_x
    blstats[BL_Y] = player_y
    obs.blstats = blstats

    # Default to all stone (unwalkable)
    glyphs = np.full((21, 79), 2359, dtype=np.int32)  # GLYPH_CMAP_OFF + 0 (stone)
    chars = np.full((21, 79), ord(" "), dtype=np.uint8)

    # Add floor tiles where specified
    if floor_tiles:
        for x, y in floor_tiles:
            glyphs[y, x] = 2359 + 12  # GLYPH_CMAP_OFF + 12 (floor)
            chars[y, x] = ord(".")

    obs.glyphs = glyphs
    obs.chars = chars
    obs.colors = np.zeros((21, 79), dtype=np.int8)
    obs.screen_descriptions = None

    return obs


class TestHeuristic:
    """Tests for the A* heuristic function."""

    def test_same_position(self):
        """Heuristic should be 0 for same position."""
        pos = Position(5, 5)
        assert _heuristic(pos, pos) == 0

    def test_orthogonal_distance(self):
        """Test heuristic for orthogonal movement."""
        a = Position(0, 0)
        b = Position(5, 0)  # 5 steps east
        h = _heuristic(a, b)
        # Should be close to 5 (pure orthogonal)
        assert 4.9 <= h <= 5.1

    def test_diagonal_distance(self):
        """Test heuristic for diagonal movement."""
        a = Position(0, 0)
        b = Position(3, 3)  # 3 steps diagonal
        h = _heuristic(a, b)
        # Should be around 3 + 0.4*3 = 4.2 (diagonal is slightly more)
        assert 4.0 <= h <= 4.5


class TestIsValidPosition:
    """Tests for position validation."""

    def test_valid_positions(self):
        """Test valid positions within bounds."""
        assert _is_valid_position(Position(0, 0)) is True
        assert _is_valid_position(Position(78, 20)) is True
        assert _is_valid_position(Position(40, 10)) is True

    def test_invalid_positions(self):
        """Test invalid positions outside bounds."""
        assert _is_valid_position(Position(-1, 0)) is False
        assert _is_valid_position(Position(0, -1)) is False
        assert _is_valid_position(Position(79, 0)) is False
        assert _is_valid_position(Position(0, 21)) is False
        assert _is_valid_position(Position(100, 100)) is False


class TestAstar:
    """Tests for the A* algorithm."""

    def test_already_at_goal(self):
        """Test when start equals goal."""
        walkable = [[True] * 79 for _ in range(21)]
        doorways = [[False] * 79 for _ in range(21)]  # No doorways
        start = Position(5, 5)

        path = _astar(start, start, walkable, doorways)

        assert path == []

    def test_simple_path(self):
        """Test simple straight-line path."""
        walkable = [[True] * 79 for _ in range(21)]
        doorways = [[False] * 79 for _ in range(21)]  # No doorways
        start = Position(5, 5)
        goal = Position(8, 5)  # 3 steps east

        path = _astar(start, goal, walkable, doorways)

        assert len(path) == 3
        assert path[-1] == goal

    def test_path_around_wall(self):
        """Test path finding around an obstacle."""
        walkable = [[True] * 79 for _ in range(21)]
        doorways = [[False] * 79 for _ in range(21)]  # No doorways
        # Create a wall in the direct path
        walkable[5][6] = False
        walkable[5][7] = False

        start = Position(5, 5)
        goal = Position(8, 5)

        path = _astar(start, goal, walkable, doorways)

        # Should find a path going around
        assert len(path) > 0
        assert path[-1] == goal
        # Verify no path position is on a wall
        for pos in path:
            assert walkable[pos.y][pos.x] is True

    def test_no_path_exists(self):
        """Test when no path exists."""
        walkable = [[False] * 79 for _ in range(21)]
        doorways = [[False] * 79 for _ in range(21)]  # No doorways
        walkable[5][5] = True  # Only start is walkable

        start = Position(5, 5)
        goal = Position(8, 5)

        path = _astar(start, goal, walkable, doorways)

        assert path == []

    def test_goal_not_walkable(self):
        """Test when goal is not walkable."""
        walkable = [[True] * 79 for _ in range(21)]
        doorways = [[False] * 79 for _ in range(21)]  # No doorways
        walkable[10][8] = False  # Goal is a wall

        start = Position(5, 5)
        goal = Position(8, 10)

        path = _astar(start, goal, walkable, doorways)

        assert path == []

    def test_diagonal_doorway_blocked(self):
        """Test that diagonal movement through doorways is blocked."""
        walkable = [[True] * 79 for _ in range(21)]
        doorways = [[False] * 79 for _ in range(21)]
        # Place a doorway at (6, 5)
        doorways[5][6] = True

        start = Position(5, 5)
        goal = Position(7, 4)  # Diagonally past the doorway

        path = _astar(start, goal, walkable, doorways)

        # Should find a path, but NOT go diagonally through the doorway
        assert len(path) > 0
        assert path[-1] == goal
        # Verify no diagonal move involves the doorway
        prev = start
        for pos in path:
            dx = abs(pos.x - prev.x)
            dy = abs(pos.y - prev.y)
            is_diagonal = dx + dy == 2
            if is_diagonal:
                # Neither position should be the doorway
                assert not (doorways[prev.y][prev.x] or doorways[pos.y][pos.x])
            prev = pos


class TestFindPath:
    """Tests for find_path function with mock observations."""

    def test_no_path_needed(self):
        """Test when already at target returns ALREADY_AT_TARGET."""
        floor_tiles = [(40, 10)]  # Just the player position
        obs = make_mock_observation(player_x=40, player_y=10, floor_tiles=floor_tiles)

        result = find_path(obs, Position(40, 10))

        from src.api.pathfinding import PathStopReason
        assert result.reason == PathStopReason.ALREADY_AT_TARGET
        assert result.path == []

    def test_simple_path_east(self):
        """Test simple path moving east."""
        # Create a corridor
        floor_tiles = [(x, 10) for x in range(38, 45)]
        obs = make_mock_observation(player_x=40, player_y=10, floor_tiles=floor_tiles)

        result = find_path(obs, Position(43, 10))

        from src.api.pathfinding import PathStopReason
        assert result.reason == PathStopReason.SUCCESS
        assert len(result.path) == 3
        assert all(d == Direction.E for d in result.path)


class TestIntegrationWithRealEnvironment:
    """Integration tests using real NLE environment."""

    def test_find_path_real_env(self, nle_env):
        """Test pathfinding in real environment returns PathResult."""
        obs = nle_env.reset()

        from src.api.queries import get_position
        from src.api.pathfinding import PathResult, PathStopReason

        player_pos = get_position(obs)

        # Try to find path to self - use allow_with_hostiles to bypass hostile check
        result = find_path(obs, player_pos, allow_with_hostiles=True)
        assert isinstance(result, PathResult)
        assert result.reason == PathStopReason.ALREADY_AT_TARGET
        assert result.path == []

    def test_find_unexplored_real_env(self, nle_env):
        """Test finding unexplored tiles returns TargetResult."""
        obs = nle_env.reset()

        from src.api.pathfinding import TargetResult

        # Use allow_with_hostiles to bypass hostile check
        result = find_unexplored(obs, allow_with_hostiles=True)

        assert isinstance(result, TargetResult)
        # On a fresh game, there should usually be unexplored area
        assert result.position is None or isinstance(result.position, Position)

    def test_find_stairs_functions(self, nle_env):
        """Test stair finding functions return TargetResult."""
        obs = nle_env.reset()

        from src.api.pathfinding import TargetResult

        # Use allow_with_hostiles to bypass hostile check
        stairs_up = find_stairs_up(obs, allow_with_hostiles=True)
        stairs_down = find_stairs_down(obs, allow_with_hostiles=True)

        assert isinstance(stairs_up, TargetResult)
        assert isinstance(stairs_down, TargetResult)
        # May or may not find stairs depending on visibility
        assert stairs_up.position is None or isinstance(stairs_up.position, Position)
        assert stairs_down.position is None or isinstance(stairs_down.position, Position)

    def test_path_distance(self, nle_env):
        """Test path distance calculation."""
        obs = nle_env.reset()

        from src.api.queries import get_position

        player_pos = get_position(obs)

        # Distance to self should be 0 (empty path)
        dist = path_distance(obs, player_pos)
        assert dist == 0

    def test_find_nearest_floor(self, nle_env):
        """Test finding nearest tile matching predicate."""
        obs = nle_env.reset()

        # Find nearest floor tile (should be very close)
        nearest_floor = find_nearest(obs, lambda t: t.is_floor)

        # Player typically starts on a floor
        if nearest_floor:
            assert isinstance(nearest_floor, Position)
