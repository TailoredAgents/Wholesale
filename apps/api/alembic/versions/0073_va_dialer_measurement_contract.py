"""Add VA dialer definitions and measurement contract.

Revision ID: 0073_va_dialer_metrics
Revises: 0072_conversion_experiments
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0073_va_dialer_metrics"
down_revision: str | None = "0072_conversion_experiments"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "prospecting_cohorts",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("campaign_id", sa.Uuid(), nullable=False),
        sa.Column("script_version_id", sa.Uuid(), nullable=True),
        sa.Column("created_by_user_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(160), nullable=False),
        sa.Column("code", sa.String(80), nullable=False),
        sa.Column("status", sa.String(40), server_default="active", nullable=False),
        sa.Column("source_name", sa.String(160), nullable=False),
        sa.Column("list_type", sa.String(160), nullable=False),
        sa.Column("market_label", sa.String(160), nullable=False),
        sa.Column("dialer_mode", sa.String(40), nullable=False),
        sa.Column("call_window_start_hour", sa.Integer(), nullable=False),
        sa.Column("call_window_end_hour", sa.Integer(), nullable=False),
        sa.Column("timezone", sa.String(80), nullable=False),
        sa.Column("starts_on", sa.Date(), nullable=False),
        sa.Column("ends_on", sa.Date(), nullable=True),
        sa.Column("cohort_metadata", sa.JSON(), nullable=False),
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
        sa.ForeignKeyConstraint(["campaign_id"], ["campaigns.id"]),
        sa.ForeignKeyConstraint(["script_version_id"], ["prospecting_script_versions.id"]),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "organization_id",
            "code",
            name="uq_prospecting_cohorts_org_code",
        ),
    )
    for column in (
        "organization_id",
        "campaign_id",
        "script_version_id",
        "status",
        "dialer_mode",
        "starts_on",
    ):
        op.create_index(
            f"ix_prospecting_cohorts_{column}",
            "prospecting_cohorts",
            [column],
        )

    op.add_column("campaign_costs", sa.Column("cohort_id", sa.Uuid(), nullable=True))
    op.create_foreign_key(
        "fk_campaign_costs_cohort_id",
        "campaign_costs",
        "prospecting_cohorts",
        ["cohort_id"],
        ["id"],
    )
    op.create_index("ix_campaign_costs_cohort_id", "campaign_costs", ["cohort_id"])

    op.create_table(
        "prospecting_work_sessions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("campaign_id", sa.Uuid(), nullable=False),
        sa.Column("cohort_id", sa.Uuid(), nullable=False),
        sa.Column("caller_user_id", sa.Uuid(), nullable=False),
        sa.Column("campaign_cost_id", sa.Uuid(), nullable=False),
        sa.Column("created_by_user_id", sa.Uuid(), nullable=False),
        sa.Column("work_date", sa.Date(), nullable=False),
        sa.Column("paid_minutes", sa.Integer(), nullable=False),
        sa.Column("productive_calling_minutes", sa.Integer(), nullable=False),
        sa.Column("hourly_rate_cents", sa.BigInteger(), nullable=False),
        sa.Column("labor_cost_cents", sa.BigInteger(), nullable=False),
        sa.Column("source", sa.String(40), nullable=False),
        sa.Column("provider_session_id", sa.String(255), nullable=True),
        sa.Column("notes", sa.String(1000), nullable=True),
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
        sa.ForeignKeyConstraint(["campaign_id"], ["campaigns.id"]),
        sa.ForeignKeyConstraint(["cohort_id"], ["prospecting_cohorts.id"]),
        sa.ForeignKeyConstraint(["caller_user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["campaign_cost_id"], ["campaign_costs.id"]),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("campaign_cost_id"),
    )
    for column in (
        "organization_id",
        "campaign_id",
        "cohort_id",
        "caller_user_id",
        "work_date",
    ):
        op.create_index(
            f"ix_prospecting_work_sessions_{column}",
            "prospecting_work_sessions",
            [column],
        )

    op.add_column(
        "prospect_calling_batches",
        sa.Column("cohort_id", sa.Uuid(), nullable=True),
    )
    op.add_column(
        "prospect_calling_batches",
        sa.Column(
            "dialer_mode",
            sa.String(40),
            server_default="one_line_power",
            nullable=False,
        ),
    )
    op.create_foreign_key(
        "fk_prospect_calling_batches_cohort_id",
        "prospect_calling_batches",
        "prospecting_cohorts",
        ["cohort_id"],
        ["id"],
    )
    op.create_index(
        "ix_prospect_calling_batches_cohort_id",
        "prospect_calling_batches",
        ["cohort_id"],
    )
    op.create_index(
        "ix_prospect_calling_batches_dialer_mode",
        "prospect_calling_batches",
        ["dialer_mode"],
    )

    attempt_columns = (
        sa.Column("cohort_id", sa.Uuid(), nullable=True),
        sa.Column(
            "dialer_mode",
            sa.String(40),
            server_default="one_line_power",
            nullable=False,
        ),
        sa.Column(
            "answer_classification",
            sa.String(40),
            server_default="unknown",
            nullable=False,
        ),
        sa.Column(
            "party_classification",
            sa.String(40),
            server_default="unknown",
            nullable=False,
        ),
        sa.Column(
            "interest_classification",
            sa.String(40),
            server_default="not_assessed",
            nullable=False,
        ),
        sa.Column(
            "follow_up_permission",
            sa.String(40),
            server_default="not_recorded",
            nullable=False,
        ),
        sa.Column(
            "classification_source",
            sa.String(40),
            server_default="manual_outcome",
            nullable=False,
        ),
        sa.Column("dial_started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("answered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("right_party_confirmed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("interest_confirmed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "measurement_metadata",
            sa.JSON(),
            server_default=sa.text("'{}'"),
            nullable=False,
        ),
    )
    for column in attempt_columns:
        op.add_column("prospecting_attempts", column)
    op.create_foreign_key(
        "fk_prospecting_attempts_cohort_id",
        "prospecting_attempts",
        "prospecting_cohorts",
        ["cohort_id"],
        ["id"],
    )
    for column in (
        "cohort_id",
        "dialer_mode",
        "answer_classification",
        "party_classification",
        "interest_classification",
        "follow_up_permission",
    ):
        op.create_index(
            f"ix_prospecting_attempts_{column}",
            "prospecting_attempts",
            [column],
        )

    op.execute(
        sa.text(
            """
            UPDATE prospecting_attempts
            SET
                cohort_id = (
                    SELECT pcb.cohort_id
                    FROM prospect_calling_batch_entries pcbe
                    JOIN prospect_calling_batches pcb
                      ON pcb.id = pcbe.prospect_calling_batch_id
                    WHERE pcbe.id = prospecting_attempts.batch_entry_id
                ),
                dialer_mode = COALESCE((
                    SELECT pcb.dialer_mode
                    FROM prospect_calling_batch_entries pcbe
                    JOIN prospect_calling_batches pcb
                      ON pcb.id = pcbe.prospect_calling_batch_id
                    WHERE pcbe.id = prospecting_attempts.batch_entry_id
                ), 'one_line_power'),
                dial_started_at = started_at,
                answer_classification = CASE
                    WHEN outcome = 'no_answer' THEN 'no_answer'
                    WHEN outcome = 'left_voicemail' THEN 'machine'
                    WHEN outcome IS NULL THEN 'unknown'
                    ELSE 'live_person'
                END,
                party_classification = CASE
                    WHEN outcome = 'wrong_number' THEN 'wrong_party'
                    WHEN outcome IN (
                        'callback_requested', 'follow_up', 'interested',
                        'appointment_set', 'not_interested', 'do_not_call'
                    ) THEN 'right_party'
                    ELSE 'unknown'
                END,
                interest_classification = CASE
                    WHEN outcome IN (
                        'callback_requested', 'follow_up', 'interested', 'appointment_set'
                    ) THEN 'interested'
                    WHEN outcome IN ('not_interested', 'do_not_call') THEN 'not_interested'
                    ELSE 'not_assessed'
                END,
                follow_up_permission = CASE
                    WHEN outcome IN (
                        'callback_requested', 'follow_up', 'interested', 'appointment_set'
                    ) THEN 'granted'
                    WHEN outcome IN ('wrong_number', 'not_interested', 'do_not_call') THEN 'declined'
                    ELSE 'not_recorded'
                END,
                answered_at = CASE
                    WHEN outcome IS NOT NULL AND outcome <> 'no_answer' THEN completed_at
                    ELSE NULL
                END,
                right_party_confirmed_at = CASE
                    WHEN outcome IN (
                        'callback_requested', 'follow_up', 'interested',
                        'appointment_set', 'not_interested', 'do_not_call'
                    ) THEN completed_at
                    ELSE NULL
                END,
                interest_confirmed_at = CASE
                    WHEN outcome IN (
                        'callback_requested', 'follow_up', 'interested', 'appointment_set'
                    ) THEN completed_at
                    ELSE NULL
                END
            """
        )
    )

    op.add_column(
        "prospect_handoffs",
        sa.Column("decision_code", sa.String(80), nullable=True),
    )
    op.create_index(
        "ix_prospect_handoffs_decision_code",
        "prospect_handoffs",
        ["decision_code"],
    )
    op.execute(
        sa.text(
            """
            UPDATE prospect_handoffs
            SET decision_code = CASE
                WHEN status = 'accepted' THEN 'accepted_interested'
                WHEN status = 'needs_correction' THEN 'correction_other'
                ELSE NULL
            END
            """
        )
    )


def downgrade() -> None:
    op.drop_index("ix_prospect_handoffs_decision_code", table_name="prospect_handoffs")
    op.drop_column("prospect_handoffs", "decision_code")

    for column in (
        "follow_up_permission",
        "interest_classification",
        "party_classification",
        "answer_classification",
        "dialer_mode",
        "cohort_id",
    ):
        op.drop_index(f"ix_prospecting_attempts_{column}", table_name="prospecting_attempts")
    op.drop_constraint(
        "fk_prospecting_attempts_cohort_id",
        "prospecting_attempts",
        type_="foreignkey",
    )
    for column in (
        "measurement_metadata",
        "interest_confirmed_at",
        "right_party_confirmed_at",
        "answered_at",
        "dial_started_at",
        "classification_source",
        "follow_up_permission",
        "interest_classification",
        "party_classification",
        "answer_classification",
        "dialer_mode",
        "cohort_id",
    ):
        op.drop_column("prospecting_attempts", column)

    op.drop_index(
        "ix_prospect_calling_batches_dialer_mode",
        table_name="prospect_calling_batches",
    )
    op.drop_index(
        "ix_prospect_calling_batches_cohort_id",
        table_name="prospect_calling_batches",
    )
    op.drop_constraint(
        "fk_prospect_calling_batches_cohort_id",
        "prospect_calling_batches",
        type_="foreignkey",
    )
    op.drop_column("prospect_calling_batches", "dialer_mode")
    op.drop_column("prospect_calling_batches", "cohort_id")

    for column in (
        "work_date",
        "caller_user_id",
        "cohort_id",
        "campaign_id",
        "organization_id",
    ):
        op.drop_index(
            f"ix_prospecting_work_sessions_{column}",
            table_name="prospecting_work_sessions",
        )
    op.drop_table("prospecting_work_sessions")

    op.drop_index("ix_campaign_costs_cohort_id", table_name="campaign_costs")
    op.drop_constraint(
        "fk_campaign_costs_cohort_id",
        "campaign_costs",
        type_="foreignkey",
    )
    op.drop_column("campaign_costs", "cohort_id")

    for column in (
        "starts_on",
        "dialer_mode",
        "status",
        "script_version_id",
        "campaign_id",
        "organization_id",
    ):
        op.drop_index(
            f"ix_prospecting_cohorts_{column}",
            table_name="prospecting_cohorts",
        )
    op.drop_table("prospecting_cohorts")
