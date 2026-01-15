"""Tests for dungeon memory."""

import pytest

from src.memory.dungeon import (
    DungeonMemory,
    LevelFeature,
    LevelMemory,
    TileMemory,
    TileType,
)


class TestTileMemory:
    """Tests for TileMemory dataclass."""

    def test_default_values(self):
        """Test default tile memory values."""
        tile = TileMemory()
        assert tile.tile_type == TileType.UNKNOWN
        assert not tile.explored
        assert not tile.walkable
        assert tile.times_visited == 0

    def test_to_dict(self):
        """Test converting tile to dictionary."""
        tile = TileMemory(
            tile_type=TileType.FLOOR,
            glyph=100,
            char=".",
            explored=True,
            walkable=True,
            last_seen_turn=50,
            times_visited=3,
        )
        d = tile.to_dict()
        assert d["type"] == "floor"
        assert d["explored"] is True
        assert d["visits"] == 3

    def test_from_dict(self):
        """Test creating tile from dictionary."""
        d = {
            "type": "corridor",
            "glyph": 50,
            "char": "#",
            "explored": True,
            "walkable": True,
            "last_seen": 100,
            "visits": 5,
        }
        tile = TileMemory.from_dict(d)
        assert tile.tile_type == TileType.CORRIDOR
        assert tile.explored
        assert tile.times_visited == 5


class TestLevelFeature:
    """Tests for LevelFeature dataclass."""

    def test_creation(self):
        """Test creating a level feature."""
        feature = LevelFeature(
            feature_type="altar",
            position_x=40,
            position_y=10,
            info={"alignment": "lawful"},
        )
        assert feature.feature_type == "altar"
        assert feature.position_x == 40
        assert feature.info["alignment"] == "lawful"

    def test_to_dict(self):
        """Test converting feature to dictionary."""
        feature = LevelFeature("stairs_up", 30, 15)
        d = feature.to_dict()
        assert d["type"] == "stairs_up"
        assert d["x"] == 30
        assert d["y"] == 15

    def test_from_dict(self):
        """Test creating feature from dictionary."""
        d = {"type": "fountain", "x": 20, "y": 12, "info": {}}
        feature = LevelFeature.from_dict(d)
        assert feature.feature_type == "fountain"
        assert feature.position_x == 20


class TestLevelMemory:
    """Tests for LevelMemory class."""

    @pytest.fixture
    def level(self):
        """Create a fresh level memory."""
        return LevelMemory(level_number=1, branch="main")

    def test_initial_state(self, level):
        """Test initial level state."""
        assert level.level_number == 1
        assert level.branch == "main"
        assert level.tiles_explored == 0
        assert level.upstairs_pos is None
        assert level.downstairs_pos is None

    def test_update_tile(self, level):
        """Test updating a tile."""
        level.update_tile(
            x=40,
            y=10,
            tile_type=TileType.FLOOR,
            glyph=100,
            char=".",
            walkable=True,
            turn=100,
        )

        tile = level.get_tile(40, 10)
        assert tile is not None
        assert tile.tile_type == TileType.FLOOR
        assert tile.explored
        assert tile.walkable
        assert tile.last_seen_turn == 100
        assert level.tiles_explored == 1

    def test_update_same_tile_twice(self, level):
        """Test that updating same tile doesn't double-count exploration."""
        level.update_tile(40, 10, TileType.FLOOR, turn=100)
        level.update_tile(40, 10, TileType.FLOOR, turn=101)

        assert level.tiles_explored == 1
        tile = level.get_tile(40, 10)
        assert tile.times_visited == 2
        assert tile.last_seen_turn == 101

    def test_stairs_tracking(self, level):
        """Test automatic stairs position tracking."""
        level.update_tile(30, 10, TileType.STAIRS_UP, turn=100)
        level.update_tile(50, 15, TileType.STAIRS_DOWN, turn=100)

        assert level.upstairs_pos == (30, 10)
        assert level.downstairs_pos == (50, 15)

    def test_feature_tracking(self, level):
        """Test automatic feature tracking."""
        level.update_tile(40, 12, TileType.ALTAR, turn=100, feature_info="neutral")
        level.update_tile(35, 10, TileType.FOUNTAIN, turn=100)

        altars = level.get_features("altar")
        assert len(altars) == 1
        assert altars[0].position_x == 40

        fountains = level.get_features("fountain")
        assert len(fountains) == 1

    def test_is_explored(self, level):
        """Test exploration check."""
        assert not level.is_explored(40, 10)
        level.update_tile(40, 10, TileType.FLOOR, turn=100)
        assert level.is_explored(40, 10)

    def test_is_walkable(self, level):
        """Test walkability check."""
        level.update_tile(40, 10, TileType.FLOOR, walkable=True, turn=100)
        level.update_tile(41, 10, TileType.WALL, walkable=False, turn=100)

        assert level.is_walkable(40, 10)
        assert not level.is_walkable(41, 10)

    def test_find_unexplored(self, level):
        """Test finding unexplored tiles."""
        # Create an explored walkable tile
        level.update_tile(40, 10, TileType.FLOOR, walkable=True, turn=100)

        # Unexplored tiles adjacent to explored walkable should be returned
        unexplored = level.find_unexplored()
        # Adjacent positions to (40, 10) that are unexplored
        assert (39, 10) in unexplored or (41, 10) in unexplored

    def test_out_of_bounds(self, level):
        """Test handling out of bounds coordinates."""
        # Should not raise, just ignore
        level.update_tile(-1, -1, TileType.FLOOR, turn=100)
        level.update_tile(100, 100, TileType.FLOOR, turn=100)

        assert level.get_tile(-1, -1) is None
        assert level.get_tile(100, 100) is None

    def test_serialization(self, level):
        """Test level serialization and deserialization."""
        level.update_tile(40, 10, TileType.FLOOR, turn=100, walkable=True)
        level.update_tile(30, 10, TileType.STAIRS_UP, turn=100)
        level.first_visited_turn = 100
        level.last_visited_turn = 150

        # Serialize
        data = level.serialize()
        assert isinstance(data, bytes)

        # Deserialize
        restored = LevelMemory.deserialize(data)

        assert restored.level_number == 1
        assert restored.branch == "main"
        assert restored.tiles_explored == 2
        assert restored.upstairs_pos == (30, 10)
        assert restored.is_explored(40, 10)
        assert restored.is_walkable(40, 10)

    def test_to_ascii(self, level):
        """Test ASCII rendering."""
        level.update_tile(40, 10, TileType.FLOOR, char=".", turn=100)
        level.update_tile(41, 10, TileType.FLOOR, char=".", turn=100)

        ascii_map = level.to_ascii(player_pos=(40, 10))

        # Player should be at @
        lines = ascii_map.split("\n")
        assert "@" in lines[10]


