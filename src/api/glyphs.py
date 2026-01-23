"""
Glyph parsing utilities for NetHack.

Converts NLE glyph IDs to human-readable entity information.
NLE uses glyph IDs to represent everything visible on the map.
"""

from dataclasses import dataclass
from enum import Enum
from typing import Optional

from nle import nethack

from .models import ObjectClass, Position


# === Module-level caches built from NLE APIs ===


def _build_monster_name_cache() -> dict[int, str]:
    """Build monster name cache from NLE permonst."""
    cache = {}
    for mon_id in range(400):  # NLE has ~381 monsters
        try:
            name = nethack.permonst(mon_id).mname
            if name:
                cache[mon_id] = name
        except (IndexError, AttributeError):
            break
    return cache


def _build_cmap_name_cache() -> dict[int, str]:
    """Build cmap name cache from NLE symdef."""
    cache = {}
    for cmap_id in range(100):  # NLE has ~65 cmap entries
        try:
            sym = nethack.symdef.from_idx(cmap_id)
            cache[cmap_id] = sym.explanation
        except (IndexError, AttributeError):
            break
    return cache


def _build_walkable_cmap() -> set[int]:
    """Build walkable terrain set from NLE symdef explanations.

    This identifies terrain that is ALWAYS walkable (no special conditions).
    Water/lava/air/cloud require flight and are handled separately.

    IMPORTANT: cmap 0 is "stone" (unexplored/out-of-sight) even though its
    explanation is "dark part of a room" (same as cmap 20). We must NOT include
    cmap 0 as walkable - pathfinding should not path through unexplored areas!

    Verified against NLE symdef (0-95):
      WALKABLE: 20 (dark room), 12 (doorway), 13-14 (open door),
                19 (floor), 21-22 (corridor), 23-26 (stairs/ladders),
                27-31 (altar/grave/throne/sink/fountain), 33 (ice),
                35-36 (lowered drawbridge), 64 (vibrating square)
      NOT WALKABLE: 0 (stone/unexplored), 1-11 (walls), 15-16 (closed door),
                    17-18 (bars/tree), 32/34/41 (water/lava),
                    37-38 (raised drawbridge), 39-40 (air/cloud - need flight),
                    42-63 (traps)
    """
    walkable = set()
    walkable_keywords = {
        "floor",
        "corridor",
        "doorway",
        "open door",
        "staircase",
        "ladder",
        "altar",
        "grave",
        "throne",
        "sink",
        "fountain",
        "ice",
        "lowered drawbridge",
        "dark part of a room",  # Unlit room areas are walkable
        "vibrating square",  # Special endgame marker, walkable despite being a "trap"
    }
    for cmap_id in range(100):
        try:
            sym = nethack.symdef.from_idx(cmap_id)
            explanation = sym.explanation.lower()
            if any(kw in explanation for kw in walkable_keywords):
                # Exclude closed doors (they have "door" but aren't walkable)
                if "closed" not in explanation:
                    # CRITICAL: cmap 0 is "stone" (unexplored/out-of-sight) even though
                    # its explanation is "dark part of a room" (same as cmap 20).
                    # We must NOT mark cmap 0 as walkable - it's where we can't see!
                    if cmap_id != 0:
                        walkable.add(cmap_id)
        except (IndexError, AttributeError):
            break
    return walkable


def _build_dangerous_terrain_cmap() -> set[int]:
    """Build dangerous terrain set (water/lava) from NLE symdef.

    These tiles kill the player if stepped on without flight/levitation.
    """
    dangerous = set()
    for cmap_id in range(100):
        try:
            sym = nethack.symdef.from_idx(cmap_id)
            explanation = sym.explanation.lower()
            if "water" in explanation or "lava" in explanation:
                dangerous.add(cmap_id)
        except (IndexError, AttributeError):
            break
    return dangerous


