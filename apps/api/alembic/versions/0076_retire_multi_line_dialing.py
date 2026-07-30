"""Retire multi-line dialing in favor of one-by-one calling.

Revision ID: 0076_retire_multi_line
Revises: 0075_dialer_provider
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0076_retire_multi_line"
down_revision: str | None = "0075_dialer_provider"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        "UPDATE prospecting_cohorts "
        "SET dialer_mode = 'one_line_power' "
        "WHERE dialer_mode = 'multi_line_parallel'"
    )
    op.execute(
        "UPDATE prospect_calling_batches "
        "SET dialer_mode = 'one_line_power' "
        "WHERE dialer_mode = 'multi_line_parallel'"
    )
    op.execute(
        "UPDATE prospecting_attempts "
        "SET dialer_mode = 'one_line_power' "
        "WHERE dialer_mode = 'multi_line_parallel'"
    )


def downgrade() -> None:
    # Historical rows cannot be reliably distinguished from native one-by-one rows.
    pass
