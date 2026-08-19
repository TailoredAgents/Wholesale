"""Add durable coordination controls for the native prospecting dialer.

Revision ID: 0105_dial_session_coordinator
Revises: 0104_prospecting_voice_context
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0105_dial_session_coordinator"
down_revision: str | None = "0104_prospecting_voice_context"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


CURRENT_WORK_CHECK = (
    "(current_prospect_id IS NULL "
    "AND current_batch_entry_id IS NULL "
    "AND current_attempt_id IS NULL) OR "
    "(current_prospect_id IS NOT NULL "
    "AND current_batch_entry_id IS NOT NULL "
    "AND current_attempt_id IS NOT NULL)"
)

LEASE_LIFECYCLE_CHECK = (
    "(state IN ('ended', 'stopped', 'failed', 'expired') "
    "AND lease_token IS NULL AND lease_expires_at IS NULL) OR "
    "(state NOT IN ('ended', 'stopped', 'failed', 'expired') "
    "AND lease_token IS NOT NULL AND lease_expires_at IS NOT NULL)"
)


def upgrade() -> None:
    op.add_column(
        "organizations",
        sa.Column(
            "prospecting_dialer_enabled",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )
    op.add_column(
        "campaigns",
        sa.Column(
            "prospecting_dialer_enabled",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )

    op.create_check_constraint(
        "ck_prospecting_dial_sessions_current_work",
        "prospecting_dial_sessions",
        CURRENT_WORK_CHECK,
    )
    op.create_check_constraint(
        "ck_prospecting_dial_sessions_lease_lifecycle",
        "prospecting_dial_sessions",
        LEASE_LIFECYCLE_CHECK,
    )

    op.create_index(
        "ix_prospect_calling_batch_entries_dial_candidate",
        "prospect_calling_batch_entries",
        [
            "organization_id",
            "assigned_user_id",
            "prospect_calling_batch_id",
            "status",
            "next_attempt_at",
            "sequence_number",
        ],
    )

    op.add_column(
        "prospecting_dial_legs",
        sa.Column(
            "reserved_cost_cents",
            sa.BigInteger(),
            nullable=False,
            server_default="0",
        ),
    )
    op.add_column(
        "prospecting_dial_legs",
        sa.Column("actual_cost_cents", sa.BigInteger(), nullable=True),
    )
    op.create_check_constraint(
        "ck_prospecting_dial_legs_reserved_cost",
        "prospecting_dial_legs",
        "reserved_cost_cents >= 0",
    )
    op.create_check_constraint(
        "ck_prospecting_dial_legs_actual_cost",
        "prospecting_dial_legs",
        "actual_cost_cents IS NULL OR actual_cost_cents >= 0",
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_prospecting_dial_legs_actual_cost",
        "prospecting_dial_legs",
        type_="check",
    )
    op.drop_constraint(
        "ck_prospecting_dial_legs_reserved_cost",
        "prospecting_dial_legs",
        type_="check",
    )
    op.drop_column("prospecting_dial_legs", "actual_cost_cents")
    op.drop_column("prospecting_dial_legs", "reserved_cost_cents")

    op.drop_index(
        "ix_prospect_calling_batch_entries_dial_candidate",
        table_name="prospect_calling_batch_entries",
    )

    op.drop_constraint(
        "ck_prospecting_dial_sessions_lease_lifecycle",
        "prospecting_dial_sessions",
        type_="check",
    )
    op.drop_constraint(
        "ck_prospecting_dial_sessions_current_work",
        "prospecting_dial_sessions",
        type_="check",
    )

    op.drop_column("campaigns", "prospecting_dialer_enabled")
    op.drop_column("organizations", "prospecting_dialer_enabled")
