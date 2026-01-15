"""
Main agent orchestration loop.

Coordinates LLM decisions, skill execution, and memory updates
to play NetHack autonomously.
"""

import asyncio
import json
import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Optional

from .llm_client import get_agent_tools, LLMClient, LLMResponse
from .parser import ActionType, AgentDecision, DecisionParser
from .prompts import PromptManager
from .skill_synthesis import SkillSynthesizer

from src.api.models import Direction
from src.config import AgentConfig
from src.memory import EpisodeMemory
from src.sandbox.manager import SkillSandbox
from src.skills import SkillExecutor, SkillLibrary
from src.tui.logging import DecisionLogger, SkillLogger, GameStateLogger

logger = logging.getLogger(__name__)
decision_logger = DecisionLogger()
skill_logger = SkillLogger()
game_state_logger = GameStateLogger()


@dataclass
class AgentConfig:
    """Configuration for the agent."""

    max_turns: int = 100000
    max_consecutive_errors: int = 5
    decision_timeout: float = 60.0
    skill_timeout: float = 30.0
    hp_flee_threshold: float = 0.3
    auto_save_skills: bool = True
    log_decisions: bool = True
    skills_enabled: bool = False  # Enable write_skill/invoke_skill tools
    max_recent_messages: int = 10  # Number of recent messages to keep in full


@dataclass
class AgentState:
    """Current state of the agent."""

    turn: int = 0
    decisions_made: int = 0
    skills_executed: int = 0
    skills_created: int = 0
    consecutive_errors: int = 0
    last_decision: Optional[AgentDecision] = None
    last_skill_result: Optional[dict] = None
    running: bool = False
    paused: bool = False


@dataclass
class AgentResult:
    """Result of an agent episode."""

    episode_id: str
    started_at: datetime
    ended_at: Optional[datetime] = None
    end_reason: str = ""
    final_score: int = 0
    final_turns: int = 0
    final_depth: int = 0
    decisions_made: int = 0
    skills_executed: int = 0
    skills_created: int = 0
    errors: list[str] = field(default_factory=list)


