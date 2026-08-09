"""Serialize active e-signature sends per approved contract package.

Revision ID: 0094_esign_send_intents
Revises: 0093_resend_event_reliability
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0094_esign_send_intents"
down_revision: str | None = "0093_resend_event_reliability"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    active_predicate = sa.text(
        "status NOT IN ('completed', 'declined', 'expired', 'cancelled', 'error')"
    )
    op.create_index(
        "uq_esign_envelope_active_package",
        "esign_envelopes",
        ["contract_package_id"],
        unique=True,
        postgresql_where=active_predicate,
        sqlite_where=active_predicate,
    )


def downgrade() -> None:
    op.drop_index(
        "uq_esign_envelope_active_package",
        table_name="esign_envelopes",
    )
