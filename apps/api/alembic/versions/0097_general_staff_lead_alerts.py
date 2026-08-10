"""Generalize internal staff alerts across every lead source.

Revision ID: 0097_general_staff_lead_alerts
Revises: 0096_underwriting_comp_copilot
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0097_general_staff_lead_alerts"
down_revision: str | None = "0096_underwriting_comp_copilot"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "staff_lead_alerts",
        sa.Column("source_type", sa.String(length=80), nullable=True),
    )
    op.add_column(
        "staff_lead_alerts",
        sa.Column("source_event_id", sa.Uuid(), nullable=True),
    )
    op.execute(
        sa.text(
            "UPDATE staff_lead_alerts "
            "SET source_type = 'facebook_lead_form', source_event_id = meta_lead_event_id"
        )
    )
    op.alter_column(
        "staff_lead_alerts",
        "source_type",
        existing_type=sa.String(length=80),
        nullable=False,
    )
    op.alter_column(
        "staff_lead_alerts",
        "source_event_id",
        existing_type=sa.Uuid(),
        nullable=False,
    )
    op.alter_column(
        "staff_lead_alerts",
        "meta_lead_event_id",
        existing_type=sa.Uuid(),
        nullable=True,
    )
    op.create_index(
        "ix_staff_lead_alerts_source_type",
        "staff_lead_alerts",
        ["source_type"],
    )
    op.create_index(
        "ix_staff_lead_alerts_source_event_id",
        "staff_lead_alerts",
        ["source_event_id"],
    )
    op.create_unique_constraint(
        "uq_staff_lead_alerts_source_recipient",
        "staff_lead_alerts",
        ["organization_id", "source_type", "source_event_id", "recipient_user_id"],
    )


def downgrade() -> None:
    op.execute(sa.text("DELETE FROM staff_lead_alerts WHERE meta_lead_event_id IS NULL"))
    op.drop_constraint(
        "uq_staff_lead_alerts_source_recipient",
        "staff_lead_alerts",
        type_="unique",
    )
    op.drop_index("ix_staff_lead_alerts_source_event_id", table_name="staff_lead_alerts")
    op.drop_index("ix_staff_lead_alerts_source_type", table_name="staff_lead_alerts")
    op.alter_column(
        "staff_lead_alerts",
        "meta_lead_event_id",
        existing_type=sa.Uuid(),
        nullable=False,
    )
    op.drop_column("staff_lead_alerts", "source_event_id")
    op.drop_column("staff_lead_alerts", "source_type")
