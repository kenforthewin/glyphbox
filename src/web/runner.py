"""Agent runner for the web interface.

Wraps the agent loop to persist turns to a PostgresRepository,
analogous to TUIAgentRunner emitting Textual events.
"""

import asyncio
import logging
from collections.abc import Callable
from dataclasses import asdict
from datetime import datetime
from typing import Any

from src.agent import NetHackAgent
from src.api import NetHackAPI
from src.persistence.models import RunRecord, TurnRecord
from src.persistence.postgres import PostgresRepository

logger = logging.getLogger(__name__)


class WebAgentRunner:
    """Wraps NetHackAgent to persist turns for the web interface.

    Lifecycle:
        runner = WebAgentRunner(agent, api, repo)
        run_id = await runner.start()
        # ... agent plays, turns are persisted ...
        await runner.stop()
    """

    def __init__(
        self,
        agent: NetHackAgent,
        api: NetHackAPI,
        repo: PostgresRepository,
        user_id: int | None = None,
        on_finished: Callable[[str], None] | None = None,
    ):
        self.agent = agent
        self.api = api
        self.repo = repo
        self._user_id = user_id
        self._on_finished = on_finished

        self._task: asyncio.Task | None = None
        self._running = False
        self._run_record: RunRecord | None = None
        self._turn_counter = 0

    @property
    def run_id(self) -> str | None:
        return self._run_record.run_id if self._run_record else None

    async def start(self, run_id: str | None = None) -> str:
        """Start the agent and return the run_id.

        Args:
            run_id: Optional pre-generated run ID (e.g. from RunManager).
                If provided, used as the episode_id so the run record
                matches across web server and worker processes.
        """
        if self._running:
            raise RuntimeError("Runner already active")

        self._running = True
        self.agent.start_episode(self.api, episode_id=run_id)

        # Build config snapshot safely
        config_snapshot = None
        if self.agent.config:
            try:
                config_snapshot = asdict(self.agent.config)
            except Exception:
                config_snapshot = None

        episode_id = self.agent._result.episode_id

        # If a run_id was provided, a placeholder RunRecord may already exist
        # (created by ProcrastinateBackend). Update it instead of inserting.
        existing = await self.repo.get_run(episode_id) if run_id else None
        if existing:
            existing.model = self.agent.llm.model
            existing.provider = self.agent.llm.provider
            existing.config_snapshot = config_snapshot
            existing.status = "running"
            await self.repo.update_run(existing)
            self._run_record = existing
        else:
            self._run_record = RunRecord(
                run_id=episode_id,
                started_at=datetime.now(),
                model=self.agent.llm.model,
                provider=self.agent.llm.provider,
                config_snapshot=config_snapshot,
                status="running",
                user_id=self._user_id,
                visibility="public",
            )
            self._run_record = await self.repo.create_run(self._run_record)
        self._turn_counter = 0

        self._task = asyncio.create_task(self._run_loop())
        logger.info(f"WebAgentRunner started: run_id={self._run_record.run_id}")

        return self._run_record.run_id

    async def _run_loop(self) -> None:
        """Main agent loop with turn persistence."""
        try:
            while not self.agent.is_done and self._running:
                if self.agent.state.paused:
                    await asyncio.sleep(0.1)
                    continue

                # Capture game state before the agent decides
                pre_state = self._capture_game_state()

                try:
                    decision = await self.agent.step()
                except asyncio.CancelledError:
                    logger.info("Agent step cancelled")
                    raise

                if decision and decision.is_valid:
                    turn = self._build_turn_record(pre_state, decision)
                    await self.repo.save_turn(turn)
                    await self._update_run_stats()

                await asyncio.sleep(0)  # Yield to event loop

            # Capture final game state (death screen, etc.) as one last turn
            await self._save_final_turn()

            end_reason = self._determine_end_reason()
            await self._finalize_run(end_reason)

        except asyncio.CancelledError:
            await self._finalize_run("cancelled")
            raise

        except Exception as e:
            logger.exception(f"Run loop error: {e}")
            await self._finalize_run(f"error: {e}")

        finally:
            self._running = False
            # Clean up NLE environment
            try:
                self.api.close()
            except Exception:
                pass
            # Notify RunManager that this run finished
            if self._on_finished and self._run_record:
                try:
                    self._on_finished(self._run_record.run_id)
                except Exception:
                    pass

    def _capture_game_state(self) -> dict[str, Any]:
        """Snapshot game state before the agent decides."""
        try:
            stats = self.api.get_stats()
            # Serialize inventory items to dicts
            inventory = None
            try:
                items = self.api.get_inventory()
                if items:
                    inventory = [
                        {"slot": item.slot, "name": item.name, "quantity": item.quantity}
                        for item in items
                    ]
            except Exception:
                pass
            # Get dungeon overview (free action, no turn consumed)
            dungeon_overview = None
            try:
                dungeon_overview = self.api.get_overview() or None
            except Exception:
                pass
            return {
                "screen": self.api.get_screen(),
                "screen_colors": self.api.get_screen_colors(),
                "message": self.api.get_message(),
                "player_x": stats.position.x,
                "player_y": stats.position.y,
                "hp": stats.hp,
                "max_hp": stats.max_hp,
                "dungeon_level": stats.dungeon_level,
                "depth": stats.depth,
                "xp_level": stats.xp_level,
                "score": stats.score,
                "hunger": (
                    stats.hunger.value if hasattr(stats.hunger, "value") else str(stats.hunger)
                ),
                "game_turn": stats.turn,
                "inventory": inventory,
                "dungeon_overview": dungeon_overview,
            }
        except Exception as e:
            logger.warning(f"Failed to capture game state: {e}")
            return {}

    def _build_turn_record(self, pre_state: dict, decision: Any) -> TurnRecord:
        """Construct a TurnRecord from pre-state + decision + result."""
        self._turn_counter += 1
        result = self.agent.state.last_skill_result or {}

        return TurnRecord(
            run_id=self._run_record.run_id,
            turn_number=self._turn_counter,
            game_turn=pre_state.get("game_turn", 0),
            timestamp=datetime.now(),
            game_screen=pre_state.get("screen", ""),
            game_screen_colors=pre_state.get("screen_colors") or None,
            player_x=pre_state.get("player_x", 0),
            player_y=pre_state.get("player_y", 0),
            hp=pre_state.get("hp", 0),
            max_hp=pre_state.get("max_hp", 0),
            dungeon_level=pre_state.get("dungeon_level", 1),
            depth=pre_state.get("depth", 0),
            xp_level=pre_state.get("xp_level", 1),
            score=pre_state.get("score", 0),
            hunger=pre_state.get("hunger", "Not Hungry"),
            game_message=pre_state.get("message", ""),
            llm_reasoning=decision.reasoning or "",
            llm_model=self.agent.llm.model,
            llm_prompt_tokens=(decision.llm_usage or {}).get("prompt_tokens"),
            llm_completion_tokens=(decision.llm_usage or {}).get("completion_tokens"),
            llm_total_tokens=(decision.llm_usage or {}).get("total_tokens"),
            llm_finish_reason=getattr(decision, "llm_finish_reason", None),
            action_type=decision.action.value if decision.action else "unknown",
            code=decision.code,
            skill_name=decision.skill_name,
            execution_success=result.get("success", True),
            execution_error=result.get("error"),
            game_messages=result.get("messages", []),
            api_calls=result.get("api_calls", []),
            inventory=pre_state.get("inventory"),
            dungeon_overview=pre_state.get("dungeon_overview"),
        )

    async def _save_final_turn(self) -> None:
        """Save a synthetic game-over turn with summary stats.

        The normal loop records pre-state before each step, so when the game
        ends mid-step the death screen is never saved.  Instead of showing
        the NLE post-death screen (top-ten list), we build a simple summary.
        """
        if not self._run_record:
            return
        try:
            # Pull peak stats from previously saved turns (NLE zeroes stats
            # after death, so the live observation is unreliable).
            peak = await self.repo.get_run_peak_stats(self._run_record.run_id)
            score = peak["score"] if peak else 0
            depth = peak["depth"] if peak else 1
            xp_level = peak["xp_level"] if peak else 1
            game_turn = peak["game_turn"] if peak else 0

            # Build a simple game-over screen (80-col centered)
            lines = [""] * 8
            lines.append("GAME OVER".center(80))
            lines.append("")
            lines.append(f"Score: {score}".center(80))
            lines.append(f"Depth: {depth}   XL: {xp_level}   Turns: {game_turn}".center(80))
            lines.append("")
            lines.extend([""] * (24 - len(lines)))
            game_over_screen = "\n".join(lines)

            self._turn_counter += 1
            final_turn = TurnRecord(
                run_id=self._run_record.run_id,
                turn_number=self._turn_counter,
                game_turn=game_turn,
                timestamp=datetime.now(),
                game_screen=game_over_screen,
                game_screen_colors=None,
                player_x=0,
                player_y=0,
                hp=0,
                max_hp=0,
                dungeon_level=depth,
                depth=depth,
                xp_level=xp_level,
                score=score,
                hunger="",
                game_message="",
                llm_reasoning="",
                llm_model=self.agent.llm.model,
                action_type="game_over",
                code="",
                execution_success=True,
                game_messages=[],
                api_calls=[],
                inventory=None,
                dungeon_overview=None,
            )
            await self.repo.save_turn(final_turn)
        except Exception as e:
            logger.warning(f"Failed to save final turn: {e}")

    async def _update_run_stats(self) -> None:
        """Update running totals on the RunRecord."""
        if not self._run_record:
            return
        self._run_record.total_agent_turns = self._turn_counter
        await self.repo.update_run(self._run_record)

    def _determine_end_reason(self) -> str:
        if not self._running:
            return "stopped by user"
        if self.agent._api and hasattr(self.agent._api, "is_done") and self.agent._api.is_done:
            return "game over"
        if self.agent.state.consecutive_errors >= self.agent.config.max_consecutive_errors:
            return "too many errors"
        return "completed"

    async def _finalize_run(self, end_reason: str) -> None:
        """Write final stats to the run record."""
        if not self._run_record:
            return

        try:
            result = self.agent.end_episode(end_reason)
            self._run_record.final_score = result.final_score
            self._run_record.final_game_turns = result.final_turns
            self._run_record.final_depth = result.final_depth
            self._run_record.total_agent_turns = result.decisions_made
        except Exception as e:
            logger.warning(f"Failed to get final stats: {e}")

        # Always try peak stats from turns — end_episode often returns zeros
        # because NLE resets stats after death, and _save_final_turn captures
        # that zeroed-out state as the latest turn.
        try:
            peak = await self.repo.get_run_peak_stats(self._run_record.run_id)
            if peak:
                self._run_record.final_score = max(
                    self._run_record.final_score, peak["score"]
                )
                self._run_record.final_game_turns = max(
                    self._run_record.final_game_turns, peak["game_turn"]
                )
                self._run_record.final_depth = max(
                    self._run_record.final_depth, peak["depth"]
                )
                self._run_record.final_xp_level = max(
                    self._run_record.final_xp_level, peak["xp_level"]
                )
        except Exception as e:
            logger.warning(f"Failed to get peak stats from turns: {e}")

        self._run_record.ended_at = datetime.now()
        self._run_record.end_reason = end_reason
        self._run_record.status = "stopped"
        await self.repo.update_run(self._run_record)

        logger.info(f"Run finalized: {self._run_record.run_id} ({end_reason})")

    async def stop(self) -> None:
        """Stop the agent run."""
        self._running = False
        self.agent.stop()

        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

    async def wait(self) -> None:
        """Block until the run loop completes.

        Used by worker processes to await the full run lifecycle.
        """
        if self._task:
            try:
                await self._task
            except asyncio.CancelledError:
                pass

    @property
    def is_running(self) -> bool:
        return self._running
