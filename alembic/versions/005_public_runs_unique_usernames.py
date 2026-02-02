"""Make all runs public, add unique username index and leaderboard indexes.

Revision ID: 005
Revises: 004
Create Date: 2026-02-02
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "005"
down_revision: Union[str, None] = "004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Change runs.visibility server_default to 'public'
    op.alter_column(
        "runs",
        "visibility",
        server_default="public",
    )

    # 2. Make all existing runs public
    op.execute("UPDATE runs SET visibility = 'public'")

    # 3. Fix duplicate display_names before adding unique index:
    #    append '-{id}' to any duplicates (keep lowest id unchanged)
    op.execute("""
        UPDATE users SET display_name = display_name || '-' || id::text
        WHERE id NOT IN (
            SELECT MIN(id) FROM users GROUP BY display_name
        )
        AND display_name != ''
    """)

    # 4. Add unique index on users.display_name
    op.create_index("idx_users_display_name", "users", ["display_name"], unique=True)

    # 5. Add leaderboard indexes
    op.create_index("idx_runs_score", "runs", [sa.text("final_score DESC")])
    op.create_index("idx_runs_depth", "runs", [sa.text("final_depth DESC")])


def downgrade() -> None:
    op.drop_index("idx_runs_depth")
    op.drop_index("idx_runs_score")
    op.drop_index("idx_users_display_name")
    op.alter_column("runs", "visibility", server_default="private")
