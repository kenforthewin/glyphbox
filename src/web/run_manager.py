"""Run lifecycle management with swappable backend.

The RunBackend protocol allows swapping between in-process asyncio tasks
(InProcessBackend), or Procrastinate worker processes (ProcrastinateBackend)
without changing the RunManager.
"""

import logging
import uuid
from typing import Protocol, runtime_checkable

from fastapi import HTTPException

from src.web.run_config import RunConfig

logger = logging.getLogger(__name__)


@runtime_checkable
class RunBackend(Protocol):
    """Protocol for run execution backends.

    Implementations manage the actual execution of agent runs.
    The RunManager handles concurrency, ownership, and lifecycle on top.
    """

    async def start_run(self, run_id: str, config: RunConfig) -> None:
        """Start an agent run with the given configuration."""
        ...

    async def stop_run(self, run_id: str) -> None:
        """Stop a running agent and clean up."""
        ...

    def is_running(self, run_id: str) -> bool:
        """Check if a run is currently active."""
        ...

    def get_active_run_ids(self) -> list[str]:
        """List all active run IDs."""
        ...


class InProcessBackend:
    """Runs agents as asyncio tasks in the web server process.

    Used when worker.enabled=False (the default). Creates the agent,
    game environment, and runner internally from the RunConfig.
    """

    def __init__(self, repo=None, auth_config=None):
        self._repo = repo
        self._auth_config = auth_config
        self._runners: dict = {}  # run_id -> WebAgentRunner
        self._on_finished_callback = None

    def set_on_finished_callback(self, callback):
        """Set the callback invoked when a run finishes."""
        self._on_finished_callback = callback

    async def start_run(self, run_id: str, config: RunConfig) -> None:
        from src.web.agent_factory import create_agent_for_run
        from src.web.auth import decrypt_key
        from src.web.runner import WebAgentRunner

        # Decrypt API key for this user
        user = await self._repo.get_user(config.user_id)
        if not user or not user.encrypted_openrouter_key:
            raise HTTPException(400, "No API key stored for user")

        api_key = decrypt_key(user.encrypted_openrouter_key, self._auth_config.encryption_key)

        agent, api = create_agent_for_run(
            api_key=api_key,
            model=config.model,
            character=config.character,
            temperature=config.temperature,
            reasoning=config.reasoning,
            max_turns=config.max_turns,
        )

        runner = WebAgentRunner(
            agent=agent,
            api=api,
            repo=self._repo,
            user_id=config.user_id,
            on_finished=self._on_finished_callback,
        )
        await runner.start(run_id=run_id)
        self._runners[run_id] = runner

    async def stop_run(self, run_id: str) -> None:
        runner = self._runners.pop(run_id, None)
        if runner:
            await runner.stop()

    def is_running(self, run_id: str) -> bool:
        runner = self._runners.get(run_id)
        return runner is not None and runner.is_running

    def get_active_run_ids(self) -> list[str]:
        return [rid for rid, r in self._runners.items() if r.is_running]

    def remove(self, run_id: str) -> None:
        """Remove a finished run from tracking (no stop)."""
        self._runners.pop(run_id, None)


