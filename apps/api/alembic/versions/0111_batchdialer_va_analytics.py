"""Add normalized BatchDialer call facts and explicit agent identities.

Revision ID: 0111_batchdialer_va_facts
Revises: 0110_batchdialer_direct_sync
"""

from collections.abc import Sequence
from typing import Any

import sqlalchemy as sa

from alembic import op

revision: str = "0111_batchdialer_va_facts"
down_revision: str | None = "0110_batchdialer_direct_sync"
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
        "batchdialer_agent_identities",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("provider_agent_id", sa.String(length=255), nullable=False),
        sa.Column("first_name", sa.String(length=255), nullable=True),
        sa.Column("last_name", sa.String(length=255), nullable=True),
        sa.Column("display_name", sa.String(length=255), nullable=True),
        sa.Column("mapped_user_id", sa.Uuid(), nullable=True),
        sa.Column("mapped_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("mapped_at", sa.DateTime(timezone=True), nullable=True),
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
        sa.Column(
            "provider_snapshot",
            sa.JSON(),
            server_default=sa.text("'{}'"),
            nullable=False,
        ),
        *_timestamp_columns(),
        sa.CheckConstraint(
            "length(trim(provider_agent_id)) > 0",
            name="ck_batchdialer_agent_identities_provider_id",
        ),
        sa.CheckConstraint(
            "mapped_user_id IS NULL OR mapped_at IS NOT NULL",
            name="ck_batchdialer_agent_identities_explicit_mapping",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name="fk_batchdialer_agent_identities_organization",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["mapped_user_id"],
            ["users.id"],
            name="fk_batchdialer_agent_identities_mapped_user",
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["mapped_by_user_id"],
            ["users.id"],
            name="fk_batchdialer_agent_identities_mapped_by_user",
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "organization_id",
            "provider_agent_id",
            name="uq_batchdialer_agent_identities_org_provider",
        ),
        sa.UniqueConstraint(
            "organization_id",
            "mapped_user_id",
            name="uq_batchdialer_agent_identities_org_mapped_user",
        ),
    )
    op.create_index(
        "ix_batchdialer_agent_identities_org_last_seen",
        "batchdialer_agent_identities",
        ["organization_id", "last_seen_at"],
    )

    op.create_table(
        "batchdialer_call_facts",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("provider_event_id", sa.Uuid(), nullable=False),
        sa.Column("agent_identity_id", sa.Uuid(), nullable=True),
        sa.Column("lead_id", sa.Uuid(), nullable=True),
        sa.Column("call_record_id", sa.Uuid(), nullable=True),
        sa.Column("provider_cdr_id", sa.String(length=255), nullable=False),
        sa.Column("provider_call_id", sa.String(length=255), nullable=True),
        sa.Column("provider_contact_id", sa.String(length=255), nullable=True),
        sa.Column("provider_campaign_id", sa.String(length=255), nullable=True),
        sa.Column("provider_campaign_name", sa.String(length=255), nullable=True),
        sa.Column("provider_agent_id", sa.String(length=255), nullable=True),
        sa.Column("provider_agent_name", sa.String(length=255), nullable=True),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("duration_seconds", sa.Integer(), nullable=True),
        sa.Column(
            "direction",
            sa.String(length=40),
            server_default="outbound",
            nullable=False,
        ),
        sa.Column("provider_status", sa.String(length=80), nullable=True),
        sa.Column("raw_disposition", sa.String(length=255), nullable=True),
        sa.Column(
            "disposition_classification",
            sa.String(length=40),
            server_default="unknown",
            nullable=False,
        ),
        sa.Column("final_outcome", sa.String(length=80), nullable=True),
        sa.Column("final_qualification_status", sa.String(length=80), nullable=True),
        sa.Column("mood", sa.String(length=80), nullable=True),
        sa.Column("is_voicemail", sa.Boolean(), server_default="false", nullable=False),
        sa.Column(
            "recording_available", sa.Boolean(), server_default="false", nullable=False
        ),
        sa.Column("transcript_status", sa.String(length=80), nullable=True),
        sa.Column(
            "transcript_available", sa.Boolean(), server_default="false", nullable=False
        ),
        sa.Column(
            "qualification_evidence_present",
            sa.Boolean(),
            server_default="false",
            nullable=False,
        ),
        sa.Column(
            "lead_created_by_event",
            sa.Boolean(),
            server_default="false",
            nullable=False,
        ),
        sa.Column("source_payload_sha256", sa.String(length=64), nullable=True),
        sa.Column(
            "normalization_version",
            sa.String(length=80),
            server_default="batchdialer_call_fact_v1",
            nullable=False,
        ),
        sa.Column(
            "final_processing_status",
            sa.String(length=40),
            server_default="pending",
            nullable=False,
        ),
        *_timestamp_columns(),
        sa.CheckConstraint(
            "length(trim(provider_cdr_id)) > 0",
            name="ck_batchdialer_call_facts_provider_cdr",
        ),
        sa.CheckConstraint(
            "duration_seconds IS NULL OR duration_seconds >= 0",
            name="ck_batchdialer_call_facts_duration",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name="fk_batchdialer_call_facts_organization",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["provider_event_id"],
            ["prospecting_provider_events.id"],
            name="fk_batchdialer_call_facts_provider_event",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["agent_identity_id"],
            ["batchdialer_agent_identities.id"],
            name="fk_batchdialer_call_facts_agent_identity",
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["lead_id"],
            ["leads.id"],
            name="fk_batchdialer_call_facts_lead",
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["call_record_id"],
            ["call_records.id"],
            name="fk_batchdialer_call_facts_call_record",
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "provider_event_id",
            name="uq_batchdialer_call_facts_provider_event",
        ),
        sa.UniqueConstraint(
            "organization_id",
            "provider_cdr_id",
            name="uq_batchdialer_call_facts_org_cdr",
        ),
    )
    op.create_index(
        "ix_batchdialer_call_facts_org_started",
        "batchdialer_call_facts",
        ["organization_id", "started_at"],
    )
    op.create_index(
        "ix_batchdialer_call_facts_org_activity",
        "batchdialer_call_facts",
        [
            "organization_id",
            sa.text("COALESCE(started_at, occurred_at, received_at)"),
        ],
    )
    op.create_index(
        "ix_batchdialer_call_facts_org_agent_started",
        "batchdialer_call_facts",
        ["organization_id", "provider_agent_id", "started_at"],
    )
    op.create_index(
        "ix_batchdialer_call_facts_org_campaign_started",
        "batchdialer_call_facts",
        ["organization_id", "provider_campaign_id", "started_at"],
    )
    op.create_index(
        "ix_batchdialer_call_facts_org_qualification",
        "batchdialer_call_facts",
        ["organization_id", "final_qualification_status"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_batchdialer_call_facts_org_qualification",
        table_name="batchdialer_call_facts",
    )
    op.drop_index(
        "ix_batchdialer_call_facts_org_campaign_started",
        table_name="batchdialer_call_facts",
    )
    op.drop_index(
        "ix_batchdialer_call_facts_org_agent_started",
        table_name="batchdialer_call_facts",
    )
    op.drop_index(
        "ix_batchdialer_call_facts_org_started",
        table_name="batchdialer_call_facts",
    )
    op.drop_index(
        "ix_batchdialer_call_facts_org_activity",
        table_name="batchdialer_call_facts",
    )
    op.drop_table("batchdialer_call_facts")

    op.drop_index(
        "ix_batchdialer_agent_identities_org_last_seen",
        table_name="batchdialer_agent_identities",
    )
    op.drop_table("batchdialer_agent_identities")
