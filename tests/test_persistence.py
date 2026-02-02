"""Tests for the persistence layer (PostgreSQL implementation)."""

import os
from datetime import datetime

import pytest
from sqlalchemy.ext.asyncio import create_async_engine

from src.persistence.models import RunRecord, TurnRecord
from src.persistence.postgres import PostgresRepository
from src.persistence.tables import metadata

TEST_DB_URL = os.environ.get(
    "NETHACK_TEST_DB_URL",
    "postgresql+asyncpg://nethack:nethack@localhost:5432/nethack_agent_test",
)

# Skip all tests in this module if Postgres is unavailable
pytestmark = pytest.mark.skipif(
    os.environ.get("SKIP_DB_TESTS", "").lower() in ("1", "true"),
    reason="Database tests skipped (SKIP_DB_TESTS=1)",
)


@pytest.fixture
async def engine():
    """Create a test engine with fresh schema."""
    eng = create_async_engine(TEST_DB_URL)
    try:
        async with eng.begin() as conn:
            await conn.run_sync(metadata.drop_all)
            await conn.run_sync(metadata.create_all)
        yield eng
    finally:
        async with eng.begin() as conn:
            await conn.run_sync(metadata.drop_all)
        await eng.dispose()


@pytest.fixture
async def repo(engine):
    """Create a PostgresRepository with clean schema."""
    return PostgresRepository(engine)


@pytest.fixture
def sample_run():
    return RunRecord(
        run_id="test-run-001",
        started_at=datetime(2026, 1, 15, 10, 0, 0),
        model="anthropic/claude-3-haiku",
        provider="openrouter",
        config_snapshot={"max_turns": 100, "temperature": 0.1},
        status="running",
    )


@pytest.fixture
def sample_turn():
    return TurnRecord(
        run_id="test-run-001",
        turn_number=1,
        game_turn=42,
        timestamp=datetime(2026, 1, 15, 10, 0, 5),
        game_screen="  ------\n  |....|\n  |..@.|\n  ------",
        player_x=35,
        player_y=10,
        hp=16,
        max_hp=16,
        dungeon_level=1,
        depth=1,
        xp_level=1,
        score=0,
        hunger="Not Hungry",
        game_message="Welcome to NetHack!",
        llm_reasoning="I should explore east to find the stairs.",
        llm_model="anthropic/claude-3-haiku",
        action_type="execute_code",
        code="nh.move(Direction.E)",
        execution_success=True,
        game_messages=["You see a door."],
        api_calls=[{"method": "move", "args": ["E"], "success": True}],
    )


# === Run tests ===


class TestRunCRUD:
    async def test_create_run(self, repo, sample_run):
        result = await repo.create_run(sample_run)
        assert result.id is not None
        assert result.run_id == "test-run-001"

    async def test_get_run(self, repo, sample_run):
        await repo.create_run(sample_run)
        fetched = await repo.get_run("test-run-001")
        assert fetched is not None
        assert fetched.run_id == "test-run-001"
        assert fetched.model == "anthropic/claude-3-haiku"
        assert fetched.provider == "openrouter"
        assert fetched.config_snapshot == {"max_turns": 100, "temperature": 0.1}
        assert fetched.status == "running"

    async def test_get_run_not_found(self, repo):
        assert await repo.get_run("nonexistent") is None

    async def test_update_run(self, repo, sample_run):
        await repo.create_run(sample_run)
        sample_run.ended_at = datetime(2026, 1, 15, 10, 30, 0)
        sample_run.end_reason = "death"
        sample_run.final_score = 1234
        sample_run.final_game_turns = 500
        sample_run.final_depth = 5
        sample_run.total_agent_turns = 42
        sample_run.status = "stopped"
        await repo.update_run(sample_run)

        fetched = await repo.get_run("test-run-001")
        assert fetched.end_reason == "death"
        assert fetched.final_score == 1234
        assert fetched.final_game_turns == 500
        assert fetched.final_depth == 5
        assert fetched.total_agent_turns == 42
        assert fetched.status == "stopped"

    async def test_list_runs(self, repo):
        for i in range(5):
            await repo.create_run(
                RunRecord(
                    run_id=f"run-{i:03d}",
                    started_at=datetime(2026, 1, 15, 10 + i, 0, 0),
                    model="test-model",
                    provider="test",
                )
            )
        runs = await repo.list_runs(limit=3)
        assert len(runs) == 3
        # Most recent first
        assert runs[0].run_id == "run-004"
        assert runs[1].run_id == "run-003"
        assert runs[2].run_id == "run-002"

    async def test_list_runs_offset(self, repo):
        for i in range(5):
            await repo.create_run(
                RunRecord(
                    run_id=f"run-{i:03d}",
                    started_at=datetime(2026, 1, 15, 10 + i, 0, 0),
                    model="test-model",
                    provider="test",
                )
            )
        runs = await repo.list_runs(limit=2, offset=3)
        assert len(runs) == 2
        assert runs[0].run_id == "run-001"
        assert runs[1].run_id == "run-000"

    async def test_user_id_and_visibility(self, repo):
        run = RunRecord(
            run_id="user-run-001",
            started_at=datetime(2026, 1, 15, 10, 0, 0),
            model="test-model",
            provider="test",
            user_id=None,
            visibility="public",
        )
        await repo.create_run(run)
        fetched = await repo.get_run("user-run-001")
        assert fetched.user_id is None
        assert fetched.visibility == "public"


# === Turn tests ===


