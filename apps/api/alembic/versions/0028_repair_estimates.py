"""Repair estimate evidence.

Revision ID: 0028_repair_estimates
Revises: 0027_underwriting_calibration
Create Date: 2026-07-21 00:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0028_repair_estimates"
down_revision: str | None = "0027_underwriting_calibration"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "repair_estimates",
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("lead_id", sa.Uuid(), nullable=False),
        sa.Column("property_id", sa.Uuid(), nullable=False),
        sa.Column("created_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("source_type", sa.String(80), nullable=False),
        sa.Column("contractor_name", sa.String(255), nullable=True),
        sa.Column("estimate_date", sa.DateTime(timezone=True), nullable=False),
        sa.Column("scope_items", sa.JSON(), nullable=False),
        sa.Column("subtotal_cents", sa.BigInteger(), nullable=False),
        sa.Column("contingency_percentage", sa.Integer(), nullable=False),
        sa.Column("contingency_cents", sa.BigInteger(), nullable=False),
        sa.Column("total_cents", sa.BigInteger(), nullable=False),
        sa.Column("evidence_reference", sa.String(500), nullable=True),
        sa.Column("notes", sa.String(2000), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        sa.ForeignKeyConstraint(["lead_id"], ["leads.id"]),
        sa.ForeignKeyConstraint(["property_id"], ["properties.id"]),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_repair_estimates_organization_id",
        "repair_estimates",
        ["organization_id"],
    )
    op.create_index("ix_repair_estimates_lead_id", "repair_estimates", ["lead_id"])
    op.create_index("ix_repair_estimates_property_id", "repair_estimates", ["property_id"])
    op.create_index("ix_repair_estimates_source_type", "repair_estimates", ["source_type"])


def downgrade() -> None:
    op.drop_index("ix_repair_estimates_source_type", table_name="repair_estimates")
    op.drop_index("ix_repair_estimates_property_id", table_name="repair_estimates")
    op.drop_index("ix_repair_estimates_lead_id", table_name="repair_estimates")
    op.drop_index("ix_repair_estimates_organization_id", table_name="repair_estimates")
    op.drop_table("repair_estimates")
