"""Allow Voice records to bind directly to cold prospecting work.

Revision ID: 0104_prospecting_voice_context
Revises: 0103_native_prospecting_dialer
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0104_prospecting_voice_context"
down_revision: str | None = "0103_native_prospecting_dialer"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


VOICE_INTENT_CONTEXT_CHECK = (
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
    "AND contact_id IS NULL)"
)

CALL_RECORD_CONTEXT_CHECK = (
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


def upgrade() -> None:
    for table_name in ("voice_call_intents", "call_records"):
        op.alter_column(
            table_name,
            "conversation_id",
            existing_type=sa.Uuid(),
            nullable=True,
        )
        op.alter_column(
            table_name,
            "contact_id",
            existing_type=sa.Uuid(),
            nullable=True,
        )
        op.add_column(table_name, sa.Column("prospect_id", sa.Uuid(), nullable=True))
        op.add_column(
            table_name,
            sa.Column("prospecting_attempt_id", sa.Uuid(), nullable=True),
        )
        op.add_column(
            table_name,
            sa.Column("prospecting_dial_leg_id", sa.Uuid(), nullable=True),
        )

    for table_name, prefix in (
        ("voice_call_intents", "voice_call_intents"),
        ("call_records", "call_records"),
    ):
        op.create_foreign_key(
            f"fk_{prefix}_prospect_id",
            table_name,
            "prospects",
            ["prospect_id"],
            ["id"],
        )
        op.create_foreign_key(
            f"fk_{prefix}_prospecting_attempt_id",
            table_name,
            "prospecting_attempts",
            ["prospecting_attempt_id"],
            ["id"],
        )
        op.create_foreign_key(
            f"fk_{prefix}_prospecting_dial_leg_id",
            table_name,
            "prospecting_dial_legs",
            ["prospecting_dial_leg_id"],
            ["id"],
        )
        for column_name in (
            "prospect_id",
            "prospecting_attempt_id",
            "prospecting_dial_leg_id",
        ):
            op.create_index(
                f"ix_{prefix}_{column_name}",
                table_name,
                [column_name],
            )

    op.create_unique_constraint(
        "uq_voice_call_intents_prospecting_dial_leg",
        "voice_call_intents",
        ["prospecting_dial_leg_id"],
    )
    op.create_unique_constraint(
        "uq_call_records_prospecting_dial_leg",
        "call_records",
        ["prospecting_dial_leg_id"],
    )
    op.create_unique_constraint(
        "uq_prospecting_dial_legs_call_record",
        "prospecting_dial_legs",
        ["call_record_id"],
    )
    op.create_check_constraint(
        "ck_voice_call_intents_context",
        "voice_call_intents",
        VOICE_INTENT_CONTEXT_CHECK,
    )
    op.create_check_constraint(
        "ck_call_records_context",
        "call_records",
        CALL_RECORD_CONTEXT_CHECK,
    )

    provider_sequence_predicate = sa.text(
        "dial_leg_id IS NOT NULL AND provider_sequence_number IS NOT NULL"
    )
    op.create_index(
        "ix_prospecting_provider_events_leg_sequence",
        "prospecting_provider_events",
        [
            "organization_id",
            "provider",
            "dial_leg_id",
            "provider_sequence_number",
        ],
        postgresql_where=provider_sequence_predicate,
        sqlite_where=provider_sequence_predicate,
    )
    op.create_index(
        "ix_prospecting_provider_events_call_lookup",
        "prospecting_provider_events",
        ["organization_id", "provider", "provider_call_id"],
    )


def _assert_no_prospect_voice_evidence() -> None:
    """Refuse a lossy downgrade after the feature has written cold-call evidence."""

    context = op.get_context()
    if context.as_sql:
        # Offline SQL cannot inspect the target database. The live migration path
        # below remains guarded and is the supported production downgrade path.
        return
    connection = op.get_bind()
    for table_name in ("voice_call_intents", "call_records"):
        has_cold_context = connection.execute(
            sa.text(
                f"SELECT EXISTS ("  # noqa: S608 - table names are fixed constants above.
                f"SELECT 1 FROM {table_name} "
                "WHERE prospect_id IS NOT NULL "
                "OR prospecting_attempt_id IS NOT NULL "
                "OR prospecting_dial_leg_id IS NOT NULL "
                "OR conversation_id IS NULL "
                "OR contact_id IS NULL)"
            )
        ).scalar_one()
        if has_cold_context:
            raise RuntimeError(
                "Cannot downgrade prospect-aware Voice context while cold-call evidence exists. "
                "Retain revision 0104 or archive the evidence through an approved data migration."
            )


def downgrade() -> None:
    _assert_no_prospect_voice_evidence()

    op.drop_index(
        "ix_prospecting_provider_events_call_lookup",
        table_name="prospecting_provider_events",
    )
    op.drop_index(
        "ix_prospecting_provider_events_leg_sequence",
        table_name="prospecting_provider_events",
    )
    op.drop_constraint(
        "ck_call_records_context",
        "call_records",
        type_="check",
    )
    op.drop_constraint(
        "ck_voice_call_intents_context",
        "voice_call_intents",
        type_="check",
    )
    op.drop_constraint(
        "uq_prospecting_dial_legs_call_record",
        "prospecting_dial_legs",
        type_="unique",
    )
    op.drop_constraint(
        "uq_call_records_prospecting_dial_leg",
        "call_records",
        type_="unique",
    )
    op.drop_constraint(
        "uq_voice_call_intents_prospecting_dial_leg",
        "voice_call_intents",
        type_="unique",
    )

    for table_name, prefix in (
        ("call_records", "call_records"),
        ("voice_call_intents", "voice_call_intents"),
    ):
        for column_name in (
            "prospecting_dial_leg_id",
            "prospecting_attempt_id",
            "prospect_id",
        ):
            op.drop_index(
                f"ix_{prefix}_{column_name}",
                table_name=table_name,
            )
            op.drop_constraint(
                f"fk_{prefix}_{column_name}",
                table_name,
                type_="foreignkey",
            )
            op.drop_column(table_name, column_name)
        op.alter_column(
            table_name,
            "contact_id",
            existing_type=sa.Uuid(),
            nullable=False,
        )
        op.alter_column(
            table_name,
            "conversation_id",
            existing_type=sa.Uuid(),
            nullable=False,
        )
