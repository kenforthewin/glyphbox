"""Tests for ProcrastinateBackend."""

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.persistence.models import RunRecord
from src.web.procrastinate_backend import ProcrastinateBackend
from src.web.run_config import RunConfig


def _make_config(run_id: str = "run-1", user_id: int = 10) -> RunConfig:
    return RunConfig(
        run_id=run_id,
        user_id=user_id,
        model="test/model",
        character="random",
        temperature=0.1,
        reasoning="none",
        max_turns=100,
    )


def _make_run_record(run_id: str, status: str = "running", user_id: int = 10) -> RunRecord:
    return RunRecord(
        run_id=run_id,
        started_at=datetime.now(),
        status=status,
        user_id=user_id,
    )


class TestProcrastinateBackend:
    @pytest.fixture
    def mock_repo(self):
        repo = AsyncMock()
        repo.create_run = AsyncMock()
        repo.get_run = AsyncMock(return_value=None)
        repo.update_run = AsyncMock()
        return repo

    @pytest.fixture
    def mock_proc_app(self):
        return MagicMock()

    @pytest.fixture
    def backend(self, mock_proc_app, mock_repo):
        return ProcrastinateBackend(mock_proc_app, mock_repo)

    @pytest.mark.asyncio
    async def test_start_run_creates_placeholder_and_enqueues(self, backend, mock_repo):
        config = _make_config(run_id="run-abc", user_id=42)

        # Mock the task import that happens inside start_run
        mock_task = MagicMock()
        mock_defer = AsyncMock()
        mock_task.configure.return_value.defer_async = mock_defer

        with patch.dict(
            "sys.modules",
            {"src.worker.tasks": MagicMock(run_agent_task=mock_task)},
        ):
            await backend.start_run("run-abc", config)

        # Placeholder run created
        mock_repo.create_run.assert_awaited_once()
        created_run = mock_repo.create_run.call_args[0][0]
        assert created_run.run_id == "run-abc"
        assert created_run.status == "starting"
        assert created_run.user_id == 42

        # Job enqueued
        mock_defer.assert_awaited_once()
        call_kwargs = mock_defer.call_args[1]
        assert call_kwargs["run_id"] == "run-abc"
        assert call_kwargs["user_id"] == 42
        assert call_kwargs["model"] == "test/model"

    @pytest.mark.asyncio
    async def test_start_run_tracks_as_active(self, backend, mock_repo):
        config = _make_config(run_id="run-abc")

        mock_task = MagicMock()
        mock_task.configure.return_value.defer_async = AsyncMock()

        with patch.dict(
            "sys.modules",
            {"src.worker.tasks": MagicMock(run_agent_task=mock_task)},
        ):
            await backend.start_run("run-abc", config)

        assert backend.is_running("run-abc")
        assert "run-abc" in backend.get_active_run_ids()

    @pytest.mark.asyncio
    async def test_stop_run_updates_status(self, backend, mock_repo):
        backend._active_runs.add("run-abc")
        run = _make_run_record("run-abc", status="running")
        mock_repo.get_run = AsyncMock(return_value=run)

        await backend.stop_run("run-abc")

        mock_repo.update_run.assert_awaited_once()
        assert run.status == "stopped"
        assert run.end_reason == "stopped by user"
        assert run.ended_at is not None
        assert not backend.is_running("run-abc")

    @pytest.mark.asyncio
    async def test_stop_run_noop_for_unknown(self, backend, mock_repo):
        mock_repo.get_run = AsyncMock(return_value=None)
        await backend.stop_run("nonexistent")
        mock_repo.update_run.assert_not_awaited()

    def test_is_running_false_for_unknown(self, backend):
        assert not backend.is_running("nonexistent")

    def test_get_active_run_ids_empty(self, backend):
        assert backend.get_active_run_ids() == []

    @pytest.mark.asyncio
    async def test_check_completed_runs_cleans_up(self, backend, mock_repo):
        backend._active_runs.add("run-done")
        backend._active_runs.add("run-still-going")

        async def fake_get_run(run_id):
            if run_id == "run-done":
                return _make_run_record("run-done", status="stopped")
            return _make_run_record("run-still-going", status="running")

        mock_repo.get_run = AsyncMock(side_effect=fake_get_run)

        await backend._check_completed_runs()

        assert not backend.is_running("run-done")
        assert backend.is_running("run-still-going")

    @pytest.mark.asyncio
    async def test_recover_state(self, backend):
        runs = [
            _make_run_record("run-1", status="running", user_id=10),
            _make_run_record("run-2", status="starting", user_id=20),
        ]
        await backend.recover_state(runs)

        assert backend.is_running("run-1")
        assert backend.is_running("run-2")
        assert len(backend.get_active_run_ids()) == 2

    @pytest.mark.asyncio
    async def test_recover_state_clears_previous(self, backend):
        backend._active_runs.add("old-run")
        runs = [_make_run_record("run-1", status="running")]
        await backend.recover_state(runs)

        assert not backend.is_running("old-run")
        assert backend.is_running("run-1")
