"""Tests for skill statistics storage."""

import pytest
import tempfile
from datetime import datetime
from pathlib import Path

from src.skills.statistics import StatisticsStore
from src.skills.models import GameStateSnapshot, SkillExecution


@pytest.fixture
def temp_db():
    """Create a temporary database file."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir) / "test_stats.db"


@pytest.fixture
def store(temp_db):
    """Create an initialized statistics store."""
    s = StatisticsStore(str(temp_db))
    s.initialize()
    yield s
    s.close()


@pytest.fixture
def sample_execution():
    """Create a sample execution record."""
    return SkillExecution(
        skill_name="cautious_explore",
        params={"max_steps": 50},
        started_at=datetime.now(),
        ended_at=datetime.now(),
        success=True,
        stopped_reason="fully_explored",
        result_data={"tiles_explored": 100},
        actions_taken=45,
        turns_elapsed=40,
    )


@pytest.fixture
def execution_with_state():
    """Create an execution with state snapshots."""
    before = GameStateSnapshot(
        turn=100, hp=20, max_hp=20, dungeon_level=1,
        position_x=10, position_y=10, gold=0, xp_level=1,
    )
    after = GameStateSnapshot(
        turn=140, hp=18, max_hp=20, dungeon_level=1,
        position_x=25, position_y=15, gold=50, xp_level=1,
    )
    return SkillExecution(
        skill_name="explore",
        params={},
        started_at=datetime.now(),
        ended_at=datetime.now(),
        success=True,
        stopped_reason="done",
        actions_taken=40,
        turns_elapsed=40,
        state_before=before,
        state_after=after,
    )


class TestStatisticsStoreInitialization:
    """Tests for store initialization."""

    def test_init_creates_database(self, temp_db):
        """Test that initialization creates the database file."""
        store = StatisticsStore(str(temp_db))
        store.initialize()

        assert temp_db.exists()
        store.close()

    def test_init_creates_parent_directory(self):
        """Test that initialization creates parent directory if needed."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "subdir" / "stats.db"
            store = StatisticsStore(str(db_path))
            store.initialize()

            assert db_path.parent.exists()
            assert db_path.exists()
            store.close()

    def test_context_manager(self, temp_db):
        """Test using store as context manager."""
        with StatisticsStore(str(temp_db)) as store:
            # Store should be initialized
            stats = store.get_all_statistics()
            assert stats == []

    def test_double_initialization(self, temp_db):
        """Test that double initialization doesn't cause issues."""
        store = StatisticsStore(str(temp_db))
        store.initialize()
        store.initialize()  # Should not raise
        store.close()


class TestRecordExecution:
    """Tests for recording executions."""

    def test_record_execution(self, store, sample_execution):
        """Test recording a basic execution."""
        row_id = store.record_execution(sample_execution)

        assert row_id is not None
        assert row_id > 0

    def test_record_execution_with_episode(self, store, sample_execution):
        """Test recording execution with episode ID."""
        row_id = store.record_execution(sample_execution, episode_id="ep_001")

        assert row_id > 0

    def test_record_updates_statistics(self, store, sample_execution):
        """Test that recording updates aggregated statistics."""
        store.record_execution(sample_execution)

        stats = store.get_statistics("cautious_explore")
        assert stats is not None
        assert stats.total_executions == 1
        assert stats.successful_executions == 1
        assert stats.total_actions == 45
        assert stats.total_turns == 40

    def test_record_multiple_executions(self, store):
        """Test recording multiple executions."""
        for i in range(5):
            exec_record = SkillExecution(
                skill_name="test_skill",
                params={},
                started_at=datetime.now(),
                ended_at=datetime.now(),
                success=(i % 2 == 0),  # Alternating success/failure
                stopped_reason="done" if i % 2 == 0 else "error",
                actions_taken=10,
                turns_elapsed=8,
            )
            store.record_execution(exec_record)

        stats = store.get_statistics("test_skill")
        assert stats.total_executions == 5
        assert stats.successful_executions == 3  # i=0,2,4
        assert stats.failed_executions == 2  # i=1,3

    def test_record_with_state_snapshots(self, store, execution_with_state):
        """Test recording execution with state snapshots."""
        row_id = store.record_execution(execution_with_state)
        assert row_id > 0

        # Retrieve and check
        executions = store.get_executions(skill_name="explore")
        assert len(executions) == 1
        assert executions[0].state_before is not None
        assert executions[0].state_before.turn == 100
        assert executions[0].state_after is not None
        assert executions[0].state_after.turn == 140


class TestGetStatistics:
    """Tests for retrieving statistics."""

    def test_get_statistics_existing(self, store, sample_execution):
        """Test getting statistics for existing skill."""
        store.record_execution(sample_execution)

        stats = store.get_statistics("cautious_explore")
        assert stats is not None
        assert stats.skill_name == "cautious_explore"

    def test_get_statistics_nonexistent(self, store):
        """Test getting statistics for nonexistent skill."""
        stats = store.get_statistics("nonexistent")
        assert stats is None

    def test_get_all_statistics(self, store):
        """Test getting statistics for all skills."""
        # Record executions for different skills
        for skill in ["skill_a", "skill_b", "skill_c"]:
            exec_record = SkillExecution(
                skill_name=skill,
                params={},
                started_at=datetime.now(),
                ended_at=datetime.now(),
                success=True,
                stopped_reason="done",
                actions_taken=10,
                turns_elapsed=5,
            )
            store.record_execution(exec_record)

        all_stats = store.get_all_statistics()
        assert len(all_stats) == 3
        skill_names = {s.skill_name for s in all_stats}
        assert skill_names == {"skill_a", "skill_b", "skill_c"}

    def test_statistics_stop_reasons(self, store):
        """Test that stop reasons are tracked correctly."""
        for reason in ["done", "done", "error", "timeout"]:
            exec_record = SkillExecution(
                skill_name="test",
                params={},
                started_at=datetime.now(),
                ended_at=datetime.now(),
                success=(reason == "done"),
                stopped_reason=reason,
                actions_taken=1,
                turns_elapsed=1,
            )
            store.record_execution(exec_record)

        stats = store.get_statistics("test")
        assert stats.stop_reasons["done"] == 2
        assert stats.stop_reasons["error"] == 1
        assert stats.stop_reasons["timeout"] == 1


