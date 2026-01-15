"""Tests for working memory."""

import pytest

from src.memory.working import (
    EntitySighting,
    PendingGoal,
    TurnSnapshot,
    WorkingMemory,
)


class TestTurnSnapshot:
    """Tests for TurnSnapshot dataclass."""

    def test_creation(self):
        """Test creating a turn snapshot."""
        snap = TurnSnapshot(
            turn=100,
            hp=20,
            max_hp=30,
            position_x=10,
            position_y=15,
            dungeon_level=2,
            monsters_visible=3,
            items_here=2,
            hunger_state="hungry",
            message="You see a grid bug.",
        )
        assert snap.turn == 100
        assert snap.hp == 20
        assert snap.max_hp == 30
        assert snap.position_x == 10
        assert snap.monsters_visible == 3
        assert snap.hunger_state == "hungry"


class TestPendingGoal:
    """Tests for PendingGoal dataclass."""

    def test_creation(self):
        """Test creating a pending goal."""
        goal = PendingGoal(
            goal_type="explore",
            priority=3,
            target=(10, 15),
            reason="Find stairs down",
            created_turn=100,
        )
        assert goal.goal_type == "explore"
        assert goal.priority == 3
        assert goal.target == (10, 15)

    def test_expiration(self):
        """Test goal expiration."""
        goal = PendingGoal(
            goal_type="fight",
            priority=1,
            created_turn=100,
            expires_turn=110,
        )
        assert not goal.is_expired(105)
        assert not goal.is_expired(110)
        assert goal.is_expired(111)

    def test_no_expiration(self):
        """Test goal with no expiration."""
        goal = PendingGoal(goal_type="explore", priority=5, created_turn=100)
        assert not goal.is_expired(1000)


class TestWorkingMemory:
    """Tests for WorkingMemory class."""

    @pytest.fixture
    def memory(self):
        """Create fresh working memory."""
        return WorkingMemory()

    def test_initial_state(self, memory):
        """Test initial memory state."""
        assert memory.current_turn == 0
        assert memory.current_level == 1
        assert not memory.in_combat
        assert memory.get_current_state() is None

    def test_update_turn(self, memory):
        """Test updating turn state."""
        memory.update_turn(
            turn=100,
            hp=20,
            max_hp=30,
            position_x=10,
            position_y=15,
            dungeon_level=2,
            monsters_visible=2,  # Total visible (including pets)
            hostile_monsters_visible=1,  # Hostile only
        )

        assert memory.current_turn == 100
        assert memory.current_level == 2
        assert memory.in_combat  # hostile_monsters_visible > 0

        state = memory.get_current_state()
        assert state is not None
        assert state.hp == 20
        assert state.dungeon_level == 2

    def test_turn_history(self, memory):
        """Test turn history tracking."""
        for i in range(5):
            memory.update_turn(
                turn=i * 10,
                hp=20 - i,
                max_hp=20,
                position_x=10 + i,
                position_y=15,
                dungeon_level=1,
            )

        recent = memory.get_recent_turns(3)
        assert len(recent) == 3
        # Most recent first
        assert recent[0].turn == 40
        assert recent[1].turn == 30
        assert recent[2].turn == 20

    def test_hp_trend_stable(self, memory):
        """Test HP trend detection - stable."""
        for i in range(5):
            memory.update_turn(
                turn=i * 10, hp=20, max_hp=20,
                position_x=10, position_y=15, dungeon_level=1,
            )
        assert memory.get_hp_trend() == "stable"

    def test_hp_trend_decreasing(self, memory):
        """Test HP trend detection - decreasing."""
        for i in range(5):
            memory.update_turn(
                turn=i * 10, hp=20 - i * 3, max_hp=20,
                position_x=10, position_y=15, dungeon_level=1,
            )
        assert memory.get_hp_trend() == "decreasing"

    def test_hp_trend_critical(self, memory):
        """Test HP trend detection - critical."""
        # Need at least 2 turns for trend calculation
        memory.update_turn(
            turn=99, hp=10, max_hp=20,
            position_x=10, position_y=15, dungeon_level=1,
        )
        memory.update_turn(
            turn=100, hp=3, max_hp=20,
            position_x=10, position_y=15, dungeon_level=1,
        )
        assert memory.get_hp_trend() == "critical"


