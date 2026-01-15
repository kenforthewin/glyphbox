"""Tests for skill data models."""

import pytest
from datetime import datetime, timedelta

from src.skills.models import (
    GameStateSnapshot,
    Skill,
    SkillCategory,
    SkillExecution,
    SkillMetadata,
    SkillStatistics,
)


class TestSkillCategory:
    """Tests for SkillCategory enum."""

    def test_from_string_valid(self):
        """Test converting valid strings to categories."""
        assert SkillCategory.from_string("exploration") == SkillCategory.EXPLORATION
        assert SkillCategory.from_string("combat") == SkillCategory.COMBAT
        assert SkillCategory.from_string("resource") == SkillCategory.RESOURCE
        assert SkillCategory.from_string("navigation") == SkillCategory.NAVIGATION
        assert SkillCategory.from_string("interaction") == SkillCategory.INTERACTION
        assert SkillCategory.from_string("utility") == SkillCategory.UTILITY
        assert SkillCategory.from_string("custom") == SkillCategory.CUSTOM

    def test_from_string_case_insensitive(self):
        """Test that category conversion is case-insensitive."""
        assert SkillCategory.from_string("EXPLORATION") == SkillCategory.EXPLORATION
        assert SkillCategory.from_string("Combat") == SkillCategory.COMBAT
        assert SkillCategory.from_string("RESOURCE") == SkillCategory.RESOURCE

    def test_from_string_invalid_returns_custom(self):
        """Test that invalid strings return CUSTOM category."""
        assert SkillCategory.from_string("unknown") == SkillCategory.CUSTOM
        assert SkillCategory.from_string("invalid") == SkillCategory.CUSTOM
        assert SkillCategory.from_string("") == SkillCategory.CUSTOM


class TestSkillMetadata:
    """Tests for SkillMetadata dataclass."""

    def test_default_values(self):
        """Test default values for metadata."""
        meta = SkillMetadata()
        assert meta.description == ""
        assert meta.category == SkillCategory.CUSTOM
        assert meta.stops_when == []
        assert meta.author == "agent"
        assert meta.version == 1
        assert meta.created_at is None
        assert meta.updated_at is None
        assert meta.tags == []

    def test_custom_values(self):
        """Test creating metadata with custom values."""
        now = datetime.now()
        meta = SkillMetadata(
            description="Test skill",
            category=SkillCategory.COMBAT,
            stops_when=["target_dead", "low_hp"],
            author="human",
            version=2,
            created_at=now,
            updated_at=now,
            tags=["combat", "melee"],
        )
        assert meta.description == "Test skill"
        assert meta.category == SkillCategory.COMBAT
        assert meta.stops_when == ["target_dead", "low_hp"]
        assert meta.author == "human"
        assert meta.version == 2
        assert meta.created_at == now
        assert meta.tags == ["combat", "melee"]

    def test_to_dict(self):
        """Test converting metadata to dictionary."""
        now = datetime.now()
        meta = SkillMetadata(
            description="Test",
            category=SkillCategory.EXPLORATION,
            stops_when=["done"],
            created_at=now,
        )
        d = meta.to_dict()
        assert d["description"] == "Test"
        assert d["category"] == "exploration"
        assert d["stops_when"] == ["done"]
        assert d["created_at"] == now.isoformat()

    def test_from_dict(self):
        """Test creating metadata from dictionary."""
        now = datetime.now()
        d = {
            "description": "Test",
            "category": "combat",
            "stops_when": ["done"],
            "author": "human",
            "version": 3,
            "created_at": now.isoformat(),
            "tags": ["test"],
        }
        meta = SkillMetadata.from_dict(d)
        assert meta.description == "Test"
        assert meta.category == SkillCategory.COMBAT
        assert meta.stops_when == ["done"]
        assert meta.author == "human"
        assert meta.version == 3
        assert meta.created_at == now
        assert meta.tags == ["test"]

    def test_from_dict_minimal(self):
        """Test creating metadata from minimal dictionary."""
        meta = SkillMetadata.from_dict({})
        assert meta.description == ""
        assert meta.category == SkillCategory.CUSTOM
        assert meta.stops_when == []


