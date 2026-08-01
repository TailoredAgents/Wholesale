"""Add staff cellphone forwarding and default team lines to simultaneous ring.

Revision ID: 0084_staff_voice_forwarding
Revises: 0083_buyer_communications
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0084_staff_voice_forwarding"
down_revision: str | None = "0083_buyer_communications"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("users", sa.Column("voice_forwarding_number", sa.String(80), nullable=True))
    op.add_column(
        "users",
        sa.Column(
            "voice_forwarding_enabled",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )
    op.execute(
        """
        UPDATE voice_lines
        SET ring_strategy = 'simultaneous'
        WHERE department_key IN ('acquisitions', 'dispositions')
        """
    )


def downgrade() -> None:
    op.drop_column("users", "voice_forwarding_enabled")
    op.drop_column("users", "voice_forwarding_number")
