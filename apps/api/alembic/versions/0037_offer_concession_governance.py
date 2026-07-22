"""Phase 7 offer concession governance and negotiation ledger.

Revision ID: 0037_offer_concession_governance
Revises: 0036_phase6_field_workflow
Create Date: 2026-07-22 00:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0037_offer_concession_governance"
down_revision: str | None = "0036_phase6_field_workflow"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def id_column() -> sa.Column[object]:
    return sa.Column("id", sa.Uuid(), nullable=False)


def timestamps() -> tuple[sa.Column[object], sa.Column[object]]:
    return (
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )


def index_columns(table: str, columns: tuple[str, ...]) -> None:
    for column in columns:
        op.create_index(f"ix_{table}_{column}", table, [column])


def upgrade() -> None:
    op.create_table(
        "offer_concessions",
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("lead_id", sa.Uuid(), nullable=False),
        sa.Column("property_id", sa.Uuid(), nullable=False),
        sa.Column("offer_negotiation_plan_id", sa.Uuid(), nullable=False),
        sa.Column("underwriting_version_id", sa.Uuid(), nullable=False),
        sa.Column("appointment_id", sa.Uuid(), nullable=True),
        sa.Column("requested_by_user_id", sa.Uuid(), nullable=False),
        sa.Column("approval_request_id", sa.Uuid(), nullable=True),
        sa.Column("decided_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("presented_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("sequence_number", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(40), nullable=False),
        sa.Column("authority_basis", sa.String(80), nullable=False),
        sa.Column("previous_offer_cents", sa.BigInteger(), nullable=False),
        sa.Column("proposed_offer_cents", sa.BigInteger(), nullable=False),
        sa.Column("concession_delta_cents", sa.BigInteger(), nullable=False),
        sa.Column("seller_counter_cents", sa.BigInteger(), nullable=True),
        sa.Column("reason", sa.String(2000), nullable=False),
        sa.Column("seller_exchange", sa.String(2000), nullable=False),
        sa.Column("decision_notes", sa.String(2000), nullable=True),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("presented_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("source_snapshot", sa.JSON(), nullable=False),
        id_column(),
        *timestamps(),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        sa.ForeignKeyConstraint(["lead_id"], ["leads.id"]),
        sa.ForeignKeyConstraint(["property_id"], ["properties.id"]),
        sa.ForeignKeyConstraint(["offer_negotiation_plan_id"], ["offer_negotiation_plans.id"]),
        sa.ForeignKeyConstraint(["underwriting_version_id"], ["underwriting_versions.id"]),
        sa.ForeignKeyConstraint(["appointment_id"], ["appointments.id"]),
        sa.ForeignKeyConstraint(["requested_by_user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["approval_request_id"], ["approval_requests.id"]),
        sa.ForeignKeyConstraint(["decided_by_user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["presented_by_user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "offer_negotiation_plan_id",
            "sequence_number",
            name="uq_offer_concessions_plan_sequence",
        ),
    )
    index_columns(
        "offer_concessions",
        (
            "organization_id",
            "lead_id",
            "property_id",
            "offer_negotiation_plan_id",
            "underwriting_version_id",
            "appointment_id",
            "approval_request_id",
            "status",
        ),
    )

    op.create_table(
        "offer_negotiation_events",
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("lead_id", sa.Uuid(), nullable=False),
        sa.Column("property_id", sa.Uuid(), nullable=False),
        sa.Column("offer_negotiation_plan_id", sa.Uuid(), nullable=False),
        sa.Column("concession_id", sa.Uuid(), nullable=True),
        sa.Column("appointment_id", sa.Uuid(), nullable=True),
        sa.Column("actor_user_id", sa.Uuid(), nullable=False),
        sa.Column("event_type", sa.String(80), nullable=False),
        sa.Column("channel", sa.String(40), nullable=False),
        sa.Column("previous_offer_cents", sa.BigInteger(), nullable=True),
        sa.Column("amount_cents", sa.BigInteger(), nullable=True),
        sa.Column("seller_counter_cents", sa.BigInteger(), nullable=True),
        sa.Column("notes", sa.String(2000), nullable=False),
        sa.Column("seller_response", sa.String(2000), nullable=True),
        sa.Column("objections", sa.JSON(), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("metadata", sa.JSON(), nullable=False),
        id_column(),
        *timestamps(),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        sa.ForeignKeyConstraint(["lead_id"], ["leads.id"]),
        sa.ForeignKeyConstraint(["property_id"], ["properties.id"]),
        sa.ForeignKeyConstraint(["offer_negotiation_plan_id"], ["offer_negotiation_plans.id"]),
        sa.ForeignKeyConstraint(["concession_id"], ["offer_concessions.id"]),
        sa.ForeignKeyConstraint(["appointment_id"], ["appointments.id"]),
        sa.ForeignKeyConstraint(["actor_user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    index_columns(
        "offer_negotiation_events",
        (
            "organization_id",
            "lead_id",
            "property_id",
            "offer_negotiation_plan_id",
            "concession_id",
            "appointment_id",
            "event_type",
        ),
    )

    op.add_column(
        "field_negotiation_sessions",
        sa.Column("governing_concession_id", sa.Uuid(), nullable=True),
    )
    op.create_foreign_key(
        "fk_field_negotiation_sessions_governing_concession",
        "field_negotiation_sessions",
        "offer_concessions",
        ["governing_concession_id"],
        ["id"],
    )
    op.create_index(
        "ix_field_negotiation_sessions_governing_concession_id",
        "field_negotiation_sessions",
        ["governing_concession_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_field_negotiation_sessions_governing_concession_id",
        table_name="field_negotiation_sessions",
    )
    op.drop_constraint(
        "fk_field_negotiation_sessions_governing_concession",
        "field_negotiation_sessions",
        type_="foreignkey",
    )
    op.drop_column("field_negotiation_sessions", "governing_concession_id")
    op.drop_table("offer_negotiation_events")
    op.drop_table("offer_concessions")
