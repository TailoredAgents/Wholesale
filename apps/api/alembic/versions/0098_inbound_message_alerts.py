"""Persist inbound-message staff alert routing.

Revision ID: 0098_inbound_message_alerts
Revises: 0097_general_staff_lead_alerts
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0098_inbound_message_alerts"
down_revision: str | None = "0097_general_staff_lead_alerts"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column(
            "inbound_message_alert_sms_enabled",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )
    op.execute(
        sa.text(
            "UPDATE users SET inbound_message_alert_sms_enabled = lead_alert_sms_enabled"
        )
    )
    op.alter_column(
        "staff_lead_alerts",
        "lead_id",
        existing_type=sa.Uuid(),
        nullable=True,
    )
    op.add_column(
        "staff_lead_alerts",
        sa.Column(
            "conversation_id",
            sa.Uuid(),
            sa.ForeignKey("conversations.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.create_index(
        "ix_staff_lead_alerts_conversation_id",
        "staff_lead_alerts",
        ["conversation_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_staff_lead_alerts_conversation_id",
        table_name="staff_lead_alerts",
    )
    op.drop_column("staff_lead_alerts", "conversation_id")
    op.execute(sa.text("DELETE FROM staff_lead_alerts WHERE lead_id IS NULL"))
    op.alter_column(
        "staff_lead_alerts",
        "lead_id",
        existing_type=sa.Uuid(),
        nullable=False,
    )
    op.drop_column("users", "inbound_message_alert_sms_enabled")
