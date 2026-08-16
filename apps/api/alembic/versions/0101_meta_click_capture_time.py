"""Persist the original Meta click capture timestamp.

Revision ID: 0101_meta_click_capture_time
Revises: 0100_voice_lines_always_on
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0101_meta_click_capture_time"
down_revision: str | None = "0100_voice_lines_always_on"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # These stay nullable intentionally. Existing records do not contain a trustworthy
    # original click time, so guessing during migration would corrupt attribution.
    for table_name in (
        "lead_form_submissions",
        "attribution_touches",
        "conversion_events",
    ):
        op.add_column(
            table_name,
            sa.Column("fbclid_captured_at", sa.DateTime(timezone=True), nullable=True),
        )


def downgrade() -> None:
    for table_name in (
        "conversion_events",
        "attribution_touches",
        "lead_form_submissions",
    ):
        op.drop_column(table_name, "fbclid_captured_at")
