"""Tests for action execution."""

import pytest

from src.api.actions import ActionExecutor
from src.api.models import Direction, ActionResult


class TestActionExecutorBasic:
    """Basic tests for ActionExecutor that don't require NLE."""

    def test_direction_keys_mapping(self, nle_env):
        """Test that direction key mappings are correct."""
        executor = ActionExecutor(nle_env)

        # Check that vi-keys are mapped
        assert executor._direction_keys[Direction.N] == ord("k")
        assert executor._direction_keys[Direction.S] == ord("j")
        assert executor._direction_keys[Direction.E] == ord("l")
        assert executor._direction_keys[Direction.W] == ord("h")
        assert executor._direction_keys[Direction.NE] == ord("u")
        assert executor._direction_keys[Direction.NW] == ord("y")
        assert executor._direction_keys[Direction.SE] == ord("n")
        assert executor._direction_keys[Direction.SW] == ord("b")


class TestMovement:
    """Tests for movement actions."""

    def test_move_north(self, nle_env):
        """Test moving north."""
        nle_env.reset()
        executor = ActionExecutor(nle_env)

        result = executor.move(Direction.N)

        assert isinstance(result, ActionResult)
        # Result may or may not be successful depending on game state

    def test_move_invalid_direction(self, nle_env):
        """Test moving in UP direction (stairs, not movement)."""
        nle_env.reset()
        executor = ActionExecutor(nle_env)

        # UP/DOWN are for stairs, not movement, but should still work
        result = executor.move(Direction.UP)
        assert isinstance(result, ActionResult)

    def test_wait_action(self, nle_env):
        """Test wait action."""
        nle_env.reset()
        executor = ActionExecutor(nle_env)

        result = executor.wait()

        assert result.success is True
        assert result.turn_elapsed is True

    def test_search_action(self, nle_env):
        """Test search action."""
        nle_env.reset()
        executor = ActionExecutor(nle_env)

        result = executor.search()

        assert result.success is True


class TestCombat:
    """Tests for combat actions."""

    def test_attack_direction(self, nle_env):
        """Test attack in a direction."""
        nle_env.reset()
        executor = ActionExecutor(nle_env)

        # Attack north (may or may not hit anything)
        result = executor.attack(Direction.N)

        assert isinstance(result, ActionResult)

    def test_kick_direction(self, nle_env):
        """Test kick in a direction."""
        nle_env.reset()
        executor = ActionExecutor(nle_env)

        # Kick north
        result = executor.kick(Direction.N)

        assert isinstance(result, ActionResult)


class TestItems:
    """Tests for item actions."""

    def test_pickup(self, nle_env):
        """Test pickup action."""
        nle_env.reset()
        executor = ActionExecutor(nle_env)

        # Pickup (may or may not have items)
        result = executor.pickup()

        assert isinstance(result, ActionResult)

    def test_eat_action(self, nle_env):
        """Test eat action."""
        nle_env.reset()
        executor = ActionExecutor(nle_env)

        # Try to eat (may prompt for food selection)
        result = executor.eat()

        assert isinstance(result, ActionResult)


class TestUtility:
    """Tests for utility actions."""

    def test_look_action(self, nle_env):
        """Test look action."""
        nle_env.reset()
        executor = ActionExecutor(nle_env)

        result = executor.look()

        assert result.success is True

    def test_pray_action(self, nle_env):
        """Test pray action."""
        nle_env.reset()
        executor = ActionExecutor(nle_env)

        result = executor.pray()

        # Pray works, though may have consequences
        assert isinstance(result, ActionResult)

    def test_escape_action(self, nle_env):
        """Test escape key."""
        nle_env.reset()
        executor = ActionExecutor(nle_env)

        result = executor.escape()

        assert isinstance(result, ActionResult)

    def test_space_action(self, nle_env):
        """Test space key (dismiss message)."""
        nle_env.reset()
        executor = ActionExecutor(nle_env)

        result = executor.space()

        assert isinstance(result, ActionResult)


class TestRawActions:
    """Tests for raw action sending."""

    def test_send_keys(self, nle_env):
        """Test sending raw keys."""
        nle_env.reset()
        executor = ActionExecutor(nle_env)

        # Send a wait command
        result = executor.send_keys(".")

        assert result.success is True

    def test_send_action_index(self, nle_env):
        """Test sending raw action index."""
        nle_env.reset()
        executor = ActionExecutor(nle_env)

        # Send action index 0 (whatever that is)
        result = executor.send_action(0)

        assert isinstance(result, ActionResult)


class TestMultiStepActions:
    """Tests for actions that require multiple keypresses."""

    def test_open_door_direction(self, nle_env):
        """Test open door action."""
        nle_env.reset()
        executor = ActionExecutor(nle_env)

        # Try to open door north (may or may not have door)
        result = executor.open_door(Direction.N)

        assert isinstance(result, ActionResult)

    def test_close_door_direction(self, nle_env):
        """Test close door action."""
        nle_env.reset()
        executor = ActionExecutor(nle_env)

        result = executor.close_door(Direction.N)

        assert isinstance(result, ActionResult)

    def test_drop_item(self, nle_env):
        """Test drop item action."""
        nle_env.reset()
        executor = ActionExecutor(nle_env)

        # Try to drop item 'a' (may or may not exist)
        result = executor.drop("a")

        assert isinstance(result, ActionResult)

    def test_throw_item(self, nle_env):
        """Test throw item action."""
        nle_env.reset()
        executor = ActionExecutor(nle_env)

        # Try to throw item 'a' north
        result = executor.throw("a", Direction.N)

        assert isinstance(result, ActionResult)
