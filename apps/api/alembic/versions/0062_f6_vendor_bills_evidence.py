"""Add vendor, bill, and private finance evidence records.

Revision ID: 0062_f6_vendor_evidence
Revises: 0061_f6_operational_posting
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0062_f6_vendor_evidence"
down_revision: str | None = "0061_f6_operational_posting"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "vendor_profiles",
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("counterparty_id", sa.Uuid(), nullable=False),
        sa.Column("vendor_type", sa.String(80), nullable=False),
        sa.Column("status", sa.String(40), nullable=False),
        sa.Column("default_expense_account_key", sa.String(120)),
        sa.Column(
            "payment_terms_days",
            sa.Integer(),
            server_default="0",
            nullable=False,
        ),
        sa.Column(
            "tax_reportable",
            sa.Boolean(),
            server_default="false",
            nullable=False,
        ),
        sa.Column("w9_status", sa.String(40), nullable=False),
        sa.Column("w9_requested_at", sa.DateTime(timezone=True)),
        sa.Column("w9_received_at", sa.DateTime(timezone=True)),
        sa.Column("w9_verified_at", sa.DateTime(timezone=True)),
        sa.Column("w9_verified_by_user_id", sa.Uuid()),
        sa.Column("remittance_address", sa.String(1000)),
        sa.Column("created_by_user_id", sa.Uuid(), nullable=False),
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
        sa.ForeignKeyConstraint(
            ["counterparty_id"],
            ["business_counterparties.id"],
        ),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        sa.ForeignKeyConstraint(["w9_verified_by_user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "organization_id",
            "counterparty_id",
            name="uq_vendor_profiles_org_counterparty",
        ),
    )
    op.create_index(
        "ix_vendor_profiles_organization_id",
        "vendor_profiles",
        ["organization_id"],
    )
    op.create_index(
        "ix_vendor_profiles_counterparty_id",
        "vendor_profiles",
        ["counterparty_id"],
    )
    op.create_index("ix_vendor_profiles_status", "vendor_profiles", ["status"])
    op.create_index(
        "ix_vendor_profiles_w9_status",
        "vendor_profiles",
        ["w9_status"],
    )
    op.create_index(
        "ix_vendor_profiles_org_status",
        "vendor_profiles",
        ["organization_id", "status"],
    )

    op.create_table(
        "vendor_bills",
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("vendor_profile_id", sa.Uuid(), nullable=False),
        sa.Column("financial_obligation_id", sa.Uuid()),
        sa.Column("deal_id", sa.Uuid()),
        sa.Column("transaction_id", sa.Uuid()),
        sa.Column("bill_number", sa.String(120), nullable=False),
        sa.Column("status", sa.String(40), nullable=False),
        sa.Column("issue_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("due_at", sa.DateTime(timezone=True)),
        sa.Column("amount_cents", sa.BigInteger(), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False),
        sa.Column("description", sa.String(1000), nullable=False),
        sa.Column("created_by_user_id", sa.Uuid(), nullable=False),
        sa.Column("approved_by_user_id", sa.Uuid()),
        sa.Column("approved_at", sa.DateTime(timezone=True)),
        sa.Column("paid_at", sa.DateTime(timezone=True)),
        sa.Column("payment_reference", sa.String(255)),
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
            name="ck_vendor_bills_positive_amount",
        ),
        sa.ForeignKeyConstraint(["approved_by_user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["deal_id"], ["deals.id"]),
        sa.ForeignKeyConstraint(
            ["financial_obligation_id"],
            ["financial_obligations.id"],
        ),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        sa.ForeignKeyConstraint(["transaction_id"], ["transactions.id"]),
        sa.ForeignKeyConstraint(
            ["vendor_profile_id"],
            ["vendor_profiles.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "organization_id",
            "vendor_profile_id",
            "bill_number",
            name="uq_vendor_bills_org_vendor_number",
        ),
    )
    op.create_index(
        "ix_vendor_bills_organization_id",
        "vendor_bills",
        ["organization_id"],
    )
    op.create_index(
        "ix_vendor_bills_vendor_profile_id",
        "vendor_bills",
        ["vendor_profile_id"],
    )
    op.create_index(
        "ix_vendor_bills_financial_obligation_id",
        "vendor_bills",
        ["financial_obligation_id"],
    )
    op.create_index("ix_vendor_bills_deal_id", "vendor_bills", ["deal_id"])
    op.create_index(
        "ix_vendor_bills_transaction_id",
        "vendor_bills",
        ["transaction_id"],
    )
    op.create_index("ix_vendor_bills_status", "vendor_bills", ["status"])
    op.create_index("ix_vendor_bills_due_at", "vendor_bills", ["due_at"])
    op.create_index(
        "ix_vendor_bills_org_status_due",
        "vendor_bills",
        ["organization_id", "status", "due_at"],
    )

    op.create_table(
        "vendor_bill_lines",
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("vendor_bill_id", sa.Uuid(), nullable=False),
        sa.Column("line_number", sa.Integer(), nullable=False),
        sa.Column("description", sa.String(1000), nullable=False),
        sa.Column("amount_cents", sa.BigInteger(), nullable=False),
        sa.Column("expense_account_key", sa.String(120), nullable=False),
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
            "amount_cents > 0",
            name="ck_vendor_bill_lines_positive_amount",
        ),
        sa.ForeignKeyConstraint(["deal_id"], ["deals.id"]),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        sa.ForeignKeyConstraint(["transaction_id"], ["transactions.id"]),
        sa.ForeignKeyConstraint(
            ["vendor_bill_id"],
            ["vendor_bills.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "vendor_bill_id",
            "line_number",
            name="uq_vendor_bill_lines_bill_number",
        ),
    )
    op.create_index(
        "ix_vendor_bill_lines_organization_id",
        "vendor_bill_lines",
        ["organization_id"],
    )
    op.create_index(
        "ix_vendor_bill_lines_vendor_bill_id",
        "vendor_bill_lines",
        ["vendor_bill_id"],
    )
    op.create_index(
        "ix_vendor_bill_lines_deal_id",
        "vendor_bill_lines",
        ["deal_id"],
    )
    op.create_index(
        "ix_vendor_bill_lines_transaction_id",
        "vendor_bill_lines",
        ["transaction_id"],
    )

    op.create_table(
        "finance_documents",
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("vendor_profile_id", sa.Uuid()),
        sa.Column("vendor_bill_id", sa.Uuid()),
        sa.Column("financial_obligation_id", sa.Uuid()),
        sa.Column("transaction_id", sa.Uuid()),
        sa.Column("uploaded_by_user_id", sa.Uuid(), nullable=False),
        sa.Column("document_type", sa.String(80), nullable=False),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("status", sa.String(40), nullable=False),
        sa.Column(
            "is_sensitive",
            sa.Boolean(),
            server_default="false",
            nullable=False,
        ),
        sa.Column("file_name", sa.String(255), nullable=False),
        sa.Column("content_type", sa.String(120), nullable=False),
        sa.Column("file_size", sa.Integer(), nullable=False),
        sa.Column("sha256", sa.String(64), nullable=False),
        sa.Column("file_data", sa.LargeBinary()),
        sa.Column(
            "storage_provider",
            sa.String(40),
            server_default="database",
            nullable=False,
        ),
        sa.Column("storage_key", sa.String(1000)),
        sa.Column(
            "malware_scan_status",
            sa.String(40),
            server_default="not_configured",
            nullable=False,
        ),
        sa.Column("retention_until", sa.DateTime(timezone=True)),
        sa.Column("deleted_at", sa.DateTime(timezone=True)),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("notes", sa.String(1000)),
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
        sa.ForeignKeyConstraint(
            ["financial_obligation_id"],
            ["financial_obligations.id"],
        ),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        sa.ForeignKeyConstraint(["transaction_id"], ["transactions.id"]),
        sa.ForeignKeyConstraint(["uploaded_by_user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["vendor_bill_id"], ["vendor_bills.id"]),
        sa.ForeignKeyConstraint(
            ["vendor_profile_id"],
            ["vendor_profiles.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_finance_documents_organization_id",
        "finance_documents",
        ["organization_id"],
    )
    op.create_index(
        "ix_finance_documents_vendor_profile_id",
        "finance_documents",
        ["vendor_profile_id"],
    )
    op.create_index(
        "ix_finance_documents_vendor_bill_id",
        "finance_documents",
        ["vendor_bill_id"],
    )
    op.create_index(
        "ix_finance_documents_financial_obligation_id",
        "finance_documents",
        ["financial_obligation_id"],
    )
    op.create_index(
        "ix_finance_documents_transaction_id",
        "finance_documents",
        ["transaction_id"],
    )
    op.create_index(
        "ix_finance_documents_document_type",
        "finance_documents",
        ["document_type"],
    )
    op.create_index(
        "ix_finance_documents_status",
        "finance_documents",
        ["status"],
    )
    op.create_index(
        "ix_finance_documents_org_type",
        "finance_documents",
        ["organization_id", "document_type", "status"],
    )


def downgrade() -> None:
    op.drop_table("finance_documents")
    op.drop_table("vendor_bill_lines")
    op.drop_table("vendor_bills")
    op.drop_table("vendor_profiles")
