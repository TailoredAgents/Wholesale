"""shared inbox foundation

Revision ID: 0018_shared_inbox
Revises: 0017_lead_archiving
Create Date: 2026-07-17 00:00:00
"""

import uuid
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0018_shared_inbox"
down_revision: str | None = "0017_lead_archiving"
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
        "conversations",
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("lead_id", sa.Uuid(), nullable=False),
        sa.Column("contact_id", sa.Uuid(), nullable=False),
        sa.Column("assigned_user_id", sa.Uuid(), nullable=True),
        sa.Column("status", sa.String(length=80), nullable=False),
        sa.Column("queue_key", sa.String(length=120), nullable=False),
        sa.Column("priority", sa.String(length=80), nullable=False),
        sa.Column("unread_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("last_activity_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_inbound_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_outbound_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("metadata", sa.JSON(), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        *timestamp_columns(),
        sa.ForeignKeyConstraint(["assigned_user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["contact_id"], ["contacts.id"]),
        sa.ForeignKeyConstraint(["lead_id"], ["leads.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "organization_id",
            "lead_id",
            name="uq_conversations_org_lead",
        ),
    )
    op.create_index("ix_conversations_organization_id", "conversations", ["organization_id"])
    op.create_index("ix_conversations_lead_id", "conversations", ["lead_id"])
    op.create_index("ix_conversations_contact_id", "conversations", ["contact_id"])
    op.create_index("ix_conversations_assigned_user_id", "conversations", ["assigned_user_id"])
    op.create_index("ix_conversations_queue_key", "conversations", ["queue_key"])

    bind = op.get_bind()
    lead_rows = bind.execute(
        sa.text("SELECT id, organization_id, contact_id, assigned_user_id, created_at FROM leads")
    ).mappings()
    conversations_table = sa.table(
        "conversations",
        sa.column("id", sa.Uuid()),
        sa.column("organization_id", sa.Uuid()),
        sa.column("lead_id", sa.Uuid()),
        sa.column("contact_id", sa.Uuid()),
        sa.column("assigned_user_id", sa.Uuid()),
        sa.column("status", sa.String()),
        sa.column("queue_key", sa.String()),
        sa.column("priority", sa.String()),
        sa.column("unread_count", sa.Integer()),
        sa.column("last_activity_at", sa.DateTime(timezone=True)),
        sa.column("metadata", sa.JSON()),
    )
    conversation_rows = [
        {
            "id": uuid.uuid4(),
            "organization_id": row["organization_id"],
            "lead_id": row["id"],
            "contact_id": row["contact_id"],
            "assigned_user_id": row["assigned_user_id"],
            "status": "open",
            "queue_key": ("acquisitions_follow_up" if row["assigned_user_id"] else "unassigned"),
            "priority": "normal",
            "unread_count": 0,
            "last_activity_at": row["created_at"],
            "metadata": {"source": "migration", "unified_timeline": True},
        }
        for row in lead_rows
    ]
    if conversation_rows:
        op.bulk_insert(conversations_table, conversation_rows)

    op.add_column(
        "communication_records",
        sa.Column("conversation_id", sa.Uuid(), nullable=True),
    )
    op.create_foreign_key(
        "fk_communication_records_conversation_id",
        "communication_records",
        "conversations",
        ["conversation_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_communication_records_conversation_id",
        "communication_records",
        ["conversation_id"],
    )
    bind.execute(
        sa.text(
            "UPDATE communication_records "
            "SET conversation_id = ("
            "SELECT conversations.id FROM conversations "
            "WHERE conversations.organization_id = communication_records.organization_id "
            "AND conversations.lead_id = communication_records.lead_id"
            ")"
        )
    )

    op.create_table(
        "conversation_watchers",
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("conversation_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("source", sa.String(length=80), nullable=False),
        sa.Column("notification_level", sa.String(length=80), nullable=False),
        sa.Column("is_muted", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        *timestamp_columns(),
        sa.ForeignKeyConstraint(
            ["conversation_id"],
            ["conversations.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "conversation_id",
            "user_id",
            name="uq_conversation_watchers_conversation_user",
        ),
    )
    op.create_index(
        "ix_conversation_watchers_organization_id",
        "conversation_watchers",
        ["organization_id"],
    )
    op.create_index(
        "ix_conversation_watchers_conversation_id",
        "conversation_watchers",
        ["conversation_id"],
    )
    op.create_index("ix_conversation_watchers_user_id", "conversation_watchers", ["user_id"])

    op.create_table(
        "conversation_assignment_events",
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("conversation_id", sa.Uuid(), nullable=False),
        sa.Column("lead_id", sa.Uuid(), nullable=False),
        sa.Column("actor_user_id", sa.Uuid(), nullable=True),
        sa.Column("previous_assigned_user_id", sa.Uuid(), nullable=True),
        sa.Column("assigned_user_id", sa.Uuid(), nullable=True),
        sa.Column("previous_queue_key", sa.String(length=120), nullable=False),
        sa.Column("queue_key", sa.String(length=120), nullable=False),
        sa.Column("reason", sa.String(length=500), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(["actor_user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["assigned_user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(
            ["conversation_id"],
            ["conversations.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(["lead_id"], ["leads.id"]),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        sa.ForeignKeyConstraint(["previous_assigned_user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_conversation_assignment_events_organization_id",
        "conversation_assignment_events",
        ["organization_id"],
    )
    op.create_index(
        "ix_conversation_assignment_events_conversation_id",
        "conversation_assignment_events",
        ["conversation_id"],
    )
    op.create_index(
        "ix_conversation_assignment_events_lead_id",
        "conversation_assignment_events",
        ["lead_id"],
    )
    assignment_events_table = sa.table(
        "conversation_assignment_events",
        sa.column("id", sa.Uuid()),
        sa.column("organization_id", sa.Uuid()),
        sa.column("conversation_id", sa.Uuid()),
        sa.column("lead_id", sa.Uuid()),
        sa.column("actor_user_id", sa.Uuid()),
        sa.column("previous_assigned_user_id", sa.Uuid()),
        sa.column("assigned_user_id", sa.Uuid()),
        sa.column("previous_queue_key", sa.String()),
        sa.column("queue_key", sa.String()),
        sa.column("reason", sa.String()),
    )
    if conversation_rows:
        op.bulk_insert(
            assignment_events_table,
            [
                {
                    "id": uuid.uuid4(),
                    "organization_id": row["organization_id"],
                    "conversation_id": row["id"],
                    "lead_id": row["lead_id"],
                    "actor_user_id": None,
                    "previous_assigned_user_id": None,
                    "assigned_user_id": row["assigned_user_id"],
                    "previous_queue_key": "unassigned",
                    "queue_key": row["queue_key"],
                    "reason": "Conversation backfilled from existing lead.",
                }
                for row in conversation_rows
            ],
        )

    op.create_table(
        "communication_provider_events",
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("conversation_id", sa.Uuid(), nullable=True),
        sa.Column("provider", sa.String(length=80), nullable=False),
        sa.Column("event_type", sa.String(length=120), nullable=False),
        sa.Column("external_event_id", sa.String(length=255), nullable=False),
        sa.Column("processing_status", sa.String(length=80), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_message", sa.String(length=2000), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        *timestamp_columns(),
        sa.ForeignKeyConstraint(
            ["conversation_id"],
            ["conversations.id"],
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "organization_id",
            "provider",
            "external_event_id",
            name="uq_provider_events_org_provider_external",
        ),
    )
    op.create_index(
        "ix_communication_provider_events_organization_id",
        "communication_provider_events",
        ["organization_id"],
    )
    op.create_index(
        "ix_communication_provider_events_conversation_id",
        "communication_provider_events",
        ["conversation_id"],
    )

    op.create_table(
        "call_records",
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("conversation_id", sa.Uuid(), nullable=False),
        sa.Column("lead_id", sa.Uuid(), nullable=False),
        sa.Column("contact_id", sa.Uuid(), nullable=False),
        sa.Column("actor_user_id", sa.Uuid(), nullable=True),
        sa.Column("communication_record_id", sa.Uuid(), nullable=True),
        sa.Column("provider", sa.String(length=80), nullable=False),
        sa.Column("provider_call_id", sa.String(length=255), nullable=True),
        sa.Column("direction", sa.String(length=40), nullable=False),
        sa.Column("status", sa.String(length=80), nullable=False),
        sa.Column("from_number", sa.String(length=80), nullable=True),
        sa.Column("to_number", sa.String(length=80), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("answered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("duration_seconds", sa.Integer(), nullable=True),
        sa.Column("disposition", sa.String(length=120), nullable=True),
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
            "provider",
            "provider_call_id",
            name="uq_call_records_org_provider_call",
        ),
    )
    op.create_index("ix_call_records_organization_id", "call_records", ["organization_id"])
    op.create_index("ix_call_records_conversation_id", "call_records", ["conversation_id"])
    op.create_index("ix_call_records_lead_id", "call_records", ["lead_id"])
    op.create_index("ix_call_records_contact_id", "call_records", ["contact_id"])

    op.create_table(
        "call_recordings",
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("call_record_id", sa.Uuid(), nullable=False),
        sa.Column("provider", sa.String(length=80), nullable=False),
        sa.Column("provider_recording_id", sa.String(length=255), nullable=True),
        sa.Column("status", sa.String(length=80), nullable=False),
        sa.Column("media_reference", sa.String(length=1000), nullable=True),
        sa.Column("duration_seconds", sa.Integer(), nullable=True),
        sa.Column("channel_count", sa.Integer(), nullable=True),
        sa.Column("consent_status", sa.String(length=80), nullable=False),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("metadata", sa.JSON(), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        *timestamp_columns(),
        sa.ForeignKeyConstraint(
            ["call_record_id"],
            ["call_records.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "organization_id",
            "provider",
            "provider_recording_id",
            name="uq_call_recordings_org_provider_recording",
        ),
    )
    op.create_index(
        "ix_call_recordings_organization_id",
        "call_recordings",
        ["organization_id"],
    )
    op.create_index("ix_call_recordings_call_record_id", "call_recordings", ["call_record_id"])

    op.create_table(
        "call_transcripts",
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("recording_id", sa.Uuid(), nullable=False),
        sa.Column("provider", sa.String(length=80), nullable=False),
        sa.Column("model_name", sa.String(length=120), nullable=True),
        sa.Column("status", sa.String(length=80), nullable=False),
        sa.Column("language", sa.String(length=40), nullable=True),
        sa.Column("transcript_text", sa.Text(), nullable=True),
        sa.Column("speaker_segments", sa.JSON(), nullable=True),
        sa.Column("confidence_score", sa.Integer(), nullable=True),
        sa.Column("approved_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_message", sa.String(length=2000), nullable=True),
        sa.Column("metadata", sa.JSON(), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        *timestamp_columns(),
        sa.ForeignKeyConstraint(["approved_by_user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        sa.ForeignKeyConstraint(
            ["recording_id"],
            ["call_recordings.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_call_transcripts_organization_id",
        "call_transcripts",
        ["organization_id"],
    )
    op.create_index("ix_call_transcripts_recording_id", "call_transcripts", ["recording_id"])


def downgrade() -> None:
    op.drop_table("call_transcripts")
    op.drop_table("call_recordings")
    op.drop_table("call_records")
    op.drop_table("communication_provider_events")
    op.drop_table("conversation_assignment_events")
    op.drop_table("conversation_watchers")
    op.drop_index(
        "ix_communication_records_conversation_id",
        table_name="communication_records",
    )
    op.drop_constraint(
        "fk_communication_records_conversation_id",
        "communication_records",
        type_="foreignkey",
    )
    op.drop_column("communication_records", "conversation_id")
    op.drop_table("conversations")
