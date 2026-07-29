"""Add durable in-person e-signature session fields.

Revision ID: 0069_in_person_esign
Revises: 0068_f8_mailbox_context
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0069_in_person_esign"
down_revision: str | None = "0068_f8_mailbox_context"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "esign_envelopes",
        sa.Column(
            "delivery_mode",
            sa.String(40),
            server_default="email",
            nullable=False,
        ),
    )
    op.add_column(
        "esign_recipients",
        sa.Column("embedded_signing_url", sa.String(1000), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("esign_recipients", "embedded_signing_url")
    op.drop_column("esign_envelopes", "delivery_mode")