class NetHackAgent:
    """
    Main agent that plays NetHack using LLM-guided skill execution.

    Coordinates:
    - LLM client for strategic decisions
    - Skill library and executor
    - Memory systems (episode, dungeon, working)
    - Skill synthesis for generating new skills

    Example usage:
        agent = NetHackAgent(
            llm_client=llm,
            skill_library=library,
            skill_executor=executor,
        )

        # Run a full episode
        result = await agent.run_episode(api)

        # Or step-by-step
        agent.start_episode(api)
        while not agent.is_done:
            await agent.step()
        result = agent.end_episode()
    """

    def __init__(
        self,
        llm_client: LLMClient,
        skill_library: SkillLibrary,
        skill_executor: SkillExecutor,
        config: Optional[AgentConfig] = None,
        db_path: Optional[str] = None,
    ):
        """
        Initialize the NetHack agent.

        Args:
            llm_client: LLM client for decisions
            skill_library: Library of available skills
            skill_executor: Executor for running skills
            config: Agent configuration
            db_path: Path to memory database
        """
        self.llm = llm_client
        self.library = skill_library
        self.executor = skill_executor
        self.config = config or AgentConfig()

        # Components
        self.prompts = PromptManager(skills_enabled=self.config.skills_enabled)
        self.parser = DecisionParser()
        self.synthesizer = SkillSynthesizer(
            library=skill_library,
            executor=skill_executor,
            auto_save=self.config.auto_save_skills,
        )
        self.sandbox = SkillSandbox()

        # Memory
        self._db_path = db_path
        self.memory: Optional[EpisodeMemory] = None

        # Game API
        self._api: Optional[Any] = None

        # State
        self.state = AgentState()
        self._result: Optional[AgentResult] = None

        # Conversation history for multi-turn LLM context
        self._conversation: list[dict] = []
        self._max_conversation_turns = 10

    async def run_episode(self, api: Any) -> AgentResult:
        """
        Run a complete episode.

        Args:
            api: NetHackAPI instance

        Returns:
            AgentResult with episode outcome
        """
        self.start_episode(api)

        try:
            while not self.is_done:
                await self.step()
        except Exception as e:
            logger.exception(f"Episode error: {e}")
            self._result.errors.append(str(e))

        return self.end_episode()

    def start_episode(self, api: Any) -> None:
        """
        Start a new episode.

        Args:
            api: NetHackAPI instance
        """
        self._api = api
        self.state = AgentState(running=True)
        self._result = AgentResult(
            episode_id=f"ep_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
            started_at=datetime.now(),
        )

        # Initialize memory
        self.memory = EpisodeMemory(
            db_path=self._db_path,
            episode_id=self._result.episode_id,
        )
        self.memory.start()

        # Clear conversation
        self._conversation.clear()

        logger.info(f"Started episode: {self._result.episode_id}")

    def end_episode(self, reason: str = "completed") -> AgentResult:
        """
        End the current episode.

        Args:
            reason: Reason for ending

        Returns:
            AgentResult with final statistics
        """
        self.state.running = False

        if self._result:
            self._result.ended_at = datetime.now()
            self._result.end_reason = reason
            self._result.decisions_made = self.state.decisions_made
            self._result.skills_executed = self.state.skills_executed
            self._result.skills_created = self.state.skills_created

            # Get final stats from API if available
            if self._api:
                try:
                    stats = self._api.get_stats()
                    self._result.final_score = getattr(stats, "score", 0)
                    self._result.final_turns = getattr(stats, "turn", self.state.turn)
                    self._result.final_depth = getattr(stats, "dungeon_level", 1)
                except Exception:
                    pass

        # End memory tracking
        if self.memory:
            self.memory.end(
                end_reason=reason,
                final_score=self._result.final_score if self._result else 0,
                final_turns=self._result.final_turns if self._result else 0,
            )
            self.memory.close()

        logger.info(f"Ended episode: {reason}")
        return self._result

    @property
    def is_done(self) -> bool:
        """Check if episode is finished."""
        if not self.state.running:
            return True

        if self._api and self._api.is_done:
            return True

        if self.state.turn >= self.config.max_turns:
            return True

        if self.state.consecutive_errors >= self.config.max_consecutive_errors:
            return True

        return False

    async def step(self) -> Optional[AgentDecision]:
        """
        Execute one agent step.

        Returns:
            The decision made, or None if episode ended
        """
        if self.is_done:
            return None

        if self.state.paused:
            await asyncio.sleep(0.1)
            return None

        try:
            # Update state from game
            self._update_game_state()

            # Get decision from LLM
            decision = await self._get_decision()
            self.state.last_decision = decision
            self.state.decisions_made += 1

            if not decision.is_valid:
                logger.warning(f"Invalid decision: {decision.parse_error}")
                self.state.consecutive_errors += 1
                return decision

            # Execute decision
            await self._execute_decision(decision)
            self.state.consecutive_errors = 0

            return decision

        except Exception as e:
            logger.exception(f"Step error: {e}")
            self.state.consecutive_errors += 1
            if self._result:
                self._result.errors.append(str(e))
            return None

    def _update_game_state(self) -> None:
        """Update memory with current game state."""
        if not self._api or not self.memory:
            return

        try:
            stats = self._api.get_stats()
            position = self._api.get_position()
            monsters = self._api.get_visible_monsters()
            items = self._api.get_items_here()
            message = self._api.get_message()

            self.state.turn = stats.turn

            # Log game state
            game_state_logger.log_state(
                turn=stats.turn,
                hp=stats.hp,
                max_hp=stats.max_hp,
                position=(position.x, position.y),
                dlvl=stats.dungeon_level,
                message=message,
            )

            # Count hostile monsters separately from all visible monsters
            hostile_monsters = [m for m in monsters if m.is_hostile]

            self.memory.update_state(
                turn=stats.turn,
                hp=stats.hp,
                max_hp=stats.max_hp,
                position_x=position.x,
                position_y=position.y,
                dungeon_level=stats.dungeon_level,
                monsters_visible=len(monsters),
                hostile_monsters_visible=len(hostile_monsters),
                items_here=len(items) if items else 0,
                hunger_state=getattr(stats, "hunger_state", "not hungry"),
                message=message,
                xp_level=getattr(stats, "xp_level", 1),
                score=getattr(stats, "score", 0),
            )

            # Record monster sightings
            for monster in monsters:
                self.memory.working.record_sighting(
                    name=monster.name,
                    position_x=monster.position.x,
                    position_y=monster.position.y,
                    turn=stats.turn,
                    entity_type="monster",
                    is_hostile=monster.is_hostile,
                )

        except Exception as e:
            logger.warning(f"Failed to update game state: {e}")

    async def _get_decision(self) -> AgentDecision:
        """Get a decision from the LLM using tool calling."""
        # Build context
        game_state = self.memory.get_summary() if self.memory else {}

        # Add real-time info: hostile monsters with positions
        if self._api:
            position = self._api.get_position()
            hostile_monsters = self._api.get_hostile_monsters()
            if hostile_monsters:
                monster_details = []
                for m in hostile_monsters:
                    dist = position.distance_to(m.position)
                    direction = position.direction_to(m.position)
                    dir_name = direction.name if direction else "?"
                    adjacent = " [ADJACENT]" if dist == 1 else ""
                    monster_details.append(
                        f"{m.name} at ({m.position.x}, {m.position.y}) [{dist} tiles {dir_name}]{adjacent}"
                    )
                game_state["hostile_monster_details"] = monster_details

            # Add doors
            doors = self._api.find_doors()
            if doors:
                door_details = []
                for pos, is_open in doors:
                    dist = position.distance_to(pos)
                    direction = position.direction_to(pos)
                    dir_name = direction.name if direction else "?"
                    state = "open" if is_open else "closed"
                    door_details.append(
                        f"({pos.x}, {pos.y}) [{state}] [{dist} tiles {dir_name}]"
                    )
                game_state["door_details"] = door_details

            # Add stairs if visible
            stairs_down = self._api.find_stairs_down()
            if stairs_down.success:
                pos = stairs_down.position
                dist = position.distance_to(pos)
                direction = position.direction_to(pos)
                dir_name = direction.name if direction else "?"
                game_state["stairs_down"] = f"({pos.x}, {pos.y}) [{dist} tiles {dir_name}]"

            stairs_up = self._api.find_stairs_up()
            if stairs_up.success:
                pos = stairs_up.position
                dist = position.distance_to(pos)
                direction = position.direction_to(pos)
                dir_name = direction.name if direction else "?"
                game_state["stairs_up"] = f"({pos.x}, {pos.y}) [{dist} tiles {dir_name}]"

        # Get saved skills (agent-written skills only)
        saved_skills = [
            s.name for s in self.library.list_skills()
            if s.metadata.author == "agent"
        ]

        # Get recent events
        events = []
        if self.memory:
            for e in self.memory.get_events(limit=10):
                events.append({
                    "turn": e.turn,
                    "type": e.event_type,
                    "desc": e.description,
                })

        # Get last result
        last_result = self.state.last_skill_result

        # Get the full game screen (what a human would see)
        game_screen = ""
        if self._api:
            game_screen = self._api.get_screen()

        # Format prompt with game screen
        prompt = self.prompts.format_decision_prompt(
            game_state=game_state,
            saved_skills=saved_skills,
            recent_events=events,
            last_result=last_result,
            game_screen=game_screen,
        )

        # Get LLM response with tool calling
        system = self.prompts.get_system_prompt()

        # Build messages for the request, compressing old messages
        messages = self._build_messages_with_compression(prompt)

        response = await self.llm.complete_with_tools(
            messages=messages,
            tools=get_agent_tools(self.config.skills_enabled),
            system=system,
        )

        # Store full message in conversation history
        self._conversation.append({"role": "user", "content": prompt})
        if response.tool_call:
            # Store the full tool call as assistant message
            tool_content = json.dumps({
                "tool": response.tool_call.name,
                "arguments": response.tool_call.arguments
            })
            self._conversation.append({"role": "assistant", "content": tool_content})
        else:
            self._conversation.append({"role": "assistant", "content": response.content})

        # Log if configured
        if self.config.log_decisions:
            if response.tool_call:
                logger.debug(f"LLM tool call: {response.tool_call.name}({response.tool_call.arguments})")
            else:
                logger.debug(f"LLM response: {response.content[:500]}...")

        # Create decision from tool call
        if response.tool_call:
            decision = self._create_decision_from_tool_call(response.tool_call, response.content)
        else:
            # Fallback to text parsing if no tool call
            decision = self.parser.parse(response.content)

        return decision

    def _build_messages_with_compression(self, current_prompt: str) -> list[dict]:
        """Build message list, keeping recent messages full and compressing older ones."""
        # Get conversation slice we'll use
        conv_slice = self._conversation[-self._max_conversation_turns * 2:]
        total = len(conv_slice)
        max_recent = self.config.max_recent_messages * 2  # *2 for user+assistant pairs

        messages = []
        for i, msg in enumerate(conv_slice):
            is_recent = (total - i) <= max_recent
            if is_recent:
                messages.append(msg)
            else:
                compressed = self._compress_message(msg)
                if compressed:
                    messages.append(compressed)

        # Add current prompt
        messages.append({"role": "user", "content": current_prompt})
        return messages

    def _compress_message(self, msg: dict) -> dict | None:
        """Compress a message for older context."""
        role = msg.get("role", "")
        content = msg.get("content", "")

        if role == "user":
            # User prompts contain screen + game state, just note it existed
            return None  # Skip entirely - the assistant response has the context

        if role == "assistant":
            # Try to parse as JSON tool call
            try:
                data = json.loads(content)
                if "tool" in data and "arguments" in data:
                    tool = data["tool"]
                    reasoning = data["arguments"].get("reasoning", "")[:60]
                    return {"role": "assistant", "content": f"[{tool}: {reasoning}]"}
            except (json.JSONDecodeError, TypeError):
                pass
            # Non-JSON assistant message, truncate
            return {"role": "assistant", "content": content[:100] + "..." if len(content) > 100 else content}

        return msg

    def _create_decision_from_tool_call(self, tool_call, raw_response: str) -> AgentDecision:
        """Create AgentDecision from a tool call."""
        tool_name = tool_call.name
        args = tool_call.arguments

        try:
            action = ActionType(tool_name)
        except ValueError:
            action = ActionType.UNKNOWN

        return AgentDecision(
            action=action,
            skill_name=args.get("skill_name"),
            params=args.get("params", {}),
            reasoning=args.get("reasoning", ""),
            code=args.get("code"),
            raw_response=raw_response,
        )

    async def _execute_decision(self, decision: AgentDecision) -> None:
        """Execute an agent decision."""
        # Log the decision
        decision_logger.log_decision(
            decision_type=decision.action.value if decision.action else "unknown",
            skill_name=decision.skill_name,
            params=decision.params,
            reasoning=decision.reasoning,
        )

        if decision.action == ActionType.EXECUTE_CODE:
            await self._execute_code(decision.code)

        elif decision.action == ActionType.WRITE_SKILL:
            await self._write_skill(decision.skill_name, decision.code)

        elif decision.action == ActionType.INVOKE_SKILL:
            await self._execute_skill(decision.skill_name, decision.params)

    async def _execute_code(self, code: str) -> None:
        """Execute ad-hoc code in sandbox."""
        if not self._api:
            logger.warning("No API available for execute_code")
            return

        if not code:
            logger.warning("No code provided for execute_code")
            return

        try:
            result = await self.sandbox.execute_code(code, self._api)

            # Extract game messages and failed API calls from result
            game_messages = []
            return_value = None
            failed_calls = []
            if result.result:
                game_messages = result.result.get("game_messages", [])
                return_value = result.result.get("return_value")
                failed_calls = result.result.get("failed_api_calls", [])

            self.state.last_skill_result = {
                "tool": "execute_code",
                "success": result.success,
                "error": result.error,
                "return_value": return_value,
                "messages": game_messages,  # Include game messages for LLM feedback
                "failed_api_calls": failed_calls,  # Include failed API calls for feedback
            }

            # Include stdout if there was any output
            if result.stdout:
                self.state.last_skill_result["output"] = result.stdout

            # Record in memory
            if self.memory:
                self.memory.record_event("execute_code", f"Ran: {code[:100]}")

            if result.success:
                logger.info(f"Executed code successfully")
            else:
                logger.warning(f"Code execution failed: {result.error}")

        except Exception as e:
            logger.error(f"execute_code failed: {e}")
            self.state.last_skill_result = {
                "tool": "execute_code",
                "success": False,
                "error": str(e),
            }

    async def _write_skill(self, skill_name: str, code: str) -> None:
        """Write a new skill to the library."""
        # Reuse existing _create_skill logic
        await self._create_skill(skill_name, code)

    async def _execute_skill(self, skill_name: str, params: dict) -> None:
        """Execute a skill from the library."""
        if not self.executor:
            logger.warning("No executor available")
            return

        # Log skill start
        skill_logger.log_execution_start(skill_name, params)

        try:
            execution = await self.executor.execute(
                skill_name,
                timeout=self.config.skill_timeout,
                **params,
            )

            self.state.skills_executed += 1
            self.state.last_skill_result = {
                "skill": skill_name,
                "success": execution.success,
                "stopped_reason": execution.stopped_reason,
                "actions": execution.actions_taken,
                "turns": execution.turns_elapsed,
                "result_data": execution.result_data,  # Contains hints and extra info
            }

            # Record in memory
            if self.memory:
                self.memory.record_skill_execution(
                    skill_name=skill_name,
                    success=execution.success,
                    stopped_reason=execution.stopped_reason,
                    actions_taken=execution.actions_taken,
                    turns_elapsed=execution.turns_elapsed,
                    result_data=execution.result_data,
                )

            # Log skill end
            skill_logger.log_execution_end(
                skill_name=skill_name,
                success=execution.success,
                stopped_reason=execution.stopped_reason,
                actions_taken=execution.actions_taken,
                turns_elapsed=execution.turns_elapsed,
                result=execution.result_data,
            )

            logger.info(
                f"Executed {skill_name}: "
                f"{'success' if execution.success else 'failed'} "
                f"({execution.stopped_reason})"
            )

        except Exception as e:
            logger.error(f"Skill execution failed: {e}")
            skill_logger.log_execution_end(
                skill_name=skill_name,
                success=False,
                stopped_reason="error",
                result={"error": str(e)},
            )
            self.state.last_skill_result = {
                "skill": skill_name,
                "success": False,
                "error": str(e),
            }

    async def _create_skill(self, skill_name: str, code: str) -> None:
        """Create a new skill from generated code."""
        if not code:
            logger.warning("No code provided for skill creation")
            return

        # Get previous failed attempts for context
        failed = self.synthesizer.get_failed_attempts(skill_name)

        result = await self.synthesizer.synthesize(
            name=skill_name,
            code=code,
            test_before_save=bool(self.executor),
        )

        if result.success:
            self.state.skills_created += 1
            if self.memory:
                self.memory.record_skill_created(skill_name)
            logger.info(f"Created skill: {skill_name}")
        else:
            logger.warning(f"Failed to create skill {skill_name}: {result.error}")

    def pause(self) -> None:
        """Pause the agent."""
        self.state.paused = True

    def resume(self) -> None:
        """Resume the agent."""
        self.state.paused = False

    def stop(self) -> None:
        """Stop the agent."""
        self.state.running = False


async def create_agent(
    llm_config: dict,
    skills_dir: str = "skills",
    db_path: Optional[str] = None,
) -> NetHackAgent:
    """
    Factory function to create a configured agent.

    Args:
        llm_config: LLM configuration dict
        skills_dir: Path to skills directory
        db_path: Path to memory database

    Returns:
        Configured NetHackAgent
    """
    # Create LLM client
    llm = LLMClient(
        provider=llm_config.get("provider", AgentConfig.provider),
        model=llm_config.get("model", AgentConfig.model),
        base_url=llm_config.get("base_url", AgentConfig.base_url),
        temperature=llm_config.get("temperature", AgentConfig.temperature),
    )

    # Create skill library
    library = SkillLibrary(skills_dir)
    library.load_all()

    # Create executor (without API for now - will be set on episode start)
    # Note: Executor needs API instance which we don't have yet
    executor = None  # Will be created when episode starts

    # Create agent
    agent = NetHackAgent(
        llm_client=llm,
        skill_library=library,
        skill_executor=executor,
        db_path=db_path,
    )

    return agent
