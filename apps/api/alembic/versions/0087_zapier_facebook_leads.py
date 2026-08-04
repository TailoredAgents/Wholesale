"""Identify the Facebook lead ingestion method.

Revision ID: 0087_zapier_facebook
Revises: 0086_meta_lead_ads
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0087_zapier_facebook"
down_revision: str | None = "0086_meta_lead_ads"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "meta_lead_events",
        sa.Column(
            "ingestion_method",
            sa.String(80),
            nullable=False,
            server_default="direct_graph",
        ),
    )
    op.create_index(
        "ix_meta_lead_events_ingestion_method",
        "meta_lead_events",
        ["ingestion_method"],
    )
    op.execute(
        sa.text(
            "UPDATE meta_lead_events "
            "SET status = 'needs_review', "
            "last_error = 'Direct Graph ingestion was retired before this event completed.' "
            "WHERE ingestion_method = 'direct_graph' "
            "AND status IN ('pending', 'retry', 'blocked', 'processing')"
        )
    )
    op.alter_column(
        "meta_lead_events",
        "ingestion_method",
        server_default="zapier",
    )


def downgrade() -> None:
    op.drop_index("ix_meta_lead_events_ingestion_method", table_name="meta_lead_events")
    op.drop_column("meta_lead_events", "ingestion_method")
