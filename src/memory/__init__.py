"""Memory and persistence layer for game state and cross-episode learning."""

from .manager import MemoryManager
from .working import (
    EntitySighting,
    PendingGoal,
    TurnSnapshot,
    WorkingMemory,
)
from .dungeon import (
    DungeonMemory,
    LevelFeature,
    LevelMemory,
    TileMemory,
    TileType,
)
from .episode import (
    EpisodeEvent,
    EpisodeMemory,
    EpisodeStatistics,
)

__all__ = [
    # Manager
    "MemoryManager",
    # Working Memory
    "EntitySighting",
    "PendingGoal",
    "TurnSnapshot",
    "WorkingMemory",
    # Dungeon Memory
    "DungeonMemory",
    "LevelFeature",
    "LevelMemory",
    "TileMemory",
    "TileType",
    # Episode Memory
    "EpisodeEvent",
    "EpisodeMemory",
    "EpisodeStatistics",
]
