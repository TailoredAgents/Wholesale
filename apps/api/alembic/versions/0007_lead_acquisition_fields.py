"""lead acquisition fields

Revision ID: 0007_lead_acquisition_fields
Revises: 0006_conversion_events
Create Date: 2026-07-15 00:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0007_lead_acquisition_fields"
down_revision: str | None = "0006_conversion_events"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("leads", sa.Column("motivation", sa.String(length=500), nullable=True))
    op.add_column("leads", sa.Column("desired_timeline", sa.String(length=120), nullable=True))
    op.add_column("leads", sa.Column("property_condition", sa.String(length=120), nullable=True))
    op.add_column("leads", sa.Column("occupancy_status", sa.String(length=120), nullable=True))
    op.add_column("leads", sa.Column("asking_price", sa.String(length=120), nullable=True))
    op.add_column("leads", sa.Column("mortgage_balance", sa.String(length=120), nullable=True))
    op.add_column("leads", sa.Column("appointment_status", sa.String(length=120), nullable=True))
    op.add_column(
        "leads",
        sa.Column("next_follow_up_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("leads", "next_follow_up_at")
    op.drop_column("leads", "appointment_status")
    op.drop_column("leads", "mortgage_balance")
    op.drop_column("leads", "asking_price")
    op.drop_column("leads", "occupancy_status")
    op.drop_column("leads", "property_condition")
    op.drop_column("leads", "desired_timeline")
    op.drop_column("leads", "motivation")
