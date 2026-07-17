"""lead archiving

Revision ID: 0017_lead_archiving
Revises: 0016_market_analyses
Create Date: 2026-07-17 00:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0017_lead_archiving"
down_revision: str | None = "0016_market_analyses"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("leads", sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True))
    op.create_index("ix_leads_archived_at", "leads", ["archived_at"])


def downgrade() -> None:
    op.drop_index("ix_leads_archived_at", table_name="leads")
    op.drop_column("leads", "archived_at")
