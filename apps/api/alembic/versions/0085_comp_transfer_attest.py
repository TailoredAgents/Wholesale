"""Add transfer eligibility evidence to manual comparables.

Revision ID: 0085_comp_transfer_attest
Revises: 0084_staff_voice_forwarding
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0085_comp_transfer_attest"
down_revision: str | None = "0084_staff_voice_forwarding"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "underwriting_manual_comparables",
        sa.Column("transaction_type", sa.String(160), nullable=True),
    )
    op.add_column(
        "underwriting_manual_comparables",
        sa.Column(
            "arms_length_verified",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )
    op.add_column(
        "underwriting_manual_comparables",
        sa.Column("arms_length_evidence", sa.String(1000), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("underwriting_manual_comparables", "arms_length_evidence")
    op.drop_column("underwriting_manual_comparables", "arms_length_verified")
    op.drop_column("underwriting_manual_comparables", "transaction_type")
