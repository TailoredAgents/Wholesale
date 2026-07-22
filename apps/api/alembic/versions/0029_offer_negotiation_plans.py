"""Offer negotiation plans and accountable approval decisions.

Revision ID: 0029_offer_negotiation_plans
Revises: 0028_repair_estimates
Create Date: 2026-07-21 00:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0029_offer_negotiation_plans"
down_revision: str | None = "0028_repair_estimates"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "approval_requests",
        sa.Column("decided_by_user_id", sa.Uuid(), nullable=True),
    )
    op.create_foreign_key(
        "fk_approval_requests_decided_by_user_id_users",
        "approval_requests",
        "users",
        ["decided_by_user_id"],
        ["id"],
    )
    op.create_table(
        "offer_negotiation_plans",
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("lead_id", sa.Uuid(), nullable=False),
        sa.Column("property_id", sa.Uuid(), nullable=False),
        sa.Column("underwriting_version_id", sa.Uuid(), nullable=False),
        sa.Column("market_analysis_id", sa.Uuid(), nullable=True),
        sa.Column("approval_request_id", sa.Uuid(), nullable=True),
        sa.Column("created_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("status", sa.String(80), nullable=False),
        sa.Column("seller_asking_price_cents", sa.BigInteger(), nullable=True),
        sa.Column("arv_low_cents", sa.BigInteger(), nullable=True),
        sa.Column("arv_point_cents", sa.BigInteger(), nullable=True),
        sa.Column("arv_high_cents", sa.BigInteger(), nullable=True),
        sa.Column("total_rehab_cents", sa.BigInteger(), nullable=True),
        sa.Column("disposition_cents", sa.BigInteger(), nullable=True),
        sa.Column("opening_offer_cents", sa.BigInteger(), nullable=False),
        sa.Column("target_contract_cents", sa.BigInteger(), nullable=False),
        sa.Column("stretch_contract_cents", sa.BigInteger(), nullable=False),
        sa.Column("seller_ceiling_cents", sa.BigInteger(), nullable=False),
        sa.Column("seller_context", sa.String(2000), nullable=True),
        sa.Column("rationale", sa.String(2000), nullable=False),
        sa.Column("source_snapshot", sa.JSON(), nullable=False),
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
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        sa.ForeignKeyConstraint(["lead_id"], ["leads.id"]),
        sa.ForeignKeyConstraint(["property_id"], ["properties.id"]),
        sa.ForeignKeyConstraint(["underwriting_version_id"], ["underwriting_versions.id"]),
        sa.ForeignKeyConstraint(["market_analysis_id"], ["underwriting_market_analyses.id"]),
        sa.ForeignKeyConstraint(["approval_request_id"], ["approval_requests.id"]),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    for column in (
        "organization_id",
        "lead_id",
        "property_id",
        "underwriting_version_id",
        "market_analysis_id",
        "approval_request_id",
        "status",
    ):
        op.create_index(
            f"ix_offer_negotiation_plans_{column}",
            "offer_negotiation_plans",
            [column],
        )


def downgrade() -> None:
    op.drop_table("offer_negotiation_plans")
    op.drop_constraint(
        "fk_approval_requests_decided_by_user_id_users",
        "approval_requests",
        type_="foreignkey",
    )
    op.drop_column("approval_requests", "decided_by_user_id")
