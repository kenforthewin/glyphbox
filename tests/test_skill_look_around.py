"""Tests for the look_around skill."""

import pytest

from src.sandbox.manager import SkillSandbox, SandboxConfig


class TestLookAroundSkillLoading:
    """Tests for loading the look_around skill."""

    def test_skill_exists_in_library(self, skill_library):
        """Test that look_around skill is loaded in the library."""
        skill = skill_library.get("look_around")
        assert skill is not None
        assert skill.name == "look_around"

    def test_skill_category(self, skill_library):
        """Test that look_around is in exploration category."""
        skill = skill_library.get("look_around")
        assert skill is not None
        from src.skills.models import SkillCategory
        assert skill.category == SkillCategory.EXPLORATION

    def test_skill_has_docstring(self, skill_library):
        """Test that skill has a description."""
        skill = skill_library.get("look_around")
        assert skill is not None
        assert skill.description
        assert "spatial" in skill.description.lower() or "view" in skill.description.lower()


class TestLookAroundExecution:
    """Tests for executing the look_around skill."""

    @pytest.fixture
    def sandbox(self):
        """Create a sandbox instance."""
        return SkillSandbox(SandboxConfig(timeout_seconds=10.0))

    @pytest.fixture
    def api(self, nethack_api):
        """Get a reset NetHackAPI instance."""
        nethack_api.reset()
        return nethack_api

    @pytest.mark.asyncio
    async def test_execute_returns_success(self, sandbox, api, skill_library):
        """Test that look_around executes successfully."""
        skill = skill_library.get("look_around")
        assert skill is not None

        result = await sandbox.execute_local(
            code=skill.code,
            skill_name="look_around",
            params={},
            api=api,
        )

        assert result.success is True
        assert result.result is not None
        assert result.result.get("stopped_reason") == "looked"

    @pytest.mark.asyncio
    async def test_returns_zero_actions_and_turns(self, sandbox, api, skill_library):
        """Test that look_around doesn't consume game actions or turns."""
        skill = skill_library.get("look_around")
        result = await sandbox.execute_local(
            code=skill.code,
            skill_name="look_around",
            params={},
            api=api,
        )

        assert result.actions_taken == 0
        assert result.turns_elapsed == 0

    @pytest.mark.asyncio
    async def test_returns_screen_data(self, sandbox, api, skill_library):
        """Test that look_around returns the game screen."""
        skill = skill_library.get("look_around")
        result = await sandbox.execute_local(
            code=skill.code,
            skill_name="look_around",
            params={},
            api=api,
        )

        assert result.success is True
        data = result.result.get("data", {})

        # Should have screen
        assert "screen" in data
        assert isinstance(data["screen"], str)
        assert len(data["screen"]) > 0
        # Screen should contain the player symbol
        assert "@" in data["screen"]

    @pytest.mark.asyncio
    async def test_returns_player_position(self, sandbox, api, skill_library):
        """Test that look_around returns player position."""
        skill = skill_library.get("look_around")
        result = await sandbox.execute_local(
            code=skill.code,
            skill_name="look_around",
            params={},
            api=api,
        )

        data = result.result.get("data", {})
        assert "player_position" in data
        assert "x" in data["player_position"]
        assert "y" in data["player_position"]
        assert isinstance(data["player_position"]["x"], int)
        assert isinstance(data["player_position"]["y"], int)

    @pytest.mark.asyncio
    async def test_returns_monsters_list(self, sandbox, api, skill_library):
        """Test that look_around returns a monsters list."""
        skill = skill_library.get("look_around")
        result = await sandbox.execute_local(
            code=skill.code,
            skill_name="look_around",
            params={},
            api=api,
        )

        data = result.result.get("data", {})
        assert "monsters" in data
        assert isinstance(data["monsters"], list)

        # Each monster should have required fields
        for monster in data["monsters"]:
            assert "name" in monster
            assert "distance" in monster
            assert "direction" in monster
            assert "is_hostile" in monster
            assert "is_adjacent" in monster
            assert "position" in monster

    @pytest.mark.asyncio
    async def test_returns_items_here_list(self, sandbox, api, skill_library):
        """Test that look_around returns items at current position."""
        skill = skill_library.get("look_around")
        result = await sandbox.execute_local(
            code=skill.code,
            skill_name="look_around",
            params={},
            api=api,
        )

        data = result.result.get("data", {})
        assert "items_here" in data
        assert isinstance(data["items_here"], list)

    @pytest.mark.asyncio
    async def test_hint_contains_summary(self, sandbox, api, skill_library):
        """Test that the hint contains a readable summary."""
        skill = skill_library.get("look_around")
        result = await sandbox.execute_local(
            code=skill.code,
            skill_name="look_around",
            params={},
            api=api,
        )

        data = result.result.get("data", {})
        assert "hint" in data
        hint = data["hint"]

        # Hint should contain key sections
        assert "CURRENT VIEW" in hint
        assert "VISIBLE MONSTERS" in hint
        assert "ITEMS HERE" in hint
        assert "GAME SCREEN" in hint
        assert "Position:" in hint
        assert "HP:" in hint


