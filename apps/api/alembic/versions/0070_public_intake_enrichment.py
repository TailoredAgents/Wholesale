"""Add secure public-intake enrichment fields.

Revision ID: 0070_public_intake_enrichment
Revises: 0069_in_person_esign
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0070_public_intake_enrichment"
down_revision: str | None = "0069_in_person_esign"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "lead_form_submissions",
        sa.Column("enrichment_token_hash", sa.String(64), nullable=True),
    )
    op.add_column(
        "lead_form_submissions",
        sa.Column("enrichment_expires_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "lead_form_submissions",
        sa.Column("enriched_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_lead_form_submissions_enrichment_token_hash",
        "lead_form_submissions",
        ["enrichment_token_hash"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_lead_form_submissions_enrichment_token_hash",
        table_name="lead_form_submissions",
    )
    op.drop_column("lead_form_submissions", "enriched_at")
    op.drop_column("lead_form_submissions", "enrichment_expires_at")
    op.drop_column("lead_form_submissions", "enrichment_token_hash")
