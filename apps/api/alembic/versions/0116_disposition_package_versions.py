"""Add immutable disposition package versions and prepared recipients.

Revision ID: 0116_disposition_package_versions
Revises: 0115_disposition_buyer_pool
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0116_disposition_package_versions"
down_revision: str | None = "0115_disposition_buyer_pool"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "disposition_cases",
        sa.Column("desired_assignment_fee_cents", sa.BigInteger(), nullable=True),
    )
    op.create_table(
        "disposition_package_versions",
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("disposition_case_id", sa.Uuid(), nullable=False),
        sa.Column("created_by_user_id", sa.Uuid(), nullable=False),
        sa.Column("approved_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column("lock_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column("policy_version", sa.String(length=80), nullable=False),
        sa.Column("renderer_version", sa.String(length=80), nullable=False),
        sa.Column("public_snapshot", sa.JSON(), nullable=False),
        sa.Column("private_economics_snapshot", sa.JSON(), nullable=False),
        sa.Column("evidence_manifest", sa.JSON(), nullable=False),
        sa.Column("readiness_snapshot", sa.JSON(), nullable=False),
        sa.Column("source_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("email_summary", sa.String(length=4000), nullable=False),
        sa.Column("sms_summary", sa.String(length=1000), nullable=False),
        sa.Column("approval_reason", sa.String(length=2000), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("pdf_file_name", sa.String(length=255), nullable=True),
        sa.Column("pdf_content_type", sa.String(length=120), nullable=True),
        sa.Column("pdf_size", sa.BigInteger(), nullable=True),
        sa.Column("pdf_sha256", sa.String(length=64), nullable=True),
        sa.Column("pdf_data", sa.LargeBinary(), nullable=True),
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.CheckConstraint(
            "version_number > 0",
            name="ck_disposition_package_versions_version_positive",
        ),
        sa.CheckConstraint(
            "lock_version > 0",
            name="ck_disposition_package_versions_lock_positive",
        ),
        sa.CheckConstraint(
            "status IN ('draft', 'approved', 'superseded', 'rejected')",
            name="ck_disposition_package_versions_status",
        ),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        sa.ForeignKeyConstraint(
            ["disposition_case_id"], ["disposition_cases.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["approved_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.UniqueConstraint(
            "disposition_case_id",
            "version_number",
            name="uq_disposition_package_versions_case_version",
        ),
    )
    op.create_index(
        "ix_disposition_package_versions_org_case_created",
        "disposition_package_versions",
        ["organization_id", "disposition_case_id", "created_at"],
    )
    op.create_index(
        "ix_disposition_package_versions_case_status",
        "disposition_package_versions",
        ["disposition_case_id", "status"],
    )
    op.add_column(
        "disposition_campaigns",
        sa.Column("package_version_id", sa.Uuid(), nullable=True),
    )
    op.create_foreign_key(
        "fk_disposition_campaigns_package_version",
        "disposition_campaigns",
        "disposition_package_versions",
        ["package_version_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_index(
        "ix_disposition_campaigns_package_version_id",
        "disposition_campaigns",
        ["package_version_id"],
    )
    op.create_table(
        "disposition_campaign_recipients",
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("disposition_campaign_id", sa.Uuid(), nullable=False),
        sa.Column("disposition_case_id", sa.Uuid(), nullable=False),
        sa.Column("package_version_id", sa.Uuid(), nullable=False),
        sa.Column("buyer_id", sa.Uuid(), nullable=True),
        sa.Column("prepared_by_user_id", sa.Uuid(), nullable=False),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column("captured_identity", sa.JSON(), nullable=False),
        sa.Column("captured_destination", sa.JSON(), nullable=False),
        sa.Column("idempotency_key", sa.String(length=255), nullable=False),
        sa.Column("artifact_sha256", sa.String(length=64), nullable=False),
        sa.Column("prepared_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.CheckConstraint(
            "status = 'prepared_not_sent'",
            name="ck_disposition_campaign_recipients_prepared_only",
        ),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        sa.ForeignKeyConstraint(
            ["disposition_campaign_id"], ["disposition_campaigns.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["disposition_case_id"], ["disposition_cases.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["package_version_id"],
            ["disposition_package_versions.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(["buyer_id"], ["buyers.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["prepared_by_user_id"], ["users.id"]),
        sa.UniqueConstraint(
            "organization_id",
            "idempotency_key",
            name="uq_disposition_campaign_recipients_org_idempotency",
        ),
        sa.UniqueConstraint(
            "disposition_campaign_id",
            "buyer_id",
            name="uq_disposition_campaign_recipients_campaign_buyer",
        ),
    )
    op.create_index(
        "ix_disposition_campaign_recipients_campaign",
        "disposition_campaign_recipients",
        ["disposition_campaign_id"],
    )
    op.create_index(
        "ix_disposition_campaign_recipients_package",
        "disposition_campaign_recipients",
        ["package_version_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_disposition_campaign_recipients_package",
        table_name="disposition_campaign_recipients",
    )
    op.drop_index(
        "ix_disposition_campaign_recipients_campaign",
        table_name="disposition_campaign_recipients",
    )
    op.drop_table("disposition_campaign_recipients")
    op.drop_index(
        "ix_disposition_campaigns_package_version_id",
        table_name="disposition_campaigns",
    )
    op.drop_constraint(
        "fk_disposition_campaigns_package_version",
        "disposition_campaigns",
        type_="foreignkey",
    )
    op.drop_column("disposition_campaigns", "package_version_id")
    op.drop_index(
        "ix_disposition_package_versions_case_status",
        table_name="disposition_package_versions",
    )
    op.drop_index(
        "ix_disposition_package_versions_org_case_created",
        table_name="disposition_package_versions",
    )
    op.drop_table("disposition_package_versions")
    op.drop_column("disposition_cases", "desired_assignment_fee_cents")
