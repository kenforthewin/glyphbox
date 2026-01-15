"""Tests for TUI events."""

import pytest
import time

from src.tui.events import (
    DecisionMade,
    SkillExecuted,
    GameStateUpdated,
    AgentStatusChanged,
)
from src.agent.parser import ActionType, AgentDecision


class TestDecisionMade:
    """Tests for DecisionMade event."""

    def test_creation(self):
        """Test creating a DecisionMade event."""
        decision = AgentDecision(
            action=ActionType.INVOKE_SKILL,
            skill_name="explore",
            reasoning="Need to explore",
        )
        event = DecisionMade(
            decision=decision,
            turn=100,
            timestamp=time.time(),
        )

        assert event.decision == decision
        assert event.turn == 100
        assert event.timestamp > 0

    def test_decision_with_code(self):
        """Test DecisionMade with write_skill action."""
        decision = AgentDecision(
            action=ActionType.WRITE_SKILL,
            skill_name="flee",
            code="async def flee(nh): pass",
            reasoning="Need escape skill",
        )
        event = DecisionMade(
            decision=decision,
            turn=50,
            timestamp=time.time(),
        )

        assert event.decision.code is not None
        assert event.decision.action == ActionType.WRITE_SKILL


class TestSkillExecuted:
    """Tests for SkillExecuted event."""

    def test_success(self):
        """Test successful skill execution event."""
        event = SkillExecuted(
            skill_name="explore",
            success=True,
            stopped_reason="reached_stairs",
            actions=45,
            turns=30,
        )

        assert event.skill_name == "explore"
        assert event.success is True
        assert event.stopped_reason == "reached_stairs"
        assert event.actions == 45
        assert event.turns == 30

    def test_failure(self):
        """Test failed skill execution event."""
        event = SkillExecuted(
            skill_name="fight",
            success=False,
            stopped_reason="low_hp",
            actions=10,
            turns=5,
        )

        assert event.success is False
        assert event.stopped_reason == "low_hp"


class TestGameStateUpdated:
    """Tests for GameStateUpdated event."""

    def test_creation(self):
        """Test creating a GameStateUpdated event."""
        screen = "." * 80 + "\n" * 24
        event = GameStateUpdated(
            screen=screen,
            hp=15,
            max_hp=20,
            turn=100,
            dungeon_level=3,
            score=250,
            message="You see a goblin.",
            hunger="not_hungry",
        )

        assert event.hp == 15
        assert event.max_hp == 20
        assert event.turn == 100
        assert event.dungeon_level == 3
        assert event.score == 250
        assert event.message == "You see a goblin."
        assert event.hunger == "not_hungry"

    def test_low_hp(self):
        """Test event with low HP."""
        event = GameStateUpdated(
            screen="",
            hp=3,
            max_hp=20,
            turn=200,
            dungeon_level=5,
            score=100,
            message="You feel weak!",
            hunger="weak",
        )

        assert event.hp == 3
        assert event.hunger == "weak"


class TestAgentStatusChanged:
    """Tests for AgentStatusChanged event."""

    def test_running(self):
        """Test running status."""
        event = AgentStatusChanged(status="running")
        assert event.status == "running"
        assert event.error_message is None

    def test_paused(self):
        """Test paused status."""
        event = AgentStatusChanged(status="paused")
        assert event.status == "paused"

    def test_stopped(self):
        """Test stopped status."""
        event = AgentStatusChanged(status="stopped")
        assert event.status == "stopped"

    def test_error_with_message(self):
        """Test error status with message."""
        event = AgentStatusChanged(
            status="error",
            error_message="Connection lost",
        )
        assert event.status == "error"
        assert event.error_message == "Connection lost"
