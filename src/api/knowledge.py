"""
NetHack knowledge base.

Contains information about monsters, items, and game mechanics.
This is a simplified version - a full implementation would include
data from the NetHack wiki or source code.
"""

from dataclasses import dataclass
from typing import Optional


@dataclass
class MonsterInfo:
    """Information about a monster type."""

    name: str
    symbol: str
    difficulty: int  # 0-30 scale
    speed: int  # Movement speed
    ac: int  # Armor class
    mr: int  # Magic resistance (0-100)
    attacks: list[str]  # Attack descriptions
    resistances: list[str]  # Resistances
    flags: list[str]  # Special flags (flies, swims, etc.)
    corpse_safe: bool  # Safe to eat corpse?
    corpse_effects: list[str]  # Effects of eating corpse


@dataclass
class ItemInfo:
    """Information about an item type."""

    name: str
    symbol: str
    weight: int  # In units
    price: int  # Base price in gold
    material: str  # iron, wood, cloth, etc.
    effects: list[str]  # Effects when used


# Monster database (subset of important monsters)
MONSTERS: dict[str, MonsterInfo] = {
    "grid bug": MonsterInfo(
        name="grid bug",
        symbol="x",
        difficulty=0,
        speed=12,
        ac=9,
        mr=0,
        attacks=["1d1 electric"],
        resistances=["electricity", "poison"],
        flags=["flies"],
        corpse_safe=True,
        corpse_effects=["shock resistance (if lucky)"],
    ),
    "lichen": MonsterInfo(
        name="lichen",
        symbol="F",
        difficulty=0,
        speed=1,
        ac=9,
        mr=0,
        attacks=["1d1 stick"],
        resistances=[],
        flags=["stationary"],
        corpse_safe=True,
        corpse_effects=[],
    ),
    "newt": MonsterInfo(
        name="newt",
        symbol=":",
        difficulty=0,
        speed=6,
        ac=8,
        mr=0,
        attacks=["1d2 bite"],
        resistances=[],
        flags=["swims"],
        corpse_safe=True,
        corpse_effects=["may increase max power"],
    ),
    "floating eye": MonsterInfo(
        name="floating eye",
        symbol="e",
        difficulty=2,
        speed=1,
        ac=9,
        mr=10,
        attacks=["0d0 passive paralyze"],
        resistances=[],
        flags=["flies", "amphibious"],
        corpse_safe=True,
        corpse_effects=["telepathy"],
    ),
    "little dog": MonsterInfo(
        name="little dog",
        symbol="d",
        difficulty=2,
        speed=18,
        ac=6,
        mr=0,
        attacks=["1d6 bite"],
        resistances=[],
        flags=["domestic", "carnivore"],
        corpse_safe=True,
        corpse_effects=["aggravate monster (if tame)"],
    ),
    "dog": MonsterInfo(
        name="dog",
        symbol="d",
        difficulty=4,
        speed=16,
        ac=5,
        mr=0,
        attacks=["1d6 bite"],
        resistances=[],
        flags=["domestic", "carnivore"],
        corpse_safe=True,
        corpse_effects=["aggravate monster (if tame)"],
    ),
    "kitten": MonsterInfo(
        name="kitten",
        symbol="f",
        difficulty=2,
        speed=18,
        ac=6,
        mr=0,
        attacks=["1d6 bite"],
        resistances=[],
        flags=["domestic", "carnivore"],
        corpse_safe=True,
        corpse_effects=["aggravate monster (if tame)"],
    ),
    "goblin": MonsterInfo(
        name="goblin",
        symbol="o",
        difficulty=0,
        speed=6,
        ac=10,
        mr=0,
        attacks=["1d4 weapon"],
        resistances=[],
        flags=["humanoid"],
        corpse_safe=True,
        corpse_effects=[],
    ),
    "hobgoblin": MonsterInfo(
        name="hobgoblin",
        symbol="o",
        difficulty=1,
        speed=9,
        ac=10,
        mr=0,
        attacks=["1d6 weapon"],
        resistances=[],
        flags=["humanoid"],
        corpse_safe=True,
        corpse_effects=[],
    ),
    "orc": MonsterInfo(
        name="orc",
        symbol="o",
        difficulty=1,
        speed=9,
        ac=10,
        mr=0,
        attacks=["1d8 weapon"],
        resistances=[],
        flags=["humanoid", "orc"],
        corpse_safe=True,
        corpse_effects=[],
    ),
    "kobold": MonsterInfo(
        name="kobold",
        symbol="k",
        difficulty=0,
        speed=6,
        ac=10,
        mr=0,
        attacks=["1d4 weapon"],
        resistances=["poison"],
        flags=["humanoid", "poisonous"],
        corpse_safe=False,
        corpse_effects=["poison"],
    ),
    "jackal": MonsterInfo(
        name="jackal",
        symbol="d",
        difficulty=0,
        speed=12,
        ac=7,
        mr=0,
        attacks=["1d2 bite"],
        resistances=[],
        flags=["carnivore"],
        corpse_safe=True,
        corpse_effects=[],
    ),
    "sewer rat": MonsterInfo(
        name="sewer rat",
        symbol="r",
        difficulty=0,
        speed=12,
        ac=7,
        mr=0,
        attacks=["1d3 bite"],
        resistances=[],
        flags=["carnivore"],
        corpse_safe=True,
        corpse_effects=[],
    ),
    "giant rat": MonsterInfo(
        name="giant rat",
        symbol="r",
        difficulty=1,
        speed=10,
        ac=7,
        mr=0,
        attacks=["1d3 bite"],
        resistances=[],
        flags=["carnivore"],
        corpse_safe=True,
        corpse_effects=[],
    ),
    "gnome": MonsterInfo(
        name="gnome",
        symbol="G",
        difficulty=1,
        speed=6,
        ac=10,
        mr=0,
        attacks=["1d6 weapon"],
        resistances=[],
        flags=["humanoid", "gnome"],
        corpse_safe=True,
        corpse_effects=[],
    ),
    "dwarf": MonsterInfo(
        name="dwarf",
        symbol="h",
        difficulty=2,
        speed=6,
        ac=10,
        mr=10,
        attacks=["1d8 weapon"],
        resistances=[],
        flags=["humanoid", "dwarf"],
        corpse_safe=True,
        corpse_effects=[],
    ),
    "cockatrice": MonsterInfo(
        name="cockatrice",
        symbol="c",
        difficulty=5,
        speed=6,
        ac=6,
        mr=30,
        attacks=["1d3 bite petrify", "0d0 touch petrify"],
        resistances=["poison", "petrification"],
        flags=["poisonous"],
        corpse_safe=False,
        corpse_effects=["instant petrification!"],
    ),
    "acid blob": MonsterInfo(
        name="acid blob",
        symbol="b",
        difficulty=1,
        speed=3,
        ac=8,
        mr=0,
        attacks=["0d0 passive acid"],
        resistances=["acid", "sleep", "poison", "petrification"],
        flags=["mindless", "amorphous"],
        corpse_safe=False,
        corpse_effects=["acid damage"],
    ),
}

