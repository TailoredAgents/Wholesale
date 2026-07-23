"""Enable the draft-only Transaction Copilot.

Revision ID: 0048_enable_transaction_copilot
Revises: 0047_transaction_copilot
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0048_enable_transaction_copilot"
down_revision: str | None = "0047_transaction_copilot"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    policies = sa.table(
        "ai_capability_runtime_policies",
        sa.column("capability_key", sa.String()),
        sa.column("status", sa.String()),
        sa.column("requires_human_review", sa.Boolean()),
    )
    op.execute(
        policies.update()
        .where(policies.c.capability_key == "transaction.coordinate")
        .values(status="enabled", requires_human_review=True)
    )


def downgrade() -> None:
    policies = sa.table(
        "ai_capability_runtime_policies",
        sa.column("capability_key", sa.String()),
        sa.column("status", sa.String()),
    )
    op.execute(
        policies.update()
        .where(policies.c.capability_key == "transaction.coordinate")
        .values(status="disabled")
    )
