"""Tests for skill library."""

import pytest
import tempfile
from pathlib import Path

from src.skills.library import SkillLibrary
from src.skills.models import Skill, SkillCategory, SkillMetadata


@pytest.fixture
def temp_skills_dir():
    """Create a temporary skills directory."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def library(temp_skills_dir):
    """Create a library with temporary directory."""
    return SkillLibrary(str(temp_skills_dir))


@pytest.fixture
def sample_skill_code():
    """Sample valid skill code."""
    return '''"""
A sample exploration skill.

Explores the dungeon safely.
"""


async def sample_explore(nh, max_steps: int = 10, **params):
    """
    Sample exploration skill.

    Category: exploration
    Stops when: done, max_steps

    Args:
        nh: NetHackAPI instance
        max_steps: Maximum steps to take
    """
    return SkillResult.stopped("done", success=True, actions=0, turns=0)
'''


class TestSkillLibraryBasics:
    """Basic tests for SkillLibrary."""

    def test_init_with_path(self, temp_skills_dir):
        """Test creating library with custom path."""
        lib = SkillLibrary(str(temp_skills_dir))
        assert lib.skills_dir == temp_skills_dir

    def test_init_default_path(self):
        """Test creating library with default path."""
        lib = SkillLibrary()
        assert lib.skills_dir == Path("skills")

    def test_empty_library(self, library):
        """Test empty library state."""
        assert library.list_names() == []
        assert library.list_skills() == []
        assert library.get("nonexistent") is None

    def test_exists_false(self, library):
        """Test exists returns False for missing skill."""
        assert library.exists("nonexistent") is False


class TestSkillLibraryLoading:
    """Tests for loading skills from filesystem."""

    def test_load_all_empty_dir(self, library):
        """Test loading from empty directory."""
        count = library.load_all()
        assert count == 0

    def test_load_skill_file(self, temp_skills_dir, sample_skill_code):
        """Test loading a skill from file."""
        # Create exploration category directory
        exploration_dir = temp_skills_dir / "exploration"
        exploration_dir.mkdir()

        # Write skill file
        skill_file = exploration_dir / "sample_explore.py"
        skill_file.write_text(sample_skill_code)

        # Load skills
        lib = SkillLibrary(str(temp_skills_dir))
        count = lib.load_all()

        assert count == 1
        assert lib.exists("sample_explore")
        skill = lib.get("sample_explore")
        assert skill is not None
        assert skill.category == SkillCategory.EXPLORATION

    def test_load_multiple_categories(self, temp_skills_dir):
        """Test loading skills from multiple categories."""
        # Create multiple categories
        for cat in ["exploration", "combat", "resource"]:
            cat_dir = temp_skills_dir / cat
            cat_dir.mkdir()

            # Create a simple skill in each
            skill_code = f'''
async def {cat}_skill(nh, **params):
    """
    A {cat} skill.

    Category: {cat}
    Stops when: done
    """
    return SkillResult.stopped("done", success=True, actions=0, turns=0)
'''
            skill_file = cat_dir / f"{cat}_skill.py"
            skill_file.write_text(skill_code)

        lib = SkillLibrary(str(temp_skills_dir))
        count = lib.load_all()

        assert count == 3
        assert lib.exists("exploration_skill")
        assert lib.exists("combat_skill")
        assert lib.exists("resource_skill")

    def test_skip_files_starting_with_underscore(self, temp_skills_dir):
        """Test that files starting with _ are skipped."""
        exploration_dir = temp_skills_dir / "exploration"
        exploration_dir.mkdir()

        # Create _private skill (should be skipped)
        private_file = exploration_dir / "_private.py"
        private_file.write_text("async def _private(nh): pass")

        # Create normal skill
        normal_file = exploration_dir / "normal.py"
        normal_file.write_text('''
async def normal(nh, **params):
    """Normal skill. Category: exploration. Stops when: done"""
    return SkillResult.stopped("done", success=True, actions=0, turns=0)
''')

        lib = SkillLibrary(str(temp_skills_dir))
        count = lib.load_all()

        assert count == 1
        assert lib.exists("normal")
        assert not lib.exists("_private")

    def test_skip_hidden_directories(self, temp_skills_dir):
        """Test that hidden directories (starting with .) are skipped."""
        # Create hidden directory
        hidden_dir = temp_skills_dir / ".hidden"
        hidden_dir.mkdir()

        skill_file = hidden_dir / "secret.py"
        skill_file.write_text("async def secret(nh): pass")

        lib = SkillLibrary(str(temp_skills_dir))
        count = lib.load_all()

        assert count == 0


class TestSkillLibrarySaving:
    """Tests for saving skills."""

    def test_save_new_skill(self, library, sample_skill_code):
        """Test saving a new skill."""
        skill = library.save("test_skill", sample_skill_code)

        assert skill.name == "test_skill"
        assert library.exists("test_skill")

        # Check file was created
        expected_path = library.skills_dir / "exploration" / "test_skill.py"
        assert expected_path.exists()

    def test_save_duplicate_raises_error(self, library, sample_skill_code):
        """Test that saving duplicate without overwrite raises error."""
        library.save("test_skill", sample_skill_code)

        with pytest.raises(ValueError, match="already exists"):
            library.save("test_skill", sample_skill_code)

    def test_save_with_overwrite(self, library, sample_skill_code):
        """Test saving duplicate with overwrite=True."""
        library.save("test_skill", sample_skill_code)

        # Modify code slightly
        new_code = sample_skill_code.replace("max_steps: int = 10", "max_steps: int = 20")
        skill = library.save("test_skill", new_code, overwrite=True)

        assert "max_steps: int = 20" in skill.code

    def test_save_invalid_code_raises_error(self, library):
        """Test that saving invalid code raises error."""
        invalid_code = "this is not valid python"

        with pytest.raises(ValueError, match="Invalid skill code"):
            library.save("invalid", invalid_code)

    def test_save_creates_category_directory(self, library):
        """Test that saving creates category directory if needed."""
        code = '''
async def combat_skill(nh, **params):
    """
    Combat skill for testing.

    Category: combat
    Stops when: done
    """
    return SkillResult.stopped("done", success=True, actions=0, turns=0)
'''
        library.save("combat_skill", code)

        combat_dir = library.skills_dir / "combat"
        assert combat_dir.exists()


class TestSkillLibraryDeletion:
    """Tests for deleting skills."""

    def test_delete_skill(self, library, sample_skill_code):
        """Test deleting a skill."""
        library.save("test_skill", sample_skill_code)
        assert library.exists("test_skill")

        result = library.delete("test_skill")
        assert result is True
        assert not library.exists("test_skill")

    def test_delete_nonexistent_returns_false(self, library):
        """Test deleting nonexistent skill returns False."""
        result = library.delete("nonexistent")
        assert result is False

    def test_delete_removes_file(self, library, sample_skill_code):
        """Test that deleting also removes the file."""
        library.save("test_skill", sample_skill_code)
        expected_path = library.skills_dir / "exploration" / "test_skill.py"
        assert expected_path.exists()

        library.delete("test_skill")
        assert not expected_path.exists()

    def test_delete_without_file_deletion(self, library, sample_skill_code):
        """Test deleting skill without removing file."""
        library.save("test_skill", sample_skill_code)
        expected_path = library.skills_dir / "exploration" / "test_skill.py"

        library.delete("test_skill", delete_file=False)
        assert not library.exists("test_skill")
        assert expected_path.exists()  # File still exists


class TestSkillLibraryListing:
    """Tests for listing skills."""

    def test_list_all_skills(self, library, sample_skill_code):
        """Test listing all skills."""
        # Save a few skills
        library.save("skill1", sample_skill_code)

        combat_code = sample_skill_code.replace("exploration", "combat").replace("sample_explore", "combat_skill")
        library.save("combat_skill", combat_code)

        all_skills = library.list_skills()
        assert len(all_skills) == 2

    def test_list_skills_by_category(self, library, sample_skill_code):
        """Test listing skills filtered by category."""
        library.save("explore1", sample_skill_code)

        combat_code = sample_skill_code.replace("exploration", "combat").replace("sample_explore", "combat_skill")
        library.save("combat_skill", combat_code)

        exploration_skills = library.list_skills(category=SkillCategory.EXPLORATION)
        assert len(exploration_skills) == 1
        assert exploration_skills[0].name == "explore1"

        combat_skills = library.list_skills(category=SkillCategory.COMBAT)
        assert len(combat_skills) == 1
        assert combat_skills[0].name == "combat_skill"

    def test_list_names(self, library, sample_skill_code):
        """Test listing skill names."""
        library.save("skill1", sample_skill_code)

        names = library.list_names()
        assert "skill1" in names

    def test_list_names_by_category(self, library, sample_skill_code):
        """Test listing skill names by category."""
        library.save("explore1", sample_skill_code)

        names = library.list_names(category=SkillCategory.EXPLORATION)
        assert "explore1" in names

        combat_names = library.list_names(category=SkillCategory.COMBAT)
        assert "explore1" not in combat_names


class TestSkillLibraryAddFromCode:
    """Tests for adding skills from code."""

    def test_add_from_code_persisted(self, library, sample_skill_code):
        """Test adding skill from code with persistence."""
        skill = library.add_from_code("test_skill", sample_skill_code, persist=True)

        assert library.exists("test_skill")
        # Check file was created
        assert skill.file_path is not None
        assert Path(skill.file_path).exists()

    def test_add_from_code_not_persisted(self, library, sample_skill_code):
        """Test adding skill from code without persistence."""
        skill = library.add_from_code("test_skill", sample_skill_code, persist=False)

        assert library.exists("test_skill")
        assert skill.file_path is None  # No file path when not persisted

    def test_add_invalid_code_raises_error(self, library):
        """Test that adding invalid code raises error."""
        with pytest.raises(ValueError, match="Invalid skill code"):
            library.add_from_code("invalid", "not valid python", persist=False)


class TestSkillLibraryMetadata:
    """Tests for skill metadata handling."""

    def test_get_code(self, library, sample_skill_code):
        """Test getting just the code for a skill."""
        library.save("test", sample_skill_code)

        code = library.get_code("test")
        assert code is not None
        assert "async def sample_explore" in code

    def test_get_code_nonexistent(self, library):
        """Test getting code for nonexistent skill."""
        code = library.get_code("nonexistent")
        assert code is None

    def test_get_summary(self, library, sample_skill_code):
        """Test getting library summary."""
        library.save("test", sample_skill_code)

        summary = library.get_summary()
        assert summary["total_skills"] == 1
        assert "exploration" in summary["by_category"]
        assert len(summary["skills"]) == 1

    def test_format_for_prompt(self, library, sample_skill_code):
        """Test formatting library for LLM prompt."""
        library.save("test", sample_skill_code)

        prompt_text = library.format_for_prompt()
        assert "Available skills:" in prompt_text
        assert "test" in prompt_text
