"""Unify tasks, approvals, and primary next actions.

Revision ID: 0078_tasks_primary_actions
Revises: 0077_user_calling_eligibility
"""

import uuid
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta

import sqlalchemy as sa

from alembic import op

revision: str = "0078_tasks_primary_actions"
down_revision: str | None = "0077_user_calling_eligibility"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("tasks", sa.Column("deal_id", sa.Uuid(), nullable=True))
    op.add_column(
        "tasks",
        sa.Column(
            "work_kind",
            sa.String(length=40),
            nullable=False,
            server_default="supporting",
        ),
    )
    op.add_column("tasks", sa.Column("completed_by_user_id", sa.Uuid(), nullable=True))
    op.add_column("tasks", sa.Column("outcome", sa.String(length=120), nullable=True))
    op.add_column("tasks", sa.Column("completion_notes", sa.String(length=2000), nullable=True))
    op.add_column("tasks", sa.Column("successor_task_id", sa.Uuid(), nullable=True))
    op.create_foreign_key("fk_tasks_deal_id_deals", "tasks", "deals", ["deal_id"], ["id"])
    op.create_foreign_key(
        "fk_tasks_completed_by_user_id_users",
        "tasks",
        "users",
        ["completed_by_user_id"],
        ["id"],
    )
    op.create_foreign_key(
        "fk_tasks_successor_task_id_tasks",
        "tasks",
        "tasks",
        ["successor_task_id"],
        ["id"],
    )
    op.create_index("ix_tasks_deal_id", "tasks", ["deal_id"], unique=False)
    op.create_index("ix_tasks_work_kind", "tasks", ["work_kind"], unique=False)

    connection = op.get_bind()
    task_rows = connection.execute(
        sa.text(
            """
            SELECT id, lead_id
            FROM tasks
            WHERE status IN ('open', 'in_progress')
              AND task_type IN (
                  'speed_to_lead',
                  'lead_manager_next_action',
                  'appointment_recovery'
              )
            ORDER BY lead_id, created_at DESC, id DESC
            """
        )
    ).mappings()
    selected_leads: set[uuid.UUID] = set()
    for row in task_rows:
        lead_id = row["lead_id"]
        if lead_id is None or lead_id in selected_leads:
            continue
        connection.execute(
            sa.text("UPDATE tasks SET work_kind = 'primary_next_action' WHERE id = :task_id"),
            {"task_id": row["id"]},
        )
        selected_leads.add(lead_id)

    now = datetime.now(UTC)
    uncovered_leads = connection.execute(
        sa.text(
            """
            SELECT leads.id, leads.organization_id, leads.assigned_user_id,
                   leads.next_follow_up_at
            FROM leads
            WHERE leads.archived_at IS NULL
              AND leads.stage_key NOT IN ('dead', 'disqualified', 'closed')
              AND NOT EXISTS (
                  SELECT 1
                  FROM tasks
                  WHERE tasks.lead_id = leads.id
                    AND tasks.work_kind = 'primary_next_action'
                    AND tasks.status IN ('open', 'in_progress')
              )
            """
        )
    ).mappings()
    for lead in uncovered_leads:
        connection.execute(
            sa.text(
                """
                INSERT INTO tasks (
                    id, organization_id, lead_id, deal_id, responsible_user_id,
                    task_type, work_kind, title, status, priority, due_at,
                    completed_at, completed_by_user_id, outcome, completion_notes,
                    successor_task_id, created_at, updated_at
                ) VALUES (
                    :id, :organization_id, :lead_id, NULL, :responsible_user_id,
                    'primary_next_action', 'primary_next_action',
                    'Review seller lead and set the next action', 'open', 'high',
                    :due_at, NULL, NULL, NULL, NULL, NULL, :created_at, :updated_at
                )
                """
            ),
            {
                "id": uuid.uuid4(),
                "organization_id": lead["organization_id"],
                "lead_id": lead["id"],
                "responsible_user_id": lead["assigned_user_id"],
                "due_at": lead["next_follow_up_at"] or now + timedelta(minutes=5),
                "created_at": now,
                "updated_at": now,
            },
        )

    deal_rows = connection.execute(
        sa.text(
            """
            SELECT deals.id, deals.organization_id, deals.lead_id,
                   COALESCE(
                       transactions.coordinator_user_id,
                       transactions.owner_user_id,
                       leads.assigned_user_id
                   ) AS responsible_user_id,
                   COALESCE(
                       transactions.due_diligence_deadline,
                       transactions.assignment_deadline,
                       transactions.closing_date,
                       :now
                   ) AS due_at
            FROM deals
            JOIN leads ON leads.id = deals.lead_id
            LEFT JOIN transactions ON transactions.deal_id = deals.id
                AND transactions.status NOT IN ('funded', 'cancelled')
            WHERE deals.stage_key NOT IN ('funded', 'closed', 'cancelled', 'dead')
              AND NOT EXISTS (
                  SELECT 1
                  FROM tasks
                  WHERE tasks.deal_id = deals.id
                    AND tasks.work_kind = 'primary_next_action'
                    AND tasks.status IN ('open', 'in_progress')
              )
            """
        ),
        {"now": now},
    ).mappings()
    selected_deals: set[uuid.UUID] = set()
    for deal in deal_rows:
        if deal["id"] in selected_deals:
            continue
        selected_deals.add(deal["id"])
        connection.execute(
            sa.text(
                """
                UPDATE tasks
                SET status = 'cancelled',
                    completed_at = :completed_at,
                    outcome = 'moved_to_deal'
                WHERE lead_id = :lead_id
                  AND work_kind = 'primary_next_action'
                  AND status IN ('open', 'in_progress')
                """
            ),
            {"lead_id": deal["lead_id"], "completed_at": now},
        )
        connection.execute(
            sa.text(
                """
                INSERT INTO tasks (
                    id, organization_id, lead_id, deal_id, responsible_user_id,
                    task_type, work_kind, title, status, priority, due_at,
                    completed_at, completed_by_user_id, outcome, completion_notes,
                    successor_task_id, created_at, updated_at
                ) VALUES (
                    :id, :organization_id, :lead_id, :deal_id, :responsible_user_id,
                    'deal_next_action', 'primary_next_action',
                    'Advance the deal to its next milestone', 'open', 'high',
                    :due_at, NULL, NULL, NULL, NULL, NULL, :created_at, :updated_at
                )
                """
            ),
            {
                "id": uuid.uuid4(),
                "organization_id": deal["organization_id"],
                "lead_id": deal["lead_id"],
                "deal_id": deal["id"],
                "responsible_user_id": deal["responsible_user_id"],
                "due_at": deal["due_at"] or now,
                "created_at": now,
                "updated_at": now,
            },
        )

    op.create_index(
        "uq_tasks_active_primary_lead",
        "tasks",
        ["organization_id", "lead_id"],
        unique=True,
        postgresql_where=sa.text(
            "work_kind = 'primary_next_action' "
            "AND status IN ('open', 'in_progress') "
            "AND lead_id IS NOT NULL"
        ),
        sqlite_where=sa.text(
            "work_kind = 'primary_next_action' "
            "AND status IN ('open', 'in_progress') "
            "AND lead_id IS NOT NULL"
        ),
    )
    op.create_index(
        "uq_tasks_active_primary_deal",
        "tasks",
        ["organization_id", "deal_id"],
        unique=True,
        postgresql_where=sa.text(
            "work_kind = 'primary_next_action' "
            "AND status IN ('open', 'in_progress') "
            "AND deal_id IS NOT NULL"
        ),
        sqlite_where=sa.text(
            "work_kind = 'primary_next_action' "
            "AND status IN ('open', 'in_progress') "
            "AND deal_id IS NOT NULL"
        ),
    )


def downgrade() -> None:
    op.drop_index("uq_tasks_active_primary_deal", table_name="tasks")
    op.drop_index("uq_tasks_active_primary_lead", table_name="tasks")
    op.drop_index("ix_tasks_work_kind", table_name="tasks")
    op.drop_index("ix_tasks_deal_id", table_name="tasks")
    op.drop_constraint("fk_tasks_successor_task_id_tasks", "tasks", type_="foreignkey")
    op.drop_constraint("fk_tasks_completed_by_user_id_users", "tasks", type_="foreignkey")
    op.drop_constraint("fk_tasks_deal_id_deals", "tasks", type_="foreignkey")
    op.drop_column("tasks", "successor_task_id")
    op.drop_column("tasks", "completion_notes")
    op.drop_column("tasks", "outcome")
    op.drop_column("tasks", "completed_by_user_id")
    op.drop_column("tasks", "work_kind")
    op.drop_column("tasks", "deal_id")
