"""
Data models for the NetHack API.

These dataclasses represent game entities and state in a structured,
type-safe way that's easy for both skills and the LLM to work with.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional


class HungerState(Enum):
    """Player hunger levels."""

    SATIATED = "Satiated"
    NOT_HUNGRY = "Not Hungry"
    HUNGRY = "Hungry"
    WEAK = "Weak"
    FAINTING = "Fainting"
    FAINTED = "Fainted"

    @classmethod
    def from_blstats(cls, value: int) -> "HungerState":
        """Convert blstats hunger value to HungerState."""
        # NLE hunger values: 0=Satiated, 1=Not Hungry, 2=Hungry, 3=Weak, 4=Fainting, 5=Fainted
        mapping = {
            0: cls.SATIATED,
            1: cls.NOT_HUNGRY,
            2: cls.HUNGRY,
            3: cls.WEAK,
            4: cls.FAINTING,
            5: cls.FAINTED,
        }
        return mapping.get(value, cls.NOT_HUNGRY)


class Alignment(Enum):
    """Player alignment."""

    LAWFUL = "Lawful"
    NEUTRAL = "Neutral"
    CHAOTIC = "Chaotic"

    @classmethod
    def from_blstats(cls, value: int) -> "Alignment":
        """Convert blstats alignment value."""
        # NLE: negative=Chaotic, 0=Neutral, positive=Lawful
        if value < 0:
            return cls.CHAOTIC
        elif value > 0:
            return cls.LAWFUL
        return cls.NEUTRAL


class Encumbrance(Enum):
    """Carrying capacity status."""

    UNENCUMBERED = "Unencumbered"
    BURDENED = "Burdened"
    STRESSED = "Stressed"
    STRAINED = "Strained"
    OVERTAXED = "Overtaxed"
    OVERLOADED = "Overloaded"

    @classmethod
    def from_blstats(cls, value: int) -> "Encumbrance":
        """Convert blstats encumbrance value."""
        mapping = {
            0: cls.UNENCUMBERED,
            1: cls.BURDENED,
            2: cls.STRESSED,
            3: cls.STRAINED,
            4: cls.OVERTAXED,
            5: cls.OVERLOADED,
        }
        return mapping.get(value, cls.UNENCUMBERED)


class ObjectClass(Enum):
    """NetHack object classes."""

    RANDOM = "random"
    ILLOBJ = "illobj"
    WEAPON = "weapon"
    ARMOR = "armor"
    RING = "ring"
    AMULET = "amulet"
    TOOL = "tool"
    FOOD = "food"
    POTION = "potion"
    SCROLL = "scroll"
    SPELLBOOK = "spellbook"
    WAND = "wand"
    COIN = "coin"
    GEM = "gem"
    ROCK = "rock"
    BALL = "ball"
    CHAIN = "chain"
    VENOM = "venom"

    @classmethod
    def from_oclass(cls, value: int) -> "ObjectClass":
        """Convert NLE object class integer to ObjectClass."""
        # NLE object class values
        mapping = {
            0: cls.RANDOM,
            1: cls.ILLOBJ,
            2: cls.WEAPON,
            3: cls.ARMOR,
            4: cls.RING,
            5: cls.AMULET,
            6: cls.TOOL,
            7: cls.FOOD,
            8: cls.POTION,
            9: cls.SCROLL,
            10: cls.SPELLBOOK,
            11: cls.WAND,
            12: cls.COIN,
            13: cls.GEM,
            14: cls.ROCK,
            15: cls.BALL,
            16: cls.CHAIN,
            17: cls.VENOM,
        }
        return mapping.get(value, cls.ILLOBJ)


class BUCStatus(Enum):
    """Blessed/Uncursed/Cursed status."""

    BLESSED = "blessed"
    UNCURSED = "uncursed"
    CURSED = "cursed"
    UNKNOWN = "unknown"


class Direction(Enum):
    """Movement/action directions."""

    N = "n"
    S = "s"
    E = "e"
    W = "w"
    NE = "ne"
    NW = "nw"
    SE = "se"
    SW = "sw"
    UP = "up"
    DOWN = "down"
    SELF = "self"

    @property
    def delta(self) -> tuple[int, int]:
        """Get (dx, dy) for this direction."""
        deltas = {
            Direction.N: (0, -1),
            Direction.S: (0, 1),
            Direction.E: (1, 0),
            Direction.W: (-1, 0),
            Direction.NE: (1, -1),
            Direction.NW: (-1, -1),
            Direction.SE: (1, 1),
            Direction.SW: (-1, 1),
            Direction.UP: (0, 0),
            Direction.DOWN: (0, 0),
            Direction.SELF: (0, 0),
        }
        return deltas[self]


# Direction constants for iteration
CARDINAL_DIRECTIONS = (Direction.N, Direction.S, Direction.E, Direction.W)
DIAGONAL_DIRECTIONS = (Direction.NE, Direction.NW, Direction.SE, Direction.SW)
ALL_DIRECTIONS = CARDINAL_DIRECTIONS + DIAGONAL_DIRECTIONS


@dataclass(frozen=True, order=True)
class Position:
    """A position on the map."""

    x: int
    y: int

    def distance_to(self, other: "Position") -> int:
        """Manhattan distance to another position."""
        return abs(self.x - other.x) + abs(self.y - other.y)

    def chebyshev_distance(self, other: "Position") -> int:
        """Chebyshev (diagonal) distance - number of king moves."""
        return max(abs(self.x - other.x), abs(self.y - other.y))

    def direction_to(self, other: "Position") -> Optional[Direction]:
        """Get the compass direction toward another position."""
        dx = other.x - self.x
        dy = other.y - self.y

        if dx == 0 and dy == 0:
            return Direction.SELF

        # Normalize to -1, 0, 1
        dx = 0 if dx == 0 else (1 if dx > 0 else -1)
        dy = 0 if dy == 0 else (1 if dy > 0 else -1)

        direction_map = {
            (0, -1): Direction.N,
            (0, 1): Direction.S,
            (1, 0): Direction.E,
            (-1, 0): Direction.W,
            (1, -1): Direction.NE,
            (-1, -1): Direction.NW,
            (1, 1): Direction.SE,
            (-1, 1): Direction.SW,
        }
        return direction_map.get((dx, dy))

    def adjacent(self) -> list["Position"]:
        """Get all 8 adjacent positions."""
        return [
            Position(self.x + dx, self.y + dy)
            for dx in [-1, 0, 1]
            for dy in [-1, 0, 1]
            if not (dx == 0 and dy == 0)
        ]

    def move(self, direction: Direction) -> "Position":
        """Get position after moving in a direction."""
        dx, dy = direction.delta
        return Position(self.x + dx, self.y + dy)

    def __add__(self, other: tuple[int, int]) -> "Position":
        """Add a delta tuple to position."""
        return Position(self.x + other[0], self.y + other[1])


@dataclass
class Stats:
    """Player statistics parsed from blstats."""

    hp: int
    max_hp: int
    pw: int  # Power (mana)
    max_pw: int
    ac: int  # Armor class (lower is better)
    xp_level: int
    xp_points: int
    gold: int
    strength: int
    dexterity: int
    constitution: int
    intelligence: int
    wisdom: int
    charisma: int
    hunger: HungerState
    encumbrance: Encumbrance
    alignment: Alignment
    dungeon_level: int
    dungeon_number: int  # Which branch
    turn: int
    score: int
    position: Position

    @property
    def hp_fraction(self) -> float:
        """HP as fraction of max (0.0 to 1.0)."""
        return self.hp / self.max_hp if self.max_hp > 0 else 0.0

    @property
    def pw_fraction(self) -> float:
        """Power as fraction of max."""
        return self.pw / self.max_pw if self.max_pw > 0 else 0.0

    @property
    def is_weak(self) -> bool:
        """Check if player is weak from hunger."""
        return self.hunger in [HungerState.WEAK, HungerState.FAINTING, HungerState.FAINTED]

    @property
    def is_hungry(self) -> bool:
        """Check if player needs food soon."""
        return self.hunger in [
            HungerState.HUNGRY,
            HungerState.WEAK,
            HungerState.FAINTING,
            HungerState.FAINTED,
        ]


@dataclass
class Monster:
    """A monster on the map."""

    glyph: int
    char: str
    name: str
    position: Position
    color: int = 0
    is_peaceful: bool = False
    is_tame: bool = False
    threat_level: int = 0  # Estimated difficulty

    @property
    def is_hostile(self) -> bool:
        """Check if monster is hostile."""
        return not self.is_peaceful and not self.is_tame


@dataclass
class Item:
    """An item (on ground or in inventory)."""

    glyph: int
    name: str
    char: str = "?"
    position: Optional[Position] = None  # None if in inventory
    slot: Optional[str] = None  # Inventory letter (a-zA-Z)
    quantity: int = 1
    buc_status: BUCStatus = BUCStatus.UNKNOWN
    identified: bool = False
    object_class: ObjectClass = ObjectClass.ILLOBJ
    equipped: bool = False

    @property
    def is_weapon(self) -> bool:
        return self.object_class == ObjectClass.WEAPON

    @property
    def is_armor(self) -> bool:
        return self.object_class == ObjectClass.ARMOR

    @property
    def is_food(self) -> bool:
        return self.object_class == ObjectClass.FOOD

    @property
    def is_potion(self) -> bool:
        return self.object_class == ObjectClass.POTION

    @property
    def is_scroll(self) -> bool:
        return self.object_class == ObjectClass.SCROLL

    @property
    def is_wand(self) -> bool:
        return self.object_class == ObjectClass.WAND


@dataclass
class Tile:
    """A single map tile."""

    char: str
    glyph: int
    position: Position
    color: int = 0
    description: str = ""
    is_walkable: bool = True
    is_explored: bool = False
    has_trap: bool = False
    trap_type: Optional[str] = None
    feature: Optional[str] = None  # "door", "altar", "fountain", etc.

    @property
    def is_wall(self) -> bool:
        return self.char in ["-", "|", "+"]

    @property
    def is_door(self) -> bool:
        return self.char in ["+", "-"] and self.feature == "door"

    @property
    def is_stairs_up(self) -> bool:
        return self.char == "<"

    @property
    def is_stairs_down(self) -> bool:
        return self.char == ">"

    @property
    def is_stairs(self) -> bool:
        return self.is_stairs_up or self.is_stairs_down

    @property
    def is_corridor(self) -> bool:
        return self.char == "#"

    @property
    def is_floor(self) -> bool:
        return self.char == "."


@dataclass
class DungeonLevel:
    """Parsed representation of a dungeon level."""

    level_number: int
    dungeon_number: int
    branch: str = "Dungeons of Doom"
    tiles: list[list[Tile]] = field(default_factory=list)
    explored_tiles: int = 0
    total_walkable: int = 0

    @property
    def explored_percentage(self) -> float:
        """Percentage of walkable tiles explored."""
        if self.total_walkable == 0:
            return 0.0
        return self.explored_tiles / self.total_walkable

    def get_tile(self, pos: Position) -> Optional[Tile]:
        """Get tile at position, or None if out of bounds."""
        if 0 <= pos.y < len(self.tiles) and 0 <= pos.x < len(self.tiles[0]):
            return self.tiles[pos.y][pos.x]
        return None


@dataclass
class ActionResult:
    """Result of executing a game action."""

    success: bool
    messages: list[str] = field(default_factory=list)
    turn_elapsed: bool = True
    state_changed: bool = True
    error: Optional[str] = None

    @classmethod
    def failure(cls, error: str) -> "ActionResult":
        """Create a failure result."""
        return cls(success=False, error=error, turn_elapsed=False, state_changed=False)

    @classmethod
    def ok(cls, messages: Optional[list[str]] = None) -> "ActionResult":
        """Create a success result."""
        return cls(success=True, messages=messages or [])


@dataclass
class SkillResult:
    """Result returned by a skill execution."""

    stopped_reason: str  # Why the skill terminated
    data: dict[str, Any] = field(default_factory=dict)  # Relevant data
    actions_taken: int = 0  # Number of game actions executed
    turns_elapsed: int = 0  # Number of game turns elapsed
    success: bool = False  # Whether the skill achieved its goal

    @classmethod
    def stopped(
        cls,
        reason: str,
        success: bool = False,
        actions: int = 0,
        turns: int = 0,
        **data: Any,
    ) -> "SkillResult":
        """Create a skill result."""
        return cls(
            stopped_reason=reason,
            success=success,
            actions_taken=actions,
            turns_elapsed=turns,
            data=data,
        )


@dataclass
class AutoexploreResult:
    """Result of autoexplore operation."""

    stop_reason: str  # Why exploration stopped
    steps_taken: int  # Number of movement steps
    turns_elapsed: int  # Number of game turns
    position: "Position"  # Final position
    message: str = ""  # Human-readable explanation

    @property
    def success(self) -> bool:
        """Whether exploration completed successfully."""
        return self.stop_reason in ("fully_explored", "feature", "stairs")

    @property
    def needs_attention(self) -> bool:
        """Whether the stop reason requires player attention."""
        return self.stop_reason in ("hostile", "low_hp", "hungry", "trap", "item", "blocked")


# Action key mappings for NLE
# These map direction strings to NLE action indices
DIRECTION_KEYS = {
    Direction.N: ord("k"),
    Direction.S: ord("j"),
    Direction.E: ord("l"),
    Direction.W: ord("h"),
    Direction.NE: ord("u"),
    Direction.NW: ord("y"),
    Direction.SE: ord("n"),
    Direction.SW: ord("b"),
    Direction.UP: ord("<"),
    Direction.DOWN: ord(">"),
    Direction.SELF: ord("."),
}

# Common NetHack commands
COMMANDS = {
    "search": ord("s"),
    "wait": ord("."),
    "pickup": ord(","),
    "drop": ord("d"),
    "eat": ord("e"),
    "quaff": ord("q"),
    "read": ord("r"),
    "zap": ord("z"),
    "wear": ord("W"),
    "wield": ord("w"),
    "take_off": ord("T"),
    "remove": ord("R"),
    "throw": ord("t"),
    "fire": ord("f"),
    "apply": ord("a"),
    "open": ord("o"),
    "close": ord("c"),
    "kick": ord("D"),  # ctrl+d
    "force": ord("F"),  # force lock
    "inventory": ord("i"),
    "look": ord(":"),
    "pray": ord("p"),
    "cast": ord("Z"),
    "engrave": ord("E"),
    "pay": ord("p"),
    "enhance": ord("#"),
    "escape": 27,  # ESC key
    "space": ord(" "),
    "yes": ord("y"),
    "no": ord("n"),
}
