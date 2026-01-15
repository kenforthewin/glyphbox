"""Tests for the main agent orchestration."""

import pytest
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

from src.agent.agent import (
    AgentConfig,
    AgentResult,
    AgentState,
    NetHackAgent,
)
from src.agent.llm_client import ToolCall
from src.agent.parser import ActionType, AgentDecision


class TestAgentConfig:
    """Tests for AgentConfig dataclass."""

    def test_default_values(self):
        """Test default configuration values."""
        config = AgentConfig()
        assert config.max_turns == 100000
        assert config.max_consecutive_errors == 5
        assert config.decision_timeout == 60.0
        assert config.skill_timeout == 30.0
        assert config.hp_flee_threshold == 0.3
        assert config.auto_save_skills is True
        assert config.log_decisions is True

    def test_custom_values(self):
        """Test custom configuration values."""
        config = AgentConfig(
            max_turns=1000,
            max_consecutive_errors=3,
            skill_timeout=10.0,
        )
        assert config.max_turns == 1000
        assert config.max_consecutive_errors == 3
        assert config.skill_timeout == 10.0


class TestAgentState:
    """Tests for AgentState dataclass."""

    def test_default_state(self):
        """Test default state values."""
        state = AgentState()
        assert state.turn == 0
        assert state.decisions_made == 0
        assert state.skills_executed == 0
        assert state.skills_created == 0
        assert state.consecutive_errors == 0
        assert state.last_decision is None
        assert state.last_skill_result is None
        assert state.running is False
        assert state.paused is False


class TestAgentResult:
    """Tests for AgentResult dataclass."""

    def test_default_result(self):
        """Test default result values."""
        result = AgentResult(
            episode_id="ep_test",
            started_at=datetime.now(),
        )
        assert result.episode_id == "ep_test"
        assert result.ended_at is None
        assert result.end_reason == ""
        assert result.final_score == 0
        assert result.final_turns == 0
        assert result.final_depth == 0
        assert result.decisions_made == 0
        assert result.skills_executed == 0
        assert result.skills_created == 0
        assert result.errors == []


class TestNetHackAgent:
    """Tests for NetHackAgent."""

    def setup_method(self):
        """Set up test fixtures."""
        self.mock_llm = MagicMock()
        self.mock_llm.complete_with_tools = AsyncMock()  # async method
        self.mock_library = MagicMock()
        self.mock_executor = AsyncMock()
        self.mock_library.list_skills.return_value = []

        self.agent = NetHackAgent(
            llm_client=self.mock_llm,
            skill_library=self.mock_library,
            skill_executor=self.mock_executor,
        )

    def test_initialization(self):
        """Test agent initialization."""
        assert self.agent.llm == self.mock_llm
        assert self.agent.library == self.mock_library
        assert self.agent.executor == self.mock_executor
        assert self.agent.config is not None
        assert self.agent.state is not None

    def test_custom_config(self):
        """Test agent with custom config."""
        config = AgentConfig(max_turns=500)
        agent = NetHackAgent(
            llm_client=self.mock_llm,
            skill_library=self.mock_library,
            skill_executor=self.mock_executor,
            config=config,
        )
        assert agent.config.max_turns == 500

    def test_start_episode(self):
        """Test starting an episode."""
        mock_api = MagicMock()
        mock_api.is_done = False

        with patch('src.agent.agent.EpisodeMemory'):
            self.agent.start_episode(mock_api)

            assert self.agent.state.running is True
            assert self.agent._api == mock_api
            assert self.agent._result is not None
            assert self.agent._result.episode_id.startswith("ep_")

    def test_end_episode(self):
        """Test ending an episode."""
        mock_api = MagicMock()
        mock_api.is_done = False
        mock_stats = MagicMock()
        mock_stats.score = 100
        mock_stats.turn = 50
        mock_stats.dungeon_level = 3
        mock_api.get_stats.return_value = mock_stats

        with patch('src.agent.agent.EpisodeMemory') as mock_memory_class:
            mock_memory = MagicMock()
            mock_memory_class.return_value = mock_memory

            self.agent.start_episode(mock_api)
            self.agent.state.decisions_made = 10
            self.agent.state.skills_executed = 5
            result = self.agent.end_episode("test_completed")

            assert result.end_reason == "test_completed"
            assert result.decisions_made == 10
            assert result.skills_executed == 5
            assert result.final_score == 100
            assert self.agent.state.running is False
            mock_memory.end.assert_called_once()
            mock_memory.close.assert_called_once()

    def test_is_done_not_running(self):
        """Test is_done when not running."""
        self.agent.state.running = False
        assert self.agent.is_done is True

    def test_is_done_game_over(self):
        """Test is_done when game is over."""
        self.agent.state.running = True
        mock_api = MagicMock()
        mock_api.is_done = True
        self.agent._api = mock_api
        assert self.agent.is_done is True

    def test_is_done_max_turns(self):
        """Test is_done when max turns reached."""
        self.agent.state.running = True
        self.agent.state.turn = 100001
        self.agent._api = MagicMock(is_done=False)
        assert self.agent.is_done is True

    def test_is_done_max_errors(self):
        """Test is_done when max errors reached."""
        self.agent.state.running = True
        self.agent.state.consecutive_errors = 5
        self.agent._api = MagicMock(is_done=False)
        assert self.agent.is_done is True

    def test_is_done_still_playing(self):
        """Test is_done when still playing."""
        self.agent.state.running = True
        self.agent.state.turn = 100
        self.agent.state.consecutive_errors = 0
        self.agent._api = MagicMock(is_done=False)
        assert self.agent.is_done is False

    def test_pause_resume(self):
        """Test pause and resume."""
        assert self.agent.state.paused is False
        self.agent.pause()
        assert self.agent.state.paused is True
        self.agent.resume()
        assert self.agent.state.paused is False

    def test_stop(self):
        """Test stop."""
        self.agent.state.running = True
        self.agent.stop()
        assert self.agent.state.running is False