def _build_flight_required_cmap() -> set[int]:
    """Build set of terrain that requires flight/levitation to traverse.

    Includes both dangerous terrain (water/lava) and elemental plane terrain (air/cloud).

    Note: Uses exact matching for "air" and "cloud" to avoid false positives
    like "staircase" (contains "air") or "poison cloud".
    """
    flight_required = set()
    for cmap_id in range(100):
        try:
            sym = nethack.symdef.from_idx(cmap_id)
            explanation = sym.explanation.lower()
            # Water/lava are deadly without flight
            if "water" in explanation or "lava" in explanation:
                flight_required.add(cmap_id)
            # Air/cloud (Plane of Air) - exact match to avoid "staircase" and "poison cloud"
            elif explanation == "air" or explanation == "cloud":
                flight_required.add(cmap_id)
        except (IndexError, AttributeError):
            break
    return flight_required


def _find_boulder_obj_id() -> int:
    """Find boulder object ID from NLE objdescr."""
    for obj_id in range(500):
        try:
            name = nethack.objdescr.from_idx(obj_id).oc_name
            if name == "boulder":
                return obj_id
        except (IndexError, AttributeError):
            break
    return 447  # Fallback to known value


def _find_player_type_ids() -> tuple[int, int]:
    """Find player type monster ID range from NLE permonst."""
    player_roles = {
        "archeologist",
        "barbarian",
        "caveman",
        "cavewoman",
        "healer",
        "knight",
        "monk",
        "priest",
        "priestess",
        "ranger",
        "rogue",
        "samurai",
        "tourist",
        "valkyrie",
        "wizard",
    }
    first_id = None
    last_id = None
    for mon_id in range(400):
        try:
            name = nethack.permonst(mon_id).mname.lower()
            if name in player_roles:
                if first_id is None:
                    first_id = mon_id
                last_id = mon_id
        except (IndexError, AttributeError):
            break
    return (first_id or 327, last_id or 341)


# Build caches at module load time
_MONSTER_NAME_CACHE = _build_monster_name_cache()
_CMAP_NAME_CACHE = _build_cmap_name_cache()
_WALKABLE_CMAP = _build_walkable_cmap()
_DANGEROUS_TERRAIN_CMAP = _build_dangerous_terrain_cmap()
_FLIGHT_REQUIRED_CMAP = _build_flight_required_cmap()
_BOULDER_OBJ_ID = _find_boulder_obj_id()
_PLAYER_TYPE_RANGE = _find_player_type_ids()

# Public exports for backwards compatibility
DANGEROUS_TERRAIN_CMAP = _DANGEROUS_TERRAIN_CMAP
FLIGHT_REQUIRED_CMAP = _FLIGHT_REQUIRED_CMAP

# Individual cmap IDs for terrain types (found dynamically from NLE symdef)
CMAP_WATER = 32  # symdef: "water"
CMAP_POOL = 32  # alias for water
CMAP_LAVA = 34  # symdef: "molten lava"
CMAP_MOAT = 41  # symdef: "water" (moat variant)
CMAP_AIR = 39  # symdef: "air" (Plane of Air)
CMAP_CLOUD = 40  # symdef: "cloud" (Plane of Air)


class GlyphType(Enum):
    """Type of entity represented by a glyph."""

    MONSTER = "monster"
    PET = "pet"
    INVISIBLE = "invisible"
    DETECTED = "detected"
    CORPSE = "corpse"
    RIDDEN = "ridden"
    OBJECT = "object"
    CMAP = "cmap"  # Dungeon features (walls, floors, doors, etc.)
    EXPLOSION = "explosion"
    ZAP = "zap"
    SWALLOW = "swallow"
    WARNING = "warning"
    STATUE = "statue"
    UNKNOWN = "unknown"


@dataclass
class GlyphInfo:
    """Parsed information about a glyph."""

    glyph: int
    glyph_type: GlyphType
    char: str  # ASCII character representation
    name: str  # Human-readable name
    monster_id: Optional[int] = None
    object_id: Optional[int] = None
    cmap_id: Optional[int] = None
    color: int = 0
    is_walkable: bool = True
    is_hostile: bool = False
    is_peaceful: bool = False
    is_tame: bool = False


