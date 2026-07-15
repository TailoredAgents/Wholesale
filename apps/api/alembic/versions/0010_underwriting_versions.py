"""underwriting versions

Revision ID: 0010_underwriting_versions
Revises: 0009_appointments
Create Date: 2026-07-15 00:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0010_underwriting_versions"
down_revision: str | None = "0009_appointments"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "underwriting_versions",
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("lead_id", sa.Uuid(), nullable=False),
        sa.Column("property_id", sa.Uuid(), nullable=False),
        sa.Column("created_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=80), nullable=False),
        sa.Column("arv_low_cents", sa.BigInteger(), nullable=True),
        sa.Column("arv_high_cents", sa.BigInteger(), nullable=True),
        sa.Column("repair_low_cents", sa.BigInteger(), nullable=True),
        sa.Column("repair_high_cents", sa.BigInteger(), nullable=True),
        sa.Column("max_offer_cents", sa.BigInteger(), nullable=True),
        sa.Column("recommended_offer_cents", sa.BigInteger(), nullable=True),
        sa.Column("offer_strategy", sa.String(length=120), nullable=True),
        sa.Column("notes", sa.String(length=2000), nullable=True),
        sa.Column("source", sa.String(length=80), nullable=False),
        sa.Column("metadata", sa.JSON(), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            onupdate=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["lead_id"], ["leads.id"]),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        sa.ForeignKeyConstraint(["property_id"], ["properties.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "organization_id",
            "lead_id",
            "version_number",
            name="uq_underwriting_versions_org_lead_version",
        ),
    )
    op.create_index(
        "ix_underwriting_versions_organization_id",
        "underwriting_versions",
        ["organization_id"],
    )
    op.create_index("ix_underwriting_versions_lead_id", "underwriting_versions", ["lead_id"])
    op.create_index(
        "ix_underwriting_versions_property_id",
        "underwriting_versions",
        ["property_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_underwriting_versions_property_id", table_name="underwriting_versions")
    op.drop_index("ix_underwriting_versions_lead_id", table_name="underwriting_versions")
    op.drop_index("ix_underwriting_versions_organization_id", table_name="underwriting_versions")
    op.drop_table("underwriting_versions")
