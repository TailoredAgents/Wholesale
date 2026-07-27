"""Add operational posting rules and payment-state records.

Revision ID: 0061_f6_operational_posting
Revises: 0060_f6_double_entry
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0061_f6_operational_posting"
down_revision: str | None = "0060_f6_double_entry"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "deal_payouts",
        sa.Column("due_at", sa.DateTime(timezone=True)),
    )
    op.add_column(
        "deal_payouts",
        sa.Column("payment_reference", sa.String(255)),
    )
    op.add_column(
        "deal_payouts",
        sa.Column(
            "evidence_references",
            sa.JSON(),
            server_default="[]",
            nullable=False,
        ),
    )

    op.create_table(
        "accounting_posting_rules",
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("rule_key", sa.String(120), nullable=False),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("source_type", sa.String(120), nullable=False),
        sa.Column("trigger_status", sa.String(80), nullable=False),
        sa.Column("strategy_key", sa.String(120), nullable=False),
        sa.Column("debit_account_key", sa.String(120), nullable=False),
        sa.Column("credit_account_key", sa.String(120), nullable=False),
        sa.Column("evidence_required", sa.Boolean(), nullable=False),
        sa.Column("status", sa.String(40), nullable=False),
        sa.Column("description", sa.String(1000), nullable=False),
        sa.Column("created_by_user_id", sa.Uuid(), nullable=False),
        sa.Column("approved_by_user_id", sa.Uuid()),
        sa.Column("approved_at", sa.DateTime(timezone=True)),
        sa.Column("effective_at", sa.DateTime(timezone=True)),
        sa.Column("superseded_at", sa.DateTime(timezone=True)),
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
        sa.ForeignKeyConstraint(["approved_by_user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "organization_id",
            "rule_key",
            "version_number",
            name="uq_accounting_posting_rules_org_key_version",
        ),
    )
    op.create_index(
        "ix_accounting_posting_rules_organization_id",
        "accounting_posting_rules",
        ["organization_id"],
    )
    op.create_index(
        "ix_accounting_posting_rules_status",
        "accounting_posting_rules",
        ["status"],
    )
    op.create_index(
        "ix_accounting_posting_rules_org_status",
        "accounting_posting_rules",
        ["organization_id", "status"],
    )

    op.create_table(
        "accounting_source_links",
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("posting_rule_id", sa.Uuid(), nullable=False),
        sa.Column("journal_entry_id", sa.Uuid(), nullable=False),
        sa.Column("source_type", sa.String(120), nullable=False),
        sa.Column("source_id", sa.String(255), nullable=False),
        sa.Column("posting_purpose", sa.String(120), nullable=False),
        sa.Column("source_fingerprint", sa.String(64), nullable=False),
        sa.Column("status", sa.String(40), nullable=False),
        sa.Column("exception_detail", sa.String(2000)),
        sa.Column("generated_by_user_id", sa.Uuid(), nullable=False),
        sa.Column("generated_at", sa.DateTime(timezone=True), nullable=False),
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
        sa.ForeignKeyConstraint(["generated_by_user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["journal_entry_id"], ["journal_entries.id"]),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        sa.ForeignKeyConstraint(
            ["posting_rule_id"],
            ["accounting_posting_rules.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "organization_id",
            "source_type",
            "source_id",
            "posting_purpose",
            name="uq_accounting_source_links_source_purpose",
        ),
    )
    op.create_index(
        "ix_accounting_source_links_organization_id",
        "accounting_source_links",
        ["organization_id"],
    )
    op.create_index(
        "ix_accounting_source_links_posting_rule_id",
        "accounting_source_links",
        ["posting_rule_id"],
    )
    op.create_index(
        "ix_accounting_source_links_journal_entry_id",
        "accounting_source_links",
        ["journal_entry_id"],
    )
    op.create_index(
        "ix_accounting_source_links_status",
        "accounting_source_links",
        ["status"],
    )
    op.create_index(
        "ix_accounting_source_links_org_status",
        "accounting_source_links",
        ["organization_id", "status"],
    )

    op.create_table(
        "financial_obligations",
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("obligation_type", sa.String(80), nullable=False),
        sa.Column("direction", sa.String(20), nullable=False),
        sa.Column("counterparty_name", sa.String(255), nullable=False),
        sa.Column("user_id", sa.Uuid()),
        sa.Column("expense_account_key", sa.String(120)),
        sa.Column("amount_cents", sa.BigInteger(), nullable=False),
        sa.Column("status", sa.String(40), nullable=False),
        sa.Column("source_type", sa.String(120)),
        sa.Column("source_id", sa.String(255)),
        sa.Column("due_at", sa.DateTime(timezone=True)),
        sa.Column("approved_by_user_id", sa.Uuid()),
        sa.Column("approved_at", sa.DateTime(timezone=True)),
        sa.Column("paid_at", sa.DateTime(timezone=True)),
        sa.Column("payment_reference", sa.String(255)),
        sa.Column("evidence_references", sa.JSON(), nullable=False),
        sa.Column("notes", sa.String(2000)),
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
        sa.CheckConstraint(
            "amount_cents > 0",
            name="ck_financial_obligations_positive_amount",
        ),
        sa.ForeignKeyConstraint(["approved_by_user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_financial_obligations_organization_id",
        "financial_obligations",
        ["organization_id"],
    )
    op.create_index(
        "ix_financial_obligations_status",
        "financial_obligations",
        ["status"],
    )
    op.create_index(
        "ix_financial_obligations_org_status",
        "financial_obligations",
        ["organization_id", "status"],
    )


def downgrade() -> None:
    op.drop_table("financial_obligations")
    op.drop_table("accounting_source_links")
    op.drop_table("accounting_posting_rules")
    op.drop_column("deal_payouts", "evidence_references")
    op.drop_column("deal_payouts", "payment_reference")
    op.drop_column("deal_payouts", "due_at")
