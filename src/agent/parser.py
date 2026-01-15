"""
Decision parser for LLM responses.

Parses JSON decisions from LLM output and validates them.
"""

import json
import logging
import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional

logger = logging.getLogger(__name__)


class ActionType(Enum):
    """Types of agent actions."""

    EXECUTE_CODE = "execute_code"  # Run ad-hoc code
    WRITE_SKILL = "write_skill"  # Save skill to library
    INVOKE_SKILL = "invoke_skill"  # Run saved skill
    UNKNOWN = "unknown"


@dataclass
class AgentDecision:
    """Parsed decision from the agent."""

    action: ActionType
    skill_name: Optional[str] = None
    params: dict[str, Any] = field(default_factory=dict)
    reasoning: str = ""
    code: Optional[str] = None
    command: Optional[str] = None  # For direct_action
    raw_response: str = ""
    parse_error: Optional[str] = None

    @property
    def is_valid(self) -> bool:
        """Check if the decision is valid."""
        if self.parse_error:
            return False

        if self.action == ActionType.EXECUTE_CODE:
            return self.code is not None

        if self.action == ActionType.WRITE_SKILL:
            return self.skill_name is not None and self.code is not None

        if self.action == ActionType.INVOKE_SKILL:
            return self.skill_name is not None

        return False

    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "action": self.action.value,
            "skill_name": self.skill_name,
            "params": self.params,
            "reasoning": self.reasoning,
            "code": self.code,
            "command": self.command,
            "is_valid": self.is_valid,
            "parse_error": self.parse_error,
        }


class DecisionParser:
    """
    Parses LLM responses into structured decisions.

    Handles JSON extraction from markdown code blocks and
    validates decision structure.

    Example usage:
        parser = DecisionParser()
        decision = parser.parse(llm_response)

        if decision.is_valid:
            if decision.action == ActionType.INVOKE_SKILL:
                execute_skill(decision.skill_name, decision.params)
            elif decision.action == ActionType.CREATE_SKILL:
                create_skill(decision.skill_name, decision.code)
    """

    # Patterns for extracting JSON from LLM responses
    JSON_BLOCK_PATTERN = re.compile(r"```(?:json)?\s*\n?(.*?)\n?```", re.DOTALL)
    BARE_JSON_PATTERN = re.compile(r"\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}", re.DOTALL)

    # Pattern for extracting Python code from markdown
    CODE_BLOCK_PATTERN = re.compile(r"```(?:python)?\s*\n?(.*?)\n?```", re.DOTALL)

    def parse(self, response: str) -> AgentDecision:
        """
        Parse an LLM response into an AgentDecision.

        Args:
            response: Raw LLM response text

        Returns:
            AgentDecision (check is_valid for success)
        """
        decision = AgentDecision(
            action=ActionType.UNKNOWN,
            raw_response=response,
        )

        # Try to extract JSON
        json_str = self._extract_json(response)
        if not json_str:
            decision.parse_error = "No JSON found in response"
            return decision

        # Parse JSON
        try:
            data = json.loads(json_str)
        except json.JSONDecodeError as e:
            decision.parse_error = f"Invalid JSON: {e}"
            return decision

        # Extract fields
        return self._parse_json_decision(data, response)

    def _extract_json(self, response: str) -> Optional[str]:
        """Extract JSON from response (handles code blocks)."""
        # First try to find JSON in code blocks
        matches = self.JSON_BLOCK_PATTERN.findall(response)
        for match in matches:
            match = match.strip()
            if match.startswith("{"):
                return match

        # Try to find bare JSON object
        matches = self.BARE_JSON_PATTERN.findall(response)
        if matches:
            # Return the largest match (most likely the full decision)
            return max(matches, key=len)

        return None

    def _parse_json_decision(self, data: dict, raw_response: str) -> AgentDecision:
        """Parse a JSON decision dictionary."""
        # Get action type
        action_str = data.get("action", "").lower()
        try:
            action = ActionType(action_str)
        except ValueError:
            action = ActionType.UNKNOWN

        # Extract fields
        skill_name = data.get("skill_name") or data.get("name")
        params = data.get("params", {})
        reasoning = data.get("reasoning", "")
        command = data.get("command")

        # Handle code for execute_code and write_skill
        code = data.get("code")
        if action == ActionType.WRITE_SKILL and not code:
            # Try to extract code from the raw response
            code = self._extract_code(raw_response)

        decision = AgentDecision(
            action=action,
            skill_name=skill_name,
            params=params if isinstance(params, dict) else {},
            reasoning=reasoning,
            code=code,
            command=command,
            raw_response=raw_response,
        )

        # Validate based on action type
        if action == ActionType.UNKNOWN:
            decision.parse_error = f"Unknown action type: {action_str}"
        elif action == ActionType.EXECUTE_CODE:
            if not code:
                decision.parse_error = "execute_code requires code"
        elif action == ActionType.WRITE_SKILL:
            if not skill_name:
                decision.parse_error = "write_skill requires skill_name"
            elif not code:
                decision.parse_error = "write_skill requires code"
        elif action == ActionType.INVOKE_SKILL:
            if not skill_name:
                decision.parse_error = "invoke_skill requires skill_name"

        return decision

    def _extract_code(self, response: str) -> Optional[str]:
        """Extract Python code from response."""
        matches = self.CODE_BLOCK_PATTERN.findall(response)

        # Look for async def functions
        for match in matches:
            if "async def" in match:
                return match.strip()

        # Return first code block if no async def found
        if matches:
            return matches[0].strip()

        return None

    def parse_multiple(self, response: str) -> list[AgentDecision]:
        """
        Parse a response that might contain multiple decisions.

        Args:
            response: Raw LLM response text

        Returns:
            List of AgentDecision objects
        """
        decisions = []

        # Try to find multiple JSON blocks
        matches = self.JSON_BLOCK_PATTERN.findall(response)
        if not matches:
            matches = self.BARE_JSON_PATTERN.findall(response)

        for match in matches:
            match = match.strip()
            if not match.startswith("{"):
                continue

            try:
                data = json.loads(match)
                decision = self._parse_json_decision(data, response)
                decisions.append(decision)
            except json.JSONDecodeError:
                continue

        # If no decisions found, try parsing as single
        if not decisions:
            decisions.append(self.parse(response))

        return decisions


def extract_skill_name_from_code(code: str) -> Optional[str]:
    """
    Extract the skill function name from Python code.

    Args:
        code: Python code containing async function definition

    Returns:
        Function name or None
    """
    pattern = r"async\s+def\s+(\w+)\s*\("
    match = re.search(pattern, code)
    return match.group(1) if match else None


def validate_skill_code(code: str) -> tuple[bool, Optional[str]]:
    """
    Basic validation of skill code structure.

    Args:
        code: Python code to validate

    Returns:
        (is_valid, error_message)
    """
    if not code:
        return False, "No code provided"

    if "async def" not in code:
        return False, "Skill must be an async function"

    # Check for required parameter
    if "(nh" not in code and "(nh," not in code:
        return False, "Skill must have 'nh' as first parameter"

    # Check for return statement
    if "return" not in code and "SkillResult" not in code:
        return False, "Skill should return a SkillResult"

    return True, None
