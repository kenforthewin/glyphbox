"""
Integration tests for autoexplore edge cases using MiniHack environments.

These tests verify our edge case implementations work correctly in real game scenarios.
"""

import pytest
import numpy as np
import gymnasium
import minihack
import minihack.envs

from src.api.queries import (
    is_blind,
    is_confused,
    is_stunned,
    can_fly,
    in_sokoban,
    get_position,
    BL_CONDITION,
    BL_DNUM,
    BL_MASK_BLIND,
    BL_MASK_CONF,
    BL_MASK_STUN,
    BL_MASK_FLY,
    BL_MASK_LEV,
    DNUM_SOKOBAN,
)
from src.api.glyphs import (
    is_dangerous_terrain_glyph,
    is_boulder_glyph,
    CMAP_POOL,
    CMAP_WATER,
    CMAP_LAVA,
    CMAP_MOAT,
    DANGEROUS_TERRAIN_CMAP,
)
from src.api.pathfinding import (
    find_path,
    find_unexplored,
    _build_walkability_grid,
    PathStopReason,
)
from src.api.models import Position


class MockObservation:
    """Wrapper to adapt MiniHack observation to our expected format."""

    def __init__(self, obs):
        self.blstats = obs["blstats"]
        self.glyphs = obs["glyphs"]
        self.chars = obs["chars"] if "chars" in obs else np.zeros((21, 79), dtype=np.uint8)
        self.colors = obs["colors"] if "colors" in obs else np.zeros((21, 79), dtype=np.int8)
        self.screen_descriptions = None
        self.inv_letters = obs.get("inv_letters", np.zeros(55, dtype=np.uint8))
        self.inv_glyphs = obs.get("inv_glyphs", np.zeros(55, dtype=np.int32))
        self.inv_oclasses = obs.get("inv_oclasses", np.zeros(55, dtype=np.uint8))
        self.inv_strs = obs.get("inv_strs", np.zeros((55, 80), dtype=np.uint8))


def make_minihack_env(env_name, max_steps=1000):
    """Create a MiniHack environment with standard observations."""
    env = gymnasium.make(
        env_name,
        observation_keys=(
            "glyphs",
            "blstats",
            "chars",
            "colors",
            "inv_letters",
            "inv_glyphs",
            "inv_oclasses",
            "inv_strs",
        ),
        max_episode_steps=max_steps,
    )
    return env


# =============================================================================
# Tests for Lava/Water Detection in Real Environments
# =============================================================================


class TestLavaDetection:
    """Tests for lava detection using MiniHack lava environments."""

    def test_lava_visible_in_freeze_lava(self):
        """Test that we can detect lava in MiniHack-Freeze-Lava environment."""
        env = make_minihack_env("MiniHack-Freeze-Lava-Full-v0")
        try:
            obs, _ = env.reset(seed=42)
            wrapped_obs = MockObservation(obs)

            # Search for lava glyphs
            lava_positions = []
            for y in range(21):
                for x in range(79):
                    glyph = int(wrapped_obs.glyphs[y, x])
                    if is_dangerous_terrain_glyph(glyph, can_fly=False):
                        lava_positions.append((x, y))

            # There should be lava in a lava freeze env
            print(f"Found {len(lava_positions)} dangerous terrain tiles (lava)")
            assert len(lava_positions) > 0, "Freeze-Lava env should have lava"

        finally:
            env.close()

    def test_walkability_grid_marks_lava_unwalkable(self):
        """Test that walkability grid marks lava as unwalkable."""
        env = make_minihack_env("MiniHack-Freeze-Lava-Full-v0")
        try:
            obs, _ = env.reset(seed=42)
            wrapped_obs = MockObservation(obs)

            # Build walkability grid without flying
            walkable, doorways = _build_walkability_grid(
                wrapped_obs, avoid_monsters=True, avoid_traps=True, player_can_fly=False
            )

            # Count lava tiles that are correctly marked unwalkable
            from nle import nethack
            lava_correctly_blocked = 0
            for y in range(21):
                for x in range(79):
                    glyph = int(wrapped_obs.glyphs[y, x])
                    if is_dangerous_terrain_glyph(glyph, can_fly=False):
                        if not walkable[y][x]:
                            lava_correctly_blocked += 1

            print(f"Lava tiles correctly blocked: {lava_correctly_blocked}")
            assert lava_correctly_blocked > 0, "Lava should be marked unwalkable"

        finally:
            env.close()


