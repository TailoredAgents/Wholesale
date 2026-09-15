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
    / "0130_retire_automatic_lead_reminders.py"
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


def test_cleanup_retires_all_generated_lead_reminders_but_keeps_manual_reminders() -> None:
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
    notifications = sa.Table(
        "notifications",
        metadata,
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("entity_type", sa.String()),
        sa.Column("entity_id", sa.Uuid()),
        sa.Column("read_at", sa.DateTime(timezone=True)),
    )
    metadata.create_all(engine)

    now = datetime.now(UTC)
    organization_id = uuid4()
    automatic_lead_id = uuid4()
    legacy_lead_id = uuid4()
    manual_lead_id = uuid4()
    automatic_task_id = uuid4()
    legacy_task_id = uuid4()
    manual_task_id = uuid4()
    automatic_due_at = now + timedelta(days=2)
    legacy_due_at = now - timedelta(days=2)
    manual_due_at = now + timedelta(days=180)

    with engine.begin() as connection:
        connection.execute(
            sa.insert(leads),
            [
                {"id": automatic_lead_id, "next_follow_up_at": automatic_due_at},
                {"id": legacy_lead_id, "next_follow_up_at": legacy_due_at},
                {"id": manual_lead_id, "next_follow_up_at": manual_due_at},
            ],
        )
        base_task = {
            "organization_id": organization_id,
            "deal_id": None,
            "work_kind": "primary_next_action",
            "status": "open",
            "updated_at": now,
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
                    "task_type": "speed_to_lead",
                    "title": "Contact Generated Seller",
                    "due_at": automatic_due_at,
                },
                {
                    **base_task,
                    "id": legacy_task_id,
                    "lead_id": legacy_lead_id,
                    "task_type": "primary_next_action",
                    "title": "Review seller lead and set the next action",
                    "due_at": legacy_due_at,
                },
                {
                    **base_task,
                    "id": manual_task_id,
                    "lead_id": manual_lead_id,
                    "task_type": "follow_up",
                    "title": "Call seller in six months",
                    "due_at": manual_due_at,
                },
            ],
        )
        automatic_notification_id = uuid4()
        manual_notification_id = uuid4()
        connection.execute(
            sa.insert(notifications),
            [
                {
                    "id": automatic_notification_id,
                    "entity_type": "task",
                    "entity_id": automatic_task_id,
                    "read_at": None,
                },
                {
                    "id": manual_notification_id,
                    "entity_type": "task",
                    "entity_id": manual_task_id,
                    "read_at": None,
                },
            ],
        )

        namespace = migration_namespace(connection)
        assert namespace["revision"] == "0130_manual_lead_reminders"
        assert namespace["down_revision"] == "0129_correct_realtime_line"
        namespace["upgrade"]()

        rows = {
            UUID(str(row.id)): row
            for row in connection.execute(
                sa.select(tasks.c.id, tasks.c.status, tasks.c.outcome)
            )
        }
        assert rows[automatic_task_id].status == "cancelled"
        assert rows[legacy_task_id].status == "cancelled"
        assert rows[manual_task_id].status == "open"
        assert rows[automatic_task_id].outcome == "automation_retired"
        assert connection.scalar(
            sa.select(leads.c.next_follow_up_at).where(leads.c.id == automatic_lead_id)
        ) is None
        assert connection.scalar(
            sa.select(leads.c.next_follow_up_at).where(leads.c.id == legacy_lead_id)
        ) is None
        assert connection.scalar(
            sa.select(leads.c.next_follow_up_at).where(leads.c.id == manual_lead_id)
        ) is not None
        assert connection.scalar(sa.select(sa.func.count()).select_from(audit_events)) == 2
        assert connection.scalar(
            sa.select(notifications.c.read_at).where(
                notifications.c.id == automatic_notification_id
            )
        ) is not None
        assert connection.scalar(
            sa.select(notifications.c.read_at).where(
                notifications.c.id == manual_notification_id
            )
        ) is None

        namespace["downgrade"]()
        assert connection.scalar(
            sa.select(tasks.c.status).where(tasks.c.id == automatic_task_id)
        ) == "cancelled"
