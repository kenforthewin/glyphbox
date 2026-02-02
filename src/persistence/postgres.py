"""Async PostgreSQL repository using SQLAlchemy Core + asyncpg."""

import logging

from sqlalchemy import desc, distinct, func, insert, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncEngine

from .models import RunRecord, TurnRecord, UserRecord
from .tables import runs, turns, users

logger = logging.getLogger(__name__)


class PostgresRepository:
    """Async repository backed by PostgreSQL.

    All methods are async. Engine lifecycle is managed externally
    (created in FastAPI lifespan or CLI, passed to constructor).
    """

    def __init__(self, engine: AsyncEngine):
        self._engine = engine

    # === User management ===

    async def upsert_user(
        self,
        openrouter_id: str,
        display_name: str = "",
        encrypted_openrouter_key: str | None = None,
    ) -> UserRecord:
        """Insert or update a user by openrouter_id. Returns the user."""
        stmt = (
            pg_insert(users)
            .values(
                openrouter_id=openrouter_id,
                display_name=display_name,
                encrypted_openrouter_key=encrypted_openrouter_key,
            )
            .on_conflict_do_update(
                index_elements=[users.c.openrouter_id],
                set_={
                    "encrypted_openrouter_key": encrypted_openrouter_key,
                    "updated_at": func.now(),
                },
            )
            .returning(users)
        )
        async with self._engine.begin() as conn:
            result = await conn.execute(stmt)
            row = result.mappings().one()
        return self._row_to_user(row)

    async def get_user(self, user_id: int) -> UserRecord | None:
        async with self._engine.connect() as conn:
            result = await conn.execute(select(users).where(users.c.id == user_id))
            row = result.mappings().first()
        if not row:
            return None
        return self._row_to_user(row)

    async def get_user_by_openrouter_id(self, openrouter_id: str) -> UserRecord | None:
        async with self._engine.connect() as conn:
            result = await conn.execute(select(users).where(users.c.openrouter_id == openrouter_id))
            row = result.mappings().first()
        if not row:
            return None
        return self._row_to_user(row)

    # === Run lifecycle ===

    async def create_run(self, run: RunRecord) -> RunRecord:
        async with self._engine.begin() as conn:
            result = await conn.execute(
                insert(runs)
                .values(
                    run_id=run.run_id,
                    started_at=run.started_at,
                    model=run.model,
                    provider=run.provider,
                    config_snapshot=run.config_snapshot,
                    end_reason=run.end_reason,
                    final_score=run.final_score,
                    final_game_turns=run.final_game_turns,
                    final_depth=run.final_depth,
                    final_xp_level=run.final_xp_level,
                    total_agent_turns=run.total_agent_turns,
                    total_llm_tokens=run.total_llm_tokens,
                    status=run.status,
                    user_id=run.user_id,
                    visibility=run.visibility,
                )
                .returning(runs.c.id)
            )
            run.id = result.scalar_one()
        return run

    async def update_run(self, run: RunRecord) -> None:
        async with self._engine.begin() as conn:
            await conn.execute(
                update(runs)
                .where(runs.c.run_id == run.run_id)
                .values(
                    model=run.model,
                    provider=run.provider,
                    config_snapshot=run.config_snapshot,
                    ended_at=run.ended_at,
                    end_reason=run.end_reason,
                    final_score=run.final_score,
                    final_game_turns=run.final_game_turns,
                    final_depth=run.final_depth,
                    final_xp_level=run.final_xp_level,
                    total_agent_turns=run.total_agent_turns,
                    total_llm_tokens=run.total_llm_tokens,
                    status=run.status,
                )
            )

    async def get_run(self, run_id: str) -> RunRecord | None:
        async with self._engine.connect() as conn:
            result = await conn.execute(select(runs).where(runs.c.run_id == run_id))
            row = result.mappings().first()
        if not row:
            return None
        return self._row_to_run(row)

    async def list_runs(
        self,
        limit: int = 50,
        offset: int = 0,
        sort_by: str = "recent",
        model_filter: str | None = None,
        user_id: int | None = None,
    ) -> list[RunRecord]:
        """List runs with optional filtering and sorting.

        All runs are public — no visibility filtering.
        Joins peak stats from turns so score/depth are accurate even when
        run-level finalization failed to persist them.

        Args:
            sort_by: "recent" (default), "score", or "depth"
            model_filter: filter to runs using this model
            user_id: filter to runs by this user
        """
        peak = (
            select(
                turns.c.run_id,
                func.max(turns.c.score).label("peak_score"),
                func.max(func.greatest(turns.c.depth, turns.c.dungeon_level)).label("peak_depth"),
            )
            .group_by(turns.c.run_id)
            .subquery()
        )
        effective_score = func.greatest(
            runs.c.final_score, func.coalesce(peak.c.peak_score, 0)
        )
        effective_depth = func.greatest(
            runs.c.final_depth, func.coalesce(peak.c.peak_depth, 0)
        )

        query = (
            select(
                runs,
                users.c.display_name.label("username"),
                effective_score.label("effective_score"),
                effective_depth.label("effective_depth"),
            )
            .outerjoin(users, runs.c.user_id == users.c.id)
            .outerjoin(peak, runs.c.run_id == peak.c.run_id)
            .limit(limit)
            .offset(offset)
        )

        if model_filter:
            query = query.where(runs.c.model == model_filter)
        if user_id is not None:
            query = query.where(runs.c.user_id == user_id)

        if sort_by == "score":
            query = query.order_by(desc(effective_score))
        elif sort_by == "depth":
            query = query.order_by(desc(effective_depth))
        else:
            query = query.order_by(desc(runs.c.started_at))

        async with self._engine.connect() as conn:
            result = await conn.execute(query)
            rows = result.mappings().all()

        records = []
        for row in rows:
            run = self._row_to_run(row)
            run.final_score = row["effective_score"] or run.final_score
            run.final_depth = row["effective_depth"] or run.final_depth
            records.append(run)
        return records

    async def get_leaderboard(
        self,
        metric: str = "score",
        limit: int = 50,
    ) -> list[RunRecord]:
        """Get top runs ranked by score or depth.

        Only includes finished runs (not currently running).
        Uses peak stats from turns as fallback when run-level stats are 0.
        """
        peak = (
            select(
                turns.c.run_id,
                func.max(turns.c.score).label("peak_score"),
                func.max(func.greatest(turns.c.depth, turns.c.dungeon_level)).label("peak_depth"),
            )
            .group_by(turns.c.run_id)
            .subquery()
        )

        effective_score = func.greatest(
            runs.c.final_score, func.coalesce(peak.c.peak_score, 0)
        )
        effective_depth = func.greatest(
            runs.c.final_depth, func.coalesce(peak.c.peak_depth, 0)
        )

        query = (
            select(
                runs,
                users.c.display_name.label("username"),
                effective_score.label("effective_score"),
                effective_depth.label("effective_depth"),
            )
            .outerjoin(users, runs.c.user_id == users.c.id)
            .outerjoin(peak, runs.c.run_id == peak.c.run_id)
            .where(runs.c.status != "running")
            .limit(limit)
        )

        if metric == "depth":
            query = query.order_by(desc(effective_depth), desc(effective_score))
        else:
            query = query.order_by(desc(effective_score), desc(effective_depth))

        async with self._engine.connect() as conn:
            result = await conn.execute(query)
            rows = result.mappings().all()

        records = []
        for row in rows:
            run = self._row_to_run(row)
            run.final_score = row["effective_score"] or run.final_score
            run.final_depth = row["effective_depth"] or run.final_depth
            records.append(run)
        return records

    async def list_runs_by_status(self, statuses: list[str]) -> list[RunRecord]:
        """List runs matching any of the given statuses."""
        query = select(runs).where(runs.c.status.in_(statuses))
        async with self._engine.connect() as conn:
            result = await conn.execute(query)
            rows = result.mappings().all()
        return [self._row_to_run(row) for row in rows]

    async def list_distinct_models(self) -> list[str]:
        """Return distinct model names from all runs, sorted alphabetically."""
        query = select(distinct(runs.c.model)).where(runs.c.model != "").order_by(runs.c.model)
        async with self._engine.connect() as conn:
            result = await conn.execute(query)
            return [row[0] for row in result.fetchall()]

    async def update_user_display_name(self, user_id: int, display_name: str) -> UserRecord:
        """Update a user's display name. Raises if name is taken (unique constraint)."""
        async with self._engine.begin() as conn:
            result = await conn.execute(
                update(users)
                .where(users.c.id == user_id)
                .values(display_name=display_name, updated_at=func.now())
                .returning(users)
            )
            row = result.mappings().first()
        if not row:
            raise ValueError(f"User {user_id} not found")
        return self._row_to_user(row)

    # === Turn persistence ===

    async def save_turn(self, turn: TurnRecord) -> TurnRecord:
        async with self._engine.begin() as conn:
            result = await conn.execute(
                insert(turns)
                .values(
                    run_id=turn.run_id,
                    turn_number=turn.turn_number,
                    game_turn=turn.game_turn,
                    timestamp=turn.timestamp,
                    game_screen=turn.game_screen,
                    player_x=turn.player_x,
                    player_y=turn.player_y,
                    hp=turn.hp,
                    max_hp=turn.max_hp,
                    dungeon_level=turn.dungeon_level,
                    depth=turn.depth,
                    xp_level=turn.xp_level,
                    score=turn.score,
                    hunger=turn.hunger,
                    game_message=turn.game_message,
                    llm_reasoning=turn.llm_reasoning,
                    llm_model=turn.llm_model,
                    llm_prompt_tokens=turn.llm_prompt_tokens,
                    llm_completion_tokens=turn.llm_completion_tokens,
                    llm_total_tokens=turn.llm_total_tokens,
                    llm_finish_reason=turn.llm_finish_reason,
                    action_type=turn.action_type,
                    code=turn.code,
                    skill_name=turn.skill_name,
                    execution_success=turn.execution_success,
                    execution_error=turn.execution_error,
                    execution_time_ms=turn.execution_time_ms,
                    game_messages=turn.game_messages or None,
                    api_calls=turn.api_calls or None,
                    inventory=turn.inventory or None,
                    dungeon_overview=turn.dungeon_overview or None,
                )
                .returning(turns.c.id)
            )
            turn.id = result.scalar_one()
        return turn

    async def get_turns(
        self, run_id: str, after_turn: int = 0, limit: int = 100
    ) -> list[TurnRecord]:
        async with self._engine.connect() as conn:
            result = await conn.execute(
                select(turns)
                .where(turns.c.run_id == run_id, turns.c.turn_number > after_turn)
                .order_by(turns.c.turn_number)
                .limit(limit)
            )
            rows = result.mappings().all()
        return [self._row_to_turn(row) for row in rows]

    async def get_turn(self, run_id: str, turn_number: int) -> TurnRecord | None:
        async with self._engine.connect() as conn:
            result = await conn.execute(
                select(turns).where(
                    turns.c.run_id == run_id,
                    turns.c.turn_number == turn_number,
                )
            )
            row = result.mappings().first()
        if not row:
            return None
        return self._row_to_turn(row)

    async def get_latest_turn(self, run_id: str) -> TurnRecord | None:
        async with self._engine.connect() as conn:
            result = await conn.execute(
                select(turns)
                .where(turns.c.run_id == run_id)
                .order_by(desc(turns.c.turn_number))
                .limit(1)
            )
            row = result.mappings().first()
        if not row:
            return None
        return self._row_to_turn(row)

    async def get_run_peak_stats(self, run_id: str) -> dict:
        """Get peak score/depth/xp/game_turn across all turns for a run."""
        query = (
            select(
                func.max(turns.c.score).label("score"),
                func.max(func.greatest(turns.c.depth, turns.c.dungeon_level)).label("depth"),
                func.max(turns.c.xp_level).label("xp_level"),
                func.max(turns.c.game_turn).label("game_turn"),
            )
            .where(turns.c.run_id == run_id)
        )
        async with self._engine.connect() as conn:
            row = (await conn.execute(query)).mappings().first()
        if not row or row["score"] is None:
            return {}
        return {
            "score": row["score"] or 0,
            "depth": row["depth"] or 0,
            "xp_level": row["xp_level"] or 0,
            "game_turn": row["game_turn"] or 0,
        }

    async def count_turns(self, run_id: str) -> int:
        async with self._engine.connect() as conn:
            result = await conn.execute(
                select(func.count()).select_from(turns).where(turns.c.run_id == run_id)
            )
            return result.scalar_one()

    async def close(self) -> None:
        await self._engine.dispose()

    # === Row mapping ===

    def _row_to_run(self, row) -> RunRecord:
        return RunRecord(
            id=row["id"],
            run_id=row["run_id"],
            started_at=row["started_at"],
            ended_at=row["ended_at"],
            model=row["model"],
            provider=row["provider"],
            config_snapshot=row["config_snapshot"],
            end_reason=row["end_reason"] or "",
            final_score=row["final_score"],
            final_game_turns=row["final_game_turns"],
            final_depth=row["final_depth"],
            final_xp_level=row["final_xp_level"],
            total_agent_turns=row["total_agent_turns"],
            total_llm_tokens=row["total_llm_tokens"],
            status=row["status"] or "running",
            user_id=row["user_id"],
            visibility=row["visibility"] or "public",
            username=row.get("username", "") or "",
        )

    def _row_to_user(self, row) -> UserRecord:
        return UserRecord(
            id=row["id"],
            openrouter_id=row["openrouter_id"],
            display_name=row["display_name"] or "",
            email=row.get("email"),
            avatar_url=row.get("avatar_url"),
            encrypted_openrouter_key=row.get("encrypted_openrouter_key"),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    def _row_to_turn(self, row) -> TurnRecord:
        return TurnRecord(
            id=row["id"],
            run_id=row["run_id"],
            turn_number=row["turn_number"],
            game_turn=row["game_turn"],
            timestamp=row["timestamp"],
            game_screen=row["game_screen"],
            player_x=row["player_x"],
            player_y=row["player_y"],
            hp=row["hp"],
            max_hp=row["max_hp"],
            dungeon_level=row["dungeon_level"],
            depth=row["depth"],
            xp_level=row["xp_level"],
            score=row["score"],
            hunger=row["hunger"] or "Not Hungry",
            game_message=row["game_message"] or "",
            llm_reasoning=row["llm_reasoning"] or "",
            llm_model=row["llm_model"] or "",
            llm_prompt_tokens=row["llm_prompt_tokens"],
            llm_completion_tokens=row["llm_completion_tokens"],
            llm_total_tokens=row["llm_total_tokens"],
            llm_finish_reason=row["llm_finish_reason"],
            action_type=row["action_type"],
            code=row["code"],
            skill_name=row["skill_name"],
            execution_success=row["execution_success"],
            execution_error=row["execution_error"],
            execution_time_ms=row["execution_time_ms"],
            game_messages=row["game_messages"] or [],
            api_calls=row["api_calls"] or [],
            inventory=row["inventory"],
            dungeon_overview=row["dungeon_overview"],
        )