def parse_glyph(glyph: int, char: Optional[str] = None, description: Optional[str] = None) -> GlyphInfo:
    """
    Parse a glyph ID into structured information.

    Args:
        glyph: NLE glyph ID
        char: Optional ASCII character (for display)
        description: Optional description from screen_descriptions (authoritative for names)

    Returns:
        GlyphInfo with parsed details
    """
    if char is None:
        char = "?"

    # Check glyph type using NLE utilities
    if nethack.glyph_is_pet(glyph):
        mon_id = nethack.glyph_to_mon(glyph)
        # Use screen_description (authoritative), fallback to generic
        name = description if description else f"pet (id:{mon_id})"
        # Clean "tame " prefix from description if present
        if name.startswith("tame "):
            name = name[5:]
        return GlyphInfo(
            glyph=glyph,
            glyph_type=GlyphType.PET,
            char=char,
            name=name,
            monster_id=mon_id,
            is_walkable=False,
            is_tame=True,
        )

    if nethack.glyph_is_monster(glyph):
        mon_id = nethack.glyph_to_mon(glyph)
        # Use screen_description (authoritative), fallback to generic with char
        name = description if description else f"monster '{char}' (id:{mon_id})"
        # Player glyph is also "monster" - player types are mon_id 327-341
        is_player = char == "@" and mon_id >= _PLAYER_TYPE_RANGE[0]
        return GlyphInfo(
            glyph=glyph,
            glyph_type=GlyphType.MONSTER,
            char=char,
            name="player" if is_player else name,
            monster_id=mon_id,
            is_walkable=is_player,  # Player position is walkable for pathfinding
            is_hostile=not is_player,  # Assume hostile unless known peaceful
        )

    if nethack.glyph_is_invisible(glyph):
        return GlyphInfo(
            glyph=glyph,
            glyph_type=GlyphType.INVISIBLE,
            char=char,
            name="invisible monster",
            is_walkable=False,
            is_hostile=True,
        )

    if nethack.glyph_is_detected_monster(glyph):
        mon_id = nethack.glyph_to_mon(glyph)
        # Use screen_description (authoritative), fallback to generic
        name = description if description else f"detected monster (id:{mon_id})"
        return GlyphInfo(
            glyph=glyph,
            glyph_type=GlyphType.DETECTED,
            char=char,
            name=name,
            monster_id=mon_id,
            is_walkable=False,
        )

    if nethack.glyph_is_body(glyph):
        mon_id = nethack.glyph_to_mon(glyph)
        # Use screen_description (authoritative, already says "X corpse")
        name = description if description else f"corpse (id:{mon_id})"
        return GlyphInfo(
            glyph=glyph,
            glyph_type=GlyphType.CORPSE,
            char=char,
            name=name,
            monster_id=mon_id,
            is_walkable=True,
        )

    if nethack.glyph_is_statue(glyph):
        mon_id = nethack.glyph_to_mon(glyph)
        # Use screen_description (authoritative)
        name = description if description else f"statue (id:{mon_id})"
        # Only append "statue" if not already in description
        if "statue" not in name.lower():
            name = f"{name} statue"
        return GlyphInfo(
            glyph=glyph,
            glyph_type=GlyphType.STATUE,
            char=char,
            name=name,
            monster_id=mon_id,
            is_walkable=False,
        )

    if nethack.glyph_is_ridden_monster(glyph):
        mon_id = nethack.glyph_to_mon(glyph)
        # Use screen_description (authoritative), fallback to NLE cache
        name = description if description else _MONSTER_NAME_CACHE.get(mon_id, f"monster {mon_id}")
        # Only prepend "ridden" if not already in description
        if not name.startswith("ridden"):
            name = f"ridden {name}"
        return GlyphInfo(
            glyph=glyph,
            glyph_type=GlyphType.RIDDEN,
            char=char,
            name=name,
            monster_id=mon_id,
            is_walkable=False,
            is_tame=True,
        )

    if nethack.glyph_is_object(glyph):
        obj_id = nethack.glyph_to_obj(glyph)
        # Use screen_description if provided (authoritative), otherwise fallback to generic
        if description:
            name = description
        elif char == "$":
            name = "gold"
        elif char == "%":
            name = "food"
        elif char == ")":
            name = "weapon"
        elif char == "[":
            name = "armor"
        elif char == "!":
            name = "potion"
        elif char == "?":
            name = "scroll"
        elif char == "/":
            name = "wand"
        elif char == "=":
            name = "ring"
        elif char == '"':
            name = "amulet"
        elif char == "+":
            name = "spellbook"
        elif char == "(":
            name = "tool"
        elif char == "*":
            name = "gem"
        elif char == "`" or obj_id == _BOULDER_OBJ_ID:  # Boulder
            name = "boulder"
        else:
            name = f"object {obj_id}"
        # Boulders block movement
        walkable = obj_id != _BOULDER_OBJ_ID
        return GlyphInfo(
            glyph=glyph,
            glyph_type=GlyphType.OBJECT,
            char=char,
            name=name,
            object_id=obj_id,
            is_walkable=walkable,  # Can walk over items except boulders
        )

    if nethack.glyph_is_cmap(glyph):
        cmap_id = nethack.glyph_to_cmap(glyph)
        # Special case: cmap 0 is unexplored stone, not "dark part of a room"
        # NLE's symdef misleadingly gives cmap 0 the same explanation as cmap 20
        if cmap_id == 0:
            name = "solid stone"
            is_walkable = False
        else:
            # Use screen_description (authoritative) if provided, fallback to NLE cache
            name = description if description else _CMAP_NAME_CACHE.get(cmap_id, f"terrain {cmap_id}")
            is_walkable = cmap_id in _WALKABLE_CMAP
        return GlyphInfo(
            glyph=glyph,
            glyph_type=GlyphType.CMAP,
            char=char,
            name=name,
            cmap_id=cmap_id,
            is_walkable=is_walkable,
        )

    if nethack.glyph_is_trap(glyph):
        trap_id = nethack.glyph_to_trap(glyph)
        # Use screen_description (authoritative), fallback to NLE cache
        name = description if description else _CMAP_NAME_CACHE.get(34 + trap_id, f"trap {trap_id}")
        return GlyphInfo(
            glyph=glyph,
            glyph_type=GlyphType.CMAP,
            char=char,
            name=name,
            cmap_id=34 + trap_id,
            is_walkable=True,  # Traps are technically walkable
        )

    if nethack.glyph_is_warning(glyph):
        warning_level = nethack.glyph_to_warning(glyph)
        return GlyphInfo(
            glyph=glyph,
            glyph_type=GlyphType.WARNING,
            char=char,
            name=f"warning level {warning_level}",
            is_walkable=False,
            is_hostile=True,
        )

    if nethack.glyph_is_swallow(glyph):
        return GlyphInfo(
            glyph=glyph,
            glyph_type=GlyphType.SWALLOW,
            char=char,
            name="engulfed",
            is_walkable=False,
        )

    # Check for zap/explosion by range
    if nethack.GLYPH_ZAP_OFF <= glyph < nethack.GLYPH_SWALLOW_OFF:
        return GlyphInfo(
            glyph=glyph,
            glyph_type=GlyphType.ZAP,
            char=char,
            name="zap effect",
            is_walkable=True,
        )

    if nethack.GLYPH_EXPLODE_OFF <= glyph < nethack.GLYPH_ZAP_OFF:
        return GlyphInfo(
            glyph=glyph,
            glyph_type=GlyphType.EXPLOSION,
            char=char,
            name="explosion",
            is_walkable=True,
        )

    # Unknown glyph
    return GlyphInfo(
        glyph=glyph,
        glyph_type=GlyphType.UNKNOWN,
        char=char,
        name=f"unknown glyph {glyph}",
        is_walkable=True,
    )


