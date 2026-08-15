"""Make active company voice lines available around the clock.

Revision ID: 0100_voice_lines_always_on
Revises: 0099_sms_consent_recipient
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0100_voice_lines_always_on"
down_revision: str | None = "0099_sms_consent_recipient"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        UPDATE voice_lines
        SET coverage_start_hour = 0,
            coverage_end_hour = 24
        WHERE status = 'active'
        """
    )
    op.alter_column(
        "voice_lines",
        "coverage_start_hour",
        existing_type=sa.Integer(),
        existing_nullable=False,
        server_default=sa.text("0"),
    )
    op.alter_column(
        "voice_lines",
        "coverage_end_hour",
        existing_type=sa.Integer(),
        existing_nullable=False,
        server_default=sa.text("24"),
    )


def downgrade() -> None:
    op.alter_column(
        "voice_lines",
        "coverage_end_hour",
        existing_type=sa.Integer(),
        existing_nullable=False,
        server_default=sa.text("20"),
    )
    op.alter_column(
        "voice_lines",
        "coverage_start_hour",
        existing_type=sa.Integer(),
        existing_nullable=False,
        server_default=sa.text("9"),
    )
