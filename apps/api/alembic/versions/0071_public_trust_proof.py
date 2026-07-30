"""Add evidence-backed public trust proof records.

Revision ID: 0071_public_trust_proof
Revises: 0070_public_intake_enrichment
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0071_public_trust_proof"
down_revision: str | None = "0070_public_intake_enrichment"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "public_proof_records",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("proof_type", sa.String(40), nullable=False),
        sa.Column("title", sa.String(180), nullable=False),
        sa.Column("content", sa.Text(), nullable=True),
        sa.Column("attribution_name", sa.String(120), nullable=True),
        sa.Column("attribution_detail", sa.String(180), nullable=True),
        sa.Column("location_label", sa.String(120), nullable=True),
        sa.Column("rating", sa.Integer(), nullable=True),
        sa.Column("metric_label", sa.String(120), nullable=True),
        sa.Column("metric_value", sa.String(80), nullable=True),
        sa.Column("methodology", sa.String(2000), nullable=True),
        sa.Column("as_of_date", sa.Date(), nullable=True),
        sa.Column("source_type", sa.String(60), nullable=False),
        sa.Column("source_url", sa.String(1000), nullable=True),
        sa.Column("source_reference", sa.String(500), nullable=True),
        sa.Column("show_source_link", sa.Boolean(), server_default="false", nullable=False),
        sa.Column(
            "permission_status",
            sa.String(40),
            server_default="pending",
            nullable=False,
        ),
        sa.Column("permission_evidence_notes", sa.String(2000), nullable=True),
        sa.Column("material_connection", sa.String(500), nullable=True),
        sa.Column("disclosure", sa.String(500), nullable=True),
        sa.Column(
            "publication_status",
            sa.String(40),
            server_default="draft",
            nullable=False,
        ),
        sa.Column("featured", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("sort_order", sa.Integer(), server_default="0", nullable=False),
        sa.Column("created_by_user_id", sa.Uuid(), nullable=False),
        sa.Column("updated_by_user_id", sa.Uuid(), nullable=False),
        sa.Column("approved_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("retired_at", sa.DateTime(timezone=True), nullable=True),
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
            "proof_type IN ('review', 'seller_story', 'completed_purchase', 'statistic')",
            name="ck_public_proof_records_type",
        ),
        sa.CheckConstraint(
            "permission_status IN ('pending', 'granted', 'not_required', 'revoked')",
            name="ck_public_proof_records_permission",
        ),
        sa.CheckConstraint(
            "publication_status IN ('draft', 'in_review', 'published', 'retired')",
            name="ck_public_proof_records_publication",
        ),
        sa.CheckConstraint(
            "rating IS NULL OR (rating >= 1 AND rating <= 5)",
            name="ck_public_proof_records_rating",
        ),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["updated_by_user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["approved_by_user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_public_proof_records_organization_id",
        "public_proof_records",
        ["organization_id"],
    )
    op.create_index(
        "ix_public_proof_records_proof_type",
        "public_proof_records",
        ["proof_type"],
    )
    op.create_index(
        "ix_public_proof_records_publication_status",
        "public_proof_records",
        ["publication_status"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_public_proof_records_publication_status",
        table_name="public_proof_records",
    )
    op.drop_index("ix_public_proof_records_proof_type", table_name="public_proof_records")
    op.drop_index(
        "ix_public_proof_records_organization_id",
        table_name="public_proof_records",
    )
    op.drop_table("public_proof_records")
