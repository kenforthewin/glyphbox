"""
Skill executor for running skills in the sandbox.

Handles skill execution, state tracking, and error handling.
"""

import logging
from datetime import datetime
from typing import Any, Optional

from src.sandbox import (
    ExecutionResult,
    SandboxConfig,
    SkillExecutionError,
    SkillSandbox,
    SkillTimeoutError,
)

from .models import GameStateSnapshot, Skill, SkillExecution, SkillStatistics
from .library import SkillLibrary

logger = logging.getLogger(__name__)


class SkillExecutor:
    """
    Executes skills from the library.

    Manages the sandbox, tracks execution history, and updates statistics.

    Example usage:
        executor = SkillExecutor(library, api)

        # Execute a skill by name
        result = await executor.execute("cautious_explore", max_steps=100)

        # Execute code directly (for agent-generated skills)
        result = await executor.execute_code(code, "new_skill", params={})

        # Get execution history
        history = executor.get_history("cautious_explore")
    """

    def __init__(
        self,
        library: SkillLibrary,
        api: Any,  # NetHackAPI
        sandbox_config: Optional[SandboxConfig] = None,
        use_docker: bool = False,
    ):
        """
        Initialize the executor.

        Args:
            library: Skill library to load skills from
            api: NetHackAPI instance for game interaction
            sandbox_config: Configuration for the sandbox
            use_docker: Whether to use Docker sandbox (False for local execution)
        """
        self.library = library
        self.api = api
        self.use_docker = use_docker

        # Initialize sandbox
        config = sandbox_config or SandboxConfig()
        self._sandbox = SkillSandbox(config)

        # Execution tracking
        self._history: list[SkillExecution] = []
        self._statistics: dict[str, SkillStatistics] = {}
        self._current_execution: Optional[SkillExecution] = None

    async def execute(
        self,
        skill_name: str,
        timeout: Optional[float] = None,
        **params,
    ) -> SkillExecution:
        """
        Execute a skill from the library.

        Args:
            skill_name: Name of skill to execute
            timeout: Execution timeout in seconds
            **params: Parameters to pass to the skill

        Returns:
            SkillExecution record with results

        Raises:
            ValueError: If skill not found
            SkillExecutionError: If execution fails
        """
        skill = self.library.get(skill_name)
        if not skill:
            raise ValueError(f"Skill not found: {skill_name}")

        return await self._execute_skill(skill, params, timeout)

    async def execute_code(
        self,
        code: str,
        skill_name: str,
        params: Optional[dict[str, Any]] = None,
        timeout: Optional[float] = None,
        persist: bool = False,
    ) -> SkillExecution:
        """
        Execute skill code directly (for agent-generated skills).

        Args:
            code: Python skill code
            skill_name: Name for the skill
            params: Parameters to pass to the skill
            timeout: Execution timeout in seconds
            persist: Whether to save the skill to the library if successful

        Returns:
            SkillExecution record with results
        """
        params = params or {}

        # Create temporary skill object
        skill = Skill(name=skill_name, code=code)

        # Execute
        execution = await self._execute_skill(skill, params, timeout)

        # Persist if requested and successful
        if persist and execution.success:
            try:
                self.library.add_from_code(skill_name, code, persist=True)
                logger.info(f"Persisted successful skill: {skill_name}")
            except Exception as e:
                logger.warning(f"Failed to persist skill {skill_name}: {e}")

        return execution

    async def _execute_skill(
        self,
        skill: Skill,
        params: dict[str, Any],
        timeout: Optional[float] = None,
    ) -> SkillExecution:
        """Execute a skill and record the execution."""
        # Capture state before
        state_before = None
        try:
            state_before = GameStateSnapshot.from_api(self.api)
        except Exception as e:
            logger.warning(f"Failed to capture state before: {e}")

        # Create execution record
        execution = SkillExecution(
            skill_name=skill.name,
            params=params,
            started_at=datetime.now(),
            state_before=state_before,
        )
        self._current_execution = execution

        try:
            # Run in sandbox
            if self.use_docker:
                result = await self._sandbox.execute(
                    code=skill.code,
                    skill_name=skill.name,
                    params=params,
                    api_proxy=None,  # Would need APIProxy for Docker
                    timeout=timeout,
                )
            else:
                result = await self._sandbox.execute_local(
                    code=skill.code,
                    skill_name=skill.name,
                    params=params,
                    api=self.api,
                    timeout=timeout,
                )

            # Update execution record
            execution.ended_at = datetime.now()
            execution.success = result.success
            execution.actions_taken = result.actions_taken
            execution.turns_elapsed = result.turns_elapsed

            if result.result:
                execution.stopped_reason = result.result.get("stopped_reason", "")
                execution.result_data = result.result.get("data", {})

            if result.error:
                execution.error = result.error

        except SkillTimeoutError as e:
            execution.ended_at = datetime.now()
            execution.success = False
            execution.stopped_reason = "timeout"
            execution.error = str(e)

        except SkillExecutionError as e:
            execution.ended_at = datetime.now()
            execution.success = False
            execution.stopped_reason = "error"
            execution.error = str(e)

        except Exception as e:
            execution.ended_at = datetime.now()
            execution.success = False
            execution.stopped_reason = "error"
            execution.error = f"Unexpected error: {e}"
            logger.exception(f"Skill execution failed: {e}")

        finally:
            self._current_execution = None

        # Capture state after
        try:
            execution.state_after = GameStateSnapshot.from_api(self.api)
        except Exception as e:
            logger.warning(f"Failed to capture state after: {e}")

        # Record history and statistics
        self._record_execution(execution)

        return execution

    def _record_execution(self, execution: SkillExecution) -> None:
        """Record an execution in history and statistics."""
        # Add to history
        self._history.append(execution)

        # Update statistics
        if execution.skill_name not in self._statistics:
            self._statistics[execution.skill_name] = SkillStatistics(
                skill_name=execution.skill_name
            )

        self._statistics[execution.skill_name].record_execution(execution)

    def get_history(
        self,
        skill_name: Optional[str] = None,
        limit: int = 100,
    ) -> list[SkillExecution]:
        """
        Get execution history.

        Args:
            skill_name: Filter by skill name (None for all)
            limit: Maximum number of records to return

        Returns:
            List of execution records (most recent first)
        """
        history = self._history
        if skill_name:
            history = [e for e in history if e.skill_name == skill_name]

        return list(reversed(history[-limit:]))

    def get_statistics(self, skill_name: str) -> Optional[SkillStatistics]:
        """
        Get statistics for a skill.

        Args:
            skill_name: Skill name

        Returns:
            SkillStatistics or None if no executions
        """
        return self._statistics.get(skill_name)

    def get_all_statistics(self) -> dict[str, SkillStatistics]:
        """Get statistics for all executed skills."""
        return self._statistics.copy()

    def get_best_skills(
        self,
        min_executions: int = 3,
        top_n: int = 10,
    ) -> list[tuple[str, float]]:
        """
        Get the best performing skills by success rate.

        Args:
            min_executions: Minimum executions to be considered
            top_n: Number of skills to return

        Returns:
            List of (skill_name, success_rate) tuples
        """
        results = []
        for name, stats in self._statistics.items():
            if stats.total_executions >= min_executions:
                results.append((name, stats.success_rate))

        results.sort(key=lambda x: x[1], reverse=True)
        return results[:top_n]

    def clear_history(self) -> None:
        """Clear execution history (keeps statistics)."""
        self._history.clear()

    def reset_statistics(self) -> None:
        """Reset all statistics."""
        self._statistics.clear()
        self._history.clear()

    @property
    def current_execution(self) -> Optional[SkillExecution]:
        """Get the currently running execution, if any."""
        return self._current_execution

    def close(self) -> None:
        """Clean up resources."""
        self._sandbox.close()

    async def __aenter__(self) -> "SkillExecutor":
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        self.close()
