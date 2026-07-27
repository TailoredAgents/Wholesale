"""Add balanced accounting periods and journals.

Revision ID: 0060_f6_double_entry
Revises: 0059_f6_accounting_tax
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0060_f6_double_entry"
down_revision: str | None = "0059_f6_accounting_tax"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "accounting_periods",
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("accounting_profile_id", sa.Uuid(), nullable=False),
        sa.Column("period_key", sa.String(7), nullable=False),
        sa.Column("period_start_at", sa.Date(), nullable=False),
        sa.Column("period_end_at", sa.Date(), nullable=False),
        sa.Column("status", sa.String(40), nullable=False),
        sa.Column("review_started_by_user_id", sa.Uuid()),
        sa.Column("review_started_at", sa.DateTime(timezone=True)),
        sa.Column("closed_by_user_id", sa.Uuid()),
        sa.Column("closed_at", sa.DateTime(timezone=True)),
        sa.Column("locked_by_user_id", sa.Uuid()),
        sa.Column("locked_at", sa.DateTime(timezone=True)),
        sa.Column("reopened_by_user_id", sa.Uuid()),
        sa.Column("reopened_at", sa.DateTime(timezone=True)),
        sa.Column("reopen_reason", sa.String(2000)),
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
            "period_end_at >= period_start_at",
            name="ck_accounting_period_date_order",
        ),
        sa.ForeignKeyConstraint(
            ["accounting_profile_id"],
            ["accounting_profiles.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(["closed_by_user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["locked_by_user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        sa.ForeignKeyConstraint(["reopened_by_user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["review_started_by_user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "organization_id",
            "period_key",
            name="uq_accounting_periods_org_key",
        ),
    )
    op.create_index(
        "ix_accounting_periods_organization_id",
        "accounting_periods",
        ["organization_id"],
    )
    op.create_index(
        "ix_accounting_periods_accounting_profile_id",
        "accounting_periods",
        ["accounting_profile_id"],
    )
    op.create_index(
        "ix_accounting_periods_status",
        "accounting_periods",
        ["status"],
    )

    op.create_table(
        "journal_entries",
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("accounting_period_id", sa.Uuid(), nullable=False),
        sa.Column("entry_number", sa.String(40), nullable=False),
        sa.Column("entry_date", sa.Date(), nullable=False),
        sa.Column("status", sa.String(40), nullable=False),
        sa.Column("memo", sa.String(1000), nullable=False),
        sa.Column("source_type", sa.String(120), nullable=False),
        sa.Column("source_id", sa.String(255)),
        sa.Column("posting_rule_version", sa.Integer(), nullable=False),
        sa.Column("evidence_references", sa.JSON(), nullable=False),
        sa.Column("idempotency_key", sa.String(255), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False),
        sa.Column("total_debits_cents", sa.BigInteger(), nullable=False),
        sa.Column("total_credits_cents", sa.BigInteger(), nullable=False),
        sa.Column("prepared_by_user_id", sa.Uuid(), nullable=False),
        sa.Column("approved_by_user_id", sa.Uuid()),
        sa.Column("posted_by_user_id", sa.Uuid()),
        sa.Column("reversed_by_user_id", sa.Uuid()),
        sa.Column("reverses_entry_id", sa.Uuid()),
        sa.Column("approved_at", sa.DateTime(timezone=True)),
        sa.Column("posted_at", sa.DateTime(timezone=True)),
        sa.Column("reversed_at", sa.DateTime(timezone=True)),
        sa.Column("review_notes", sa.String(2000)),
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
            "total_debits_cents = total_credits_cents",
            name="ck_journal_entries_balanced_totals",
        ),
        sa.CheckConstraint(
            "total_debits_cents > 0",
            name="ck_journal_entries_positive_total",
        ),
        sa.ForeignKeyConstraint(["accounting_period_id"], ["accounting_periods.id"]),
        sa.ForeignKeyConstraint(["approved_by_user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        sa.ForeignKeyConstraint(["posted_by_user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["prepared_by_user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["reversed_by_user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["reverses_entry_id"], ["journal_entries.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "organization_id",
            "entry_number",
            name="uq_journal_entries_org_number",
        ),
        sa.UniqueConstraint(
            "organization_id",
            "idempotency_key",
            name="uq_journal_entries_org_idempotency",
        ),
        sa.UniqueConstraint(
            "reverses_entry_id",
            name="uq_journal_entries_reverses_entry",
        ),
    )
    op.create_index(
        "ix_journal_entries_organization_id",
        "journal_entries",
        ["organization_id"],
    )
    op.create_index(
        "ix_journal_entries_accounting_period_id",
        "journal_entries",
        ["accounting_period_id"],
    )
    op.create_index(
        "ix_journal_entries_status",
        "journal_entries",
        ["status"],
    )
    op.create_index(
        "ix_journal_entries_reverses_entry_id",
        "journal_entries",
        ["reverses_entry_id"],
    )
    op.create_index(
        "ix_journal_entries_org_status_date",
        "journal_entries",
        ["organization_id", "status", "entry_date"],
    )

    op.create_table(
        "journal_lines",
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("journal_entry_id", sa.Uuid(), nullable=False),
        sa.Column("accounting_account_id", sa.Uuid(), nullable=False),
        sa.Column("line_number", sa.Integer(), nullable=False),
        sa.Column("debit_cents", sa.BigInteger(), server_default="0", nullable=False),
        sa.Column("credit_cents", sa.BigInteger(), server_default="0", nullable=False),
        sa.Column("memo", sa.String(1000)),
        sa.Column("deal_id", sa.Uuid()),
        sa.Column("transaction_id", sa.Uuid()),
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
            "debit_cents >= 0 AND credit_cents >= 0",
            name="ck_journal_lines_nonnegative",
        ),
        sa.CheckConstraint(
            "(debit_cents > 0 AND credit_cents = 0) OR "
            "(credit_cents > 0 AND debit_cents = 0)",
            name="ck_journal_lines_single_side",
        ),
        sa.ForeignKeyConstraint(["accounting_account_id"], ["accounting_accounts.id"]),
        sa.ForeignKeyConstraint(["deal_id"], ["deals.id"]),
        sa.ForeignKeyConstraint(
            ["journal_entry_id"],
            ["journal_entries.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        sa.ForeignKeyConstraint(["transaction_id"], ["transactions.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "journal_entry_id",
            "line_number",
            name="uq_journal_lines_entry_number",
        ),
    )
    op.create_index(
        "ix_journal_lines_organization_id",
        "journal_lines",
        ["organization_id"],
    )
    op.create_index(
        "ix_journal_lines_journal_entry_id",
        "journal_lines",
        ["journal_entry_id"],
    )
    op.create_index(
        "ix_journal_lines_accounting_account_id",
        "journal_lines",
        ["accounting_account_id"],
    )
    op.create_index("ix_journal_lines_deal_id", "journal_lines", ["deal_id"])
    op.create_index(
        "ix_journal_lines_transaction_id",
        "journal_lines",
        ["transaction_id"],
    )


def downgrade() -> None:
    op.drop_table("journal_lines")
    op.drop_table("journal_entries")
    op.drop_table("accounting_periods")
