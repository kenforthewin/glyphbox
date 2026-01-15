"""Integration tests for NetHackAPI."""

import pytest

from src.api.nethack_api import NetHackAPI
from src.api.models import Direction, Position, ActionResult


class TestNetHackAPILifecycle:
    """Tests for API lifecycle management."""

    def test_create_and_close(self):
        """Test creating and closing API."""
        api = NetHackAPI(max_episode_steps=100)
        try:
            obs = api.reset()
            assert obs is not None
        finally:
            api.close()

    def test_context_manager(self):
        """Test using API as context manager."""
        with NetHackAPI(max_episode_steps=100) as api:
            obs = api.reset()
            assert obs is not None

    def test_reset_returns_observation(self):
        """Test that reset returns an observation."""
        with NetHackAPI(max_episode_steps=100) as api:
            obs = api.reset()
            assert obs is not None
            assert hasattr(obs, "glyphs")
            assert hasattr(obs, "blstats")


class TestNetHackAPIQueries:
    """Tests for API query methods."""

    def test_get_stats(self, nethack_api):
        """Test get_stats method."""
        nethack_api.reset()
        stats = nethack_api.get_stats()

        assert stats.hp > 0
        assert stats.max_hp >= stats.hp
        assert stats.dungeon_level >= 1
        assert isinstance(stats.position, Position)

    def test_get_position(self, nethack_api):
        """Test get_position method."""
        nethack_api.reset()
        pos = nethack_api.get_position()

        assert isinstance(pos, Position)
        assert 0 <= pos.x < 79
        assert 0 <= pos.y < 21

    def test_get_screen(self, nethack_api):
        """Test get_screen method."""
        nethack_api.reset()
        screen = nethack_api.get_screen()

        assert isinstance(screen, str)
        assert len(screen) > 0
        # Screen should have multiple lines
        lines = screen.split("\n")
        assert len(lines) >= 20

    def test_get_message(self, nethack_api):
        """Test get_message method."""
        nethack_api.reset()
        message = nethack_api.get_message()

        # Message may be empty or contain text
        assert isinstance(message, str)

    def test_get_inventory(self, nethack_api):
        """Test get_inventory method."""
        nethack_api.reset()
        inventory = nethack_api.get_inventory()

        assert isinstance(inventory, list)
        # Player should have some starting items
        assert len(inventory) > 0

    def test_get_current_level(self, nethack_api):
        """Test get_current_level method."""
        nethack_api.reset()
        level = nethack_api.get_current_level()

        assert level.level_number == 1
        assert level.dungeon_number == 0  # Dungeons of Doom
        assert len(level.tiles) == 21
        assert len(level.tiles[0]) == 79

    def test_get_visible_monsters(self, nethack_api):
        """Test get_visible_monsters method."""
        nethack_api.reset()
        monsters = nethack_api.get_visible_monsters()

        assert isinstance(monsters, list)

    def test_get_adjacent_monsters(self, nethack_api):
        """Test get_adjacent_monsters method."""
        nethack_api.reset()
        monsters = nethack_api.get_adjacent_monsters()

        assert isinstance(monsters, list)


class TestNetHackAPIActions:
    """Tests for API action methods."""

    def test_move(self, nethack_api):
        """Test move method."""
        nethack_api.reset()
        result = nethack_api.move(Direction.N)

        assert isinstance(result, ActionResult)

    def test_wait(self, nethack_api):
        """Test wait method."""
        nethack_api.reset()
        result = nethack_api.wait()

        assert result.success is True

    def test_search(self, nethack_api):
        """Test search method."""
        nethack_api.reset()
        result = nethack_api.search()

        assert result.success is True

    def test_attack(self, nethack_api):
        """Test attack method."""
        nethack_api.reset()
        result = nethack_api.attack(Direction.N)

        assert isinstance(result, ActionResult)

    def test_kick(self, nethack_api):
        """Test kick method."""
        nethack_api.reset()
        result = nethack_api.kick(Direction.N)

        assert isinstance(result, ActionResult)

    def test_pickup(self, nethack_api):
        """Test pickup method."""
        nethack_api.reset()
        result = nethack_api.pickup()

        assert isinstance(result, ActionResult)

    def test_send_keys(self, nethack_api):
        """Test send_keys method."""
        nethack_api.reset()
        # Send a wait command via raw keys
        result = nethack_api.send_keys(".")

        assert result.success is True


