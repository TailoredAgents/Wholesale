"""Add governed disposition outreach revisions, deliveries, and reply links.

Revision ID: 0117_disposition_outreach
Revises: 0116_disposition_package
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0117_disposition_outreach"
down_revision: str | None = "0116_disposition_package"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def timestamps() -> tuple[sa.Column[object], sa.Column[object]]:
    return (
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
    )


def upgrade() -> None:
    op.create_table(
        "disposition_outreach_revisions",
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("disposition_campaign_id", sa.Uuid(), nullable=False),
        sa.Column("disposition_case_id", sa.Uuid(), nullable=False),
        sa.Column("package_version_id", sa.Uuid(), nullable=False),
        sa.Column("created_by_user_id", sa.Uuid(), nullable=False),
        sa.Column("approved_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("revision_number", sa.Integer(), nullable=False),
        sa.Column("lock_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("status", sa.String(length=40), nullable=False, server_default="draft"),
        sa.Column(
            "mode",
            sa.String(length=40),
            nullable=False,
            server_default="supervised",
        ),
        sa.Column("recipient_cap", sa.Integer(), nullable=False),
        sa.Column("recipient_manifest_hash", sa.String(length=64), nullable=False),
        sa.Column("approval_hash", sa.String(length=64), nullable=True),
        sa.Column("package_source_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("artifact_sha256", sa.String(length=64), nullable=False),
        sa.Column("email_sender_alias_id", sa.Uuid(), nullable=True),
        sa.Column("sms_voice_line_id", sa.Uuid(), nullable=True),
        sa.Column("sender_snapshot", sa.JSON(), nullable=False),
        sa.Column("approval_reason", sa.String(length=2000), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("queued_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("paused_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.Uuid(), primary_key=True),
        *timestamps(),
        sa.CheckConstraint(
            "revision_number >= 1",
            name="ck_disposition_outreach_revisions_revision_number",
        ),
        sa.CheckConstraint(
            "lock_version >= 1",
            name="ck_disposition_outreach_revisions_lock_version",
        ),
        sa.CheckConstraint(
            "recipient_cap >= 1",
            name="ck_disposition_outreach_revisions_recipient_cap",
        ),
        sa.CheckConstraint(
            "mode = 'supervised'",
            name="ck_disposition_outreach_revisions_supervised_mode",
        ),
        sa.CheckConstraint(
            "status IN ('draft', 'review_required', 'approved', 'queued', 'sending', "
            "'paused', 'provider_degraded', 'completed', 'completed_with_failures', "
            "'cancelled', 'invalidated')",
            name="ck_disposition_outreach_revisions_status",
        ),
        sa.CheckConstraint(
            "length(recipient_manifest_hash) = 64",
            name="ck_disposition_outreach_revisions_manifest_hash",
        ),
        sa.CheckConstraint(
            "approval_hash IS NULL OR length(approval_hash) = 64",
            name="ck_disposition_outreach_revisions_approval_hash",
        ),
        sa.CheckConstraint(
            "length(package_source_fingerprint) = 64",
            name="ck_disposition_outreach_revisions_source_fingerprint",
        ),
        sa.CheckConstraint(
            "length(artifact_sha256) = 64",
            name="ck_disposition_outreach_revisions_artifact_hash",
        ),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        sa.ForeignKeyConstraint(
            ["disposition_campaign_id"],
            ["disposition_campaigns.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["disposition_case_id"],
            ["disposition_cases.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["package_version_id"],
            ["disposition_package_versions.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(
            ["approved_by_user_id"], ["users.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["email_sender_alias_id"],
            ["email_sender_aliases.id"],
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["sms_voice_line_id"], ["voice_lines.id"], ondelete="SET NULL"
        ),
        sa.UniqueConstraint(
            "disposition_campaign_id",
            "revision_number",
            name="uq_disposition_outreach_revisions_campaign_revision",
        ),
    )
    op.create_index(
        "ix_disposition_outreach_revisions_campaign_status",
        "disposition_outreach_revisions",
        ["organization_id", "disposition_campaign_id", "status"],
    )
    op.create_index(
        "ix_disposition_outreach_revisions_case_status",
        "disposition_outreach_revisions",
        ["organization_id", "disposition_case_id", "status"],
    )

    op.create_table(
        "disposition_outreach_deliveries",
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("outreach_revision_id", sa.Uuid(), nullable=False),
        sa.Column("disposition_campaign_id", sa.Uuid(), nullable=False),
        sa.Column("disposition_case_id", sa.Uuid(), nullable=False),
        sa.Column("package_version_id", sa.Uuid(), nullable=False),
        sa.Column("disposition_campaign_recipient_id", sa.Uuid(), nullable=False),
        sa.Column("buyer_id", sa.Uuid(), nullable=False),
        sa.Column("contact_id", sa.Uuid(), nullable=True),
        sa.Column("conversation_id", sa.Uuid(), nullable=True),
        sa.Column("channel", sa.String(length=40), nullable=False),
        sa.Column("normalized_destination", sa.String(length=320), nullable=False),
        sa.Column("captured_destination", sa.String(length=320), nullable=False),
        sa.Column("captured_identity", sa.JSON(), nullable=False),
        sa.Column("subject", sa.String(length=255), nullable=True),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("body_hash", sa.String(length=64), nullable=False),
        sa.Column("idempotency_key", sa.String(length=120), nullable=False),
        sa.Column("eligibility_status", sa.String(length=40), nullable=False),
        sa.Column("eligibility_snapshot", sa.JSON(), nullable=False),
        sa.Column("exclusion_reason", sa.String(length=2000), nullable=True),
        sa.Column(
            "status",
            sa.String(length=40),
            nullable=False,
            server_default="prepared",
        ),
        sa.Column("provider", sa.String(length=80), nullable=True),
        sa.Column("provider_message_id", sa.String(length=255), nullable=True),
        sa.Column("communication_record_id", sa.Uuid(), nullable=True),
        sa.Column("communication_dispatch_id", sa.Uuid(), nullable=True),
        sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("processing_started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("processing_token", sa.Uuid(), nullable=True),
        sa.Column("provider_accepted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("delivered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("replied_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("failed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_code", sa.String(length=120), nullable=True),
        sa.Column("error_message", sa.String(length=2000), nullable=True),
        sa.Column("id", sa.Uuid(), primary_key=True),
        *timestamps(),
        sa.CheckConstraint(
            "channel IN ('email', 'sms')",
            name="ck_disposition_outreach_deliveries_channel",
        ),
        sa.CheckConstraint(
            "eligibility_status IN ('eligible', 'ineligible')",
            name="ck_disposition_outreach_deliveries_eligibility",
        ),
        sa.CheckConstraint(
            "status IN ('prepared', 'ineligible', 'approved', 'queued', 'claimed', "
            "'provider_accepted', 'sent', 'delivered', 'replied', 'failed_retryable', "
            "'failed_terminal', 'delivery_unknown', 'suppressed', 'opted_out', "
            "'cancelled')",
            name="ck_disposition_outreach_deliveries_status",
        ),
        sa.CheckConstraint(
            "attempt_count >= 0",
            name="ck_disposition_outreach_deliveries_attempt_count",
        ),
        sa.CheckConstraint(
            "length(body_hash) = 64",
            name="ck_disposition_outreach_deliveries_body_hash",
        ),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        sa.ForeignKeyConstraint(
            ["outreach_revision_id"],
            ["disposition_outreach_revisions.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["disposition_campaign_id"],
            ["disposition_campaigns.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["disposition_case_id"],
            ["disposition_cases.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["package_version_id"],
            ["disposition_package_versions.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["disposition_campaign_recipient_id"],
            ["disposition_campaign_recipients.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(["buyer_id"], ["buyers.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["contact_id"], ["contacts.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(
            ["conversation_id"], ["conversations.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["communication_record_id"],
            ["communication_records.id"],
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["communication_dispatch_id"],
            ["communication_dispatches.id"],
            ondelete="SET NULL",
        ),
        sa.UniqueConstraint(
            "organization_id",
            "idempotency_key",
            name="uq_disposition_outreach_deliveries_org_idempotency",
        ),
        sa.UniqueConstraint(
            "outreach_revision_id",
            "buyer_id",
            "channel",
            name="uq_disposition_outreach_deliveries_revision_buyer_channel",
        ),
        sa.UniqueConstraint(
            "outreach_revision_id",
            "channel",
            "normalized_destination",
            name="uq_disposition_outreach_deliveries_revision_channel_destination",
        ),
        sa.UniqueConstraint(
            "organization_id",
            "provider",
            "provider_message_id",
            name="uq_disposition_outreach_deliveries_org_provider_message",
        ),
    )
    op.create_index(
        "ix_disposition_outreach_deliveries_worker_claim",
        "disposition_outreach_deliveries",
        [
            "organization_id",
            "status",
            "next_attempt_at",
            "processing_started_at",
            "created_at",
        ],
    )
    op.create_index(
        "ix_disposition_outreach_deliveries_case_status",
        "disposition_outreach_deliveries",
        ["organization_id", "disposition_case_id", "status"],
    )
    op.create_index(
        "ix_disposition_outreach_deliveries_campaign_status",
        "disposition_outreach_deliveries",
        ["organization_id", "disposition_campaign_id", "status"],
    )
    op.create_index(
        "ix_disposition_outreach_deliveries_conversation_channel",
        "disposition_outreach_deliveries",
        ["organization_id", "conversation_id", "channel", "status"],
    )

    op.create_table(
        "disposition_reply_links",
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("communication_record_id", sa.Uuid(), nullable=False),
        sa.Column("outreach_delivery_id", sa.Uuid(), nullable=True),
        sa.Column("outreach_revision_id", sa.Uuid(), nullable=True),
        sa.Column("disposition_campaign_id", sa.Uuid(), nullable=True),
        sa.Column("disposition_case_id", sa.Uuid(), nullable=True),
        sa.Column("buyer_id", sa.Uuid(), nullable=True),
        sa.Column("task_id", sa.Uuid(), nullable=True),
        sa.Column("routing_status", sa.String(length=40), nullable=False),
        sa.Column("routing_confidence", sa.Integer(), nullable=False),
        sa.Column(
            "reply_classification",
            sa.String(length=80),
            nullable=False,
            server_default="needs_review",
        ),
        sa.Column("linked_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("id", sa.Uuid(), primary_key=True),
        *timestamps(),
        sa.CheckConstraint(
            "routing_status IN ('matched', 'ambiguous', 'needs_review')",
            name="ck_disposition_reply_links_routing_status",
        ),
        sa.CheckConstraint(
            "routing_confidence BETWEEN 0 AND 100",
            name="ck_disposition_reply_links_routing_confidence",
        ),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        sa.ForeignKeyConstraint(
            ["communication_record_id"],
            ["communication_records.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["outreach_delivery_id"],
            ["disposition_outreach_deliveries.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["outreach_revision_id"],
            ["disposition_outreach_revisions.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["disposition_campaign_id"],
            ["disposition_campaigns.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["disposition_case_id"],
            ["disposition_cases.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(["buyer_id"], ["buyers.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["task_id"], ["tasks.id"], ondelete="SET NULL"),
        sa.UniqueConstraint(
            "communication_record_id",
            name="uq_disposition_reply_links_communication",
        ),
    )
    op.create_index(
        "ix_disposition_reply_links_case_routing",
        "disposition_reply_links",
        ["organization_id", "disposition_case_id", "routing_status", "linked_at"],
    )
    op.create_index(
        "ix_disposition_reply_links_delivery",
        "disposition_reply_links",
        ["outreach_delivery_id", "linked_at"],
    )
    op.create_index(
        "ix_disposition_reply_links_campaign",
        "disposition_reply_links",
        ["disposition_campaign_id", "linked_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_disposition_reply_links_campaign",
        table_name="disposition_reply_links",
    )
    op.drop_index(
        "ix_disposition_reply_links_delivery",
        table_name="disposition_reply_links",
    )
    op.drop_index(
        "ix_disposition_reply_links_case_routing",
        table_name="disposition_reply_links",
    )
    op.drop_table("disposition_reply_links")

    op.drop_index(
        "ix_disposition_outreach_deliveries_conversation_channel",
        table_name="disposition_outreach_deliveries",
    )
    op.drop_index(
        "ix_disposition_outreach_deliveries_campaign_status",
        table_name="disposition_outreach_deliveries",
    )
    op.drop_index(
        "ix_disposition_outreach_deliveries_case_status",
        table_name="disposition_outreach_deliveries",
    )
    op.drop_index(
        "ix_disposition_outreach_deliveries_worker_claim",
        table_name="disposition_outreach_deliveries",
    )
    op.drop_table("disposition_outreach_deliveries")

    op.drop_index(
        "ix_disposition_outreach_revisions_case_status",
        table_name="disposition_outreach_revisions",
    )
    op.drop_index(
        "ix_disposition_outreach_revisions_campaign_status",
        table_name="disposition_outreach_revisions",
    )
    op.drop_table("disposition_outreach_revisions")