class TestNetHackAgentStep:
    """Tests for agent step execution."""

    def setup_method(self):
        """Set up test fixtures."""
        self.mock_llm = MagicMock()
        self.mock_llm.complete_with_tools = AsyncMock()  # async method
        self.mock_library = MagicMock()
        self.mock_executor = AsyncMock()

        # Set up skill library
        self.mock_library.list_skills.return_value = []

        self.agent = NetHackAgent(
            llm_client=self.mock_llm,
            skill_library=self.mock_library,
            skill_executor=self.mock_executor,
        )

    @pytest.mark.asyncio
    async def test_step_when_done(self):
        """Test step returns None when done."""
        self.agent.state.running = False
        result = await self.agent.step()
        assert result is None

    @pytest.mark.asyncio
    async def test_step_when_paused(self):
        """Test step returns None when paused."""
        self.agent.state.running = True
        self.agent.state.paused = True
        self.agent._api = MagicMock(is_done=False)

        result = await self.agent.step()
        assert result is None

    @pytest.mark.asyncio
    async def test_step_invoke_skill(self):
        """Test step with invoke_skill decision."""
        mock_api = MagicMock()
        mock_api.is_done = False
        mock_stats = MagicMock(turn=10, hp=20, max_hp=30, dungeon_level=1, score=0, xp_level=1, hunger_state="not hungry")
        mock_api.get_stats.return_value = mock_stats
        mock_api.get_position.return_value = MagicMock(x=5, y=5)
        mock_api.get_visible_monsters.return_value = []
        mock_api.get_items_here.return_value = []
        mock_api.get_message.return_value = ""

        with patch('src.agent.agent.EpisodeMemory') as mock_memory_class:
            mock_memory = MagicMock()
            mock_memory.get_summary.return_value = {}
            mock_memory.get_events.return_value = []
            mock_memory.working = MagicMock()
            mock_memory.working.get_goals.return_value = []
            mock_memory_class.return_value = mock_memory

            self.agent.start_episode(mock_api)

            # Set up LLM response with tool call
            llm_response = MagicMock()
            llm_response.content = ""
            llm_response.tool_call = ToolCall(
                name="invoke_skill",
                arguments={"skill_name": "explore", "reasoning": "test"}
            )
            self.mock_llm.complete_with_tools.return_value = llm_response

            # Set up executor
            execution = MagicMock()
            execution.success = True
            execution.stopped_reason = "completed"
            execution.actions_taken = 5
            execution.turns_elapsed = 3
            self.mock_executor.execute.return_value = execution

            decision = await self.agent.step()

            assert decision is not None
            assert decision.action == ActionType.INVOKE_SKILL
            assert decision.skill_name == "explore"
            assert self.agent.state.decisions_made == 1
            assert self.agent.state.skills_executed == 1
            assert self.agent.state.consecutive_errors == 0

    @pytest.mark.asyncio
    async def test_step_invalid_decision(self):
        """Test step with invalid decision (no tool call)."""
        mock_api = MagicMock()
        mock_api.is_done = False
        mock_stats = MagicMock(turn=10, hp=20, max_hp=30, dungeon_level=1, score=0, xp_level=1, hunger_state="not hungry")
        mock_api.get_stats.return_value = mock_stats
        mock_api.get_position.return_value = MagicMock(x=5, y=5)
        mock_api.get_visible_monsters.return_value = []
        mock_api.get_items_here.return_value = []
        mock_api.get_message.return_value = ""

        with patch('src.agent.agent.EpisodeMemory') as mock_memory_class:
            mock_memory = MagicMock()
            mock_memory.get_summary.return_value = {}
            mock_memory.get_events.return_value = []
            mock_memory.working = MagicMock()
            mock_memory.working.get_goals.return_value = []
            mock_memory_class.return_value = mock_memory

            self.agent.start_episode(mock_api)

            # Set up invalid LLM response (no tool call, falls back to text parsing)
            llm_response = MagicMock()
            llm_response.content = "I don't know what to do"
            llm_response.tool_call = None  # No tool call
            self.mock_llm.complete_with_tools.return_value = llm_response

            decision = await self.agent.step()

            assert decision is not None
            assert not decision.is_valid
            assert self.agent.state.consecutive_errors == 1

    @pytest.mark.asyncio
    async def test_step_exception_handling(self):
        """Test step handles exceptions in LLM call."""
        mock_api = MagicMock()
        mock_api.is_done = False
        mock_stats = MagicMock(turn=10, hp=20, max_hp=30, dungeon_level=1, score=0, xp_level=1, hunger_state="not hungry")
        mock_api.get_stats.return_value = mock_stats
        mock_api.get_position.return_value = MagicMock(x=5, y=5)
        mock_api.get_visible_monsters.return_value = []
        mock_api.get_items_here.return_value = []
        mock_api.get_message.return_value = ""

        with patch('src.agent.agent.EpisodeMemory') as mock_memory_class:
            mock_memory = MagicMock()
            mock_memory.get_summary.return_value = {}
            mock_memory.get_events.return_value = []
            mock_memory.working = MagicMock()
            mock_memory.working.get_goals.return_value = []
            mock_memory_class.return_value = mock_memory

            self.agent.start_episode(mock_api)

            # Make LLM call raise an exception
            self.mock_llm.complete_with_tools.side_effect = RuntimeError("LLM error")

            decision = await self.agent.step()

            assert decision is None
            assert self.agent.state.consecutive_errors == 1
            assert len(self.agent._result.errors) == 1


