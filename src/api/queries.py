"""
State query methods for parsing NLE observations.

These functions extract structured information from raw NLE observations.
"""

import re
from typing import Optional

import numpy as np

from .environment import Observation
from .glyphs import GlyphType, is_boulder_glyph, is_hostile_glyph, is_item_glyph, is_monster_glyph, parse_glyph
from .models import (
    Alignment,
    BUCStatus,
    DungeonLevel,
    Encumbrance,
    HungerState,
    Item,
    Monster,
    ObjectClass,
    Position,
    Stats,
    Tile,
)

# Blstats indices (from NLE documentation)
BL_X = 0
BL_Y = 1
BL_STR25 = 2
BL_STR125 = 3
BL_DEX = 4
BL_CON = 5
BL_INT = 6
BL_WIS = 7
BL_CHA = 8
BL_SCORE = 9
BL_HP = 10
BL_HPMAX = 11
BL_DEPTH = 12
BL_GOLD = 13
BL_ENE = 14
BL_ENEMAX = 15
BL_AC = 16
BL_HD = 17
BL_XP = 18
BL_EXP = 19
BL_TIME = 20
BL_HUNGER = 21
BL_CAP = 22
BL_DNUM = 23
BL_DLEVEL = 24
BL_CONDITION = 25
BL_ALIGN = 26

# Condition mask values (bit flags in blstats[BL_CONDITION])
BL_MASK_BLIND = 32
BL_MASK_CONF = 256
BL_MASK_STUN = 128
BL_MASK_FLY = 2048
BL_MASK_LEV = 1024

# Dungeon branch numbers
DNUM_DUNGEONS_OF_DOOM = 0
DNUM_GEHENNOM = 1
DNUM_GNOMISH_MINES = 2
DNUM_QUEST = 3
DNUM_SOKOBAN = 4

# Monster IDs for special detection
MONSTER_ID_SHOPKEEPER = 268
MONSTER_ID_GRID_BUG = 110


def is_blind(obs: Observation) -> bool:
    """Check if player is blind."""
    condition = int(obs.blstats[BL_CONDITION])
    return bool(condition & BL_MASK_BLIND)


def is_confused(obs: Observation) -> bool:
    """Check if player is confused."""
    condition = int(obs.blstats[BL_CONDITION])
    return bool(condition & BL_MASK_CONF)


def is_stunned(obs: Observation) -> bool:
    """Check if player is stunned."""
    condition = int(obs.blstats[BL_CONDITION])
    return bool(condition & BL_MASK_STUN)


def can_fly(obs: Observation) -> bool:
    """Check if player can fly (flying or levitating)."""
    condition = int(obs.blstats[BL_CONDITION])
    return bool(condition & (BL_MASK_FLY | BL_MASK_LEV))


def in_sokoban(obs: Observation) -> bool:
    """Check if player is in Sokoban branch."""
    dungeon_num = int(obs.blstats[BL_DNUM])
    return dungeon_num == DNUM_SOKOBAN


def is_grid_bug_form(obs: Observation) -> bool:
    """Check if player is polymorphed into grid bug (cardinal movement only)."""
    from nle import nethack
    pos = get_position(obs)
    glyph = int(obs.glyphs[pos.y, pos.x])
    if nethack.glyph_is_monster(glyph):
        mon_id = nethack.glyph_to_mon(glyph)
        return mon_id == MONSTER_ID_GRID_BUG
    return False


def find_shopkeeper(obs: Observation) -> Optional[Position]:
    """Find shopkeeper position on current level, or None if not visible."""
    from nle import nethack
    for y in range(21):
        for x in range(79):
            glyph = int(obs.glyphs[y, x])
            if nethack.glyph_is_monster(glyph):
                mon_id = nethack.glyph_to_mon(glyph)
                if mon_id == MONSTER_ID_SHOPKEEPER:
                    return Position(x, y)
    return None


def is_near_shopkeeper(x: int, y: int, obs: Observation, radius: int = 10) -> bool:
    """Check if position is near a shopkeeper (likely in shop)."""
    shopkeeper = find_shopkeeper(obs)
    if shopkeeper is None:
        return False
    return abs(x - shopkeeper.x) <= radius and abs(y - shopkeeper.y) <= radius


