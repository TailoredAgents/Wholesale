"""Remove the imported DNC evidence review gate.

Revision ID: 0055_remove_dnc_review_gate
Revises: 0054_compliance_policy
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0055_remove_dnc_review_gate"
down_revision: str | None = "0054_compliance_policy"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    prospects = sa.table(
        "prospects",
        sa.column("normalized_phone", sa.String()),
        sa.column("call_eligibility", sa.String()),
        sa.column("suppression_status", sa.String()),
    )
    op.execute(
        prospects.update()
        .where(
            prospects.c.call_eligibility == "review_required",
            prospects.c.normalized_phone.is_not(None),
        )
        .values(call_eligibility="eligible", suppression_status="clear")
    )


def downgrade() -> None:
    pass