class RunManager:
    """Manages run lifecycle with concurrency limits and ownership.

    Wraps a RunBackend with:
    - Per-user concurrency limits
    - Global concurrency limits
    - Ownership tracking for authorization
    - Automatic cleanup when runs finish
    """

    def __init__(
        self,
        backend: RunBackend,
        max_runs_per_user: int = 1,
        max_total_runs: int = 10,
    ):
        self._backend = backend
        self._max_per_user = max_runs_per_user
        self._max_total = max_total_runs

        # Ownership tracking (in-memory, reset on server restart)
        self._run_owners: dict[str, int] = {}  # run_id -> user_id
        self._user_runs: dict[int, set[str]] = {}  # user_id -> {run_ids}

    def _on_run_finished(self, run_id: str) -> None:
        """Callback invoked when a run ends (game over, error, etc.)."""
        user_id = self._run_owners.pop(run_id, None)
        if user_id is not None and user_id in self._user_runs:
            self._user_runs[user_id].discard(run_id)
            if not self._user_runs[user_id]:
                del self._user_runs[user_id]

        # Remove from backend tracking
        if isinstance(self._backend, InProcessBackend):
            self._backend.remove(run_id)

        logger.info(f"Run {run_id} finished, cleaned up (user_id={user_id})")

    def get_on_finished_callback(self):
        """Return the callback to pass to InProcessBackend / WebAgentRunner."""
        return self._on_run_finished

    async def create_and_start_run(
        self,
        user_id: int,
        config: RunConfig,
    ) -> str:
        """Start a run with concurrency checks. Returns run_id.

        Generates a run_id, sets it on the config, and delegates to the backend.
        """
        # Check per-user limit
        user_active = self._user_runs.get(user_id, set())
        if len(user_active) >= self._max_per_user:
            raise HTTPException(
                429,
                f"Concurrent run limit reached ({self._max_per_user} per user). "
                "Stop your current run first.",
            )

        # Check global limit
        active_count = len(self._backend.get_active_run_ids())
        if active_count >= self._max_total:
            raise HTTPException(
                429,
                f"Server run limit reached ({self._max_total} total). Try again later.",
            )

        # Generate run_id and stamp it on the config
        run_id = f"run_{uuid.uuid4().hex[:12]}"
        config.run_id = run_id
        config.user_id = user_id

        # Start the run via backend
        await self._backend.start_run(run_id, config)

        # Track ownership
        self._run_owners[run_id] = user_id
        if user_id not in self._user_runs:
            self._user_runs[user_id] = set()
        self._user_runs[user_id].add(run_id)

        logger.info(f"Run {run_id} started for user {user_id}")
        return run_id

    async def stop_run(self, run_id: str, user_id: int) -> None:
        """Stop a run. Raises 404 if not running, 403 if not owner."""
        if not self._backend.is_running(run_id):
            raise HTTPException(404, f"Run {run_id} is not currently running")

        owner = self._run_owners.get(run_id)
        if owner != user_id:
            raise HTTPException(403, "You can only stop your own runs")

        await self._backend.stop_run(run_id)

        # Clean up ownership (stop_run triggers finalize which calls _on_run_finished,
        # but do it here too for safety)
        self._run_owners.pop(run_id, None)
        if user_id in self._user_runs:
            self._user_runs[user_id].discard(run_id)

        logger.info(f"Run {run_id} stopped by user {user_id}")

    async def stop_all(self) -> None:
        """Stop all active runs (for server shutdown)."""
        for run_id in list(self._backend.get_active_run_ids()):
            try:
                await self._backend.stop_run(run_id)
            except Exception as e:
                logger.warning(f"Error stopping run {run_id} during shutdown: {e}")

        self._run_owners.clear()
        self._user_runs.clear()
        logger.info("All runs stopped")

    async def recover_state(self, repo) -> None:
        """Rebuild ownership maps from the database after a restart.

        Queries runs with status 'running' or 'starting' and
        re-populates the in-memory tracking maps. For ProcrastinateBackend,
        also rebuilds job ID tracking.
        """
        from src.web.procrastinate_backend import ProcrastinateBackend

        active_runs = await repo.list_runs_by_status(["running", "starting"])
        for run in active_runs:
            if run.user_id is not None:
                self._run_owners[run.run_id] = run.user_id
                if run.user_id not in self._user_runs:
                    self._user_runs[run.user_id] = set()
                self._user_runs[run.user_id].add(run.run_id)

        if isinstance(self._backend, ProcrastinateBackend):
            await self._backend.recover_state(active_runs)

        logger.info(
            f"Recovered state: {len(self._run_owners)} active runs "
            f"across {len(self._user_runs)} users"
        )

    def is_running(self, run_id: str) -> bool:
        return self._backend.is_running(run_id)

    def get_run_owner(self, run_id: str) -> int | None:
        return self._run_owners.get(run_id)

    def get_user_active_runs(self, user_id: int) -> list[str]:
        return list(self._user_runs.get(user_id, set()))

    @property
    def active_count(self) -> int:
        return len(self._backend.get_active_run_ids())