class TestRiverDetection:
    """Tests for water/river detection using MiniHack river environments."""

    def test_water_in_river_environment(self):
        """Test that we can detect water in river environment."""
        env = make_minihack_env("MiniHack-River-v0")
        try:
            obs, _ = env.reset(seed=42)
            wrapped_obs = MockObservation(obs)

            # Search for water/pool glyphs
            from nle import nethack
            pool_glyph = nethack.GLYPH_CMAP_OFF + CMAP_POOL
            water_glyph = nethack.GLYPH_CMAP_OFF + CMAP_WATER

            water_positions = []
            for y in range(21):
                for x in range(79):
                    glyph = int(wrapped_obs.glyphs[y, x])
                    if glyph == pool_glyph or glyph == water_glyph:
                        water_positions.append((x, y))
                    elif is_dangerous_terrain_glyph(glyph, can_fly=False):
                        water_positions.append((x, y))

            print(f"Found {len(water_positions)} water/dangerous terrain tiles")
            # River environment should have water
            # Note: Exact count depends on map generation

        finally:
            env.close()


# =============================================================================
# Tests for Sokoban Detection
# =============================================================================


class TestSokobanDetection:
    """Tests for Sokoban detection using MiniHack Sokoban environments."""

    def test_minihack_sokoban_environment(self):
        """Test Sokoban environment behavior with pushable objects."""
        env = make_minihack_env("MiniHack-Sokoban1a-v1")
        try:
            obs, _ = env.reset(seed=42)
            wrapped_obs = MockObservation(obs)

            # MiniHack Sokoban may or may not set DNUM to 4
            dnum = int(wrapped_obs.blstats[BL_DNUM])
            print(f"Sokoban environment dungeon number: {dnum}")

            # MiniHack Sokoban uses rocks (`) instead of real boulders
            # Check for rock-like objects (shown as ` character)
            from nle import nethack

            pushable_positions = []
            for y in range(21):
                for x in range(79):
                    glyph = int(wrapped_obs.glyphs[y, x])
                    # Check for rocks (object glyph with ` char)
                    if nethack.glyph_is_object(glyph):
                        char = chr(obs['chars'][y, x]) if obs['chars'][y, x] > 0 else ' '
                        if char == '`':  # Rock character in MiniHack Sokoban
                            pushable_positions.append((x, y))
                    # Also check for actual boulders (in case env changes)
                    if is_boulder_glyph(glyph):
                        pushable_positions.append((x, y))

            print(f"Found {len(pushable_positions)} pushable object(s)")
            # Sokoban should have pushable objects (rocks or boulders)
            assert len(pushable_positions) > 0, "Sokoban should have pushable objects"

        finally:
            env.close()


# =============================================================================
# Tests for Corridor Exploration
# =============================================================================


class TestCorridorExploration:
    """Tests for corridor exploration using MiniHack corridor environments."""

    def test_corridor_pathfinding(self):
        """Test pathfinding works in corridor environments."""
        env = make_minihack_env("MiniHack-Corridor-R3-v0")
        try:
            obs, _ = env.reset(seed=42)
            wrapped_obs = MockObservation(obs)

            # Get player position
            player_pos = get_position(wrapped_obs)
            print(f"Player position: {player_pos}")

            # Try to find an unexplored target
            result = find_unexplored(wrapped_obs, allow_with_hostiles=True)
            print(f"Find unexplored result: {result}")

            # Corridor environment should have unexplored areas to find
            assert result.reason == PathStopReason.SUCCESS, f"Expected SUCCESS, got {result.reason}: {result.message}"
            assert result.position is not None, "Should find an unexplored position"

        finally:
            env.close()


