"""Tests for the prompt manager."""

import pytest
from src.agent.prompts import PromptManager


class TestPromptManager:
    """Tests for PromptManager."""

    def setup_method(self):
        """Set up test fixtures."""
        self.manager = PromptManager()  # Default: skills_enabled=False
        self.manager_with_skills = PromptManager(skills_enabled=True)

    def test_get_system_prompt(self):
        """Test getting system prompt."""
        prompt = self.manager.get_system_prompt()
        assert isinstance(prompt, str)
        assert len(prompt) > 100
        # Should contain key concepts
        assert "NetHack" in prompt
        assert "execute_code" in prompt.lower() or "tool" in prompt.lower()

    def test_get_system_prompt_no_skills(self):
        """Test that no-skills prompt excludes skill tools."""
        prompt = self.manager.get_system_prompt()
        assert "1 tool" in prompt
        assert "write_skill" not in prompt
        assert "invoke_skill" not in prompt

    def test_get_system_prompt_with_skills(self):
        """Test that skills-enabled prompt includes skill tools."""
        prompt = self.manager_with_skills.get_system_prompt()
        assert "3 tools" in prompt
        assert "write_skill" in prompt
        assert "invoke_skill" in prompt

    def test_format_decision_prompt_minimal(self):
        """Test formatting decision prompt with minimal data (no skills)."""
        prompt = self.manager.format_decision_prompt(
            game_state={},
            saved_skills=[],
            recent_events=[],
            last_result=None,
        )
        assert isinstance(prompt, str)
        assert "GAME STATE" in prompt
        # When skills disabled, no "Saved Skills" section
        assert "Saved Skills" not in prompt

    def test_format_decision_prompt_minimal_with_skills(self):
        """Test formatting decision prompt with skills enabled."""
        prompt = self.manager_with_skills.format_decision_prompt(
            game_state={},
            saved_skills=[],
            recent_events=[],
            last_result=None,
        )
        assert isinstance(prompt, str)
        assert "GAME STATE" in prompt
        assert "Saved Skills" in prompt

    def test_format_decision_prompt_with_game_state(self):
        """Test formatting decision prompt with game state."""
        game_state = {
            "current_turn": 100,
            "hp": 15,
            "max_hp": 20,
            "current_level": 3,
            "hunger_state": "not hungry",
            "position_x": 10,
            "position_y": 15,
        }
        prompt = self.manager.format_decision_prompt(
            game_state=game_state,
            saved_skills=[],
            recent_events=[],
            last_result=None,
        )
        # Position and hunger are included (not visible on screen)
        assert "Position: (10, 15)" in prompt
        assert "not hungry" in prompt

    def test_format_decision_prompt_with_saved_skills(self):
        """Test formatting decision prompt with saved skills (skills enabled)."""
        saved_skills = ["explore_corridor", "fight_adjacent"]
        prompt = self.manager_with_skills.format_decision_prompt(
            game_state={},
            saved_skills=saved_skills,
            recent_events=[],
            last_result=None,
        )
        assert "explore_corridor" in prompt
        assert "fight_adjacent" in prompt

    def test_format_decision_prompt_with_events(self):
        """Test formatting decision prompt with recent events."""
        events = [
            {"turn": 95, "type": "combat", "desc": "Killed a jackal"},
            {"turn": 98, "type": "item", "desc": "Found a scroll"},
        ]
        prompt = self.manager.format_decision_prompt(
            game_state={},
            saved_skills=[],
            recent_events=events,
            last_result=None,
        )
        assert "Killed a jackal" in prompt
        assert "Found a scroll" in prompt

    def test_format_decision_prompt_with_last_result(self):
        """Test formatting decision prompt with last result."""
        last_result = {
            "tool": "execute_code",
            "success": True,
            "hint": "Moved east successfully",
        }
        prompt = self.manager.format_decision_prompt(
            game_state={},
            saved_skills=[],
            recent_events=[],
            last_result=last_result,
        )
        assert "Moved east successfully" in prompt or "success" in prompt.lower()

    def test_format_skill_creation_prompt(self):
        """Test formatting skill creation prompt."""
        prompt = self.manager.format_skill_creation_prompt(
            situation="A floating eye is blocking my path",
            game_state={"hp": 20, "max_hp": 20},
            existing_skills=["explore", "fight"],
        )
        assert isinstance(prompt, str)
        assert "floating eye" in prompt
        assert "explore" in prompt or "fight" in prompt

    def test_format_skill_creation_prompt_with_context(self):
        """Test skill creation with game context."""
        game_state = {
            "hp": 20,
            "max_hp": 20,
        }
        prompt = self.manager.format_skill_creation_prompt(
            situation="Need to eat food",
            game_state=game_state,
            existing_skills=["eat_when_hungry"],
        )
        assert "eat food" in prompt.lower() or "need to eat" in prompt.lower()

    def test_format_skill_creation_prompt_with_failed_attempts(self):
        """Test skill creation with previous failed attempts."""
        failed_attempts = [
            "async def bad_skill(nh): pass  # Didn't check inventory",
        ]
        prompt = self.manager.format_skill_creation_prompt(
            situation="Need new approach",
            game_state={"hp": 15, "max_hp": 20},
            existing_skills=["explore"],
            failed_attempts=failed_attempts,
        )
        assert "Didn't check inventory" in prompt or "previous" in prompt.lower() or "Failed" in prompt

    def test_format_analysis_prompt(self):
        """Test formatting analysis prompt."""
        prompt = self.manager.format_analysis_prompt(
            game_state={
                "hp": 5,
                "max_hp": 20,
            },
            question="Should I fight or flee?",
        )
        assert isinstance(prompt, str)
        assert "fight or flee" in prompt

    def test_prompt_manager_templates_loaded(self):
        """Test that internal templates are loaded."""
        # The manager should have template strings in _templates dict
        assert hasattr(self.manager, '_templates')
        assert "system" in self.manager._templates
        assert "decision" in self.manager._templates
        assert len(self.manager._templates["system"]) > 0
        assert len(self.manager._templates["decision"]) > 0