class TestSkill:
    """Tests for Skill dataclass."""

    def test_basic_creation(self):
        """Test creating a basic skill."""
        code = "async def test_skill(nh, **params): pass"
        skill = Skill(name="test_skill", code=code)
        assert skill.name == "test_skill"
        assert skill.code == code
        assert skill.category == SkillCategory.CUSTOM
        assert skill.description == ""
        assert skill.file_path is None

    def test_with_metadata(self):
        """Test creating skill with metadata."""
        meta = SkillMetadata(
            description="A test skill",
            category=SkillCategory.COMBAT,
        )
        skill = Skill(
            name="combat_skill",
            code="async def combat_skill(nh): pass",
            metadata=meta,
        )
        assert skill.category == SkillCategory.COMBAT
        assert skill.description == "A test skill"

    def test_to_dict(self):
        """Test converting skill to dictionary."""
        skill = Skill(
            name="test",
            code="async def test(nh): pass",
            file_path="/path/to/skill.py",
        )
        d = skill.to_dict()
        assert d["name"] == "test"
        assert d["code"] == "async def test(nh): pass"
        assert d["file_path"] == "/path/to/skill.py"
        assert "metadata" in d

    def test_from_dict(self):
        """Test creating skill from dictionary."""
        d = {
            "name": "test",
            "code": "async def test(nh): pass",
            "metadata": {
                "description": "Test desc",
                "category": "exploration",
            },
            "file_path": "/path/test.py",
        }
        skill = Skill.from_dict(d)
        assert skill.name == "test"
        assert skill.code == "async def test(nh): pass"
        assert skill.description == "Test desc"
        assert skill.category == SkillCategory.EXPLORATION
        assert skill.file_path == "/path/test.py"


class TestGameStateSnapshot:
    """Tests for GameStateSnapshot dataclass."""

    def test_creation(self):
        """Test creating a game state snapshot."""
        snap = GameStateSnapshot(
            turn=100,
            hp=20,
            max_hp=30,
            dungeon_level=3,
            position_x=40,
            position_y=10,
            gold=500,
            xp_level=5,
            monsters_visible=2,
            monsters_adjacent=1,
        )
        assert snap.turn == 100
        assert snap.hp == 20
        assert snap.max_hp == 30
        assert snap.dungeon_level == 3
        assert snap.position_x == 40
        assert snap.position_y == 10
        assert snap.gold == 500
        assert snap.xp_level == 5
        assert snap.monsters_visible == 2
        assert snap.monsters_adjacent == 1

    def test_default_monster_counts(self):
        """Test default monster counts are zero."""
        snap = GameStateSnapshot(
            turn=1, hp=10, max_hp=10, dungeon_level=1,
            position_x=10, position_y=10, gold=0, xp_level=1,
        )
        assert snap.monsters_visible == 0
        assert snap.monsters_adjacent == 0

    def test_to_dict(self):
        """Test converting snapshot to dictionary."""
        snap = GameStateSnapshot(
            turn=50, hp=15, max_hp=20, dungeon_level=2,
            position_x=30, position_y=15, gold=100, xp_level=3,
        )
        d = snap.to_dict()
        assert d["turn"] == 50
        assert d["hp"] == 15
        assert d["gold"] == 100

    def test_from_dict(self):
        """Test creating snapshot from dictionary."""
        d = {
            "turn": 100,
            "hp": 20,
            "max_hp": 30,
            "dungeon_level": 3,
            "position_x": 40,
            "position_y": 10,
            "gold": 500,
            "xp_level": 5,
        }
        snap = GameStateSnapshot.from_dict(d)
        assert snap.turn == 100
        assert snap.hp == 20


