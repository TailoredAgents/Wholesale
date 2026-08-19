"""Tie native prospecting appointments to their source attempt.

Revision ID: 0106_prospecting_dispositions
Revises: 0105_dial_session_coordinator
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0106_prospecting_dispositions"
down_revision: str | None = "0105_dial_session_coordinator"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "appointments",
        sa.Column("prospecting_attempt_id", sa.Uuid(), nullable=True),
    )
    op.create_foreign_key(
        "fk_appointments_prospecting_attempt",
        "appointments",
        "prospecting_attempts",
        ["prospecting_attempt_id"],
        ["id"],
    )
    op.create_index(
        "ix_appointments_prospecting_attempt_id",
        "appointments",
        ["prospecting_attempt_id"],
    )
    op.create_unique_constraint(
        "uq_appointments_org_prospecting_attempt",
        "appointments",
        ["organization_id", "prospecting_attempt_id"],
    )


def downgrade() -> None:
    op.drop_constraint(
        "uq_appointments_org_prospecting_attempt",
        "appointments",
        type_="unique",
    )
    op.drop_index("ix_appointments_prospecting_attempt_id", table_name="appointments")
    op.drop_constraint(
        "fk_appointments_prospecting_attempt",
        "appointments",
        type_="foreignkey",
    )
    op.drop_column("appointments", "prospecting_attempt_id")
