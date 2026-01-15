"""Tests for sandbox validation module."""

import pytest

from src.sandbox.validation import (
    validate_syntax,
    validate_security,
    validate_signature,
    validate_skill,
    extract_skill_metadata,
    ValidationResult,
)
from src.sandbox.exceptions import SkillSyntaxError, SkillSecurityError


class TestValidateSyntax:
    """Tests for syntax validation."""

    def test_valid_syntax(self):
        """Valid Python code should pass."""
        code = '''
async def explore(nh, **params):
    """Explore the dungeon."""
    return SkillResult.stopped("completed", success=True)
'''
        # Should not raise
        validate_syntax(code)

    def test_invalid_syntax(self):
        """Invalid Python should raise SkillSyntaxError."""
        code = '''
def foo(
    # Missing closing paren
'''
        with pytest.raises(SkillSyntaxError) as exc_info:
            validate_syntax(code, "test_skill")

        assert exc_info.value.skill_name == "test_skill"

    def test_syntax_error_has_line_info(self):
        """Syntax errors should include line information."""
        code = '''
def foo():
    pass

def bar(:  # Invalid syntax on line 5
    pass
'''
        with pytest.raises(SkillSyntaxError) as exc_info:
            validate_syntax(code)

        assert exc_info.value.line > 0


class TestValidateSecurity:
    """Tests for security validation."""

    def test_safe_code_passes(self):
        """Safe code should pass validation."""
        code = '''
async def explore(nh, **params):
    stats = nh.get_stats()
    if stats["hp"] < 10:
        return SkillResult.stopped("low_hp", success=False)
    return SkillResult.stopped("completed", success=True)
'''
        # Should not raise, may return warnings
        warnings = validate_security(code)
        assert isinstance(warnings, list)

    def test_forbidden_import_os(self):
        """Importing os should fail."""
        code = '''
import os

async def exploit(nh, **params):
    os.system("rm -rf /")
'''
        with pytest.raises(SkillSecurityError) as exc_info:
            validate_security(code, "exploit")

        assert "import" in str(exc_info.value).lower()

    def test_forbidden_import_subprocess(self):
        """Importing subprocess should fail."""
        code = '''
import subprocess

async def exploit(nh, **params):
    subprocess.run(["ls"])
'''
        with pytest.raises(SkillSecurityError):
            validate_security(code)

    def test_forbidden_from_import(self):
        """From imports of forbidden modules should fail."""
        code = '''
from os import system

async def exploit(nh, **params):
    system("ls")
'''
        with pytest.raises(SkillSecurityError):
            validate_security(code)

    def test_forbidden_exec(self):
        """Using exec() should fail."""
        code = '''
async def exploit(nh, **params):
    exec("import os; os.system('ls')")
'''
        with pytest.raises(SkillSecurityError) as exc_info:
            validate_security(code)

        assert "exec" in str(exc_info.value).lower()

    def test_forbidden_eval(self):
        """Using eval() should fail."""
        code = '''
async def exploit(nh, **params):
    return eval("1+1")
'''
        with pytest.raises(SkillSecurityError):
            validate_security(code)

    def test_forbidden_open(self):
        """Using open() should fail."""
        code = '''
async def exploit(nh, **params):
    with open("/etc/passwd") as f:
        return f.read()
'''
        with pytest.raises(SkillSecurityError):
            validate_security(code)

    def test_forbidden_dunder_class(self):
        """Accessing __class__ should fail."""
        code = '''
async def exploit(nh, **params):
    return nh.__class__.__bases__
'''
        with pytest.raises(SkillSecurityError) as exc_info:
            validate_security(code)

        assert "__class__" in str(exc_info.value) or "__bases__" in str(exc_info.value)

    def test_forbidden_dunder_globals(self):
        """Accessing __globals__ should fail."""
        code = '''
async def exploit(nh, **params):
    return exploit.__globals__
'''
        with pytest.raises(SkillSecurityError):
            validate_security(code)

    def test_forbidden_subscript_bypass(self):
        """String subscript bypass attempts should fail."""
        code = '''
async def exploit(nh, **params):
    return nh["__class__"]
'''
        with pytest.raises(SkillSecurityError):
            validate_security(code)

    def test_allowed_imports(self):
        """Allowed imports should pass."""
        code = '''
import asyncio
import math
import random
from typing import Optional

async def safe_skill(nh, **params):
    value = math.sqrt(random.random())
    return value
'''
        # Should not raise
        warnings = validate_security(code)
        assert not any("forbidden" in w.lower() for w in warnings)

    def test_unknown_import_warning(self):
        """Unknown imports should produce warnings."""
        code = '''
import some_unknown_module

async def skill(nh, **params):
    pass
'''
        warnings = validate_security(code)
        assert len(warnings) > 0
        assert "unknown" in warnings[0].lower()


