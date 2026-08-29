"""Add the provider-neutral disposition handoff foundation.

Revision ID: 0119_disposition_provider
Revises: 0118_disposition_offer_room
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0119_disposition_provider"
down_revision: str | None = "0118_disposition_offer_room"
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
        "disposition_provider_accounts",
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("provider_key", sa.String(80), nullable=False),
        sa.Column("provider_label", sa.String(120), nullable=False),
        sa.Column("connection_mode", sa.String(40), nullable=False, server_default="manual"),
        sa.Column("status", sa.String(40), nullable=False, server_default="manual_ready"),
        sa.Column("capability_snapshot", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("created_by_user_id", sa.Uuid(), nullable=False),
        sa.Column("connected_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("id", sa.Uuid(), primary_key=True),
        *timestamps(),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"]),
        sa.UniqueConstraint(
            "organization_id",
            "provider_key",
            name="uq_disposition_provider_accounts_org_provider",
        ),
        sa.CheckConstraint(
            "connection_mode = 'manual'",
            name="ck_disposition_provider_accounts_manual_mode",
        ),
        sa.CheckConstraint(
            "status = 'manual_ready'",
            name="ck_disposition_provider_accounts_status",
        ),
    )
    op.create_index(
        op.f("ix_disposition_provider_accounts_organization_id"),
        "disposition_provider_accounts",
        ["organization_id"],
    )

    op.create_table(
        "disposition_provider_listings",
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("provider_account_id", sa.Uuid(), nullable=False),
        sa.Column("disposition_case_id", sa.Uuid(), nullable=False),
        sa.Column("property_id", sa.Uuid(), nullable=False),
        sa.Column("created_by_user_id", sa.Uuid(), nullable=False),
        sa.Column("status", sa.String(40), nullable=False, server_default="draft"),
        sa.Column("lock_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("package_version_id", sa.Uuid()),
        sa.Column("external_property_id", sa.String(255)),
        sa.Column("external_url", sa.Text()),
        sa.Column("provider_status", sa.String(40)),
        sa.Column("public_payload_sha256", sa.String(64)),
        sa.Column("package_source_fingerprint", sa.String(64)),
        sa.Column("manual_published_at", sa.DateTime(timezone=True)),
        sa.Column("last_refreshed_at", sa.DateTime(timezone=True)),
        sa.Column("disconnected_at", sa.DateTime(timezone=True)),
        sa.Column("disconnected_by_user_id", sa.Uuid()),
        sa.Column("disconnect_reason", sa.String(2000)),
        sa.Column("id", sa.Uuid(), primary_key=True),
        *timestamps(),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        sa.ForeignKeyConstraint(
            ["provider_account_id"],
            ["disposition_provider_accounts.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["disposition_case_id"], ["disposition_cases.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["property_id"], ["properties.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(
            ["package_version_id"],
            ["disposition_package_versions.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["disconnected_by_user_id"], ["users.id"], ondelete="SET NULL"
        ),
        sa.UniqueConstraint(
            "organization_id",
            "disposition_case_id",
            "provider_account_id",
            name="uq_disposition_provider_listings_case_account",
        ),
        sa.CheckConstraint(
            "status IN ('draft', 'release_approved', 'manual_published', 'disconnected')",
            name="ck_disposition_provider_listings_status",
        ),
        sa.CheckConstraint(
            "lock_version >= 1", name="ck_disposition_provider_listings_lock_version"
        ),
        sa.CheckConstraint(
            "provider_status IS NULL OR provider_status IN "
            "('draft', 'active', 'paused', 'under_contract', 'sold', 'archived', 'unknown')",
            name="ck_disposition_provider_listings_provider_status",
        ),
    )
    op.create_index(
        "ix_disposition_provider_listings_case_status",
        "disposition_provider_listings",
        ["organization_id", "disposition_case_id", "status"],
    )

    op.create_table(
        "disposition_provider_listing_revisions",
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("listing_id", sa.Uuid(), nullable=False),
        sa.Column("disposition_case_id", sa.Uuid(), nullable=False),
        sa.Column("package_version_id", sa.Uuid(), nullable=False),
        sa.Column("created_by_user_id", sa.Uuid(), nullable=False),
        sa.Column("approved_by_user_id", sa.Uuid()),
        sa.Column("revision_number", sa.Integer(), nullable=False),
        sa.Column("lock_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("status", sa.String(40), nullable=False),
        sa.Column("public_payload", sa.JSON(), nullable=False),
        sa.Column("public_payload_sha256", sa.String(64), nullable=False),
        sa.Column("package_source_fingerprint", sa.String(64), nullable=False),
        sa.Column("approval_reason", sa.String(2000)),
        sa.Column("approved_at", sa.DateTime(timezone=True)),
        sa.Column("id", sa.Uuid(), primary_key=True),
        *timestamps(),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        sa.ForeignKeyConstraint(
            ["listing_id"], ["disposition_provider_listings.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["disposition_case_id"], ["disposition_cases.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["package_version_id"],
            ["disposition_package_versions.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["approved_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.UniqueConstraint(
            "listing_id",
            "revision_number",
            name="uq_disposition_provider_revisions_listing_number",
        ),
        sa.CheckConstraint(
            "revision_number >= 1", name="ck_disposition_provider_revisions_number"
        ),
        sa.CheckConstraint(
            "lock_version >= 1", name="ck_disposition_provider_revisions_lock_version"
        ),
        sa.CheckConstraint(
            "status IN ('draft', 'approved', 'superseded')",
            name="ck_disposition_provider_revisions_status",
        ),
    )
    op.create_index(
        "ix_disposition_provider_revisions_case_status",
        "disposition_provider_listing_revisions",
        ["organization_id", "disposition_case_id", "status"],
    )

    op.create_table(
        "disposition_provider_source_links",
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("listing_id", sa.Uuid(), nullable=False),
        sa.Column("listing_revision_id", sa.Uuid(), nullable=False),
        sa.Column("created_by_user_id", sa.Uuid(), nullable=False),
        sa.Column("provider_key", sa.String(80), nullable=False),
        sa.Column("external_property_id", sa.String(255), nullable=False),
        sa.Column("external_url", sa.Text(), nullable=False),
        sa.Column("provider_status", sa.String(40), nullable=False),
        sa.Column("source_snapshot", sa.JSON(), nullable=False),
        sa.Column("source_snapshot_sha256", sa.String(64), nullable=False),
        sa.Column("idempotency_key", sa.String(120), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("note", sa.String(1000)),
        sa.Column("id", sa.Uuid(), primary_key=True),
        *timestamps(),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        sa.ForeignKeyConstraint(
            ["listing_id"], ["disposition_provider_listings.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["listing_revision_id"],
            ["disposition_provider_listing_revisions.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"]),
        sa.UniqueConstraint(
            "organization_id",
            "idempotency_key",
            name="uq_disposition_provider_source_links_idempotency",
        ),
        sa.CheckConstraint(
            "provider_status IN "
            "('draft', 'active', 'paused', 'under_contract', 'sold', 'archived', 'unknown')",
            name="ck_disposition_provider_source_links_status",
        ),
    )
    op.create_index(
        "ix_disposition_provider_source_links_listing_observed",
        "disposition_provider_source_links",
        ["listing_id", "observed_at"],
    )

    op.create_table(
        "disposition_provider_evidence",
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("listing_id", sa.Uuid(), nullable=False),
        sa.Column("disposition_case_id", sa.Uuid(), nullable=False),
        sa.Column("source_link_id", sa.Uuid()),
        sa.Column("recorded_by_user_id", sa.Uuid(), nullable=False),
        sa.Column("reviewed_by_user_id", sa.Uuid()),
        sa.Column("event_type", sa.String(40), nullable=False),
        sa.Column("external_event_id", sa.String(255)),
        sa.Column("idempotency_key", sa.String(120), nullable=False),
        sa.Column("review_status", sa.String(40), nullable=False, server_default="staged"),
        sa.Column("lock_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("buyer_name", sa.String(255)),
        sa.Column("buyer_email", sa.String(320)),
        sa.Column("buyer_phone", sa.String(80)),
        sa.Column("offer_amount_cents", sa.BigInteger()),
        sa.Column("message", sa.String(4000)),
        sa.Column("public_metadata", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("evidence_sha256", sa.String(64), nullable=False),
        sa.Column("review_note", sa.String(2000)),
        sa.Column("reviewed_at", sa.DateTime(timezone=True)),
        sa.Column("id", sa.Uuid(), primary_key=True),
        *timestamps(),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        sa.ForeignKeyConstraint(
            ["listing_id"], ["disposition_provider_listings.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["disposition_case_id"], ["disposition_cases.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["source_link_id"], ["disposition_provider_source_links.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(["recorded_by_user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["reviewed_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.UniqueConstraint(
            "organization_id",
            "idempotency_key",
            name="uq_disposition_provider_evidence_idempotency",
        ),
        sa.CheckConstraint(
            "event_type IN ('inquiry', 'offer', 'engagement')",
            name="ck_disposition_provider_evidence_event_type",
        ),
        sa.CheckConstraint(
            "review_status IN ('staged', 'reviewed', 'dismissed')",
            name="ck_disposition_provider_evidence_review_status",
        ),
        sa.CheckConstraint(
            "lock_version >= 1", name="ck_disposition_provider_evidence_lock_version"
        ),
        sa.CheckConstraint(
            "offer_amount_cents IS NULL OR offer_amount_cents > 0",
            name="ck_disposition_provider_evidence_offer_amount",
        ),
    )
    op.create_index(
        "ix_disposition_provider_evidence_case_review",
        "disposition_provider_evidence",
        ["organization_id", "disposition_case_id", "review_status", "occurred_at"],
    )

    op.create_table(
        "disposition_provider_sync_runs",
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("provider_account_id", sa.Uuid(), nullable=False),
        sa.Column("listing_id", sa.Uuid()),
        sa.Column("disposition_case_id", sa.Uuid(), nullable=False),
        sa.Column("requested_by_user_id", sa.Uuid(), nullable=False),
        sa.Column("operation", sa.String(80), nullable=False),
        sa.Column("status", sa.String(40), nullable=False),
        sa.Column("mode", sa.String(40), nullable=False, server_default="manual"),
        sa.Column("request_sha256", sa.String(64), nullable=False),
        sa.Column("result_summary", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("error_message", sa.String(2000)),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("id", sa.Uuid(), primary_key=True),
        *timestamps(),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        sa.ForeignKeyConstraint(
            ["provider_account_id"],
            ["disposition_provider_accounts.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["listing_id"], ["disposition_provider_listings.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["disposition_case_id"], ["disposition_cases.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["requested_by_user_id"], ["users.id"]),
        sa.CheckConstraint("mode = 'manual'", name="ck_disposition_provider_sync_runs_mode"),
        sa.CheckConstraint(
            "status IN ('completed', 'failed')",
            name="ck_disposition_provider_sync_runs_status",
        ),
    )
    op.create_index(
        "ix_disposition_provider_sync_runs_case_started",
        "disposition_provider_sync_runs",
        ["organization_id", "disposition_case_id", "started_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_disposition_provider_sync_runs_case_started",
        table_name="disposition_provider_sync_runs",
    )
    op.drop_table("disposition_provider_sync_runs")
    op.drop_index(
        "ix_disposition_provider_evidence_case_review",
        table_name="disposition_provider_evidence",
    )
    op.drop_table("disposition_provider_evidence")
    op.drop_index(
        "ix_disposition_provider_source_links_listing_observed",
        table_name="disposition_provider_source_links",
    )
    op.drop_table("disposition_provider_source_links")
    op.drop_index(
        "ix_disposition_provider_revisions_case_status",
        table_name="disposition_provider_listing_revisions",
    )
    op.drop_table("disposition_provider_listing_revisions")
    op.drop_index(
        "ix_disposition_provider_listings_case_status",
        table_name="disposition_provider_listings",
    )
    op.drop_table("disposition_provider_listings")
    op.drop_index(
        op.f("ix_disposition_provider_accounts_organization_id"),
        table_name="disposition_provider_accounts",
    )
    op.drop_table("disposition_provider_accounts")
