"""Add measured disposition Copilot review evidence.

Revision ID: 0120_disposition_copilot_eval
Revises: 0119_disposition_provider
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0120_disposition_copilot_eval"
down_revision: str | None = "0119_disposition_provider"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.alter_column(
        "ai_run_logs",
        "output_summary",
        existing_type=sa.String(length=4000),
        type_=sa.Text(),
        existing_nullable=True,
    )
    op.add_column(
        "disposition_copilot_reviews",
        sa.Column(
            "quality_evaluation",
            sa.JSON(),
            nullable=False,
            server_default=sa.text("'{}'"),
        ),
    )


def downgrade() -> None:
    op.drop_column("disposition_copilot_reviews", "quality_evaluation")
    connection = op.get_bind()
    if connection.dialect.name == "postgresql":
        op.execute(
            sa.text(
                "UPDATE ai_run_logs "
                "SET output_summary = SUBSTRING(output_summary FROM 1 FOR 4000) "
                "WHERE CHAR_LENGTH(output_summary) > 4000"
            )
        )
    else:
        op.execute(
            sa.text(
                "UPDATE ai_run_logs "
                "SET output_summary = substr(output_summary, 1, 4000) "
                "WHERE length(output_summary) > 4000"
            )
        )
    op.alter_column(
        "ai_run_logs",
        "output_summary",
        existing_type=sa.Text(),
        type_=sa.String(length=4000),
        existing_nullable=True,
    )
