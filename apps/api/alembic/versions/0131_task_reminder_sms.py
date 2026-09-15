"""Allow an explicitly scheduled task reminder to notify staff by SMS.

Revision ID: 0131_task_reminder_sms
Revises: 0130_manual_lead_reminders
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0131_task_reminder_sms"
down_revision: str | None = "0130_manual_lead_reminders"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "tasks",
        sa.Column(
            "sms_notification_enabled",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )


def downgrade() -> None:
    op.drop_column("tasks", "sms_notification_enabled")
