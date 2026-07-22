"""Operating model market, territory, campaign, and prospect foundation.

Revision ID: 0030_operating_model_foundation
Revises: 0029_offer_negotiation_plans
Create Date: 2026-07-21 00:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0030_operating_model_foundation"
down_revision: str | None = "0029_offer_negotiation_plans"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def id_column() -> sa.Column[object]:
    return sa.Column("id", sa.Uuid(), nullable=False)


def timestamps() -> tuple[sa.Column[object], sa.Column[object]]:
    return (
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )


def upgrade() -> None:
    op.create_table(
        "markets",
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(160), nullable=False),
        sa.Column("code", sa.String(80), nullable=False),
        sa.Column("state_code", sa.String(2), nullable=False),
        sa.Column("timezone", sa.String(80), nullable=False),
        sa.Column("status", sa.String(40), nullable=False),
        sa.Column("is_primary", sa.Boolean(), server_default="false", nullable=False),
        id_column(),
        *timestamps(),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("organization_id", "code", name="uq_markets_org_code"),
    )
    _indexes("markets", "organization_id", "status")

    op.create_table(
        "territories",
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("market_id", sa.Uuid(), nullable=False),
        sa.Column("assigned_team_id", sa.Uuid(), nullable=True),
        sa.Column("name", sa.String(160), nullable=False),
        sa.Column("code", sa.String(80), nullable=False),
        sa.Column("status", sa.String(40), nullable=False),
        sa.Column("county_names", sa.JSON(), nullable=False),
        sa.Column("postal_codes", sa.JSON(), nullable=False),
        id_column(),
        *timestamps(),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        sa.ForeignKeyConstraint(["market_id"], ["markets.id"]),
        sa.ForeignKeyConstraint(["assigned_team_id"], ["teams.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("market_id", "code", name="uq_territories_market_code"),
    )
    _indexes("territories", "organization_id", "market_id", "assigned_team_id", "status")

    op.create_table(
        "campaigns",
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("market_id", sa.Uuid(), nullable=False),
        sa.Column("territory_id", sa.Uuid(), nullable=True),
        sa.Column("owner_user_id", sa.Uuid(), nullable=True),
        sa.Column("name", sa.String(160), nullable=False),
        sa.Column("code", sa.String(80), nullable=False),
        sa.Column("channel", sa.String(80), nullable=False),
        sa.Column("status", sa.String(40), nullable=False),
        sa.Column("starts_on", sa.Date(), nullable=True),
        sa.Column("ends_on", sa.Date(), nullable=True),
        sa.Column("budget_cents", sa.BigInteger(), nullable=True),
        id_column(),
        *timestamps(),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        sa.ForeignKeyConstraint(["market_id"], ["markets.id"]),
        sa.ForeignKeyConstraint(["territory_id"], ["territories.id"]),
        sa.ForeignKeyConstraint(["owner_user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("organization_id", "code", name="uq_campaigns_org_code"),
    )
    _indexes(
        "campaigns",
        "organization_id",
        "market_id",
        "territory_id",
        "owner_user_id",
        "channel",
        "status",
    )

    op.create_table(
        "prospects",
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("campaign_id", sa.Uuid(), nullable=False),
        sa.Column("territory_id", sa.Uuid(), nullable=True),
        sa.Column("assigned_user_id", sa.Uuid(), nullable=True),
        sa.Column("converted_lead_id", sa.Uuid(), nullable=True),
        sa.Column("source_record_key", sa.String(255), nullable=True),
        sa.Column("status", sa.String(40), nullable=False),
        sa.Column("legal_name", sa.String(255), nullable=False),
        sa.Column("phone", sa.String(80), nullable=True),
        sa.Column("normalized_phone", sa.String(40), nullable=True),
        sa.Column("email", sa.String(320), nullable=True),
        sa.Column("normalized_email", sa.String(320), nullable=True),
        sa.Column("street_address", sa.String(255), nullable=True),
        sa.Column("city", sa.String(120), nullable=True),
        sa.Column("state_code", sa.String(2), nullable=True),
        sa.Column("postal_code", sa.String(20), nullable=True),
        sa.Column("normalized_address_key", sa.String(500), nullable=True),
        sa.Column("suppression_status", sa.String(40), nullable=False),
        sa.Column("suppression_checked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_contacted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("source_payload", sa.JSON(), nullable=True),
        id_column(),
        *timestamps(),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        sa.ForeignKeyConstraint(["campaign_id"], ["campaigns.id"]),
        sa.ForeignKeyConstraint(["territory_id"], ["territories.id"]),
        sa.ForeignKeyConstraint(["assigned_user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["converted_lead_id"], ["leads.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "campaign_id",
            "source_record_key",
            name="uq_prospects_campaign_source_record",
        ),
    )
    _indexes(
        "prospects",
        "organization_id",
        "campaign_id",
        "territory_id",
        "assigned_user_id",
        "converted_lead_id",
        "status",
        "normalized_phone",
        "normalized_email",
        "normalized_address_key",
        "suppression_status",
    )


def _indexes(table_name: str, *columns: str) -> None:
    for column in columns:
        op.create_index(f"ix_{table_name}_{column}", table_name, [column])


def downgrade() -> None:
    op.drop_table("prospects")
    op.drop_table("campaigns")
    op.drop_table("territories")
    op.drop_table("markets")
