"""Agent runner wrapper for TUI integration."""

import asyncio
import logging
import time
from typing import TYPE_CHECKING, Any, Optional

from .events import (
    AgentStatusChanged,
    DecisionMade,
    GameStateUpdated,
    SkillExecuted,
)

if TYPE_CHECKING:
    from textual.app import App
    from src.agent import NetHackAgent
    from src.api import NetHackAPI

logger = logging.getLogger(__name__)


class TUIAgentRunner:
    """
    Wraps NetHackAgent to emit events for TUI updates.

    This is the integration layer that connects the agent
    to the TUI without modifying agent.py itself.

    Example usage:
        runner = TUIAgentRunner(agent, api, app)
        await runner.start()  # Runs in background
        runner.pause()
        runner.resume()
        await runner.stop()
    """

    def __init__(
        self,
        agent: "NetHackAgent",
        api: "NetHackAPI",
        app: "App",
        update_interval: float = 0.05,
        screen_refresh_interval: float = 0.2,
    ) -> None:
        """
        Initialize the runner.

        Args:
            agent: NetHackAgent instance
            api: NetHackAPI instance
            app: Textual App for posting messages
            update_interval: Seconds between steps (for TUI responsiveness)
            screen_refresh_interval: Seconds between screen updates during execution
        """
        self.agent = agent
        self.api = api
        self.app = app
        self.update_interval = update_interval
        self.screen_refresh_interval = screen_refresh_interval

        self._task: Optional[asyncio.Task] = None
        self._screen_task: Optional[asyncio.Task] = None
        self._running = False

    async def start(self) -> None:
        """Start the agent loop in background."""
        if self._running:
            logger.warning("Agent already running")
            return

        self._running = True
        self.agent.start_episode(self.api)
        self._task = asyncio.create_task(self._run_loop())
        self._screen_task = asyncio.create_task(self._screen_refresh_loop())
        self.app.post_message(AgentStatusChanged(status="running"))
        logger.info("Agent started")

    async def _screen_refresh_loop(self) -> None:
        """Background loop that periodically refreshes game state for smooth TUI updates."""
        try:
            while self._running:
                await asyncio.sleep(self.screen_refresh_interval)
                if self._running and not self.agent.state.paused:
                    self._emit_game_state()
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.warning(f"Screen refresh loop error: {e}")

    async def _run_loop(self) -> None:
        """Main agent loop with event emission."""
        try:
            while not self.agent.is_done and self._running:
                if self.agent.state.paused:
                    await asyncio.sleep(0.1)
                    continue

                # Yield to event loop to ensure UI stays responsive
                await asyncio.sleep(0)

                # Emit game state before decision
                self._emit_game_state()

                # Execute step - can be cancelled
                try:
                    decision = await self.agent.step()
                except asyncio.CancelledError:
                    logger.info("Agent step cancelled")
                    raise

                # Emit decision event
                if decision:
                    self.app.post_message(
                        DecisionMade(
                            decision=decision,
                            turn=self.agent.state.turn,
                            timestamp=time.time(),
                        )
                    )

                # Emit skill result if present
                if self.agent.state.last_skill_result:
                    result = self.agent.state.last_skill_result
                    self.app.post_message(
                        SkillExecuted(
                            skill_name=result.get("skill", "unknown"),
                            success=result.get("success", False),
                            stopped_reason=result.get("stopped_reason", "unknown"),
                            actions=result.get("actions", 0),
                            turns=result.get("turns", 0),
                        )
                    )

                # Emit updated game state after action
                self._emit_game_state()

                # Small delay for TUI responsiveness
                await asyncio.sleep(self.update_interval)

            # Episode ended
            end_reason = "completed"
            if not self._running:
                end_reason = "stopped by user"
            elif self.agent.state.consecutive_errors >= self.agent.config.max_consecutive_errors:
                end_reason = "too many errors"

            self.agent.end_episode(end_reason)
            self.app.post_message(AgentStatusChanged(status="stopped"))
            logger.info(f"Agent stopped: {end_reason}")

        except asyncio.CancelledError:
            logger.info("Agent loop cancelled")
            try:
                self.agent.end_episode("cancelled")
            except Exception:
                pass
            raise  # Re-raise so task completes properly

        except Exception as e:
            logger.exception(f"Agent loop error: {e}")
            self.app.post_message(
                AgentStatusChanged(status="error", error_message=str(e))
            )
            try:
                self.agent.end_episode(f"error: {e}")
            except Exception:
                pass

        finally:
            self._running = False

    def _emit_game_state(self) -> None:
        """Emit current game state to TUI."""
        try:
            stats = self.api.get_stats()
            screen = self.api.get_screen()
            message = self.api.get_message()

            self.app.post_message(
                GameStateUpdated(
                    screen=screen,
                    hp=stats.hp,
                    max_hp=stats.max_hp,
                    turn=stats.turn,
                    dungeon_level=stats.dungeon_level,
                    score=stats.score,
                    message=message,
                    hunger=stats.hunger.value if hasattr(stats.hunger, "value") else str(stats.hunger),
                )
            )
        except Exception as e:
            logger.warning(f"Failed to emit game state: {e}")

    def pause(self) -> None:
        """Pause the agent."""
        self.agent.pause()
        self.app.post_message(AgentStatusChanged(status="paused"))
        logger.info("Agent paused")

    def resume(self) -> None:
        """Resume the agent."""
        self.agent.resume()
        self.app.post_message(AgentStatusChanged(status="running"))
        logger.info("Agent resumed")

    async def stop(self) -> None:
        """Stop the agent."""
        self._running = False
        self.agent.stop()

        # Cancel tasks immediately - don't wait for graceful stop
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

        if self._screen_task:
            self._screen_task.cancel()
            try:
                await self._screen_task
            except asyncio.CancelledError:
                pass

        self.app.post_message(AgentStatusChanged(status="stopped"))
        logger.info("Agent stopped")

    @property
    def is_running(self) -> bool:
        """Check if the agent is currently running."""
        return self._running

    @property
    def is_paused(self) -> bool:
        """Check if the agent is paused."""
        return self.agent.state.paused


