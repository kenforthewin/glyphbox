"""Tests for skill synthesis."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from src.agent.skill_synthesis import (
    SkillSynthesizer,
    SynthesisResult,
    enhance_skill_code,
    extract_skill_docstring,
)


class TestSynthesisResult:
    """Tests for SynthesisResult dataclass."""

    def test_default_values(self):
        """Test default values are set correctly."""
        result = SynthesisResult(success=False, skill_name="test")
        assert result.success is False
        assert result.skill_name == "test"
        assert result.error is None
        assert result.validation_errors == []
        assert result.test_result is None
        assert result.persisted is False

    def test_with_errors(self):
        """Test result with validation errors."""
        result = SynthesisResult(
            success=False,
            skill_name="bad_skill",
            error="Validation failed",
            validation_errors=["Missing return", "Bad syntax"],
        )
        assert len(result.validation_errors) == 2
        assert "Missing return" in result.validation_errors


class TestSkillSynthesizer:
    """Tests for SkillSynthesizer."""

    def setup_method(self):
        """Set up test fixtures."""
        self.mock_library = MagicMock()
        self.mock_library.exists.return_value = False
        self.mock_executor = AsyncMock()
        self.synthesizer = SkillSynthesizer(
            library=self.mock_library,
            executor=self.mock_executor,
            auto_save=True,
        )

    @pytest.mark.asyncio
    async def test_synthesize_valid_skill(self):
        """Test synthesizing a valid skill."""
        code = '''
async def test_skill(nh, **params):
    """A test skill."""
    return SkillResult.success()
'''
        with patch('src.agent.skill_synthesis.validate_skill') as mock_validate:
            mock_validate.return_value = MagicMock(valid=True, errors=[])

            result = await self.synthesizer.synthesize(
                name="test_skill",
                code=code,
                test_before_save=False,
            )

            assert result.success
            assert result.skill_name == "test_skill"
            assert result.persisted
            self.mock_library.save.assert_called_once()

    @pytest.mark.asyncio
    async def test_synthesize_invalid_code(self):
        """Test synthesizing invalid code."""
        code = "not valid python code {"

        with patch('src.agent.skill_synthesis.validate_skill') as mock_validate:
            mock_validate.return_value = MagicMock(
                valid=False,
                errors=["Syntax error", "Missing function"]
            )

            result = await self.synthesizer.synthesize(
                name="bad_skill",
                code=code,
            )

            assert not result.success
            assert "Validation failed" in result.error
            assert len(result.validation_errors) == 2
            self.mock_library.save.assert_not_called()

    @pytest.mark.asyncio
    async def test_synthesize_duplicate_name(self):
        """Test synthesizing skill with duplicate name."""
        self.mock_library.exists.return_value = True

        with patch('src.agent.skill_synthesis.validate_skill') as mock_validate:
            mock_validate.return_value = MagicMock(valid=True, errors=[])

            result = await self.synthesizer.synthesize(
                name="existing_skill",
                code="async def existing_skill(nh): return SkillResult.success()",
            )

            assert not result.success
            assert "already exists" in result.error

    @pytest.mark.asyncio
    async def test_synthesize_with_force_save(self):
        """Test force saving over existing skill."""
        self.mock_library.exists.return_value = True

        with patch('src.agent.skill_synthesis.validate_skill') as mock_validate:
            mock_validate.return_value = MagicMock(valid=True, errors=[])

            result = await self.synthesizer.synthesize(
                name="existing_skill",
                code="async def existing_skill(nh): return SkillResult.success()",
                force_save=True,
            )

            assert result.success
            self.mock_library.save.assert_called_once()

    @pytest.mark.asyncio
    async def test_synthesize_with_test_success(self):
        """Test synthesizing with successful test execution."""
        execution_mock = MagicMock()
        execution_mock.success = True
        execution_mock.stopped_reason = "completed"
        execution_mock.actions_taken = 5
        execution_mock.turns_elapsed = 3
        execution_mock.error = None

        self.mock_executor.execute_code = AsyncMock(return_value=execution_mock)

        with patch('src.agent.skill_synthesis.validate_skill') as mock_validate:
            mock_validate.return_value = MagicMock(valid=True, errors=[])

            result = await self.synthesizer.synthesize(
                name="tested_skill",
                code="async def tested_skill(nh): return SkillResult.success()",
                test_before_save=True,
            )

            assert result.success
            assert result.test_result is not None
            assert result.test_result["success"]

    @pytest.mark.asyncio
    async def test_synthesize_with_test_failure(self):
        """Test synthesizing with failed test execution."""
        execution_mock = MagicMock()
        execution_mock.success = False
        execution_mock.stopped_reason = "error"
        execution_mock.actions_taken = 0
        execution_mock.turns_elapsed = 0
        execution_mock.error = "Skill crashed"

        self.mock_executor.execute_code = AsyncMock(return_value=execution_mock)

        with patch('src.agent.skill_synthesis.validate_skill') as mock_validate:
            mock_validate.return_value = MagicMock(valid=True, errors=[])

            result = await self.synthesizer.synthesize(
                name="failing_skill",
                code="async def failing_skill(nh): raise Exception()",
                test_before_save=True,
            )

            assert not result.success
            assert "Test failed" in result.error
            self.mock_library.save.assert_not_called()

    @pytest.mark.asyncio
    async def test_synthesize_test_exception(self):
        """Test synthesizing when test raises exception."""
        self.mock_executor.execute_code = AsyncMock(
            side_effect=RuntimeError("Sandbox error")
        )

        with patch('src.agent.skill_synthesis.validate_skill') as mock_validate:
            mock_validate.return_value = MagicMock(valid=True, errors=[])

            result = await self.synthesizer.synthesize(
                name="error_skill",
                code="async def error_skill(nh): pass",
                test_before_save=True,
            )

            assert not result.success
            # Exception in _test_skill returns {"success": False, "error": str(e)}
            # which causes "Test failed: <error>" message
            assert "Test failed" in result.error or "Sandbox error" in result.error

    @pytest.mark.asyncio
    async def test_synthesize_save_failure(self):
        """Test handling save failure."""
        self.mock_library.save.side_effect = IOError("Disk full")

        with patch('src.agent.skill_synthesis.validate_skill') as mock_validate:
            mock_validate.return_value = MagicMock(valid=True, errors=[])

            result = await self.synthesizer.synthesize(
                name="unsaved_skill",
                code="async def unsaved_skill(nh): return SkillResult.success()",
            )

            assert not result.success
            assert "Failed to save" in result.error

    def test_get_failed_attempts(self):
        """Test retrieving failed attempts."""
        # Record some failures
        self.synthesizer._record_failure("skill1", "code1", "error1")
        self.synthesizer._record_failure("skill1", "code2", "error2")
        self.synthesizer._record_failure("skill2", "code3", "error3")

        attempts = self.synthesizer.get_failed_attempts("skill1")
        assert len(attempts) == 2
        assert "code1" in attempts
        assert "code2" in attempts

        attempts2 = self.synthesizer.get_failed_attempts("skill2")
        assert len(attempts2) == 1

        attempts3 = self.synthesizer.get_failed_attempts("nonexistent")
        assert len(attempts3) == 0

    @pytest.mark.asyncio
    async def test_get_recent_attempts(self):
        """Test retrieving recent synthesis attempts."""
        with patch('src.agent.skill_synthesis.validate_skill') as mock_validate:
            mock_validate.return_value = MagicMock(valid=True, errors=[])

            for i in range(5):
                await self.synthesizer.synthesize(
                    name=f"skill_{i}",
                    code=f"async def skill_{i}(nh): return SkillResult.success()",
                    test_before_save=False,
                )

        recent = self.synthesizer.get_recent_attempts(limit=3)
        assert len(recent) == 3
        # Most recent should be last
        assert recent[-1].skill_name == "skill_4"

    @pytest.mark.asyncio
    async def test_get_statistics(self):
        """Test getting synthesis statistics."""
        with patch('src.agent.skill_synthesis.validate_skill') as mock_validate:
            # 3 successful
            mock_validate.return_value = MagicMock(valid=True, errors=[])
            for i in range(3):
                await self.synthesizer.synthesize(
                    name=f"good_{i}",
                    code=f"async def good_{i}(nh): return SkillResult.success()",
                )

            # 2 failed
            mock_validate.return_value = MagicMock(valid=False, errors=["bad"])
            for i in range(2):
                await self.synthesizer.synthesize(
                    name=f"bad_{i}",
                    code="invalid",
                )

        stats = self.synthesizer.get_statistics()
        assert stats["total_attempts"] == 5
        assert stats["successful"] == 3
        assert stats["success_rate"] == 0.6

    def test_clear_history(self):
        """Test clearing synthesis history."""
        self.synthesizer._attempts = [MagicMock(), MagicMock()]
        self.synthesizer._failed_codes = {"skill1": ["code1"]}

        self.synthesizer.clear_history()

        assert len(self.synthesizer._attempts) == 0
        assert len(self.synthesizer._failed_codes) == 0


class TestSkillSynthesizerNoExecutor:
    """Tests for SkillSynthesizer without executor."""

    def setup_method(self):
        """Set up test fixtures."""
        self.mock_library = MagicMock()
        self.mock_library.exists.return_value = False
        self.synthesizer = SkillSynthesizer(
            library=self.mock_library,
            executor=None,  # No executor
            auto_save=True,
        )

    @pytest.mark.asyncio
    async def test_test_skill_skipped_without_executor(self):
        """Test that testing is skipped without executor."""
        with patch('src.agent.skill_synthesis.validate_skill') as mock_validate:
            mock_validate.return_value = MagicMock(valid=True, errors=[])

            result = await self.synthesizer.synthesize(
                name="untested_skill",
                code="async def untested_skill(nh): return SkillResult.success()",
                test_before_save=True,  # Requested but won't happen
            )

            # Should succeed without test
            assert result.success


class TestEnhanceSkillCode:
    """Tests for enhance_skill_code function."""

    def test_enhance_adds_game_over_check(self):
        """Test enhancement adds game over check."""
        code = '''
async def simple_skill(nh):
    """Simple skill."""
    return SkillResult.success()
'''
        enhanced = enhance_skill_code(code, "simple_skill")
        assert "is_done" in enhanced

    def test_enhance_adds_iteration_limit(self):
        """Test enhancement adds iteration limit."""
        code = '''
async def looping_skill(nh):
    """Looping skill."""
    while True:
        pass
'''
        enhanced = enhance_skill_code(code, "looping_skill")
        assert "max_iterations" in enhanced or "max_" in enhanced

    def test_enhance_preserves_existing_checks(self):
        """Test enhancement preserves existing safety checks."""
        code = '''
async def safe_skill(nh):
    """Already safe skill."""
    max_iterations = 50
    if nh.is_done:
        return SkillResult.stopped("game_over")
    return SkillResult.success()
'''
        enhanced = enhance_skill_code(code, "safe_skill")
        # Should not double-add checks
        assert enhanced.count("is_done") == 1
        assert enhanced.count("max_iterations") == 1


class TestExtractSkillDocstring:
    """Tests for extract_skill_docstring function."""

    def test_extract_simple_docstring(self):
        """Test extracting simple docstring."""
        code = '''
async def my_skill(nh):
    """This is the docstring."""
    pass
'''
        docstring = extract_skill_docstring(code)
        assert docstring == "This is the docstring."

    def test_extract_multiline_docstring(self):
        """Test extracting multiline docstring."""
        code = '''
async def my_skill(nh):
    """
    First line.
    Second line.
    Third line.
    """
    pass
'''
        docstring = extract_skill_docstring(code)
        assert "First line" in docstring
        assert "Third line" in docstring

    def test_no_docstring(self):
        """Test when no docstring present."""
        code = '''
async def my_skill(nh):
    pass
'''
        docstring = extract_skill_docstring(code)
        assert docstring is None

    def test_invalid_syntax(self):
        """Test with invalid Python syntax."""
        code = "async def invalid(nh { pass"
        docstring = extract_skill_docstring(code)
        assert docstring is None

    def test_extract_from_multiple_functions(self):
        """Test extraction gets first async function docstring."""
        code = '''
def helper():
    """Helper docstring."""
    pass

async def main_skill(nh):
    """Main skill docstring."""
    pass
'''
        docstring = extract_skill_docstring(code)
        assert docstring == "Main skill docstring."
