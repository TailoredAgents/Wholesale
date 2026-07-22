"""Lead Manager acceptance, qualification, and next-action controls.

Revision ID: 0034_lead_manager_os
Revises: 0033_va_prospecting_workbench
Create Date: 2026-07-22 00:00:00
"""

import uuid
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta

import sqlalchemy as sa

from alembic import op

revision: str = "0034_lead_manager_os"
down_revision: str | None = "0033_va_prospecting_workbench"
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
        "lead_qualification_script_versions",
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(160), nullable=False),
        sa.Column("status", sa.String(40), nullable=False),
        sa.Column("introduction", sa.Text(), nullable=False),
        sa.Column("questions", sa.JSON(), nullable=False),
        sa.Column("completion_rules", sa.JSON(), nullable=False),
        sa.Column("created_by_user_id", sa.Uuid(), nullable=False),
        sa.Column("approved_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        id_column(),
        *timestamps(),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["approved_by_user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "organization_id",
            "version_number",
            name="uq_lead_qualification_scripts_org_version",
        ),
    )
    for column in ("organization_id", "status"):
        op.create_index(
            f"ix_lead_qualification_script_versions_{column}",
            "lead_qualification_script_versions",
            [column],
        )

    op.create_table(
        "lead_management_cases",
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("lead_id", sa.Uuid(), nullable=False),
        sa.Column("handoff_id", sa.Uuid(), nullable=True),
        sa.Column("assigned_user_id", sa.Uuid(), nullable=False),
        sa.Column("status", sa.String(40), nullable=False),
        sa.Column("acceptance_due_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("accepted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("accepted_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("escalated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("qualification_script_version_id", sa.Uuid(), nullable=True),
        sa.Column("qualification_started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("qualification_completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("qualification_quality_basis_points", sa.Integer(), nullable=True),
        sa.Column("next_action_type", sa.String(80), nullable=True),
        sa.Column("next_action_due_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_contact_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        id_column(),
        *timestamps(),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        sa.ForeignKeyConstraint(["lead_id"], ["leads.id"]),
        sa.ForeignKeyConstraint(
            ["handoff_id"], ["prospect_handoffs.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(["assigned_user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["accepted_by_user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(
            ["qualification_script_version_id"], ["lead_qualification_script_versions.id"]
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("lead_id", name="uq_lead_management_cases_lead"),
    )
    for column in (
        "organization_id",
        "lead_id",
        "handoff_id",
        "assigned_user_id",
        "status",
        "qualification_script_version_id",
        "next_action_due_at",
    ):
        op.create_index(
            f"ix_lead_management_cases_{column}", "lead_management_cases", [column]
        )
    backfill_lead_management_cases()

    op.create_table(
        "lead_qualification_sessions",
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("case_id", sa.Uuid(), nullable=False),
        sa.Column("lead_id", sa.Uuid(), nullable=False),
        sa.Column("script_version_id", sa.Uuid(), nullable=False),
        sa.Column("completed_by_user_id", sa.Uuid(), nullable=False),
        sa.Column("status", sa.String(40), nullable=False),
        sa.Column("answers", sa.JSON(), nullable=False),
        sa.Column("missing_required_keys", sa.JSON(), nullable=False),
        sa.Column("quality_score_basis_points", sa.Integer(), nullable=False),
        sa.Column("next_action_type", sa.String(80), nullable=False),
        sa.Column("next_action_due_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=False),
        id_column(),
        *timestamps(),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        sa.ForeignKeyConstraint(
            ["case_id"], ["lead_management_cases.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["lead_id"], ["leads.id"]),
        sa.ForeignKeyConstraint(
            ["script_version_id"], ["lead_qualification_script_versions.id"]
        ),
        sa.ForeignKeyConstraint(["completed_by_user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    for column in (
        "organization_id",
        "case_id",
        "lead_id",
        "script_version_id",
        "status",
    ):
        op.create_index(
            f"ix_lead_qualification_sessions_{column}",
            "lead_qualification_sessions",
            [column],
        )


def downgrade() -> None:
    op.drop_table("lead_qualification_sessions")
    op.drop_table("lead_management_cases")
    op.drop_table("lead_qualification_script_versions")


def backfill_lead_management_cases() -> None:
    bind = op.get_bind()
    handoffs = list(
        bind.execute(
            sa.text(
                """
                SELECT id, organization_id, lead_id, assigned_user_id, status,
                       submitted_at, reviewed_by_user_id, reviewed_at
                FROM prospect_handoffs
                ORDER BY submitted_at DESC
                """
            )
        ).mappings()
    )
    latest_handoff_by_lead: dict[object, object] = {}
    for handoff in handoffs:
        latest_handoff_by_lead.setdefault(handoff["lead_id"], handoff)

    role_rows = bind.execute(
        sa.text(
            """
            SELECT u.organization_id, u.id AS user_id, r.key AS role_key
            FROM users u
            JOIN role_assignments ra ON ra.user_id = u.id
            JOIN roles r ON r.id = ra.role_id
            WHERE u.is_active = true
              AND r.key IN (
                'acquisition_manager', 'acquisition_rep', 'owner',
                'founder_operator', 'administrator'
              )
            """
        )
    ).mappings()
    role_priority = {
        "acquisition_manager": 0,
        "acquisition_rep": 1,
        "owner": 2,
        "founder_operator": 2,
        "administrator": 3,
    }
    defaults: dict[object, tuple[int, object]] = {}
    eligible_user_ids: set[object] = set()
    for row in role_rows:
        eligible_user_ids.add(row["user_id"])
        candidate = (role_priority[row["role_key"]], row["user_id"])
        current = defaults.get(row["organization_id"])
        if current is None or candidate[0] < current[0]:
            defaults[row["organization_id"]] = candidate

    leads = list(bind.execute(
        sa.text(
            """
            SELECT id, organization_id, contact_id, assigned_user_id, stage_key, created_at
            FROM leads
            WHERE archived_at IS NULL
              AND stage_key NOT IN ('dead', 'disqualified', 'lost', 'closed')
            """
        )
    ).mappings())
    now = datetime.now(UTC)
    records: list[dict[str, object | None]] = []
    routed_assignments: list[tuple[object, object, object]] = []
    for lead in leads:
        handoff = latest_handoff_by_lead.get(lead["id"])
        if handoff is not None:
            assignee_id = handoff["assigned_user_id"]
            handoff_status = str(handoff["status"])
            status = {
                "pending": "awaiting_acceptance",
                "accepted": "active",
                "needs_correction": "correction_requested",
            }.get(handoff_status, "active")
            accepted_at = handoff["reviewed_at"] if handoff_status == "accepted" else None
            accepted_by = (
                handoff["reviewed_by_user_id"] if handoff_status == "accepted" else None
            )
            submitted_at = handoff["submitted_at"]
            acceptance_due_at = submitted_at + timedelta(minutes=60)
            handoff_id = handoff["id"]
        else:
            default = defaults.get(lead["organization_id"])
            existing_assignee = (
                lead["assigned_user_id"]
                if lead["assigned_user_id"] in eligible_user_ids
                else None
            )
            assignee_id = existing_assignee or (default[1] if default else None)
            if assignee_id is None:
                continue
            handoff_id = None
            if existing_assignee is not None:
                status = "active"
                accepted_at = lead["created_at"]
                accepted_by = existing_assignee
                acceptance_due_at = lead["created_at"]
            else:
                status = "awaiting_acceptance"
                accepted_at = None
                accepted_by = None
                acceptance_due_at = now + timedelta(minutes=60)
                routed_assignments.append((lead["id"], lead["contact_id"], assignee_id))
        records.append(
            {
                "id": uuid.uuid4(),
                "organization_id": lead["organization_id"],
                "lead_id": lead["id"],
                "handoff_id": handoff_id,
                "assigned_user_id": assignee_id,
                "status": status,
                "acceptance_due_at": acceptance_due_at,
                "accepted_at": accepted_at,
                "accepted_by_user_id": accepted_by,
                "escalated_at": None,
                "qualification_script_version_id": None,
                "qualification_started_at": accepted_at,
                "qualification_completed_at": None,
                "qualification_quality_basis_points": None,
                "next_action_type": None,
                "next_action_due_at": None,
                "last_contact_at": None,
                "closed_at": None,
                "created_at": lead["created_at"],
                "updated_at": now,
            }
        )
    if not records:
        return
    for lead_id, contact_id, assignee_id in routed_assignments:
        bind.execute(
            sa.text("UPDATE leads SET assigned_user_id = :user_id WHERE id = :lead_id"),
            {"user_id": assignee_id, "lead_id": lead_id},
        )
        bind.execute(
            sa.text("UPDATE contacts SET assigned_user_id = :user_id WHERE id = :contact_id"),
            {"user_id": assignee_id, "contact_id": contact_id},
        )
        conversations = list(
            bind.execute(
                sa.text(
                    "SELECT id, organization_id, assigned_user_id, queue_key "
                    "FROM conversations WHERE lead_id = :lead_id"
                ),
                {"lead_id": lead_id},
            ).mappings()
        )
        for conversation in conversations:
            bind.execute(
                sa.text(
                    "UPDATE conversations SET assigned_user_id = :user_id, "
                    "queue_key = 'qualified' WHERE id = :conversation_id"
                ),
                {"user_id": assignee_id, "conversation_id": conversation["id"]},
            )
            bind.execute(
                sa.text(
                    """
                    INSERT INTO conversation_assignment_events (
                        id, organization_id, conversation_id, lead_id, actor_user_id,
                        previous_assigned_user_id, assigned_user_id, previous_queue_key,
                        queue_key, reason, created_at
                    ) VALUES (
                        :id, :organization_id, :conversation_id, :lead_id, NULL,
                        :previous_assigned_user_id, :assigned_user_id, :previous_queue_key,
                        'qualified', :reason, :created_at
                    )
                    """
                ),
                {
                    "id": uuid.uuid4(),
                    "organization_id": conversation["organization_id"],
                    "conversation_id": conversation["id"],
                    "lead_id": lead_id,
                    "previous_assigned_user_id": conversation["assigned_user_id"],
                    "assigned_user_id": assignee_id,
                    "previous_queue_key": conversation["queue_key"],
                    "reason": "Existing active lead routed during Lead Manager migration.",
                    "created_at": now,
                },
            )
    table = sa.table(
        "lead_management_cases",
        sa.column("id", sa.Uuid()),
        sa.column("organization_id", sa.Uuid()),
        sa.column("lead_id", sa.Uuid()),
        sa.column("handoff_id", sa.Uuid()),
        sa.column("assigned_user_id", sa.Uuid()),
        sa.column("status", sa.String()),
        sa.column("acceptance_due_at", sa.DateTime(timezone=True)),
        sa.column("accepted_at", sa.DateTime(timezone=True)),
        sa.column("accepted_by_user_id", sa.Uuid()),
        sa.column("escalated_at", sa.DateTime(timezone=True)),
        sa.column("qualification_script_version_id", sa.Uuid()),
        sa.column("qualification_started_at", sa.DateTime(timezone=True)),
        sa.column("qualification_completed_at", sa.DateTime(timezone=True)),
        sa.column("qualification_quality_basis_points", sa.Integer()),
        sa.column("next_action_type", sa.String()),
        sa.column("next_action_due_at", sa.DateTime(timezone=True)),
        sa.column("last_contact_at", sa.DateTime(timezone=True)),
        sa.column("closed_at", sa.DateTime(timezone=True)),
        sa.column("created_at", sa.DateTime(timezone=True)),
        sa.column("updated_at", sa.DateTime(timezone=True)),
    )
    op.bulk_insert(table, records)
