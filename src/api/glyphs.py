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


# Monster names by ID (common monsters)
# This is a subset - full list would be 381 entries
MONSTER_NAMES = {
    # Ants
    0: "giant ant",
    1: "killer bee",
    2: "soldier ant",
    3: "fire ant",
    4: "giant beetle",
    5: "queen bee",
    # Blobs
    6: "acid blob",
    7: "quivering blob",
    8: "gelatinous cube",
    # Cockatrices
    9: "chickatrice",
    10: "cockatrice",
    11: "pyrolisk",
    # Dogs
    12: "jackal",
    13: "fox",
    14: "coyote",
    15: "werejackal",
    16: "little dog",
    17: "dog",
    18: "large dog",
    19: "dingo",
    20: "wolf",
    21: "werewolf",
    22: "warg",
    23: "winter wolf cub",
    24: "winter wolf",
    25: "hell hound pup",
    26: "hell hound",
    # Eyes
    27: "gas spore",
    28: "floating eye",
    29: "freezing sphere",
    30: "flaming sphere",
    31: "shocking sphere",
    # Felines
    32: "kitten",
    33: "housecat",
    34: "jaguar",
    35: "lynx",
    36: "panther",
    37: "large cat",
    38: "tiger",
    # Gremlins/Gargoyles
    39: "gremlin",
    40: "gargoyle",
    41: "winged gargoyle",
    # Humanoids
    42: "hobbit",
    43: "dwarf",
    44: "bugbear",
    45: "dwarf lord",
    46: "dwarf king",
    47: "mind flayer",
    48: "master mind flayer",
    # Imps
    49: "manes",
    50: "homunculus",
    51: "imp",
    52: "lemure",
    53: "quasit",
    54: "tengu",
    # Jellies
    55: "blue jelly",
    56: "spotted jelly",
    57: "ochre jelly",
    # Kobolds
    58: "kobold",
    59: "large kobold",
    60: "kobold lord",
    61: "kobold shaman",
    # Leprechauns
    62: "leprechaun",
    # Mimics
    63: "small mimic",
    64: "large mimic",
    65: "giant mimic",
    # Nymphs
    66: "wood nymph",
    67: "water nymph",
    68: "mountain nymph",
    # Orcs
    69: "goblin",
    70: "hobgoblin",
    71: "orc",
    72: "hill orc",
    73: "Mordor orc",
    74: "Uruk-hai",
    75: "orc shaman",
    76: "orc-captain",
    # Puddings
    77: "gray ooze",
    78: "brown pudding",
    79: "black pudding",
    80: "green slime",
    # Quantum mechanic
    81: "quantum mechanic",
    # Rodents
    82: "sewer rat",
    83: "giant rat",
    84: "rabid rat",
    85: "wererat",
    86: "rock mole",
    87: "woodchuck",
    # Spiders
    88: "cave spider",
    89: "centipede",
    90: "giant spider",
    91: "scorpion",
    # Trappers
    92: "lurker above",
    93: "trapper",
    # Unicorns
    94: "white unicorn",
    95: "gray unicorn",
    96: "black unicorn",
    97: "pony",
    98: "horse",
    99: "warhorse",
    # Vortices
    100: "fog cloud",
    101: "dust vortex",
    102: "ice vortex",
    103: "energy vortex",
    104: "steam vortex",
    105: "fire vortex",
    # Worms
    106: "baby long worm",
    107: "baby purple worm",
    108: "long worm",
    109: "purple worm",
    # Xan
    110: "grid bug",
    111: "xan",
    # Light
    112: "yellow light",
    113: "black light",
    # Zruty
    114: "zruty",
    # Angelic beings
    115: "couatl",
    116: "Aleax",
    117: "Angel",
    118: "ki-rin",
    119: "Archon",
    # Bats
    120: "bat",
    121: "giant bat",
    122: "raven",
    123: "vampire bat",
    # Centaurs
    124: "plains centaur",
    125: "forest centaur",
    126: "mountain centaur",
    # Dragons
    127: "baby gray dragon",
    128: "baby silver dragon",
    129: "baby red dragon",
    130: "baby white dragon",
    131: "baby orange dragon",
    132: "baby black dragon",
    133: "baby blue dragon",
    134: "baby green dragon",
    135: "baby yellow dragon",
    136: "gray dragon",
    137: "silver dragon",
    138: "red dragon",
    139: "white dragon",
    140: "orange dragon",
    141: "black dragon",
    142: "blue dragon",
    143: "green dragon",
    144: "yellow dragon",
    # Elementals
    145: "stalker",
    146: "air elemental",
    147: "fire elemental",
    148: "earth elemental",
    149: "water elemental",
    # Fungi
    150: "lichen",
    151: "brown mold",
    152: "yellow mold",
    153: "green mold",
    154: "red mold",
    155: "shrieker",
    156: "violet fungus",
    # Gnomes
    157: "gnome",
    158: "gnome lord",
    159: "gnomish wizard",
    160: "gnome king",
    # Giants
    161: "giant",
    162: "stone giant",
    163: "hill giant",
    164: "fire giant",
    165: "frost giant",
    166: "ettin",
    167: "storm giant",
    168: "titan",
    169: "minotaur",
    # Jabberwock
    170: "jabberwock",
    # Kop
    171: "Keystone Kop",
    172: "Kop Sergeant",
    173: "Kop Lieutenant",
    174: "Kop Kaptain",
    # Liches
    175: "lich",
    176: "demilich",
    177: "master lich",
    178: "arch-lich",
    # Mummies
    179: "kobold mummy",
    180: "gnome mummy",
    181: "orc mummy",
    182: "dwarf mummy",
    183: "elf mummy",
    184: "human mummy",
    185: "ettin mummy",
    186: "giant mummy",
    # Nagas
    187: "red naga hatchling",
    188: "black naga hatchling",
    189: "golden naga hatchling",
    190: "guardian naga hatchling",
    191: "red naga",
    192: "black naga",
    193: "golden naga",
    194: "guardian naga",
    # Ogres
    195: "ogre",
    196: "ogre lord",
    197: "ogre king",
    # Piercers
    198: "rock piercer",
    199: "iron piercer",
    200: "glass piercer",
    # Quadrupeds (Q)
    201: "rothe",
    202: "mumak",
    203: "leocrotta",
    204: "wumpus",
    205: "titanothere",
    206: "baluchitherium",
    207: "mastodon",
    # Rust monster/disenchanter (R)
    208: "rust monster",
    209: "disenchanter",
    # Snakes (S)
    210: "garter snake",
    211: "snake",
    212: "water moccasin",
    213: "python",
    214: "pit viper",
    215: "cobra",
    # Trolls (T)
    216: "troll",
    217: "ice troll",
    218: "rock troll",
    219: "water troll",
    220: "Olog-hai",
    # Umber hulk (U)
    221: "umber hulk",
    # Vampires (V)
    222: "vampire",
    223: "vampire lord",
    224: "Vlad the Impaler",
    # Wraiths (W)
    225: "barrow wight",
    226: "wraith",
    227: "nazgul",
    # Xorn (X)
    228: "xorn",
    # Apelike (Y)
    229: "monkey",
    230: "ape",
    231: "owlbear",
    232: "yeti",
    233: "carnivorous ape",
    234: "sasquatch",
    # Zombie (Z)
    235: "kobold zombie",
    236: "gnome zombie",
    237: "orc zombie",
    238: "dwarf zombie",
    239: "elf zombie",
    240: "human zombie",
    241: "ettin zombie",
    242: "giant zombie",
    243: "ghoul",
    244: "skeleton",
    # Golems (')
    245: "straw golem",
    246: "paper golem",
    247: "rope golem",
    248: "gold golem",
    249: "leather golem",
    250: "wood golem",
    251: "flesh golem",
    252: "clay golem",
    253: "stone golem",
    254: "glass golem",
    255: "iron golem",
    # Humans (@)
    256: "human",
    257: "wererat",  # @ form
    258: "werejackal",  # @ form
    259: "werewolf",  # @ form
    260: "elf",
    261: "Woodland-elf",
    262: "Green-elf",
    263: "Grey-elf",
    264: "elf-lord",
    265: "Elvenking",
    266: "doppelganger",
    267: "nurse",
    268: "shopkeeper",
    269: "guard",
    270: "prisoner",
    271: "Oracle",
    272: "aligned priest",
    273: "high priest",
    274: "soldier",
    275: "sergeant",
    276: "lieutenant",
    277: "captain",
    278: "watchman",
    279: "watch captain",
    280: "Medusa",
    281: "Wizard of Yendor",
    282: "Croesus",
    # Ghosts (&)
    283: "ghost",
    284: "shade",
    # Demons (&)
    285: "water demon",
    286: "horned devil",
    287: "succubus",
    288: "incubus",
    289: "erinys",
    290: "barbed devil",
    291: "marilith",
    292: "vrock",
    293: "hezrou",
    294: "bone devil",
    295: "ice devil",
    296: "nalfeshnee",
    297: "pit fiend",
    298: "sandestin",
    299: "balrog",
    300: "Juiblex",
    301: "Yeenoghu",
    302: "Orcus",
    303: "Geryon",
    304: "Dispater",
    305: "Baalzebub",
    306: "Asmodeus",
    307: "Demogorgon",
    308: "Death",
    309: "Pestilence",
    310: "Famine",
    # Sea monsters (;)
    311: "jellyfish",
    312: "piranha",
    313: "shark",
    314: "giant eel",
    315: "electric eel",
    316: "kraken",
    # Lizards (:) - confirmed: monster 318 = newt from game log
    318: "newt",
    319: "gecko",
    320: "iguana",
    321: "baby crocodile",
    322: "lizard",
    323: "chameleon",
    324: "crocodile",
    325: "salamander",
    326: "komodo dragon",
    # Player types (various)
    327: "archeologist",
    328: "barbarian",
    329: "caveman",
    330: "cavewoman",
    331: "healer",
    332: "knight",
    333: "monk",
    334: "priest",
    335: "priestess",
    336: "ranger",
    337: "rogue",
    338: "samurai",
    339: "tourist",
    340: "valkyrie",
    341: "wizard",
}