def get_stats(obs: Observation) -> Stats:
    """
    Parse blstats into Stats dataclass.

    Args:
        obs: NLE observation

    Returns:
        Stats with all player statistics
    """
    bl = obs.blstats

    # Strength handling - NLE uses str25 for 18/** notation
    str_val = int(bl[BL_STR25])
    if str_val > 18:
        str_val = 18  # Cap at 18 for display, actual value in str125

    return Stats(
        hp=int(bl[BL_HP]),
        max_hp=int(bl[BL_HPMAX]),
        pw=int(bl[BL_ENE]),
        max_pw=int(bl[BL_ENEMAX]),
        ac=int(bl[BL_AC]),
        xp_level=int(bl[BL_XP]),
        xp_points=int(bl[BL_EXP]),
        gold=int(bl[BL_GOLD]),
        strength=str_val,
        dexterity=int(bl[BL_DEX]),
        constitution=int(bl[BL_CON]),
        intelligence=int(bl[BL_INT]),
        wisdom=int(bl[BL_WIS]),
        charisma=int(bl[BL_CHA]),
        hunger=HungerState.from_blstats(int(bl[BL_HUNGER])),
        encumbrance=Encumbrance.from_blstats(int(bl[BL_CAP])),
        alignment=Alignment.from_blstats(int(bl[BL_ALIGN])),
        dungeon_level=int(bl[BL_DLEVEL]),
        dungeon_number=int(bl[BL_DNUM]),
        turn=int(bl[BL_TIME]),
        score=int(bl[BL_SCORE]),
        position=Position(int(bl[BL_X]), int(bl[BL_Y])),
    )


def get_position(obs: Observation) -> Position:
    """Get player's current position."""
    return Position(int(obs.blstats[BL_X]), int(obs.blstats[BL_Y]))


def get_screen(obs: Observation) -> str:
    """Get the raw ASCII screen (24x80)."""
    return obs.get_screen()


def get_message(obs: Observation) -> str:
    """Get the current game message."""
    return obs.get_message()


def get_visible_monsters(obs: Observation) -> list[Monster]:
    """
    Get all monsters currently visible on screen.

    Args:
        obs: NLE observation

    Returns:
        List of Monster objects for all visible monsters (excluding player)
    """
    monsters = []
    player_pos = get_position(obs)

    for y in range(21):
        for x in range(79):
            glyph = int(obs.glyphs[y, x])
            if is_monster_glyph(glyph):
                pos = Position(x, y)
                # Skip player position
                if pos == player_pos:
                    continue

                char = chr(obs.chars[y, x])
                color = int(obs.colors[y, x])
                # Get description from screen_descriptions for accurate monster name
                description = ""
                if obs.screen_descriptions is not None:
                    desc_bytes = bytes(obs.screen_descriptions[y, x])
                    description = desc_bytes.decode("latin-1", errors="replace").rstrip("\x00")
                info = parse_glyph(glyph, char, description)

                # Determine hostility from screen description
                # NetHack prefixes peaceful monsters with "peaceful "
                is_peaceful = "peaceful" in description.lower()
                is_tame = info.glyph_type == GlyphType.PET

                monsters.append(
                    Monster(
                        glyph=glyph,
                        char=char,
                        name=info.name,
                        position=pos,
                        color=color,
                        is_peaceful=is_peaceful,
                        is_tame=is_tame,
                        threat_level=_estimate_threat(info.monster_id or 0),
                    )
                )

    return monsters


def get_adjacent_monsters(obs: Observation) -> list[Monster]:
    """
    Get monsters in the 8 adjacent tiles.

    Args:
        obs: NLE observation

    Returns:
        List of Monster objects adjacent to player
    """
    all_monsters = get_visible_monsters(obs)
    player_pos = get_position(obs)

    return [m for m in all_monsters if player_pos.chebyshev_distance(m.position) == 1]


def get_hostile_monsters(obs: Observation) -> list[Monster]:
    """Get only hostile (non-pet, non-peaceful) monsters."""
    monsters = get_visible_monsters(obs)
    return [m for m in monsters if m.is_hostile]


def get_items_at(obs: Observation, pos: Position) -> list[Item]:
    """
    Get items at a specific position.

    Note: NLE doesn't provide detailed item info for items on the ground
    unless the player is standing on them. This returns a basic Item
    based on the glyph.
    """
    items = []

    glyph = int(obs.glyphs[pos.y, pos.x])
    if is_item_glyph(glyph):
        char = chr(obs.chars[pos.y, pos.x])
        description = ""
        if obs.screen_descriptions is not None:
            desc_bytes = bytes(obs.screen_descriptions[pos.y, pos.x])
            description = desc_bytes.decode("latin-1", errors="replace").rstrip("\x00")
        info = parse_glyph(glyph, char, description)

        items.append(
            Item(
                glyph=glyph,
                name=info.name,
                char=char,
                position=pos,
                object_class=_char_to_object_class(char),
            )
        )

    return items


