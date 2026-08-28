"""Add the governed disposition offer room and closing protection.

Revision ID: 0118_disposition_offer_room
Revises: 0117_disposition_outreach
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0118_disposition_offer_room"
down_revision: str | None = "0117_disposition_outreach"
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
    op.add_column("buyer_offers", sa.Column("idempotency_key", sa.String(120)))
    op.add_column(
        "buyer_offers",
        sa.Column("lock_version", sa.Integer(), nullable=False, server_default="1"),
    )
    op.add_column(
        "buyer_offers",
        sa.Column(
            "funding_confidence_basis_points",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
    )
    op.add_column("buyer_offers", sa.Column("due_diligence_days", sa.Integer()))
    op.add_column(
        "buyer_offers",
        sa.Column("contingencies", sa.JSON(), nullable=False, server_default="[]"),
    )
    op.add_column(
        "buyer_offers",
        sa.Column(
            "contingencies_confirmed",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )
    op.add_column("buyer_offers", sa.Column("proposed_closing_at", sa.DateTime(timezone=True)))
    op.add_column("buyer_offers", sa.Column("special_terms", sa.Text()))
    op.create_unique_constraint(
        "uq_buyer_offer_case_idempotency",
        "buyer_offers",
        ["organization_id", "disposition_case_id", "idempotency_key"],
    )
    op.create_check_constraint("ck_buyer_offer_lock_version", "buyer_offers", "lock_version >= 1")
    op.create_check_constraint(
        "ck_buyer_offer_funding_confidence",
        "buyer_offers",
        "funding_confidence_basis_points BETWEEN 0 AND 10000",
    )

    op.create_table(
        "disposition_offer_revisions",
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("disposition_case_id", sa.Uuid(), nullable=False),
        sa.Column("offer_id", sa.Uuid(), nullable=False),
        sa.Column("buyer_id", sa.Uuid(), nullable=False),
        sa.Column("created_by_user_id", sa.Uuid(), nullable=False),
        sa.Column("revision_number", sa.Integer(), nullable=False),
        sa.Column("idempotency_key", sa.String(120), nullable=False),
        sa.Column("terms_snapshot", sa.JSON(), nullable=False),
        sa.Column("risk_snapshot", sa.JSON(), nullable=False),
        sa.Column("change_reason", sa.String(1000), nullable=False),
        sa.Column("id", sa.Uuid(), primary_key=True),
        *timestamps(),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        sa.ForeignKeyConstraint(
            ["disposition_case_id"], ["disposition_cases.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["offer_id"], ["buyer_offers.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["buyer_id"], ["buyers.id"]),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"]),
        sa.UniqueConstraint(
            "offer_id", "revision_number", name="uq_disposition_offer_revision_number"
        ),
        sa.UniqueConstraint(
            "organization_id",
            "disposition_case_id",
            "idempotency_key",
            name="uq_disposition_offer_revision_idempotency",
        ),
        sa.CheckConstraint("revision_number >= 1", name="ck_disposition_offer_revision_positive"),
    )
    op.create_index(
        "ix_disposition_offer_revision_case",
        "disposition_offer_revisions",
        ["organization_id", "disposition_case_id", "created_at"],
    )

    op.create_table(
        "disposition_offer_negotiations",
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("disposition_case_id", sa.Uuid(), nullable=False),
        sa.Column("offer_id", sa.Uuid(), nullable=False),
        sa.Column("buyer_id", sa.Uuid(), nullable=False),
        sa.Column("actor_user_id", sa.Uuid(), nullable=False),
        sa.Column("event_type", sa.String(40), nullable=False),
        sa.Column("direction", sa.String(20), nullable=False),
        sa.Column("summary", sa.String(2000), nullable=False),
        sa.Column("metadata_snapshot", sa.JSON(), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("idempotency_key", sa.String(120), nullable=False),
        sa.Column("id", sa.Uuid(), primary_key=True),
        *timestamps(),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        sa.ForeignKeyConstraint(
            ["disposition_case_id"], ["disposition_cases.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["offer_id"], ["buyer_offers.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["buyer_id"], ["buyers.id"]),
        sa.ForeignKeyConstraint(["actor_user_id"], ["users.id"]),
        sa.UniqueConstraint(
            "organization_id",
            "disposition_case_id",
            "idempotency_key",
            name="uq_disposition_offer_negotiation_idem",
        ),
    )
    op.create_index(
        "ix_disposition_offer_negotiation_case",
        "disposition_offer_negotiations",
        ["organization_id", "disposition_case_id", "occurred_at"],
    )

    op.create_table(
        "disposition_buyer_selections",
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("disposition_case_id", sa.Uuid(), nullable=False),
        sa.Column("approved_by_user_id", sa.Uuid(), nullable=False),
        sa.Column("superseded_by_selection_id", sa.Uuid()),
        sa.Column("status", sa.String(40), nullable=False),
        sa.Column("lock_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("idempotency_key", sa.String(120), nullable=False),
        sa.Column("reason", sa.String(1000), nullable=False),
        sa.Column("evidence_hash", sa.String(64), nullable=False),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("replaced_at", sa.DateTime(timezone=True)),
        sa.Column("id", sa.Uuid(), primary_key=True),
        *timestamps(),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        sa.ForeignKeyConstraint(
            ["disposition_case_id"], ["disposition_cases.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["approved_by_user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(
            ["superseded_by_selection_id"],
            ["disposition_buyer_selections.id"],
            ondelete="SET NULL",
        ),
        sa.UniqueConstraint(
            "organization_id",
            "disposition_case_id",
            "idempotency_key",
            name="uq_disposition_selection_idempotency",
        ),
        sa.CheckConstraint("lock_version >= 1", name="ck_disposition_selection_lock_version"),
    )
    op.create_index(
        "uq_disposition_selection_current",
        "disposition_buyer_selections",
        ["organization_id", "disposition_case_id"],
        unique=True,
        postgresql_where=sa.text("status = 'active'"),
        sqlite_where=sa.text("status = 'active'"),
    )

    op.create_table(
        "disposition_buyer_selection_slots",
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("disposition_case_id", sa.Uuid(), nullable=False),
        sa.Column("selection_id", sa.Uuid(), nullable=False),
        sa.Column("offer_id", sa.Uuid(), nullable=False),
        sa.Column("buyer_id", sa.Uuid(), nullable=False),
        sa.Column("role", sa.String(20), nullable=False),
        sa.Column("rank", sa.Integer(), nullable=False),
        sa.Column("offer_snapshot", sa.JSON(), nullable=False),
        sa.Column("id", sa.Uuid(), primary_key=True),
        *timestamps(),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        sa.ForeignKeyConstraint(
            ["disposition_case_id"], ["disposition_cases.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["selection_id"], ["disposition_buyer_selections.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["offer_id"], ["buyer_offers.id"]),
        sa.ForeignKeyConstraint(["buyer_id"], ["buyers.id"]),
        sa.UniqueConstraint(
            "selection_id", "role", "rank", name="uq_disposition_selection_slot_rank"
        ),
        sa.UniqueConstraint("selection_id", "offer_id", name="uq_disposition_selection_slot_offer"),
        sa.CheckConstraint("rank >= 1", name="ck_disposition_selection_slot_rank"),
    )

    op.create_table(
        "disposition_closing_checkpoints",
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("disposition_case_id", sa.Uuid(), nullable=False),
        sa.Column("selection_id", sa.Uuid()),
        sa.Column("offer_id", sa.Uuid()),
        sa.Column("buyer_id", sa.Uuid()),
        sa.Column("responsible_user_id", sa.Uuid()),
        sa.Column("created_by_user_id", sa.Uuid(), nullable=False),
        sa.Column("updated_by_user_id", sa.Uuid(), nullable=False),
        sa.Column("idempotency_key", sa.String(160), nullable=False),
        sa.Column("checkpoint_type", sa.String(40), nullable=False),
        sa.Column("label", sa.String(255), nullable=False),
        sa.Column(
            "canonical_source",
            sa.String(40),
            nullable=False,
            server_default="offer_room",
        ),
        sa.Column("source_record_id", sa.Uuid()),
        sa.Column("due_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(40), nullable=False),
        sa.Column("lock_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("deadline_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.Column("notes", sa.String(2000)),
        sa.Column("evidence_snapshot", sa.JSON(), nullable=False),
        sa.Column("id", sa.Uuid(), primary_key=True),
        *timestamps(),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        sa.ForeignKeyConstraint(
            ["disposition_case_id"], ["disposition_cases.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["selection_id"], ["disposition_buyer_selections.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(["offer_id"], ["buyer_offers.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["buyer_id"], ["buyers.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["responsible_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["updated_by_user_id"], ["users.id"]),
        sa.UniqueConstraint(
            "organization_id",
            "disposition_case_id",
            "idempotency_key",
            name="uq_disposition_checkpoint_idempotency",
        ),
        sa.CheckConstraint("lock_version >= 1", name="ck_disposition_checkpoint_lock_version"),
        sa.CheckConstraint(
            "deadline_version >= 1", name="ck_disposition_checkpoint_deadline_version"
        ),
    )
    op.create_index(
        "ix_disposition_checkpoint_due",
        "disposition_closing_checkpoints",
        ["organization_id", "status", "due_at"],
    )
    op.create_index(
        "ix_disposition_checkpoint_case",
        "disposition_closing_checkpoints",
        ["organization_id", "disposition_case_id"],
    )

    op.create_table(
        "disposition_deadline_alerts",
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("disposition_case_id", sa.Uuid(), nullable=False),
        sa.Column("checkpoint_id", sa.Uuid(), nullable=False),
        sa.Column("deadline_version", sa.Integer(), nullable=False),
        sa.Column("dedupe_key", sa.String(160), nullable=False),
        sa.Column("status", sa.String(40), nullable=False),
        sa.Column("severity", sa.String(20), nullable=False),
        sa.Column("due_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("acknowledged_by_user_id", sa.Uuid()),
        sa.Column("acknowledged_at", sa.DateTime(timezone=True)),
        sa.Column("resolved_at", sa.DateTime(timezone=True)),
        sa.Column("id", sa.Uuid(), primary_key=True),
        *timestamps(),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        sa.ForeignKeyConstraint(
            ["disposition_case_id"], ["disposition_cases.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["checkpoint_id"], ["disposition_closing_checkpoints.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["acknowledged_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.UniqueConstraint(
            "organization_id", "dedupe_key", name="uq_disposition_deadline_alert_dedupe"
        ),
    )
    op.create_index(
        "ix_disposition_deadline_alert_case",
        "disposition_deadline_alerts",
        ["organization_id", "disposition_case_id", "status"],
    )

    op.create_table(
        "disposition_buyer_outcomes",
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("disposition_case_id", sa.Uuid(), nullable=False),
        sa.Column("selection_id", sa.Uuid()),
        sa.Column("offer_id", sa.Uuid(), nullable=False),
        sa.Column("buyer_id", sa.Uuid(), nullable=False),
        sa.Column("recorded_by_user_id", sa.Uuid(), nullable=False),
        sa.Column("outcome_type", sa.String(40), nullable=False),
        sa.Column("cause_category", sa.String(40), nullable=False),
        sa.Column("reason", sa.String(1000), nullable=False),
        sa.Column("details", sa.String(2000)),
        sa.Column("evidence_snapshot", sa.JSON(), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("history_applied_at", sa.DateTime(timezone=True)),
        sa.Column("completed_delta", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("failed_delta", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "reliability_delta_basis_points",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
        sa.Column("idempotency_key", sa.String(120), nullable=False),
        sa.Column("id", sa.Uuid(), primary_key=True),
        *timestamps(),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        sa.ForeignKeyConstraint(
            ["disposition_case_id"], ["disposition_cases.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["selection_id"], ["disposition_buyer_selections.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(["offer_id"], ["buyer_offers.id"]),
        sa.ForeignKeyConstraint(["buyer_id"], ["buyers.id"]),
        sa.ForeignKeyConstraint(["recorded_by_user_id"], ["users.id"]),
        sa.UniqueConstraint(
            "organization_id",
            "disposition_case_id",
            "idempotency_key",
            name="uq_disposition_buyer_outcome_idempotency",
        ),
    )
    op.create_index(
        "ix_disposition_buyer_outcome_buyer",
        "disposition_buyer_outcomes",
        ["organization_id", "buyer_id", "occurred_at"],
    )
    op.create_index(
        "uq_disposition_buyer_outcome_completed_close",
        "disposition_buyer_outcomes",
        ["organization_id", "disposition_case_id"],
        unique=True,
        postgresql_where=sa.text("outcome_type = 'completed_close'"),
        sqlite_where=sa.text("outcome_type = 'completed_close'"),
    )


def downgrade() -> None:
    op.drop_index(
        "uq_disposition_buyer_outcome_completed_close",
        table_name="disposition_buyer_outcomes",
    )
    op.drop_index("ix_disposition_buyer_outcome_buyer", table_name="disposition_buyer_outcomes")
    op.drop_table("disposition_buyer_outcomes")
    op.drop_index("ix_disposition_deadline_alert_case", table_name="disposition_deadline_alerts")
    op.drop_table("disposition_deadline_alerts")
    op.drop_index("ix_disposition_checkpoint_case", table_name="disposition_closing_checkpoints")
    op.drop_index("ix_disposition_checkpoint_due", table_name="disposition_closing_checkpoints")
    op.drop_table("disposition_closing_checkpoints")
    op.drop_table("disposition_buyer_selection_slots")
    op.drop_index("uq_disposition_selection_current", table_name="disposition_buyer_selections")
    op.drop_table("disposition_buyer_selections")
    op.drop_index(
        "ix_disposition_offer_negotiation_case",
        table_name="disposition_offer_negotiations",
    )
    op.drop_table("disposition_offer_negotiations")
    op.drop_index("ix_disposition_offer_revision_case", table_name="disposition_offer_revisions")
    op.drop_table("disposition_offer_revisions")
    op.drop_constraint("ck_buyer_offer_funding_confidence", "buyer_offers", type_="check")
    op.drop_constraint("ck_buyer_offer_lock_version", "buyer_offers", type_="check")
    op.drop_constraint("uq_buyer_offer_case_idempotency", "buyer_offers", type_="unique")
    for column in (
        "special_terms",
        "proposed_closing_at",
        "contingencies_confirmed",
        "contingencies",
        "due_diligence_days",
        "funding_confidence_basis_points",
        "lock_version",
        "idempotency_key",
    ):
        op.drop_column("buyer_offers", column)
