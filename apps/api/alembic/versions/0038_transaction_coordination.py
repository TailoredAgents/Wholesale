"""Phase 8 transaction coordination and contract controls.

Revision ID: 0038_transaction_coordination
Revises: 0037_offer_concession_governance
Create Date: 2026-07-22 00:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0038_transaction_coordination"
down_revision: str | None = "0037_offer_concession_governance"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("transactions", sa.Column("coordinator_user_id", sa.Uuid(), nullable=True))
    op.add_column(
        "transactions", sa.Column("earnest_money_due_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column(
        "transactions",
        sa.Column("earnest_money_paid_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "transactions",
        sa.Column("due_diligence_deadline", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "transactions", sa.Column("title_opened_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column(
        "transactions", sa.Column("title_cleared_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column(
        "transactions", sa.Column("assignment_deadline", sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column("transactions", sa.Column("funded_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("transactions", sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column(
        "transactions", sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.create_foreign_key(
        "fk_transactions_coordinator_user", "transactions", "users", ["coordinator_user_id"], ["id"]
    )
    op.create_index("ix_transactions_coordinator_user_id", "transactions", ["coordinator_user_id"])

    op.create_table(
        "contract_templates",
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("created_by_user_id", sa.Uuid(), nullable=False),
        sa.Column("approved_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("document_type", sa.String(80), nullable=False),
        sa.Column("state_code", sa.String(2), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(40), nullable=False),
        sa.Column("file_name", sa.String(255), nullable=False),
        sa.Column("content_type", sa.String(120), nullable=False),
        sa.Column("file_size", sa.Integer(), nullable=False),
        sa.Column("sha256", sa.String(64), nullable=False),
        sa.Column("file_data", sa.LargeBinary(), nullable=False),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("retired_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("notes", sa.String(1000), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["approved_by_user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "organization_id",
            "document_type",
            "state_code",
            "version_number",
            name="uq_contract_templates_version",
        ),
    )
    op.create_index(
        "ix_contract_templates_organization_id", "contract_templates", ["organization_id"]
    )
    op.create_index("ix_contract_templates_status", "contract_templates", ["status"])

    op.create_table(
        "contract_packages",
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("transaction_id", sa.Uuid(), nullable=False),
        sa.Column("lead_id", sa.Uuid(), nullable=False),
        sa.Column("property_id", sa.Uuid(), nullable=False),
        sa.Column("template_id", sa.Uuid(), nullable=True),
        sa.Column("created_by_user_id", sa.Uuid(), nullable=False),
        sa.Column("approval_request_id", sa.Uuid(), nullable=True),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(40), nullable=False),
        sa.Column("seller_name", sa.String(255), nullable=False),
        sa.Column("buyer_entity_name", sa.String(255), nullable=False),
        sa.Column("purchase_price_cents", sa.BigInteger(), nullable=False),
        sa.Column("earnest_money_cents", sa.BigInteger(), nullable=True),
        sa.Column("closing_date", sa.DateTime(timezone=True), nullable=True),
        sa.Column("inspection_period_days", sa.Integer(), nullable=True),
        sa.Column("terms_snapshot", sa.JSON(), nullable=False),
        sa.Column("notes", sa.String(2000), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("executed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("voided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        sa.ForeignKeyConstraint(["transaction_id"], ["transactions.id"]),
        sa.ForeignKeyConstraint(["lead_id"], ["leads.id"]),
        sa.ForeignKeyConstraint(["property_id"], ["properties.id"]),
        sa.ForeignKeyConstraint(["template_id"], ["contract_templates.id"]),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["approval_request_id"], ["approval_requests.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "transaction_id", "version_number", name="uq_contract_packages_version"
        ),
    )
    for column in ("organization_id", "transaction_id", "lead_id", "status"):
        op.create_index(f"ix_contract_packages_{column}", "contract_packages", [column])

    op.create_table(
        "transaction_documents",
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("transaction_id", sa.Uuid(), nullable=False),
        sa.Column("contract_package_id", sa.Uuid(), nullable=True),
        sa.Column("uploaded_by_user_id", sa.Uuid(), nullable=False),
        sa.Column("document_type", sa.String(80), nullable=False),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("status", sa.String(40), nullable=False),
        sa.Column("file_name", sa.String(255), nullable=False),
        sa.Column("content_type", sa.String(120), nullable=False),
        sa.Column("file_size", sa.Integer(), nullable=False),
        sa.Column("sha256", sa.String(64), nullable=False),
        sa.Column("file_data", sa.LargeBinary(), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("notes", sa.String(1000), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        sa.ForeignKeyConstraint(["transaction_id"], ["transactions.id"]),
        sa.ForeignKeyConstraint(["contract_package_id"], ["contract_packages.id"]),
        sa.ForeignKeyConstraint(["uploaded_by_user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    for column in ("organization_id", "transaction_id", "contract_package_id", "document_type"):
        op.create_index(f"ix_transaction_documents_{column}", "transaction_documents", [column])

    op.create_table(
        "transaction_parties",
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("transaction_id", sa.Uuid(), nullable=False),
        sa.Column("party_type", sa.String(80), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("company_name", sa.String(255), nullable=True),
        sa.Column("email", sa.String(320), nullable=True),
        sa.Column("phone", sa.String(80), nullable=True),
        sa.Column("address", sa.String(500), nullable=True),
        sa.Column("is_primary", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("notes", sa.String(1000), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        sa.ForeignKeyConstraint(["transaction_id"], ["transactions.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_transaction_parties_organization_id", "transaction_parties", ["organization_id"]
    )
    op.create_index(
        "ix_transaction_parties_transaction_id", "transaction_parties", ["transaction_id"]
    )

    op.create_table(
        "transaction_events",
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("transaction_id", sa.Uuid(), nullable=False),
        sa.Column("lead_id", sa.Uuid(), nullable=False),
        sa.Column("actor_user_id", sa.Uuid(), nullable=True),
        sa.Column("event_type", sa.String(80), nullable=False),
        sa.Column("summary", sa.String(500), nullable=False),
        sa.Column("details", sa.JSON(), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        sa.ForeignKeyConstraint(["transaction_id"], ["transactions.id"]),
        sa.ForeignKeyConstraint(["lead_id"], ["leads.id"]),
        sa.ForeignKeyConstraint(["actor_user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    for column in ("organization_id", "transaction_id", "lead_id", "event_type"):
        op.create_index(f"ix_transaction_events_{column}", "transaction_events", [column])

    op.add_column(
        "transaction_checklist_items", sa.Column("item_key", sa.String(120), nullable=True)
    )
    op.add_column(
        "transaction_checklist_items",
        sa.Column("category", sa.String(80), server_default="operations", nullable=False),
    )
    op.add_column(
        "transaction_checklist_items", sa.Column("description", sa.String(500), nullable=True)
    )
    op.add_column(
        "transaction_checklist_items",
        sa.Column("is_required", sa.Boolean(), server_default="true", nullable=False),
    )
    op.add_column(
        "transaction_checklist_items", sa.Column("dependency_item_id", sa.Uuid(), nullable=True)
    )
    op.add_column(
        "transaction_checklist_items", sa.Column("evidence_document_id", sa.Uuid(), nullable=True)
    )
    op.add_column(
        "transaction_checklist_items", sa.Column("evidence_notes", sa.String(1000), nullable=True)
    )
    op.add_column(
        "transaction_checklist_items",
        sa.Column("escalated_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_checklist_dependency",
        "transaction_checklist_items",
        "transaction_checklist_items",
        ["dependency_item_id"],
        ["id"],
    )
    op.create_foreign_key(
        "fk_checklist_evidence_document",
        "transaction_checklist_items",
        "transaction_documents",
        ["evidence_document_id"],
        ["id"],
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_checklist_evidence_document", "transaction_checklist_items", type_="foreignkey"
    )
    op.drop_constraint("fk_checklist_dependency", "transaction_checklist_items", type_="foreignkey")
    for column in (
        "escalated_at",
        "evidence_notes",
        "evidence_document_id",
        "dependency_item_id",
        "is_required",
        "description",
        "category",
        "item_key",
    ):
        op.drop_column("transaction_checklist_items", column)
    op.drop_table("transaction_events")
    op.drop_table("transaction_parties")
    op.drop_table("transaction_documents")
    op.drop_table("contract_packages")
    op.drop_table("contract_templates")
    op.drop_index("ix_transactions_coordinator_user_id", table_name="transactions")
    op.drop_constraint("fk_transactions_coordinator_user", "transactions", type_="foreignkey")
    for column in (
        "cancelled_at",
        "closed_at",
        "funded_at",
        "assignment_deadline",
        "title_cleared_at",
        "title_opened_at",
        "due_diligence_deadline",
        "earnest_money_paid_at",
        "earnest_money_due_at",
        "coordinator_user_id",
    ):
        op.drop_column("transactions", column)
