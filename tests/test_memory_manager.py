"""Tests for memory manager."""

import pytest
import tempfile
from pathlib import Path

from src.memory.manager import MemoryManager


@pytest.fixture
def temp_db():
    """Create a temporary database file."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir) / "test_memory.db"


@pytest.fixture
def manager(temp_db):
    """Create an initialized memory manager."""
    m = MemoryManager(str(temp_db))
    m.initialize()
    yield m
    m.close()


class TestMemoryManagerInitialization:
    """Tests for manager initialization."""

    def test_init_creates_database(self, temp_db):
        """Test that initialization creates the database file."""
        manager = MemoryManager(str(temp_db))
        manager.initialize()
        assert temp_db.exists()
        manager.close()

    def test_context_manager(self, temp_db):
        """Test using manager as context manager."""
        with MemoryManager(str(temp_db)) as manager:
            episode_id = manager.create_episode("test_ep")
            assert episode_id > 0


class TestEpisodeOperations:
    """Tests for episode operations."""

    def test_create_episode(self, manager):
        """Test creating an episode."""
        row_id = manager.create_episode("ep_001")
        assert row_id > 0

    def test_create_episode_with_metadata(self, manager):
        """Test creating episode with metadata."""
        row_id = manager.create_episode(
            "ep_002",
            metadata={"seed": 12345, "character": "Valkyrie"},
        )
        assert row_id > 0

    def test_get_episode(self, manager):
        """Test retrieving an episode."""
        manager.create_episode("ep_001")
        episode = manager.get_episode("ep_001")

        assert episode is not None
        assert episode["episode_id"] == "ep_001"
        assert episode["started_at"] is not None

    def test_get_nonexistent_episode(self, manager):
        """Test retrieving nonexistent episode."""
        episode = manager.get_episode("nonexistent")
        assert episode is None

    def test_end_episode(self, manager):
        """Test ending an episode."""
        manager.create_episode("ep_001")
        manager.end_episode(
            "ep_001",
            end_reason="death",
            final_score=1000,
            final_turns=500,
            final_depth=5,
            final_xp_level=3,
            death_reason="killed by a grid bug",
        )

        episode = manager.get_episode("ep_001")
        assert episode["end_reason"] == "death"
        assert episode["final_score"] == 1000
        assert episode["death_reason"] == "killed by a grid bug"

    def test_get_recent_episodes(self, manager):
        """Test getting recent episodes."""
        for i in range(5):
            manager.create_episode(f"ep_{i:03d}")

        recent = manager.get_recent_episodes(3)
        assert len(recent) == 3


class TestDungeonLevelOperations:
    """Tests for dungeon level operations."""

    def test_save_level(self, manager):
        """Test saving a dungeon level."""
        manager.create_episode("ep_001")
        row_id = manager.save_level(
            "ep_001",
            level_number=1,
            branch="main",
            tiles_explored=50,
            first_visited_turn=1,
        )
        assert row_id > 0

    def test_save_level_update(self, manager):
        """Test updating an existing level."""
        manager.create_episode("ep_001")
        manager.save_level("ep_001", 1, "main", tiles_explored=50)
        manager.save_level("ep_001", 1, "main", tiles_explored=100)

        level = manager.get_level("ep_001", 1, "main")
        assert level["tiles_explored"] == 100

    def test_get_level(self, manager):
        """Test retrieving a level."""
        manager.create_episode("ep_001")
        manager.save_level(
            "ep_001", 1, "main",
            tiles_explored=50,
            has_altar=1,
            altar_alignment="lawful",
        )

        level = manager.get_level("ep_001", 1, "main")
        assert level is not None
        assert level["tiles_explored"] == 50
        assert level["has_altar"] == 1

    def test_get_all_levels(self, manager):
        """Test getting all levels for an episode."""
        manager.create_episode("ep_001")
        manager.save_level("ep_001", 1, "main", tiles_explored=50)
        manager.save_level("ep_001", 2, "main", tiles_explored=30)
        manager.save_level("ep_001", 1, "mines", tiles_explored=20)

        levels = manager.get_all_levels("ep_001")
        assert len(levels) == 3


class TestStashOperations:
    """Tests for stash operations."""

    def test_save_stash(self, manager):
        """Test saving a stash."""
        manager.create_episode("ep_001")
        row_id = manager.save_stash(
            "ep_001",
            level_number=1,
            position_x=40,
            position_y=10,
            items=["long sword", "chain mail"],
            turn_discovered=100,
        )
        assert row_id > 0

    def test_get_stashes(self, manager):
        """Test retrieving stashes."""
        manager.create_episode("ep_001")
        manager.save_stash("ep_001", 1, 40, 10, ["sword"], turn_discovered=100)
        manager.save_stash("ep_001", 2, 30, 15, ["armor"], turn_discovered=200)

        stashes = manager.get_stashes("ep_001")
        assert len(stashes) == 2

        level1_stashes = manager.get_stashes("ep_001", level_number=1)
        assert len(level1_stashes) == 1
        assert "sword" in level1_stashes[0]["items"]


class TestItemDiscoveryOperations:
    """Tests for item discovery operations."""

    def test_record_item_discovery(self, manager):
        """Test recording an item discovery."""
        manager.create_episode("ep_001")
        row_id = manager.record_item_discovery(
            "ep_001",
            appearance="red potion",
            object_class="potion",
            true_identity="potion of healing",
            turn_discovered=100,
            discovery_method="use",
        )
        assert row_id > 0

    def test_get_item_identity(self, manager):
        """Test retrieving item identity."""
        manager.create_episode("ep_001")
        manager.record_item_discovery(
            "ep_001",
            appearance="red potion",
            object_class="potion",
            true_identity="potion of healing",
        )

        identity = manager.get_item_identity("ep_001", "red potion", "potion")
        assert identity is not None
        assert identity["true_identity"] == "potion of healing"

    def test_get_all_discoveries(self, manager):
        """Test getting all discoveries."""
        manager.create_episode("ep_001")
        manager.record_item_discovery("ep_001", "red potion", "potion", "healing")
        manager.record_item_discovery("ep_001", "ELAM EBOW", "scroll", "identify")

        discoveries = manager.get_all_discoveries("ep_001")
        assert len(discoveries) == 2


class TestEventOperations:
    """Tests for event operations."""

    def test_record_event(self, manager):
        """Test recording an event."""
        manager.create_episode("ep_001")
        row_id = manager.record_event(
            "ep_001",
            turn=100,
            event_type="levelup",
            description="Reached experience level 2",
            level_number=1,
            data={"new_level": 2},
        )
        assert row_id > 0

    def test_get_events(self, manager):
        """Test retrieving events."""
        manager.create_episode("ep_001")
        manager.record_event("ep_001", 100, "levelup", "Level 2")
        manager.record_event("ep_001", 150, "found_item", "Found a sword")
        manager.record_event("ep_001", 200, "levelup", "Level 3")

        all_events = manager.get_events("ep_001")
        assert len(all_events) == 3

        levelups = manager.get_events("ep_001", event_type="levelup")
        assert len(levelups) == 2


class TestMonsterKnowledgeOperations:
    """Tests for cross-episode monster knowledge."""

    def test_update_monster_knowledge(self, manager):
        """Test updating monster knowledge."""
        manager.update_monster_knowledge(
            "grid bug",
            killed=True,
            damage_dealt=5,
            damage_taken=2,
        )

        danger = manager.get_monster_danger("grid bug")
        assert 0 <= danger <= 1

    def test_monster_danger_default(self, manager):
        """Test default danger rating for unknown monster."""
        danger = manager.get_monster_danger("unknown_monster")
        assert danger == 0.5  # Default

    def test_get_dangerous_monsters(self, manager):
        """Test getting dangerous monsters."""
        # Record a death caused by a monster
        manager.update_monster_knowledge("cockatrice", caused_death=True)

        dangerous = manager.get_dangerous_monsters(threshold=0.5)
        assert "cockatrice" in dangerous

    def test_monster_knowledge_accumulates(self, manager):
        """Test that monster knowledge accumulates over encounters."""
        manager.update_monster_knowledge("orc", killed=True, damage_dealt=10)
        manager.update_monster_knowledge("orc", killed=True, damage_dealt=8)
        manager.update_monster_knowledge("orc", killed=False, damage_taken=5)

        # Should have 3 encounters
        # Can't easily verify internal state but danger should be low
        danger = manager.get_monster_danger("orc")
        assert danger < 0.5  # Should be relatively safe


class TestStatistics:
    """Tests for statistics operations."""

    def test_get_episode_statistics_empty(self, manager):
        """Test getting statistics with no episodes."""
        stats = manager.get_episode_statistics()
        assert stats["total_episodes"] == 0

    def test_get_episode_statistics(self, manager):
        """Test getting statistics with completed episodes."""
        # Create and end some episodes
        manager.create_episode("ep_001")
        manager.end_episode("ep_001", "death", final_score=1000)

        manager.create_episode("ep_002")
        manager.end_episode("ep_002", "death", final_score=2000)

        stats = manager.get_episode_statistics()
        assert stats["total_episodes"] == 2
        assert stats["avg_score"] == 1500
        assert stats["max_score"] == 2000
        assert stats["deaths"] == 2