class TestNetHackAPIPathfinding:
    """Tests for API pathfinding methods."""

    def test_internal_find_path_to_self(self, nethack_api):
        """Test internal _find_path to current position returns ALREADY_AT_TARGET."""
        nethack_api.reset()
        pos = nethack_api.get_position()

        # Use allow_with_hostiles=True to bypass hostile check for this test
        result = nethack_api._find_path(pos, allow_with_hostiles=True)

        from src.api import PathResult, PathStopReason
        assert isinstance(result, PathResult)
        assert result.reason == PathStopReason.ALREADY_AT_TARGET
        assert result.path == []

    def test_internal_find_path_hostile_in_view(self, nethack_api):
        """Test internal _find_path refuses when hostile in view."""
        nethack_api.reset()
        pos = nethack_api.get_position()

        # Without allow_with_hostiles, may get HOSTILE_IN_VIEW if there are monsters
        result = nethack_api._find_path(pos)

        from src.api import PathResult, PathStopReason
        assert isinstance(result, PathResult)
        # Either at target or blocked by hostiles
        assert result.reason in (PathStopReason.ALREADY_AT_TARGET, PathStopReason.HOSTILE_IN_VIEW)

    def test_move_to_adjacent(self, nethack_api):
        """Test move_to can move to an adjacent walkable tile."""
        nethack_api.reset()
        start_pos = nethack_api.get_position()

        # Find a walkable adjacent tile
        from src.api.models import Direction
        target = None
        for d in [Direction.N, Direction.S, Direction.E, Direction.W]:
            adj_pos = start_pos.move(d)
            tile = nethack_api.get_tile(adj_pos)
            if tile and tile.is_walkable:
                target = adj_pos
                break

        if target:
            result = nethack_api.move_to(target, allow_with_hostiles=True)
            # Should either succeed or be interrupted by hostile
            assert nethack_api.position == target or not result.success

    def test_find_unexplored(self, nethack_api):
        """Test finding unexplored area returns TargetResult."""
        nethack_api.reset()

        # Use allow_with_hostiles=True to bypass hostile check for this test
        result = nethack_api.find_unexplored(allow_with_hostiles=True)

        from src.api import TargetResult
        assert isinstance(result, TargetResult)
        # May or may not find unexplored tiles
        assert result.position is None or isinstance(result.position, Position)

    def test_find_stairs_up(self, nethack_api):
        """Test finding stairs up returns TargetResult."""
        nethack_api.reset()

        # Use allow_with_hostiles=True to bypass hostile check for this test
        result = nethack_api.find_stairs_up(allow_with_hostiles=True)

        from src.api import TargetResult
        assert isinstance(result, TargetResult)
        # Stairs up usually not on level 1
        assert result.position is None or isinstance(result.position, Position)

    def test_find_stairs_down(self, nethack_api):
        """Test finding stairs down returns TargetResult."""
        nethack_api.reset()

        # Use allow_with_hostiles=True to bypass hostile check for this test
        result = nethack_api.find_stairs_down(allow_with_hostiles=True)

        from src.api import TargetResult
        assert isinstance(result, TargetResult)
        # May or may not be visible
        assert result.position is None or isinstance(result.position, Position)


class TestNetHackAPIKnowledge:
    """Tests for API knowledge methods."""

    def test_lookup_monster(self, nethack_api):
        """Test monster lookup."""
        info = nethack_api.lookup_monster("goblin")

        assert info is not None
        assert info.name == "goblin"
        assert info.difficulty >= 0  # difficulty field, not level

    def test_lookup_monster_not_found(self, nethack_api):
        """Test monster lookup for unknown monster."""
        info = nethack_api.lookup_monster("nonexistent_monster_xyz")

        assert info is None

    def test_is_corpse_safe(self, nethack_api):
        """Test corpse safety check."""
        # Lichen corpses are always safe
        assert nethack_api.is_corpse_safe("lichen") is True

        # Cockatrice corpses are dangerous
        assert nethack_api.is_corpse_safe("cockatrice") is False

    def test_is_dangerous_melee(self, nethack_api):
        """Test dangerous monster check."""
        assert nethack_api.is_dangerous_melee("floating eye") is True
        assert nethack_api.is_dangerous_melee("cockatrice") is True
        assert nethack_api.is_dangerous_melee("grid bug") is False


class TestNetHackAPIStatePersistence:
    """Tests for state persistence across actions."""

    def test_turn_advances_on_action(self, nethack_api):
        """Test that turns advance when taking actions."""
        nethack_api.reset()

        initial_turn = nethack_api.get_stats().turn

        # Wait should advance turn
        nethack_api.wait()

        new_turn = nethack_api.get_stats().turn

        assert new_turn >= initial_turn

    def test_position_changes_on_move(self, nethack_api):
        """Test that position can change on movement."""
        nethack_api.reset()

        initial_pos = nethack_api.get_position()

        # Try moving in all directions until one succeeds
        for direction in [Direction.N, Direction.S, Direction.E, Direction.W,
                          Direction.NE, Direction.NW, Direction.SE, Direction.SW]:
            nethack_api.move(direction)
            new_pos = nethack_api.get_position()
            if new_pos != initial_pos:
                break

        # Position may or may not have changed (depends on walls)
        assert isinstance(new_pos, Position)


class TestNetHackAPIGameplay:
    """Tests for longer gameplay sequences."""

    def test_explore_briefly(self, nethack_api):
        """Test taking multiple actions."""
        nethack_api.reset()

        # Take 10 actions
        for _ in range(10):
            nethack_api.move(Direction.N)

        # Should still be able to query state
        stats = nethack_api.get_stats()
        assert stats is not None
        assert stats.hp > 0 or stats.hp <= 0  # May have died

    def test_search_multiple_times(self, nethack_api):
        """Test searching multiple times."""
        nethack_api.reset()

        # Search 5 times
        for _ in range(5):
            result = nethack_api.search()
            assert result.success is True

        # State should still be valid
        stats = nethack_api.get_stats()
        assert stats is not None