def get_items_here(obs: Observation) -> list[Item]:
    """Get items at player's current position."""
    return get_items_at(obs, get_position(obs))


def find_items_on_map(obs: Observation) -> list[Item]:
    """
    Find all visible items on the map.

    Args:
        obs: NLE observation

    Returns:
        List of Item objects for all visible items (not in inventory)
    """
    items = []

    for y in range(21):
        for x in range(79):
            glyph = int(obs.glyphs[y, x])
            # Skip boulders - they show as items but can't be picked up normally
            if is_item_glyph(glyph) and not is_boulder_glyph(glyph):
                pos = Position(x, y)
                char = chr(obs.chars[y, x])
                description = ""
                if obs.screen_descriptions is not None:
                    desc_bytes = bytes(obs.screen_descriptions[y, x])
                    description = desc_bytes.decode("latin-1", errors="replace").rstrip("\x00")
                info = parse_glyph(glyph, char, description)

                items.append(
                    Item(
                        glyph=glyph,
                        name=info.name,
                        char=char,
                        position=pos,
                        object_class=_char_to_object_class(char),
                    )
                )

    return items


def get_inventory(obs: Observation) -> list[Item]:
    """
    Parse inventory from observations.

    Args:
        obs: NLE observation with inv_strs, inv_letters, inv_oclasses, inv_glyphs

    Returns:
        List of Item objects in inventory
    """
    items = []

    for i in range(len(obs.inv_letters)):
        letter = int(obs.inv_letters[i])
        if letter == 0:  # Empty slot
            continue

        slot = chr(letter)
        glyph = int(obs.inv_glyphs[i])
        oclass = int(obs.inv_oclasses[i])

        # Parse item string
        item_str = bytes(obs.inv_strs[i]).decode("latin-1", errors="replace")
        item_str = item_str.rstrip("\x00").strip()

        if not item_str:
            continue

        # Parse quantity and name from string like "a +0 long sword" or "3 food rations"
        quantity = 1
        name = item_str
        buc = BUCStatus.UNKNOWN
        identified = False

        # Check for quantity prefix
        match = re.match(r"^(\d+)\s+", item_str)
        if match:
            quantity = int(match.group(1))
            name = item_str[match.end() :]
        elif item_str.startswith("a ") or item_str.startswith("an "):
            name = item_str.split(" ", 1)[1] if " " in item_str else item_str

        # Check for BUC status
        if "blessed" in name.lower():
            buc = BUCStatus.BLESSED
        elif "cursed" in name.lower():
            buc = BUCStatus.CURSED
        elif "uncursed" in name.lower():
            buc = BUCStatus.UNCURSED

        # Check if identified (has +/- enchantment visible usually means identified)
        if re.search(r"[+-]\d+", name):
            identified = True

        items.append(
            Item(
                glyph=glyph,
                name=name,
                slot=slot,
                quantity=quantity,
                buc_status=buc,
                identified=identified,
                object_class=ObjectClass.from_oclass(oclass),
            )
        )

    return items


def get_food_in_inventory(obs: Observation) -> list[Item]:
    """Get food items from inventory."""
    inventory = get_inventory(obs)
    return [item for item in inventory if item.is_food]


def get_weapons_in_inventory(obs: Observation) -> list[Item]:
    """Get weapon items from inventory."""
    inventory = get_inventory(obs)
    return [item for item in inventory if item.is_weapon]


