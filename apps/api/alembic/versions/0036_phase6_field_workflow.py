"""Phase 6 meeting briefs, inspections, negotiation, and field evidence.

Revision ID: 0036_phase6_field_workflow
Revises: 0035_field_dispatch
Create Date: 2026-07-22 00:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0036_phase6_field_workflow"
down_revision: str | None = "0035_field_dispatch"
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
        "field_meeting_briefs",
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("appointment_id", sa.Uuid(), nullable=False),
        sa.Column("lead_id", sa.Uuid(), nullable=False),
        sa.Column("generated_by_user_id", sa.Uuid(), nullable=False),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(40), nullable=False),
        sa.Column("source_snapshot", sa.JSON(), nullable=False),
        sa.Column("brief_data", sa.JSON(), nullable=False),
        id_column(),
        *timestamps(),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        sa.ForeignKeyConstraint(["appointment_id"], ["appointments.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["lead_id"], ["leads.id"]),
        sa.ForeignKeyConstraint(["generated_by_user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "appointment_id",
            "version_number",
            name="uq_field_meeting_briefs_appointment_version",
        ),
    )
    index_columns(
        "field_meeting_briefs", ("organization_id", "appointment_id", "lead_id", "status")
    )

    op.create_table(
        "field_inspections",
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("appointment_id", sa.Uuid(), nullable=False),
        sa.Column("lead_id", sa.Uuid(), nullable=False),
        sa.Column("property_id", sa.Uuid(), nullable=False),
        sa.Column("inspector_user_id", sa.Uuid(), nullable=False),
        sa.Column("status", sa.String(40), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reviewed_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("overall_condition", sa.String(80), nullable=True),
        sa.Column("occupancy_observed", sa.String(120), nullable=True),
        sa.Column("utilities_status", sa.String(120), nullable=True),
        sa.Column("access_notes", sa.String(1000), nullable=True),
        sa.Column("title_concerns", sa.String(1000), nullable=True),
        sa.Column("safety_concerns", sa.String(1000), nullable=True),
        sa.Column("room_observations", sa.JSON(), nullable=False),
        sa.Column("repair_items", sa.JSON(), nullable=False),
        sa.Column("inspector_notes", sa.String(2000), nullable=True),
        id_column(),
        *timestamps(),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        sa.ForeignKeyConstraint(["appointment_id"], ["appointments.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["lead_id"], ["leads.id"]),
        sa.ForeignKeyConstraint(["property_id"], ["properties.id"]),
        sa.ForeignKeyConstraint(["inspector_user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["reviewed_by_user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("appointment_id", name="uq_field_inspections_appointment"),
    )
    index_columns(
        "field_inspections",
        ("organization_id", "appointment_id", "lead_id", "property_id", "status"),
    )

    op.create_table(
        "field_inspection_photos",
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("inspection_id", sa.Uuid(), nullable=False),
        sa.Column("uploaded_by_user_id", sa.Uuid(), nullable=False),
        sa.Column("area", sa.String(120), nullable=False),
        sa.Column("caption", sa.String(500), nullable=True),
        sa.Column("file_name", sa.String(255), nullable=False),
        sa.Column("content_type", sa.String(120), nullable=False),
        sa.Column("byte_size", sa.Integer(), nullable=False),
        sa.Column("sha256", sa.String(64), nullable=False),
        sa.Column("captured_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("image_data", sa.LargeBinary(), nullable=False),
        id_column(),
        *timestamps(),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        sa.ForeignKeyConstraint(["inspection_id"], ["field_inspections.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["uploaded_by_user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    index_columns("field_inspection_photos", ("organization_id", "inspection_id"))

    op.create_table(
        "field_negotiation_sessions",
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("appointment_id", sa.Uuid(), nullable=False),
        sa.Column("lead_id", sa.Uuid(), nullable=False),
        sa.Column("recorded_by_user_id", sa.Uuid(), nullable=False),
        sa.Column(
            "decision_makers_confirmed", sa.Boolean(), server_default="false", nullable=False
        ),
        sa.Column("decision_makers", sa.JSON(), nullable=False),
        sa.Column("seller_asking_price_cents", sa.BigInteger(), nullable=True),
        sa.Column("offer_presented_cents", sa.BigInteger(), nullable=True),
        sa.Column("seller_counter_cents", sa.BigInteger(), nullable=True),
        sa.Column("agreed_price_cents", sa.BigInteger(), nullable=True),
        sa.Column("approved_ceiling_cents", sa.BigInteger(), nullable=True),
        sa.Column("objections", sa.JSON(), nullable=False),
        sa.Column("commitments", sa.JSON(), nullable=False),
        sa.Column("outcome", sa.String(80), nullable=False),
        sa.Column("notes", sa.String(2000), nullable=True),
        sa.Column("next_follow_up_at", sa.DateTime(timezone=True), nullable=True),
        id_column(),
        *timestamps(),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        sa.ForeignKeyConstraint(["appointment_id"], ["appointments.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["lead_id"], ["leads.id"]),
        sa.ForeignKeyConstraint(["recorded_by_user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("appointment_id", name="uq_field_negotiation_sessions_appointment"),
    )
    index_columns(
        "field_negotiation_sessions",
        ("organization_id", "appointment_id", "lead_id", "outcome"),
    )

    op.create_table(
        "field_underwriting_transfers",
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("inspection_id", sa.Uuid(), nullable=False),
        sa.Column("lead_id", sa.Uuid(), nullable=False),
        sa.Column("reviewed_by_user_id", sa.Uuid(), nullable=False),
        sa.Column("source_underwriting_version_id", sa.Uuid(), nullable=True),
        sa.Column("repair_estimate_id", sa.Uuid(), nullable=True),
        sa.Column("created_underwriting_version_id", sa.Uuid(), nullable=False),
        sa.Column("transfer_snapshot", sa.JSON(), nullable=False),
        id_column(),
        *timestamps(),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        sa.ForeignKeyConstraint(["inspection_id"], ["field_inspections.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["lead_id"], ["leads.id"]),
        sa.ForeignKeyConstraint(["reviewed_by_user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["source_underwriting_version_id"], ["underwriting_versions.id"]),
        sa.ForeignKeyConstraint(["repair_estimate_id"], ["repair_estimates.id"]),
        sa.ForeignKeyConstraint(["created_underwriting_version_id"], ["underwriting_versions.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("inspection_id", name="uq_field_underwriting_transfers_inspection"),
    )
    index_columns(
        "field_underwriting_transfers",
        ("organization_id", "inspection_id", "lead_id", "created_underwriting_version_id"),
    )


def downgrade() -> None:
    op.drop_table("field_underwriting_transfers")
    op.drop_table("field_negotiation_sessions")
    op.drop_table("field_inspection_photos")
    op.drop_table("field_inspections")
    op.drop_table("field_meeting_briefs")
