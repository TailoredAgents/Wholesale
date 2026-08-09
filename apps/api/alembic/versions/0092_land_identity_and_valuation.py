"""Add parcel-first identity and immutable Land valuation evidence.

Revision ID: 0092_land_identity_and_valuation
Revises: 0091_unified_asset_foundation
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0092_land_identity_and_valuation"
down_revision: str | None = "0091_unified_asset_foundation"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "properties",
        sa.Column("normalized_parcel_key", sa.String(length=500), nullable=True),
    )
    op.create_index(
        "ix_properties_normalized_parcel_key",
        "properties",
        ["normalized_parcel_key"],
    )
    op.execute(
        sa.text(
            """
            UPDATE properties
            SET normalized_parcel_key =
                upper(state) || '|' ||
                regexp_replace(
                    trim(
                        both '_' from lower(
                            regexp_replace(trim(county), '[^A-Za-z0-9]+', '_', 'g')
                        )
                    ),
                    '_county$',
                    ''
                ) || '|' ||
                upper(regexp_replace(trim(parcel_id), '[^A-Za-z0-9]+', '', 'g'))
            WHERE parcel_id IS NOT NULL
              AND trim(parcel_id) <> ''
              AND county IS NOT NULL
              AND trim(county) <> ''
              AND length(trim(state)) = 2
            """
        )
    )

    op.create_table(
        "land_offer_policy_versions",
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("created_by_user_id", sa.Uuid(), nullable=False),
        sa.Column("approved_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column("title", sa.String(length=160), nullable=False),
        sa.Column("quick_sale_discount_low_basis_points", sa.Integer(), nullable=False),
        sa.Column("quick_sale_discount_high_basis_points", sa.Integer(), nullable=False),
        sa.Column("opening_reserve_basis_points", sa.Integer(), nullable=False),
        sa.Column("assignment_fee_cents", sa.BigInteger(), nullable=False),
        sa.Column("closing_title_reserve_cents", sa.BigInteger(), nullable=False),
        sa.Column("curative_reserve_cents", sa.BigInteger(), nullable=False),
        sa.Column("uncertainty_reserve_cents", sa.BigInteger(), nullable=False),
        sa.Column("maximum_dispersion_basis_points", sa.Integer(), nullable=False),
        sa.Column("minimum_comparable_count", sa.Integer(), nullable=False),
        sa.Column("notes", sa.String(length=2000), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["approved_by_user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "organization_id",
            "version_number",
            name="uq_land_offer_policy_org_version",
        ),
    )
    op.create_index(
        "ix_land_offer_policy_versions_organization_id",
        "land_offer_policy_versions",
        ["organization_id"],
    )
    op.create_index(
        "ix_land_offer_policy_versions_status",
        "land_offer_policy_versions",
        ["status"],
    )

    op.create_table(
        "land_valuation_analyses",
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("lead_id", sa.Uuid(), nullable=False),
        sa.Column("property_id", sa.Uuid(), nullable=False),
        sa.Column("property_snapshot_id", sa.Uuid(), nullable=False),
        sa.Column("source_analysis_id", sa.Uuid(), nullable=True),
        sa.Column("policy_version_id", sa.Uuid(), nullable=True),
        sa.Column("created_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column(
            "valuation_profile",
            sa.String(length=80),
            nullable=False,
            server_default="land_v1",
        ),
        sa.Column(
            "methodology_version",
            sa.String(length=80),
            nullable=False,
            server_default="land_v1",
        ),
        sa.Column("analysis_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("request_idempotency_key", sa.String(length=160), nullable=True),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column("guidance_status", sa.String(length=40), nullable=False),
        sa.Column(
            "valuation_basis",
            sa.String(length=40),
            nullable=False,
            server_default="per_acre",
        ),
        sa.Column("access_evidence_status", sa.String(length=40), nullable=False),
        sa.Column("subject_acres_ten_thousandths", sa.BigInteger(), nullable=False),
        sa.Column("subject_lot_count", sa.Integer(), nullable=True),
        sa.Column("supported_value_low_cents", sa.BigInteger(), nullable=True),
        sa.Column("supported_value_cents", sa.BigInteger(), nullable=True),
        sa.Column("supported_value_high_cents", sa.BigInteger(), nullable=True),
        sa.Column("quick_sale_low_cents", sa.BigInteger(), nullable=True),
        sa.Column("quick_sale_high_cents", sa.BigInteger(), nullable=True),
        sa.Column("opening_offer_cents", sa.BigInteger(), nullable=True),
        sa.Column("seller_contract_ceiling_cents", sa.BigInteger(), nullable=True),
        sa.Column("assignment_fee_cents", sa.BigInteger(), nullable=False),
        sa.Column("closing_title_reserve_cents", sa.BigInteger(), nullable=False),
        sa.Column("curative_reserve_cents", sa.BigInteger(), nullable=False),
        sa.Column("uncertainty_reserve_cents", sa.BigInteger(), nullable=False),
        sa.Column("confidence_score", sa.Integer(), nullable=False),
        sa.Column("selected_comp_count", sa.Integer(), nullable=False),
        sa.Column("rejected_comp_count", sa.Integer(), nullable=False),
        sa.Column("selected_comps", sa.JSON(), nullable=False),
        sa.Column("rejected_comps", sa.JSON(), nullable=False),
        sa.Column("subject_snapshot", sa.JSON(), nullable=False),
        sa.Column("search_snapshot", sa.JSON(), nullable=False),
        sa.Column("assumptions", sa.JSON(), nullable=False),
        sa.Column("review_reasons", sa.JSON(), nullable=False),
        sa.Column("guidance_blockers", sa.JSON(), nullable=False),
        sa.Column("policy_snapshot", sa.JSON(), nullable=False),
        sa.Column("metadata", sa.JSON(), nullable=True),
        sa.Column(
            "id",
            sa.Uuid(),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "subject_acres_ten_thousandths > 0",
            name="ck_land_valuation_positive_acres",
        ),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["lead_id"], ["leads.id"]),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        sa.ForeignKeyConstraint(
            ["policy_version_id"],
            ["land_offer_policy_versions.id"],
        ),
        sa.ForeignKeyConstraint(["property_id"], ["properties.id"]),
        sa.ForeignKeyConstraint(
            ["property_snapshot_id"],
            ["property_intelligence_snapshots.id"],
        ),
        sa.ForeignKeyConstraint(
            ["source_analysis_id"],
            ["land_valuation_analyses.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "lead_id",
            "version_number",
            name="uq_land_valuation_lead_version",
        ),
        sa.UniqueConstraint(
            "organization_id",
            "lead_id",
            "analysis_fingerprint",
            name="uq_land_valuation_lead_fingerprint",
        ),
        sa.UniqueConstraint(
            "organization_id",
            "lead_id",
            "request_idempotency_key",
            name="uq_land_valuation_lead_idempotency",
        ),
    )
    for column_name in (
        "organization_id",
        "lead_id",
        "property_id",
        "property_snapshot_id",
        "source_analysis_id",
        "policy_version_id",
        "valuation_profile",
        "analysis_fingerprint",
        "request_idempotency_key",
        "status",
        "guidance_status",
    ):
        op.create_index(
            f"ix_land_valuation_analyses_{column_name}",
            "land_valuation_analyses",
            [column_name],
        )


def downgrade() -> None:
    op.drop_table("land_valuation_analyses")
    op.drop_table("land_offer_policy_versions")
    op.drop_index("ix_properties_normalized_parcel_key", table_name="properties")
    op.drop_column("properties", "normalized_parcel_key")
