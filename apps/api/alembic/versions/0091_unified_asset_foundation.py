"""Add the shared House and Land persistence foundation.

Revision ID: 0091_unified_asset_foundation
Revises: 0090_property_timestamps
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0091_unified_asset_foundation"
down_revision: str | None = "0090_property_timestamps"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


ASSET_CLASS_TABLES = (
    "campaigns",
    "prospects",
    "prospecting_script_versions",
    "lead_qualification_script_versions",
    "leads",
)

ASSET_CLASS_CHECKS = {
    "campaigns": "ck_campaigns_asset_class",
    "prospects": "ck_prospects_asset_class",
    "prospecting_script_versions": "ck_prospecting_script_versions_asset_class",
    "lead_qualification_script_versions": (
        "ck_lead_qualification_script_versions_asset_class"
    ),
    "leads": "ck_leads_asset_class",
}


def _add_required_string(
    table_name: str,
    column_name: str,
    *,
    length: int,
    default: str,
) -> None:
    op.add_column(
        table_name,
        sa.Column(
            column_name,
            sa.String(length=length),
            nullable=True,
            server_default=default,
        ),
    )
    op.execute(
        sa.text(
            f"UPDATE {table_name} SET {column_name} = :default "
            f"WHERE {column_name} IS NULL"
        ).bindparams(default=default)
    )
    op.alter_column(
        table_name,
        column_name,
        existing_type=sa.String(length=length),
        existing_nullable=True,
        nullable=False,
        server_default=default,
    )


def _add_required_json(table_name: str, column_name: str) -> None:
    op.add_column(
        table_name,
        sa.Column(
            column_name,
            sa.JSON(),
            nullable=True,
            server_default=sa.text("'{}'"),
        ),
    )
    op.execute(
        sa.text(f"UPDATE {table_name} SET {column_name} = '{{}}' WHERE {column_name} IS NULL")
    )
    op.alter_column(
        table_name,
        column_name,
        existing_type=sa.JSON(),
        existing_nullable=True,
        nullable=False,
        server_default=sa.text("'{}'"),
    )


def upgrade() -> None:
    for table_name in ASSET_CLASS_TABLES:
        _add_required_string(
            table_name,
            "asset_class",
            length=40,
            default="house",
        )
        op.create_check_constraint(
            ASSET_CLASS_CHECKS[table_name],
            table_name,
            "asset_class IN ('house', 'land')",
        )
        op.create_index(
            f"ix_{table_name}_asset_class",
            table_name,
            ["asset_class"],
        )

    _add_required_json("leads", "qualification_context")

    op.add_column(
        "properties",
        sa.Column("parcel_id", sa.String(length=255), nullable=True),
    )
    op.create_index("ix_properties_parcel_id", "properties", ["parcel_id"])

    _add_required_string(
        "property_intelligence_snapshots",
        "research_profile",
        length=80,
        default="house_v1",
    )
    op.create_index(
        "ix_property_intelligence_snapshots_research_profile",
        "property_intelligence_snapshots",
        ["research_profile"],
    )
    op.drop_constraint(
        "uq_property_intelligence_property_version",
        "property_intelligence_snapshots",
        type_="unique",
    )
    op.create_unique_constraint(
        "uq_property_intelligence_property_profile_version",
        "property_intelligence_snapshots",
        ["property_id", "research_profile", "version_number"],
    )

    _add_required_string(
        "property_research_runs",
        "research_profile",
        length=80,
        default="house_v1",
    )
    op.create_index(
        "ix_property_research_runs_research_profile",
        "property_research_runs",
        ["research_profile"],
    )

    for table_name in ("underwriting_versions", "underwriting_market_analyses"):
        _add_required_string(
            table_name,
            "valuation_profile",
            length=80,
            default="house_v3",
        )
        op.create_index(
            f"ix_{table_name}_valuation_profile",
            table_name,
            ["valuation_profile"],
        )

    _add_required_json("buyer_criteria", "criteria_metadata")


def downgrade() -> None:
    op.drop_column("buyer_criteria", "criteria_metadata")

    for table_name in ("underwriting_market_analyses", "underwriting_versions"):
        op.drop_index(f"ix_{table_name}_valuation_profile", table_name=table_name)
        op.drop_column(table_name, "valuation_profile")

    op.drop_index(
        "ix_property_research_runs_research_profile",
        table_name="property_research_runs",
    )
    op.drop_column("property_research_runs", "research_profile")

    op.drop_constraint(
        "uq_property_intelligence_property_profile_version",
        "property_intelligence_snapshots",
        type_="unique",
    )
    # Different profiles may independently use the same version number. Renumber them
    # deterministically before restoring the legacy property-wide uniqueness contract.
    op.execute(
        sa.text(
            """
            WITH ranked AS (
                SELECT
                    id,
                    ROW_NUMBER() OVER (
                        PARTITION BY property_id
                        ORDER BY version_number, created_at, id
                    ) AS legacy_version_number
                FROM property_intelligence_snapshots
            )
            UPDATE property_intelligence_snapshots
            SET version_number = (
                SELECT ranked.legacy_version_number
                FROM ranked
                WHERE ranked.id = property_intelligence_snapshots.id
            )
            """
        )
    )
    op.create_unique_constraint(
        "uq_property_intelligence_property_version",
        "property_intelligence_snapshots",
        ["property_id", "version_number"],
    )
    op.drop_index(
        "ix_property_intelligence_snapshots_research_profile",
        table_name="property_intelligence_snapshots",
    )
    op.drop_column("property_intelligence_snapshots", "research_profile")

    op.drop_index("ix_properties_parcel_id", table_name="properties")
    op.drop_column("properties", "parcel_id")

    op.drop_column("leads", "qualification_context")
    for table_name in reversed(ASSET_CLASS_TABLES):
        op.drop_index(f"ix_{table_name}_asset_class", table_name=table_name)
        op.drop_constraint(
            ASSET_CLASS_CHECKS[table_name],
            table_name,
            type_="check",
        )
        op.drop_column(table_name, "asset_class")
