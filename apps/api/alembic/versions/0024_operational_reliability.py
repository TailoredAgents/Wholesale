"""Operational reliability records

Revision ID: 0024_operational_reliability
Revises: 0023_google_workspace_email
Create Date: 2026-07-21 00:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0024_operational_reliability"
down_revision: str | None = "0023_google_workspace_email"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "worker_heartbeats",
        sa.Column("service_name", sa.String(length=160), nullable=False),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("heartbeat_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_success_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("consecutive_failures", sa.Integer(), server_default="0", nullable=False),
        sa.Column("total_failures", sa.Integer(), server_default="0", nullable=False),
        sa.Column("metadata", sa.JSON(), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("service_name"),
    )
    op.create_table(
        "operational_failures",
        sa.Column("service_name", sa.String(length=160), nullable=False),
        sa.Column("operation_name", sa.String(length=160), nullable=False),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column("fingerprint", sa.String(length=64), nullable=False),
        sa.Column("attempt_count", sa.Integer(), server_default="1", nullable=False),
        sa.Column("error_type", sa.String(length=255), nullable=False),
        sa.Column("error_message", sa.String(length=2000), nullable=False),
        sa.Column("first_occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("next_retry_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("metadata", sa.JSON(), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_operational_failures_service_name", "operational_failures", ["service_name"]
    )
    op.create_index(
        "ix_operational_failures_operation_name", "operational_failures", ["operation_name"]
    )
    op.create_index("ix_operational_failures_status", "operational_failures", ["status"])
    op.create_index(
        "ix_operational_failures_fingerprint", "operational_failures", ["fingerprint"]
    )


def downgrade() -> None:
    op.drop_index("ix_operational_failures_fingerprint", table_name="operational_failures")
    op.drop_index("ix_operational_failures_status", table_name="operational_failures")
    op.drop_index("ix_operational_failures_operation_name", table_name="operational_failures")
    op.drop_index("ix_operational_failures_service_name", table_name="operational_failures")
    op.drop_table("operational_failures")
    op.drop_table("worker_heartbeats")
