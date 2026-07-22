"""Closer availability, capacity, territory, and appointment dispatch.

Revision ID: 0035_field_dispatch
Revises: 0034_lead_manager_os
Create Date: 2026-07-22 00:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0035_field_dispatch"
down_revision: str | None = "0034_lead_manager_os"
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


def upgrade() -> None:
    op.create_table(
        "closer_dispatch_profiles",
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("timezone", sa.String(80), nullable=False),
        sa.Column("working_days", sa.JSON(), nullable=False),
        sa.Column("workday_start_minute", sa.Integer(), nullable=False),
        sa.Column("workday_end_minute", sa.Integer(), nullable=False),
        sa.Column("daily_capacity", sa.Integer(), nullable=False),
        sa.Column("default_appointment_minutes", sa.Integer(), nullable=False),
        sa.Column("travel_buffer_minutes", sa.Integer(), nullable=False),
        sa.Column("home_base_postal_code", sa.String(20), nullable=True),
        sa.Column(
            "territory_enforcement_enabled",
            sa.Boolean(),
            server_default="true",
            nullable=False,
        ),
        sa.Column("is_active", sa.Boolean(), server_default="true", nullable=False),
        id_column(),
        *timestamps(),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "organization_id",
            "user_id",
            name="uq_closer_dispatch_profiles_org_user",
        ),
    )
    op.create_index(
        "ix_closer_dispatch_profiles_organization_id",
        "closer_dispatch_profiles",
        ["organization_id"],
    )
    op.create_index("ix_closer_dispatch_profiles_user_id", "closer_dispatch_profiles", ["user_id"])

    op.create_table(
        "closer_territory_coverages",
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("dispatch_profile_id", sa.Uuid(), nullable=False),
        sa.Column("territory_id", sa.Uuid(), nullable=False),
        id_column(),
        *timestamps(),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        sa.ForeignKeyConstraint(
            ["dispatch_profile_id"], ["closer_dispatch_profiles.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["territory_id"], ["territories.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "dispatch_profile_id",
            "territory_id",
            name="uq_closer_territory_coverages_profile_territory",
        ),
    )
    for column in ("organization_id", "dispatch_profile_id", "territory_id"):
        op.create_index(
            f"ix_closer_territory_coverages_{column}",
            "closer_territory_coverages",
            [column],
        )

    op.create_table(
        "closer_availability_blocks",
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("dispatch_profile_id", sa.Uuid(), nullable=False),
        sa.Column("block_type", sa.String(40), nullable=False),
        sa.Column("starts_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ends_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("reason", sa.String(500), nullable=False),
        sa.Column("created_by_user_id", sa.Uuid(), nullable=False),
        id_column(),
        *timestamps(),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        sa.ForeignKeyConstraint(
            ["dispatch_profile_id"], ["closer_dispatch_profiles.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    for column in ("organization_id", "dispatch_profile_id", "block_type"):
        op.create_index(
            f"ix_closer_availability_blocks_{column}",
            "closer_availability_blocks",
            [column],
        )

    op.create_table(
        "appointment_dispatch_records",
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("appointment_id", sa.Uuid(), nullable=False),
        sa.Column("lead_id", sa.Uuid(), nullable=False),
        sa.Column("closer_user_id", sa.Uuid(), nullable=False),
        sa.Column("territory_id", sa.Uuid(), nullable=True),
        sa.Column("decided_by_user_id", sa.Uuid(), nullable=False),
        sa.Column("decision_status", sa.String(40), nullable=False),
        sa.Column("scheduled_start_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("scheduled_end_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("daily_booked_count", sa.Integer(), nullable=False),
        sa.Column("travel_buffer_minutes", sa.Integer(), nullable=False),
        sa.Column("territory_match", sa.Boolean(), nullable=False),
        sa.Column("violations", sa.JSON(), nullable=False),
        sa.Column("candidate_snapshot", sa.JSON(), nullable=False),
        sa.Column("decision_reason", sa.String(1000), nullable=True),
        id_column(),
        *timestamps(),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        sa.ForeignKeyConstraint(["appointment_id"], ["appointments.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["lead_id"], ["leads.id"]),
        sa.ForeignKeyConstraint(["closer_user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["territory_id"], ["territories.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["decided_by_user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    for column in (
        "organization_id",
        "appointment_id",
        "lead_id",
        "closer_user_id",
        "territory_id",
        "decision_status",
    ):
        op.create_index(
            f"ix_appointment_dispatch_records_{column}",
            "appointment_dispatch_records",
            [column],
        )


def downgrade() -> None:
    op.drop_table("appointment_dispatch_records")
    op.drop_table("closer_availability_blocks")
    op.drop_table("closer_territory_coverages")
    op.drop_table("closer_dispatch_profiles")
