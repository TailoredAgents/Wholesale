from datetime import UTC, datetime, timedelta
from pathlib import Path
from runpy import run_path
from typing import Any
from uuid import UUID, uuid4

import sqlalchemy as sa

MIGRATION = (
    Path(__file__).parents[1]
    / "alembic"
    / "versions"
    / "0127_retire_legacy_automatic_tasks.py"
)


class MigrationOp:
    def __init__(self, connection: sa.Connection) -> None:
        self.connection = connection

    def get_bind(self) -> sa.Connection:
        return self.connection


def migration_namespace(connection: sa.Connection) -> dict[str, Any]:
    namespace = run_path(str(MIGRATION))
    recorder = MigrationOp(connection)
    namespace["upgrade"].__globals__["op"] = recorder
    namespace["downgrade"].__globals__["op"] = recorder
    return namespace


def test_cleanup_only_retires_overdue_five_minute_legacy_automation() -> None:
    engine = sa.create_engine("sqlite://")
    metadata = sa.MetaData()
    leads = sa.Table(
        "leads",
        metadata,
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("next_follow_up_at", sa.DateTime(timezone=True)),
    )
    tasks = sa.Table(
        "tasks",
        metadata,
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("lead_id", sa.Uuid()),
        sa.Column("deal_id", sa.Uuid()),
        sa.Column("task_type", sa.String(), nullable=False),
        sa.Column("work_kind", sa.String(), nullable=False),
        sa.Column("title", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("due_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.Column("completed_by_user_id", sa.Uuid()),
        sa.Column("outcome", sa.String()),
        sa.Column("completion_notes", sa.String()),
    )
    audit_events = sa.Table(
        "audit_events",
        metadata,
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("actor_user_id", sa.Uuid()),
        sa.Column("actor_type", sa.String(), nullable=False),
        sa.Column("action", sa.String(), nullable=False),
        sa.Column("entity_type", sa.String(), nullable=False),
        sa.Column("entity_id", sa.Uuid()),
        sa.Column("previous_value", sa.JSON()),
        sa.Column("new_value", sa.JSON()),
        sa.Column("reason", sa.String()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    metadata.create_all(engine)

    now = datetime.now(UTC)
    organization_id = uuid4()
    automatic_lead_id = uuid4()
    explicit_lead_id = uuid4()
    automatic_task_id = uuid4()
    explicit_task_id = uuid4()
    speed_task_id = uuid4()
    future_task_id = uuid4()
    automatic_created_at = now - timedelta(days=2)
    automatic_due_at = automatic_created_at + timedelta(minutes=5)
    explicit_created_at = now - timedelta(days=3)
    explicit_due_at = now - timedelta(days=1)
    future_created_at = now - timedelta(minutes=1)

    with engine.begin() as connection:
        connection.execute(
            sa.insert(leads),
            [
                {"id": automatic_lead_id, "next_follow_up_at": automatic_due_at},
                {"id": explicit_lead_id, "next_follow_up_at": explicit_due_at},
            ],
        )
        base_task = {
            "organization_id": organization_id,
            "deal_id": None,
            "work_kind": "primary_next_action",
            "status": "open",
            "updated_at": automatic_created_at,
            "completed_at": None,
            "completed_by_user_id": None,
            "outcome": None,
            "completion_notes": None,
        }
        connection.execute(
            sa.insert(tasks),
            [
                {
                    **base_task,
                    "id": automatic_task_id,
                    "lead_id": automatic_lead_id,
                    "task_type": "primary_next_action",
                    "title": "Review seller lead and set the next action",
                    "due_at": automatic_due_at,
                    "created_at": automatic_created_at,
                },
                {
                    **base_task,
                    "id": explicit_task_id,
                    "lead_id": explicit_lead_id,
                    "task_type": "primary_next_action",
                    "title": "Review seller lead and set the next action",
                    "due_at": explicit_due_at,
                    "created_at": explicit_created_at,
                },
                {
                    **base_task,
                    "id": speed_task_id,
                    "lead_id": explicit_lead_id,
                    "task_type": "speed_to_lead",
                    "title": "Contact Explicit Seller",
                    "due_at": automatic_due_at,
                    "created_at": automatic_created_at,
                },
                {
                    **base_task,
                    "id": future_task_id,
                    "lead_id": explicit_lead_id,
                    "task_type": "primary_next_action",
                    "title": "Review seller lead and set the next action",
                    "due_at": future_created_at + timedelta(minutes=5),
                    "created_at": future_created_at,
                },
            ],
        )

        namespace = migration_namespace(connection)
        assert namespace["revision"] == "0127_retire_legacy_tasks"
        assert namespace["down_revision"] == "0126_company_disposition_view"
        namespace["upgrade"]()

        rows = {
            row.id: row
            for row in connection.execute(
                sa.select(tasks.c.id, tasks.c.status, tasks.c.outcome, tasks.c.completion_notes)
            )
        }
        assert rows[automatic_task_id].status == "cancelled"
        assert rows[automatic_task_id].outcome == "automation_retired"
        assert "explicit follow-up policy" in rows[automatic_task_id].completion_notes
        assert rows[explicit_task_id].status == "open"
        assert rows[speed_task_id].status == "open"
        assert rows[future_task_id].status == "open"
        assert connection.scalar(
            sa.select(leads.c.next_follow_up_at).where(leads.c.id == automatic_lead_id)
        ) is None
        assert connection.scalar(
            sa.select(leads.c.next_follow_up_at).where(leads.c.id == explicit_lead_id)
        ) is not None
        audit = connection.execute(sa.select(audit_events)).mappings().one()
        assert UUID(str(audit["entity_id"])) == automatic_task_id
        assert audit["actor_type"] == "system"
        assert audit["action"] == "task.legacy_automation_retired"

        namespace["downgrade"]()
        assert connection.scalar(
            sa.select(tasks.c.status).where(tasks.c.id == automatic_task_id)
        ) == "cancelled"
