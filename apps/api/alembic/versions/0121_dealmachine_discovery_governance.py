"""Add governed DealMachine discovery tiers and credit attribution.

Revision ID: 0121_dealmachine_buyer_tiers
Revises: 0120_disposition_copilot_eval
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0121_dealmachine_buyer_tiers"
down_revision: str | None = "0120_disposition_copilot_eval"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "buyer_discovery_runs",
        sa.Column("search_tier", sa.String(length=40), nullable=True),
    )
    op.add_column(
        "buyer_discovery_runs",
        sa.Column("request_fingerprint", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "buyer_discovery_runs",
        sa.Column("target_candidate_count", sa.Integer(), nullable=True),
    )
    op.add_column(
        "buyer_discovery_runs",
        sa.Column("estimated_credit_cap", sa.Integer(), nullable=True),
    )
    op.add_column(
        "buyer_discovery_runs",
        sa.Column("estimated_credits", sa.Integer(), nullable=True),
    )
    op.add_column(
        "buyer_discovery_runs",
        sa.Column("actual_credits", sa.Integer(), nullable=True),
    )
    op.create_index(
        "ix_buyer_discovery_runs_org_case_tier_created",
        "buyer_discovery_runs",
        ["organization_id", "disposition_case_id", "search_tier", "created_at"],
    )
    op.create_index(
        "ix_buyer_discovery_runs_org_fingerprint_created",
        "buyer_discovery_runs",
        ["organization_id", "request_fingerprint", "created_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_buyer_discovery_runs_org_fingerprint_created",
        table_name="buyer_discovery_runs",
    )
    op.drop_index(
        "ix_buyer_discovery_runs_org_case_tier_created",
        table_name="buyer_discovery_runs",
    )
    op.drop_column("buyer_discovery_runs", "actual_credits")
    op.drop_column("buyer_discovery_runs", "estimated_credits")
    op.drop_column("buyer_discovery_runs", "estimated_credit_cap")
    op.drop_column("buyer_discovery_runs", "target_candidate_count")
    op.drop_column("buyer_discovery_runs", "request_fingerprint")
    op.drop_column("buyer_discovery_runs", "search_tier")
