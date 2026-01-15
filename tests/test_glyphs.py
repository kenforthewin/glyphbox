"""Tests for glyph parsing."""

import pytest
from nle import nethack

from src.api.glyphs import (
    GlyphType,
    is_hostile_glyph,
    is_item_glyph,
    is_monster_glyph,
    is_walkable_glyph,
    parse_glyph,
)


class TestGlyphParsing:
    """Tests for glyph parsing functions."""

    def test_parse_monster_glyph(self):
        """Test parsing a monster glyph."""
        # Grid bug is monster ID 110
        glyph = nethack.GLYPH_MON_OFF + 110
        info = parse_glyph(glyph, "x", description="grid bug")

        assert info.glyph_type == GlyphType.MONSTER
        assert info.char == "x"
        assert "grid bug" in info.name.lower()
        assert info.monster_id == 110
        assert info.is_walkable is False

    def test_parse_pet_glyph(self):
        """Test parsing a pet glyph."""
        # Little dog is monster ID 16
        glyph = nethack.GLYPH_PET_OFF + 16
        info = parse_glyph(glyph, "d", description="little dog")

        assert info.glyph_type == GlyphType.PET
        assert info.is_tame is True
        assert info.is_hostile is False
        assert "dog" in info.name.lower()

    def test_parse_object_glyph(self):
        """Test parsing an object glyph."""
        glyph = nethack.GLYPH_OBJ_OFF + 100
        info = parse_glyph(glyph, "%")

        assert info.glyph_type == GlyphType.OBJECT
        assert info.is_walkable is True  # Can walk over items
        assert info.object_id == 100

    def test_parse_cmap_floor(self):
        """Test parsing floor terrain."""
        # Floor is cmap ID 12
        glyph = nethack.GLYPH_CMAP_OFF + 12
        info = parse_glyph(glyph, ".")

        assert info.glyph_type == GlyphType.CMAP
        assert info.is_walkable is True
        assert info.cmap_id == 12

    def test_parse_cmap_wall(self):
        """Test parsing wall terrain."""
        # Vertical wall is cmap ID 1
        glyph = nethack.GLYPH_CMAP_OFF + 1
        info = parse_glyph(glyph, "|")

        assert info.glyph_type == GlyphType.CMAP
        assert info.is_walkable is False
        assert info.cmap_id == 1

    def test_parse_cmap_door(self):
        """Test parsing door terrain."""
        # Closed door is cmap ID 15, open door is 16, broken door is 17
        closed_glyph = nethack.GLYPH_CMAP_OFF + 15
        open_glyph = nethack.GLYPH_CMAP_OFF + 16
        broken_glyph = nethack.GLYPH_CMAP_OFF + 17

        closed_info = parse_glyph(closed_glyph, "+")
        open_info = parse_glyph(open_glyph, "-")
        broken_info = parse_glyph(broken_glyph, "-")

        # Closed doors are NOT walkable (must be opened first)
        assert closed_info.is_walkable is False
        # Open and broken doors ARE walkable
        assert open_info.is_walkable is True
        assert broken_info.is_walkable is True


class TestGlyphPredicates:
    """Tests for glyph predicate functions."""

    def test_is_monster_glyph(self):
        monster_glyph = nethack.GLYPH_MON_OFF + 50
        pet_glyph = nethack.GLYPH_PET_OFF + 16
        object_glyph = nethack.GLYPH_OBJ_OFF + 10
        cmap_glyph = nethack.GLYPH_CMAP_OFF + 12

        assert is_monster_glyph(monster_glyph) is True
        assert is_monster_glyph(pet_glyph) is True  # Pets are monsters too
        assert is_monster_glyph(object_glyph) is False
        assert is_monster_glyph(cmap_glyph) is False

    def test_is_hostile_glyph(self):
        monster_glyph = nethack.GLYPH_MON_OFF + 50
        pet_glyph = nethack.GLYPH_PET_OFF + 16
        object_glyph = nethack.GLYPH_OBJ_OFF + 10

        assert is_hostile_glyph(monster_glyph) is True
        assert is_hostile_glyph(pet_glyph) is False  # Pets are not hostile
        assert is_hostile_glyph(object_glyph) is False

    def test_is_item_glyph(self):
        object_glyph = nethack.GLYPH_OBJ_OFF + 10
        corpse_glyph = nethack.GLYPH_BODY_OFF + 5
        monster_glyph = nethack.GLYPH_MON_OFF + 50

        assert is_item_glyph(object_glyph) is True
        assert is_item_glyph(corpse_glyph) is True  # Corpses are items
        assert is_item_glyph(monster_glyph) is False

    def test_is_walkable_glyph(self):
        floor_glyph = nethack.GLYPH_CMAP_OFF + 12
        wall_glyph = nethack.GLYPH_CMAP_OFF + 1
        object_glyph = nethack.GLYPH_OBJ_OFF + 10

        assert is_walkable_glyph(floor_glyph) is True
        assert is_walkable_glyph(wall_glyph) is False
        assert is_walkable_glyph(object_glyph) is True  # Can walk over items