class TestGetExecutions:
    """Tests for retrieving execution history."""

    def test_get_executions_all(self, store, sample_execution):
        """Test getting all executions."""
        store.record_execution(sample_execution)
        store.record_execution(sample_execution)

        executions = store.get_executions()
        assert len(executions) == 2

    def test_get_executions_by_skill(self, store):
        """Test filtering executions by skill name."""
        for skill in ["skill_a", "skill_b", "skill_a"]:
            exec_record = SkillExecution(
                skill_name=skill,
                params={},
                started_at=datetime.now(),
                success=True,
                stopped_reason="done",
            )
            store.record_execution(exec_record)

        skill_a_execs = store.get_executions(skill_name="skill_a")
        assert len(skill_a_execs) == 2

        skill_b_execs = store.get_executions(skill_name="skill_b")
        assert len(skill_b_execs) == 1

    def test_get_executions_by_episode(self, store, sample_execution):
        """Test filtering executions by episode ID."""
        store.record_execution(sample_execution, episode_id="ep_001")
        store.record_execution(sample_execution, episode_id="ep_001")
        store.record_execution(sample_execution, episode_id="ep_002")

        ep1_execs = store.get_executions(episode_id="ep_001")
        assert len(ep1_execs) == 2

        ep2_execs = store.get_executions(episode_id="ep_002")
        assert len(ep2_execs) == 1

    def test_get_executions_limit(self, store, sample_execution):
        """Test limiting number of returned executions."""
        for _ in range(10):
            store.record_execution(sample_execution)

        executions = store.get_executions(limit=5)
        assert len(executions) == 5

    def test_get_executions_order(self, store):
        """Test that executions are returned most recent first."""
        for i in range(3):
            exec_record = SkillExecution(
                skill_name=f"skill_{i}",
                params={"order": i},
                started_at=datetime.now(),
                success=True,
                stopped_reason="done",
            )
            store.record_execution(exec_record)

        executions = store.get_executions(limit=3)
        # Most recent should be first (skill_2)
        assert executions[0].skill_name == "skill_2"


class TestGenerateReport:
    """Tests for generating statistics reports."""

    def test_generate_report_empty(self, store):
        """Test generating report with no data."""
        report = store.generate_report()

        assert report["overall"]["total_executions"] == 0
        assert report["skills"] == []
        assert report["top_stop_reasons"] == []

    def test_generate_report_with_data(self, store, sample_execution):
        """Test generating report with execution data."""
        # Record several executions
        for _ in range(5):
            store.record_execution(sample_execution)

        # Record some failures too
        failed = SkillExecution(
            skill_name="failing_skill",
            params={},
            started_at=datetime.now(),
            ended_at=datetime.now(),
            success=False,
            stopped_reason="error",
            actions_taken=5,
            turns_elapsed=3,
        )
        for _ in range(3):
            store.record_execution(failed)

        report = store.generate_report()

        assert report["overall"]["total_executions"] == 8
        assert report["overall"]["successful_executions"] == 5
        assert report["overall"]["unique_skills"] == 2

        # Check skills section
        assert len(report["skills"]) == 2

        # Check stop reasons
        stop_reasons_dict = dict(report["top_stop_reasons"])
        assert stop_reasons_dict.get("fully_explored") == 5
        assert stop_reasons_dict.get("error") == 3

    def test_generate_report_success_rate(self, store):
        """Test that report calculates success rate correctly."""
        for success in [True, True, True, False, False]:
            exec_record = SkillExecution(
                skill_name="test",
                params={},
                started_at=datetime.now(),
                success=success,
                stopped_reason="done" if success else "error",
            )
            store.record_execution(exec_record)

        report = store.generate_report()

        expected_rate = 3 / 5
        assert report["overall"]["success_rate"] == expected_rate


class TestAutoConnection:
    """Tests for automatic connection handling."""

    def test_auto_connect_on_operation(self, temp_db):
        """Test that store auto-connects when needed."""
        store = StatisticsStore(str(temp_db))
        # Don't call initialize explicitly

        # This should auto-initialize
        stats = store.get_all_statistics()
        assert stats == []

        store.close()

    def test_close_and_reopen(self, temp_db):
        """Test closing and reopening connection."""
        store = StatisticsStore(str(temp_db))
        store.initialize()

        # Record something
        exec_record = SkillExecution(
            skill_name="test",
            params={},
            started_at=datetime.now(),
            success=True,
            stopped_reason="done",
        )
        store.record_execution(exec_record)
        store.close()

        # Reopen
        store2 = StatisticsStore(str(temp_db))
        store2.initialize()

        # Data should persist
        stats = store2.get_statistics("test")
        assert stats is not None
        assert stats.total_executions == 1

        store2.close()
