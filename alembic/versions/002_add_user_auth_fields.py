"""Add encrypted_openrouter_key to users table.

Revision ID: 002
Revises: 001
Create Date: 2026-02-01
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "002"
down_revision: Union[str, None] = "001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("users", sa.Column("encrypted_openrouter_key", sa.Text, nullable=True))


def downgrade() -> None:
    op.drop_column("users", "encrypted_openrouter_key")