class TestSkillExecution:
    """Tests for SkillExecution dataclass."""

    def test_basic_creation(self):
        """Test creating a basic execution record."""
        now = datetime.now()
        exec_record = SkillExecution(
            skill_name="test_skill",
            params={"max_steps": 10},
            started_at=now,
        )
        assert exec_record.skill_name == "test_skill"
        assert exec_record.params == {"max_steps": 10}
        assert exec_record.started_at == now
        assert exec_record.ended_at is None
        assert exec_record.success is False
        assert exec_record.stopped_reason == ""
        assert exec_record.error is None

    def test_complete_execution(self):
        """Test a complete execution record."""
        start = datetime.now()
        end = start + timedelta(seconds=5)
        exec_record = SkillExecution(
            skill_name="explore",
            params={},
            started_at=start,
            ended_at=end,
            success=True,
            stopped_reason="fully_explored",
            result_data={"tiles_explored": 50},
            actions_taken=30,
            turns_elapsed=25,
        )
        assert exec_record.success is True
        assert exec_record.stopped_reason == "fully_explored"
        assert exec_record.actions_taken == 30
        assert exec_record.turns_elapsed == 25

    def test_duration_seconds(self):
        """Test calculating execution duration."""
        start = datetime.now()
        end = start + timedelta(seconds=10)
        exec_record = SkillExecution(
            skill_name="test",
            params={},
            started_at=start,
            ended_at=end,
        )
        assert exec_record.duration_seconds == 10.0

    def test_duration_seconds_not_ended(self):
        """Test duration when execution hasn't ended."""
        exec_record = SkillExecution(
            skill_name="test",
            params={},
            started_at=datetime.now(),
        )
        assert exec_record.duration_seconds == 0.0

    def test_to_dict(self):
        """Test converting execution to dictionary."""
        now = datetime.now()
        exec_record = SkillExecution(
            skill_name="test",
            params={"x": 1},
            started_at=now,
            success=True,
            stopped_reason="done",
        )
        d = exec_record.to_dict()
        assert d["skill_name"] == "test"
        assert d["params"] == {"x": 1}
        assert d["success"] is True
        assert d["stopped_reason"] == "done"

    def test_from_dict(self):
        """Test creating execution from dictionary."""
        now = datetime.now()
        d = {
            "skill_name": "test",
            "params": {"y": 2},
            "started_at": now.isoformat(),
            "ended_at": now.isoformat(),
            "success": True,
            "stopped_reason": "complete",
            "actions_taken": 5,
            "turns_elapsed": 3,
        }
        exec_record = SkillExecution.from_dict(d)
        assert exec_record.skill_name == "test"
        assert exec_record.success is True
        assert exec_record.actions_taken == 5

    def test_with_state_snapshots(self):
        """Test execution with state snapshots."""
        before = GameStateSnapshot(
            turn=100, hp=20, max_hp=20, dungeon_level=1,
            position_x=10, position_y=10, gold=0, xp_level=1,
        )
        after = GameStateSnapshot(
            turn=110, hp=15, max_hp=20, dungeon_level=1,
            position_x=15, position_y=12, gold=50, xp_level=1,
        )
        exec_record = SkillExecution(
            skill_name="explore",
            params={},
            started_at=datetime.now(),
            state_before=before,
            state_after=after,
        )
        assert exec_record.state_before.turn == 100
        assert exec_record.state_after.turn == 110


