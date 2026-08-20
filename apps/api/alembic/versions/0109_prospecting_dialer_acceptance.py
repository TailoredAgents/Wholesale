"""Add durable D10 native-dialer production acceptance evidence.

Revision ID: 0109_prospecting_acceptance
Revises: 0108_prospecting_callbacks
"""

from collections.abc import Sequence
from typing import Any

import sqlalchemy as sa

from alembic import op

revision: str = "0109_prospecting_acceptance"
down_revision: str | None = "0108_prospecting_callbacks"
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
    op.add_column(
        "organizations",
        sa.Column(
            "prospecting_dialer_acceptance_required",
            sa.Boolean(),
            server_default="true",
            nullable=False,
        ),
    )

    op.create_table(
        "prospecting_dialer_pilots",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("caller_user_id", sa.Uuid(), nullable=False),
        sa.Column("campaign_id", sa.Uuid(), nullable=False),
        sa.Column("cohort_id", sa.Uuid(), nullable=False),
        sa.Column("prospect_calling_batch_id", sa.Uuid(), nullable=False),
        sa.Column("voice_line_id", sa.Uuid(), nullable=False),
        sa.Column("status", sa.String(length=40), server_default="draft", nullable=False),
        sa.Column("revision", sa.Integer(), server_default="1", nullable=False),
        sa.Column("effective_line_count", sa.Integer(), server_default="1", nullable=False),
        sa.Column(
            "timezone",
            sa.String(length=80),
            server_default="America/New_York",
            nullable=False,
        ),
        sa.Column("required_clean_shift_count", sa.Integer(), server_default="3", nullable=False),
        sa.Column("minimum_attempts_per_shift", sa.Integer(), server_default="25", nullable=False),
        sa.Column(
            "minimum_productive_minutes_per_shift",
            sa.Integer(),
            server_default="60",
            nullable=False,
        ),
        sa.Column("minimum_total_attempts", sa.Integer(), server_default="75", nullable=False),
        sa.Column("minimum_batch_size", sa.Integer(), server_default="75", nullable=False),
        sa.Column("maximum_batch_size", sa.Integer(), server_default="250", nullable=False),
        sa.Column("daily_dial_limit", sa.Integer(), server_default="50", nullable=False),
        sa.Column(
            "daily_spend_limit_cents",
            sa.BigInteger(),
            server_default="1000",
            nullable=False,
        ),
        sa.Column("configuration_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("start_attestation", sa.JSON(), server_default=sa.text("'{}'"), nullable=False),
        sa.Column("smoke_test_evidence", sa.JSON(), server_default=sa.text("'{}'"), nullable=False),
        sa.Column(
            "kill_switch_evidence", sa.JSON(), server_default=sa.text("'{}'"), nullable=False
        ),
        sa.Column(
            "batchdialer_comparison_evidence",
            sa.JSON(),
            server_default=sa.text("'{}'"),
            nullable=False,
        ),
        sa.Column("rollback_evidence", sa.JSON(), server_default=sa.text("'{}'"), nullable=False),
        sa.Column(
            "final_evidence_snapshot",
            sa.JSON(),
            server_default=sa.text("'{}'"),
            nullable=False,
        ),
        sa.Column("evidence_hash", sa.String(length=64), nullable=True),
        sa.Column("created_by_user_id", sa.Uuid(), nullable=False),
        sa.Column("updated_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("started_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("submitted_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("submission_reason", sa.String(length=2000), nullable=True),
        sa.Column("accepted_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("accepted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("acceptance_reason", sa.String(length=2000), nullable=True),
        sa.Column("rejected_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("rejected_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("rejection_reason", sa.String(length=2000), nullable=True),
        sa.Column("rolled_back_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("rolled_back_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("rollback_reason", sa.String(length=2000), nullable=True),
        sa.Column("revoked_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revocation_reason", sa.String(length=2000), nullable=True),
        sa.Column("cancelled_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancellation_reason", sa.String(length=2000), nullable=True),
        *_timestamp_columns(),
        sa.CheckConstraint(
            "status IN ('draft', 'smoke_testing', 'running', 'ready_for_owner_review', "
            "'accepted', "
            "'rejected', 'rolled_back', 'revoked', 'cancelled')",
            name="ck_prospecting_dialer_pilots_status",
        ),
        sa.CheckConstraint("revision >= 1", name="ck_prospecting_dialer_pilots_revision"),
        sa.CheckConstraint(
            "effective_line_count = 1",
            name="ck_prospecting_dialer_pilots_one_line",
        ),
        sa.CheckConstraint(
            "length(trim(timezone)) > 0",
            name="ck_prospecting_dialer_pilots_timezone",
        ),
        sa.CheckConstraint(
            "required_clean_shift_count >= 3 "
            "AND minimum_attempts_per_shift >= 25 "
            "AND minimum_productive_minutes_per_shift >= 60 "
            "AND minimum_total_attempts >= 75 "
            "AND minimum_total_attempts >= "
            "required_clean_shift_count * minimum_attempts_per_shift",
            name="ck_prospecting_dialer_pilots_thresholds",
        ),
        sa.CheckConstraint(
            "minimum_batch_size >= 75 AND maximum_batch_size <= 250 "
            "AND minimum_batch_size <= maximum_batch_size",
            name="ck_prospecting_dialer_pilots_batch_bounds",
        ),
        sa.CheckConstraint(
            "daily_dial_limit BETWEEN 25 AND 50",
            name="ck_prospecting_dialer_pilots_daily_dials",
        ),
        sa.CheckConstraint(
            "daily_spend_limit_cents BETWEEN 1 AND 1000",
            name="ck_prospecting_dialer_pilots_daily_spend",
        ),
        sa.CheckConstraint(
            "length(configuration_fingerprint) = 64",
            name="ck_prospecting_dialer_pilots_fingerprint",
        ),
        sa.CheckConstraint(
            "evidence_hash IS NULL OR length(evidence_hash) = 64",
            name="ck_prospecting_dialer_pilots_evidence_hash",
        ),
        sa.CheckConstraint(
            "status IN ('draft', 'cancelled') "
            "OR (started_at IS NOT NULL AND started_by_user_id IS NOT NULL)",
            name="ck_prospecting_dialer_pilots_started",
        ),
        sa.CheckConstraint(
            "status NOT IN ('ready_for_owner_review', 'accepted', 'rejected', 'revoked') "
            "OR (submitted_at IS NOT NULL AND submitted_by_user_id IS NOT NULL "
            "AND submission_reason IS NOT NULL AND length(trim(submission_reason)) > 0 "
            "AND evidence_hash IS NOT NULL)",
            name="ck_prospecting_dialer_pilots_submitted",
        ),
        sa.CheckConstraint(
            "status NOT IN ('accepted', 'revoked') "
            "OR (accepted_at IS NOT NULL AND accepted_by_user_id IS NOT NULL "
            "AND acceptance_reason IS NOT NULL AND length(trim(acceptance_reason)) > 0)",
            name="ck_prospecting_dialer_pilots_accepted",
        ),
        sa.CheckConstraint(
            "status <> 'rejected' "
            "OR (rejected_at IS NOT NULL AND rejected_by_user_id IS NOT NULL "
            "AND rejection_reason IS NOT NULL AND length(trim(rejection_reason)) > 0)",
            name="ck_prospecting_dialer_pilots_rejected",
        ),
        sa.CheckConstraint(
            "status <> 'rolled_back' "
            "OR (rolled_back_at IS NOT NULL AND rolled_back_by_user_id IS NOT NULL "
            "AND rollback_reason IS NOT NULL AND length(trim(rollback_reason)) > 0 "
            "AND evidence_hash IS NOT NULL)",
            name="ck_prospecting_dialer_pilots_rolled_back",
        ),
        sa.CheckConstraint(
            "status <> 'revoked' "
            "OR (revoked_at IS NOT NULL AND revoked_by_user_id IS NOT NULL "
            "AND revocation_reason IS NOT NULL AND length(trim(revocation_reason)) > 0)",
            name="ck_prospecting_dialer_pilots_revoked",
        ),
        sa.CheckConstraint(
            "status <> 'cancelled' "
            "OR (cancelled_at IS NOT NULL AND cancelled_by_user_id IS NOT NULL "
            "AND cancellation_reason IS NOT NULL "
            "AND length(trim(cancellation_reason)) > 0)",
            name="ck_prospecting_dialer_pilots_cancelled",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"], ["organizations.id"], name="fk_dialer_pilots_organization"
        ),
        sa.ForeignKeyConstraint(["caller_user_id"], ["users.id"], name="fk_dialer_pilots_caller"),
        sa.ForeignKeyConstraint(
            ["campaign_id"], ["campaigns.id"], name="fk_dialer_pilots_campaign"
        ),
        sa.ForeignKeyConstraint(
            ["cohort_id"], ["prospecting_cohorts.id"], name="fk_dialer_pilots_cohort"
        ),
        sa.ForeignKeyConstraint(
            ["prospect_calling_batch_id"],
            ["prospect_calling_batches.id"],
            name="fk_dialer_pilots_calling_batch",
        ),
        sa.ForeignKeyConstraint(
            ["voice_line_id"], ["voice_lines.id"], name="fk_dialer_pilots_voice_line"
        ),
        sa.ForeignKeyConstraint(
            ["created_by_user_id"], ["users.id"], name="fk_dialer_pilots_created_by"
        ),
        sa.ForeignKeyConstraint(
            ["updated_by_user_id"], ["users.id"], name="fk_dialer_pilots_updated_by"
        ),
        sa.ForeignKeyConstraint(
            ["started_by_user_id"], ["users.id"], name="fk_dialer_pilots_started_by"
        ),
        sa.ForeignKeyConstraint(
            ["submitted_by_user_id"], ["users.id"], name="fk_dialer_pilots_submitted_by"
        ),
        sa.ForeignKeyConstraint(
            ["accepted_by_user_id"], ["users.id"], name="fk_dialer_pilots_accepted_by"
        ),
        sa.ForeignKeyConstraint(
            ["rejected_by_user_id"], ["users.id"], name="fk_dialer_pilots_rejected_by"
        ),
        sa.ForeignKeyConstraint(
            ["rolled_back_by_user_id"], ["users.id"], name="fk_dialer_pilots_rolled_back_by"
        ),
        sa.ForeignKeyConstraint(
            ["revoked_by_user_id"], ["users.id"], name="fk_dialer_pilots_revoked_by"
        ),
        sa.ForeignKeyConstraint(
            ["cancelled_by_user_id"], ["users.id"], name="fk_dialer_pilots_cancelled_by"
        ),
        sa.PrimaryKeyConstraint("id"),
    )

    pilot_index_columns = (
        "organization_id",
        "caller_user_id",
        "campaign_id",
        "cohort_id",
        "prospect_calling_batch_id",
        "voice_line_id",
        "status",
        "evidence_hash",
    )
    for column_name in pilot_index_columns:
        op.create_index(
            f"ix_prospecting_dialer_pilots_{column_name}",
            "prospecting_dialer_pilots",
            [column_name],
        )
    open_predicate = sa.text(
        "status IN ('draft', 'smoke_testing', 'running', 'ready_for_owner_review')"
    )
    op.create_index(
        "uq_prospecting_dialer_pilots_open_org",
        "prospecting_dialer_pilots",
        ["organization_id"],
        unique=True,
        postgresql_where=open_predicate,
        sqlite_where=open_predicate,
    )
    accepted_predicate = sa.text("status = 'accepted'")
    op.create_index(
        "uq_prospecting_dialer_pilots_accepted_scope",
        "prospecting_dialer_pilots",
        [
            "organization_id",
            "caller_user_id",
            "campaign_id",
            "cohort_id",
            "prospect_calling_batch_id",
            "voice_line_id",
        ],
        unique=True,
        postgresql_where=accepted_predicate,
        sqlite_where=accepted_predicate,
    )

    op.add_column(
        "prospecting_dial_sessions",
        sa.Column("pilot_id", sa.Uuid(), nullable=True),
    )
    op.create_foreign_key(
        "fk_prospecting_dial_sessions_pilot_id",
        "prospecting_dial_sessions",
        "prospecting_dialer_pilots",
        ["pilot_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_prospecting_dial_sessions_pilot_id",
        "prospecting_dial_sessions",
        ["pilot_id"],
    )

    op.create_table(
        "prospecting_dialer_pilot_attempt_reviews",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("pilot_id", sa.Uuid(), nullable=False),
        sa.Column("attempt_id", sa.Uuid(), nullable=False),
        sa.Column("dial_session_id", sa.Uuid(), nullable=False),
        sa.Column("status", sa.String(length=40), server_default="pending", nullable=False),
        sa.Column("server_dial_leg_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("server_terminal_leg_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("disposition_complete", sa.Boolean(), server_default="false", nullable=False),
        sa.Column(
            "recording_review_required", sa.Boolean(), server_default="false", nullable=False
        ),
        sa.Column("recording_reviewed", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("callback_required", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("callback_reconciled", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("handoff_required", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("handoff_reconciled", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("provider_cost_verified", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("compliance_clear", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("evidence_snapshot", sa.JSON(), nullable=False),
        sa.Column("evidence_hash", sa.String(length=64), nullable=False),
        sa.Column("reviewed_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("review_reason", sa.String(length=2000), nullable=True),
        *_timestamp_columns(),
        sa.CheckConstraint(
            "status IN ('pending', 'passed', 'failed')",
            name="ck_prospecting_pilot_attempt_reviews_status",
        ),
        sa.CheckConstraint(
            "server_dial_leg_count >= 0 AND server_terminal_leg_count >= 0 "
            "AND server_terminal_leg_count <= server_dial_leg_count",
            name="ck_prospecting_pilot_attempt_reviews_counts",
        ),
        sa.CheckConstraint(
            "length(evidence_hash) = 64",
            name="ck_prospecting_pilot_attempt_reviews_hash",
        ),
        sa.CheckConstraint(
            "(status = 'pending' AND reviewed_by_user_id IS NULL AND reviewed_at IS NULL) "
            "OR (status IN ('passed', 'failed') "
            "AND reviewed_by_user_id IS NOT NULL AND reviewed_at IS NOT NULL)",
            name="ck_prospecting_pilot_attempt_reviews_decision",
        ),
        sa.CheckConstraint(
            "status <> 'failed' OR (review_reason IS NOT NULL AND length(trim(review_reason)) > 0)",
            name="ck_prospecting_pilot_attempt_reviews_failure_reason",
        ),
        sa.CheckConstraint(
            "status <> 'passed' OR (disposition_complete "
            "AND (NOT recording_review_required OR recording_reviewed) "
            "AND (NOT callback_required OR callback_reconciled) "
            "AND (NOT handoff_required OR handoff_reconciled) "
            "AND provider_cost_verified AND compliance_clear "
            "AND server_terminal_leg_count = server_dial_leg_count)",
            name="ck_prospecting_pilot_attempt_reviews_passed",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"], ["organizations.id"], name="fk_pilot_attempt_reviews_org"
        ),
        sa.ForeignKeyConstraint(
            ["pilot_id"], ["prospecting_dialer_pilots.id"], name="fk_pilot_attempt_reviews_pilot"
        ),
        sa.ForeignKeyConstraint(
            ["attempt_id"], ["prospecting_attempts.id"], name="fk_pilot_attempt_reviews_attempt"
        ),
        sa.ForeignKeyConstraint(
            ["dial_session_id"],
            ["prospecting_dial_sessions.id"],
            name="fk_pilot_attempt_reviews_session",
        ),
        sa.ForeignKeyConstraint(
            ["reviewed_by_user_id"], ["users.id"], name="fk_pilot_attempt_reviews_reviewer"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("attempt_id", name="uq_prospecting_pilot_attempt_reviews_attempt"),
    )
    op.create_index(
        "ix_prospecting_pilot_attempt_reviews_org",
        "prospecting_dialer_pilot_attempt_reviews",
        ["organization_id"],
    )
    op.create_index(
        "ix_prospecting_pilot_attempt_reviews_pilot_status",
        "prospecting_dialer_pilot_attempt_reviews",
        ["pilot_id", "status"],
    )
    op.create_index(
        "ix_prospecting_pilot_attempt_reviews_session",
        "prospecting_dialer_pilot_attempt_reviews",
        ["dial_session_id"],
    )

    op.create_table(
        "prospecting_dialer_pilot_shift_reviews",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("pilot_id", sa.Uuid(), nullable=False),
        sa.Column("dial_session_id", sa.Uuid(), nullable=False),
        sa.Column("shift_date", sa.Date(), nullable=False),
        sa.Column("timezone", sa.String(length=80), nullable=False),
        sa.Column("status", sa.String(length=40), server_default="pending", nullable=False),
        sa.Column("server_attempt_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column(
            "server_reviewed_attempt_count", sa.Integer(), server_default="0", nullable=False
        ),
        sa.Column("server_passed_attempt_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("productive_minutes", sa.Integer(), server_default="0", nullable=False),
        sa.Column("all_attempts_reviewed", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("all_legs_terminal", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("no_duplicate_calls", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("no_lost_answers", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("no_stuck_sessions", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("callbacks_reconciled", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("handoffs_reconciled", sa.Boolean(), server_default="false", nullable=False),
        sa.Column(
            "provider_billing_verified", sa.Boolean(), server_default="false", nullable=False
        ),
        sa.Column("daily_caps_respected", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("kill_switches_verified", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("recordings_reviewed", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("compliance_clear", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("evidence_snapshot", sa.JSON(), nullable=False),
        sa.Column("evidence_hash", sa.String(length=64), nullable=False),
        sa.Column("reviewed_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("review_reason", sa.String(length=2000), nullable=True),
        *_timestamp_columns(),
        sa.CheckConstraint(
            "status IN ('pending', 'passed', 'failed')",
            name="ck_prospecting_pilot_shift_reviews_status",
        ),
        sa.CheckConstraint(
            "server_attempt_count >= 0 AND server_reviewed_attempt_count >= 0 "
            "AND server_passed_attempt_count >= 0 "
            "AND server_reviewed_attempt_count <= server_attempt_count "
            "AND server_passed_attempt_count <= server_reviewed_attempt_count",
            name="ck_prospecting_pilot_shift_reviews_counts",
        ),
        sa.CheckConstraint(
            "productive_minutes >= 0",
            name="ck_prospecting_pilot_shift_reviews_minutes",
        ),
        sa.CheckConstraint(
            "length(trim(timezone)) > 0",
            name="ck_prospecting_pilot_shift_reviews_timezone",
        ),
        sa.CheckConstraint(
            "length(evidence_hash) = 64",
            name="ck_prospecting_pilot_shift_reviews_hash",
        ),
        sa.CheckConstraint(
            "(status = 'pending' AND reviewed_by_user_id IS NULL AND reviewed_at IS NULL) "
            "OR (status IN ('passed', 'failed') "
            "AND reviewed_by_user_id IS NOT NULL AND reviewed_at IS NOT NULL)",
            name="ck_prospecting_pilot_shift_reviews_decision",
        ),
        sa.CheckConstraint(
            "status <> 'failed' OR (review_reason IS NOT NULL AND length(trim(review_reason)) > 0)",
            name="ck_prospecting_pilot_shift_reviews_failure_reason",
        ),
        sa.CheckConstraint(
            "status <> 'passed' OR ("
            "server_reviewed_attempt_count = server_attempt_count "
            "AND server_passed_attempt_count = server_attempt_count "
            "AND productive_minutes > 0 "
            "AND all_attempts_reviewed AND all_legs_terminal "
            "AND no_duplicate_calls AND no_lost_answers AND no_stuck_sessions "
            "AND callbacks_reconciled AND handoffs_reconciled "
            "AND provider_billing_verified AND daily_caps_respected "
            "AND kill_switches_verified AND recordings_reviewed AND compliance_clear)",
            name="ck_prospecting_pilot_shift_reviews_passed",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"], ["organizations.id"], name="fk_pilot_shift_reviews_org"
        ),
        sa.ForeignKeyConstraint(
            ["pilot_id"], ["prospecting_dialer_pilots.id"], name="fk_pilot_shift_reviews_pilot"
        ),
        sa.ForeignKeyConstraint(
            ["dial_session_id"],
            ["prospecting_dial_sessions.id"],
            name="fk_pilot_shift_reviews_session",
        ),
        sa.ForeignKeyConstraint(
            ["reviewed_by_user_id"], ["users.id"], name="fk_pilot_shift_reviews_reviewer"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "pilot_id", "shift_date", name="uq_prospecting_pilot_shift_reviews_pilot_date"
        ),
    )
    op.create_index(
        "ix_prospecting_pilot_shift_reviews_org",
        "prospecting_dialer_pilot_shift_reviews",
        ["organization_id"],
    )
    op.create_index(
        "ix_prospecting_pilot_shift_reviews_pilot_status",
        "prospecting_dialer_pilot_shift_reviews",
        ["pilot_id", "status"],
    )
    op.create_index(
        "ix_prospecting_pilot_shift_reviews_date",
        "prospecting_dialer_pilot_shift_reviews",
        ["shift_date"],
    )


def _assert_no_acceptance_evidence() -> None:
    """Refuse to discard owner decisions or the evidence supporting them."""

    context = op.get_context()
    if context.as_sql:
        return
    has_evidence = (
        op.get_bind()
        .execute(
            sa.text(
                "SELECT EXISTS ("
                "SELECT 1 FROM prospecting_dialer_pilots "
                "UNION ALL SELECT 1 FROM prospecting_dialer_pilot_attempt_reviews "
                "UNION ALL SELECT 1 FROM prospecting_dialer_pilot_shift_reviews)"
            )
        )
        .scalar_one()
    )
    if has_evidence:
        raise RuntimeError(
            "Cannot downgrade D10 prospecting dialer acceptance while pilot evidence exists. "
            "Retain revision 0109 or archive the evidence through an approved data migration."
        )


def downgrade() -> None:
    _assert_no_acceptance_evidence()

    op.drop_index(
        "ix_prospecting_pilot_shift_reviews_date",
        table_name="prospecting_dialer_pilot_shift_reviews",
    )
    op.drop_index(
        "ix_prospecting_pilot_shift_reviews_pilot_status",
        table_name="prospecting_dialer_pilot_shift_reviews",
    )
    op.drop_index(
        "ix_prospecting_pilot_shift_reviews_org",
        table_name="prospecting_dialer_pilot_shift_reviews",
    )
    op.drop_table("prospecting_dialer_pilot_shift_reviews")

    op.drop_index(
        "ix_prospecting_pilot_attempt_reviews_session",
        table_name="prospecting_dialer_pilot_attempt_reviews",
    )
    op.drop_index(
        "ix_prospecting_pilot_attempt_reviews_pilot_status",
        table_name="prospecting_dialer_pilot_attempt_reviews",
    )
    op.drop_index(
        "ix_prospecting_pilot_attempt_reviews_org",
        table_name="prospecting_dialer_pilot_attempt_reviews",
    )
    op.drop_table("prospecting_dialer_pilot_attempt_reviews")

    op.drop_index(
        "ix_prospecting_dial_sessions_pilot_id",
        table_name="prospecting_dial_sessions",
    )
    op.drop_constraint(
        "fk_prospecting_dial_sessions_pilot_id",
        "prospecting_dial_sessions",
        type_="foreignkey",
    )
    op.drop_column("prospecting_dial_sessions", "pilot_id")

    op.drop_index(
        "uq_prospecting_dialer_pilots_accepted_scope",
        table_name="prospecting_dialer_pilots",
    )
    op.drop_index(
        "uq_prospecting_dialer_pilots_open_org",
        table_name="prospecting_dialer_pilots",
    )
    for column_name in reversed(
        (
            "organization_id",
            "caller_user_id",
            "campaign_id",
            "cohort_id",
            "prospect_calling_batch_id",
            "voice_line_id",
            "status",
            "evidence_hash",
        )
    ):
        op.drop_index(
            f"ix_prospecting_dialer_pilots_{column_name}",
            table_name="prospecting_dialer_pilots",
        )
    op.drop_table("prospecting_dialer_pilots")
    op.drop_column("organizations", "prospecting_dialer_acceptance_required")
