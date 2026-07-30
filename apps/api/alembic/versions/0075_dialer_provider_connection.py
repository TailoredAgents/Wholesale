"""Add provider-neutral dialer synchronization records.

Revision ID: 0075_dialer_provider
Revises: 0074_propstream_pipeline
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0075_dialer_provider"
down_revision: str | None = "0074_propstream_pipeline"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    for column in (
        sa.Column("provider", sa.String(80), nullable=True),
        sa.Column("provider_call_id", sa.String(255), nullable=True),
        sa.Column("provider_recording_id", sa.String(255), nullable=True),
        sa.Column("provider_agent_id", sa.String(255), nullable=True),
    ):
        op.add_column("prospecting_attempts", column)
    for column in ("provider", "provider_call_id", "provider_recording_id"):
        op.create_index(
            f"ix_prospecting_attempts_{column}",
            "prospecting_attempts",
            [column],
        )
    op.create_index(
        "uq_prospecting_attempts_provider_call",
        "prospecting_attempts",
        ["organization_id", "provider", "provider_call_id"],
        unique=True,
    )

    op.create_table(
        "prospecting_provider_campaigns",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("prospect_calling_batch_id", sa.Uuid(), nullable=False),
        sa.Column("provider", sa.String(80), nullable=False),
        sa.Column("provider_campaign_id", sa.String(255), nullable=True),
        sa.Column("mode", sa.String(40), nullable=False),
        sa.Column("status", sa.String(40), nullable=False),
        sa.Column("eligible_contact_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("synced_contact_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("failed_contact_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("retry_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("request_payload", sa.JSON(), nullable=False),
        sa.Column("response_payload", sa.JSON(), nullable=False),
        sa.Column("error_message", sa.String(2000), nullable=True),
        sa.Column("last_synced_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_reconciled_at", sa.DateTime(timezone=True), nullable=True),
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
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        sa.ForeignKeyConstraint(
            ["prospect_calling_batch_id"],
            ["prospect_calling_batches.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "prospect_calling_batch_id",
            name="uq_prospecting_provider_campaigns_batch",
        ),
        sa.UniqueConstraint(
            "organization_id",
            "provider",
            "provider_campaign_id",
            name="uq_prospecting_provider_campaigns_external",
        ),
    )
    for column in ("organization_id", "prospect_calling_batch_id", "provider", "status"):
        op.create_index(
            f"ix_prospecting_provider_campaigns_{column}",
            "prospecting_provider_campaigns",
            [column],
        )

    op.create_table(
        "prospecting_provider_contacts",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("provider_campaign_sync_id", sa.Uuid(), nullable=False),
        sa.Column("batch_entry_id", sa.Uuid(), nullable=False),
        sa.Column("prospect_id", sa.Uuid(), nullable=False),
        sa.Column("provider", sa.String(80), nullable=False),
        sa.Column("provider_contact_id", sa.String(255), nullable=True),
        sa.Column("status", sa.String(40), nullable=False),
        sa.Column("contact_payload", sa.JSON(), nullable=False),
        sa.Column("provider_metadata", sa.JSON(), nullable=False),
        sa.Column("last_event_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_message", sa.String(2000), nullable=True),
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
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        sa.ForeignKeyConstraint(
            ["provider_campaign_sync_id"],
            ["prospecting_provider_campaigns.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["batch_entry_id"],
            ["prospect_calling_batch_entries.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(["prospect_id"], ["prospects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "batch_entry_id",
            name="uq_prospecting_provider_contacts_entry",
        ),
        sa.UniqueConstraint(
            "organization_id",
            "provider",
            "provider_contact_id",
            name="uq_prospecting_provider_contacts_external",
        ),
    )
    for column in (
        "organization_id",
        "provider_campaign_sync_id",
        "batch_entry_id",
        "prospect_id",
        "provider",
        "status",
    ):
        op.create_index(
            f"ix_prospecting_provider_contacts_{column}",
            "prospecting_provider_contacts",
            [column],
        )

    op.create_table(
        "prospecting_provider_events",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("provider_campaign_sync_id", sa.Uuid(), nullable=True),
        sa.Column("provider_contact_sync_id", sa.Uuid(), nullable=True),
        sa.Column("batch_entry_id", sa.Uuid(), nullable=True),
        sa.Column("attempt_id", sa.Uuid(), nullable=True),
        sa.Column("provider", sa.String(80), nullable=False),
        sa.Column("external_event_id", sa.String(255), nullable=False),
        sa.Column("event_type", sa.String(120), nullable=False),
        sa.Column("processing_status", sa.String(40), nullable=False),
        sa.Column("provider_call_id", sa.String(255), nullable=True),
        sa.Column("provider_recording_id", sa.String(255), nullable=True),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("retry_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("error_message", sa.String(2000), nullable=True),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
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
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        sa.ForeignKeyConstraint(
            ["provider_campaign_sync_id"],
            ["prospecting_provider_campaigns.id"],
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["provider_contact_sync_id"],
            ["prospecting_provider_contacts.id"],
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["batch_entry_id"],
            ["prospect_calling_batch_entries.id"],
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["attempt_id"],
            ["prospecting_attempts.id"],
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "organization_id",
            "provider",
            "external_event_id",
            name="uq_prospecting_provider_events_external",
        ),
    )
    for column in (
        "organization_id",
        "provider_campaign_sync_id",
        "provider_contact_sync_id",
        "batch_entry_id",
        "attempt_id",
        "provider",
        "event_type",
        "processing_status",
        "provider_call_id",
        "provider_recording_id",
    ):
        op.create_index(
            f"ix_prospecting_provider_events_{column}",
            "prospecting_provider_events",
            [column],
        )


def downgrade() -> None:
    op.drop_table("prospecting_provider_events")
    op.drop_table("prospecting_provider_contacts")
    op.drop_table("prospecting_provider_campaigns")
    op.drop_index(
        "uq_prospecting_attempts_provider_call",
        table_name="prospecting_attempts",
    )
    for column in ("provider_recording_id", "provider_call_id", "provider"):
        op.drop_index(
            f"ix_prospecting_attempts_{column}",
            table_name="prospecting_attempts",
        )
    for column in (
        "provider_agent_id",
        "provider_recording_id",
        "provider_call_id",
        "provider",
    ):
        op.drop_column("prospecting_attempts", column)
