"""Procrastinate-based backend for executing agent runs in worker processes.

Jobs are enqueued into PostgreSQL via Procrastinate; worker processes pick
them up and run the full agent loop. The web server tracks active jobs and
monitors completion by periodically checking the runs table.
"""

import asyncio
import logging

from src.persistence.models import RunRecord
from src.web.run_config import RunConfig

logger = logging.getLogger(__name__)


class ProcrastinateBackend:
    """Dispatches agent runs to Procrastinate worker processes.

    The web server enqueues jobs and tracks them. Workers (separate processes)
    execute the actual agent loop. Completion is detected by monitoring
    the ``runs`` table in PostgreSQL.
    """

    def __init__(self, procrastinate_app, repo):
        self._app = procrastinate_app
        self._repo = repo
        self._active_runs: set[str] = set()  # run_ids we believe are running
        self._monitor_task: asyncio.Task | None = None
        self._monitor_interval: float = 10.0
        self._on_finished_callback = None

    def set_on_finished_callback(self, callback):
        """Set the callback invoked when a run is detected as finished."""
        self._on_finished_callback = callback

    async def start_run(self, run_id: str, config: RunConfig) -> None:
        """Create a placeholder RunRecord and enqueue a Procrastinate job."""
        from datetime import datetime

        from src.worker.tasks import run_agent_task

        # Create placeholder run record so REST/WebSocket find it immediately
        placeholder = RunRecord(
            run_id=run_id,
            started_at=datetime.now(),
            model=config.model,
            provider="openrouter",
            status="starting",
            user_id=config.user_id,
            visibility="public",
        )
        await self._repo.create_run(placeholder)

        # Enqueue the job for a worker to pick up
        await run_agent_task.configure(queue="agent_runs").defer_async(
            run_id=run_id,
            user_id=config.user_id,
            model=config.model,
            character=config.character,
            temperature=config.temperature,
            reasoning=config.reasoning,
            max_turns=config.max_turns,
        )

        self._active_runs.add(run_id)
        logger.info(f"Enqueued job for run {run_id}")

    async def stop_run(self, run_id: str) -> None:
        """Stop a run and finalize its record.

        Sets the DB status directly to "stopped" so the record is fully
        resolved regardless of whether a worker is processing it.
        """
        from datetime import datetime

        self._active_runs.discard(run_id)

        run = await self._repo.get_run(run_id)
        if run and run.status not in ("stopped", "error", "completed"):
            # Populate final stats from peak turn values
            try:
                peak = await self._repo.get_run_peak_stats(run_id)
                if peak:
                    run.final_score = max(run.final_score, peak["score"])
                    run.final_game_turns = max(run.final_game_turns, peak["game_turn"])
                    run.final_depth = max(run.final_depth, peak["depth"])
                    run.final_xp_level = max(run.final_xp_level, peak["xp_level"])
            except Exception as e:
                logger.warning(f"Failed to get peak stats for {run_id}: {e}")

            run.status = "stopped"
            run.end_reason = "stopped by user"
            run.ended_at = datetime.now()
            await self._repo.update_run(run)

        logger.info(f"Stopped run {run_id}")

    def is_running(self, run_id: str) -> bool:
        return run_id in self._active_runs

    def get_active_run_ids(self) -> list[str]:
        return list(self._active_runs)

    async def start_monitoring(self, interval: float = 10.0) -> None:
        """Start background task that detects completed runs."""
        self._monitor_interval = interval
        self._monitor_task = asyncio.create_task(self._monitor_loop())

    async def stop_monitoring(self) -> None:
        """Stop the background monitor."""
        if self._monitor_task:
            self._monitor_task.cancel()
            try:
                await self._monitor_task
            except asyncio.CancelledError:
                pass
            self._monitor_task = None

    async def _monitor_loop(self) -> None:
        """Periodically check runs table for completed runs."""
        while True:
            try:
                await asyncio.sleep(self._monitor_interval)
                await self._check_completed_runs()
            except asyncio.CancelledError:
                return
            except Exception:
                logger.exception("Error in run monitor loop")

    async def _check_completed_runs(self) -> None:
        """Remove runs from tracking if they're no longer active in DB."""
        if not self._active_runs:
            return

        terminal_statuses = {"stopped", "error", "completed"}
        for run_id in list(self._active_runs):
            run = await self._repo.get_run(run_id)
            if run and run.status in terminal_statuses:
                self._active_runs.discard(run_id)
                if self._on_finished_callback:
                    self._on_finished_callback(run_id)
                logger.info(f"Monitor: run {run_id} completed (status={run.status})")

    async def recover_state(self, active_runs: list[RunRecord]) -> None:
        """Rebuild tracking from a list of active RunRecords.

        Called on web server startup to re-populate the active runs set
        from runs that are still in-progress in the database.
        """
        self._active_runs.clear()
        for run in active_runs:
            self._active_runs.add(run.run_id)
        logger.info(f"Recovered {len(self._active_runs)} active runs")
