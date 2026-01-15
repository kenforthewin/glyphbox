"""
Skill statistics persistence and reporting.

Tracks skill execution statistics in SQLite for cross-session analysis.
"""

import json
import logging
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Optional

from .models import SkillExecution, SkillStatistics

logger = logging.getLogger(__name__)

# Default database path
DEFAULT_DB_PATH = "data/skill_stats.db"

# SQL schema
SCHEMA = """
CREATE TABLE IF NOT EXISTS skill_executions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    skill_name TEXT NOT NULL,
    params TEXT,
    started_at TEXT NOT NULL,
    ended_at TEXT,
    success INTEGER NOT NULL DEFAULT 0,
    stopped_reason TEXT,
    result_data TEXT,
    actions_taken INTEGER DEFAULT 0,
    turns_elapsed INTEGER DEFAULT 0,
    error TEXT,
    state_before TEXT,
    state_after TEXT,
    episode_id TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_skill_name ON skill_executions(skill_name);
CREATE INDEX IF NOT EXISTS idx_started_at ON skill_executions(started_at);
CREATE INDEX IF NOT EXISTS idx_episode_id ON skill_executions(episode_id);

CREATE TABLE IF NOT EXISTS skill_statistics (
    skill_name TEXT PRIMARY KEY,
    total_executions INTEGER DEFAULT 0,
    successful_executions INTEGER DEFAULT 0,
    failed_executions INTEGER DEFAULT 0,
    total_actions INTEGER DEFAULT 0,
    total_turns INTEGER DEFAULT 0,
    stop_reasons TEXT,
    last_executed TEXT,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
);
"""