class TestEntityTracking:
    """Tests for entity tracking in working memory."""

    @pytest.fixture
    def memory(self):
        """Create fresh working memory."""
        mem = WorkingMemory()
        mem.update_turn(turn=100, hp=20, max_hp=20, position_x=10, position_y=15, dungeon_level=1)
        return mem

    def test_record_monster_sighting(self, memory):
        """Test recording monster sightings."""
        memory.record_sighting(
            name="grid bug",
            position_x=11,
            position_y=15,
            turn=100,
            entity_type="monster",
            is_hostile=True,
        )

        monsters = memory.get_recent_monsters()
        assert len(monsters) == 1
        assert monsters[0].name == "grid bug"
        assert monsters[0].is_hostile

    def test_record_item_sighting(self, memory):
        """Test recording item sightings."""
        memory.record_sighting(
            name="long sword",
            position_x=12,
            position_y=15,
            turn=100,
            entity_type="item",
        )

        items = memory.get_recent_items()
        assert len(items) == 1
        assert items[0].name == "long sword"

    def test_monster_filter_hostile_only(self, memory):
        """Test filtering for hostile monsters only."""
        memory.record_sighting("grid bug", 11, 15, 100, "monster", is_hostile=True)
        memory.record_sighting("dog", 12, 15, 100, "monster", is_hostile=False)

        hostile = memory.get_recent_monsters(hostile_only=True)
        assert len(hostile) == 1
        assert hostile[0].name == "grid bug"

    def test_sighting_expiry(self, memory):
        """Test that old sightings expire."""
        memory.record_sighting("grid bug", 11, 15, 50, "monster", is_hostile=True)

        # Update to turn 200 (50 turns later)
        memory.update_turn(turn=200, hp=20, max_hp=20, position_x=10, position_y=15, dungeon_level=1)

        # Default expiry is 50 turns, so sighting at turn 50 should be gone
        monsters = memory.get_recent_monsters()
        assert len(monsters) == 0

    def test_get_monster_at(self, memory):
        """Test getting monster at specific position."""
        memory.record_sighting("orc", 15, 20, 100, "monster", is_hostile=True)

        monster = memory.get_monster_at(15, 20)
        assert monster is not None
        assert monster.name == "orc"

        no_monster = memory.get_monster_at(99, 99)
        assert no_monster is None


