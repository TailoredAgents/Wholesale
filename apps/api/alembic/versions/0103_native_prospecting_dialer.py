"""Add the native prospecting dialer foundation.

Revision ID: 0103_native_prospecting_dialer
Revises: 0102_address_only_website_leads
"""

from collections.abc import Sequence
from typing import Any

import sqlalchemy as sa

from alembic import op

revision: str = "0103_native_prospecting_dialer"
down_revision: str | None = "0102_address_only_website_leads"
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
    for table_name in ("organizations", "campaigns", "voice_lines"):
        op.add_column(
            table_name,
            sa.Column(
                "prospecting_dialer_max_concurrent_legs",
                sa.Integer(),
                server_default="1",
                nullable=False,
            ),
        )

    op.create_check_constraint(
        "ck_organizations_prospecting_dialer_leg_limit",
        "organizations",
        "prospecting_dialer_max_concurrent_legs BETWEEN 1 AND 3",
    )
    op.create_check_constraint(
        "ck_campaigns_prospecting_dialer_leg_limit",
        "campaigns",
        "prospecting_dialer_max_concurrent_legs BETWEEN 1 AND 3",
    )
    op.create_check_constraint(
        "ck_voice_lines_prospecting_dialer_leg_limit",
        "voice_lines",
        "prospecting_dialer_max_concurrent_legs BETWEEN 1 AND 3",
    )

    op.create_table(
        "prospecting_dialer_profiles",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("voice_line_id", sa.Uuid(), nullable=True),
        sa.Column("status", sa.String(length=40), server_default="inactive", nullable=False),
        sa.Column("default_line_count", sa.Integer(), server_default="1", nullable=False),
        sa.Column("max_line_count", sa.Integer(), server_default="1", nullable=False),
        sa.Column(
            "recording_policy",
            sa.String(length=80),
            server_default="company_policy",
            nullable=False,
        ),
        sa.Column("daily_dial_limit", sa.Integer(), nullable=True),
        sa.Column("daily_spend_limit_cents", sa.BigInteger(), nullable=True),
        sa.Column("profile_metadata", sa.JSON(), server_default=sa.text("'{}'"), nullable=False),
        sa.Column("created_by_user_id", sa.Uuid(), nullable=False),
        sa.Column("updated_by_user_id", sa.Uuid(), nullable=True),
        *_timestamp_columns(),
        sa.CheckConstraint(
            "status IN ('inactive', 'active', 'suspended')",
            name="ck_prospecting_dialer_profiles_status",
        ),
        sa.CheckConstraint(
            "default_line_count BETWEEN 1 AND 3",
            name="ck_prospecting_dialer_profiles_default_lines",
        ),
        sa.CheckConstraint(
            "max_line_count BETWEEN 1 AND 3",
            name="ck_prospecting_dialer_profiles_max_lines",
        ),
        sa.CheckConstraint(
            "default_line_count <= max_line_count",
            name="ck_prospecting_dialer_profiles_line_order",
        ),
        sa.CheckConstraint(
            "daily_dial_limit IS NULL OR daily_dial_limit > 0",
            name="ck_prospecting_dialer_profiles_daily_dials",
        ),
        sa.CheckConstraint(
            "daily_spend_limit_cents IS NULL OR daily_spend_limit_cents >= 0",
            name="ck_prospecting_dialer_profiles_daily_spend",
        ),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(
            ["voice_line_id"],
            ["voice_lines.id"],
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["updated_by_user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "organization_id",
            "user_id",
            name="uq_prospecting_dialer_profiles_org_user",
        ),
    )
    for column in (
        "organization_id",
        "user_id",
        "voice_line_id",
        "status",
        "created_by_user_id",
        "updated_by_user_id",
    ):
        op.create_index(
            f"ix_prospecting_dialer_profiles_{column}",
            "prospecting_dialer_profiles",
            [column],
        )

    op.create_table(
        "prospecting_dial_sessions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("dialer_profile_id", sa.Uuid(), nullable=False),
        sa.Column("caller_user_id", sa.Uuid(), nullable=False),
        sa.Column("campaign_id", sa.Uuid(), nullable=False),
        sa.Column("cohort_id", sa.Uuid(), nullable=True),
        sa.Column("prospect_calling_batch_id", sa.Uuid(), nullable=True),
        sa.Column("voice_line_id", sa.Uuid(), nullable=True),
        sa.Column("current_prospect_id", sa.Uuid(), nullable=True),
        sa.Column("current_batch_entry_id", sa.Uuid(), nullable=True),
        sa.Column("current_attempt_id", sa.Uuid(), nullable=True),
        sa.Column("state", sa.String(length=40), server_default="ready", nullable=False),
        sa.Column("requested_line_count", sa.Integer(), server_default="1", nullable=False),
        sa.Column("effective_line_count", sa.Integer(), server_default="1", nullable=False),
        sa.Column("organization_line_limit", sa.Integer(), server_default="1", nullable=False),
        sa.Column("va_line_limit", sa.Integer(), server_default="1", nullable=False),
        sa.Column("campaign_line_limit", sa.Integer(), server_default="1", nullable=False),
        sa.Column("voice_line_limit", sa.Integer(), server_default="1", nullable=False),
        sa.Column("feature_line_limit", sa.Integer(), server_default="1", nullable=False),
        sa.Column("idempotency_key", sa.String(length=255), nullable=False),
        sa.Column("browser_session_id", sa.String(length=255), nullable=True),
        sa.Column("provider_session_id", sa.String(length=255), nullable=True),
        sa.Column("lease_token", sa.String(length=255), nullable=True),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("paused_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("resumed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "heartbeat_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("stop_reason", sa.String(length=255), nullable=True),
        sa.Column("recovery_metadata", sa.JSON(), server_default=sa.text("'{}'"), nullable=False),
        sa.Column("metadata", sa.JSON(), server_default=sa.text("'{}'"), nullable=False),
        sa.Column("created_by_user_id", sa.Uuid(), nullable=False),
        sa.Column("updated_by_user_id", sa.Uuid(), nullable=True),
        *_timestamp_columns(),
        sa.CheckConstraint(
            "state IN ('ready', 'dialing', 'ringing', 'connected', 'wrap_up', "
            "'paused', 'reconnecting', 'ended', 'stopped', 'failed', 'expired')",
            name="ck_prospecting_dial_sessions_state",
        ),
        sa.CheckConstraint(
            "requested_line_count BETWEEN 1 AND 3",
            name="ck_prospecting_dial_sessions_requested_lines",
        ),
        sa.CheckConstraint(
            "effective_line_count BETWEEN 1 AND 3",
            name="ck_prospecting_dial_sessions_effective_lines",
        ),
        sa.CheckConstraint(
            "organization_line_limit BETWEEN 1 AND 3 "
            "AND va_line_limit BETWEEN 1 AND 3 "
            "AND campaign_line_limit BETWEEN 1 AND 3 "
            "AND voice_line_limit BETWEEN 1 AND 3 "
            "AND feature_line_limit BETWEEN 1 AND 3",
            name="ck_prospecting_dial_sessions_line_limits",
        ),
        sa.CheckConstraint(
            "effective_line_count <= requested_line_count "
            "AND effective_line_count <= organization_line_limit "
            "AND effective_line_count <= va_line_limit "
            "AND effective_line_count <= campaign_line_limit "
            "AND effective_line_count <= voice_line_limit "
            "AND effective_line_count <= feature_line_limit",
            name="ck_prospecting_dial_sessions_effective_cap",
        ),
        sa.CheckConstraint(
            "(state IN ('ended', 'stopped', 'failed', 'expired') "
            "AND ended_at IS NOT NULL) OR "
            "(state NOT IN ('ended', 'stopped', 'failed', 'expired') "
            "AND ended_at IS NULL)",
            name="ck_prospecting_dial_sessions_terminal_state",
        ),
        sa.CheckConstraint(
            "lease_expires_at IS NULL OR lease_token IS NOT NULL",
            name="ck_prospecting_dial_sessions_lease",
        ),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        sa.ForeignKeyConstraint(["dialer_profile_id"], ["prospecting_dialer_profiles.id"]),
        sa.ForeignKeyConstraint(["caller_user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["campaign_id"], ["campaigns.id"]),
        sa.ForeignKeyConstraint(["cohort_id"], ["prospecting_cohorts.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(
            ["prospect_calling_batch_id"],
            ["prospect_calling_batches.id"],
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(["voice_line_id"], ["voice_lines.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(
            ["current_prospect_id"],
            ["prospects.id"],
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["current_batch_entry_id"],
            ["prospect_calling_batch_entries.id"],
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["current_attempt_id"],
            ["prospecting_attempts.id"],
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["updated_by_user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "organization_id",
            "idempotency_key",
            name="uq_prospecting_dial_sessions_idempotency",
        ),
        sa.UniqueConstraint(
            "organization_id",
            "browser_session_id",
            name="uq_prospecting_dial_sessions_browser",
        ),
        sa.UniqueConstraint(
            "organization_id",
            "provider_session_id",
            name="uq_prospecting_dial_sessions_provider",
        ),
    )
    for column in (
        "organization_id",
        "dialer_profile_id",
        "caller_user_id",
        "campaign_id",
        "cohort_id",
        "prospect_calling_batch_id",
        "voice_line_id",
        "current_prospect_id",
        "current_batch_entry_id",
        "current_attempt_id",
        "state",
        "lease_expires_at",
        "heartbeat_at",
        "ended_at",
        "created_by_user_id",
        "updated_by_user_id",
    ):
        op.create_index(
            f"ix_prospecting_dial_sessions_{column}",
            "prospecting_dial_sessions",
            [column],
        )
    op.create_index(
        "uq_prospecting_dial_sessions_active_user",
        "prospecting_dial_sessions",
        ["organization_id", "caller_user_id"],
        unique=True,
        postgresql_where=sa.text("ended_at IS NULL"),
        sqlite_where=sa.text("ended_at IS NULL"),
    )

    op.create_table(
        "prospecting_dial_legs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("dial_session_id", sa.Uuid(), nullable=False),
        sa.Column("prospect_id", sa.Uuid(), nullable=False),
        sa.Column("batch_entry_id", sa.Uuid(), nullable=False),
        sa.Column("attempt_id", sa.Uuid(), nullable=True),
        sa.Column("contact_point_id", sa.Uuid(), nullable=True),
        sa.Column("voice_line_id", sa.Uuid(), nullable=True),
        sa.Column("call_record_id", sa.Uuid(), nullable=True),
        sa.Column("line_slot", sa.Integer(), server_default="1", nullable=False),
        sa.Column("recipient", sa.String(length=80), nullable=False),
        sa.Column("provider", sa.String(length=80), nullable=False),
        sa.Column("provider_call_id", sa.String(length=255), nullable=True),
        sa.Column("provider_recording_id", sa.String(length=255), nullable=True),
        sa.Column("idempotency_key", sa.String(length=255), nullable=False),
        sa.Column("status", sa.String(length=40), server_default="queued", nullable=False),
        sa.Column(
            "last_provider_event_sequence",
            sa.BigInteger(),
            server_default="0",
            nullable=False,
        ),
        sa.Column("last_provider_event_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "queued_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("dialing_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ringing_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("answered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("connected_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("failed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "answer_classification",
            sa.String(length=40),
            server_default="unknown",
            nullable=False,
        ),
        sa.Column(
            "party_classification",
            sa.String(length=40),
            server_default="unknown",
            nullable=False,
        ),
        sa.Column("terminal_result", sa.String(length=120), nullable=True),
        sa.Column("provider_error_code", sa.String(length=120), nullable=True),
        sa.Column("provider_error_message", sa.String(length=2000), nullable=True),
        sa.Column("cancellation_reason", sa.String(length=255), nullable=True),
        sa.Column("metadata", sa.JSON(), server_default=sa.text("'{}'"), nullable=False),
        *_timestamp_columns(),
        sa.CheckConstraint(
            "line_slot BETWEEN 1 AND 3",
            name="ck_prospecting_dial_legs_line_slot",
        ),
        sa.CheckConstraint(
            "status IN ('queued', 'dialing', 'ringing', 'answered', 'connected', "
            "'cancelling', 'cancelled', 'no_answer', 'busy', 'failed', 'completed')",
            name="ck_prospecting_dial_legs_status",
        ),
        sa.CheckConstraint(
            "last_provider_event_sequence >= 0",
            name="ck_prospecting_dial_legs_event_sequence",
        ),
        sa.CheckConstraint(
            "(status IN ('cancelled', 'no_answer', 'busy', 'failed', 'completed') "
            "AND completed_at IS NOT NULL) OR "
            "(status IN ('queued', 'dialing', 'ringing', 'answered', 'connected', "
            "'cancelling') AND completed_at IS NULL)",
            name="ck_prospecting_dial_legs_terminal_state",
        ),
        sa.CheckConstraint(
            "status <> 'connected' OR connected_at IS NOT NULL",
            name="ck_prospecting_dial_legs_connected_timestamp",
        ),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        sa.ForeignKeyConstraint(["dial_session_id"], ["prospecting_dial_sessions.id"]),
        sa.ForeignKeyConstraint(["prospect_id"], ["prospects.id"]),
        sa.ForeignKeyConstraint(["batch_entry_id"], ["prospect_calling_batch_entries.id"]),
        sa.ForeignKeyConstraint(
            ["attempt_id"],
            ["prospecting_attempts.id"],
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["contact_point_id"],
            ["prospect_contact_points.id"],
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(["voice_line_id"], ["voice_lines.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["call_record_id"], ["call_records.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "organization_id",
            "idempotency_key",
            name="uq_prospecting_dial_legs_org_idempotency",
        ),
        sa.UniqueConstraint(
            "organization_id",
            "provider",
            "provider_call_id",
            name="uq_prospecting_dial_legs_provider_call",
        ),
    )
    for column in (
        "organization_id",
        "dial_session_id",
        "prospect_id",
        "batch_entry_id",
        "attempt_id",
        "contact_point_id",
        "voice_line_id",
        "call_record_id",
        "provider",
        "provider_call_id",
        "provider_recording_id",
        "status",
        "completed_at",
        "answer_classification",
        "party_classification",
    ):
        op.create_index(
            f"ix_prospecting_dial_legs_{column}",
            "prospecting_dial_legs",
            [column],
        )
    for index_name, columns, predicate in (
        (
            "uq_prospecting_dial_legs_active_prospect",
            ["organization_id", "prospect_id"],
            "completed_at IS NULL",
        ),
        (
            "uq_prospecting_dial_legs_active_entry",
            ["batch_entry_id"],
            "completed_at IS NULL",
        ),
        (
            "uq_prospecting_dial_legs_active_slot",
            ["dial_session_id", "line_slot"],
            "completed_at IS NULL",
        ),
        (
            "uq_prospecting_dial_legs_connected_session",
            ["dial_session_id"],
            "connected_at IS NOT NULL AND completed_at IS NULL",
        ),
    ):
        op.create_index(
            index_name,
            "prospecting_dial_legs",
            columns,
            unique=True,
            postgresql_where=sa.text(predicate),
            sqlite_where=sa.text(predicate),
        )

    op.create_table(
        "prospecting_qualification_responses",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("attempt_id", sa.Uuid(), nullable=False),
        sa.Column("script_version_id", sa.Uuid(), nullable=False),
        sa.Column("question_key", sa.String(length=160), nullable=False),
        sa.Column(
            "state",
            sa.String(length=40),
            server_default="not_covered",
            nullable=False,
        ),
        sa.Column("answer_value", sa.JSON(), nullable=True),
        sa.Column("source", sa.String(length=40), server_default="va_entry", nullable=False),
        sa.Column("actor_user_id", sa.Uuid(), nullable=True),
        sa.Column("is_required", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("captured_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("transcript_evidence", sa.JSON(), nullable=True),
        sa.Column("metadata", sa.JSON(), server_default=sa.text("'{}'"), nullable=False),
        *_timestamp_columns(),
        sa.CheckConstraint(
            "state IN ('not_covered', 'answered', 'needs_follow_up', 'conflict')",
            name="ck_prospecting_qualification_responses_state",
        ),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        sa.ForeignKeyConstraint(
            ["attempt_id"],
            ["prospecting_attempts.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(["script_version_id"], ["prospecting_script_versions.id"]),
        sa.ForeignKeyConstraint(["actor_user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "attempt_id",
            "question_key",
            name="uq_prospecting_qualification_attempt_question",
        ),
    )
    for column in (
        "organization_id",
        "attempt_id",
        "script_version_id",
        "question_key",
        "state",
        "source",
        "actor_user_id",
    ):
        op.create_index(
            f"ix_prospecting_qualification_responses_{column}",
            "prospecting_qualification_responses",
            [column],
        )

    for new_column in (
        sa.Column("dial_session_id", sa.Uuid(), nullable=True),
        sa.Column("dial_leg_id", sa.Uuid(), nullable=True),
        sa.Column("provider_sequence_number", sa.BigInteger(), nullable=True),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("signature_verified", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("signature_fingerprint", sa.String(length=64), nullable=True),
        sa.Column("payload_sha256", sa.String(length=64), nullable=True),
    ):
        op.add_column("prospecting_provider_events", new_column)
    op.create_foreign_key(
        "fk_prospecting_provider_events_dial_session_id",
        "prospecting_provider_events",
        "prospecting_dial_sessions",
        ["dial_session_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        "fk_prospecting_provider_events_dial_leg_id",
        "prospecting_provider_events",
        "prospecting_dial_legs",
        ["dial_leg_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_prospecting_provider_events_dial_session_id",
        "prospecting_provider_events",
        ["dial_session_id"],
    )
    op.create_index(
        "ix_prospecting_provider_events_dial_leg_id",
        "prospecting_provider_events",
        ["dial_leg_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_prospecting_provider_events_dial_leg_id",
        table_name="prospecting_provider_events",
    )
    op.drop_index(
        "ix_prospecting_provider_events_dial_session_id",
        table_name="prospecting_provider_events",
    )
    op.drop_constraint(
        "fk_prospecting_provider_events_dial_leg_id",
        "prospecting_provider_events",
        type_="foreignkey",
    )
    op.drop_constraint(
        "fk_prospecting_provider_events_dial_session_id",
        "prospecting_provider_events",
        type_="foreignkey",
    )
    for column in (
        "payload_sha256",
        "signature_fingerprint",
        "signature_verified",
        "occurred_at",
        "provider_sequence_number",
        "dial_leg_id",
        "dial_session_id",
    ):
        op.drop_column("prospecting_provider_events", column)

    op.drop_table("prospecting_qualification_responses")
    op.drop_table("prospecting_dial_legs")
    op.drop_table("prospecting_dial_sessions")
    op.drop_table("prospecting_dialer_profiles")

    op.drop_constraint(
        "ck_voice_lines_prospecting_dialer_leg_limit",
        "voice_lines",
        type_="check",
    )
    op.drop_constraint(
        "ck_campaigns_prospecting_dialer_leg_limit",
        "campaigns",
        type_="check",
    )
    op.drop_constraint(
        "ck_organizations_prospecting_dialer_leg_limit",
        "organizations",
        type_="check",
    )
    for table_name in ("voice_lines", "campaigns", "organizations"):
        op.drop_column(table_name, "prospecting_dialer_max_concurrent_legs")
