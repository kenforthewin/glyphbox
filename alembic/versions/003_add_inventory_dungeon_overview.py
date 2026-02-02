"""Add inventory and dungeon_overview columns to turns.

Revision ID: 003
Revises: 002
Create Date: 2026-02-02
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "003"
down_revision: Union[str, None] = "002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("turns", sa.Column("inventory", sa.JSON, nullable=True))
    op.add_column("turns", sa.Column("dungeon_overview", sa.Text, nullable=True))


def downgrade() -> None:
    op.drop_column("turns", "dungeon_overview")
    op.drop_column("turns", "inventory")
