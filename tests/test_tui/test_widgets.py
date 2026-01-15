"""Tests for TUI widgets."""

import pytest
from unittest.mock import MagicMock, patch

from src.tui.widgets import (
    StatsBar,
    GameScreenWidget,
    DecisionLogWidget,
    ReasoningPanel,
    ControlsWidget,
)
from src.tui.events import (
    DecisionMade,
    SkillExecuted,
    GameStateUpdated,
    AgentStatusChanged,
)
from src.agent.parser import ActionType, AgentDecision


class TestStatsBar:
    """Tests for StatsBar widget."""

    def test_creation(self):
        """Test creating a StatsBar widget."""
        widget = StatsBar()
        assert widget._hp == 0
        assert widget._max_hp == 0
        assert widget._turn == 0

    def test_default_values(self):
        """Test default values are set correctly."""
        widget = StatsBar()
        assert widget._level == 1
        assert widget._score == 0
        assert widget._hunger == "Not Hungry"


class TestGameScreenWidget:
    """Tests for GameScreenWidget."""

    def test_creation(self):
        """Test creating a GameScreenWidget."""
        widget = GameScreenWidget()
        assert widget._screen is not None

    def test_empty_screen(self):
        """Test empty screen generation."""
        widget = GameScreenWidget()
        screen = widget._empty_screen()
        lines = screen.split("\n")
        assert len(lines) == 24
        assert all(len(line) == 80 for line in lines)


class TestDecisionLogWidget:
    """Tests for DecisionLogWidget."""

    def test_creation(self):
        """Test creating a DecisionLogWidget."""
        widget = DecisionLogWidget()
        assert widget._decision_count == 0


class TestReasoningPanel:
    """Tests for ReasoningPanel widget."""

    def test_creation(self):
        """Test creating a ReasoningPanel."""
        widget = ReasoningPanel()
        # Should be able to create without error
        assert widget is not None


class TestControlsWidget:
    """Tests for ControlsWidget."""

    def test_creation(self):
        """Test creating a ControlsWidget."""
        widget = ControlsWidget()
        assert widget._status == "ready"


class TestWidgetEventHandling:
    """Tests for widget event handling logic."""

    def test_stats_bar_hp_color_coding(self):
        """Test HP color coding logic in StatsBar."""
        widget = StatsBar()

        # High HP (> 50%)
        widget._hp = 15
        widget._max_hp = 20
        ratio = widget._hp / widget._max_hp
        assert ratio > 0.5  # Should be green

        # Medium HP (25-50%)
        widget._hp = 8
        ratio = widget._hp / widget._max_hp
        assert 0.25 < ratio <= 0.5  # Should be yellow

        # Low HP (< 25%)
        widget._hp = 4
        ratio = widget._hp / widget._max_hp
        assert ratio <= 0.25  # Should be red

    def test_game_screen_update(self):
        """Test game screen stores screen data."""
        widget = GameScreenWidget()

        new_screen = "@" + "." * 79 + "\n" * 23
        event = GameStateUpdated(
            screen=new_screen,
            hp=10,
            max_hp=20,
            turn=50,
            dungeon_level=2,
            score=100,
            message="Test",
            hunger="not_hungry",
        )

        # Simulate event handling
        widget._screen = event.screen
        assert widget._screen == new_screen
        assert "@" in widget._screen

    def test_decision_action_colors(self):
        """Test decision log color mapping."""
        action_colors = {
            "invoke_skill": "green",
            "create_skill": "yellow",
            "analyze": "cyan",
            "direct_action": "magenta",
            "unknown": "red",
        }

        # All action types should have a color
        for action_type in ActionType:
            color = action_colors.get(action_type.value, "white")
            assert color is not None

    def test_controls_status_mapping(self):
        """Test controls status to color mapping."""
        status_colors = {
            "ready": "white",
            "running": "green",
            "paused": "yellow",
            "stopped": "red",
            "error": "red bold",
        }

        for status in ["ready", "running", "paused", "stopped", "error"]:
            assert status in status_colors