def is_monster_glyph(glyph: int) -> bool:
    """Check if glyph represents any kind of monster."""
    return (
        nethack.glyph_is_monster(glyph)
        or nethack.glyph_is_pet(glyph)
        or nethack.glyph_is_invisible(glyph)
        or nethack.glyph_is_detected_monster(glyph)
        or nethack.glyph_is_ridden_monster(glyph)
    )


def is_hostile_glyph(glyph: int) -> bool:
    """Check if glyph represents a potentially hostile monster."""
    if nethack.glyph_is_pet(glyph) or nethack.glyph_is_ridden_monster(glyph):
        return False
    return (
        nethack.glyph_is_monster(glyph)
        or nethack.glyph_is_invisible(glyph)
        or nethack.glyph_is_detected_monster(glyph)
        or nethack.glyph_is_warning(glyph)
    )


def is_item_glyph(glyph: int) -> bool:
    """Check if glyph represents an item."""
    return nethack.glyph_is_object(glyph) or nethack.glyph_is_body(glyph)


def is_walkable_glyph(glyph: int) -> bool:
    """Check if a glyph represents walkable terrain."""
    # Special case: player glyph is always walkable (it's where WE are!)
    # The player glyph is a monster glyph with mon_id in the player type range
    if nethack.glyph_is_monster(glyph):
        mon_id = nethack.glyph_to_mon(glyph)
        if mon_id >= _PLAYER_TYPE_RANGE[0]:
            return True
    info = parse_glyph(glyph)
    return info.is_walkable