class TestGoalManagement:
    """Tests for goal management in working memory."""

    @pytest.fixture
    def memory(self):
        """Create fresh working memory."""
        mem = WorkingMemory()
        mem.update_turn(turn=100, hp=20, max_hp=20, position_x=10, position_y=15, dungeon_level=1)
        return mem

    def test_add_goal(self, memory):
        """Test adding a goal."""
        memory.add_goal("explore", priority=5, reason="Find stairs")

        goals = memory.get_goals()
        assert len(goals) == 1
        assert goals[0].goal_type == "explore"
        assert goals[0].priority == 5

    def test_goal_priority_ordering(self, memory):
        """Test that goals are ordered by priority."""
        memory.add_goal("explore", priority=5)
        memory.add_goal("fight", priority=1)
        memory.add_goal("pickup", priority=3)

        goals = memory.get_goals()
        assert goals[0].goal_type == "fight"  # priority 1
        assert goals[1].goal_type == "pickup"  # priority 3
        assert goals[2].goal_type == "explore"  # priority 5

    def test_get_top_goal(self, memory):
        """Test getting highest priority goal."""
        memory.add_goal("explore", priority=5)
        memory.add_goal("fight", priority=1)

        top = memory.get_top_goal()
        assert top is not None
        assert top.goal_type == "fight"

    def test_complete_goal(self, memory):
        """Test completing a goal."""
        memory.add_goal("explore", priority=5)
        goal = memory.get_top_goal()

        memory.complete_goal(goal)

        assert len(memory.get_goals()) == 0

    def test_goal_expiration(self, memory):
        """Test automatic goal expiration."""
        memory.add_goal("fight", priority=1, expires_in_turns=5)

        # Advance time past expiration
        memory.update_turn(turn=110, hp=20, max_hp=20, position_x=10, position_y=15, dungeon_level=1)

        assert memory.get_top_goal() is None

    def test_filter_goals_by_type(self, memory):
        """Test filtering goals by type."""
        memory.add_goal("explore", priority=5)
        memory.add_goal("fight", priority=1)
        memory.add_goal("explore", priority=3)

        explore_goals = memory.get_goals(goal_type="explore")
        assert len(explore_goals) == 2

    def test_clear_goals(self, memory):
        """Test clearing all goals."""
        memory.add_goal("explore", priority=5)
        memory.add_goal("fight", priority=1)

        memory.clear_goals()
        assert len(memory.get_goals()) == 0

    def test_clear_goals_by_type(self, memory):
        """Test clearing goals of specific type."""
        memory.add_goal("explore", priority=5)
        memory.add_goal("fight", priority=1)

        memory.clear_goals(goal_type="explore")

        goals = memory.get_goals()
        assert len(goals) == 1
        assert goals[0].goal_type == "fight"


class TestMessageTracking:
    """Tests for message tracking in working memory."""

    @pytest.fixture
    def memory(self):
        """Create working memory with some messages."""
        mem = WorkingMemory()
        mem.update_turn(turn=100, hp=20, max_hp=20, position_x=10, position_y=15,
                       dungeon_level=1, message="You see a grid bug.")
        mem.update_turn(turn=101, hp=19, max_hp=20, position_x=10, position_y=15,
                       dungeon_level=1, message="The grid bug bites!")
        mem.update_turn(turn=102, hp=20, max_hp=20, position_x=10, position_y=15,
                       dungeon_level=1, message="You kill the grid bug!")
        return mem

    def test_get_recent_messages(self, memory):
        """Test getting recent messages."""
        messages = memory.get_recent_messages(2)
        assert len(messages) == 2
        # Most recent first
        assert "kill" in messages[0][1]

    def test_search_messages(self, memory):
        """Test searching messages by keyword."""
        results = memory.search_messages("grid bug")
        assert len(results) == 3

        kill_results = memory.search_messages("kill")
        assert len(kill_results) == 1


class TestWorkingMemorySummary:
    """Tests for working memory summary."""

    def test_get_summary(self):
        """Test getting memory summary."""
        memory = WorkingMemory()
        memory.update_turn(turn=100, hp=15, max_hp=20, position_x=10, position_y=15,
                          dungeon_level=3, monsters_visible=2, hostile_monsters_visible=2)
        memory.add_goal("fight", priority=1)

        summary = memory.get_summary()

        assert summary["current_turn"] == 100
        assert summary["current_level"] == 3
        assert summary["hp"] == 15
        assert summary["max_hp"] == 20
        assert summary["in_combat"] is True
        assert summary["pending_goals"] == 1
        assert summary["top_goal"] == "fight"

    def test_clear(self):
        """Test clearing all working memory."""
        memory = WorkingMemory()
        memory.update_turn(turn=100, hp=20, max_hp=20, position_x=10, position_y=15, dungeon_level=3)
        memory.add_goal("explore", priority=5)
        memory.record_sighting("orc", 11, 15, 100, "monster", is_hostile=True)

        memory.clear()

        assert memory.current_turn == 0
        assert memory.current_level == 1
        assert memory.get_current_state() is None
        assert len(memory.get_goals()) == 0
        assert len(memory.get_recent_monsters()) == 0