async def create_watched_agent(
    config: Optional[dict] = None,
) -> tuple["NetHackAgent", "NetHackAPI"]:
    """
    Create an agent and API instance ready for TUI watching.

    Args:
        config: Optional configuration dict

    Returns:
        Tuple of (agent, api)
    """
    from src.agent import NetHackAgent, AgentConfig
    from src.agent.llm_client import LLMClient
    from src.api import NetHackAPI
    from src.skills import SkillLibrary, SkillExecutor
    from src.config import load_config

    # Load configuration
    if config is None:
        config = load_config()

    # Create API (which creates its own NLEWrapper internally)
    api = NetHackAPI(
        env_name=config.environment.name,
        max_episode_steps=config.environment.max_episode_steps,
    )
    api.reset()  # Must reset to start a fresh game

    # Create LLM client
    llm = LLMClient(
        provider=config.agent.provider,
        model=config.agent.model,
        base_url=config.agent.base_url,
        temperature=config.agent.temperature,
    )

    # Clear custom skills from previous runs (start fresh each time)
    import shutil
    from pathlib import Path
    custom_skills_dir = Path(config.skills.library_path) / "custom"
    if custom_skills_dir.exists():
        shutil.rmtree(custom_skills_dir)
        custom_skills_dir.mkdir()

    # Create skill library
    library = SkillLibrary(config.skills.library_path)
    library.load_all()

    # Create executor
    executor = SkillExecutor(api=api, library=library)

    # Create agent
    agent_config = AgentConfig(
        max_turns=config.agent.max_turns,
        max_consecutive_errors=5,
        decision_timeout=60.0,
        skill_timeout=config.sandbox.timeout_seconds,
        max_recent_messages=config.agent.max_recent_messages,
    )

    agent = NetHackAgent(
        llm_client=llm,
        skill_library=library,
        skill_executor=executor,
        config=agent_config,
    )

    return agent, api
