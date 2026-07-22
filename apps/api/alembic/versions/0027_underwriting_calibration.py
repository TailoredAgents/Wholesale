"""Underwriting calibration cases.

Revision ID: 0027_underwriting_calibration
Revises: 0026_property_address_validation
Create Date: 2026-07-21 00:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0027_underwriting_calibration"
down_revision: str | None = "0026_property_address_validation"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "underwriting_calibration_cases",
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("lead_id", sa.Uuid(), nullable=False),
        sa.Column("property_id", sa.Uuid(), nullable=False),
        sa.Column("analysis_id", sa.Uuid(), nullable=False),
        sa.Column("recorded_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("market_key", sa.String(255), nullable=False),
        sa.Column("benchmark_type", sa.String(80), nullable=False),
        sa.Column("evidence_date", sa.DateTime(timezone=True), nullable=False),
        sa.Column("benchmark_arv_cents", sa.BigInteger(), nullable=False),
        sa.Column("actual_rehab_cents", sa.BigInteger(), nullable=True),
        sa.Column("actual_seller_contract_cents", sa.BigInteger(), nullable=True),
        sa.Column("actual_disposition_cents", sa.BigInteger(), nullable=True),
        sa.Column("predicted_arv_low_cents", sa.BigInteger(), nullable=True),
        sa.Column("predicted_arv_point_cents", sa.BigInteger(), nullable=True),
        sa.Column("predicted_arv_high_cents", sa.BigInteger(), nullable=True),
        sa.Column("predicted_rehab_cents", sa.BigInteger(), nullable=True),
        sa.Column("predicted_seller_ceiling_cents", sa.BigInteger(), nullable=True),
        sa.Column("predicted_disposition_cents", sa.BigInteger(), nullable=True),
        sa.Column("evidence_reference", sa.String(500), nullable=True),
        sa.Column("notes", sa.String(2000), nullable=True),
        sa.Column(
            "id",
            sa.Uuid(),
            nullable=False,
        ),
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
        sa.ForeignKeyConstraint(["analysis_id"], ["underwriting_market_analyses.id"]),
        sa.ForeignKeyConstraint(["recorded_by_user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "organization_id",
            "analysis_id",
            name="uq_underwriting_calibration_org_analysis",
        ),
    )
    op.create_index(
        "ix_underwriting_calibration_cases_organization_id",
        "underwriting_calibration_cases",
        ["organization_id"],
    )
    op.create_index(
        "ix_underwriting_calibration_cases_lead_id",
        "underwriting_calibration_cases",
        ["lead_id"],
    )
    op.create_index(
        "ix_underwriting_calibration_cases_property_id",
        "underwriting_calibration_cases",
        ["property_id"],
    )
    op.create_index(
        "ix_underwriting_calibration_cases_analysis_id",
        "underwriting_calibration_cases",
        ["analysis_id"],
    )
    op.create_index(
        "ix_underwriting_calibration_cases_market_key",
        "underwriting_calibration_cases",
        ["market_key"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_underwriting_calibration_cases_market_key",
        table_name="underwriting_calibration_cases",
    )
    op.drop_index(
        "ix_underwriting_calibration_cases_analysis_id",
        table_name="underwriting_calibration_cases",
    )
    op.drop_index(
        "ix_underwriting_calibration_cases_property_id",
        table_name="underwriting_calibration_cases",
    )
    op.drop_index(
        "ix_underwriting_calibration_cases_lead_id",
        table_name="underwriting_calibration_cases",
    )
    op.drop_index(
        "ix_underwriting_calibration_cases_organization_id",
        table_name="underwriting_calibration_cases",
    )
    op.drop_table("underwriting_calibration_cases")
