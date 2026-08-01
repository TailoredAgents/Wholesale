"""Add shared-team routing controls to company phone lines.

Revision ID: 0082_shared_voice_routing
Revises: 0081_phone_line_ownership
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0082_shared_voice_routing"
down_revision: str | None = "0081_phone_line_ownership"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("voice_lines", sa.Column("assigned_team_id", sa.Uuid(), nullable=True))
    op.add_column(
        "voice_lines",
        sa.Column(
            "ring_strategy",
            sa.String(length=40),
            server_default="sequential",
            nullable=False,
        ),
    )
    op.create_foreign_key(
        "fk_voice_lines_assigned_team_id",
        "voice_lines",
        "teams",
        ["assigned_team_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index("ix_voice_lines_assigned_team_id", "voice_lines", ["assigned_team_id"])


def downgrade() -> None:
    op.drop_index("ix_voice_lines_assigned_team_id", table_name="voice_lines")
    op.drop_constraint("fk_voice_lines_assigned_team_id", "voice_lines", type_="foreignkey")
    op.drop_column("voice_lines", "ring_strategy")
    op.drop_column("voice_lines", "assigned_team_id")
