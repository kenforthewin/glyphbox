"""Add llm_finish_reason column to turns.

Revision ID: 004
Revises: 003
Create Date: 2026-02-02
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "004"
down_revision: Union[str, None] = "003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("turns", sa.Column("llm_finish_reason", sa.String, nullable=True))


def downgrade() -> None:
    op.drop_column("turns", "llm_finish_reason")