class TestNetHackAgentRunEpisode:
    """Tests for full episode execution."""

    def setup_method(self):
        """Set up test fixtures."""
        self.mock_llm = MagicMock()
        self.mock_llm.complete_with_tools = AsyncMock()  # async method
        self.mock_library = MagicMock()
        self.mock_executor = AsyncMock()
        self.mock_library.list_skills.return_value = []

        self.agent = NetHackAgent(
            llm_client=self.mock_llm,
            skill_library=self.mock_library,
            skill_executor=self.mock_executor,
            config=AgentConfig(max_turns=10),
        )

    @pytest.mark.asyncio
    async def test_run_episode_game_over(self):
        """Test running episode until game over."""
        mock_api = MagicMock()
        mock_stats = MagicMock(turn=1, hp=20, max_hp=30, dungeon_level=1, score=100, xp_level=1, hunger_state="not hungry")
        mock_api.get_stats.return_value = mock_stats
        mock_api.get_position.return_value = MagicMock(x=5, y=5)
        mock_api.get_visible_monsters.return_value = []
        mock_api.get_items_here.return_value = []
        mock_api.get_message.return_value = ""

        # Game ends after first check
        mock_api.is_done = True

        with patch('src.agent.agent.EpisodeMemory') as mock_memory_class:
            mock_memory = MagicMock()
            mock_memory.get_summary.return_value = {}
            mock_memory.get_events.return_value = []
            mock_memory.working = MagicMock()
            mock_memory.working.get_goals.return_value = []
            mock_memory_class.return_value = mock_memory

            result = await self.agent.run_episode(mock_api)

            assert result is not None
            assert result.final_score == 100

    @pytest.mark.asyncio
    async def test_run_episode_max_errors(self):
        """Test episode ends on max consecutive errors."""
        mock_api = MagicMock()
        mock_api.is_done = False
        mock_stats = MagicMock(turn=1, hp=20, max_hp=30, dungeon_level=1, score=0, xp_level=1, hunger_state="not hungry")
        mock_api.get_stats.return_value = mock_stats
        mock_api.get_position.return_value = MagicMock(x=5, y=5)
        mock_api.get_visible_monsters.return_value = []
        mock_api.get_items_here.return_value = []
        mock_api.get_message.return_value = ""

        with patch('src.agent.agent.EpisodeMemory') as mock_memory_class:
            mock_memory = MagicMock()
            mock_memory.get_summary.return_value = {}
            mock_memory.get_events.return_value = []
            mock_memory.working = MagicMock()
            mock_memory.working.get_goals.return_value = []
            mock_memory_class.return_value = mock_memory

            # Make LLM call raise an exception
            self.mock_llm.complete_with_tools.side_effect = RuntimeError("Repeated LLM error")

            self.agent.config.max_consecutive_errors = 3
            self.agent.config.max_turns = 100  # Override max_turns to allow multiple iterations
            result = await self.agent.run_episode(mock_api)

            assert result is not None
            assert len(result.errors) == 3


