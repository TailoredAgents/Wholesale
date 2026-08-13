"""Bind new SMS consent evidence to the permitted recipient.

Revision ID: 0099_sms_consent_recipient
Revises: 0098_inbound_message_alerts
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0099_sms_consent_recipient"
down_revision: str | None = "0098_inbound_message_alerts"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "consent_records",
        sa.Column("normalized_address", sa.String(length=320), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("consent_records", "normalized_address")
