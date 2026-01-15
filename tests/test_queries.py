"""Tests for state query functions."""

import pytest
import numpy as np
from unittest.mock import MagicMock

from src.api.queries import (
    get_stats,
    get_position,
    get_visible_monsters,
    get_adjacent_monsters,
    get_inventory,
    get_current_level,
    find_stairs,
    find_doors,
    BL_X,
    BL_Y,
    BL_HP,
    BL_HPMAX,
    BL_HUNGER,
)
from src.api.models import Position, HungerState


def make_mock_observation(blstats=None, glyphs=None, chars=None, colors=None):
    """Create a mock observation for testing."""
    obs = MagicMock()

    # Default blstats
    if blstats is None:
        blstats = np.zeros(27, dtype=np.int64)
        blstats[BL_X] = 40  # Middle of screen
        blstats[BL_Y] = 10
        blstats[BL_HP] = 16
        blstats[BL_HPMAX] = 16
    obs.blstats = blstats

    # Default glyphs (all stone/unexplored)
    if glyphs is None:
        glyphs = np.full((21, 79), 2359, dtype=np.int32)  # GLYPH_CMAP_OFF + 0 (stone)
    obs.glyphs = glyphs

    # Default chars
    if chars is None:
        chars = np.full((21, 79), ord(" "), dtype=np.uint8)
    obs.chars = chars

    # Default colors
    if colors is None:
        colors = np.zeros((21, 79), dtype=np.int8)
    obs.colors = colors

    # Screen descriptions (optional)
    obs.screen_descriptions = None

    # Inventory (empty by default)
    obs.inv_letters = np.zeros(55, dtype=np.uint8)
    obs.inv_glyphs = np.zeros(55, dtype=np.int32)
    obs.inv_oclasses = np.zeros(55, dtype=np.uint8)
    obs.inv_strs = np.zeros((55, 80), dtype=np.uint8)

    return obs


class TestGetStats:
    """Tests for get_stats function."""

    def test_basic_stats_parsing(self):
        """Test parsing basic stats from blstats."""
        blstats = np.zeros(27, dtype=np.int64)
        blstats[BL_X] = 25
        blstats[BL_Y] = 12
        blstats[BL_HP] = 14
        blstats[BL_HPMAX] = 16
        blstats[10 + 4] = 50  # ENE (power)
        blstats[10 + 5] = 100  # ENEMAX

        obs = make_mock_observation(blstats=blstats)
        stats = get_stats(obs)

        assert stats.hp == 14
        assert stats.max_hp == 16
        assert stats.position == Position(25, 12)

    def test_hunger_state_parsing(self):
        """Test parsing hunger state."""
        blstats = np.zeros(27, dtype=np.int64)
        blstats[BL_HUNGER] = 2  # Hungry

        obs = make_mock_observation(blstats=blstats)
        stats = get_stats(obs)

        assert stats.hunger == HungerState.HUNGRY

    def test_hp_fraction(self):
        """Test HP fraction calculation."""
        blstats = np.zeros(27, dtype=np.int64)
        blstats[BL_HP] = 8
        blstats[BL_HPMAX] = 16

        obs = make_mock_observation(blstats=blstats)
        stats = get_stats(obs)

        assert stats.hp_fraction == 0.5


class TestGetPosition:
    """Tests for get_position function."""

    def test_position_extraction(self):
        """Test extracting player position."""
        blstats = np.zeros(27, dtype=np.int64)
        blstats[BL_X] = 50
        blstats[BL_Y] = 15

        obs = make_mock_observation(blstats=blstats)
        pos = get_position(obs)

        assert pos == Position(50, 15)


class TestGetInventory:
    """Tests for inventory parsing."""

    def test_empty_inventory(self):
        """Test parsing empty inventory."""
        obs = make_mock_observation()
        inventory = get_inventory(obs)

        assert len(inventory) == 0

    def test_single_item_inventory(self):
        """Test parsing inventory with one item."""
        obs = make_mock_observation()

        # Add a single item
        obs.inv_letters[0] = ord("a")
        obs.inv_glyphs[0] = 1906 + 50  # Some object glyph
        obs.inv_oclasses[0] = 7  # FOOD class
        item_str = b"+0 food ration"
        obs.inv_strs[0, :len(item_str)] = list(item_str)

        inventory = get_inventory(obs)

        assert len(inventory) == 1
        assert inventory[0].slot == "a"
        assert inventory[0].is_food


class TestFindStairs:
    """Tests for find_stairs function."""

    def test_no_stairs(self):
        """Test when no stairs are visible."""
        obs = make_mock_observation()

        up, down = find_stairs(obs)

        assert up is None
        assert down is None

    def test_stairs_up(self):
        """Test finding stairs up."""
        obs = make_mock_observation()
        obs.chars[5, 10] = ord("<")

        up, down = find_stairs(obs)

        assert up == Position(10, 5)
        assert down is None

    def test_stairs_down(self):
        """Test finding stairs down."""
        obs = make_mock_observation()
        obs.chars[8, 20] = ord(">")

        up, down = find_stairs(obs)

        assert up is None
        assert down == Position(20, 8)

    def test_both_stairs(self):
        """Test finding both stairs."""
        obs = make_mock_observation()
        obs.chars[5, 10] = ord("<")
        obs.chars[15, 30] = ord(">")

        up, down = find_stairs(obs)

        assert up == Position(10, 5)
        assert down == Position(30, 15)


class TestIntegrationWithRealEnvironment:
    """Integration tests using real NLE environment."""

    def test_get_stats_real_env(self, nle_env):
        """Test get_stats with real environment."""
        obs = nle_env.reset()
        stats = get_stats(obs)

        # Basic sanity checks
        assert stats.hp > 0
        assert stats.max_hp >= stats.hp
        assert stats.dungeon_level == 1
        assert 0 <= stats.position.x < 79
        assert 0 <= stats.position.y < 21

    def test_get_current_level_real_env(self, nle_env):
        """Test get_current_level with real environment."""
        obs = nle_env.reset()
        level = get_current_level(obs)

        assert level.level_number == 1
        assert len(level.tiles) == 21
        assert len(level.tiles[0]) == 79
        assert level.explored_tiles >= 0

    def test_get_visible_monsters_real_env(self, nle_env):
        """Test get_visible_monsters with real environment."""
        obs = nle_env.reset()
        monsters = get_visible_monsters(obs)

        # May or may not have monsters, but shouldn't crash
        assert isinstance(monsters, list)

    def test_find_stairs_real_env(self, nle_env):
        """Test find_stairs with real environment."""
        obs = nle_env.reset()
        up, down = find_stairs(obs)

        # On level 1, there should be stairs down somewhere
        # (might not be visible initially though)
        # Just ensure it doesn't crash
        assert up is None or isinstance(up, Position)
        assert down is None or isinstance(down, Position)
