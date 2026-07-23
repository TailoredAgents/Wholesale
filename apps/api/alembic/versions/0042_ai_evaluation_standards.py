"""Phase AI2 golden-case evaluation standards.

Revision ID: 0042_ai_evaluation_standards
Revises: 0041_ai_copilot_governance
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0042_ai_evaluation_standards"
down_revision: str | None = "0041_ai_copilot_governance"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "ai_evaluation_datasets",
        sa.Column("dataset_key", sa.String(160), nullable=False, server_default="manual"),
    )
    op.add_column(
        "ai_evaluation_datasets",
        sa.Column(
            "minimum_factual_accuracy_basis_points",
            sa.Integer(),
            nullable=False,
            server_default="9000",
        ),
    )
    op.add_column(
        "ai_evaluation_datasets",
        sa.Column(
            "minimum_evidence_coverage_basis_points",
            sa.Integer(),
            nullable=False,
            server_default="9000",
        ),
    )
    op.add_column(
        "ai_evaluation_datasets",
        sa.Column("owner_role_key", sa.String(120), nullable=False, server_default="owner"),
    )
    op.add_column(
        "ai_evaluation_datasets",
        sa.Column("case_schema_version", sa.Integer(), nullable=False, server_default="1"),
    )
    op.add_column(
        "ai_evaluation_datasets",
        sa.Column("reviewer_instructions", sa.Text(), nullable=False, server_default=""),
    )
    op.add_column(
        "ai_evaluation_datasets",
        sa.Column("disagreement_policy", sa.Text(), nullable=False, server_default=""),
    )
    op.add_column(
        "ai_evaluation_datasets",
        sa.Column("redaction_policy", sa.JSON(), nullable=False, server_default="{}"),
    )
    op.add_column(
        "ai_evaluation_datasets",
        sa.Column("required_review_scopes", sa.JSON(), nullable=False, server_default="[]"),
    )

    op.add_column(
        "ai_evaluation_cases",
        sa.Column("case_type", sa.String(40), nullable=False, server_default="operating"),
    )
    op.add_column(
        "ai_evaluation_cases",
        sa.Column("scenario_family", sa.String(120), nullable=False, server_default="manual"),
    )
    op.add_column(
        "ai_evaluation_cases",
        sa.Column("source_type", sa.String(40), nullable=False, server_default="synthetic"),
    )
    op.add_column(
        "ai_evaluation_cases",
        sa.Column("source_reference", sa.String(255), nullable=True),
    )
    op.add_column(
        "ai_evaluation_cases",
        sa.Column("redaction_status", sa.String(40), nullable=False, server_default="verified"),
    )
    op.add_column(
        "ai_evaluation_cases",
        sa.Column("expected_uncertainty", sa.JSON(), nullable=False, server_default="[]"),
    )
    op.add_column(
        "ai_evaluation_cases",
        sa.Column("required_evidence", sa.JSON(), nullable=False, server_default="[]"),
    )
    op.add_column(
        "ai_evaluation_cases",
        sa.Column("prohibited_behaviors", sa.JSON(), nullable=False, server_default="[]"),
    )
    op.add_column(
        "ai_evaluation_cases",
        sa.Column("reviewer_notes", sa.Text(), nullable=False, server_default=""),
    )

    op.create_table(
        "ai_evaluation_dataset_reviews",
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("dataset_id", sa.Uuid(), nullable=False),
        sa.Column("review_scope", sa.String(40), nullable=False),
        sa.Column("reviewer_role_key", sa.String(120), nullable=False),
        sa.Column("status", sa.String(40), nullable=False),
        sa.Column("notes", sa.String(2000), nullable=False),
        sa.Column("reviewed_by_user_id", sa.Uuid(), nullable=False),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("id", sa.Uuid(), primary_key=True),
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
        sa.ForeignKeyConstraint(
            ["dataset_id"],
            ["ai_evaluation_datasets.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(["reviewed_by_user_id"], ["users.id"]),
        sa.UniqueConstraint(
            "dataset_id",
            "review_scope",
            name="uq_ai_evaluation_dataset_review_scope",
        ),
    )
    op.create_index(
        "ix_ai_evaluation_dataset_reviews_organization_id",
        "ai_evaluation_dataset_reviews",
        ["organization_id"],
    )
    op.create_index(
        "ix_ai_evaluation_dataset_reviews_dataset_id",
        "ai_evaluation_dataset_reviews",
        ["dataset_id"],
    )

    op.add_column(
        "ai_evaluation_runs",
        sa.Column(
            "factual_accuracy_basis_points",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
    )
    op.add_column(
        "ai_evaluation_runs",
        sa.Column(
            "evidence_coverage_basis_points",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
    )
    op.add_column(
        "ai_evaluation_results",
        sa.Column(
            "factual_accuracy_basis_points",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
    )
    op.add_column(
        "ai_evaluation_results",
        sa.Column(
            "evidence_coverage_basis_points",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
    )


def downgrade() -> None:
    op.drop_column("ai_evaluation_results", "evidence_coverage_basis_points")
    op.drop_column("ai_evaluation_results", "factual_accuracy_basis_points")
    op.drop_column("ai_evaluation_runs", "evidence_coverage_basis_points")
    op.drop_column("ai_evaluation_runs", "factual_accuracy_basis_points")
    op.drop_index(
        "ix_ai_evaluation_dataset_reviews_dataset_id",
        table_name="ai_evaluation_dataset_reviews",
    )
    op.drop_index(
        "ix_ai_evaluation_dataset_reviews_organization_id",
        table_name="ai_evaluation_dataset_reviews",
    )
    op.drop_table("ai_evaluation_dataset_reviews")
    for column in (
        "reviewer_notes",
        "prohibited_behaviors",
        "required_evidence",
        "expected_uncertainty",
        "redaction_status",
        "source_reference",
        "source_type",
        "scenario_family",
        "case_type",
    ):
        op.drop_column("ai_evaluation_cases", column)
    for column in (
        "required_review_scopes",
        "redaction_policy",
        "disagreement_policy",
        "reviewer_instructions",
        "case_schema_version",
        "owner_role_key",
        "minimum_evidence_coverage_basis_points",
        "minimum_factual_accuracy_basis_points",
        "dataset_key",
    ):
        op.drop_column("ai_evaluation_datasets", column)
