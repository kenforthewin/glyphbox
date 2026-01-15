"""Tests for the decision parser."""

import pytest
from src.agent.parser import (
    ActionType,
    AgentDecision,
    DecisionParser,
    extract_skill_name_from_code,
    validate_skill_code,
)


class TestActionType:
    """Tests for ActionType enum."""

    def test_action_types_exist(self):
        """Test all expected action types exist."""
        assert ActionType.EXECUTE_CODE.value == "execute_code"
        assert ActionType.WRITE_SKILL.value == "write_skill"
        assert ActionType.INVOKE_SKILL.value == "invoke_skill"
        assert ActionType.UNKNOWN.value == "unknown"


class TestAgentDecision:
    """Tests for AgentDecision dataclass."""

    def test_execute_code_valid(self):
        """Test valid execute_code decision."""
        decision = AgentDecision(
            action=ActionType.EXECUTE_CODE,
            code="nh.move(Direction.E); nh.pickup()",
            reasoning="Moving east and picking up",
        )
        assert decision.is_valid
        assert decision.code == "nh.move(Direction.E); nh.pickup()"

    def test_execute_code_missing_code(self):
        """Test execute_code without code is invalid."""
        decision = AgentDecision(
            action=ActionType.EXECUTE_CODE,
            code=None,
        )
        assert not decision.is_valid

    def test_write_skill_valid(self):
        """Test valid write_skill decision."""
        code = """
async def flee_from_danger(nh, **params):
    return SkillResult.success()
"""
        decision = AgentDecision(
            action=ActionType.WRITE_SKILL,
            skill_name="flee_from_danger",
            code=code,
        )
        assert decision.is_valid

    def test_write_skill_missing_name(self):
        """Test write_skill without name is invalid."""
        decision = AgentDecision(
            action=ActionType.WRITE_SKILL,
            skill_name=None,
            code="async def test(nh): pass",
        )
        assert not decision.is_valid

    def test_write_skill_missing_code(self):
        """Test write_skill without code is invalid."""
        decision = AgentDecision(
            action=ActionType.WRITE_SKILL,
            skill_name="test_skill",
            code=None,
        )
        assert not decision.is_valid

    def test_invoke_skill_valid(self):
        """Test valid invoke_skill decision."""
        decision = AgentDecision(
            action=ActionType.INVOKE_SKILL,
            skill_name="explore_dungeon",
            params={"max_steps": 100},
        )
        assert decision.is_valid
        assert decision.skill_name == "explore_dungeon"
        assert decision.params == {"max_steps": 100}

    def test_invoke_skill_missing_name(self):
        """Test invoke_skill without name is invalid."""
        decision = AgentDecision(
            action=ActionType.INVOKE_SKILL,
            skill_name=None,
        )
        assert not decision.is_valid

    def test_parse_error_makes_invalid(self):
        """Test that parse_error makes decision invalid."""
        decision = AgentDecision(
            action=ActionType.INVOKE_SKILL,
            skill_name="explore",
            parse_error="Invalid JSON",
        )
        assert not decision.is_valid

    def test_to_dict(self):
        """Test conversion to dictionary."""
        decision = AgentDecision(
            action=ActionType.INVOKE_SKILL,
            skill_name="explore",
            params={"depth": 5},
            reasoning="Need to explore",
        )
        d = decision.to_dict()
        assert d["action"] == "invoke_skill"
        assert d["skill_name"] == "explore"
        assert d["params"] == {"depth": 5}
        assert d["reasoning"] == "Need to explore"
        assert d["is_valid"] is True


