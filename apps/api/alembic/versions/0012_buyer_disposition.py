"""buyer disposition

Revision ID: 0012_buyer_disposition
Revises: 0011_transactions
Create Date: 2026-07-15 00:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0012_buyer_disposition"
down_revision: str | None = "0011_transactions"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "buyers",
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("company_name", sa.String(length=255), nullable=True),
        sa.Column("email", sa.String(length=320), nullable=True),
        sa.Column("phone", sa.String(length=80), nullable=True),
        sa.Column("buyer_type", sa.String(length=80), nullable=False),
        sa.Column("status", sa.String(length=80), nullable=False),
        sa.Column("proof_of_funds_status", sa.String(length=80), nullable=False),
        sa.Column("max_purchase_price_cents", sa.BigInteger(), nullable=True),
        sa.Column("notes", sa.String(length=2000), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            onupdate=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_buyers_organization_id", "buyers", ["organization_id"])

    op.create_table(
        "buyer_criteria",
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("buyer_id", sa.Uuid(), nullable=False),
        sa.Column("markets", sa.String(length=500), nullable=True),
        sa.Column("property_types", sa.String(length=500), nullable=True),
        sa.Column("min_price_cents", sa.BigInteger(), nullable=True),
        sa.Column("max_price_cents", sa.BigInteger(), nullable=True),
        sa.Column("rehab_levels", sa.String(length=500), nullable=True),
        sa.Column("notes", sa.String(length=1000), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            onupdate=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(["buyer_id"], ["buyers.id"]),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_buyer_criteria_organization_id", "buyer_criteria", ["organization_id"])
    op.create_index("ix_buyer_criteria_buyer_id", "buyer_criteria", ["buyer_id"])

    op.create_table(
        "buyer_offers",
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("lead_id", sa.Uuid(), nullable=False),
        sa.Column("deal_id", sa.Uuid(), nullable=True),
        sa.Column("buyer_id", sa.Uuid(), nullable=False),
        sa.Column("amount_cents", sa.BigInteger(), nullable=False),
        sa.Column("earnest_money_cents", sa.BigInteger(), nullable=True),
        sa.Column("financing_type", sa.String(length=80), nullable=False),
        sa.Column("status", sa.String(length=80), nullable=False),
        sa.Column("proof_of_funds_received", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("notes", sa.String(length=2000), nullable=True),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            onupdate=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(["buyer_id"], ["buyers.id"]),
        sa.ForeignKeyConstraint(["deal_id"], ["deals.id"]),
        sa.ForeignKeyConstraint(["lead_id"], ["leads.id"]),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_buyer_offers_organization_id", "buyer_offers", ["organization_id"])
    op.create_index("ix_buyer_offers_lead_id", "buyer_offers", ["lead_id"])
    op.create_index("ix_buyer_offers_deal_id", "buyer_offers", ["deal_id"])
    op.create_index("ix_buyer_offers_buyer_id", "buyer_offers", ["buyer_id"])


def downgrade() -> None:
    op.drop_index("ix_buyer_offers_buyer_id", table_name="buyer_offers")
    op.drop_index("ix_buyer_offers_deal_id", table_name="buyer_offers")
    op.drop_index("ix_buyer_offers_lead_id", table_name="buyer_offers")
    op.drop_index("ix_buyer_offers_organization_id", table_name="buyer_offers")
    op.drop_table("buyer_offers")
    op.drop_index("ix_buyer_criteria_buyer_id", table_name="buyer_criteria")
    op.drop_index("ix_buyer_criteria_organization_id", table_name="buyer_criteria")
    op.drop_table("buyer_criteria")
    op.drop_index("ix_buyers_organization_id", table_name="buyers")
    op.drop_table("buyers")
