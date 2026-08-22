"""Add durable state for the direct BatchDialer integration.

Revision ID: 0110_batchdialer_direct_sync
Revises: 0109_prospecting_acceptance
"""

from collections.abc import Sequence
from typing import Any

import sqlalchemy as sa

from alembic import op

revision: str = "0110_batchdialer_direct_sync"
down_revision: str | None = "0109_prospecting_acceptance"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _timestamp_columns() -> tuple[sa.Column[Any], sa.Column[Any]]:
    return (
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
    )


def upgrade() -> None:
    op.create_table(
        "batchdialer_sync_checkpoints",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("stream", sa.String(length=80), server_default="cdrs", nullable=False),
        sa.Column("status", sa.String(length=40), server_default="idle", nullable=False),
        sa.Column("lease_token", sa.String(length=64), nullable=True),
        sa.Column("lease_owner", sa.String(length=255), nullable=True),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("next_poll_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("scan_date", sa.Date(), nullable=True),
        sa.Column("next_page_cursor", sa.String(length=4000), nullable=True),
        sa.Column("last_attempt_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_success_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_campaign_refresh_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column(
            "consecutive_failure_count", sa.Integer(), server_default="0", nullable=False
        ),
        sa.Column("poll_count", sa.BigInteger(), server_default="0", nullable=False),
        sa.Column("success_count", sa.BigInteger(), server_default="0", nullable=False),
        sa.Column("failure_count", sa.BigInteger(), server_default="0", nullable=False),
        sa.Column("fetched_cdr_count", sa.BigInteger(), server_default="0", nullable=False),
        sa.Column("archived_event_count", sa.BigInteger(), server_default="0", nullable=False),
        sa.Column("updated_event_count", sa.BigInteger(), server_default="0", nullable=False),
        sa.Column("qualified_event_count", sa.BigInteger(), server_default="0", nullable=False),
        sa.Column(
            "quarantined_event_count", sa.BigInteger(), server_default="0", nullable=False
        ),
        sa.Column("sync_metadata", sa.JSON(), server_default=sa.text("'{}'"), nullable=False),
        *_timestamp_columns(),
        sa.CheckConstraint(
            "length(trim(stream)) > 0",
            name="ck_batchdialer_sync_checkpoints_stream",
        ),
        sa.CheckConstraint(
            "(lease_token IS NULL AND lease_owner IS NULL AND lease_expires_at IS NULL) OR "
            "(lease_token IS NOT NULL AND lease_owner IS NOT NULL "
            "AND lease_expires_at IS NOT NULL)",
            name="ck_batchdialer_sync_checkpoints_lease",
        ),
        sa.CheckConstraint(
            "consecutive_failure_count >= 0 AND poll_count >= 0 "
            "AND success_count >= 0 AND failure_count >= 0 "
            "AND fetched_cdr_count >= 0 AND archived_event_count >= 0 "
            "AND updated_event_count >= 0 AND qualified_event_count >= 0 "
            "AND quarantined_event_count >= 0",
            name="ck_batchdialer_sync_checkpoints_counters",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name="fk_batchdialer_sync_checkpoints_organization",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "organization_id",
            "stream",
            name="uq_batchdialer_sync_checkpoints_org_stream",
        ),
    )
    op.create_index(
        "ix_batchdialer_sync_checkpoints_due",
        "batchdialer_sync_checkpoints",
        ["stream", "next_poll_at"],
    )
    op.create_index(
        "ix_batchdialer_sync_checkpoints_lease",
        "batchdialer_sync_checkpoints",
        ["stream", "lease_expires_at"],
    )

    op.create_table(
        "batchdialer_campaigns",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("provider_campaign_id", sa.String(length=255), nullable=False),
        sa.Column("parent_campaign_id", sa.String(length=255), nullable=True),
        sa.Column("external_campaign_id", sa.String(length=255), nullable=True),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("mode", sa.String(length=80), nullable=True),
        sa.Column("status", sa.String(length=40), server_default="unknown", nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("recycle_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("hierarchy_level", sa.Integer(), server_default="0", nullable=False),
        sa.Column("contact_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("cdr_seen_count", sa.BigInteger(), server_default="0", nullable=False),
        sa.Column("qualified_cdr_count", sa.BigInteger(), server_default="0", nullable=False),
        sa.Column("imported_lead_count", sa.BigInteger(), server_default="0", nullable=False),
        sa.Column("provider_created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "first_seen_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "last_seen_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("last_cdr_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("provider_snapshot", sa.JSON(), server_default=sa.text("'{}'"), nullable=False),
        *_timestamp_columns(),
        sa.CheckConstraint(
            "length(trim(provider_campaign_id)) > 0 AND length(trim(name)) > 0",
            name="ck_batchdialer_campaigns_identity",
        ),
        sa.CheckConstraint(
            "recycle_count >= 0 AND hierarchy_level >= 0 AND contact_count >= 0 "
            "AND cdr_seen_count >= 0 AND qualified_cdr_count >= 0 "
            "AND imported_lead_count >= 0",
            name="ck_batchdialer_campaigns_counters",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name="fk_batchdialer_campaigns_organization",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "organization_id",
            "provider_campaign_id",
            name="uq_batchdialer_campaigns_org_provider",
        ),
    )
    op.create_index(
        "ix_batchdialer_campaigns_org_active_status",
        "batchdialer_campaigns",
        ["organization_id", "is_active", "status"],
    )
    op.create_index(
        "ix_batchdialer_campaigns_org_last_cdr",
        "batchdialer_campaigns",
        ["organization_id", "last_cdr_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_batchdialer_campaigns_org_last_cdr",
        table_name="batchdialer_campaigns",
    )
    op.drop_index(
        "ix_batchdialer_campaigns_org_active_status",
        table_name="batchdialer_campaigns",
    )
    op.drop_table("batchdialer_campaigns")

    op.drop_index(
        "ix_batchdialer_sync_checkpoints_lease",
        table_name="batchdialer_sync_checkpoints",
    )
    op.drop_index(
        "ix_batchdialer_sync_checkpoints_due",
        table_name="batchdialer_sync_checkpoints",
    )
    op.drop_table("batchdialer_sync_checkpoints")
