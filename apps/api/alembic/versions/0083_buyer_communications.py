"""Allow voice records to use buyer conversations without fake leads.

Revision ID: 0083_buyer_communications
Revises: 0082_shared_voice_routing
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0083_buyer_communications"
down_revision: str | None = "0082_shared_voice_routing"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.alter_column(
        "voice_call_intents",
        "lead_id",
        existing_type=sa.Uuid(),
        nullable=True,
    )
    op.alter_column(
        "call_records",
        "lead_id",
        existing_type=sa.Uuid(),
        nullable=True,
    )


def downgrade() -> None:
    op.alter_column(
        "call_records",
        "lead_id",
        existing_type=sa.Uuid(),
        nullable=False,
    )
    op.alter_column(
        "voice_call_intents",
        "lead_id",
        existing_type=sa.Uuid(),
        nullable=False,
    )
