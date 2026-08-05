"""Track automatic Meta lead address enrichment.

Revision ID: 0088_meta_address_enrich
Revises: 0087_zapier_facebook
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0088_meta_address_enrich"
down_revision: str | None = "0087_zapier_facebook"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "meta_lead_events",
        sa.Column(
            "address_enrichment_status",
            sa.String(80),
            nullable=False,
            server_default="pending",
        ),
    )
    op.add_column(
        "meta_lead_events",
        sa.Column(
            "address_enrichment_attempt_count",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
    )
    op.add_column(
        "meta_lead_events",
        sa.Column("address_enrichment_last_attempt_at", sa.DateTime(timezone=True)),
    )
    op.add_column(
        "meta_lead_events",
        sa.Column("address_enrichment_next_attempt_at", sa.DateTime(timezone=True)),
    )
    op.add_column(
        "meta_lead_events",
        sa.Column("address_enriched_at", sa.DateTime(timezone=True)),
    )
    op.add_column(
        "meta_lead_events",
        sa.Column("address_enrichment_last_error", sa.String(2000)),
    )
    op.create_index(
        "ix_meta_lead_events_address_enrichment_status",
        "meta_lead_events",
        ["address_enrichment_status"],
    )
    op.create_index(
        "ix_meta_lead_events_address_enrichment_due",
        "meta_lead_events",
        ["address_enrichment_status", "address_enrichment_next_attempt_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_meta_lead_events_address_enrichment_due",
        table_name="meta_lead_events",
    )
    op.drop_index(
        "ix_meta_lead_events_address_enrichment_status",
        table_name="meta_lead_events",
    )
    op.drop_column("meta_lead_events", "address_enrichment_last_error")
    op.drop_column("meta_lead_events", "address_enriched_at")
    op.drop_column("meta_lead_events", "address_enrichment_next_attempt_at")
    op.drop_column("meta_lead_events", "address_enrichment_last_attempt_at")
    op.drop_column("meta_lead_events", "address_enrichment_attempt_count")
    op.drop_column("meta_lead_events", "address_enrichment_status")