class StatisticsStore:
    """
    Persistent storage for skill statistics.

    Stores execution history and aggregated statistics in SQLite.

    Example usage:
        store = StatisticsStore("data/stats.db")
        store.initialize()

        # Record an execution
        store.record_execution(execution, episode_id="ep_001")

        # Get statistics
        stats = store.get_statistics("cautious_explore")

        # Generate report
        report = store.generate_report()
    """

    def __init__(self, db_path: Optional[str] = None):
        """
        Initialize the statistics store.

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
        self._conn.executescript(SCHEMA)
        self._conn.commit()

        logger.info(f"Statistics store initialized at {self.db_path}")

    def _ensure_connected(self) -> None:
        """Ensure database is connected."""
        if self._conn is None:
            self.initialize()

    def record_execution(
        self,
        execution: SkillExecution,
        episode_id: Optional[str] = None,
    ) -> int:
        """
        Record a skill execution.

        Args:
            execution: Execution record
            episode_id: Optional episode identifier

        Returns:
            Row ID of inserted record
        """
        self._ensure_connected()

        cursor = self._conn.execute(
            """
            INSERT INTO skill_executions (
                skill_name, params, started_at, ended_at, success,
                stopped_reason, result_data, actions_taken, turns_elapsed,
                error, state_before, state_after, episode_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                execution.skill_name,
                json.dumps(execution.params),
                execution.started_at.isoformat(),
                execution.ended_at.isoformat() if execution.ended_at else None,
                1 if execution.success else 0,
                execution.stopped_reason,
                json.dumps(execution.result_data),
                execution.actions_taken,
                execution.turns_elapsed,
                execution.error,
                json.dumps(execution.state_before.to_dict()) if execution.state_before else None,
                json.dumps(execution.state_after.to_dict()) if execution.state_after else None,
                episode_id,
            ),
        )
        self._conn.commit()

        # Update aggregated statistics
        self._update_statistics(execution)

        return cursor.lastrowid

    def _update_statistics(self, execution: SkillExecution) -> None:
        """Update aggregated statistics for a skill."""
        skill_name = execution.skill_name

        # Get existing stats or create new
        row = self._conn.execute(
            "SELECT * FROM skill_statistics WHERE skill_name = ?",
            (skill_name,),
        ).fetchone()

        if row:
            # Update existing
            stop_reasons = json.loads(row["stop_reasons"] or "{}")
            if execution.stopped_reason:
                stop_reasons[execution.stopped_reason] = (
                    stop_reasons.get(execution.stopped_reason, 0) + 1
                )

            self._conn.execute(
                """
                UPDATE skill_statistics SET
                    total_executions = total_executions + 1,
                    successful_executions = successful_executions + ?,
                    failed_executions = failed_executions + ?,
                    total_actions = total_actions + ?,
                    total_turns = total_turns + ?,
                    stop_reasons = ?,
                    last_executed = ?,
                    updated_at = ?
                WHERE skill_name = ?
                """,
                (
                    1 if execution.success else 0,
                    0 if execution.success else 1,
                    execution.actions_taken,
                    execution.turns_elapsed,
                    json.dumps(stop_reasons),
                    datetime.now().isoformat(),
                    datetime.now().isoformat(),
                    skill_name,
                ),
            )
        else:
            # Insert new
            stop_reasons = {}
            if execution.stopped_reason:
                stop_reasons[execution.stopped_reason] = 1

            self._conn.execute(
                """
                INSERT INTO skill_statistics (
                    skill_name, total_executions, successful_executions,
                    failed_executions, total_actions, total_turns,
                    stop_reasons, last_executed, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    skill_name,
                    1,
                    1 if execution.success else 0,
                    0 if execution.success else 1,
                    execution.actions_taken,
                    execution.turns_elapsed,
                    json.dumps(stop_reasons),
                    datetime.now().isoformat(),
                    datetime.now().isoformat(),
                ),
            )

        self._conn.commit()

    def get_statistics(self, skill_name: str) -> Optional[SkillStatistics]:
        """
        Get statistics for a skill.

        Args:
            skill_name: Skill name

        Returns:
            SkillStatistics or None if not found
        """
        self._ensure_connected()

        row = self._conn.execute(
            "SELECT * FROM skill_statistics WHERE skill_name = ?",
            (skill_name,),
        ).fetchone()

        if not row:
            return None

        return SkillStatistics(
            skill_name=row["skill_name"],
            total_executions=row["total_executions"],
            successful_executions=row["successful_executions"],
            failed_executions=row["failed_executions"],
            total_actions=row["total_actions"],
            total_turns=row["total_turns"],
            stop_reasons=json.loads(row["stop_reasons"] or "{}"),
            last_executed=datetime.fromisoformat(row["last_executed"]) if row["last_executed"] else None,
        )

    def get_all_statistics(self) -> list[SkillStatistics]:
        """Get statistics for all skills."""
        self._ensure_connected()

        rows = self._conn.execute(
            "SELECT * FROM skill_statistics ORDER BY total_executions DESC"
        ).fetchall()

        results = []
        for row in rows:
            results.append(SkillStatistics(
                skill_name=row["skill_name"],
                total_executions=row["total_executions"],
                successful_executions=row["successful_executions"],
                failed_executions=row["failed_executions"],
                total_actions=row["total_actions"],
                total_turns=row["total_turns"],
                stop_reasons=json.loads(row["stop_reasons"] or "{}"),
                last_executed=datetime.fromisoformat(row["last_executed"]) if row["last_executed"] else None,
            ))

        return results

    def get_executions(
        self,
        skill_name: Optional[str] = None,
        episode_id: Optional[str] = None,
        limit: int = 100,
    ) -> list[SkillExecution]:
        """
        Get execution history.

        Args:
            skill_name: Filter by skill name
            episode_id: Filter by episode
            limit: Maximum records to return

        Returns:
            List of execution records
        """
        self._ensure_connected()

        query = "SELECT * FROM skill_executions WHERE 1=1"
        params = []

        if skill_name:
            query += " AND skill_name = ?"
            params.append(skill_name)

        if episode_id:
            query += " AND episode_id = ?"
            params.append(episode_id)

        query += " ORDER BY started_at DESC LIMIT ?"
        params.append(limit)

        rows = self._conn.execute(query, params).fetchall()

        results = []
        for row in rows:
            from .models import GameStateSnapshot

            state_before = None
            if row["state_before"]:
                state_before = GameStateSnapshot.from_dict(json.loads(row["state_before"]))

            state_after = None
            if row["state_after"]:
                state_after = GameStateSnapshot.from_dict(json.loads(row["state_after"]))

            results.append(SkillExecution(
                skill_name=row["skill_name"],
                params=json.loads(row["params"] or "{}"),
                started_at=datetime.fromisoformat(row["started_at"]),
                ended_at=datetime.fromisoformat(row["ended_at"]) if row["ended_at"] else None,
                success=bool(row["success"]),
                stopped_reason=row["stopped_reason"] or "",
                result_data=json.loads(row["result_data"] or "{}"),
                actions_taken=row["actions_taken"],
                turns_elapsed=row["turns_elapsed"],
                error=row["error"],
                state_before=state_before,
                state_after=state_after,
            ))

        return results

    def generate_report(self) -> dict:
        """
        Generate a comprehensive statistics report.

        Returns:
            Dict with overall stats, per-skill breakdown, and trends
        """
        self._ensure_connected()

        # Overall stats
        overall = self._conn.execute(
            """
            SELECT
                COUNT(*) as total_executions,
                SUM(success) as successful,
                SUM(actions_taken) as total_actions,
                SUM(turns_elapsed) as total_turns,
                COUNT(DISTINCT skill_name) as unique_skills,
                COUNT(DISTINCT episode_id) as unique_episodes
            FROM skill_executions
            """
        ).fetchone()

        # Per-skill breakdown
        skills = self.get_all_statistics()

        # Top stop reasons
        stop_reasons = {}
        for skill in skills:
            for reason, count in skill.stop_reasons.items():
                stop_reasons[reason] = stop_reasons.get(reason, 0) + count

        sorted_reasons = sorted(stop_reasons.items(), key=lambda x: x[1], reverse=True)

        return {
            "overall": {
                "total_executions": overall["total_executions"],
                "successful_executions": overall["successful"],
                "success_rate": overall["successful"] / overall["total_executions"] if overall["total_executions"] > 0 else 0,
                "total_actions": overall["total_actions"],
                "total_turns": overall["total_turns"],
                "unique_skills": overall["unique_skills"],
                "unique_episodes": overall["unique_episodes"],
            },
            "skills": [s.to_dict() for s in skills[:20]],
            "top_stop_reasons": sorted_reasons[:10],
        }

    def close(self) -> None:
        """Close database connection."""
        if self._conn:
            self._conn.close()
            self._conn = None

    def __enter__(self) -> "StatisticsStore":
        self.initialize()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.close()