# Cmap (dungeon feature) names
CMAP_NAMES = {
    0: "stone",
    1: "vertical wall",
    2: "horizontal wall",
    3: "top-left corner",
    4: "top-right corner",
    5: "bottom-left corner",
    6: "bottom-right corner",
    7: "cross wall",
    8: "upward T wall",
    9: "downward T wall",
    10: "leftward T wall",
    11: "rightward T wall",
    12: "floor",
    13: "dark floor",
    14: "corridor",
    15: "closed door",
    16: "open door",
    17: "broken door",  # Might be iron bars
    18: "iron bars",
    19: "tree/room floor",  # Context dependent
    20: "stairs up",
    21: "stairs down",
    22: "ladder up",
    23: "ladder down",
    24: "altar",
    25: "grave",
    26: "throne",
    27: "sink",
    28: "fountain",
    29: "pool",
    30: "corridor",  # Lit corridor
    31: "air",
    32: "cloud",
    33: "water",
    34: "arrow trap",
    35: "dart trap",
    36: "falling rock trap",
    37: "squeaky board",
    38: "bear trap",
    39: "land mine",
    40: "rolling boulder trap",
    41: "sleeping gas trap",
    42: "rust trap",
    43: "fire trap",
    44: "pit",
    45: "spiked pit",
    46: "hole",
    47: "trap door",
    48: "teleport trap",
    49: "level teleporter",
    50: "magic portal",
    51: "web",
    52: "statue trap",
    53: "magic trap",
    54: "anti-magic trap",
    55: "polymorph trap",
}

