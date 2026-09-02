"""Add explicit investor queues to disposition execution sessions.

Revision ID: 0125_disposition_explicit_queues
Revises: 0124_disposition_sessions
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0125_disposition_explicit_queues"
down_revision: str | None = "0124_disposition_sessions"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "disposition_execution_sessions",
        sa.Column(
            "queue_mode",
            sa.String(length=40),
            nullable=False,
            server_default="automatic",
        ),
    )
    op.create_check_constraint(
        "ck_disposition_execution_sessions_queue_mode",
        "disposition_execution_sessions",
        "queue_mode IN ('automatic', 'explicit')",
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_disposition_execution_sessions_queue_mode",
        "disposition_execution_sessions",
        type_="check",
    )
    op.drop_column("disposition_execution_sessions", "queue_mode")