class TestLookAroundMonsterInfo:
    """Tests for monster information in look_around output."""

    @pytest.fixture
    def sandbox(self):
        """Create a sandbox instance."""
        return SkillSandbox(SandboxConfig(timeout_seconds=10.0))

    @pytest.fixture
    def api(self, nethack_api):
        """Get a reset NetHackAPI instance."""
        nethack_api.reset()
        return nethack_api

    @pytest.mark.asyncio
    async def test_monster_direction_is_valid(self, sandbox, api, skill_library):
        """Test that monster directions are valid direction names."""
        skill = skill_library.get("look_around")
        result = await sandbox.execute_local(
            code=skill.code,
            skill_name="look_around",
            params={},
            api=api,
        )

        data = result.result.get("data", {})
        valid_directions = {
            "north", "south", "east", "west",
            "northeast", "northwest", "southeast", "southwest",
            "here", "unknown"
        }

        for monster in data.get("monsters", []):
            assert monster["direction"] in valid_directions

    @pytest.mark.asyncio
    async def test_monster_move_command_is_valid(self, sandbox, api, skill_library):
        """Test that monster move commands are valid direct_action commands."""
        skill = skill_library.get("look_around")
        result = await sandbox.execute_local(
            code=skill.code,
            skill_name="look_around",
            params={},
            api=api,
        )

        data = result.result.get("data", {})
        valid_commands = {
            "move_north", "move_south", "move_east", "move_west",
            "move_ne", "move_nw", "move_se", "move_sw",
            None  # Adjacent monsters don't need a move command
        }

        for monster in data.get("monsters", []):
            assert monster.get("move_command") in valid_commands

    @pytest.mark.asyncio
    async def test_adjacent_monster_marked_correctly(self, sandbox, api, skill_library):
        """Test that adjacent monsters (distance=1) are marked as adjacent."""
        skill = skill_library.get("look_around")
        result = await sandbox.execute_local(
            code=skill.code,
            skill_name="look_around",
            params={},
            api=api,
        )

        data = result.result.get("data", {})

        for monster in data.get("monsters", []):
            if monster["distance"] == 1:
                assert monster["is_adjacent"] is True
            else:
                assert monster["is_adjacent"] is False

    @pytest.mark.asyncio
    async def test_monsters_sorted_by_distance(self, sandbox, api, skill_library):
        """Test that monsters are sorted by distance (closest first)."""
        skill = skill_library.get("look_around")
        result = await sandbox.execute_local(
            code=skill.code,
            skill_name="look_around",
            params={},
            api=api,
        )

        data = result.result.get("data", {})
        monsters = data.get("monsters", [])

        if len(monsters) > 1:
            distances = [m["distance"] for m in monsters]
            assert distances == sorted(distances), "Monsters should be sorted by distance"


class TestLookAroundHintFormat:
    """Tests for the hint text format."""

    @pytest.fixture
    def sandbox(self):
        """Create a sandbox instance."""
        return SkillSandbox(SandboxConfig(timeout_seconds=10.0))

    @pytest.fixture
    def api(self, nethack_api):
        """Get a reset NetHackAPI instance."""
        nethack_api.reset()
        return nethack_api

    @pytest.mark.asyncio
    async def test_hint_includes_move_commands_for_monsters(self, sandbox, api, skill_library):
        """Test that hint includes move commands for non-adjacent monsters."""
        skill = skill_library.get("look_around")
        result = await sandbox.execute_local(
            code=skill.code,
            skill_name="look_around",
            params={},
            api=api,
        )

        data = result.result.get("data", {})
        hint = data.get("hint", "")
        monsters = data.get("monsters", [])

        # For any non-adjacent monster, the hint should mention the move command
        for monster in monsters:
            if not monster["is_adjacent"] and monster.get("move_command"):
                assert monster["move_command"] in hint or "use:" in hint

    @pytest.mark.asyncio
    async def test_hint_labels_hostile_monsters(self, sandbox, api, skill_library):
        """Test that hint clearly labels hostile monsters."""
        skill = skill_library.get("look_around")
        result = await sandbox.execute_local(
            code=skill.code,
            skill_name="look_around",
            params={},
            api=api,
        )

        data = result.result.get("data", {})
        hint = data.get("hint", "")

        # Hint should use clear labeling
        assert "HOSTILE" in hint or "peaceful" in hint or "No monsters visible" in hint

    @pytest.mark.asyncio
    async def test_hint_shows_no_monsters_message(self, sandbox, api, skill_library):
        """Test that hint shows appropriate message when no monsters visible."""
        skill = skill_library.get("look_around")
        result = await sandbox.execute_local(
            code=skill.code,
            skill_name="look_around",
            params={},
            api=api,
        )

        data = result.result.get("data", {})
        hint = data.get("hint", "")
        monsters = data.get("monsters", [])

        if len(monsters) == 0:
            assert "No monsters visible" in hint