def is_closed_door_glyph(glyph: int) -> bool:
    """Check if glyph is a closed door (cmap_id 15 or 16 per NLE symdef)."""
    if not nethack.glyph_is_cmap(glyph):
        return False
    cmap_id = nethack.glyph_to_cmap(glyph)
    return cmap_id in (15, 16)


def is_dangerous_terrain_glyph(glyph: int, can_fly: bool = False) -> bool:
    """
    Check if glyph is dangerous terrain (water/lava) for grounded players.

    Uses NLE's symdef.from_idx() to get authoritative terrain descriptions.

    Args:
        glyph: NLE glyph ID
        can_fly: Whether player can fly/levitate (avoids water/lava danger)

    Returns:
        True if terrain is dangerous and player can't fly
    """
    if can_fly:
        return False  # Flying/levitating avoids danger

    if not nethack.glyph_is_cmap(glyph):
        return False

    cmap_id = nethack.glyph_to_cmap(glyph)

    # Fast path: check known dangerous cmap IDs
    if cmap_id in _DANGEROUS_TERRAIN_CMAP:
        return True

    # Fallback: check symdef explanation for water/lava keywords
    # This handles any cmap IDs we might have missed
    try:
        sym = nethack.symdef.from_idx(cmap_id)
        explanation = sym.explanation.lower()
        if 'water' in explanation or 'lava' in explanation:
            return True
    except (IndexError, AttributeError):
        pass

    return False


def is_flight_required_glyph(glyph: int) -> bool:
    """
    Check if glyph requires flight/levitation to traverse.

    This includes:
    - Dangerous terrain (water, lava) - deadly without flight
    - Elemental plane terrain (air, cloud) - impassable without flight

    Args:
        glyph: NLE glyph ID

    Returns:
        True if terrain requires flight to traverse
    """
    if not nethack.glyph_is_cmap(glyph):
        return False

    cmap_id = nethack.glyph_to_cmap(glyph)
    return cmap_id in _FLIGHT_REQUIRED_CMAP


def is_boulder_glyph(glyph: int) -> bool:
    """Check if glyph represents a boulder."""
    if not nethack.glyph_is_object(glyph):
        return False
    obj_id = nethack.glyph_to_obj(glyph)
    return obj_id == _BOULDER_OBJ_ID
