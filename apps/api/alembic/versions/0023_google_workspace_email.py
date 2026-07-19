"""Google Workspace email integration

Revision ID: 0023_google_workspace_email
Revises: 0022_ai_call_quality
Create Date: 2026-07-18 00:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0023_google_workspace_email"
down_revision: str | None = "0022_ai_call_quality"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.alter_column(
        "communication_dispatches",
        "recipient",
        existing_type=sa.String(length=80),
        type_=sa.String(length=320),
        existing_nullable=False,
    )
    op.alter_column(
        "communication_records",
        "body",
        existing_type=sa.String(length=4000),
        type_=sa.Text(),
        existing_nullable=False,
    )
    op.create_table(
        "email_accounts",
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("connected_by_user_id", sa.Uuid(), nullable=False),
        sa.Column("provider", sa.String(length=80), nullable=False),
        sa.Column("provider_account_id", sa.String(length=320), nullable=False),
        sa.Column("email_address", sa.String(length=320), nullable=False),
        sa.Column("display_name", sa.String(length=255), nullable=False),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column("is_shared", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("sync_enabled", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("encrypted_access_token", sa.Text(), nullable=True),
        sa.Column("encrypted_refresh_token", sa.Text(), nullable=False),
        sa.Column("access_token_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("history_cursor", sa.String(length=255), nullable=True),
        sa.Column("last_synced_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.String(length=2000), nullable=True),
        sa.Column("signature_text", sa.String(length=4000), nullable=True),
        sa.Column("metadata", sa.JSON(), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(["connected_by_user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "organization_id",
            "provider",
            "email_address",
            name="uq_email_accounts_org_provider_address",
        ),
    )
    op.create_index("ix_email_accounts_organization_id", "email_accounts", ["organization_id"])
    op.create_index("ix_email_accounts_user_id", "email_accounts", ["user_id"])
    op.create_table(
        "email_templates",
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("created_by_user_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.Column("subject_template", sa.String(length=255), nullable=False),
        sa.Column("body_template", sa.String(length=4000), nullable=False),
        sa.Column("is_shared", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("organization_id", "name", name="uq_email_templates_org_name"),
    )
    op.create_index("ix_email_templates_organization_id", "email_templates", ["organization_id"])
    op.create_table(
        "email_attachments",
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("communication_record_id", sa.Uuid(), nullable=False),
        sa.Column("email_account_id", sa.Uuid(), nullable=False),
        sa.Column("provider_message_id", sa.String(length=255), nullable=False),
        sa.Column("provider_attachment_id", sa.String(length=255), nullable=False),
        sa.Column("filename", sa.String(length=500), nullable=False),
        sa.Column("content_type", sa.String(length=255), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("content_id", sa.String(length=500), nullable=True),
        sa.Column("disposition", sa.String(length=40), nullable=False),
        sa.Column("metadata", sa.JSON(), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["communication_record_id"], ["communication_records.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["email_account_id"], ["email_accounts.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "communication_record_id",
            "provider_attachment_id",
            name="uq_email_attachments_communication_provider_id",
        ),
    )
    op.create_index(
        "ix_email_attachments_organization_id", "email_attachments", ["organization_id"]
    )
    op.create_index(
        "ix_email_attachments_communication_record_id",
        "email_attachments",
        ["communication_record_id"],
    )
    op.create_index(
        "ix_email_attachments_email_account_id", "email_attachments", ["email_account_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_email_attachments_email_account_id", table_name="email_attachments")
    op.drop_index("ix_email_attachments_communication_record_id", table_name="email_attachments")
    op.drop_index("ix_email_attachments_organization_id", table_name="email_attachments")
    op.drop_table("email_attachments")
    op.drop_index("ix_email_templates_organization_id", table_name="email_templates")
    op.drop_table("email_templates")
    op.drop_index("ix_email_accounts_user_id", table_name="email_accounts")
    op.drop_index("ix_email_accounts_organization_id", table_name="email_accounts")
    op.drop_table("email_accounts")
    op.alter_column(
        "communication_records",
        "body",
        existing_type=sa.Text(),
        type_=sa.String(length=4000),
        existing_nullable=False,
    )
    op.alter_column(
        "communication_dispatches",
        "recipient",
        existing_type=sa.String(length=320),
        type_=sa.String(length=80),
        existing_nullable=False,
    )
