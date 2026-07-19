"""AI usage cost and call quality tracking

Revision ID: 0022_ai_call_quality
Revises: 0021_recording_retention
Create Date: 2026-07-18 00:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0022_ai_call_quality"
down_revision: str | None = "0021_recording_retention"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("ai_run_logs", sa.Column("input_tokens", sa.Integer(), nullable=True))
    op.add_column("ai_run_logs", sa.Column("output_tokens", sa.Integer(), nullable=True))
    op.add_column("ai_run_logs", sa.Column("cost_microusd", sa.BigInteger(), nullable=True))
    op.add_column("ai_run_logs", sa.Column("metadata", sa.JSON(), nullable=True))
    op.execute(
        "UPDATE ai_run_logs SET cost_microusd = cost_cents * 10000 "
        "WHERE cost_cents IS NOT NULL AND cost_microusd IS NULL"
    )


def downgrade() -> None:
    op.drop_column("ai_run_logs", "metadata")
    op.drop_column("ai_run_logs", "cost_microusd")
    op.drop_column("ai_run_logs", "output_tokens")
    op.drop_column("ai_run_logs", "input_tokens")
