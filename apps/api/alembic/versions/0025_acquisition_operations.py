"""Acquisition operations workflow

Revision ID: 0025_acquisition_operations
Revises: 0024_operational_reliability
Create Date: 2026-07-21 00:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0025_acquisition_operations"
down_revision: str | None = "0024_operational_reliability"
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
        "teams",
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(160), nullable=False),
        sa.Column("team_type", sa.String(80), nullable=False),
        sa.Column("manager_user_id", sa.Uuid(), nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default="true", nullable=False),
        id_column(),
        *timestamps(),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        sa.ForeignKeyConstraint(["manager_user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("organization_id", "name", name="uq_teams_org_name"),
    )
    op.create_index("ix_teams_organization_id", "teams", ["organization_id"])
    op.create_table(
        "team_memberships",
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("team_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("membership_role", sa.String(80), nullable=False),
        id_column(),
        *timestamps(),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        sa.ForeignKeyConstraint(["team_id"], ["teams.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("team_id", "user_id", name="uq_team_memberships_team_user"),
    )
    op.create_index("ix_team_memberships_organization_id", "team_memberships", ["organization_id"])
    op.create_index("ix_team_memberships_team_id", "team_memberships", ["team_id"])
    op.create_index("ix_team_memberships_user_id", "team_memberships", ["user_id"])
    op.create_table(
        "calendar_events",
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("appointment_id", sa.Uuid(), nullable=False),
        sa.Column("owner_user_id", sa.Uuid(), nullable=True),
        sa.Column("provider", sa.String(80), nullable=False),
        sa.Column("external_event_id", sa.String(255), nullable=True),
        sa.Column("status", sa.String(80), nullable=False),
        sa.Column("event_payload", sa.JSON(), nullable=False),
        sa.Column("last_error", sa.String(2000), nullable=True),
        sa.Column("synced_at", sa.DateTime(timezone=True), nullable=True),
        id_column(),
        *timestamps(),
        sa.ForeignKeyConstraint(["appointment_id"], ["appointments.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        sa.ForeignKeyConstraint(["owner_user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "organization_id",
            "appointment_id",
            "provider",
            name="uq_calendar_events_org_appointment_provider",
        ),
    )
    op.create_index("ix_calendar_events_organization_id", "calendar_events", ["organization_id"])
    op.create_index("ix_calendar_events_appointment_id", "calendar_events", ["appointment_id"])
    op.create_index("ix_calendar_events_status", "calendar_events", ["status"])
    _create_operational_tables()


def _create_operational_tables() -> None:
    table_specs: list[
        tuple[
            str, list[sa.Column[object]], list[sa.ForeignKeyConstraint], list[sa.UniqueConstraint]
        ]
    ] = []
    table_specs.append(
        (
            "calling_lists",
            [
                sa.Column("organization_id", sa.Uuid(), nullable=False),
                sa.Column("name", sa.String(160), nullable=False),
                sa.Column("description", sa.String(1000), nullable=True),
                sa.Column("status", sa.String(80), nullable=False),
                sa.Column("created_by_user_id", sa.Uuid(), nullable=False),
                sa.Column("default_assignee_user_id", sa.Uuid(), nullable=True),
            ],
            [
                sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
                sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"]),
                sa.ForeignKeyConstraint(["default_assignee_user_id"], ["users.id"]),
            ],
            [sa.UniqueConstraint("organization_id", "name", name="uq_calling_lists_org_name")],
        )
    )
    table_specs.append(
        (
            "calling_list_entries",
            [
                sa.Column("organization_id", sa.Uuid(), nullable=False),
                sa.Column("calling_list_id", sa.Uuid(), nullable=False),
                sa.Column("lead_id", sa.Uuid(), nullable=False),
                sa.Column("assigned_user_id", sa.Uuid(), nullable=True),
                sa.Column("status", sa.String(80), nullable=False),
                sa.Column("attempt_count", sa.Integer(), server_default="0", nullable=False),
                sa.Column("disposition", sa.String(120), nullable=True),
                sa.Column("notes", sa.String(1000), nullable=True),
                sa.Column("last_attempt_at", sa.DateTime(timezone=True), nullable=True),
                sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
            ],
            [
                sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
                sa.ForeignKeyConstraint(
                    ["calling_list_id"], ["calling_lists.id"], ondelete="CASCADE"
                ),
                sa.ForeignKeyConstraint(["lead_id"], ["leads.id"]),
                sa.ForeignKeyConstraint(["assigned_user_id"], ["users.id"]),
            ],
            [
                sa.UniqueConstraint(
                    "calling_list_id", "lead_id", name="uq_calling_list_entries_list_lead"
                )
            ],
        )
    )
    table_specs.append(
        (
            "saved_views",
            [
                sa.Column("organization_id", sa.Uuid(), nullable=False),
                sa.Column("owner_user_id", sa.Uuid(), nullable=False),
                sa.Column("team_id", sa.Uuid(), nullable=True),
                sa.Column("resource_type", sa.String(80), nullable=False),
                sa.Column("name", sa.String(160), nullable=False),
                sa.Column("filters", sa.JSON(), nullable=False),
                sa.Column("is_shared", sa.Boolean(), server_default="false", nullable=False),
            ],
            [
                sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
                sa.ForeignKeyConstraint(["owner_user_id"], ["users.id"]),
                sa.ForeignKeyConstraint(["team_id"], ["teams.id"]),
            ],
            [
                sa.UniqueConstraint(
                    "organization_id",
                    "owner_user_id",
                    "resource_type",
                    "name",
                    name="uq_saved_views_owner_resource_name",
                )
            ],
        )
    )
    table_specs.append(
        (
            "notifications",
            [
                sa.Column("organization_id", sa.Uuid(), nullable=False),
                sa.Column("recipient_user_id", sa.Uuid(), nullable=False),
                sa.Column("notification_type", sa.String(120), nullable=False),
                sa.Column("title", sa.String(255), nullable=False),
                sa.Column("body", sa.String(1000), nullable=False),
                sa.Column("entity_type", sa.String(120), nullable=True),
                sa.Column("entity_id", sa.Uuid(), nullable=True),
                sa.Column("action_url", sa.String(500), nullable=True),
                sa.Column("dedupe_key", sa.String(255), nullable=False),
                sa.Column("read_at", sa.DateTime(timezone=True), nullable=True),
            ],
            [
                sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
                sa.ForeignKeyConstraint(["recipient_user_id"], ["users.id"]),
            ],
            [
                sa.UniqueConstraint(
                    "organization_id",
                    "recipient_user_id",
                    "dedupe_key",
                    name="uq_notifications_recipient_dedupe",
                )
            ],
        )
    )
    table_specs.append(
        (
            "duplicate_candidates",
            [
                sa.Column("organization_id", sa.Uuid(), nullable=False),
                sa.Column("primary_lead_id", sa.Uuid(), nullable=False),
                sa.Column("duplicate_lead_id", sa.Uuid(), nullable=False),
                sa.Column("status", sa.String(80), nullable=False),
                sa.Column("match_score", sa.Integer(), nullable=False),
                sa.Column("match_reasons", sa.JSON(), nullable=False),
                sa.Column("reviewed_by_user_id", sa.Uuid(), nullable=True),
                sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
                sa.Column("resolution_notes", sa.String(1000), nullable=True),
            ],
            [
                sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
                sa.ForeignKeyConstraint(["primary_lead_id"], ["leads.id"]),
                sa.ForeignKeyConstraint(["duplicate_lead_id"], ["leads.id"]),
                sa.ForeignKeyConstraint(["reviewed_by_user_id"], ["users.id"]),
            ],
            [
                sa.UniqueConstraint(
                    "organization_id",
                    "primary_lead_id",
                    "duplicate_lead_id",
                    name="uq_duplicate_candidates_lead_pair",
                )
            ],
        )
    )
    table_specs.append(
        (
            "lead_merge_events",
            [
                sa.Column("organization_id", sa.Uuid(), nullable=False),
                sa.Column("primary_lead_id", sa.Uuid(), nullable=False),
                sa.Column("duplicate_lead_id", sa.Uuid(), nullable=False),
                sa.Column("merged_by_user_id", sa.Uuid(), nullable=False),
                sa.Column("merge_strategy", sa.String(80), nullable=False),
                sa.Column("merge_snapshot", sa.JSON(), nullable=False),
            ],
            [
                sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
                sa.ForeignKeyConstraint(["primary_lead_id"], ["leads.id"]),
                sa.ForeignKeyConstraint(["duplicate_lead_id"], ["leads.id"]),
                sa.ForeignKeyConstraint(["merged_by_user_id"], ["users.id"]),
            ],
            [],
        )
    )
    table_specs.append(
        (
            "follow_up_plans",
            [
                sa.Column("organization_id", sa.Uuid(), nullable=False),
                sa.Column("name", sa.String(160), nullable=False),
                sa.Column("description", sa.String(1000), nullable=True),
                sa.Column("status", sa.String(80), nullable=False),
                sa.Column("created_by_user_id", sa.Uuid(), nullable=False),
                sa.Column("steps", sa.JSON(), nullable=False),
            ],
            [
                sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
                sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"]),
            ],
            [sa.UniqueConstraint("organization_id", "name", name="uq_follow_up_plans_org_name")],
        )
    )
    table_specs.append(
        (
            "follow_up_enrollments",
            [
                sa.Column("organization_id", sa.Uuid(), nullable=False),
                sa.Column("follow_up_plan_id", sa.Uuid(), nullable=False),
                sa.Column("lead_id", sa.Uuid(), nullable=False),
                sa.Column("enrolled_by_user_id", sa.Uuid(), nullable=False),
                sa.Column("status", sa.String(80), nullable=False),
                sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
                sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
                sa.Column("current_step", sa.Integer(), server_default="0", nullable=False),
            ],
            [
                sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
                sa.ForeignKeyConstraint(["follow_up_plan_id"], ["follow_up_plans.id"]),
                sa.ForeignKeyConstraint(["lead_id"], ["leads.id"]),
                sa.ForeignKeyConstraint(["enrolled_by_user_id"], ["users.id"]),
            ],
            [
                sa.UniqueConstraint(
                    "follow_up_plan_id",
                    "lead_id",
                    "status",
                    name="uq_follow_up_enrollments_plan_lead_status",
                )
            ],
        )
    )
    for name, columns, foreign_keys, unique_constraints in table_specs:
        op.create_table(
            name,
            *columns,
            id_column(),
            *timestamps(),
            *foreign_keys,
            sa.PrimaryKeyConstraint("id"),
            *unique_constraints,
        )
        op.create_index(f"ix_{name}_organization_id", name, ["organization_id"])
    for table, columns in {
        "calling_lists": ("status",),
        "calling_list_entries": ("calling_list_id", "lead_id", "assigned_user_id", "status"),
        "saved_views": ("owner_user_id", "team_id"),
        "notifications": ("recipient_user_id", "notification_type"),
        "duplicate_candidates": ("primary_lead_id", "duplicate_lead_id", "status"),
        "lead_merge_events": ("primary_lead_id", "duplicate_lead_id"),
        "follow_up_plans": ("status",),
        "follow_up_enrollments": ("follow_up_plan_id", "lead_id", "status"),
    }.items():
        for column in columns:
            op.create_index(f"ix_{table}_{column}", table, [column])


def downgrade() -> None:
    for table in (
        "follow_up_enrollments",
        "follow_up_plans",
        "lead_merge_events",
        "duplicate_candidates",
        "notifications",
        "saved_views",
        "calling_list_entries",
        "calling_lists",
        "calendar_events",
        "team_memberships",
        "teams",
    ):
        op.drop_table(table)
