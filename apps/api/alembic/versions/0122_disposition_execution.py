"""Add structured disposition execution metadata.

Revision ID: 0122_disposition_execution
Revises: 0121_dealmachine_buyer_tiers
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0122_disposition_execution"
down_revision: str | None = "0121_dealmachine_buyer_tiers"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "buyer_engagements",
        sa.Column("idempotency_key", sa.String(length=120), nullable=True),
    )
    op.create_unique_constraint(
        "uq_buyer_engagements_case_idempotency",
        "buyer_engagements",
        ["organization_id", "disposition_case_id", "idempotency_key"],
    )
    op.add_column(
        "buyer_engagements",
        sa.Column(
            "metadata",
            sa.JSON(),
            nullable=False,
            server_default=sa.text("'{}'"),
        ),
    )
    op.create_table(
        "disposition_package_share_links",
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("disposition_case_id", sa.Uuid(), nullable=False),
        sa.Column("package_version_id", sa.Uuid(), nullable=False),
        sa.Column("created_by_user_id", sa.Uuid(), nullable=False),
        sa.Column("revoked_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("token_digest", sa.String(length=64), nullable=False),
        sa.Column("token_hint", sa.String(length=12), nullable=False),
        sa.Column("artifact_sha256", sa.String(length=64), nullable=False),
        sa.Column("lock_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revocation_reason", sa.String(length=500), nullable=True),
        sa.Column("access_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("first_accessed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_accessed_at", sa.DateTime(timezone=True), nullable=True),
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
            "lock_version > 0",
            name="ck_disposition_package_share_links_lock_positive",
        ),
        sa.CheckConstraint(
            "access_count >= 0",
            name="ck_disposition_package_share_links_access_count_nonnegative",
        ),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        sa.ForeignKeyConstraint(
            ["disposition_case_id"],
            ["disposition_cases.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["package_version_id"],
            ["disposition_package_versions.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(
            ["revoked_by_user_id"],
            ["users.id"],
            ondelete="SET NULL",
        ),
        sa.UniqueConstraint(
            "token_digest",
            name="uq_disposition_package_share_links_token_digest",
        ),
    )
    op.create_index(
        "ix_disposition_package_share_links_org_case_created",
        "disposition_package_share_links",
        ["organization_id", "disposition_case_id", "created_at"],
    )
    op.create_index(
        "ix_disposition_package_share_links_package_expiry",
        "disposition_package_share_links",
        ["package_version_id", "expires_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_disposition_package_share_links_package_expiry",
        table_name="disposition_package_share_links",
    )
    op.drop_index(
        "ix_disposition_package_share_links_org_case_created",
        table_name="disposition_package_share_links",
    )
    op.drop_table("disposition_package_share_links")
    op.drop_column("buyer_engagements", "metadata")
    op.drop_constraint(
        "uq_buyer_engagements_case_idempotency",
        "buyer_engagements",
        type_="unique",
    )
    op.drop_column("buyer_engagements", "idempotency_key")
