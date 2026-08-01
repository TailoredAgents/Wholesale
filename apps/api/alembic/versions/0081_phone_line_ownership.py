"""Add department ownership and coverage policy to company phone lines.

Revision ID: 0081_phone_line_ownership
Revises: 0080_underwriting_shadow_replay
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0081_phone_line_ownership"
down_revision: str | None = "0080_underwriting_shadow_replay"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("voice_lines", sa.Column("fallback_user_id", sa.Uuid(), nullable=True))
    op.add_column(
        "voice_lines",
        sa.Column(
            "department_key",
            sa.String(length=40),
            server_default="acquisitions",
            nullable=False,
        ),
    )
    op.add_column(
        "voice_lines",
        sa.Column(
            "purpose_key",
            sa.String(length=80),
            server_default="seller_conversations",
            nullable=False,
        ),
    )
    op.add_column(
        "voice_lines",
        sa.Column(
            "coverage_timezone",
            sa.String(length=80),
            server_default="America/New_York",
            nullable=False,
        ),
    )
    op.add_column(
        "voice_lines",
        sa.Column("coverage_start_hour", sa.Integer(), server_default="9", nullable=False),
    )
    op.add_column(
        "voice_lines",
        sa.Column("coverage_end_hour", sa.Integer(), server_default="20", nullable=False),
    )
    op.add_column(
        "voice_lines",
        sa.Column(
            "missed_call_action",
            sa.String(length=80),
            server_default="fallback_then_voicemail",
            nullable=False,
        ),
    )
    op.create_foreign_key(
        "fk_voice_lines_fallback_user_id",
        "voice_lines",
        "users",
        ["fallback_user_id"],
        ["id"],
    )
    op.create_index("ix_voice_lines_fallback_user_id", "voice_lines", ["fallback_user_id"])


def downgrade() -> None:
    op.drop_index("ix_voice_lines_fallback_user_id", table_name="voice_lines")
    op.drop_constraint("fk_voice_lines_fallback_user_id", "voice_lines", type_="foreignkey")
    op.drop_column("voice_lines", "missed_call_action")
    op.drop_column("voice_lines", "coverage_end_hour")
    op.drop_column("voice_lines", "coverage_start_hour")
    op.drop_column("voice_lines", "coverage_timezone")
    op.drop_column("voice_lines", "purpose_key")
    op.drop_column("voice_lines", "department_key")
    op.drop_column("voice_lines", "fallback_user_id")
