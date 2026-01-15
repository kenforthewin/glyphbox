"""Tests for episode memory."""

import pytest
import tempfile
from pathlib import Path

from src.memory.episode import EpisodeEvent, EpisodeMemory, EpisodeStatistics


class TestEpisodeStatistics:
    """Tests for EpisodeStatistics dataclass."""

    def test_creation(self):
        """Test creating episode statistics."""
        from datetime import datetime
        stats = EpisodeStatistics(
            episode_id="ep_001",
            started_at=datetime.now(),
            final_score=1000,
            final_turns=500,
        )
        assert stats.episode_id == "ep_001"
        assert stats.final_score == 1000

    def test_to_dict(self):
        """Test converting statistics to dictionary."""
        from datetime import datetime
        stats = EpisodeStatistics(
            episode_id="ep_001",
            started_at=datetime.now(),
            final_score=1000,
            monsters_killed=5,
        )
        d = stats.to_dict()
        assert d["episode_id"] == "ep_001"
        assert d["final_score"] == 1000
        assert d["monsters_killed"] == 5


class TestEpisodeEvent:
    """Tests for EpisodeEvent dataclass."""

    def test_creation(self):
        """Test creating an event."""
        event = EpisodeEvent(
            turn=100,
            event_type="levelup",
            description="Reached level 2",
            level_number=1,
            data={"new_level": 2},
        )
        assert event.turn == 100
        assert event.event_type == "levelup"
        assert event.data["new_level"] == 2


