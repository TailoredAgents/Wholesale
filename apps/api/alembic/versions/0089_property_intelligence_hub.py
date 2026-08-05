"""Add reusable property intelligence snapshots and research jobs.

Revision ID: 0089_property_intelligence
Revises: 0088_meta_address_enrich
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0089_property_intelligence"
down_revision: str | None = "0088_meta_address_enrich"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "properties",
        sa.Column("research_status", sa.String(40), nullable=False, server_default="not_started"),
    )
    op.add_column("properties", sa.Column("research_requested_at", sa.DateTime(timezone=True)))
    op.add_column("properties", sa.Column("research_completed_at", sa.DateTime(timezone=True)))
    op.add_column("properties", sa.Column("research_last_error", sa.String(2000)))
    op.create_index("ix_properties_research_status", "properties", ["research_status"])

    op.create_table(
        "property_intelligence_snapshots",
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("property_id", sa.Uuid(), nullable=False),
        sa.Column("source_lead_id", sa.Uuid()),
        sa.Column("source_market_analysis_id", sa.Uuid()),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(40), nullable=False),
        sa.Column("is_current", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("address_signature", sa.String(500), nullable=False),
        sa.Column("completeness_score", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("confidence_score", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("facts", sa.JSON(), nullable=False),
        sa.Column("valuation", sa.JSON(), nullable=False),
        sa.Column("comparables", sa.JSON(), nullable=False),
        sa.Column("market_context", sa.JSON(), nullable=False),
        sa.Column("sources", sa.JSON(), nullable=False),
        sa.Column("conflicts", sa.JSON(), nullable=False),
        sa.Column("media", sa.JSON(), nullable=False),
        sa.Column("metadata", sa.JSON()),
        sa.Column("captured_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        sa.ForeignKeyConstraint(["property_id"], ["properties.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["source_lead_id"], ["leads.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(
            ["source_market_analysis_id"],
            ["underwriting_market_analyses.id"],
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "property_id", "version_number", name="uq_property_intelligence_property_version"
        ),
    )
    for name, columns in (
        ("ix_property_intelligence_snapshots_organization_id", ["organization_id"]),
        ("ix_property_intelligence_snapshots_property_id", ["property_id"]),
        ("ix_property_intelligence_snapshots_source_lead_id", ["source_lead_id"]),
        (
            "ix_property_intelligence_snapshots_source_market_analysis_id",
            ["source_market_analysis_id"],
        ),
        ("ix_property_intelligence_snapshots_status", ["status"]),
        ("ix_property_intelligence_snapshots_is_current", ["is_current"]),
        ("ix_property_intelligence_snapshots_address_signature", ["address_signature"]),
        ("ix_property_intelligence_snapshots_expires_at", ["expires_at"]),
    ):
        op.create_index(name, "property_intelligence_snapshots", columns)

    op.create_table(
        "property_research_runs",
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("property_id", sa.Uuid(), nullable=False),
        sa.Column("source_lead_id", sa.Uuid()),
        sa.Column("idempotency_key", sa.String(500), nullable=False),
        sa.Column("trigger_source", sa.String(120), nullable=False),
        sa.Column("address_signature", sa.String(500), nullable=False),
        sa.Column("status", sa.String(40), nullable=False),
        sa.Column("force_refresh", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("next_attempt_at", sa.DateTime(timezone=True)),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.Column("last_error", sa.String(2000)),
        sa.Column("metadata", sa.JSON()),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        sa.ForeignKeyConstraint(["property_id"], ["properties.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["source_lead_id"], ["leads.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "organization_id", "idempotency_key", name="uq_property_research_org_idempotency"
        ),
    )
    for name, columns in (
        ("ix_property_research_runs_organization_id", ["organization_id"]),
        ("ix_property_research_runs_property_id", ["property_id"]),
        ("ix_property_research_runs_source_lead_id", ["source_lead_id"]),
        ("ix_property_research_runs_status", ["status"]),
        ("ix_property_research_runs_next_attempt_at", ["next_attempt_at"]),
    ):
        op.create_index(name, "property_research_runs", columns)


def downgrade() -> None:
    op.drop_table("property_research_runs")
    op.drop_table("property_intelligence_snapshots")
    op.drop_index("ix_properties_research_status", table_name="properties")
    op.drop_column("properties", "research_last_error")
    op.drop_column("properties", "research_completed_at")
    op.drop_column("properties", "research_requested_at")
    op.drop_column("properties", "research_status")
