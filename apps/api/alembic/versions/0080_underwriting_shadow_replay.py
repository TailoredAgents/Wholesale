"""Add underwriting shadow-validation scenario evidence.

Revision ID: 0080_underwriting_shadow_replay
Revises: 0079_underwriting_manual_comps
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0080_underwriting_shadow_replay"
down_revision: str | None = "0079_underwriting_manual_comps"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "underwriting_calibration_cases",
        sa.Column(
            "validation_scenarios",
            sa.JSON(),
            server_default=sa.text("'[]'"),
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_column("underwriting_calibration_cases", "validation_scenarios")