def _make_turn(run_id: str, turn_number: int, **kwargs) -> TurnRecord:
    """Helper to create a TurnRecord with minimal required fields."""
    defaults = dict(
        run_id=run_id,
        turn_number=turn_number,
        game_turn=turn_number * 10,
        timestamp=datetime(2026, 1, 15, 10, 0, turn_number),
        game_screen=f"screen-{turn_number}",
        player_x=35,
        player_y=10,
        hp=16,
        max_hp=16,
        dungeon_level=1,
        depth=1,
        xp_level=1,
        score=0,
        hunger="Not Hungry",
        game_message="",
        llm_reasoning=f"reasoning-{turn_number}",
        llm_model="test-model",
        action_type="execute_code",
    )
    defaults.update(kwargs)
    return TurnRecord(**defaults)


class TestTurnCRUD:
    async def test_save_turn(self, repo, sample_run, sample_turn):
        await repo.create_run(sample_run)
        result = await repo.save_turn(sample_turn)
        assert result.id is not None

    async def test_get_turn(self, repo, sample_run, sample_turn):
        await repo.create_run(sample_run)
        await repo.save_turn(sample_turn)

        fetched = await repo.get_turn("test-run-001", 1)
        assert fetched is not None
        assert fetched.turn_number == 1
        assert fetched.game_turn == 42
        assert fetched.game_screen == "  ------\n  |....|\n  |..@.|\n  ------"
        assert fetched.player_x == 35
        assert fetched.player_y == 10
        assert fetched.hp == 16
        assert fetched.max_hp == 16
        assert fetched.llm_reasoning == "I should explore east to find the stairs."
        assert fetched.action_type == "execute_code"
        assert fetched.code == "nh.move(Direction.E)"
        assert fetched.execution_success is True
        assert fetched.game_messages == ["You see a door."]
        assert fetched.api_calls == [{"method": "move", "args": ["E"], "success": True}]

    async def test_get_turn_not_found(self, repo, sample_run):
        await repo.create_run(sample_run)
        assert await repo.get_turn("test-run-001", 999) is None

    async def test_get_turns(self, repo, sample_run):
        await repo.create_run(sample_run)
        for i in range(1, 6):
            await repo.save_turn(_make_turn("test-run-001", i))

        turns = await repo.get_turns("test-run-001")
        assert len(turns) == 5
        assert turns[0].turn_number == 1
        assert turns[4].turn_number == 5

    async def test_get_turns_after(self, repo, sample_run):
        await repo.create_run(sample_run)
        for i in range(1, 6):
            await repo.save_turn(_make_turn("test-run-001", i))

        turns = await repo.get_turns("test-run-001", after_turn=3)
        assert len(turns) == 2
        assert turns[0].turn_number == 4
        assert turns[1].turn_number == 5

    async def test_get_turns_limit(self, repo, sample_run):
        await repo.create_run(sample_run)
        for i in range(1, 11):
            await repo.save_turn(_make_turn("test-run-001", i))

        turns = await repo.get_turns("test-run-001", limit=3)
        assert len(turns) == 3

    async def test_get_latest_turn(self, repo, sample_run):
        await repo.create_run(sample_run)
        for i in range(1, 4):
            await repo.save_turn(_make_turn("test-run-001", i))

        latest = await repo.get_latest_turn("test-run-001")
        assert latest is not None
        assert latest.turn_number == 3

    async def test_get_latest_turn_empty(self, repo, sample_run):
        await repo.create_run(sample_run)
        assert await repo.get_latest_turn("test-run-001") is None

    async def test_count_turns(self, repo, sample_run):
        await repo.create_run(sample_run)
        assert await repo.count_turns("test-run-001") == 0

        for i in range(1, 4):
            await repo.save_turn(_make_turn("test-run-001", i))

        assert await repo.count_turns("test-run-001") == 3

    async def test_duplicate_turn_rejected(self, repo, sample_run, sample_turn):
        await repo.create_run(sample_run)
        await repo.save_turn(sample_turn)
        with pytest.raises(Exception):
            await repo.save_turn(sample_turn)


# === Serialization tests ===


class TestSerialization:
    def test_turn_to_dict(self, sample_turn):
        d = sample_turn.to_dict()
        assert d["run_id"] == "test-run-001"
        assert d["turn_number"] == 1
        assert d["timestamp"] == "2026-01-15T10:00:05"
        assert d["game_messages"] == ["You see a door."]
        assert d["api_calls"] == [{"method": "move", "args": ["E"], "success": True}]

    def test_run_to_dict(self, sample_run):
        d = sample_run.to_dict()
        assert d["run_id"] == "test-run-001"
        assert d["started_at"] == "2026-01-15T10:00:00"
        assert d["ended_at"] is None
        assert d["config_snapshot"] == {"max_turns": 100, "temperature": 0.1}
        assert d["user_id"] is None
        assert d["visibility"] == "public"

    async def test_nullable_fields_round_trip(self, repo, sample_run):
        await repo.create_run(sample_run)
        turn = TurnRecord(
            run_id="test-run-001",
            turn_number=1,
            game_turn=10,
            timestamp=datetime(2026, 1, 15, 10, 0, 1),
            game_screen="screen",
            player_x=0,
            player_y=0,
            hp=10,
            max_hp=10,
            dungeon_level=1,
            depth=1,
            xp_level=1,
            score=0,
            hunger="Not Hungry",
            game_message="",
            llm_reasoning="",
            llm_model="test",
            action_type="execute_code",
            # All nullable fields left as defaults
        )
        await repo.save_turn(turn)
        fetched = await repo.get_turn("test-run-001", 1)
        assert fetched.code is None
        assert fetched.skill_name is None
        assert fetched.execution_error is None
        assert fetched.llm_prompt_tokens is None
        assert fetched.game_messages == []
        assert fetched.api_calls == []