def get_current_level(obs: Observation) -> DungeonLevel:
    """
    Build a DungeonLevel from current observations.

    Args:
        obs: NLE observation

    Returns:
        DungeonLevel with parsed tile grid
    """
    stats = get_stats(obs)
    tiles = []
    explored_count = 0
    walkable_count = 0

    for y in range(21):
        row = []
        for x in range(79):
            glyph = int(obs.glyphs[y, x])
            char = chr(obs.chars[y, x])
            color = int(obs.colors[y, x])

            # Get description from screen_descriptions (authoritative for names)
            description = ""
            if obs.screen_descriptions is not None:
                desc_bytes = bytes(obs.screen_descriptions[y, x])
                description = desc_bytes.decode("latin-1", errors="replace").rstrip("\x00")

            info = parse_glyph(glyph, char, description)

            # Determine if explored (non-stone)
            is_explored = info.glyph_type != GlyphType.CMAP or info.cmap_id != 0

            # Determine feature type
            feature = None
            if info.name in ["closed door", "open door", "broken door"]:
                feature = "door"
            elif info.name == "altar":
                feature = "altar"
            elif info.name == "fountain":
                feature = "fountain"
            elif info.name == "throne":
                feature = "throne"
            elif info.name == "sink":
                feature = "sink"
            elif info.name == "grave":
                feature = "grave"
            elif "stairs" in info.name or "ladder" in info.name:
                feature = "stairs"

            # Check for traps
            has_trap = "trap" in info.name.lower()
            trap_type = info.name if has_trap else None

            tile = Tile(
                char=char,
                glyph=glyph,
                position=Position(x, y),
                color=color,
                description=description,
                is_walkable=info.is_walkable,
                is_explored=is_explored,
                has_trap=has_trap,
                trap_type=trap_type,
                feature=feature,
            )
            row.append(tile)

            if is_explored:
                explored_count += 1
            if info.is_walkable and is_explored:
                walkable_count += 1

        tiles.append(row)

    # Determine branch name
    branch = _dungeon_number_to_branch(stats.dungeon_number)

    return DungeonLevel(
        level_number=stats.dungeon_level,
        dungeon_number=stats.dungeon_number,
        branch=branch,
        tiles=tiles,
        explored_tiles=explored_count,
        total_walkable=max(walkable_count, 1),  # Avoid division by zero
    )


def find_stairs(obs: Observation) -> tuple[Optional[Position], Optional[Position]]:
    """
    Find stairs up and down on current level.

    Returns:
        Tuple of (stairs_up_position, stairs_down_position), either may be None
    """
    stairs_up = None
    stairs_down = None

    for y in range(21):
        for x in range(79):
            char = chr(obs.chars[y, x])
            if char == "<":
                stairs_up = Position(x, y)
            elif char == ">":
                stairs_down = Position(x, y)

    return stairs_up, stairs_down


def find_doors(obs: Observation) -> list[tuple[Position, bool]]:
    """
    Find all doors on current level.

    Returns:
        List of (position, is_open) tuples
    """
    doors = []

    for y in range(21):
        for x in range(79):
            glyph = int(obs.glyphs[y, x])
            info = parse_glyph(glyph)

            if info.cmap_id == 15:  # Closed door
                doors.append((Position(x, y), False))
            elif info.cmap_id == 16:  # Open door
                doors.append((Position(x, y), True))

    return doors


def _estimate_threat(monster_id: int) -> int:
    """Estimate threat level of a monster (0-10 scale)."""
    # Very rough heuristic based on monster ID ranges
    # Lower IDs tend to be weaker monsters
    if monster_id < 30:
        return 1
    elif monster_id < 60:
        return 2
    elif monster_id < 100:
        return 3
    elif monster_id < 150:
        return 5
    elif monster_id < 200:
        return 7
    else:
        return 9


def _char_to_object_class(char: str) -> ObjectClass:
    """Convert item character to object class."""
    mapping = {
        ")": ObjectClass.WEAPON,
        "[": ObjectClass.ARMOR,
        "=": ObjectClass.RING,
        '"': ObjectClass.AMULET,
        "(": ObjectClass.TOOL,
        "%": ObjectClass.FOOD,
        "!": ObjectClass.POTION,
        "?": ObjectClass.SCROLL,
        "+": ObjectClass.SPELLBOOK,
        "/": ObjectClass.WAND,
        "$": ObjectClass.COIN,
        "*": ObjectClass.GEM,
        "`": ObjectClass.ROCK,
        "0": ObjectClass.BALL,
        "_": ObjectClass.CHAIN,
    }
    return mapping.get(char, ObjectClass.ILLOBJ)


def _dungeon_number_to_branch(dnum: int) -> str:
    """Convert dungeon number to branch name."""
    branches = {
        0: "Dungeons of Doom",
        1: "Gehennom",
        2: "Gnomish Mines",
        3: "Quest",
        4: "Sokoban",
        5: "Fort Ludios",
        6: "Vlad's Tower",
        7: "Elemental Planes",
    }
    return branches.get(dnum, f"Unknown Branch {dnum}")