class TestDecisionParser:
    """Tests for DecisionParser."""

    def setup_method(self):
        """Set up test fixtures."""
        self.parser = DecisionParser()

    def test_parse_json_block(self):
        """Test parsing JSON in code block."""
        response = """
I'll explore the dungeon.

```json
{
    "action": "invoke_skill",
    "skill_name": "cautious_explore",
    "params": {"max_steps": 50},
    "reasoning": "Need to find stairs"
}
```
"""
        decision = self.parser.parse(response)
        assert decision.action == ActionType.INVOKE_SKILL
        assert decision.skill_name == "cautious_explore"
        assert decision.params == {"max_steps": 50}
        assert decision.reasoning == "Need to find stairs"
        assert decision.is_valid

    def test_parse_bare_json(self):
        """Test parsing bare JSON without code block."""
        response = """
{"action": "invoke_skill", "skill_name": "fight_monster", "reasoning": "Combat time"}
"""
        decision = self.parser.parse(response)
        assert decision.action == ActionType.INVOKE_SKILL
        assert decision.skill_name == "fight_monster"
        assert decision.is_valid

    def test_parse_execute_code(self):
        """Test parsing execute_code decision."""
        response = """
```json
{
    "action": "execute_code",
    "code": "nh.move(Direction.E)\\nnh.pickup()",
    "reasoning": "Moving east and picking up"
}
```
"""
        decision = self.parser.parse(response)
        assert decision.action == ActionType.EXECUTE_CODE
        assert decision.code is not None
        assert "nh.move" in decision.code
        assert decision.is_valid

    def test_parse_write_skill(self):
        """Test parsing write_skill decision."""
        response = """
```json
{
    "action": "write_skill",
    "skill_name": "flee_from_monster",
    "reasoning": "Need escape skill"
}
```

```python
async def flee_from_monster(nh, **params):
    \"\"\"Flee from nearby monsters.\"\"\"
    return SkillResult.success()
```
"""
        decision = self.parser.parse(response)
        assert decision.action == ActionType.WRITE_SKILL
        assert decision.skill_name == "flee_from_monster"
        assert decision.code is not None
        assert "async def flee_from_monster" in decision.code
        assert decision.is_valid

    def test_parse_no_json(self):
        """Test parsing response with no JSON."""
        response = "I think we should explore the dungeon carefully."
        decision = self.parser.parse(response)
        assert not decision.is_valid
        assert decision.parse_error == "No JSON found in response"

    def test_parse_invalid_json(self):
        """Test parsing invalid JSON."""
        response = """
```json
{action: "invoke_skill", skill_name: "test"}
```
"""
        decision = self.parser.parse(response)
        assert not decision.is_valid
        assert "Invalid JSON" in decision.parse_error

    def test_parse_unknown_action(self):
        """Test parsing unknown action type."""
        response = """
{"action": "do_something_weird", "skill_name": "test"}
"""
        decision = self.parser.parse(response)
        assert decision.action == ActionType.UNKNOWN
        assert not decision.is_valid
        assert "Unknown action type" in decision.parse_error

    def test_parse_invoke_skill_no_name(self):
        """Test invoke_skill without skill_name."""
        response = """
{"action": "invoke_skill", "reasoning": "test"}
"""
        decision = self.parser.parse(response)
        assert not decision.is_valid
        assert "requires skill_name" in decision.parse_error

    def test_parse_execute_code_no_code(self):
        """Test execute_code without code."""
        response = """
{"action": "execute_code", "reasoning": "test"}
"""
        decision = self.parser.parse(response)
        assert not decision.is_valid
        assert "requires code" in decision.parse_error

    def test_parse_write_skill_no_name(self):
        """Test write_skill without skill_name."""
        response = """
{"action": "write_skill", "code": "async def test(nh): pass"}
"""
        decision = self.parser.parse(response)
        assert not decision.is_valid
        assert "requires skill_name" in decision.parse_error

    def test_parse_write_skill_no_code(self):
        """Test write_skill without code."""
        response = """
{"action": "write_skill", "skill_name": "test"}
"""
        decision = self.parser.parse(response)
        assert not decision.is_valid
        assert "requires code" in decision.parse_error

    def test_parse_with_name_field(self):
        """Test parsing with 'name' instead of 'skill_name'."""
        response = """
{"action": "invoke_skill", "name": "explore"}
"""
        decision = self.parser.parse(response)
        assert decision.skill_name == "explore"
        assert decision.is_valid

    def test_parse_multiple_decisions(self):
        """Test parsing multiple decisions."""
        response = """
First action:
```json
{"action": "invoke_skill", "skill_name": "explore"}
```

Second action:
```json
{"action": "invoke_skill", "skill_name": "fight"}
```
"""
        decisions = self.parser.parse_multiple(response)
        assert len(decisions) == 2
        assert decisions[0].skill_name == "explore"
        assert decisions[1].skill_name == "fight"

    def test_parse_multiple_no_decisions(self):
        """Test parse_multiple falls back to single parse."""
        response = "No JSON here"
        decisions = self.parser.parse_multiple(response)
        assert len(decisions) == 1
        assert not decisions[0].is_valid

    def test_raw_response_preserved(self):
        """Test that raw response is preserved."""
        response = '{"action": "invoke_skill", "skill_name": "test"}'
        decision = self.parser.parse(response)
        assert decision.raw_response == response


class TestExtractSkillNameFromCode:
    """Tests for extract_skill_name_from_code function."""

    def test_extract_simple(self):
        """Test extracting name from simple function."""
        code = "async def my_skill(nh): pass"
        assert extract_skill_name_from_code(code) == "my_skill"

    def test_extract_with_params(self):
        """Test extracting name with parameters."""
        code = "async def complex_skill(nh, param1, **kwargs): pass"
        assert extract_skill_name_from_code(code) == "complex_skill"

    def test_extract_no_function(self):
        """Test with no function definition."""
        code = "x = 1 + 2"
        assert extract_skill_name_from_code(code) is None

    def test_extract_sync_function(self):
        """Test with sync function (should not match)."""
        code = "def sync_skill(nh): pass"
        assert extract_skill_name_from_code(code) is None


class TestValidateSkillCode:
    """Tests for validate_skill_code function."""

    def test_valid_code(self):
        """Test valid skill code."""
        code = """
async def valid_skill(nh, **params):
    return SkillResult.success()
"""
        is_valid, error = validate_skill_code(code)
        assert is_valid
        assert error is None

    def test_empty_code(self):
        """Test empty code."""
        is_valid, error = validate_skill_code("")
        assert not is_valid
        assert "No code provided" in error

    def test_no_async(self):
        """Test code without async."""
        code = "def sync_skill(nh): return None"
        is_valid, error = validate_skill_code(code)
        assert not is_valid
        assert "async function" in error

    def test_no_nh_param(self):
        """Test code without nh parameter."""
        code = "async def bad_skill(api): return None"
        is_valid, error = validate_skill_code(code)
        assert not is_valid
        assert "'nh'" in error

    def test_no_return(self):
        """Test code without return statement."""
        # Note: function name avoids containing "return" substring
        code = "async def missing_ret(nh): pass"
        is_valid, error = validate_skill_code(code)
        assert not is_valid
        assert "SkillResult" in error

    def test_with_skill_result(self):
        """Test code with SkillResult."""
        code = """
async def skill(nh):
    return SkillResult.stopped("done")
"""
        is_valid, error = validate_skill_code(code)
        assert is_valid