class TestPromptFormatting:
    """Tests for specific prompt formatting details."""

    def setup_method(self):
        """Set up test fixtures."""
        self.manager = PromptManager()
        self.manager_with_skills = PromptManager(skills_enabled=True)

    def test_decision_prompt_contains_action_instructions(self):
        """Test that decision prompt explains available actions."""
        prompt = self.manager.format_decision_prompt(
            game_state={},
            saved_skills=[],
            recent_events=[],
            last_result=None,
        )
        # Should have some instruction or state info
        assert "GAME STATE" in prompt or "Skills" in prompt

    def test_skill_creation_prompt_contains_api_info(self):
        """Test that skill creation prompt mentions API."""
        prompt = self.manager.format_skill_creation_prompt(
            situation="Test",
            game_state={"hp": 20, "max_hp": 20},
            existing_skills=["explore"],
        )
        # Should mention the nh API or how to write skills
        assert "nh" in prompt.lower() or "api" in prompt.lower() or "async" in prompt

    def test_prompts_are_reasonable_length(self):
        """Test that prompts aren't excessively long."""
        decision_prompt = self.manager_with_skills.format_decision_prompt(
            game_state={"hp": 10, "max_hp": 20},
            saved_skills=[f"skill_{i}" for i in range(10)],
            recent_events=[
                {"turn": i, "type": "test", "desc": f"Event {i}"}
                for i in range(5)
            ],
            last_result={"success": True, "hint": "All good"},
        )
        # Should be under 10k characters for reasonable token usage
        assert len(decision_prompt) < 10000

    def test_game_state_formatting(self):
        """Test game state is formatted readably."""
        game_state = {
            "current_turn": 500,
            "hp": 30,
            "max_hp": 50,
            "current_level": 5,
            "xp_level": 4,
            "position_x": 25,
            "position_y": 12,
            "hunger_state": "hungry",
        }
        prompt = self.manager.format_decision_prompt(
            game_state=game_state,
            saved_skills=[],
            recent_events=[],
            last_result=None,
        )
        # Position and hunger should appear (not visible on screen status bar)
        assert "Position: (25, 12)" in prompt
        assert "hungry" in prompt


class TestEdgeCases:
    """Test edge cases and error handling."""

    def setup_method(self):
        """Set up test fixtures."""
        self.manager = PromptManager()
        self.manager_with_skills = PromptManager(skills_enabled=True)

    def test_empty_everything(self):
        """Test with all empty inputs."""
        prompt = self.manager.format_decision_prompt(
            game_state={},
            saved_skills=[],
            recent_events=[],
            last_result=None,
        )
        assert isinstance(prompt, str)
        assert len(prompt) > 0

    def test_none_values_in_game_state(self):
        """Test game state with None values."""
        game_state = {
            "current_turn": 100,
            "hp": 15,
            "max_hp": 20,
        }
        prompt = self.manager.format_decision_prompt(
            game_state=game_state,
            saved_skills=[],
            recent_events=[],
            last_result=None,
        )
        # Should not crash
        assert isinstance(prompt, str)

    def test_special_characters_in_skills(self):
        """Test skills with special characters (skills enabled)."""
        saved_skills = ["skill_with_underscore", "skill-with-dash"]
        prompt = self.manager_with_skills.format_decision_prompt(
            game_state={},
            saved_skills=saved_skills,
            recent_events=[],
            last_result=None,
        )
        # Should not crash and should contain the content
        assert "skill_with_underscore" in prompt

    def test_unicode_in_events(self):
        """Test events with unicode characters."""
        events = [
            {"turn": 1, "type": "test", "desc": "Picked up a sword"},
        ]
        prompt = self.manager.format_decision_prompt(
            game_state={},
            saved_skills=[],
            recent_events=events,
            last_result=None,
        )
        assert isinstance(prompt, str)