class TestEpisodeMemory:
    """Tests for EpisodeMemory class."""

    @pytest.fixture
    def temp_db(self):
        """Create a temporary database file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield str(Path(tmpdir) / "test_memory.db")

    @pytest.fixture
    def episode(self, temp_db):
        """Create a fresh episode memory."""
        ep = EpisodeMemory(db_path=temp_db)
        ep.start()
        yield ep
        ep.close()

    @pytest.fixture
    def episode_no_db(self):
        """Create episode memory without database."""
        ep = EpisodeMemory()
        ep.start()
        yield ep

    def test_episode_creation(self, episode):
        """Test episode creation."""
        assert episode.episode_id is not None
        assert episode._started

    def test_episode_with_custom_id(self, temp_db):
        """Test episode with custom ID."""
        ep = EpisodeMemory(db_path=temp_db, episode_id="custom_001")
        ep.start()
        assert ep.episode_id == "custom_001"
        ep.close()

    def test_update_state(self, episode):
        """Test updating episode state."""
        episode.update_state(
            turn=100,
            hp=20,
            max_hp=30,
            position_x=40,
            position_y=10,
            dungeon_level=2,
            monsters_visible=1,
            xp_level=1,
        )

        summary = episode.get_summary()
        assert summary["current_turn"] == 100
        assert summary["current_level"] == 2
        assert summary["hp"] == 20

    def test_xp_level_tracking(self, episode):
        """Test XP level tracking triggers event."""
        episode.update_state(
            turn=100, hp=20, max_hp=20,
            position_x=10, position_y=15, dungeon_level=1,
            xp_level=1,
        )
        episode.update_state(
            turn=200, hp=25, max_hp=25,
            position_x=10, position_y=15, dungeon_level=1,
            xp_level=2,
        )

        events = episode.get_events(event_type="levelup")
        assert len(events) == 1
        assert events[0].description == "Reached experience level 2"

    def test_record_event(self, episode):
        """Test recording events."""
        episode.record_event(
            "found_item",
            "Found a long sword",
            turn=100,
            data={"item": "long sword"},
        )

        events = episode.get_events()
        # Should have at least episode_start and found_item
        assert len(events) >= 2

        found_events = episode.get_events(event_type="found_item")
        assert len(found_events) == 1
        assert found_events[0].data["item"] == "long sword"

    def test_record_skill_execution(self, episode):
        """Test recording skill executions."""
        episode.record_skill_execution(
            skill_name="cautious_explore",
            success=True,
            stopped_reason="monster_spotted",
            actions_taken=10,
            turns_elapsed=8,
        )

        stats = episode.get_statistics()
        assert stats.skills_used == 1
        assert stats.total_actions == 10

    def test_record_skill_created(self, episode):
        """Test recording skill creation."""
        episode.record_skill_created("new_combat_skill")

        stats = episode.get_statistics()
        assert stats.skills_created == 1

    def test_record_monster_kill(self, episode):
        """Test recording monster kills."""
        episode.record_monster_kill("grid bug", damage_dealt=5)
        episode.record_monster_kill("orc", damage_dealt=15)

        stats = episode.get_statistics()
        assert stats.monsters_killed == 2
        assert stats.damage_dealt == 20

    def test_record_damage_taken(self, episode):
        """Test recording damage taken."""
        episode.record_damage_taken(5, source="orc")
        episode.record_damage_taken(3, source="orc")

        stats = episode.get_statistics()
        assert stats.damage_taken == 8

    def test_end_episode(self, episode):
        """Test ending an episode."""
        episode.update_state(
            turn=100, hp=20, max_hp=20,
            position_x=10, position_y=15, dungeon_level=3,
            xp_level=2,
        )

        stats = episode.end(
            end_reason="death",
            final_score=1000,
            final_turns=500,
            death_reason="killed by a troll",
        )

        assert stats.end_reason == "death"
        assert stats.final_score == 1000
        assert stats.death_reason == "killed by a troll"

    def test_episode_summary(self, episode_no_db):
        """Test getting episode summary."""
        episode_no_db.update_state(
            turn=100, hp=15, max_hp=20,
            position_x=10, position_y=15, dungeon_level=2,
            monsters_visible=1,
            hostile_monsters_visible=1,  # Hostile count sets in_combat
        )
        episode_no_db.record_monster_kill("orc")
        episode_no_db.working.add_goal("fight", priority=1)

        summary = episode_no_db.get_summary()

        assert summary["current_turn"] == 100
        assert summary["hp"] == 15
        assert summary["in_combat"] is True
        assert summary["monsters_killed"] == 1
        assert summary["pending_goals"] == 1

    def test_context_manager(self, temp_db):
        """Test episode as context manager."""
        with EpisodeMemory(db_path=temp_db, episode_id="test_ep") as episode:
            episode.update_state(
                turn=100, hp=20, max_hp=20,
                position_x=10, position_y=15, dungeon_level=1,
            )
            episode.record_event("test_event", "Testing")

        # Episode should be ended after context


class TestEpisodeMemoryIntegration:
    """Integration tests for episode memory with all subsystems."""

    @pytest.fixture
    def episode(self):
        """Create episode without database for faster tests."""
        ep = EpisodeMemory()
        ep.start()
        yield ep

    def test_full_gameplay_simulation(self, episode):
        """Test simulating a full gameplay session."""
        # Start exploring
        episode.update_state(
            turn=1, hp=20, max_hp=20,
            position_x=40, position_y=10, dungeon_level=1,
        )
        episode.working.add_goal("explore", priority=5)
        episode.record_skill_execution("cautious_explore", success=True, actions_taken=20)

        # Encounter monster
        episode.update_state(
            turn=21, hp=20, max_hp=20,
            position_x=45, position_y=12, dungeon_level=1,
            monsters_visible=1,
        )
        episode.working.record_sighting("orc", 46, 12, 21, "monster", is_hostile=True)
        episode.record_skill_execution("melee_fight", success=True, actions_taken=5)
        episode.record_monster_kill("orc", damage_dealt=10)

        # Take damage
        episode.record_damage_taken(5, source="orc")

        # Find stairs
        episode.dungeon.update_tile(50, 15, episode.dungeon.get_current_level()._tiles[0][0].tile_type, turn=30)

        # Descend
        episode.update_state(
            turn=35, hp=15, max_hp=20,
            position_x=30, position_y=10, dungeon_level=2,
        )

        # Die
        stats = episode.end("death", final_score=500, final_turns=40, death_reason="killed by a troll")

        assert stats.monsters_killed == 1
        assert stats.damage_dealt == 10
        assert stats.damage_taken == 5
        assert stats.skills_used >= 2
        assert stats.final_depth >= 2

    def test_dungeon_memory_integration(self, episode):
        """Test dungeon memory updates through episode."""
        episode.update_state(
            turn=1, hp=20, max_hp=20,
            position_x=40, position_y=10, dungeon_level=1,
        )

        # Manually update dungeon tiles
        from src.memory.dungeon import TileType
        episode.dungeon.update_tile(40, 10, TileType.FLOOR, turn=1)
        episode.dungeon.update_tile(41, 10, TileType.FLOOR, turn=1)

        stats = episode.dungeon.get_statistics()
        assert stats["total_tiles_explored"] == 2

    def test_working_memory_integration(self, episode):
        """Test working memory updates through episode."""
        episode.update_state(
            turn=100, hp=15, max_hp=20,
            position_x=40, position_y=10, dungeon_level=2,
            monsters_visible=2,
            hostile_monsters_visible=2,  # Hostile count sets in_combat
            message="You see an orc.",
        )

        assert episode.working.current_turn == 100
        assert episode.working.current_level == 2
        assert episode.working.in_combat

        messages = episode.working.get_recent_messages()
        assert len(messages) == 1
        assert "orc" in messages[0][1]
