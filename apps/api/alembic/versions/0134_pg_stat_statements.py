"""Enable PostgreSQL statement-level performance statistics.

Revision ID: 0134_pg_stat_statements
Revises: 0133_batchdialer_campaign_route
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0134_pg_stat_statements"
down_revision: str | None = "0133_batchdialer_campaign_route"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute("CREATE EXTENSION IF NOT EXISTS pg_stat_statements")


def downgrade() -> None:
    # The extension may predate this application or be shared by other tools.
    # Removing it during an application rollback would be destructive.
    pass
