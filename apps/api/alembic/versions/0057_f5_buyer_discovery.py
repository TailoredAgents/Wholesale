"""F5 provider-backed buyer discovery.

Revision ID: 0057_f5_buyer_discovery
Revises: 0056_f4_documents_esign
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0057_f5_buyer_discovery"
down_revision: str | None = "0056_f4_documents_esign"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "buyer_discovery_runs",
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("disposition_case_id", sa.Uuid(), nullable=False),
        sa.Column("requested_by_user_id", sa.Uuid(), nullable=False),
        sa.Column("provider", sa.String(40), nullable=False),
        sa.Column("status", sa.String(40), nullable=False),
        sa.Column("search_snapshot", sa.JSON(), nullable=False),
        sa.Column("provider_request", sa.JSON(), nullable=False),
        sa.Column("result_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("imported_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("credit_summary", sa.JSON()),
        sa.Column("error_message", sa.String(2000)),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        sa.ForeignKeyConstraint(
            ["disposition_case_id"], ["disposition_cases.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["requested_by_user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    for column in ("organization_id", "disposition_case_id", "status"):
        op.create_index(
            f"ix_buyer_discovery_runs_{column}",
            "buyer_discovery_runs",
            [column],
        )

    op.create_table(
        "buyer_discovery_candidates",
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("discovery_run_id", sa.Uuid(), nullable=False),
        sa.Column("buyer_id", sa.Uuid()),
        sa.Column("provider", sa.String(40), nullable=False),
        sa.Column("external_key", sa.String(255), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("company_name", sa.String(255)),
        sa.Column("email", sa.String(320)),
        sa.Column("phone", sa.String(80)),
        sa.Column("market", sa.String(255), nullable=False),
        sa.Column("state", sa.String(2), nullable=False),
        sa.Column("property_types", sa.JSON(), nullable=False),
        sa.Column("observed_purchase_count", sa.Integer(), nullable=False),
        sa.Column("no_mortgage_count", sa.Integer(), nullable=False),
        sa.Column("last_purchase_date", sa.Date()),
        sa.Column("min_purchase_price_cents", sa.BigInteger()),
        sa.Column("max_purchase_price_cents", sa.BigInteger()),
        sa.Column("score_basis_points", sa.Integer(), nullable=False),
        sa.Column("score_components", sa.JSON(), nullable=False),
        sa.Column("evidence_snapshot", sa.JSON(), nullable=False),
        sa.Column("provider_snapshot", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(40), nullable=False),
        sa.Column("imported_at", sa.DateTime(timezone=True)),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        sa.ForeignKeyConstraint(
            ["discovery_run_id"], ["buyer_discovery_runs.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["buyer_id"], ["buyers.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "discovery_run_id",
            "external_key",
            name="uq_buyer_discovery_run_external_key",
        ),
    )
    for column in ("organization_id", "discovery_run_id", "status"):
        op.create_index(
            f"ix_buyer_discovery_candidates_{column}",
            "buyer_discovery_candidates",
            [column],
        )
    op.create_index(
        "ix_buyer_discovery_candidate_provider_key",
        "buyer_discovery_candidates",
        ["organization_id", "provider", "external_key"],
    )


def downgrade() -> None:
    op.drop_table("buyer_discovery_candidates")
    op.drop_table("buyer_discovery_runs")
