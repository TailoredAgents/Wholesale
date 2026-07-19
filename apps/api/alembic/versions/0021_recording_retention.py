"""call recording retention and deletion audit fields

Revision ID: 0021_recording_retention
Revises: 0020_twilio_voice
Create Date: 2026-07-18 00:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0021_recording_retention"
down_revision: str | None = "0020_twilio_voice"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "call_recordings",
        sa.Column("retention_expires_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "call_recordings",
        sa.Column("deleted_by_user_id", sa.Uuid(), nullable=True),
    )
    op.add_column(
        "call_recordings",
        sa.Column("deletion_reason", sa.String(length=1000), nullable=True),
    )
    op.create_foreign_key(
        "fk_call_recordings_deleted_by_user_id",
        "call_recordings",
        "users",
        ["deleted_by_user_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_call_recordings_retention_expires_at",
        "call_recordings",
        ["retention_expires_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_call_recordings_retention_expires_at",
        table_name="call_recordings",
    )
    op.drop_constraint(
        "fk_call_recordings_deleted_by_user_id",
        "call_recordings",
        type_="foreignkey",
    )
    op.drop_column("call_recordings", "deletion_reason")
    op.drop_column("call_recordings", "deleted_by_user_id")
    op.drop_column("call_recordings", "retention_expires_at")
