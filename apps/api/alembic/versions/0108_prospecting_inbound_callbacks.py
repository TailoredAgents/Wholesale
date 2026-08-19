"""Add durable prospecting inbound callback evidence.

Revision ID: 0108_prospecting_callbacks
Revises: 0107_prospecting_evidence
"""

from collections.abc import Sequence
from typing import Any

import sqlalchemy as sa

from alembic import op

revision: str = "0108_prospecting_callbacks"
down_revision: str | None = "0107_prospecting_evidence"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


LEGACY_CALL_RECORD_CONTEXT_CHECK = (
    "(prospect_id IS NULL "
    "AND prospecting_attempt_id IS NULL "
    "AND prospecting_dial_leg_id IS NULL "
    "AND conversation_id IS NOT NULL "
    "AND contact_id IS NOT NULL) "
    "OR "
    "(prospect_id IS NOT NULL "
    "AND prospecting_attempt_id IS NOT NULL "
    "AND prospecting_dial_leg_id IS NOT NULL "
    "AND conversation_id IS NULL "
    "AND lead_id IS NULL "
    "AND contact_id IS NULL "
    "AND communication_record_id IS NULL)"
)

CALL_RECORD_CONTEXT_CHECK = (
    "(prospect_id IS NULL "
    "AND prospecting_attempt_id IS NULL "
    "AND prospecting_dial_leg_id IS NULL "
    "AND prospecting_inbound_callback_id IS NULL "
    "AND conversation_id IS NOT NULL "
    "AND contact_id IS NOT NULL) "
    "OR "
    "(prospect_id IS NOT NULL "
    "AND prospecting_attempt_id IS NOT NULL "
    "AND prospecting_dial_leg_id IS NOT NULL "
    "AND prospecting_inbound_callback_id IS NULL "
    "AND conversation_id IS NULL "
    "AND lead_id IS NULL "
    "AND contact_id IS NULL "
    "AND communication_record_id IS NULL) "
    "OR "
    "(prospecting_inbound_callback_id IS NOT NULL "
    "AND prospecting_dial_leg_id IS NULL "
    "AND ((prospect_id IS NULL AND prospecting_attempt_id IS NULL) "
    "OR (prospect_id IS NOT NULL AND prospecting_attempt_id IS NOT NULL)) "
    "AND conversation_id IS NULL "
    "AND lead_id IS NULL "
    "AND contact_id IS NULL "
    "AND communication_record_id IS NULL "
    "AND call_intent_id IS NULL "
    "AND direction = 'inbound')"
)


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
        "prospecting_inbound_callbacks",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("voice_line_id", sa.Uuid(), nullable=False),
        sa.Column("provider", sa.String(length=80), nullable=False),
        sa.Column("provider_call_id", sa.String(length=255), nullable=False),
        sa.Column("normalized_caller", sa.String(length=40), nullable=False),
        sa.Column("caller_number", sa.String(length=80), nullable=False),
        sa.Column("matched_prospect_id", sa.Uuid(), nullable=True),
        sa.Column("matched_attempt_id", sa.Uuid(), nullable=True),
        sa.Column(
            "match_status",
            sa.String(length=40),
            server_default="pending",
            nullable=False,
        ),
        sa.Column("match_strategy", sa.String(length=80), nullable=True),
        sa.Column("match_confidence_basis_points", sa.Integer(), nullable=True),
        sa.Column("candidate_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("assigned_user_id", sa.Uuid(), nullable=True),
        sa.Column("fallback_user_id", sa.Uuid(), nullable=True),
        sa.Column(
            "status",
            sa.String(length=40),
            server_default="received",
            nullable=False,
        ),
        sa.Column(
            "received_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("answered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "routing_metadata",
            sa.JSON(),
            server_default=sa.text("'{}'"),
            nullable=False,
        ),
        *_timestamp_columns(),
        sa.CheckConstraint(
            "match_status IN ('pending', 'matched', 'unknown', 'ambiguous')",
            name="ck_prospecting_inbound_callbacks_match_status",
        ),
        sa.CheckConstraint(
            "status IN ('received', 'routing', 'ringing', 'answered', 'voicemail', "
            "'missed', 'completed', 'failed', 'canceled')",
            name="ck_prospecting_inbound_callbacks_status",
        ),
        sa.CheckConstraint(
            "match_confidence_basis_points IS NULL "
            "OR match_confidence_basis_points BETWEEN 0 AND 10000",
            name="ck_prospecting_inbound_callbacks_match_confidence",
        ),
        sa.CheckConstraint(
            "candidate_count >= 0",
            name="ck_prospecting_inbound_callbacks_candidate_count",
        ),
        sa.CheckConstraint(
            "(match_status = 'matched' "
            "AND matched_prospect_id IS NOT NULL "
            "AND matched_attempt_id IS NOT NULL) OR "
            "(match_status <> 'matched' "
            "AND matched_prospect_id IS NULL "
            "AND matched_attempt_id IS NULL)",
            name="ck_prospecting_inbound_callbacks_match_context",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name="fk_prospecting_inbound_callbacks_organization_id",
        ),
        sa.ForeignKeyConstraint(
            ["voice_line_id"],
            ["voice_lines.id"],
            name="fk_prospecting_inbound_callbacks_voice_line_id",
        ),
        sa.ForeignKeyConstraint(
            ["matched_prospect_id"],
            ["prospects.id"],
            name="fk_prospecting_inbound_callbacks_matched_prospect_id",
        ),
        sa.ForeignKeyConstraint(
            ["matched_attempt_id"],
            ["prospecting_attempts.id"],
            name="fk_prospecting_inbound_callbacks_matched_attempt_id",
        ),
        sa.ForeignKeyConstraint(
            ["assigned_user_id"],
            ["users.id"],
            name="fk_prospecting_inbound_callbacks_assigned_user_id",
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["fallback_user_id"],
            ["users.id"],
            name="fk_prospecting_inbound_callbacks_fallback_user_id",
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "organization_id",
            "provider",
            "provider_call_id",
            name="uq_prospecting_inbound_callbacks_org_provider_call",
        ),
    )

    for column_name in (
        "organization_id",
        "voice_line_id",
        "provider_call_id",
        "normalized_caller",
        "matched_prospect_id",
        "matched_attempt_id",
        "match_status",
        "assigned_user_id",
        "fallback_user_id",
        "status",
        "received_at",
    ):
        op.create_index(
            f"ix_prospecting_inbound_callbacks_{column_name}",
            "prospecting_inbound_callbacks",
            [column_name],
        )
    op.create_index(
        "ix_prospecting_inbound_callbacks_line_caller_received",
        "prospecting_inbound_callbacks",
        ["organization_id", "voice_line_id", "normalized_caller", "received_at"],
    )

    op.add_column(
        "call_records",
        sa.Column("prospecting_inbound_callback_id", sa.Uuid(), nullable=True),
    )
    op.create_foreign_key(
        "fk_call_records_prospecting_inbound_callback_id",
        "call_records",
        "prospecting_inbound_callbacks",
        ["prospecting_inbound_callback_id"],
        ["id"],
    )
    op.create_index(
        "ix_call_records_prospecting_inbound_callback_id",
        "call_records",
        ["prospecting_inbound_callback_id"],
    )
    op.create_unique_constraint(
        "uq_call_records_prospecting_inbound_callback",
        "call_records",
        ["prospecting_inbound_callback_id"],
    )
    op.drop_constraint(
        "ck_call_records_context",
        "call_records",
        type_="check",
    )
    op.create_check_constraint(
        "ck_call_records_context",
        "call_records",
        CALL_RECORD_CONTEXT_CHECK,
    )

    for column_name in (
        "prospecting_inbound_callback_id",
        "prospect_id",
        "call_record_id",
    ):
        op.add_column("tasks", sa.Column(column_name, sa.Uuid(), nullable=True))

    op.create_foreign_key(
        "fk_tasks_prospecting_inbound_callback_id",
        "tasks",
        "prospecting_inbound_callbacks",
        ["prospecting_inbound_callback_id"],
        ["id"],
    )
    op.create_foreign_key(
        "fk_tasks_prospect_id",
        "tasks",
        "prospects",
        ["prospect_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        "fk_tasks_call_record_id",
        "tasks",
        "call_records",
        ["call_record_id"],
        ["id"],
        ondelete="SET NULL",
    )
    for column_name in (
        "prospecting_inbound_callback_id",
        "prospect_id",
        "call_record_id",
    ):
        op.create_index(f"ix_tasks_{column_name}", "tasks", [column_name])

    missed_callback_predicate = sa.text(
        "task_type = 'missed_prospecting_callback' AND prospecting_inbound_callback_id IS NOT NULL"
    )
    op.create_index(
        "uq_tasks_prospecting_missed_callback",
        "tasks",
        ["organization_id", "prospecting_inbound_callback_id"],
        unique=True,
        postgresql_where=missed_callback_predicate,
        sqlite_where=missed_callback_predicate,
    )


def _assert_no_inbound_callback_evidence() -> None:
    """Refuse to discard callback evidence during a live downgrade."""

    context = op.get_context()
    if context.as_sql:
        return
    has_evidence = (
        op.get_bind()
        .execute(sa.text("SELECT EXISTS (SELECT 1 FROM prospecting_inbound_callbacks)"))
        .scalar_one()
    )
    if has_evidence:
        raise RuntimeError(
            "Cannot downgrade prospecting inbound callbacks while callback evidence exists. "
            "Retain revision 0108 or archive the evidence through an approved data migration."
        )


def downgrade() -> None:
    _assert_no_inbound_callback_evidence()

    op.drop_index("uq_tasks_prospecting_missed_callback", table_name="tasks")
    for column_name in (
        "call_record_id",
        "prospect_id",
        "prospecting_inbound_callback_id",
    ):
        op.drop_index(f"ix_tasks_{column_name}", table_name="tasks")
        op.drop_constraint(f"fk_tasks_{column_name}", "tasks", type_="foreignkey")
        op.drop_column("tasks", column_name)

    op.drop_constraint("ck_call_records_context", "call_records", type_="check")
    op.drop_constraint(
        "uq_call_records_prospecting_inbound_callback",
        "call_records",
        type_="unique",
    )
    op.drop_index(
        "ix_call_records_prospecting_inbound_callback_id",
        table_name="call_records",
    )
    op.drop_constraint(
        "fk_call_records_prospecting_inbound_callback_id",
        "call_records",
        type_="foreignkey",
    )
    op.drop_column("call_records", "prospecting_inbound_callback_id")
    op.create_check_constraint(
        "ck_call_records_context",
        "call_records",
        LEGACY_CALL_RECORD_CONTEXT_CHECK,
    )

    op.drop_index(
        "ix_prospecting_inbound_callbacks_line_caller_received",
        table_name="prospecting_inbound_callbacks",
    )
    for column_name in (
        "received_at",
        "status",
        "fallback_user_id",
        "assigned_user_id",
        "match_status",
        "matched_attempt_id",
        "matched_prospect_id",
        "normalized_caller",
        "provider_call_id",
        "voice_line_id",
        "organization_id",
    ):
        op.drop_index(
            f"ix_prospecting_inbound_callbacks_{column_name}",
            table_name="prospecting_inbound_callbacks",
        )
    op.drop_table("prospecting_inbound_callbacks")
