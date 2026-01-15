"""Tests for data models."""

import pytest

from src.api.models import (
    ActionResult,
    Alignment,
    Direction,
    Encumbrance,
    HungerState,
    ObjectClass,
    Position,
    SkillResult,
    Stats,
)


class TestPosition:
    """Tests for Position dataclass."""

    def test_creation(self):
        pos = Position(10, 20)
        assert pos.x == 10
        assert pos.y == 20

    def test_equality(self):
        pos1 = Position(5, 5)
        pos2 = Position(5, 5)
        pos3 = Position(5, 6)
        assert pos1 == pos2
        assert pos1 != pos3

    def test_hashable(self):
        """Position should be usable in sets and as dict keys."""
        pos1 = Position(1, 2)
        pos2 = Position(1, 2)
        pos3 = Position(3, 4)

        s = {pos1, pos2, pos3}
        assert len(s) == 2  # pos1 and pos2 are equal

        d = {pos1: "a", pos3: "b"}
        assert d[pos2] == "a"  # pos2 equals pos1

    def test_distance_to(self):
        pos1 = Position(0, 0)
        pos2 = Position(3, 4)
        assert pos1.distance_to(pos2) == 4  # Chebyshev distance (max of dx, dy)

    def test_direction_to(self):
        center = Position(5, 5)

        assert center.direction_to(Position(5, 4)) == Direction.N
        assert center.direction_to(Position(5, 6)) == Direction.S
        assert center.direction_to(Position(6, 5)) == Direction.E
        assert center.direction_to(Position(4, 5)) == Direction.W
        assert center.direction_to(Position(6, 4)) == Direction.NE
        assert center.direction_to(Position(4, 4)) == Direction.NW
        assert center.direction_to(Position(6, 6)) == Direction.SE
        assert center.direction_to(Position(4, 6)) == Direction.SW
        assert center.direction_to(Position(5, 5)) == Direction.SELF

    def test_adjacent(self):
        pos = Position(5, 5)
        adj = pos.adjacent()
        assert len(adj) == 8
        assert Position(5, 4) in adj  # N
        assert Position(6, 5) in adj  # E
        assert Position(4, 6) in adj  # SW

    def test_move(self):
        pos = Position(5, 5)
        assert pos.move(Direction.N) == Position(5, 4)
        assert pos.move(Direction.SE) == Position(6, 6)
        assert pos.move(Direction.SELF) == Position(5, 5)

    def test_add_tuple(self):
        pos = Position(5, 5)
        assert pos + (1, 2) == Position(6, 7)
        assert pos + (-1, -1) == Position(4, 4)


class TestDirection:
    """Tests for Direction enum."""

    def test_delta(self):
        assert Direction.N.delta == (0, -1)
        assert Direction.SE.delta == (1, 1)
        assert Direction.SELF.delta == (0, 0)

    def test_all_directions(self):
        """All 8 compass directions plus up/down/self should exist."""
        directions = [Direction.N, Direction.S, Direction.E, Direction.W,
                      Direction.NE, Direction.NW, Direction.SE, Direction.SW,
                      Direction.UP, Direction.DOWN, Direction.SELF]
        assert len(directions) == 11


class TestEnums:
    """Tests for various enums."""

    def test_hunger_from_blstats(self):
        assert HungerState.from_blstats(0) == HungerState.SATIATED
        assert HungerState.from_blstats(1) == HungerState.NOT_HUNGRY
        assert HungerState.from_blstats(2) == HungerState.HUNGRY
        assert HungerState.from_blstats(3) == HungerState.WEAK
        assert HungerState.from_blstats(99) == HungerState.NOT_HUNGRY  # Unknown defaults

    def test_alignment_from_blstats(self):
        assert Alignment.from_blstats(-5) == Alignment.CHAOTIC
        assert Alignment.from_blstats(0) == Alignment.NEUTRAL
        assert Alignment.from_blstats(10) == Alignment.LAWFUL

    def test_encumbrance_from_blstats(self):
        assert Encumbrance.from_blstats(0) == Encumbrance.UNENCUMBERED
        assert Encumbrance.from_blstats(1) == Encumbrance.BURDENED
        assert Encumbrance.from_blstats(5) == Encumbrance.OVERLOADED

    def test_object_class_from_oclass(self):
        assert ObjectClass.from_oclass(2) == ObjectClass.WEAPON
        assert ObjectClass.from_oclass(3) == ObjectClass.ARMOR
        assert ObjectClass.from_oclass(7) == ObjectClass.FOOD


class TestActionResult:
    """Tests for ActionResult dataclass."""

    def test_success(self):
        result = ActionResult.ok(["You hit the goblin!"])
        assert result.success is True
        assert "You hit the goblin!" in result.messages

    def test_failure(self):
        result = ActionResult.failure("Cannot move there")
        assert result.success is False
        assert result.error == "Cannot move there"
        assert result.turn_elapsed is False


class TestSkillResult:
    """Tests for SkillResult dataclass."""

    def test_stopped(self):
        result = SkillResult.stopped(
            reason="monster_spotted",
            success=False,
            actions=10,
            turns=12,
            monster="goblin",
        )
        assert result.stopped_reason == "monster_spotted"
        assert result.success is False
        assert result.actions_taken == 10
        assert result.turns_elapsed == 12
        assert result.data["monster"] == "goblin"
