"""Retire overdue generic tasks created by the former automatic follow-up policy.

Revision ID: 0127_retire_legacy_tasks
Revises: 0126_company_disposition_view
"""

import uuid
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta

import sqlalchemy as sa

from alembic import op

revision: str = "0127_retire_legacy_tasks"
down_revision: str | None = "0126_company_disposition_view"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

LEGACY_TITLE = "Review seller lead and set the next action"
LEGACY_MINIMUM_OFFSET = timedelta(minutes=4, seconds=45)
LEGACY_MAXIMUM_OFFSET = timedelta(minutes=5, seconds=15)
RETIREMENT_NOTE = (
    "Retired by the explicit follow-up policy because this generic action was created "
    "automatically rather than scheduled by a person."
)

tasks = sa.table(
    "tasks",
    sa.column("id", sa.Uuid()),
    sa.column("organization_id", sa.Uuid()),
    sa.column("lead_id", sa.Uuid()),
    sa.column("deal_id", sa.Uuid()),
    sa.column("task_type", sa.String()),
    sa.column("work_kind", sa.String()),
    sa.column("title", sa.String()),
    sa.column("status", sa.String()),
    sa.column("due_at", sa.DateTime(timezone=True)),
    sa.column("created_at", sa.DateTime(timezone=True)),
    sa.column("updated_at", sa.DateTime(timezone=True)),
    sa.column("completed_at", sa.DateTime(timezone=True)),
    sa.column("completed_by_user_id", sa.Uuid()),
    sa.column("outcome", sa.String()),
    sa.column("completion_notes", sa.String()),
)
leads = sa.table(
    "leads",
    sa.column("id", sa.Uuid()),
    sa.column("next_follow_up_at", sa.DateTime(timezone=True)),
)
audit_events = sa.table(
    "audit_events",
    sa.column("id", sa.Uuid()),
    sa.column("organization_id", sa.Uuid()),
    sa.column("actor_user_id", sa.Uuid()),
    sa.column("actor_type", sa.String()),
    sa.column("action", sa.String()),
    sa.column("entity_type", sa.String()),
    sa.column("entity_id", sa.Uuid()),
    sa.column("previous_value", sa.JSON()),
    sa.column("new_value", sa.JSON()),
    sa.column("reason", sa.String()),
    sa.column("created_at", sa.DateTime(timezone=True)),
)


def _as_utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def _same_moment(first: datetime, second: datetime) -> bool:
    return abs((_as_utc(first) - _as_utc(second)).total_seconds()) <= 1


def upgrade() -> None:
    bind = op.get_bind()
    now = datetime.now(UTC)
    candidates = bind.execute(
        sa.select(
            tasks.c.id,
            tasks.c.organization_id,
            tasks.c.lead_id,
            tasks.c.status,
            tasks.c.due_at,
            tasks.c.created_at,
        ).where(
            tasks.c.deal_id.is_(None),
            tasks.c.task_type == "primary_next_action",
            tasks.c.work_kind == "primary_next_action",
            tasks.c.title == LEGACY_TITLE,
            tasks.c.status.in_(("open", "in_progress")),
            tasks.c.due_at.is_not(None),
            tasks.c.created_at.is_not(None),
        )
    ).mappings().all()

    for candidate in candidates:
        due_at = _as_utc(candidate["due_at"])
        created_at = _as_utc(candidate["created_at"])
        automatic_offset = due_at - created_at
        if due_at >= now or not (
            LEGACY_MINIMUM_OFFSET <= automatic_offset <= LEGACY_MAXIMUM_OFFSET
        ):
            continue

        bind.execute(
            sa.update(tasks)
            .where(tasks.c.id == candidate["id"])
            .values(
                status="cancelled",
                completed_at=now,
                completed_by_user_id=None,
                outcome="automation_retired",
                completion_notes=RETIREMENT_NOTE,
                updated_at=now,
            )
        )

        lead_id = candidate["lead_id"]
        if lead_id is not None:
            current_follow_up = bind.execute(
                sa.select(leads.c.next_follow_up_at).where(leads.c.id == lead_id)
            ).scalar_one_or_none()
            other_primary_exists = bind.execute(
                sa.select(tasks.c.id)
                .where(
                    tasks.c.lead_id == lead_id,
                    tasks.c.id != candidate["id"],
                    tasks.c.work_kind == "primary_next_action",
                    tasks.c.status.in_(("open", "in_progress")),
                )
                .limit(1)
            ).first()
            if (
                current_follow_up is not None
                and _same_moment(current_follow_up, due_at)
                and other_primary_exists is None
            ):
                bind.execute(
                    sa.update(leads)
                    .where(leads.c.id == lead_id)
                    .values(next_follow_up_at=None)
                )

        bind.execute(
            sa.insert(audit_events).values(
                id=uuid.uuid4(),
                organization_id=candidate["organization_id"],
                actor_user_id=None,
                actor_type="system",
                action="task.legacy_automation_retired",
                entity_type="task",
                entity_id=candidate["id"],
                previous_value={
                    "status": candidate["status"],
                    "due_at": due_at.isoformat(),
                },
                new_value={
                    "status": "cancelled",
                    "outcome": "automation_retired",
                },
                reason=RETIREMENT_NOTE,
                created_at=now,
            )
        )


def downgrade() -> None:
    # Deliberately irreversible: reopening retired automation would recreate task noise and could
    # overwrite follow-up decisions made after this migration ran.
    pass
