"""Add durable storage fields for provider-neutral email attachments.

Revision ID: 0067_f8_resend_inbound
Revises: 0066_f8_email_foundation
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0067_f8_resend_inbound"
down_revision: str | None = "0066_f8_email_foundation"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.alter_column(
        "email_attachments",
        "email_account_id",
        existing_type=sa.Uuid(),
        nullable=True,
    )
    op.add_column(
        "email_attachments",
        sa.Column("email_sender_alias_id", sa.Uuid(), nullable=True),
    )
    op.add_column(
        "email_attachments",
        sa.Column("sha256", sa.String(64), nullable=True),
    )
    op.add_column(
        "email_attachments",
        sa.Column("content_data", sa.LargeBinary(), nullable=True),
    )
    op.add_column(
        "email_attachments",
        sa.Column("storage_provider", sa.String(40), nullable=True),
    )
    op.add_column(
        "email_attachments",
        sa.Column("storage_key", sa.String(1000), nullable=True),
    )
    op.add_column(
        "email_attachments",
        sa.Column("malware_scan_status", sa.String(40), nullable=True),
    )
    op.add_column(
        "email_attachments",
        sa.Column("retention_until", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_email_attachments_sender_alias",
        "email_attachments",
        "email_sender_aliases",
        ["email_sender_alias_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_email_attachments_email_sender_alias_id",
        "email_attachments",
        ["email_sender_alias_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_email_attachments_email_sender_alias_id",
        table_name="email_attachments",
    )
    op.drop_constraint(
        "fk_email_attachments_sender_alias",
        "email_attachments",
        type_="foreignkey",
    )
    op.drop_column("email_attachments", "retention_until")
    op.drop_column("email_attachments", "malware_scan_status")
    op.drop_column("email_attachments", "storage_key")
    op.drop_column("email_attachments", "storage_provider")
    op.drop_column("email_attachments", "content_data")
    op.drop_column("email_attachments", "sha256")
    op.drop_column("email_attachments", "email_sender_alias_id")
    op.alter_column(
        "email_attachments",
        "email_account_id",
        existing_type=sa.Uuid(),
        nullable=False,
    )
