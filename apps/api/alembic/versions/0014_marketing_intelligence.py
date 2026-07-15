"""marketing intelligence

Revision ID: 0014_marketing_intelligence
Revises: 0013_finance_compensation
Create Date: 2026-07-15 00:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0014_marketing_intelligence"
down_revision: str | None = "0013_finance_compensation"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "offline_conversion_exports",
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("platform", sa.String(length=80), nullable=False),
        sa.Column("conversion_event_id", sa.Uuid(), nullable=True),
        sa.Column("lead_id", sa.Uuid(), nullable=True),
        sa.Column("revenue_record_id", sa.Uuid(), nullable=True),
        sa.Column("event_name", sa.String(length=120), nullable=False),
        sa.Column("click_id", sa.String(length=255), nullable=False),
        sa.Column("click_id_type", sa.String(length=80), nullable=False),
        sa.Column("value_cents", sa.BigInteger(), nullable=True),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("status", sa.String(length=80), nullable=False),
        sa.Column("attempt_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("exported_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.String(length=1000), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            onupdate=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(["conversion_event_id"], ["conversion_events.id"]),
        sa.ForeignKeyConstraint(["lead_id"], ["leads.id"]),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        sa.ForeignKeyConstraint(["revenue_record_id"], ["revenue_records.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "organization_id",
            "platform",
            "revenue_record_id",
            name="uq_offline_exports_org_platform_revenue",
        ),
    )
    op.create_index(
        "ix_offline_conversion_exports_organization_id",
        "offline_conversion_exports",
        ["organization_id"],
    )
    op.create_index(
        "ix_offline_conversion_exports_conversion_event_id",
        "offline_conversion_exports",
        ["conversion_event_id"],
    )
    op.create_index(
        "ix_offline_conversion_exports_lead_id",
        "offline_conversion_exports",
        ["lead_id"],
    )
    op.create_index(
        "ix_offline_conversion_exports_revenue_record_id",
        "offline_conversion_exports",
        ["revenue_record_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_offline_conversion_exports_revenue_record_id",
        table_name="offline_conversion_exports",
    )
    op.drop_index("ix_offline_conversion_exports_lead_id", table_name="offline_conversion_exports")
    op.drop_index(
        "ix_offline_conversion_exports_conversion_event_id",
        table_name="offline_conversion_exports",
    )
    op.drop_index(
        "ix_offline_conversion_exports_organization_id",
        table_name="offline_conversion_exports",
    )
    op.drop_table("offline_conversion_exports")
