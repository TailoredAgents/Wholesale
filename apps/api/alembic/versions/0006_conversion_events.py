"""conversion events

Revision ID: 0006_conversion_events
Revises: 0005_speed_to_lead_tasks
Create Date: 2026-07-14 00:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0006_conversion_events"
down_revision: str | None = "0005_speed_to_lead_tasks"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "conversion_events",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("lead_id", sa.Uuid(), nullable=True),
        sa.Column("event_type", sa.String(length=80), nullable=False),
        sa.Column("landing_page", sa.String(length=255), nullable=True),
        sa.Column("referrer", sa.String(length=500), nullable=True),
        sa.Column("source", sa.String(length=120), nullable=True),
        sa.Column("medium", sa.String(length=120), nullable=True),
        sa.Column("campaign", sa.String(length=255), nullable=True),
        sa.Column("term", sa.String(length=255), nullable=True),
        sa.Column("content", sa.String(length=255), nullable=True),
        sa.Column("gclid", sa.String(length=255), nullable=True),
        sa.Column("fbclid", sa.String(length=255), nullable=True),
        sa.Column("session_id", sa.String(length=120), nullable=True),
        sa.Column("ip_address", sa.String(length=80), nullable=True),
        sa.Column("user_agent", sa.String(length=500), nullable=True),
        sa.Column("metadata", sa.JSON(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["lead_id"], ["leads.id"]),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_conversion_events_event_type", "conversion_events", ["event_type"])
    op.create_index("ix_conversion_events_lead_id", "conversion_events", ["lead_id"])
    op.create_index(
        "ix_conversion_events_organization_id", "conversion_events", ["organization_id"]
    )
    op.create_index("ix_conversion_events_session_id", "conversion_events", ["session_id"])


def downgrade() -> None:
    op.drop_index("ix_conversion_events_session_id", table_name="conversion_events")
    op.drop_index("ix_conversion_events_organization_id", table_name="conversion_events")
    op.drop_index("ix_conversion_events_lead_id", table_name="conversion_events")
    op.drop_index("ix_conversion_events_event_type", table_name="conversion_events")
    op.drop_table("conversion_events")
