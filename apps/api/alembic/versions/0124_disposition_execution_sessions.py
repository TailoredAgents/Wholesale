"""Add durable per-operator disposition execution sessions.

Revision ID: 0124_disposition_sessions
Revises: 0123_disposition_advisory
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0124_disposition_sessions"
down_revision: str | None = "0123_disposition_advisory"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "disposition_execution_sessions",
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("disposition_case_id", sa.Uuid(), nullable=False),
        sa.Column("operator_user_id", sa.Uuid(), nullable=False),
        sa.Column("buyer_pool_run_id", sa.Uuid(), nullable=True),
        sa.Column("current_buyer_id", sa.Uuid(), nullable=True),
        sa.Column("state", sa.String(length=40), nullable=False, server_default="active"),
        sa.Column("queue_buyer_ids", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("skipped_buyer_ids", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("buyer_states", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("last_outcome", sa.String(length=40), nullable=True),
        sa.Column("last_outcome_buyer_id", sa.Uuid(), nullable=True),
        sa.Column("last_outcome_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("follow_up_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("paused_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("resumed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("lock_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.CheckConstraint(
            "state IN ('active', 'paused')",
            name="ck_disposition_execution_sessions_state",
        ),
        sa.CheckConstraint(
            "lock_version > 0",
            name="ck_disposition_execution_sessions_lock_positive",
        ),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        sa.ForeignKeyConstraint(
            ["disposition_case_id"],
            ["disposition_cases.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(["operator_user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(
            ["buyer_pool_run_id"],
            ["disposition_buyer_pool_runs.id"],
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["current_buyer_id"],
            ["buyers.id"],
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["last_outcome_buyer_id"],
            ["buyers.id"],
            ondelete="SET NULL",
        ),
        sa.UniqueConstraint(
            "organization_id",
            "disposition_case_id",
            "operator_user_id",
            name="uq_disposition_execution_sessions_operator_case",
        ),
    )
    op.create_index(
        "ix_disposition_execution_sessions_org_operator_state",
        "disposition_execution_sessions",
        ["organization_id", "operator_user_id", "state"],
    )
    op.create_index(
        "ix_disposition_execution_sessions_case_updated",
        "disposition_execution_sessions",
        ["disposition_case_id", "updated_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_disposition_execution_sessions_case_updated",
        table_name="disposition_execution_sessions",
    )
    op.drop_index(
        "ix_disposition_execution_sessions_org_operator_state",
        table_name="disposition_execution_sessions",
    )
    op.drop_table("disposition_execution_sessions")
