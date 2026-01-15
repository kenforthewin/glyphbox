"""
Memory manager for database operations.

Handles database connection, initialization, migrations,
and provides CRUD operations for all memory tables.
"""

import json
import logging
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)

# Default database path
DEFAULT_DB_PATH = "data/memory.db"

# Path to schema file
SCHEMA_PATH = Path(__file__).parent / "schema.sql"


class MemoryManager:
    """
    Manages the memory database.

    Provides connection management, initialization, and
    CRUD operations for game memory persistence.

    Example usage:
        manager = MemoryManager("data/memory.db")
        manager.initialize()

        # Create episode
        manager.create_episode("ep_001")

        # Record events
        manager.record_event("ep_001", 100, "levelup", "Reached level 2")

        # Query data
        events = manager.get_events("ep_001", event_type="levelup")

        manager.close()
    """

    def __init__(self, db_path: Optional[str] = None):
        """
        Initialize the memory manager.

        Args:
            db_path: Path to SQLite database (uses default if not specified)
        """
        self.db_path = Path(db_path) if db_path else Path(DEFAULT_DB_PATH)
        self._conn: Optional[sqlite3.Connection] = None

    def initialize(self) -> None:
        """Initialize the database and create tables."""
        # Create directory if needed
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

        # Connect and create tables
        self._conn = sqlite3.connect(str(self.db_path))
        self._conn.row_factory = sqlite3.Row

        # Load and execute schema
        if SCHEMA_PATH.exists():
            schema = SCHEMA_PATH.read_text()
            self._conn.executescript(schema)
        else:
            logger.warning(f"Schema file not found: {SCHEMA_PATH}")

        self._conn.commit()
        logger.info(f"Memory database initialized at {self.db_path}")

    def _ensure_connected(self) -> None:
        """Ensure database is connected."""
        if self._conn is None:
            self.initialize()

    # ==================== Episode Operations ====================

    def create_episode(self, episode_id: str, metadata: Optional[dict] = None) -> int:
        """
        Create a new episode record.

        Args:
            episode_id: Unique episode identifier
            metadata: Optional metadata dictionary

        Returns:
            Row ID of created episode
        """
        self._ensure_connected()

        cursor = self._conn.execute(
            """
            INSERT INTO episodes (episode_id, started_at, metadata)
            VALUES (?, ?, ?)
            """,
            (
                episode_id,
                datetime.now().isoformat(),
                json.dumps(metadata) if metadata else None,
            ),
        )
        self._conn.commit()
        return cursor.lastrowid

    def end_episode(
        self,
        episode_id: str,
        end_reason: str,
        final_score: int = 0,
        final_turns: int = 0,
        final_depth: int = 0,
        final_xp_level: int = 0,
        death_reason: Optional[str] = None,
        skills_used: int = 0,
        skills_created: int = 0,
    ) -> None:
        """
        Mark an episode as ended.

        Args:
            episode_id: Episode identifier
            end_reason: How episode ended ('death', 'ascension', 'quit', 'timeout')
            final_score: Final game score
            final_turns: Total turns played
            final_depth: Deepest dungeon level reached
            final_xp_level: Final experience level
            death_reason: Death message if applicable
            skills_used: Number of skills executed
            skills_created: Number of new skills created
        """
        self._ensure_connected()

        self._conn.execute(
            """
            UPDATE episodes SET
                ended_at = ?,
                end_reason = ?,
                final_score = ?,
                final_turns = ?,
                final_depth = ?,
                final_xp_level = ?,
                death_reason = ?,
                skills_used = ?,
                skills_created = ?
            WHERE episode_id = ?
            """,
            (
                datetime.now().isoformat(),
                end_reason,
                final_score,
                final_turns,
                final_depth,
                final_xp_level,
                death_reason,
                skills_used,
                skills_created,
                episode_id,
            ),
        )
        self._conn.commit()

    def get_episode(self, episode_id: str) -> Optional[dict]:
        """Get episode by ID."""
        self._ensure_connected()

        row = self._conn.execute(
            "SELECT * FROM episodes WHERE episode_id = ?",
            (episode_id,),
        ).fetchone()

        if row:
            return dict(row)
        return None

    def get_recent_episodes(self, limit: int = 10) -> list[dict]:
        """Get most recent episodes."""
        self._ensure_connected()

        rows = self._conn.execute(
            "SELECT * FROM episodes ORDER BY started_at DESC LIMIT ?",
            (limit,),
        ).fetchall()

        return [dict(row) for row in rows]

    # ==================== Dungeon Level Operations ====================

    def save_level(
        self,
        episode_id: str,
        level_number: int,
        branch: str = "main",
        **kwargs,
    ) -> int:
        """
        Save or update dungeon level data.

        Args:
            episode_id: Episode identifier
            level_number: Dungeon level number
            branch: Dungeon branch name
            **kwargs: Additional level data (tiles_explored, has_altar, etc.)

        Returns:
            Row ID
        """
        self._ensure_connected()

        # Check if level exists
        existing = self._conn.execute(
            """
            SELECT id FROM dungeon_levels
            WHERE episode_id = ? AND level_number = ? AND branch = ?
            """,
            (episode_id, level_number, branch),
        ).fetchone()

        if existing:
            # Update existing
            set_clauses = ["updated_at = ?"]
            values = [datetime.now().isoformat()]

            for key, value in kwargs.items():
                if key in (
                    "tiles_explored", "total_tiles", "upstairs_x", "upstairs_y",
                    "downstairs_x", "downstairs_y", "has_altar", "altar_alignment",
                    "has_shop", "shop_type", "has_fountain", "has_sink",
                    "tile_data", "features", "metadata", "first_visited_turn",
                    "last_visited_turn",
                ):
                    set_clauses.append(f"{key} = ?")
                    if key in ("features", "metadata") and isinstance(value, dict):
                        values.append(json.dumps(value))
                    else:
                        values.append(value)

            values.extend([episode_id, level_number, branch])
            self._conn.execute(
                f"""
                UPDATE dungeon_levels SET {', '.join(set_clauses)}
                WHERE episode_id = ? AND level_number = ? AND branch = ?
                """,
                values,
            )
            self._conn.commit()
            return existing["id"]
        else:
            # Insert new
            columns = ["episode_id", "level_number", "branch"]
            values = [episode_id, level_number, branch]

            for key, value in kwargs.items():
                if key in (
                    "tiles_explored", "total_tiles", "upstairs_x", "upstairs_y",
                    "downstairs_x", "downstairs_y", "has_altar", "altar_alignment",
                    "has_shop", "shop_type", "has_fountain", "has_sink",
                    "tile_data", "features", "metadata", "first_visited_turn",
                    "last_visited_turn",
                ):
                    columns.append(key)
                    if key in ("features", "metadata") and isinstance(value, dict):
                        values.append(json.dumps(value))
                    else:
                        values.append(value)

            placeholders = ", ".join(["?"] * len(values))
            cursor = self._conn.execute(
                f"""
                INSERT INTO dungeon_levels ({', '.join(columns)})
                VALUES ({placeholders})
                """,
                values,
            )
            self._conn.commit()
            return cursor.lastrowid

    def get_level(
        self,
        episode_id: str,
        level_number: int,
        branch: str = "main",
    ) -> Optional[dict]:
        """Get dungeon level data."""
        self._ensure_connected()

        row = self._conn.execute(
            """
            SELECT * FROM dungeon_levels
            WHERE episode_id = ? AND level_number = ? AND branch = ?
            """,
            (episode_id, level_number, branch),
        ).fetchone()

        if row:
            result = dict(row)
            # Parse JSON fields
            if result.get("features"):
                result["features"] = json.loads(result["features"])
            if result.get("metadata"):
                result["metadata"] = json.loads(result["metadata"])
            return result
        return None

    def get_all_levels(self, episode_id: str) -> list[dict]:
        """Get all dungeon levels for an episode."""
        self._ensure_connected()

        rows = self._conn.execute(
            """
            SELECT * FROM dungeon_levels
            WHERE episode_id = ?
            ORDER BY branch, level_number
            """,
            (episode_id,),
        ).fetchall()

        results = []
        for row in rows:
            result = dict(row)
            if result.get("features"):
                result["features"] = json.loads(result["features"])
            if result.get("metadata"):
                result["metadata"] = json.loads(result["metadata"])
            results.append(result)
        return results

    # ==================== Stash Operations ====================

    def save_stash(
        self,
        episode_id: str,
        level_number: int,
        position_x: int,
        position_y: int,
        items: list[str],
        branch: str = "main",
        turn_discovered: Optional[int] = None,
    ) -> int:
        """Save or update a stash location."""
        self._ensure_connected()

        # Check if stash exists at this location
        existing = self._conn.execute(
            """
            SELECT id FROM stashes
            WHERE episode_id = ? AND level_number = ? AND branch = ?
                  AND position_x = ? AND position_y = ?
            """,
            (episode_id, level_number, branch, position_x, position_y),
        ).fetchone()

        if existing:
            self._conn.execute(
                """
                UPDATE stashes SET items = ?, turn_last_seen = ?, still_exists = 1
                WHERE id = ?
                """,
                (json.dumps(items), turn_discovered, existing["id"]),
            )
            self._conn.commit()
            return existing["id"]
        else:
            cursor = self._conn.execute(
                """
                INSERT INTO stashes (
                    episode_id, level_number, branch, position_x, position_y,
                    items, turn_discovered, turn_last_seen
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    episode_id, level_number, branch, position_x, position_y,
                    json.dumps(items), turn_discovered, turn_discovered,
                ),
            )
            self._conn.commit()
            return cursor.lastrowid

    def get_stashes(
        self,
        episode_id: str,
        level_number: Optional[int] = None,
        branch: str = "main",
    ) -> list[dict]:
        """Get stashes for an episode, optionally filtered by level."""
        self._ensure_connected()

        if level_number is not None:
            rows = self._conn.execute(
                """
                SELECT * FROM stashes
                WHERE episode_id = ? AND level_number = ? AND branch = ? AND still_exists = 1
                """,
                (episode_id, level_number, branch),
            ).fetchall()
        else:
            rows = self._conn.execute(
                """
                SELECT * FROM stashes
                WHERE episode_id = ? AND still_exists = 1
                """,
                (episode_id,),
            ).fetchall()

        results = []
        for row in rows:
            result = dict(row)
            result["items"] = json.loads(result["items"])
            results.append(result)
        return results

    # ==================== Item Discovery Operations ====================

    def record_item_discovery(
        self,
        episode_id: str,
        appearance: str,
        object_class: str,
        true_identity: Optional[str] = None,
        buc_status: Optional[str] = None,
        turn_discovered: Optional[int] = None,
        discovery_method: Optional[str] = None,
    ) -> int:
        """Record an item identification."""
        self._ensure_connected()

        # Use INSERT OR REPLACE to update if exists
        cursor = self._conn.execute(
            """
            INSERT OR REPLACE INTO discovered_items (
                episode_id, appearance, object_class, true_identity,
                buc_status, turn_discovered, discovery_method
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                episode_id, appearance, object_class, true_identity,
                buc_status, turn_discovered, discovery_method,
            ),
        )
        self._conn.commit()
        return cursor.lastrowid

    def get_item_identity(
        self,
        episode_id: str,
        appearance: str,
        object_class: str,
    ) -> Optional[dict]:
        """Get the identified name for an item appearance."""
        self._ensure_connected()

        row = self._conn.execute(
            """
            SELECT * FROM discovered_items
            WHERE episode_id = ? AND appearance = ? AND object_class = ?
            """,
            (episode_id, appearance, object_class),
        ).fetchone()

        return dict(row) if row else None

    def get_all_discoveries(self, episode_id: str) -> list[dict]:
        """Get all item discoveries for an episode."""
        self._ensure_connected()

        rows = self._conn.execute(
            "SELECT * FROM discovered_items WHERE episode_id = ?",
            (episode_id,),
        ).fetchall()

        return [dict(row) for row in rows]

    # ==================== Event Operations ====================

    def record_event(
        self,
        episode_id: str,
        turn: int,
        event_type: str,
        description: Optional[str] = None,
        level_number: Optional[int] = None,
        branch: Optional[str] = None,
        position_x: Optional[int] = None,
        position_y: Optional[int] = None,
        data: Optional[dict] = None,
    ) -> int:
        """Record a significant game event."""
        self._ensure_connected()

        cursor = self._conn.execute(
            """
            INSERT INTO events (
                episode_id, turn, event_type, description,
                level_number, branch, position_x, position_y, data
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                episode_id, turn, event_type, description,
                level_number, branch, position_x, position_y,
                json.dumps(data) if data else None,
            ),
        )
        self._conn.commit()
        return cursor.lastrowid

    def get_events(
        self,
        episode_id: str,
        event_type: Optional[str] = None,
        limit: int = 100,
    ) -> list[dict]:
        """Get events for an episode."""
        self._ensure_connected()

        if event_type:
            rows = self._conn.execute(
                """
                SELECT * FROM events
                WHERE episode_id = ? AND event_type = ?
                ORDER BY turn DESC LIMIT ?
                """,
                (episode_id, event_type, limit),
            ).fetchall()
        else:
            rows = self._conn.execute(
                """
                SELECT * FROM events
                WHERE episode_id = ?
                ORDER BY turn DESC LIMIT ?
                """,
                (episode_id, limit),
            ).fetchall()

        results = []
        for row in rows:
            result = dict(row)
            if result.get("data"):
                result["data"] = json.loads(result["data"])
            results.append(result)
        return results

    # ==================== Monster Encounter Operations ====================

    def record_monster_encounter(
        self,
        episode_id: str,
        monster_name: str,
        level_number: Optional[int] = None,
        branch: Optional[str] = None,
        position_x: Optional[int] = None,
        position_y: Optional[int] = None,
        turn_seen: Optional[int] = None,
    ) -> int:
        """Record a monster encounter."""
        self._ensure_connected()

        cursor = self._conn.execute(
            """
            INSERT INTO monster_encounters (
                episode_id, monster_name, level_number, branch,
                position_x, position_y, turn_seen
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                episode_id, monster_name, level_number, branch,
                position_x, position_y, turn_seen,
            ),
        )
        self._conn.commit()
        return cursor.lastrowid

    def update_monster_outcome(
        self,
        encounter_id: int,
        outcome: str,
        damage_dealt: int = 0,
        damage_taken: int = 0,
    ) -> None:
        """Update the outcome of a monster encounter."""
        self._ensure_connected()

        self._conn.execute(
            """
            UPDATE monster_encounters SET
                outcome = ?, damage_dealt = ?, damage_taken = ?
            WHERE id = ?
            """,
            (outcome, damage_dealt, damage_taken, encounter_id),
        )
        self._conn.commit()

    # ==================== Cross-Episode Knowledge Operations ====================

    def update_monster_knowledge(
        self,
        monster_name: str,
        killed: bool = False,
        caused_death: bool = False,
        damage_dealt: int = 0,
        damage_taken: int = 0,
    ) -> None:
        """Update cross-episode monster knowledge."""
        self._ensure_connected()

        # Get existing knowledge
        row = self._conn.execute(
            "SELECT * FROM monster_knowledge WHERE monster_name = ?",
            (monster_name,),
        ).fetchone()

        if row:
            # Update existing
            encounters = row["encounters"] + 1
            kills = row["kills"] + (1 if killed else 0)
            deaths = row["deaths_caused"] + (1 if caused_death else 0)

            # Running average for damage
            old_dealt = row["avg_damage_dealt"] * row["encounters"]
            old_taken = row["avg_damage_taken"] * row["encounters"]
            new_avg_dealt = (old_dealt + damage_dealt) / encounters
            new_avg_taken = (old_taken + damage_taken) / encounters

            # Calculate danger rating (deaths weighted heavily)
            danger = min(1.0, (deaths * 0.3 + new_avg_taken * 0.01) / max(1, encounters * 0.1))

            self._conn.execute(
                """
                UPDATE monster_knowledge SET
                    encounters = ?, kills = ?, deaths_caused = ?,
                    avg_damage_dealt = ?, avg_damage_taken = ?,
                    danger_rating = ?, updated_at = ?
                WHERE monster_name = ?
                """,
                (
                    encounters, kills, deaths, new_avg_dealt, new_avg_taken,
                    danger, datetime.now().isoformat(), monster_name,
                ),
            )
        else:
            # Insert new
            danger = 0.5 + (0.3 if caused_death else 0)
            self._conn.execute(
                """
                INSERT INTO monster_knowledge (
                    monster_name, encounters, kills, deaths_caused,
                    avg_damage_dealt, avg_damage_taken, danger_rating
                ) VALUES (?, 1, ?, ?, ?, ?, ?)
                """,
                (
                    monster_name, 1 if killed else 0, 1 if caused_death else 0,
                    damage_dealt, damage_taken, danger,
                ),
            )

        self._conn.commit()

    def get_monster_danger(self, monster_name: str) -> float:
        """Get danger rating for a monster (0.0 to 1.0)."""
        self._ensure_connected()

        row = self._conn.execute(
            "SELECT danger_rating FROM monster_knowledge WHERE monster_name = ?",
            (monster_name,),
        ).fetchone()

        return row["danger_rating"] if row else 0.5  # Default to medium danger

    def get_dangerous_monsters(self, threshold: float = 0.7) -> list[str]:
        """Get list of monsters above danger threshold."""
        self._ensure_connected()

        rows = self._conn.execute(
            """
            SELECT monster_name FROM monster_knowledge
            WHERE danger_rating >= ?
            ORDER BY danger_rating DESC
            """,
            (threshold,),
        ).fetchall()

        return [row["monster_name"] for row in rows]

    # ==================== Statistics Operations ====================

    def get_episode_statistics(self) -> dict:
        """Get overall statistics across all episodes."""
        self._ensure_connected()

        stats = self._conn.execute(
            """
            SELECT
                COUNT(*) as total_episodes,
                AVG(final_score) as avg_score,
                MAX(final_score) as max_score,
                AVG(final_turns) as avg_turns,
                AVG(final_depth) as avg_depth,
                SUM(CASE WHEN end_reason = 'ascension' THEN 1 ELSE 0 END) as ascensions,
                SUM(CASE WHEN end_reason = 'death' THEN 1 ELSE 0 END) as deaths
            FROM episodes WHERE ended_at IS NOT NULL
            """,
        ).fetchone()

        return dict(stats) if stats else {}

    # ==================== Connection Management ====================

    def close(self) -> None:
        """Close database connection."""
        if self._conn:
            self._conn.close()
            self._conn = None

    def __enter__(self) -> "MemoryManager":
        self.initialize()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.close()