class TestValidateSignature:
    """Tests for function signature validation."""

    def test_valid_async_function(self):
        """Valid async function should pass."""
        code = '''
async def explore(nh, **params):
    pass
'''
        valid, name = validate_signature(code)
        assert valid is True
        assert name == "explore"

    def test_sync_function_fails(self):
        """Non-async functions should fail."""
        code = '''
def explore(nh, **params):
    pass
'''
        valid, name = validate_signature(code)
        assert valid is False

    def test_no_function_fails(self):
        """Code without functions should fail."""
        code = '''
x = 1 + 2
'''
        valid, name = validate_signature(code)
        assert valid is False

    def test_multiple_async_functions(self):
        """First async function with correct signature should be detected."""
        code = '''
async def helper():
    pass

async def main_skill(nh, **params):
    await helper()
'''
        valid, name = validate_signature(code)
        # helper() has no args so may not be valid, main_skill is the valid one
        assert valid is True
        # The first one with at least one arg gets detected
        assert name in ["helper", "main_skill"]

    def test_specific_skill_name(self):
        """Can search for specific skill name."""
        code = '''
async def helper():
    pass

async def main_skill(nh, **params):
    await helper()
'''
        valid, name = validate_signature(code, skill_name="main_skill")
        assert valid is True
        assert name == "main_skill"

    def test_function_with_no_params(self):
        """Function without params is still detected (runtime will handle param errors)."""
        code = '''
async def skill():  # No params
    pass
'''
        valid, name = validate_signature(code)
        # The signature validation is lenient - runtime catches param errors
        # A function exists, so it's considered "valid" at this stage
        assert name == "skill"


class TestValidateSkill:
    """Tests for complete skill validation."""

    def test_valid_skill(self):
        """Complete valid skill should pass."""
        code = '''
async def explore(nh, max_steps=100):
    """
    Explore the dungeon.

    Category: exploration
    Stops when: monster spotted, low HP
    """
    steps = 0
    while steps < max_steps:
        if nh.is_done:
            return SkillResult.stopped("game_over", success=False)

        monsters = nh.get_adjacent_monsters()
        if monsters:
            return SkillResult.stopped("monster_spotted", success=False, monster=monsters[0])

        stats = nh.get_stats()
        if stats["hp"] < stats["max_hp"] * 0.3:
            return SkillResult.stopped("low_hp", success=False)

        unexplored = nh.find_unexplored()
        if not unexplored:
            return SkillResult.stopped("fully_explored", success=True)

        result = nh.move_to(unexplored["x"], unexplored["y"])
        if result.success:
            steps += 1
        else:
            nh.search()
            steps += 1

    return SkillResult.stopped("max_steps", success=False, steps=steps)
'''
        result = validate_skill(code, "explore")
        assert result.valid is True
        assert result.function_name == "explore"
        assert result.has_correct_signature is True
        assert len(result.errors) == 0

    def test_invalid_syntax_returns_errors(self):
        """Syntax errors should be reported."""
        code = '''
async def skill(nh:
    pass
'''
        result = validate_skill(code, "skill")
        assert result.valid is False
        assert len(result.errors) > 0
        assert "syntax" in result.errors[0].lower()

    def test_security_violation_returns_errors(self):
        """Security violations should be reported."""
        code = '''
import os

async def skill(nh, **params):
    os.system("ls")
'''
        result = validate_skill(code, "skill")
        assert result.valid is False
        assert len(result.errors) > 0
        assert "security" in result.errors[0].lower() or "violation" in result.errors[0].lower()

    def test_missing_function_returns_errors(self):
        """Missing async function should be reported."""
        code = '''
x = 1
'''
        result = validate_skill(code, "skill")
        assert result.valid is False
        assert len(result.errors) > 0


class TestExtractSkillMetadata:
    """Tests for metadata extraction from docstrings."""

    def test_extract_full_metadata(self):
        """Should extract all metadata fields."""
        code = '''
async def explore(nh, **params):
    """
    Cautiously explore the dungeon until danger is spotted.

    Category: exploration
    Stops when: monster spotted, low HP, trap detected
    """
    pass
'''
        metadata = extract_skill_metadata(code)
        assert "explore" in metadata["description"].lower() or "dungeon" in metadata["description"].lower()
        assert metadata["category"] == "exploration"
        assert "monster spotted" in metadata["stops_when"]
        assert "low HP" in metadata["stops_when"]

    def test_extract_minimal_metadata(self):
        """Should handle minimal docstrings."""
        code = '''
async def skill(nh):
    """Simple skill."""
    pass
'''
        metadata = extract_skill_metadata(code)
        assert metadata["description"] == "Simple skill."
        assert metadata["category"] == "general"  # Default
        assert metadata["stops_when"] == []

    def test_no_docstring(self):
        """Should handle missing docstrings."""
        code = '''
async def skill(nh):
    pass
'''
        metadata = extract_skill_metadata(code)
        assert metadata["description"] == ""
        assert metadata["category"] == "general"

    def test_invalid_code_returns_defaults(self):
        """Should return defaults for invalid code."""
        code = "not valid python{"
        metadata = extract_skill_metadata(code)
        assert metadata["description"] == ""
        assert metadata["category"] == "general"
