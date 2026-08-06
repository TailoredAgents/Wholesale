"""Add bank statement import and reconciliation records.

Revision ID: 0063_f6_bank_reconciliation
Revises: 0062_f6_vendor_evidence
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0063_f6_bank_reconciliation"
down_revision: str | None = "0062_f6_vendor_evidence"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "bank_accounts",
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(160), nullable=False),
        sa.Column("institution_name", sa.String(160)),
        sa.Column("account_type", sa.String(40), nullable=False),
        sa.Column("last_four", sa.String(4)),
        sa.Column("currency", sa.String(3), nullable=False),
        sa.Column("status", sa.String(40), nullable=False),
        sa.Column("created_by_user_id", sa.Uuid(), nullable=False),
        sa.Column("notes", sa.String(1000)),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("organization_id", "name", name="uq_bank_accounts_org_name"),
    )
    op.create_index("ix_bank_accounts_organization_id", "bank_accounts", ["organization_id"])
    op.create_index("ix_bank_accounts_status", "bank_accounts", ["status"])
    op.create_index("ix_bank_accounts_org_status", "bank_accounts", ["organization_id", "status"])

    op.create_table(
        "bank_statement_imports",
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("bank_account_id", sa.Uuid(), nullable=False),
        sa.Column("imported_by_user_id", sa.Uuid(), nullable=False),
        sa.Column("file_name", sa.String(255), nullable=False),
        sa.Column("file_sha256", sa.String(64), nullable=False),
        sa.Column("source_format", sa.String(40), nullable=False),
        sa.Column("field_mapping", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(40), nullable=False),
        sa.Column("total_rows", sa.Integer(), nullable=False),
        sa.Column("imported_rows", sa.Integer(), nullable=False),
        sa.Column("invalid_rows", sa.Integer(), nullable=False),
        sa.Column("duplicate_rows", sa.Integer(), nullable=False),
        sa.Column("statement_start_on", sa.Date()),
        sa.Column("statement_end_on", sa.Date()),
        sa.Column("opening_balance_cents", sa.BigInteger()),
        sa.Column("closing_balance_cents", sa.BigInteger()),
        sa.Column("file_data", sa.LargeBinary()),
        sa.Column("storage_provider", sa.String(40), server_default="database", nullable=False),
        sa.Column("storage_key", sa.String(1000)),
        sa.Column(
            "malware_scan_status", sa.String(40), server_default="not_configured", nullable=False
        ),
        sa.Column("retention_until", sa.DateTime(timezone=True)),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        sa.ForeignKeyConstraint(["bank_account_id"], ["bank_accounts.id"]),
        sa.ForeignKeyConstraint(["imported_by_user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "organization_id",
            "bank_account_id",
            "file_sha256",
            name="uq_bank_statement_imports_account_file",
        ),
    )
    op.create_index(
        "ix_bank_statement_imports_organization_id", "bank_statement_imports", ["organization_id"]
    )
    op.create_index(
        "ix_bank_statement_imports_bank_account_id", "bank_statement_imports", ["bank_account_id"]
    )
    op.create_index("ix_bank_statement_imports_status", "bank_statement_imports", ["status"])
    op.create_index(
        "ix_bank_statement_imports_org_status",
        "bank_statement_imports",
        ["organization_id", "status"],
    )

    op.create_table(
        "bank_transactions",
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("bank_account_id", sa.Uuid(), nullable=False),
        sa.Column("statement_import_id", sa.Uuid(), nullable=False),
        sa.Column("row_number", sa.Integer(), nullable=False),
        sa.Column("external_id", sa.String(255)),
        sa.Column("occurred_on", sa.Date(), nullable=False),
        sa.Column("posted_on", sa.Date()),
        sa.Column("description", sa.String(1000), nullable=False),
        sa.Column("amount_cents", sa.BigInteger(), nullable=False),
        sa.Column("balance_cents", sa.BigInteger()),
        sa.Column("fingerprint", sa.String(64), nullable=False),
        sa.Column("status", sa.String(40), nullable=False),
        sa.Column("notes", sa.String(1000)),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint("amount_cents <> 0", name="ck_bank_transactions_nonzero_amount"),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        sa.ForeignKeyConstraint(["bank_account_id"], ["bank_accounts.id"]),
        sa.ForeignKeyConstraint(["statement_import_id"], ["bank_statement_imports.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "organization_id",
            "bank_account_id",
            "fingerprint",
            name="uq_bank_transactions_account_fingerprint",
        ),
    )
    op.create_index(
        "ix_bank_transactions_organization_id", "bank_transactions", ["organization_id"]
    )
    op.create_index(
        "ix_bank_transactions_bank_account_id", "bank_transactions", ["bank_account_id"]
    )
    op.create_index(
        "ix_bank_transactions_statement_import_id", "bank_transactions", ["statement_import_id"]
    )
    op.create_index("ix_bank_transactions_occurred_on", "bank_transactions", ["occurred_on"])
    op.create_index("ix_bank_transactions_status", "bank_transactions", ["status"])
    op.create_index(
        "ix_bank_transactions_org_status", "bank_transactions", ["organization_id", "status"]
    )

    op.create_table(
        "bank_transaction_matches",
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("bank_transaction_id", sa.Uuid(), nullable=False),
        sa.Column("journal_entry_id", sa.Uuid(), nullable=False),
        sa.Column("match_type", sa.String(40), nullable=False),
        sa.Column("matched_by_user_id", sa.Uuid(), nullable=False),
        sa.Column("notes", sa.String(1000)),
        sa.Column("matched_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        sa.ForeignKeyConstraint(
            ["bank_transaction_id"], ["bank_transactions.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["journal_entry_id"], ["journal_entries.id"]),
        sa.ForeignKeyConstraint(["matched_by_user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("bank_transaction_id", name="uq_bank_transaction_matches_transaction"),
    )
    op.create_index(
        "ix_bank_transaction_matches_organization_id",
        "bank_transaction_matches",
        ["organization_id"],
    )
    op.create_index(
        "ix_bank_transaction_matches_bank_transaction_id",
        "bank_transaction_matches",
        ["bank_transaction_id"],
    )
    op.create_index(
        "ix_bank_transaction_matches_journal_entry_id",
        "bank_transaction_matches",
        ["journal_entry_id"],
    )

    op.create_table(
        "bank_reconciliations",
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("bank_account_id", sa.Uuid(), nullable=False),
        sa.Column("statement_import_id", sa.Uuid()),
        sa.Column("statement_start_on", sa.Date(), nullable=False),
        sa.Column("statement_end_on", sa.Date(), nullable=False),
        sa.Column("opening_balance_cents", sa.BigInteger(), nullable=False),
        sa.Column("closing_balance_cents", sa.BigInteger(), nullable=False),
        sa.Column("calculated_closing_balance_cents", sa.BigInteger(), nullable=False),
        sa.Column("difference_cents", sa.BigInteger(), nullable=False),
        sa.Column("status", sa.String(40), nullable=False),
        sa.Column("prepared_by_user_id", sa.Uuid(), nullable=False),
        sa.Column("approved_by_user_id", sa.Uuid()),
        sa.Column("approved_at", sa.DateTime(timezone=True)),
        sa.Column("notes", sa.String(1000)),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        sa.ForeignKeyConstraint(["bank_account_id"], ["bank_accounts.id"]),
        sa.ForeignKeyConstraint(["statement_import_id"], ["bank_statement_imports.id"]),
        sa.ForeignKeyConstraint(["prepared_by_user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["approved_by_user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "organization_id",
            "bank_account_id",
            "statement_end_on",
            name="uq_bank_reconciliations_account_end",
        ),
    )
    op.create_index(
        "ix_bank_reconciliations_organization_id", "bank_reconciliations", ["organization_id"]
    )
    op.create_index(
        "ix_bank_reconciliations_bank_account_id", "bank_reconciliations", ["bank_account_id"]
    )
    op.create_index(
        "ix_bank_reconciliations_statement_import_id",
        "bank_reconciliations",
        ["statement_import_id"],
    )
    op.create_index("ix_bank_reconciliations_status", "bank_reconciliations", ["status"])


def downgrade() -> None:
    op.drop_table("bank_reconciliations")
    op.drop_table("bank_transaction_matches")
    op.drop_table("bank_transactions")
    op.drop_table("bank_statement_imports")
    op.drop_table("bank_accounts")