# Dangerous monsters to avoid in melee
DANGEROUS_IN_MELEE = {
    "floating eye",  # Paralyzes
    "cockatrice",  # Petrifies
    "chickatrice",  # Petrifies
    "acid blob",  # Acid splash
    "gelatinous cube",  # Engulfs
    "green slime",  # Slimes
}

# Corpses that are dangerous to eat
DANGEROUS_CORPSES = {
    "cockatrice",
    "chickatrice",
    "green slime",
    "acid blob",
    "kobold",
    "kobold lord",
    "kobold shaman",
}

# Corpses that grant intrinsics
BENEFICIAL_CORPSES = {
    "floating eye": ["telepathy"],
    "newt": ["may increase power"],
    "wraith": ["level drain (increases XP)"],
    "fire ant": ["fire resistance (if lucky)"],
    "pyrolisk": ["fire resistance"],
    "red dragon": ["fire resistance"],
    "white dragon": ["cold resistance"],
    "blue dragon": ["shock resistance"],
    "disenchanter": ["disenchant resistance"],
    "stalker": ["invisibility", "see invisible"],
    "yellow light": ["stun resistance"],
    "tengu": ["teleport control", "teleportitis"],
}


def lookup_monster(name: str) -> Optional[MonsterInfo]:
    """
    Look up monster information.

    Args:
        name: Monster name (case insensitive)

    Returns:
        MonsterInfo or None if not found
    """
    return MONSTERS.get(name.lower())


def is_dangerous_melee(monster_name: str) -> bool:
    """Check if a monster is dangerous to attack in melee."""
    return monster_name.lower() in DANGEROUS_IN_MELEE


def is_corpse_safe(monster_name: str) -> bool:
    """Check if a monster's corpse is safe to eat."""
    name = monster_name.lower()
    if name in DANGEROUS_CORPSES:
        return False
    info = lookup_monster(name)
    if info:
        return info.corpse_safe
    return True  # Assume safe if unknown


def get_corpse_effects(monster_name: str) -> list[str]:
    """Get effects of eating a monster's corpse."""
    name = monster_name.lower()
    if name in BENEFICIAL_CORPSES:
        return BENEFICIAL_CORPSES[name]
    info = lookup_monster(name)
    if info:
        return info.corpse_effects
    return []


def estimate_monster_difficulty(monster_name: str) -> int:
    """
    Estimate how difficult a monster is (0-10 scale).

    Args:
        monster_name: Name of monster

    Returns:
        Difficulty rating 0-10
    """
    info = lookup_monster(monster_name)
    if info:
        # Scale 0-30 difficulty to 0-10
        return min(10, info.difficulty // 3)
    return 5  # Unknown = medium difficulty


# Prayer timeout tracking
PRAYER_SAFE_TIMEOUT = 500  # Turns between safe prayers


def is_prayer_safe(last_prayer_turn: int, current_turn: int) -> bool:
    """
    Check if it's safe to pray.

    Args:
        last_prayer_turn: Turn number of last prayer (0 if never prayed)
        current_turn: Current turn number

    Returns:
        True if prayer timeout has passed
    """
    if last_prayer_turn == 0:
        return True
    return (current_turn - last_prayer_turn) >= PRAYER_SAFE_TIMEOUT


# Elbereth effectiveness
def elbereth_effective_against(monster_name: str) -> bool:
    """
    Check if Elbereth scares a monster.

    Most monsters respect Elbereth, but some don't:
    - Blind monsters
    - Elves (they wrote it)
    - Minotaurs
    - Humans
    - Angels
    """
    name = monster_name.lower()
    immune = {
        "minotaur",
        "angel",
        "archon",
        "aleax",
        "ki-rin",
        "couatl",
    }
    # Also elves and humans, but we check by name prefix
    if name in immune:
        return False
    if "elf" in name:
        return False
    if name.startswith("human") or name == "tourist" or name == "wizard":
        return False
    return True
