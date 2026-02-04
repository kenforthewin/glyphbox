"""Add game_screen_colors to turns.

Revision ID: 006
Revises: 005
Create Date: 2026-02-02
"""

import sqlalchemy as sa

from alembic import op

revision: str = "006"
down_revision: str | None = "005"
branch_labels: None = None
depends_on: None = None


def upgrade() -> None:
    op.add_column("turns", sa.Column("game_screen_colors", sa.Text, nullable=True))


def downgrade() -> None:
    op.drop_column("turns", "game_screen_colors")
