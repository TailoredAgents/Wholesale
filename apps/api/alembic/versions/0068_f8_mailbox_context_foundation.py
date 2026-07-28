"""Generalize shared Inbox conversations for mailbox contexts.

Revision ID: 0068_f8_mailbox_context
Revises: 0067_f8_resend_inbound
"""

import uuid
from collections.abc import Iterable, Sequence
from email.utils import getaddresses
from typing import Any

import sqlalchemy as sa

from alembic import op

revision: str = "0068_f8_mailbox_context"
down_revision: str | None = "0067_f8_resend_inbound"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "conversations",
        sa.Column(
            "conversation_type",
            sa.String(40),
            server_default="lead",
            nullable=False,
        ),
    )
    op.add_column(
        "conversations",
        sa.Column("assigned_team_id", sa.Uuid(), nullable=True),
    )
    op.add_column(
        "conversations",
        sa.Column("source_alias_id", sa.Uuid(), nullable=True),
    )
    op.add_column(
        "conversations",
        sa.Column(
            "visibility_scope",
            sa.String(40),
            server_default="standard",
            nullable=False,
        ),
    )
    op.create_index(
        "ix_conversations_conversation_type",
        "conversations",
        ["conversation_type"],
    )
    op.create_index(
        "ix_conversations_assigned_team_id",
        "conversations",
        ["assigned_team_id"],
    )
    op.create_index(
        "ix_conversations_source_alias_id",
        "conversations",
        ["source_alias_id"],
    )
    op.create_index(
        "ix_conversations_visibility_scope",
        "conversations",
        ["visibility_scope"],
    )
    op.create_foreign_key(
        "fk_conversations_assigned_team_id",
        "conversations",
        "teams",
        ["assigned_team_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        "fk_conversations_source_alias_id",
        "conversations",
        "email_sender_aliases",
        ["source_alias_id"],
        ["id"],
        ondelete="SET NULL",
    )

    _drop_foreign_keys("conversations", {"lead_id"})
    op.alter_column(
        "conversations",
        "lead_id",
        existing_type=sa.Uuid(),
        nullable=True,
    )
    op.create_foreign_key(
        "fk_conversations_lead_id_preserve_history",
        "conversations",
        "leads",
        ["lead_id"],
        ["id"],
        ondelete="SET NULL",
    )
    for table_name in (
        "communication_records",
        "communication_dispatches",
        "conversation_assignment_events",
    ):
        op.alter_column(
            table_name,
            "lead_id",
            existing_type=sa.Uuid(),
            nullable=True,
        )

    op.create_check_constraint(
        "ck_conversations_type",
        "conversations",
        "conversation_type IN ('lead', 'transaction', 'buyer', 'general')",
    )
    op.create_check_constraint(
        "ck_conversations_lead_context",
        "conversations",
        "conversation_type != 'lead' OR lead_id IS NOT NULL",
    )
    op.create_check_constraint(
        "ck_conversations_visibility_scope",
        "conversations",
        "visibility_scope IN ('standard', 'restricted')",
    )

    op.create_table(
        "conversation_context_links",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("conversation_id", sa.Uuid(), nullable=False),
        sa.Column("context_type", sa.String(40), nullable=False),
        sa.Column("lead_id", sa.Uuid()),
        sa.Column("transaction_id", sa.Uuid()),
        sa.Column("buyer_id", sa.Uuid()),
        sa.Column("disposition_case_id", sa.Uuid()),
        sa.Column("created_by_user_id", sa.Uuid()),
        sa.Column("is_primary", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("metadata", sa.JSON()),
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
        sa.CheckConstraint(
            "("
            "context_type = 'lead' AND lead_id IS NOT NULL "
            "AND transaction_id IS NULL AND buyer_id IS NULL AND disposition_case_id IS NULL"
            ") OR ("
            "context_type = 'transaction' AND lead_id IS NULL "
            "AND transaction_id IS NOT NULL AND buyer_id IS NULL "
            "AND disposition_case_id IS NULL"
            ") OR ("
            "context_type = 'buyer' AND lead_id IS NULL "
            "AND transaction_id IS NULL AND buyer_id IS NOT NULL "
            "AND disposition_case_id IS NULL"
            ") OR ("
            "context_type = 'disposition' AND lead_id IS NULL "
            "AND transaction_id IS NULL AND buyer_id IS NULL "
            "AND disposition_case_id IS NOT NULL"
            ")",
            name="ck_conversation_context_links_target",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
        ),
        sa.ForeignKeyConstraint(
            ["conversation_id"],
            ["conversations.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(["lead_id"], ["leads.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["transaction_id"],
            ["transactions.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(["buyer_id"], ["buyers.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["disposition_case_id"],
            ["disposition_cases.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["created_by_user_id"],
            ["users.id"],
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "conversation_id",
            "lead_id",
            name="uq_conversation_context_links_lead",
        ),
        sa.UniqueConstraint(
            "conversation_id",
            "transaction_id",
            name="uq_conversation_context_links_transaction",
        ),
        sa.UniqueConstraint(
            "conversation_id",
            "buyer_id",
            name="uq_conversation_context_links_buyer",
        ),
        sa.UniqueConstraint(
            "conversation_id",
            "disposition_case_id",
            name="uq_conversation_context_links_disposition",
        ),
    )
    for column_name in (
        "organization_id",
        "conversation_id",
        "context_type",
        "lead_id",
        "transaction_id",
        "buyer_id",
        "disposition_case_id",
    ):
        op.create_index(
            f"ix_conversation_context_links_{column_name}",
            "conversation_context_links",
            [column_name],
        )
    op.create_index(
        "uq_conversation_context_links_primary",
        "conversation_context_links",
        ["conversation_id"],
        unique=True,
        postgresql_where=sa.text("is_primary"),
    )

    op.create_table(
        "communication_participants",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("communication_record_id", sa.Uuid(), nullable=False),
        sa.Column("conversation_id", sa.Uuid(), nullable=False),
        sa.Column("contact_id", sa.Uuid()),
        sa.Column("user_id", sa.Uuid()),
        sa.Column("email_sender_alias_id", sa.Uuid()),
        sa.Column("participant_role", sa.String(40), nullable=False),
        sa.Column("email_address", sa.String(320), nullable=False),
        sa.Column("normalized_email", sa.String(320), nullable=False),
        sa.Column("display_name", sa.String(255)),
        sa.Column("metadata", sa.JSON()),
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
        sa.CheckConstraint(
            "participant_role IN ('from', 'to', 'cc', 'bcc', 'reply_to')",
            name="ck_communication_participants_role",
        ),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        sa.ForeignKeyConstraint(
            ["communication_record_id"],
            ["communication_records.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["conversation_id"],
            ["conversations.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(["contact_id"], ["contacts.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(
            ["email_sender_alias_id"],
            ["email_sender_aliases.id"],
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "communication_record_id",
            "participant_role",
            "normalized_email",
            name="uq_communication_participants_message_role_email",
        ),
    )
    for column_name in (
        "organization_id",
        "communication_record_id",
        "conversation_id",
        "contact_id",
        "user_id",
        "email_sender_alias_id",
        "participant_role",
        "normalized_email",
    ):
        op.create_index(
            f"ix_communication_participants_{column_name}",
            "communication_participants",
            [column_name],
        )

    _backfill_lead_contexts()
    _backfill_email_participants()


def downgrade() -> None:
    bind = op.get_bind()
    nullable_lead_counts = {
        table_name: bind.execute(
            sa.text(f"SELECT COUNT(*) FROM {table_name} WHERE lead_id IS NULL")
        ).scalar_one()
        for table_name in (
            "conversations",
            "communication_records",
            "communication_dispatches",
            "conversation_assignment_events",
        )
    }
    if any(nullable_lead_counts.values()):
        raise RuntimeError(
            "Cannot downgrade the mailbox context migration while lead-independent "
            f"records exist: {nullable_lead_counts}"
        )

    for column_name in (
        "normalized_email",
        "participant_role",
        "email_sender_alias_id",
        "user_id",
        "contact_id",
        "conversation_id",
        "communication_record_id",
        "organization_id",
    ):
        op.drop_index(
            f"ix_communication_participants_{column_name}",
            table_name="communication_participants",
        )
    op.drop_table("communication_participants")

    op.drop_index(
        "uq_conversation_context_links_primary",
        table_name="conversation_context_links",
    )
    for column_name in reversed(
        (
            "organization_id",
            "conversation_id",
            "context_type",
            "lead_id",
            "transaction_id",
            "buyer_id",
            "disposition_case_id",
        )
    ):
        op.drop_index(
            f"ix_conversation_context_links_{column_name}",
            table_name="conversation_context_links",
        )
    op.drop_table("conversation_context_links")

    op.drop_constraint(
        "ck_conversations_visibility_scope",
        "conversations",
        type_="check",
    )
    op.drop_constraint(
        "ck_conversations_lead_context",
        "conversations",
        type_="check",
    )
    op.drop_constraint("ck_conversations_type", "conversations", type_="check")

    _drop_foreign_keys("conversations", {"lead_id"})
    for table_name in (
        "conversation_assignment_events",
        "communication_dispatches",
        "communication_records",
        "conversations",
    ):
        op.alter_column(
            table_name,
            "lead_id",
            existing_type=sa.Uuid(),
            nullable=False,
        )
    op.create_foreign_key(
        "conversations_lead_id_fkey",
        "conversations",
        "leads",
        ["lead_id"],
        ["id"],
        ondelete="CASCADE",
    )

    op.drop_constraint(
        "fk_conversations_source_alias_id",
        "conversations",
        type_="foreignkey",
    )
    op.drop_constraint(
        "fk_conversations_assigned_team_id",
        "conversations",
        type_="foreignkey",
    )
    op.drop_index("ix_conversations_visibility_scope", table_name="conversations")
    op.drop_index("ix_conversations_source_alias_id", table_name="conversations")
    op.drop_index("ix_conversations_assigned_team_id", table_name="conversations")
    op.drop_index("ix_conversations_conversation_type", table_name="conversations")
    op.drop_column("conversations", "visibility_scope")
    op.drop_column("conversations", "source_alias_id")
    op.drop_column("conversations", "assigned_team_id")
    op.drop_column("conversations", "conversation_type")


def _drop_foreign_keys(table_name: str, constrained_columns: set[str]) -> None:
    inspector = sa.inspect(op.get_bind())
    for foreign_key in inspector.get_foreign_keys(table_name):
        if set(foreign_key.get("constrained_columns") or []) != constrained_columns:
            continue
        name = foreign_key.get("name")
        if not name:
            raise RuntimeError(
                f"Cannot safely replace unnamed foreign key on {table_name}: "
                f"{sorted(constrained_columns)}"
            )
        op.drop_constraint(name, table_name, type_="foreignkey")


def _backfill_lead_contexts() -> None:
    bind = op.get_bind()
    rows = bind.execute(
        sa.text(
            "SELECT id, organization_id, lead_id "
            "FROM conversations WHERE lead_id IS NOT NULL"
        )
    ).mappings()
    context_table = sa.table(
        "conversation_context_links",
        sa.column("id", sa.Uuid()),
        sa.column("organization_id", sa.Uuid()),
        sa.column("conversation_id", sa.Uuid()),
        sa.column("context_type", sa.String()),
        sa.column("lead_id", sa.Uuid()),
        sa.column("is_primary", sa.Boolean()),
        sa.column("metadata", sa.JSON()),
    )
    values = [
        {
            "id": uuid.uuid4(),
            "organization_id": row["organization_id"],
            "conversation_id": row["id"],
            "context_type": "lead",
            "lead_id": row["lead_id"],
            "is_primary": True,
            "metadata": {"source": "0068_backfill"},
        }
        for row in rows
    ]
    if values:
        op.bulk_insert(context_table, values)


def _backfill_email_participants() -> None:
    bind = op.get_bind()
    rows = bind.execute(
        sa.text(
            "SELECT id, organization_id, conversation_id, contact_id, actor_user_id, "
            "direction, metadata FROM communication_records "
            "WHERE channel = 'email' AND conversation_id IS NOT NULL"
        )
    ).mappings()
    participant_table = sa.table(
        "communication_participants",
        sa.column("id", sa.Uuid()),
        sa.column("organization_id", sa.Uuid()),
        sa.column("communication_record_id", sa.Uuid()),
        sa.column("conversation_id", sa.Uuid()),
        sa.column("contact_id", sa.Uuid()),
        sa.column("user_id", sa.Uuid()),
        sa.column("email_sender_alias_id", sa.Uuid()),
        sa.column("participant_role", sa.String()),
        sa.column("email_address", sa.String()),
        sa.column("normalized_email", sa.String()),
        sa.column("display_name", sa.String()),
        sa.column("metadata", sa.JSON()),
    )
    values: list[dict[str, Any]] = []
    for row in rows:
        metadata = row["metadata"] if isinstance(row["metadata"], dict) else {}
        alias_id = _optional_uuid(metadata.get("email_sender_alias_id"))
        for role in ("from", "to", "cc", "bcc"):
            role_values = _string_values(metadata.get(role))
            seen: set[str] = set()
            for display_name, address in getaddresses(role_values):
                normalized = address.strip().lower()
                if not _valid_email(normalized) or normalized in seen:
                    continue
                seen.add(normalized)
                is_external = (
                    row["direction"] == "inbound" and role == "from"
                ) or (row["direction"] == "outbound" and role in {"to", "cc", "bcc"})
                values.append(
                    {
                        "id": uuid.uuid4(),
                        "organization_id": row["organization_id"],
                        "communication_record_id": row["id"],
                        "conversation_id": row["conversation_id"],
                        "contact_id": row["contact_id"] if is_external else None,
                        "user_id": (
                            row["actor_user_id"]
                            if row["direction"] == "outbound" and role == "from"
                            else None
                        ),
                        "email_sender_alias_id": alias_id if role == "from" else None,
                        "participant_role": role,
                        "email_address": address.strip(),
                        "normalized_email": normalized,
                        "display_name": display_name.strip() or None,
                        "metadata": {"source": "0068_backfill"},
                    }
                )
    if values:
        op.bulk_insert(participant_table, values)


def _string_values(value: object) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, Iterable) and not isinstance(value, (bytes, dict)):
        return [item for item in value if isinstance(item, str)]
    return []


def _optional_uuid(value: object) -> uuid.UUID | None:
    try:
        return uuid.UUID(str(value)) if value else None
    except (TypeError, ValueError):
        return None


def _valid_email(value: str) -> bool:
    local, separator, domain = value.rpartition("@")
    return bool(separator and local and "." in domain and not any(char.isspace() for char in value))
