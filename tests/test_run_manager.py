"""Tests for RunManager concurrency limits and ownership tracking."""

from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException

from src.web.run_config import RunConfig
from src.web.run_manager import RunManager

# === Helpers ===


def _make_config(model: str = "test/model") -> RunConfig:
    """Create a RunConfig for testing."""
    return RunConfig(
        model=model,
        character="random",
        temperature=0.1,
        reasoning="none",
        max_turns=100,
    )


def _make_mock_backend():
    """Create a mock RunBackend that tracks runs."""
    backend = MagicMock()
    active = set()

    async def start_run(run_id, config):
        active.add(run_id)

    async def stop_run(run_id):
        active.discard(run_id)

    backend.start_run = AsyncMock(side_effect=start_run)
    backend.stop_run = AsyncMock(side_effect=stop_run)
    backend.is_running = MagicMock(side_effect=lambda rid: rid in active)
    backend.get_active_run_ids = MagicMock(side_effect=lambda: list(active))
    backend.remove = MagicMock(side_effect=lambda rid: active.discard(rid))
    return backend


# === RunManager tests ===


class TestRunManager:
    @pytest.fixture
    def backend(self):
        return _make_mock_backend()

    @pytest.fixture
    def manager(self, backend):
        return RunManager(backend, max_runs_per_user=1, max_total_runs=3)

    @pytest.mark.asyncio
    async def test_create_and_start(self, manager, backend):
        config = _make_config()
        run_id = await manager.create_and_start_run(user_id=10, config=config)
        assert run_id.startswith("run_")
        backend.start_run.assert_awaited_once()
        assert manager.is_running(run_id)
        assert manager.get_run_owner(run_id) == 10
        assert run_id in manager.get_user_active_runs(10)

    @pytest.mark.asyncio
    async def test_run_id_generated(self, manager):
        config = _make_config()
        run_id = await manager.create_and_start_run(user_id=10, config=config)
        assert run_id.startswith("run_")
        assert len(run_id) > 4
        # Config should be stamped with the generated run_id and user_id
        assert config.run_id == run_id
        assert config.user_id == 10

    @pytest.mark.asyncio
    async def test_per_user_limit(self, manager):
        c1 = _make_config()
        await manager.create_and_start_run(user_id=10, config=c1)

        c2 = _make_config()
        with pytest.raises(HTTPException) as exc_info:
            await manager.create_and_start_run(user_id=10, config=c2)
        assert exc_info.value.status_code == 429
        assert "per user" in str(exc_info.value.detail)

    @pytest.mark.asyncio
    async def test_different_users_not_limited(self, manager):
        c1 = _make_config()
        c2 = _make_config()
        await manager.create_and_start_run(user_id=10, config=c1)
        await manager.create_and_start_run(user_id=20, config=c2)
        assert manager.active_count == 2

    @pytest.mark.asyncio
    async def test_global_limit(self, manager):
        # manager allows max 3 total
        for i in range(3):
            c = _make_config()
            await manager.create_and_start_run(user_id=100 + i, config=c)

        c4 = _make_config()
        with pytest.raises(HTTPException) as exc_info:
            await manager.create_and_start_run(user_id=200, config=c4)
        assert exc_info.value.status_code == 429
        assert "total" in str(exc_info.value.detail)

    @pytest.mark.asyncio
    async def test_stop_run_success(self, manager):
        config = _make_config()
        run_id = await manager.create_and_start_run(user_id=10, config=config)
        await manager.stop_run(run_id, user_id=10)
        assert manager.get_run_owner(run_id) is None

    @pytest.mark.asyncio
    async def test_stop_run_not_running(self, manager):
        with pytest.raises(HTTPException) as exc_info:
            await manager.stop_run("nonexistent", user_id=10)
        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_stop_run_wrong_owner(self, manager):
        config = _make_config()
        run_id = await manager.create_and_start_run(user_id=10, config=config)
        with pytest.raises(HTTPException) as exc_info:
            await manager.stop_run(run_id, user_id=99)
        assert exc_info.value.status_code == 403

    @pytest.mark.asyncio
    async def test_on_finished_callback(self, manager):
        config = _make_config()
        run_id = await manager.create_and_start_run(user_id=10, config=config)

        # Simulate run finishing
        callback = manager.get_on_finished_callback()
        callback(run_id)

        assert manager.get_run_owner(run_id) is None
        assert manager.get_user_active_runs(10) == []

    @pytest.mark.asyncio
    async def test_on_finished_frees_slot(self, manager):
        """After a run finishes, the user can start another."""
        c1 = _make_config()
        run_id = await manager.create_and_start_run(user_id=10, config=c1)

        # Simulate natural completion
        callback = manager.get_on_finished_callback()
        callback(run_id)

        # Now user should be able to start another
        c2 = _make_config()
        run_id_2 = await manager.create_and_start_run(user_id=10, config=c2)
        assert run_id_2.startswith("run_")

    @pytest.mark.asyncio
    async def test_stop_all(self, manager, backend):
        c1 = _make_config()
        c2 = _make_config()
        await manager.create_and_start_run(user_id=10, config=c1)
        await manager.create_and_start_run(user_id=20, config=c2)

        await manager.stop_all()
        assert backend.stop_run.await_count == 2
        assert manager.active_count == 0
        assert manager.get_user_active_runs(10) == []
        assert manager.get_user_active_runs(20) == []

    @pytest.mark.asyncio
    async def test_active_count(self, manager):
        assert manager.active_count == 0
        c1 = _make_config()
        await manager.create_and_start_run(user_id=10, config=c1)
        assert manager.active_count == 1