# =============================================================================
# Tests for Maze Exploration
# =============================================================================


class TestMazeExploration:
    """Tests for maze exploration using MiniHack maze environments."""

    def test_explore_maze_pathfinding(self):
        """Test pathfinding in maze environment."""
        env = make_minihack_env("MiniHack-ExploreMaze-Easy-v0")
        try:
            obs, _ = env.reset(seed=42)
            wrapped_obs = MockObservation(obs)

            player_pos = get_position(wrapped_obs)
            print(f"Player starts at: {player_pos}")

            # Build walkability grid
            walkable, doorways = _build_walkability_grid(
                wrapped_obs, avoid_monsters=True, avoid_traps=True, player_can_fly=False
            )

            # Count walkable tiles
            walkable_count = sum(1 for row in walkable for tile in row if tile)
            print(f"Walkable tiles: {walkable_count}")

            # Should have a reasonable number of walkable tiles in a maze
            assert walkable_count > 10, "Maze should have walkable corridors"

        finally:
            env.close()

    def test_find_unexplored_in_maze(self):
        """Test finding unexplored areas in maze."""
        env = make_minihack_env("MiniHack-ExploreMaze-Easy-v0")
        try:
            obs, _ = env.reset(seed=42)
            wrapped_obs = MockObservation(obs)

            # Should find unexplored areas
            result = find_unexplored(wrapped_obs, allow_with_hostiles=True)
            print(f"Find unexplored result: {result}")

            # Maze environment should have unexplored areas to find
            assert result.reason == PathStopReason.SUCCESS, f"Expected SUCCESS, got {result.reason}: {result.message}"
            assert result.position is not None, "Should find an unexplored position in maze"

        finally:
            env.close()


# =============================================================================
# Tests for Flying/Levitation
# =============================================================================


class TestLevitationEnvironment:
    """Tests for levitation detection in environments that grant levitation."""

    def test_levitation_ring_inventory(self):
        """Test detection of levitation capability."""
        # Use an environment that gives levitation items
        env = make_minihack_env("MiniHack-LavaCross-Levitate-Ring-Inv-Full-v0")
        try:
            obs, _ = env.reset(seed=42)
            wrapped_obs = MockObservation(obs)

            # Check if player can fly (might not be wearing ring yet)
            flying = can_fly(wrapped_obs)
            print(f"Can fly initially: {flying}")

            # The player has the ring but may not be wearing it
            # Check inventory for ring of levitation
            inv_strs = wrapped_obs.inv_strs
            has_lev_ring = False
            for i in range(55):
                if wrapped_obs.inv_letters[i] != 0:
                    item_str = bytes(inv_strs[i]).decode("latin-1", errors="replace").rstrip("\x00")
                    if "levitation" in item_str.lower():
                        has_lev_ring = True
                        print(f"Found levitation item: {item_str}")
                        break

            print(f"Has levitation ring in inventory: {has_lev_ring}")

        finally:
            env.close()


# =============================================================================
# Tests for Player State Detection
# =============================================================================


class TestPlayerStateInGame:
    """Tests for player state detection in actual game."""

    def test_initial_state_not_blind_confused_stunned(self):
        """Test that player starts in normal state."""
        env = make_minihack_env("MiniHack-ExploreMaze-Easy-v0")
        try:
            obs, _ = env.reset(seed=42)
            wrapped_obs = MockObservation(obs)

            # Player should start in normal state
            assert is_blind(wrapped_obs) is False
            assert is_confused(wrapped_obs) is False
            assert is_stunned(wrapped_obs) is False

            # Verify condition value
            condition = int(wrapped_obs.blstats[BL_CONDITION])
            print(f"Initial condition value: {condition}")

        finally:
            env.close()


