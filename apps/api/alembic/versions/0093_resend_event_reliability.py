"""Add leases and bounded retries for Resend provider events.

Revision ID: 0093_resend_event_reliability
Revises: 0092_land_identity_and_valuation
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0093_resend_event_reliability"
down_revision: str | None = "0092_land_identity_and_valuation"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "communication_provider_events",
        sa.Column("attempt_count", sa.Integer(), server_default="0", nullable=False),
    )
    op.add_column(
        "communication_provider_events",
        sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "communication_provider_events",
        sa.Column("processing_started_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "communication_provider_events",
        sa.Column("processing_token", sa.Uuid(), nullable=True),
    )
    op.execute(
        sa.text(
            """
            UPDATE communication_provider_events
            SET processing_started_at = updated_at
            WHERE provider = 'resend'
              AND processing_status = 'processing'
              AND processing_started_at IS NULL
            """
        )
    )
    op.create_index(
        "ix_provider_events_processing_claim",
        "communication_provider_events",
        [
            "provider",
            "processing_status",
            "next_attempt_at",
            "processing_started_at",
            "received_at",
        ],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_provider_events_processing_claim",
        table_name="communication_provider_events",
    )
    op.drop_column("communication_provider_events", "processing_token")
    op.drop_column("communication_provider_events", "processing_started_at")
    op.drop_column("communication_provider_events", "next_attempt_at")
    op.drop_column("communication_provider_events", "attempt_count")
