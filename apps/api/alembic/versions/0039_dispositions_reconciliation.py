"""Phase 9 buyer disposition and deal reconciliation.

Revision ID: 0039_dispositions_reconciliation
Revises: 0038_transaction_coordination
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0039_dispositions_reconciliation"
down_revision: str | None = "0038_transaction_coordination"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


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
    op.add_column(
        "buyers",
        sa.Column(
            "reliability_score_basis_points", sa.Integer(), server_default="5000", nullable=False
        ),
    )
    op.add_column(
        "buyers", sa.Column("completed_deals", sa.Integer(), server_default="0", nullable=False)
    )
    op.add_column(
        "buyers", sa.Column("failed_deals", sa.Integer(), server_default="0", nullable=False)
    )
    op.add_column(
        "buyers", sa.Column("proof_of_funds_expires_at", sa.DateTime(timezone=True), nullable=True)
    )

    op.create_table(
        "buyer_proof_documents",
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("buyer_id", sa.Uuid(), nullable=False),
        sa.Column("uploaded_by_user_id", sa.Uuid(), nullable=False),
        sa.Column("status", sa.String(40), nullable=False),
        sa.Column("institution_name", sa.String(255), nullable=True),
        sa.Column("verified_amount_cents", sa.BigInteger(), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("file_name", sa.String(255), nullable=False),
        sa.Column("content_type", sa.String(120), nullable=False),
        sa.Column("file_size", sa.Integer(), nullable=False),
        sa.Column("sha256", sa.String(64), nullable=False),
        sa.Column("file_data", sa.LargeBinary(), nullable=False),
        sa.Column("notes", sa.String(1000), nullable=True),
        sa.Column("id", sa.Uuid(), primary_key=True),
        *timestamps(),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        sa.ForeignKeyConstraint(["buyer_id"], ["buyers.id"]),
        sa.ForeignKeyConstraint(["uploaded_by_user_id"], ["users.id"]),
    )
    op.create_index("ix_buyer_proof_documents_buyer_id", "buyer_proof_documents", ["buyer_id"])

    op.create_table(
        "disposition_cases",
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("transaction_id", sa.Uuid(), nullable=False),
        sa.Column("deal_id", sa.Uuid(), nullable=False),
        sa.Column("lead_id", sa.Uuid(), nullable=False),
        sa.Column("property_id", sa.Uuid(), nullable=False),
        sa.Column("owner_user_id", sa.Uuid(), nullable=False),
        sa.Column("compensation_plan_version_id", sa.Uuid(), nullable=False),
        sa.Column("disposition_operating_mode_id", sa.Uuid(), nullable=False),
        sa.Column("status", sa.String(40), nullable=False),
        sa.Column("strategy", sa.String(40), nullable=False),
        sa.Column("asking_price_cents", sa.BigInteger(), nullable=False),
        sa.Column("minimum_acceptable_cents", sa.BigInteger(), nullable=False),
        sa.Column("package_status", sa.String(40), nullable=False),
        sa.Column("package_snapshot", sa.JSON(), nullable=False),
        sa.Column("package_approved_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("package_approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("selected_buyer_id", sa.Uuid(), nullable=True),
        sa.Column("backup_buyer_id", sa.Uuid(), nullable=True),
        sa.Column("selection_approved_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("selection_approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("notes", sa.String(2000), nullable=True),
        sa.Column("id", sa.Uuid(), primary_key=True),
        *timestamps(),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        sa.ForeignKeyConstraint(["transaction_id"], ["transactions.id"]),
        sa.ForeignKeyConstraint(["deal_id"], ["deals.id"]),
        sa.ForeignKeyConstraint(["lead_id"], ["leads.id"]),
        sa.ForeignKeyConstraint(["property_id"], ["properties.id"]),
        sa.ForeignKeyConstraint(["owner_user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(
            ["compensation_plan_version_id"], ["compensation_plan_versions.id"]
        ),
        sa.ForeignKeyConstraint(
            ["disposition_operating_mode_id"], ["disposition_operating_modes.id"]
        ),
        sa.ForeignKeyConstraint(["package_approved_by_user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["selected_buyer_id"], ["buyers.id"]),
        sa.ForeignKeyConstraint(["backup_buyer_id"], ["buyers.id"]),
        sa.ForeignKeyConstraint(["selection_approved_by_user_id"], ["users.id"]),
        sa.UniqueConstraint("transaction_id", name="uq_disposition_cases_transaction"),
    )
    for column in ("organization_id", "transaction_id", "lead_id", "status"):
        op.create_index(f"ix_disposition_cases_{column}", "disposition_cases", [column])

    op.create_table(
        "disposition_matches",
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("disposition_case_id", sa.Uuid(), nullable=False),
        sa.Column("buyer_id", sa.Uuid(), nullable=False),
        sa.Column("score_basis_points", sa.Integer(), nullable=False),
        sa.Column("score_components", sa.JSON(), nullable=False),
        sa.Column("qualification_status", sa.String(40), nullable=False),
        sa.Column("recipient_status", sa.String(40), nullable=False),
        sa.Column("rank", sa.Integer(), nullable=False),
        sa.Column("id", sa.Uuid(), primary_key=True),
        *timestamps(),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        sa.ForeignKeyConstraint(
            ["disposition_case_id"], ["disposition_cases.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["buyer_id"], ["buyers.id"]),
        sa.UniqueConstraint(
            "disposition_case_id", "buyer_id", name="uq_disposition_matches_case_buyer"
        ),
    )
    op.create_index(
        "ix_disposition_matches_case_id", "disposition_matches", ["disposition_case_id"]
    )

    op.create_table(
        "disposition_campaigns",
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("disposition_case_id", sa.Uuid(), nullable=False),
        sa.Column("created_by_user_id", sa.Uuid(), nullable=False),
        sa.Column("status", sa.String(40), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("channel", sa.String(40), nullable=False),
        sa.Column("recipient_count", sa.Integer(), nullable=False),
        sa.Column("released_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.Uuid(), primary_key=True),
        *timestamps(),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        sa.ForeignKeyConstraint(
            ["disposition_case_id"], ["disposition_cases.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"]),
    )

    op.create_table(
        "buyer_engagements",
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("disposition_case_id", sa.Uuid(), nullable=False),
        sa.Column("buyer_id", sa.Uuid(), nullable=False),
        sa.Column("actor_user_id", sa.Uuid(), nullable=False),
        sa.Column("engagement_type", sa.String(40), nullable=False),
        sa.Column("status", sa.String(40), nullable=False),
        sa.Column("scheduled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("notes", sa.String(1000), nullable=True),
        sa.Column("id", sa.Uuid(), primary_key=True),
        *timestamps(),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        sa.ForeignKeyConstraint(
            ["disposition_case_id"], ["disposition_cases.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["buyer_id"], ["buyers.id"]),
        sa.ForeignKeyConstraint(["actor_user_id"], ["users.id"]),
    )

    op.add_column("buyer_offers", sa.Column("disposition_case_id", sa.Uuid(), nullable=True))
    op.add_column("buyer_offers", sa.Column("proof_document_id", sa.Uuid(), nullable=True))
    op.add_column(
        "buyer_offers", sa.Column("deposit_due_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column(
        "buyer_offers", sa.Column("deposit_received_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column(
        "buyer_offers", sa.Column("selected_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.create_foreign_key(
        "fk_buyer_offers_disposition_case",
        "buyer_offers",
        "disposition_cases",
        ["disposition_case_id"],
        ["id"],
    )
    op.create_foreign_key(
        "fk_buyer_offers_proof_document",
        "buyer_offers",
        "buyer_proof_documents",
        ["proof_document_id"],
        ["id"],
    )

    op.create_table(
        "deal_reconciliations",
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("transaction_id", sa.Uuid(), nullable=False),
        sa.Column("disposition_case_id", sa.Uuid(), nullable=False),
        sa.Column("compensation_plan_version_id", sa.Uuid(), nullable=False),
        sa.Column("disposition_operating_mode_id", sa.Uuid(), nullable=False),
        sa.Column("created_by_user_id", sa.Uuid(), nullable=False),
        sa.Column("approved_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("status", sa.String(40), nullable=False),
        sa.Column("gross_revenue_cents", sa.BigInteger(), nullable=False),
        sa.Column("acquisition_reserve_cents", sa.BigInteger(), nullable=False),
        sa.Column("deal_deductions_cents", sa.BigInteger(), nullable=False),
        sa.Column("adjusted_deal_margin_cents", sa.BigInteger(), nullable=False),
        sa.Column("total_compensation_cents", sa.BigInteger(), nullable=False),
        sa.Column("company_profit_cents", sa.BigInteger(), nullable=False),
        sa.Column("company_margin_basis_points", sa.Integer(), nullable=False),
        sa.Column("target_margin_basis_points", sa.Integer(), nullable=False),
        sa.Column("snapshot", sa.JSON(), nullable=False),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("notes", sa.String(2000), nullable=True),
        sa.Column("id", sa.Uuid(), primary_key=True),
        *timestamps(),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        sa.ForeignKeyConstraint(["transaction_id"], ["transactions.id"]),
        sa.ForeignKeyConstraint(["disposition_case_id"], ["disposition_cases.id"]),
        sa.ForeignKeyConstraint(
            ["compensation_plan_version_id"], ["compensation_plan_versions.id"]
        ),
        sa.ForeignKeyConstraint(
            ["disposition_operating_mode_id"], ["disposition_operating_modes.id"]
        ),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["approved_by_user_id"], ["users.id"]),
        sa.UniqueConstraint("transaction_id", name="uq_deal_reconciliations_transaction"),
    )

    op.create_table(
        "deal_payouts",
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("deal_reconciliation_id", sa.Uuid(), nullable=False),
        sa.Column("role_credit_id", sa.Uuid(), nullable=True),
        sa.Column("user_id", sa.Uuid(), nullable=True),
        sa.Column("role_key", sa.String(120), nullable=False),
        sa.Column("credit_basis_points", sa.Integer(), nullable=False),
        sa.Column("amount_cents", sa.BigInteger(), nullable=False),
        sa.Column("status", sa.String(40), nullable=False),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("paid_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.Uuid(), primary_key=True),
        *timestamps(),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        sa.ForeignKeyConstraint(
            ["deal_reconciliation_id"], ["deal_reconciliations.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["role_credit_id"], ["role_credits.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
    )


def downgrade() -> None:
    op.drop_table("deal_payouts")
    op.drop_table("deal_reconciliations")
    op.drop_constraint("fk_buyer_offers_proof_document", "buyer_offers", type_="foreignkey")
    op.drop_constraint("fk_buyer_offers_disposition_case", "buyer_offers", type_="foreignkey")
    for column in (
        "selected_at",
        "deposit_received_at",
        "deposit_due_at",
        "proof_document_id",
        "disposition_case_id",
    ):
        op.drop_column("buyer_offers", column)
    op.drop_table("buyer_engagements")
    op.drop_table("disposition_campaigns")
    op.drop_table("disposition_matches")
    op.drop_table("disposition_cases")
    op.drop_table("buyer_proof_documents")
    for column in (
        "proof_of_funds_expires_at",
        "failed_deals",
        "completed_deals",
        "reliability_score_basis_points",
    ):
        op.drop_column("buyers", column)