# Walkable cmap IDs
WALKABLE_CMAP = {
    12,  # floor
    13,  # dark floor
    14,  # corridor
    # 15 = closed door - NOT walkable until opened
    16,  # open door
    17,  # broken door - walkable (kicked/destroyed door)
    19,  # room floor/tree
    20,  # stairs up
    21,  # stairs down
    22,  # ladder up
    23,  # ladder down
    24,  # altar
    25,  # grave
    26,  # throne
    27,  # sink
    28,  # fountain
    30,  # lit corridor
}

# Dangerous terrain CMAP IDs (water/lava - deadly for grounded players)
# Note: These IDs are from NLE/MiniHack testing and may differ from vanilla NetHack
CMAP_POOL = 29        # Pool/moat (standard)
CMAP_WATER = 33       # Water (standard)
CMAP_LAVA = 34        # Lava (NLE/MiniHack uses this for lava)
CMAP_MOAT = 41        # Moat/deep water (NLE/MiniHack River environment)
DANGEROUS_TERRAIN_CMAP = {CMAP_POOL, CMAP_WATER, CMAP_LAVA, CMAP_MOAT}


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
        # Player glyph is also "monster"
        is_player = char == "@" and mon_id >= 318  # Player monster types
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
        return GlyphInfo(
            glyph=glyph,
            glyph_type=GlyphType.STATUE,
            char=char,
            name=f"{name} statue",
            monster_id=mon_id,
            is_walkable=False,
        )

    if nethack.glyph_is_ridden_monster(glyph):
        mon_id = nethack.glyph_to_mon(glyph)
        name = MONSTER_NAMES.get(mon_id, f"monster {mon_id}")
        return GlyphInfo(
            glyph=glyph,
            glyph_type=GlyphType.RIDDEN,
            char=char,
            name=f"ridden {name}",
            monster_id=mon_id,
            is_walkable=False,
            is_tame=True,
        )

    if nethack.glyph_is_object(glyph):
        obj_id = nethack.glyph_to_obj(glyph)
        # TODO: Look up object name from NLE data
        name = f"object {obj_id}"
        if char == "$":
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
        elif char == "0" or obj_id == 1:  # Boulder (obj_id 1, char '0')
            name = "boulder"
        # Boulders block movement (obj_id 1 is boulder)
        walkable = obj_id != 1
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
        name = CMAP_NAMES.get(cmap_id, f"terrain {cmap_id}")
        is_walkable = cmap_id in WALKABLE_CMAP
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
        name = CMAP_NAMES.get(34 + trap_id, f"trap {trap_id}")
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
    info = parse_glyph(glyph)
    return info.is_walkable


def is_closed_door_glyph(glyph: int) -> bool:
    """Check if glyph is a closed door (cmap_id 15)."""
    if not nethack.glyph_is_cmap(glyph):
        return False
    cmap_id = nethack.glyph_to_cmap(glyph)
    return cmap_id == 15


def is_dangerous_terrain_glyph(glyph: int, can_fly: bool = False) -> bool:
    """
    Check if glyph is dangerous terrain (water/lava) for grounded players.

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
    return cmap_id in DANGEROUS_TERRAIN_CMAP


def is_boulder_glyph(glyph: int) -> bool:
    """Check if glyph represents a boulder."""
    if not nethack.glyph_is_object(glyph):
        return False
    # Boulder is object class ROCK (14) and typically char '0'
    # We check by object ID - boulder is usually one of the first rock objects
    obj_id = nethack.glyph_to_obj(glyph)
    # Boulder object ID is 1 in the objects array (after strange object 0)
    return obj_id == 1
