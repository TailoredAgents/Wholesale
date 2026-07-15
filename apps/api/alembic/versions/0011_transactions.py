"""transactions

Revision ID: 0011_transactions
Revises: 0010_underwriting_versions
Create Date: 2026-07-15 00:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0011_transactions"
down_revision: str | None = "0010_underwriting_versions"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "transactions",
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("deal_id", sa.Uuid(), nullable=False),
        sa.Column("lead_id", sa.Uuid(), nullable=False),
        sa.Column("property_id", sa.Uuid(), nullable=False),
        sa.Column("contact_id", sa.Uuid(), nullable=False),
        sa.Column("owner_user_id", sa.Uuid(), nullable=True),
        sa.Column("status", sa.String(length=80), nullable=False),
        sa.Column("contract_type", sa.String(length=120), nullable=False),
        sa.Column("purchase_price_cents", sa.BigInteger(), nullable=False),
        sa.Column("assignment_fee_cents", sa.BigInteger(), nullable=True),
        sa.Column("earnest_money_cents", sa.BigInteger(), nullable=True),
        sa.Column("title_company", sa.String(length=255), nullable=True),
        sa.Column("closing_date", sa.DateTime(timezone=True), nullable=True),
        sa.Column("inspection_period_days", sa.Integer(), nullable=True),
        sa.Column("contract_sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("contract_executed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("notes", sa.String(length=2000), nullable=True),
        sa.Column("metadata", sa.JSON(), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            onupdate=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(["contact_id"], ["contacts.id"]),
        sa.ForeignKeyConstraint(["deal_id"], ["deals.id"]),
        sa.ForeignKeyConstraint(["lead_id"], ["leads.id"]),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        sa.ForeignKeyConstraint(["owner_user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["property_id"], ["properties.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_transactions_organization_id", "transactions", ["organization_id"])
    op.create_index("ix_transactions_deal_id", "transactions", ["deal_id"])
    op.create_index("ix_transactions_lead_id", "transactions", ["lead_id"])
    op.create_index("ix_transactions_property_id", "transactions", ["property_id"])
    op.create_index("ix_transactions_contact_id", "transactions", ["contact_id"])

    op.create_table(
        "transaction_checklist_items",
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("transaction_id", sa.Uuid(), nullable=False),
        sa.Column("responsible_user_id", sa.Uuid(), nullable=True),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("status", sa.String(length=80), nullable=False),
        sa.Column("due_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("sort_order", sa.Integer(), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            onupdate=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        sa.ForeignKeyConstraint(["responsible_user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["transaction_id"], ["transactions.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_transaction_checklist_items_organization_id",
        "transaction_checklist_items",
        ["organization_id"],
    )
    op.create_index(
        "ix_transaction_checklist_items_transaction_id",
        "transaction_checklist_items",
        ["transaction_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_transaction_checklist_items_transaction_id",
        table_name="transaction_checklist_items",
    )
    op.drop_index(
        "ix_transaction_checklist_items_organization_id",
        table_name="transaction_checklist_items",
    )
    op.drop_table("transaction_checklist_items")
    op.drop_index("ix_transactions_contact_id", table_name="transactions")
    op.drop_index("ix_transactions_property_id", table_name="transactions")
    op.drop_index("ix_transactions_lead_id", table_name="transactions")
    op.drop_index("ix_transactions_deal_id", table_name="transactions")
    op.drop_index("ix_transactions_organization_id", table_name="transactions")
    op.drop_table("transactions")