class TestSkillStatistics:
    """Tests for SkillStatistics dataclass."""

    def test_default_values(self):
        """Test default values for statistics."""
        stats = SkillStatistics(skill_name="test")
        assert stats.skill_name == "test"
        assert stats.total_executions == 0
        assert stats.successful_executions == 0
        assert stats.failed_executions == 0
        assert stats.total_actions == 0
        assert stats.total_turns == 0
        assert stats.stop_reasons == {}
        assert stats.success_rate == 0.0

    def test_success_rate(self):
        """Test success rate calculation."""
        stats = SkillStatistics(
            skill_name="test",
            total_executions=10,
            successful_executions=7,
        )
        assert stats.success_rate == 0.7

    def test_success_rate_zero_executions(self):
        """Test success rate with no executions."""
        stats = SkillStatistics(skill_name="test")
        assert stats.success_rate == 0.0

    def test_record_execution_success(self):
        """Test recording a successful execution."""
        stats = SkillStatistics(skill_name="test")
        exec_record = SkillExecution(
            skill_name="test",
            params={},
            started_at=datetime.now(),
            ended_at=datetime.now(),
            success=True,
            stopped_reason="complete",
            actions_taken=10,
            turns_elapsed=8,
        )
        stats.record_execution(exec_record)

        assert stats.total_executions == 1
        assert stats.successful_executions == 1
        assert stats.failed_executions == 0
        assert stats.total_actions == 10
        assert stats.total_turns == 8
        assert stats.stop_reasons == {"complete": 1}
        assert stats.success_rate == 1.0

    def test_record_execution_failure(self):
        """Test recording a failed execution."""
        stats = SkillStatistics(skill_name="test")
        exec_record = SkillExecution(
            skill_name="test",
            params={},
            started_at=datetime.now(),
            success=False,
            stopped_reason="error",
            actions_taken=5,
            turns_elapsed=3,
        )
        stats.record_execution(exec_record)

        assert stats.total_executions == 1
        assert stats.successful_executions == 0
        assert stats.failed_executions == 1
        assert stats.success_rate == 0.0

    def test_record_multiple_executions(self):
        """Test recording multiple executions."""
        stats = SkillStatistics(skill_name="test")

        # Record 3 successes
        for _ in range(3):
            exec_record = SkillExecution(
                skill_name="test",
                params={},
                started_at=datetime.now(),
                success=True,
                stopped_reason="complete",
                actions_taken=10,
                turns_elapsed=5,
            )
            stats.record_execution(exec_record)

        # Record 2 failures
        for _ in range(2):
            exec_record = SkillExecution(
                skill_name="test",
                params={},
                started_at=datetime.now(),
                success=False,
                stopped_reason="error",
                actions_taken=5,
                turns_elapsed=2,
            )
            stats.record_execution(exec_record)

        assert stats.total_executions == 5
        assert stats.successful_executions == 3
        assert stats.failed_executions == 2
        assert stats.success_rate == 0.6
        assert stats.stop_reasons == {"complete": 3, "error": 2}
        assert stats.avg_actions_per_execution == (30 + 10) / 5
        assert stats.avg_turns_per_execution == (15 + 4) / 5

    def test_to_dict(self):
        """Test converting statistics to dictionary."""
        stats = SkillStatistics(
            skill_name="test",
            total_executions=10,
            successful_executions=7,
            stop_reasons={"done": 5, "error": 2},
        )
        d = stats.to_dict()
        assert d["skill_name"] == "test"
        assert d["total_executions"] == 10
        assert d["successful_executions"] == 7
        assert d["stop_reasons"] == {"done": 5, "error": 2}

    def test_from_dict(self):
        """Test creating statistics from dictionary."""
        now = datetime.now()
        d = {
            "skill_name": "test",
            "total_executions": 20,
            "successful_executions": 15,
            "failed_executions": 5,
            "total_actions": 200,
            "total_turns": 150,
            "stop_reasons": {"done": 15, "error": 5},
            "avg_actions_per_execution": 10.0,
            "avg_turns_per_execution": 7.5,
            "last_executed": now.isoformat(),
        }
        stats = SkillStatistics.from_dict(d)
        assert stats.skill_name == "test"
        assert stats.total_executions == 20
        assert stats.successful_executions == 15
        assert stats.stop_reasons == {"done": 15, "error": 5}
        assert stats.last_executed == now
