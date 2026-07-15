"""finance compensation

Revision ID: 0013_finance_compensation
Revises: 0012_buyer_disposition
Create Date: 2026-07-15 00:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0013_finance_compensation"
down_revision: str | None = "0012_buyer_disposition"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "revenue_records",
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("lead_id", sa.Uuid(), nullable=True),
        sa.Column("deal_id", sa.Uuid(), nullable=True),
        sa.Column("transaction_id", sa.Uuid(), nullable=True),
        sa.Column("source", sa.String(length=120), nullable=False),
        sa.Column("status", sa.String(length=80), nullable=False),
        sa.Column("amount_cents", sa.BigInteger(), nullable=False),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("notes", sa.String(length=2000), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            onupdate=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(["deal_id"], ["deals.id"]),
        sa.ForeignKeyConstraint(["lead_id"], ["leads.id"]),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        sa.ForeignKeyConstraint(["transaction_id"], ["transactions.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_revenue_records_organization_id", "revenue_records", ["organization_id"])
    op.create_index("ix_revenue_records_lead_id", "revenue_records", ["lead_id"])
    op.create_index("ix_revenue_records_deal_id", "revenue_records", ["deal_id"])
    op.create_index(
        "ix_revenue_records_transaction_id", "revenue_records", ["transaction_id"]
    )

    op.create_table(
        "deal_deductions",
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("lead_id", sa.Uuid(), nullable=True),
        sa.Column("deal_id", sa.Uuid(), nullable=True),
        sa.Column("transaction_id", sa.Uuid(), nullable=True),
        sa.Column("category", sa.String(length=120), nullable=False),
        sa.Column("amount_cents", sa.BigInteger(), nullable=False),
        sa.Column("incurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("notes", sa.String(length=2000), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            onupdate=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(["deal_id"], ["deals.id"]),
        sa.ForeignKeyConstraint(["lead_id"], ["leads.id"]),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        sa.ForeignKeyConstraint(["transaction_id"], ["transactions.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_deal_deductions_organization_id", "deal_deductions", ["organization_id"])
    op.create_index("ix_deal_deductions_lead_id", "deal_deductions", ["lead_id"])
    op.create_index("ix_deal_deductions_deal_id", "deal_deductions", ["deal_id"])
    op.create_index(
        "ix_deal_deductions_transaction_id", "deal_deductions", ["transaction_id"]
    )

    op.create_table(
        "compensation_rules",
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("role_key", sa.String(length=120), nullable=False),
        sa.Column("basis_points", sa.Integer(), nullable=False),
        sa.Column("applies_to", sa.String(length=120), nullable=False),
        sa.Column("effective_start_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("effective_end_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default="true", nullable=False),
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
    op.create_index(
        "ix_compensation_rules_organization_id", "compensation_rules", ["organization_id"]
    )

    op.create_table(
        "compensation_calculations",
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("revenue_record_id", sa.Uuid(), nullable=False),
        sa.Column("compensation_rule_id", sa.Uuid(), nullable=False),
        sa.Column("role_key", sa.String(length=120), nullable=False),
        sa.Column("basis_amount_cents", sa.BigInteger(), nullable=False),
        sa.Column("basis_points", sa.Integer(), nullable=False),
        sa.Column("calculated_amount_cents", sa.BigInteger(), nullable=False),
        sa.Column("status", sa.String(length=80), nullable=False),
        sa.Column("notes", sa.String(length=2000), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            onupdate=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(["compensation_rule_id"], ["compensation_rules.id"]),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        sa.ForeignKeyConstraint(["revenue_record_id"], ["revenue_records.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_compensation_calculations_organization_id",
        "compensation_calculations",
        ["organization_id"],
    )
    op.create_index(
        "ix_compensation_calculations_revenue_record_id",
        "compensation_calculations",
        ["revenue_record_id"],
    )
    op.create_index(
        "ix_compensation_calculations_compensation_rule_id",
        "compensation_calculations",
        ["compensation_rule_id"],
    )

    op.create_table(
        "marketing_spend",
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("source", sa.String(length=120), nullable=False),
        sa.Column("campaign", sa.String(length=255), nullable=True),
        sa.Column("amount_cents", sa.BigInteger(), nullable=False),
        sa.Column("spend_month_at", sa.DateTime(timezone=True), nullable=False),
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
    op.create_index("ix_marketing_spend_organization_id", "marketing_spend", ["organization_id"])


def downgrade() -> None:
    op.drop_index("ix_marketing_spend_organization_id", table_name="marketing_spend")
    op.drop_table("marketing_spend")
    op.drop_index(
        "ix_compensation_calculations_compensation_rule_id",
        table_name="compensation_calculations",
    )
    op.drop_index(
        "ix_compensation_calculations_revenue_record_id",
        table_name="compensation_calculations",
    )
    op.drop_index(
        "ix_compensation_calculations_organization_id",
        table_name="compensation_calculations",
    )
    op.drop_table("compensation_calculations")
    op.drop_index("ix_compensation_rules_organization_id", table_name="compensation_rules")
    op.drop_table("compensation_rules")
    op.drop_index("ix_deal_deductions_transaction_id", table_name="deal_deductions")
    op.drop_index("ix_deal_deductions_deal_id", table_name="deal_deductions")
    op.drop_index("ix_deal_deductions_lead_id", table_name="deal_deductions")
    op.drop_index("ix_deal_deductions_organization_id", table_name="deal_deductions")
    op.drop_table("deal_deductions")
    op.drop_index("ix_revenue_records_transaction_id", table_name="revenue_records")
    op.drop_index("ix_revenue_records_deal_id", table_name="revenue_records")
    op.drop_index("ix_revenue_records_lead_id", table_name="revenue_records")
    op.drop_index("ix_revenue_records_organization_id", table_name="revenue_records")
    op.drop_table("revenue_records")