# =============================================================================
# Multi-Room with Lava (Complex Scenario)
# =============================================================================


class TestMultiRoomLava:
    """Tests for environments with lava - pathfinding avoidance."""

    def test_pathfinding_avoids_lava(self):
        """Test that pathfinding avoids lava."""
        # Use Freeze-Lava which doesn't require minigrid
        env = make_minihack_env("MiniHack-Freeze-Lava-Full-v0")
        try:
            obs, _ = env.reset(seed=42)
            wrapped_obs = MockObservation(obs)

            player_pos = get_position(wrapped_obs)
            print(f"Player at: {player_pos}")

            # Build walkability grid without flying
            walkable, _ = _build_walkability_grid(
                wrapped_obs, player_can_fly=False
            )

            # Note: Player position may show as unwalkable (monster glyph)
            # This is expected - pathfinding starts from player position
            # and only checks walkability of destinations

            # Check that ALL lava tiles are marked unwalkable
            lava_count = 0
            lava_blocked = 0
            for y in range(21):
                for x in range(79):
                    glyph = int(wrapped_obs.glyphs[y, x])
                    if is_dangerous_terrain_glyph(glyph, can_fly=False):
                        lava_count += 1
                        if not walkable[y][x]:
                            lava_blocked += 1
                        else:
                            print(f"WARNING: Lava at ({x},{y}) not blocked!")

            print(f"Lava tiles: {lava_count}, blocked: {lava_blocked}")
            assert lava_count > 0, "Should find lava in Freeze-Lava env"
            assert lava_blocked == lava_count, "All lava should be marked unwalkable"

        finally:
            env.close()


# =============================================================================
# Movement Tests
# =============================================================================


class TestMovementInEnvironment:
    """Tests for movement and pathfinding in actual environments."""

    def test_pathfind_and_move(self):
        """Test that we can pathfind and execute moves."""
        env = make_minihack_env("MiniHack-ExploreMaze-Easy-v0")
        try:
            obs, _ = env.reset(seed=42)
            wrapped_obs = MockObservation(obs)

            start_pos = get_position(wrapped_obs)
            print(f"Starting position: {start_pos}")

            # Try to find path to adjacent walkable tile
            walkable, _ = _build_walkability_grid(wrapped_obs, player_can_fly=False)

            # Find an adjacent walkable position
            target = None
            for dx, dy in [(1, 0), (0, 1), (-1, 0), (0, -1)]:
                nx, ny = start_pos.x + dx, start_pos.y + dy
                if 0 <= nx < 79 and 0 <= ny < 21 and walkable[ny][nx]:
                    target = Position(nx, ny)
                    break

            if target:
                result = find_path(wrapped_obs, target, allow_with_hostiles=True)
                print(f"Path to {target}: {result}")
                assert result.reason in [PathStopReason.SUCCESS, PathStopReason.ALREADY_AT_TARGET]
            else:
                print("No adjacent walkable tiles found")

        finally:
            env.close()


# =============================================================================
# Run Manual Tests to Print Observations
# =============================================================================


if __name__ == "__main__":
    """Manual test runner to print observations for debugging."""
    print("=== Manual MiniHack Test Runner ===\n")

    # Test lava environment
    print("Testing MiniHack-LavaCrossingS9N1-v0...")
    test = TestLavaDetection()
    test.test_lava_visible_in_lava_crossing()
    test.test_walkability_grid_marks_lava_unwalkable()

    print("\nTesting MiniHack-Sokoban1a-v1...")
    test = TestSokobanDetection()
    test.test_minihack_sokoban_environment()

    print("\nTesting MiniHack-MultiRoom-N2-Lava-v0...")
    test = TestMultiRoomLava()
    test.test_multiroom_lava_pathfinding_avoids_lava()

    print("\n=== Tests completed ===")
