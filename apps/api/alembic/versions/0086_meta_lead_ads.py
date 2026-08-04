"""Add Meta lead ingestion and staff SMS alert queues.

Revision ID: 0086_meta_lead_ads
Revises: 0085_comp_transfer_attest
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0086_meta_lead_ads"
down_revision: str | None = "0085_comp_transfer_attest"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column(
            "lead_alert_sms_enabled",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )
    op.create_table(
        "meta_lead_events",
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("lead_id", sa.Uuid(), nullable=True),
        sa.Column("provider_lead_id", sa.String(255), nullable=False),
        sa.Column("page_id", sa.String(255), nullable=False),
        sa.Column("form_id", sa.String(255), nullable=True),
        sa.Column("ad_id", sa.String(255), nullable=True),
        sa.Column("campaign_id", sa.String(255), nullable=True),
        sa.Column("status", sa.String(80), nullable=False),
        sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("lead_created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_attempt_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("webhook_payload", sa.JSON(), nullable=False),
        sa.Column("lead_payload", sa.JSON(), nullable=True),
        sa.Column("last_error", sa.String(2000), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.ForeignKeyConstraint(["lead_id"], ["leads.id"]),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "organization_id",
            "provider_lead_id",
            name="uq_meta_lead_events_org_provider_lead",
        ),
    )
    op.create_index("ix_meta_lead_events_lead_id", "meta_lead_events", ["lead_id"])
    op.create_index(
        "ix_meta_lead_events_organization_id",
        "meta_lead_events",
        ["organization_id"],
    )
    op.create_index("ix_meta_lead_events_page_id", "meta_lead_events", ["page_id"])
    op.create_index("ix_meta_lead_events_form_id", "meta_lead_events", ["form_id"])
    op.create_index("ix_meta_lead_events_status", "meta_lead_events", ["status"])
    op.create_index(
        "ix_meta_lead_events_org_status_due",
        "meta_lead_events",
        ["organization_id", "status", "next_attempt_at"],
    )
    op.create_table(
        "staff_lead_alerts",
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("meta_lead_event_id", sa.Uuid(), nullable=False),
        sa.Column("lead_id", sa.Uuid(), nullable=False),
        sa.Column("recipient_user_id", sa.Uuid(), nullable=False),
        sa.Column("recipient_phone", sa.String(40), nullable=False),
        sa.Column("message_body", sa.String(1000), nullable=False),
        sa.Column("status", sa.String(80), nullable=False),
        sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_attempt_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("delivered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("provider", sa.String(80), nullable=True),
        sa.Column("provider_message_id", sa.String(255), nullable=True),
        sa.Column("provider_response", sa.JSON(), nullable=True),
        sa.Column("last_error", sa.String(2000), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.ForeignKeyConstraint(["lead_id"], ["leads.id"]),
        sa.ForeignKeyConstraint(
            ["meta_lead_event_id"],
            ["meta_lead_events.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        sa.ForeignKeyConstraint(["recipient_user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "meta_lead_event_id",
            "recipient_user_id",
            name="uq_staff_lead_alerts_event_recipient",
        ),
    )
    op.create_index("ix_staff_lead_alerts_lead_id", "staff_lead_alerts", ["lead_id"])
    op.create_index(
        "ix_staff_lead_alerts_organization_id",
        "staff_lead_alerts",
        ["organization_id"],
    )
    op.create_index(
        "ix_staff_lead_alerts_meta_lead_event_id",
        "staff_lead_alerts",
        ["meta_lead_event_id"],
    )
    op.create_index(
        "ix_staff_lead_alerts_recipient_user_id",
        "staff_lead_alerts",
        ["recipient_user_id"],
    )
    op.create_index("ix_staff_lead_alerts_status", "staff_lead_alerts", ["status"])
    op.create_index(
        "ix_staff_lead_alerts_provider_message_id",
        "staff_lead_alerts",
        ["provider_message_id"],
    )
    op.create_index(
        "ix_staff_lead_alerts_org_status_due",
        "staff_lead_alerts",
        ["organization_id", "status", "next_attempt_at"],
    )


def downgrade() -> None:
    op.drop_table("staff_lead_alerts")
    op.drop_table("meta_lead_events")
    op.drop_column("users", "lead_alert_sms_enabled")
