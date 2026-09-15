"""Replace automatic mailbox response timers with deliberate reminders.

Revision ID: 0132_manual_inbox_reminders
Revises: 0131_task_reminder_sms
"""

from collections.abc import Sequence
from datetime import UTC, datetime

import sqlalchemy as sa

from alembic import op

revision: str = "0132_manual_inbox_reminders"
down_revision: str | None = "0131_task_reminder_sms"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "conversations",
        sa.Column(
            "response_status",
            sa.String(length=40),
            nullable=False,
            server_default="none",
        ),
    )
    op.add_column(
        "conversations",
        sa.Column("response_due_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "conversations",
        sa.Column("response_status_updated_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "conversations",
        sa.Column("response_status_updated_by_user_id", sa.Uuid(), nullable=True),
    )
    op.create_foreign_key(
        "fk_conversations_response_status_updated_by_user_id",
        "conversations",
        "users",
        ["response_status_updated_by_user_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_conversations_response_status",
        "conversations",
        ["response_status"],
    )
    op.create_index(
        "ix_conversations_response_due_at",
        "conversations",
        ["response_due_at"],
    )
    op.create_check_constraint(
        "ck_conversations_response_status",
        "conversations",
        "response_status IN ('none', 'needs_reply', 'waiting')",
    )

    # Existing red reply timers were inferred solely from elapsed time. Retire them without
    # deleting messages or changing unread state; only reminders deliberately scheduled after
    # this migration can become overdue.
    now = datetime.now(UTC)
    op.execute(
        sa.text(
            "UPDATE notifications SET read_at = :now "
            "WHERE read_at IS NULL AND notification_type IN "
            "('mailbox_response_due', 'mailbox_owner_escalation')"
        ).bindparams(now=now)
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_conversations_response_status",
        "conversations",
        type_="check",
    )
    op.drop_index("ix_conversations_response_due_at", table_name="conversations")
    op.drop_index("ix_conversations_response_status", table_name="conversations")
    op.drop_constraint(
        "fk_conversations_response_status_updated_by_user_id",
        "conversations",
        type_="foreignkey",
    )
    op.drop_column("conversations", "response_status_updated_by_user_id")
    op.drop_column("conversations", "response_status_updated_at")
    op.drop_column("conversations", "response_due_at")
    op.drop_column("conversations", "response_status")
