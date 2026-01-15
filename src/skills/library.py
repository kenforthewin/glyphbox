"""
Skill library for loading, storing, and indexing skills.

The library manages both hand-written starter skills and
agent-generated skills, providing retrieval by name or category.
"""

import json
import logging
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Optional

from src.sandbox.validation import extract_skill_metadata, validate_skill

from .models import Skill, SkillCategory, SkillMetadata

logger = logging.getLogger(__name__)

# Default skills directory (relative to project root)
DEFAULT_SKILLS_DIR = "skills"


class SkillLibrary:
    """
    Manages a library of skills.

    Skills can be loaded from the filesystem or added programmatically.
    The library maintains an index for fast lookup by name or category.

    Example usage:
        library = SkillLibrary("skills/")
        library.load_all()

        # Get a specific skill
        skill = library.get("cautious_explore")

        # List skills by category
        exploration_skills = library.list_skills(category=SkillCategory.EXPLORATION)

        # Save a new skill
        library.save("new_skill", code, metadata)
    """

    def __init__(self, skills_dir: Optional[str] = None):
        """
        Initialize the skill library.

        Args:
            skills_dir: Directory containing skill files. Uses default if not specified.
        """
        self.skills_dir = Path(skills_dir) if skills_dir else Path(DEFAULT_SKILLS_DIR)
        self._skills: dict[str, Skill] = {}
        self._by_category: dict[SkillCategory, list[str]] = {
            cat: [] for cat in SkillCategory
        }

    # Directories to exclude when loading skills (agent-generated skills from previous runs)
    DEFAULT_EXCLUDE_DIRS = {"custom", "generated", "temp"}

    def load_all(self, exclude_dirs: Optional[set[str]] = None) -> int:
        """
        Load all skills from the skills directory.

        Args:
            exclude_dirs: Directory names to skip (defaults to custom/generated/temp).
                          These typically contain agent-generated skills from previous runs.

        Returns:
            Number of skills loaded
        """
        if not self.skills_dir.exists():
            logger.warning(f"Skills directory not found: {self.skills_dir}")
            return 0

        if exclude_dirs is None:
            exclude_dirs = self.DEFAULT_EXCLUDE_DIRS

        count = 0
        for category_dir in self.skills_dir.iterdir():
            if category_dir.is_dir() and not category_dir.name.startswith("."):
                # Skip excluded directories (agent-generated skills)
                if category_dir.name in exclude_dirs:
                    logger.debug(f"Skipping excluded directory: {category_dir.name}")
                    continue

                for skill_file in category_dir.glob("*.py"):
                    if skill_file.name.startswith("_"):
                        continue
                    try:
                        skill = self._load_skill_file(skill_file)
                        if skill:
                            self._add_skill(skill)
                            count += 1
                    except Exception as e:
                        logger.error(f"Failed to load skill {skill_file}: {e}")

        logger.info(f"Loaded {count} skills from {self.skills_dir}")
        return count

    def _load_skill_file(self, file_path: Path) -> Optional[Skill]:
        """Load a skill from a Python file."""
        code = file_path.read_text()

        # Validate the skill
        validation = validate_skill(code)
        if not validation.valid:
            logger.warning(f"Invalid skill {file_path}: {validation.errors}")
            return None

        # Extract metadata from docstring
        metadata_dict = extract_skill_metadata(code)

        # Determine category from directory structure
        category_name = file_path.parent.name
        category = SkillCategory.from_string(category_name)

        # Build metadata
        metadata = SkillMetadata(
            description=metadata_dict.get("description", ""),
            category=category,
            stops_when=metadata_dict.get("stops_when", []),
            author="human",  # File-based skills are hand-written
            created_at=datetime.fromtimestamp(file_path.stat().st_ctime),
            updated_at=datetime.fromtimestamp(file_path.stat().st_mtime),
        )

        # Use function name from validation or derive from filename
        skill_name = validation.function_name or file_path.stem

        return Skill(
            name=skill_name,
            code=code,
            metadata=metadata,
            file_path=str(file_path),
        )

    def _add_skill(self, skill: Skill) -> None:
        """Add a skill to the library index."""
        self._skills[skill.name] = skill
        if skill.name not in self._by_category[skill.category]:
            self._by_category[skill.category].append(skill.name)

    def get(self, name: str) -> Optional[Skill]:
        """
        Get a skill by name.

        Args:
            name: Skill name

        Returns:
            Skill if found, None otherwise
        """
        return self._skills.get(name)

    def get_code(self, name: str) -> Optional[str]:
        """
        Get just the code for a skill.

        Args:
            name: Skill name

        Returns:
            Skill code if found, None otherwise
        """
        skill = self.get(name)
        return skill.code if skill else None

    def exists(self, name: str) -> bool:
        """Check if a skill exists."""
        return name in self._skills

    def list_skills(
        self,
        category: Optional[SkillCategory] = None,
    ) -> list[Skill]:
        """
        List skills, optionally filtered by category.

        Args:
            category: Filter by category (None for all)

        Returns:
            List of matching skills
        """
        if category is None:
            return list(self._skills.values())

        skill_names = self._by_category.get(category, [])
        return [self._skills[name] for name in skill_names if name in self._skills]

    def list_names(
        self,
        category: Optional[SkillCategory] = None,
    ) -> list[str]:
        """
        List skill names, optionally filtered by category.

        Args:
            category: Filter by category (None for all)

        Returns:
            List of skill names
        """
        if category is None:
            return list(self._skills.keys())
        return self._by_category.get(category, []).copy()

    def save(
        self,
        name: str,
        code: str,
        metadata: Optional[SkillMetadata] = None,
        overwrite: bool = False,
    ) -> Skill:
        """
        Save a new skill to the library and filesystem.

        Args:
            name: Skill name (must be valid Python identifier)
            code: Skill Python code
            metadata: Skill metadata (extracted from code if not provided)
            overwrite: Whether to overwrite existing skill

        Returns:
            The saved Skill

        Raises:
            ValueError: If skill already exists and overwrite=False
            ValueError: If skill code is invalid
        """
        # Check if exists
        if not overwrite and self.exists(name):
            raise ValueError(f"Skill '{name}' already exists. Use overwrite=True to replace.")

        # Validate code
        validation = validate_skill(code, name)
        if not validation.valid:
            raise ValueError(f"Invalid skill code: {'; '.join(validation.errors)}")

        # Extract or use provided metadata
        if metadata is None:
            metadata_dict = extract_skill_metadata(code)
            metadata = SkillMetadata(
                description=metadata_dict.get("description", ""),
                category=SkillCategory.from_string(metadata_dict.get("category", "custom")),
                stops_when=metadata_dict.get("stops_when", []),
                author="agent",
                created_at=datetime.now(),
            )

        # Set timestamps
        now = datetime.now()
        if metadata.created_at is None:
            metadata.created_at = now
        metadata.updated_at = now

        # Determine file path
        category_dir = self.skills_dir / metadata.category.value
        category_dir.mkdir(parents=True, exist_ok=True)
        file_path = category_dir / f"{name}.py"

        # Write file
        file_path.write_text(code)

        # Create skill and add to index
        skill = Skill(
            name=name,
            code=code,
            metadata=metadata,
            file_path=str(file_path),
        )
        self._add_skill(skill)

        logger.info(f"Saved skill '{name}' to {file_path}")
        return skill

    def delete(self, name: str, delete_file: bool = True) -> bool:
        """
        Delete a skill from the library.

        Args:
            name: Skill name
            delete_file: Whether to also delete the file

        Returns:
            True if deleted, False if not found
        """
        skill = self._skills.get(name)
        if not skill:
            return False

        # Remove from index
        del self._skills[name]
        if name in self._by_category[skill.category]:
            self._by_category[skill.category].remove(name)

        # Delete file if requested
        if delete_file and skill.file_path:
            file_path = Path(skill.file_path)
            if file_path.exists():
                file_path.unlink()
                logger.info(f"Deleted skill file: {file_path}")

        return True

    def add_from_code(
        self,
        name: str,
        code: str,
        persist: bool = True,
    ) -> Skill:
        """
        Add a skill from code (typically agent-generated).

        Args:
            name: Skill name
            code: Python code
            persist: Whether to save to filesystem

        Returns:
            The added Skill
        """
        if persist:
            return self.save(name, code)
        else:
            # Just add to memory without persisting
            validation = validate_skill(code, name)
            if not validation.valid:
                raise ValueError(f"Invalid skill code: {'; '.join(validation.errors)}")

            metadata_dict = extract_skill_metadata(code)
            metadata = SkillMetadata(
                description=metadata_dict.get("description", ""),
                category=SkillCategory.from_string(metadata_dict.get("category", "custom")),
                stops_when=metadata_dict.get("stops_when", []),
                author="agent",
                created_at=datetime.now(),
            )

            skill = Skill(name=name, code=code, metadata=metadata)
            self._add_skill(skill)
            return skill

    def get_summary(self) -> dict:
        """
        Get a summary of the library contents.

        Returns:
            Dict with category counts and skill list
        """
        summary = {
            "total_skills": len(self._skills),
            "by_category": {},
            "skills": [],
        }

        for category in SkillCategory:
            count = len(self._by_category.get(category, []))
            if count > 0:
                summary["by_category"][category.value] = count

        for skill in self._skills.values():
            summary["skills"].append({
                "name": skill.name,
                "category": skill.category.value,
                "description": skill.description[:100] if skill.description else "",
            })

        return summary

    def format_for_prompt(self, max_skills: int = 20) -> str:
        """
        Format library contents for inclusion in LLM prompt.

        Args:
            max_skills: Maximum number of skills to include

        Returns:
            Formatted string describing available skills
        """
        lines = ["Available skills:"]

        skills = list(self._skills.values())[:max_skills]
        for skill in skills:
            desc = skill.description[:80] + "..." if len(skill.description) > 80 else skill.description
            stops = ", ".join(skill.metadata.stops_when[:3]) if skill.metadata.stops_when else "various"
            lines.append(f"- {skill.name} ({skill.category.value}): {desc}")
            lines.append(f"  Stops when: {stops}")

        if len(self._skills) > max_skills:
            lines.append(f"  ... and {len(self._skills) - max_skills} more skills")

        return "\n".join(lines)
