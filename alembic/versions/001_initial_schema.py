"""Initial schema: users, runs, turns.

Revision ID: 001
Revises:
Create Date: 2026-02-01
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("openrouter_id", sa.String, unique=True, nullable=False),
        sa.Column("display_name", sa.String, nullable=False, server_default=""),
        sa.Column("email", sa.String, nullable=True),
        sa.Column("avatar_url", sa.String, nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )

    op.create_table(
        "runs",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("run_id", sa.String, unique=True, nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("model", sa.String, nullable=False, server_default=""),
        sa.Column("provider", sa.String, nullable=False, server_default="openrouter"),
        sa.Column("config_snapshot", sa.JSON, nullable=True),
        sa.Column("end_reason", sa.String, server_default=""),
        sa.Column("final_score", sa.Integer, server_default="0"),
        sa.Column("final_game_turns", sa.Integer, server_default="0"),
        sa.Column("final_depth", sa.Integer, server_default="0"),
        sa.Column("final_xp_level", sa.Integer, server_default="0"),
        sa.Column("total_agent_turns", sa.Integer, server_default="0"),
        sa.Column("total_llm_tokens", sa.Integer, server_default="0"),
        sa.Column("status", sa.String, server_default="running"),
        sa.Column("user_id", sa.Integer, sa.ForeignKey("users.id"), nullable=True),
        sa.Column("visibility", sa.String, server_default="private", nullable=False),
    )
    op.create_index("idx_runs_started", "runs", [sa.text("started_at DESC")])
    op.create_index("idx_runs_status", "runs", ["status"])
    op.create_index("idx_runs_user", "runs", ["user_id"])

    op.create_table(
        "turns",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("run_id", sa.String, sa.ForeignKey("runs.run_id"), nullable=False),
        sa.Column("turn_number", sa.Integer, nullable=False),
        sa.Column("game_turn", sa.Integer, nullable=False),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False),
        # Game state
        sa.Column("game_screen", sa.Text, nullable=False),
        sa.Column("player_x", sa.Integer, nullable=False),
        sa.Column("player_y", sa.Integer, nullable=False),
        sa.Column("hp", sa.Integer, nullable=False),
        sa.Column("max_hp", sa.Integer, nullable=False),
        sa.Column("dungeon_level", sa.Integer, nullable=False),
        sa.Column("depth", sa.Integer, server_default="0"),
        sa.Column("xp_level", sa.Integer, server_default="1"),
        sa.Column("score", sa.Integer, server_default="0"),
        sa.Column("hunger", sa.String, server_default="Not Hungry"),
        sa.Column("game_message", sa.Text, server_default=""),
        # LLM interaction
        sa.Column("llm_reasoning", sa.Text, server_default=""),
        sa.Column("llm_model", sa.String, server_default=""),
        sa.Column("llm_prompt_tokens", sa.Integer, nullable=True),
        sa.Column("llm_completion_tokens", sa.Integer, nullable=True),
        sa.Column("llm_total_tokens", sa.Integer, nullable=True),
        # Decision
        sa.Column("action_type", sa.String, nullable=False),
        sa.Column("code", sa.Text, nullable=True),
        sa.Column("skill_name", sa.String, nullable=True),
        # Execution result
        sa.Column("execution_success", sa.Boolean, nullable=False, server_default=sa.true()),
        sa.Column("execution_error", sa.Text, nullable=True),
        sa.Column("execution_time_ms", sa.Integer, nullable=True),
        sa.Column("game_messages", sa.JSON, nullable=True),
        sa.Column("api_calls", sa.JSON, nullable=True),
    )
    op.create_index("idx_turns_run", "turns", ["run_id", "turn_number"])
    op.create_index("idx_turns_run_turn", "turns", ["run_id", "turn_number"], unique=True)


def downgrade() -> None:
    op.drop_table("turns")
    op.drop_table("runs")
    op.drop_table("users")
