"""twilio voice lines, call intents, and call lifecycle fields

Revision ID: 0020_twilio_voice
Revises: 0019_twilio_sms
Create Date: 2026-07-17 00:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0020_twilio_voice"
down_revision: str | None = "0019_twilio_sms"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def timestamp_columns() -> list[sa.Column]:
    return [
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
    ]


def upgrade() -> None:
    op.create_table(
        "voice_lines",
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("assigned_user_id", sa.Uuid(), nullable=True),
        sa.Column("provider", sa.String(length=80), nullable=False),
        sa.Column("provider_phone_number_id", sa.String(length=255), nullable=True),
        sa.Column("phone_number", sa.String(length=80), nullable=False),
        sa.Column("label", sa.String(length=120), nullable=False),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column("is_default", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("inbound_route", sa.String(length=80), nullable=False),
        sa.Column("metadata", sa.JSON(), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        *timestamp_columns(),
        sa.ForeignKeyConstraint(["assigned_user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "organization_id",
            "phone_number",
            name="uq_voice_lines_org_phone_number",
        ),
    )
    op.create_index("ix_voice_lines_organization_id", "voice_lines", ["organization_id"])
    op.create_index("ix_voice_lines_assigned_user_id", "voice_lines", ["assigned_user_id"])

    op.create_table(
        "voice_call_intents",
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("conversation_id", sa.Uuid(), nullable=False),
        sa.Column("lead_id", sa.Uuid(), nullable=False),
        sa.Column("contact_id", sa.Uuid(), nullable=False),
        sa.Column("actor_user_id", sa.Uuid(), nullable=False),
        sa.Column("voice_line_id", sa.Uuid(), nullable=False),
        sa.Column("idempotency_key", sa.String(length=120), nullable=False),
        sa.Column("recipient", sa.String(length=80), nullable=False),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column("recording_consent_status", sa.String(length=80), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("provider_call_id", sa.String(length=255), nullable=True),
        sa.Column("metadata", sa.JSON(), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        *timestamp_columns(),
        sa.ForeignKeyConstraint(["actor_user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(
            ["conversation_id"],
            ["conversations.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(["contact_id"], ["contacts.id"]),
        sa.ForeignKeyConstraint(["lead_id"], ["leads.id"]),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        sa.ForeignKeyConstraint(["voice_line_id"], ["voice_lines.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "organization_id",
            "idempotency_key",
            name="uq_voice_call_intents_org_idempotency",
        ),
    )
    op.create_index(
        "ix_voice_call_intents_organization_id",
        "voice_call_intents",
        ["organization_id"],
    )
    op.create_index(
        "ix_voice_call_intents_conversation_id",
        "voice_call_intents",
        ["conversation_id"],
    )
    op.create_index("ix_voice_call_intents_lead_id", "voice_call_intents", ["lead_id"])
    op.create_index("ix_voice_call_intents_contact_id", "voice_call_intents", ["contact_id"])
    op.create_index(
        "ix_voice_call_intents_actor_user_id",
        "voice_call_intents",
        ["actor_user_id"],
    )
    op.create_index(
        "ix_voice_call_intents_voice_line_id",
        "voice_call_intents",
        ["voice_line_id"],
    )

    op.add_column("call_records", sa.Column("voice_line_id", sa.Uuid(), nullable=True))
    op.add_column("call_records", sa.Column("call_intent_id", sa.Uuid(), nullable=True))
    op.add_column(
        "call_records",
        sa.Column("child_provider_call_id", sa.String(length=255), nullable=True),
    )
    op.add_column(
        "call_records",
        sa.Column(
            "recording_consent_status",
            sa.String(length=80),
            server_default="not_requested",
            nullable=False,
        ),
    )
    op.create_foreign_key(
        "fk_call_records_voice_line_id",
        "call_records",
        "voice_lines",
        ["voice_line_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        "fk_call_records_call_intent_id",
        "call_records",
        "voice_call_intents",
        ["call_intent_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index("ix_call_records_voice_line_id", "call_records", ["voice_line_id"])
    op.create_index("ix_call_records_call_intent_id", "call_records", ["call_intent_id"])
    op.create_index(
        "ix_call_records_child_provider_call_id",
        "call_records",
        ["child_provider_call_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_call_records_child_provider_call_id", table_name="call_records")
    op.drop_index("ix_call_records_call_intent_id", table_name="call_records")
    op.drop_index("ix_call_records_voice_line_id", table_name="call_records")
    op.drop_constraint(
        "fk_call_records_call_intent_id",
        "call_records",
        type_="foreignkey",
    )
    op.drop_constraint(
        "fk_call_records_voice_line_id",
        "call_records",
        type_="foreignkey",
    )
    op.drop_column("call_records", "recording_consent_status")
    op.drop_column("call_records", "child_provider_call_id")
    op.drop_column("call_records", "call_intent_id")
    op.drop_column("call_records", "voice_line_id")
    op.drop_table("voice_call_intents")
    op.drop_table("voice_lines")
