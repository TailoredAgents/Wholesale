"""twilio sms delivery and suppression controls

Revision ID: 0019_twilio_sms
Revises: 0018_shared_inbox
Create Date: 2026-07-17 00:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0019_twilio_sms"
down_revision: str | None = "0018_shared_inbox"
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
        "suppression_records",
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("contact_id", sa.Uuid(), nullable=True),
        sa.Column("channel", sa.String(length=40), nullable=False),
        sa.Column("normalized_address", sa.String(length=320), nullable=False),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column("reason", sa.String(length=255), nullable=False),
        sa.Column("source", sa.String(length=120), nullable=False),
        sa.Column("provider", sa.String(length=80), nullable=True),
        sa.Column("external_event_id", sa.String(length=255), nullable=True),
        sa.Column("suppressed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("lifted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("metadata", sa.JSON(), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        *timestamp_columns(),
        sa.ForeignKeyConstraint(["contact_id"], ["contacts.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "organization_id",
            "channel",
            "normalized_address",
            name="uq_suppression_records_org_channel_address",
        ),
    )
    op.create_index(
        "ix_suppression_records_organization_id",
        "suppression_records",
        ["organization_id"],
    )
    op.create_index("ix_suppression_records_contact_id", "suppression_records", ["contact_id"])

    op.create_table(
        "communication_dispatches",
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("conversation_id", sa.Uuid(), nullable=False),
        sa.Column("lead_id", sa.Uuid(), nullable=False),
        sa.Column("contact_id", sa.Uuid(), nullable=False),
        sa.Column("actor_user_id", sa.Uuid(), nullable=True),
        sa.Column("communication_record_id", sa.Uuid(), nullable=True),
        sa.Column("idempotency_key", sa.String(length=120), nullable=False),
        sa.Column("channel", sa.String(length=40), nullable=False),
        sa.Column("recipient", sa.String(length=80), nullable=False),
        sa.Column("request_body_hash", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=80), nullable=False),
        sa.Column("provider", sa.String(length=80), nullable=False),
        sa.Column("provider_message_id", sa.String(length=255), nullable=True),
        sa.Column("error_code", sa.String(length=120), nullable=True),
        sa.Column("error_message", sa.String(length=2000), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("metadata", sa.JSON(), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        *timestamp_columns(),
        sa.ForeignKeyConstraint(["actor_user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(
            ["communication_record_id"],
            ["communication_records.id"],
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["conversation_id"],
            ["conversations.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(["contact_id"], ["contacts.id"]),
        sa.ForeignKeyConstraint(["lead_id"], ["leads.id"]),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "organization_id",
            "idempotency_key",
            name="uq_communication_dispatches_org_idempotency",
        ),
    )
    op.create_index(
        "ix_communication_dispatches_organization_id",
        "communication_dispatches",
        ["organization_id"],
    )
    op.create_index(
        "ix_communication_dispatches_conversation_id",
        "communication_dispatches",
        ["conversation_id"],
    )
    op.create_index("ix_communication_dispatches_lead_id", "communication_dispatches", ["lead_id"])
    op.create_index(
        "ix_communication_dispatches_contact_id",
        "communication_dispatches",
        ["contact_id"],
    )
    op.create_unique_constraint(
        "uq_communication_records_org_provider_message",
        "communication_records",
        ["organization_id", "provider", "provider_message_id"],
    )


def downgrade() -> None:
    op.drop_constraint(
        "uq_communication_records_org_provider_message",
        "communication_records",
        type_="unique",
    )
    op.drop_table("communication_dispatches")
    op.drop_table("suppression_records")
