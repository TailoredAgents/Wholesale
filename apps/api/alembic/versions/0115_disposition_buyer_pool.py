"""Add the canonical disposition buyer-pool persistence layer.

Revision ID: 0115_disposition_buyer_pool
Revises: 0114_buyer_profiles_buy_boxes
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0115_disposition_buyer_pool"
down_revision: str | None = "0114_buyer_profiles_buy_boxes"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "buyer_source_links",
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("buyer_id", sa.Uuid(), nullable=False),
        sa.Column("provider", sa.String(length=80), nullable=False),
        sa.Column("external_key", sa.String(length=255), nullable=False),
        sa.Column("discovery_candidate_id", sa.Uuid(), nullable=True),
        sa.Column("evidence_snapshot", sa.JSON(), nullable=False),
        sa.Column("approved_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        sa.ForeignKeyConstraint(["buyer_id"], ["buyers.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["discovery_candidate_id"],
            ["buyer_discovery_candidates.id"],
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["approved_by_user_id"], ["users.id"], ondelete="SET NULL"
        ),
        sa.UniqueConstraint(
            "organization_id",
            "provider",
            "external_key",
            name="uq_buyer_source_links_org_provider_external",
        ),
    )
    op.create_index(
        "ix_buyer_source_links_org_buyer",
        "buyer_source_links",
        ["organization_id", "buyer_id"],
    )
    op.create_index(
        "ix_buyer_source_links_discovery_candidate",
        "buyer_source_links",
        ["discovery_candidate_id"],
    )

    op.create_table(
        "disposition_buyer_pool_runs",
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("disposition_case_id", sa.Uuid(), nullable=False),
        sa.Column("generated_by_user_id", sa.Uuid(), nullable=False),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column("asset_class", sa.String(length=40), nullable=False),
        sa.Column("matcher_version", sa.String(length=80), nullable=False),
        sa.Column("score_policy_version", sa.String(length=80), nullable=False),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column("input_snapshot", sa.JSON(), nullable=False),
        sa.Column("input_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("source_counts", sa.JSON(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.CheckConstraint(
            "version_number > 0",
            name="ck_disposition_buyer_pool_runs_version_positive",
        ),
        sa.CheckConstraint(
            "asset_class IN ('house', 'land')",
            name="ck_disposition_buyer_pool_runs_asset_class",
        ),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        sa.ForeignKeyConstraint(
            ["disposition_case_id"], ["disposition_cases.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["generated_by_user_id"], ["users.id"]),
        sa.UniqueConstraint(
            "disposition_case_id",
            "version_number",
            name="uq_disposition_buyer_pool_runs_case_version",
        ),
    )
    op.create_index(
        "ix_disposition_buyer_pool_runs_org_case_created",
        "disposition_buyer_pool_runs",
        ["organization_id", "disposition_case_id", "created_at"],
    )
    op.create_index(
        "ix_disposition_buyer_pool_runs_case_status",
        "disposition_buyer_pool_runs",
        ["disposition_case_id", "status"],
    )
    op.create_index(
        "ix_disposition_buyer_pool_runs_generated_by",
        "disposition_buyer_pool_runs",
        ["generated_by_user_id"],
    )

    op.create_table(
        "disposition_buyer_pool_candidates",
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("disposition_case_id", sa.Uuid(), nullable=False),
        sa.Column("identity_key", sa.String(length=255), nullable=False),
        sa.Column("source_type", sa.String(length=40), nullable=False),
        sa.Column("buyer_id", sa.Uuid(), nullable=True),
        sa.Column("latest_discovery_candidate_id", sa.Uuid(), nullable=True),
        sa.Column("provider", sa.String(length=80), nullable=True),
        sa.Column("external_key", sa.String(length=255), nullable=True),
        sa.Column("display_name", sa.String(length=255), nullable=False),
        sa.Column("company_name", sa.String(length=255), nullable=True),
        sa.Column("email", sa.String(length=320), nullable=True),
        sa.Column("phone", sa.String(length=80), nullable=True),
        sa.Column("provenance_snapshot", sa.JSON(), nullable=False),
        sa.Column("overlap_status", sa.String(length=40), nullable=False),
        sa.Column("possible_buyer_id", sa.Uuid(), nullable=True),
        sa.Column("overlap_evidence", sa.JSON(), nullable=False),
        sa.Column("decision_status", sa.String(length=40), nullable=False),
        sa.Column("lifecycle_stage", sa.String(length=40), nullable=False),
        sa.Column("decision_reason", sa.String(length=1000), nullable=True),
        sa.Column("lock_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("decision_updated_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("decision_updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("approved_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.CheckConstraint(
            "source_type IN ('internal', 'external')",
            name="ck_disposition_buyer_pool_candidates_source_type",
        ),
        sa.CheckConstraint(
            "lock_version > 0",
            name="ck_disposition_buyer_pool_candidates_lock_positive",
        ),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        sa.ForeignKeyConstraint(
            ["disposition_case_id"], ["disposition_cases.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["buyer_id"], ["buyers.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(
            ["latest_discovery_candidate_id"],
            ["buyer_discovery_candidates.id"],
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["possible_buyer_id"], ["buyers.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["decision_updated_by_user_id"], ["users.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["approved_by_user_id"], ["users.id"], ondelete="SET NULL"
        ),
        sa.UniqueConstraint(
            "organization_id",
            "disposition_case_id",
            "identity_key",
            name="uq_disposition_buyer_pool_candidates_identity",
        ),
    )
    op.create_index(
        "ix_disposition_buyer_pool_candidates_case_stage",
        "disposition_buyer_pool_candidates",
        ["organization_id", "disposition_case_id", "lifecycle_stage"],
    )
    op.create_index(
        "ix_disposition_buyer_pool_candidates_case_source",
        "disposition_buyer_pool_candidates",
        ["organization_id", "disposition_case_id", "source_type"],
    )
    op.create_index(
        "ix_disposition_buyer_pool_candidates_org_buyer",
        "disposition_buyer_pool_candidates",
        ["organization_id", "buyer_id"],
    )
    op.create_index(
        "uq_disposition_buyer_pool_candidates_case_buyer",
        "disposition_buyer_pool_candidates",
        ["organization_id", "disposition_case_id", "buyer_id"],
        unique=True,
        postgresql_where=sa.text("buyer_id IS NOT NULL"),
        sqlite_where=sa.text("buyer_id IS NOT NULL"),
    )
    op.create_index(
        "ix_disposition_buyer_pool_candidates_provider_key",
        "disposition_buyer_pool_candidates",
        ["organization_id", "provider", "external_key"],
    )
    op.create_index(
        "ix_disposition_buyer_pool_candidates_case_decision",
        "disposition_buyer_pool_candidates",
        ["organization_id", "disposition_case_id", "decision_status"],
    )
    op.create_index(
        "ix_disposition_buyer_pool_candidates_discovery",
        "disposition_buyer_pool_candidates",
        ["latest_discovery_candidate_id"],
    )
    op.create_index(
        "ix_disposition_buyer_pool_candidates_possible_buyer",
        "disposition_buyer_pool_candidates",
        ["possible_buyer_id"],
    )

    op.create_table(
        "disposition_buyer_pool_entries",
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("buyer_pool_run_id", sa.Uuid(), nullable=False),
        sa.Column("buyer_pool_candidate_id", sa.Uuid(), nullable=False),
        sa.Column("buyer_id", sa.Uuid(), nullable=True),
        sa.Column("buy_box_version_id", sa.Uuid(), nullable=True),
        sa.Column("proof_document_id", sa.Uuid(), nullable=True),
        sa.Column("source_type", sa.String(length=40), nullable=False),
        sa.Column("score_basis_points", sa.Integer(), nullable=False),
        sa.Column("rank", sa.Integer(), nullable=False),
        sa.Column("eligibility_status", sa.String(length=40), nullable=False),
        sa.Column("score_components", sa.JSON(), nullable=False),
        sa.Column("score_explanation", sa.JSON(), nullable=False),
        sa.Column("supporting_evidence", sa.JSON(), nullable=False),
        sa.Column("conflicting_evidence", sa.JSON(), nullable=False),
        sa.Column("disqualifying_reasons", sa.JSON(), nullable=False),
        sa.Column("evidence_snapshot", sa.JSON(), nullable=False),
        sa.Column("criteria_snapshot", sa.JSON(), nullable=False),
        sa.Column("source_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.CheckConstraint(
            "source_type IN ('internal', 'external')",
            name="ck_disposition_buyer_pool_entries_source_type",
        ),
        sa.CheckConstraint(
            "score_basis_points BETWEEN 0 AND 10000",
            name="ck_disposition_buyer_pool_entries_score_range",
        ),
        sa.CheckConstraint(
            "rank > 0",
            name="ck_disposition_buyer_pool_entries_rank_positive",
        ),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        sa.ForeignKeyConstraint(
            ["buyer_pool_run_id"],
            ["disposition_buyer_pool_runs.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["buyer_pool_candidate_id"],
            ["disposition_buyer_pool_candidates.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(["buyer_id"], ["buyers.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(
            ["buy_box_version_id"],
            ["buyer_buy_box_versions.id"],
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["proof_document_id"],
            ["buyer_proof_documents.id"],
            ondelete="SET NULL",
        ),
        sa.UniqueConstraint(
            "buyer_pool_run_id",
            "buyer_pool_candidate_id",
            name="uq_disposition_buyer_pool_entries_run_candidate",
        ),
    )
    op.create_index(
        "ix_disposition_buyer_pool_entries_run_rank",
        "disposition_buyer_pool_entries",
        ["buyer_pool_run_id", "rank"],
    )
    op.create_index(
        "ix_disposition_buyer_pool_entries_run_eligibility",
        "disposition_buyer_pool_entries",
        ["buyer_pool_run_id", "eligibility_status", "rank"],
    )
    op.create_index(
        "ix_disposition_buyer_pool_entries_org_buyer",
        "disposition_buyer_pool_entries",
        ["organization_id", "buyer_id"],
    )
    op.create_index(
        "ix_disposition_buyer_pool_entries_candidate",
        "disposition_buyer_pool_entries",
        ["buyer_pool_candidate_id"],
    )
    op.create_index(
        "ix_disposition_buyer_pool_entries_buy_box",
        "disposition_buyer_pool_entries",
        ["buy_box_version_id"],
    )
    op.create_index(
        "ix_disposition_buyer_pool_entries_proof",
        "disposition_buyer_pool_entries",
        ["proof_document_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_disposition_buyer_pool_entries_proof",
        table_name="disposition_buyer_pool_entries",
    )
    op.drop_index(
        "ix_disposition_buyer_pool_entries_buy_box",
        table_name="disposition_buyer_pool_entries",
    )
    op.drop_index(
        "ix_disposition_buyer_pool_entries_candidate",
        table_name="disposition_buyer_pool_entries",
    )
    op.drop_index(
        "ix_disposition_buyer_pool_entries_org_buyer",
        table_name="disposition_buyer_pool_entries",
    )
    op.drop_index(
        "ix_disposition_buyer_pool_entries_run_eligibility",
        table_name="disposition_buyer_pool_entries",
    )
    op.drop_index(
        "ix_disposition_buyer_pool_entries_run_rank",
        table_name="disposition_buyer_pool_entries",
    )
    op.drop_table("disposition_buyer_pool_entries")

    op.drop_index(
        "ix_disposition_buyer_pool_candidates_possible_buyer",
        table_name="disposition_buyer_pool_candidates",
    )
    op.drop_index(
        "ix_disposition_buyer_pool_candidates_discovery",
        table_name="disposition_buyer_pool_candidates",
    )
    op.drop_index(
        "ix_disposition_buyer_pool_candidates_case_decision",
        table_name="disposition_buyer_pool_candidates",
    )
    op.drop_index(
        "ix_disposition_buyer_pool_candidates_provider_key",
        table_name="disposition_buyer_pool_candidates",
    )
    op.drop_index(
        "ix_disposition_buyer_pool_candidates_org_buyer",
        table_name="disposition_buyer_pool_candidates",
    )
    op.drop_index(
        "uq_disposition_buyer_pool_candidates_case_buyer",
        table_name="disposition_buyer_pool_candidates",
    )
    op.drop_index(
        "ix_disposition_buyer_pool_candidates_case_source",
        table_name="disposition_buyer_pool_candidates",
    )
    op.drop_index(
        "ix_disposition_buyer_pool_candidates_case_stage",
        table_name="disposition_buyer_pool_candidates",
    )
    op.drop_table("disposition_buyer_pool_candidates")

    op.drop_index(
        "ix_disposition_buyer_pool_runs_generated_by",
        table_name="disposition_buyer_pool_runs",
    )
    op.drop_index(
        "ix_disposition_buyer_pool_runs_case_status",
        table_name="disposition_buyer_pool_runs",
    )
    op.drop_index(
        "ix_disposition_buyer_pool_runs_org_case_created",
        table_name="disposition_buyer_pool_runs",
    )
    op.drop_table("disposition_buyer_pool_runs")

    op.drop_index(
        "ix_buyer_source_links_discovery_candidate",
        table_name="buyer_source_links",
    )
    op.drop_index(
        "ix_buyer_source_links_org_buyer",
        table_name="buyer_source_links",
    )
    op.drop_table("buyer_source_links")