class TestAgentConversation:
    """Tests for conversation history management."""

    def setup_method(self):
        """Set up test fixtures."""
        self.mock_llm = MagicMock()
        self.mock_llm.complete_with_tools = AsyncMock()  # async method
        self.mock_library = MagicMock()
        self.mock_executor = AsyncMock()
        self.mock_library.list_skills.return_value = []

        self.agent = NetHackAgent(
            llm_client=self.mock_llm,
            skill_library=self.mock_library,
            skill_executor=self.mock_executor,
        )

    def test_conversation_cleared_on_start(self):
        """Test conversation is cleared on episode start."""
        self.agent._conversation = [{"role": "user", "content": "old"}]

        mock_api = MagicMock()
        with patch('src.agent.agent.EpisodeMemory'):
            self.agent.start_episode(mock_api)
            assert len(self.agent._conversation) == 0

    @pytest.mark.asyncio
    async def test_conversation_history_used(self):
        """Test conversation history is passed to LLM."""
        mock_api = MagicMock()
        mock_api.is_done = False
        mock_stats = MagicMock(turn=10, hp=20, max_hp=30, dungeon_level=1, score=0, xp_level=1, hunger_state="not hungry")
        mock_api.get_stats.return_value = mock_stats
        mock_api.get_position.return_value = MagicMock(x=5, y=5)
        mock_api.get_visible_monsters.return_value = []
        mock_api.get_items_here.return_value = []
        mock_api.get_message.return_value = ""

        with patch('src.agent.agent.EpisodeMemory') as mock_memory_class:
            mock_memory = MagicMock()
            mock_memory.get_summary.return_value = {}
            mock_memory.get_events.return_value = []
            mock_memory.working = MagicMock()
            mock_memory.working.get_goals.return_value = []
            mock_memory_class.return_value = mock_memory

            self.agent.start_episode(mock_api)

            # Add conversation history
            self.agent._conversation = [
                {"role": "user", "content": "prev1"},
                {"role": "assistant", "content": "prev2"},
            ]

            llm_response = MagicMock()
            llm_response.content = ""
            llm_response.tool_call = ToolCall(
                name="look_around",
                arguments={"reasoning": "checking surroundings"}
            )
            self.mock_llm.complete_with_tools.return_value = llm_response

            await self.agent.step()

            # Should use tool calling
            self.mock_llm.complete_with_tools.assert_called_once()
            call_args = self.mock_llm.complete_with_tools.call_args
            messages = call_args.kwargs.get("messages") or call_args[1].get("messages")
            # Messages should include history plus new prompt
            assert len(messages) >= 3  # prev1, prev2, new prompt