class TestDungeonMemory:
    """Tests for DungeonMemory class."""

    @pytest.fixture
    def dungeon(self):
        """Create a fresh dungeon memory."""
        return DungeonMemory()

    def test_initial_state(self, dungeon):
        """Test initial dungeon state."""
        assert dungeon.current_level_number == 1
        assert dungeon.current_branch == "main"
        assert dungeon.deepest_level == 1

    def test_get_level_creates(self, dungeon):
        """Test that get_level creates level if needed."""
        level = dungeon.get_level(1, "main")
        assert level is not None
        assert level.level_number == 1

    def test_get_level_no_create(self, dungeon):
        """Test get_level with create=False."""
        level = dungeon.get_level(5, "main", create=False)
        assert level is None

    def test_set_current_level(self, dungeon):
        """Test setting current level."""
        dungeon.set_current_level(3, "main")

        assert dungeon.current_level_number == 3
        assert dungeon.deepest_level == 3

    def test_deepest_tracking(self, dungeon):
        """Test deepest level tracking."""
        dungeon.set_current_level(3, "main")
        dungeon.set_current_level(5, "main")
        dungeon.set_current_level(2, "main")  # Go back up

        assert dungeon.deepest_level == 5

    def test_update_tile(self, dungeon):
        """Test updating tile on current level."""
        dungeon.update_tile(40, 10, TileType.FLOOR, turn=100)

        level = dungeon.get_current_level()
        assert level.is_explored(40, 10)
        assert level.first_visited_turn == 100
        assert level.last_visited_turn == 100

    def test_multiple_branches(self, dungeon):
        """Test tracking multiple branches."""
        dungeon.set_current_level(1, "main")
        dungeon.update_tile(40, 10, TileType.FLOOR, turn=100)

        dungeon.set_current_level(1, "mines")
        dungeon.update_tile(30, 12, TileType.FLOOR, turn=110)

        main_levels = dungeon.get_levels_by_branch("main")
        mines_levels = dungeon.get_levels_by_branch("mines")

        assert len(main_levels) == 1
        assert len(mines_levels) == 1

    def test_find_feature(self, dungeon):
        """Test finding features across all levels."""
        # Add stairs on multiple levels
        dungeon.set_current_level(1, "main")
        dungeon.update_tile(30, 10, TileType.STAIRS_DOWN, turn=100)

        dungeon.set_current_level(2, "main")
        dungeon.update_tile(35, 12, TileType.STAIRS_DOWN, turn=110)

        results = dungeon.find_feature("stairs_down")
        assert len(results) == 2

    def test_get_statistics(self, dungeon):
        """Test getting dungeon statistics."""
        dungeon.set_current_level(3, "main")
        dungeon.update_tile(40, 10, TileType.FLOOR, turn=100)

        stats = dungeon.get_statistics()

        assert stats["deepest_main"] == 3
        assert stats["total_levels_visited"] == 1
        assert stats["total_tiles_explored"] == 1

    def test_clear(self, dungeon):
        """Test clearing dungeon memory."""
        dungeon.set_current_level(5, "main")
        dungeon.update_tile(40, 10, TileType.FLOOR, turn=100)

        dungeon.clear()

        assert dungeon.current_level_number == 1
        assert dungeon.deepest_level == 1
        assert len(dungeon.get_all_levels()) == 0
