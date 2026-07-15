from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.auth import Principal
from app.core.config import get_settings
from app.models.foundation import ActivityEvent, AuditEvent, Contact, Lead, Property, Task, User
from app.schemas.tasks import TaskQueueItemRead, TaskRead

SPEED_TO_LEAD_TASK_TYPE = "speed_to_lead"
OPEN_TASK_STATUSES = ("open", "in_progress")


def ensure_speed_to_lead_task(db: Session, lead: Lead, contact: Contact) -> Task:
    existing = db.scalar(
        select(Task).where(
            Task.organization_id == lead.organization_id,
            Task.lead_id == lead.id,
            Task.task_type == SPEED_TO_LEAD_TASK_TYPE,
            Task.status.in_(OPEN_TASK_STATUSES),
        )
    )
    if existing is not None:
        return existing

    due_at = datetime.now(UTC) + timedelta(minutes=get_settings().speed_to_lead_due_minutes)
    task = Task(
        organization_id=lead.organization_id,
        lead_id=lead.id,
        responsible_user_id=lead.assigned_user_id,
        task_type=SPEED_TO_LEAD_TASK_TYPE,
        title=f"Contact {contact.legal_name}",
        status="open",
        priority="urgent",
        due_at=due_at,
        completed_at=None,
    )
    db.add(task)
    db.flush()
    db.add(
        ActivityEvent(
            organization_id=lead.organization_id,
            actor_user_id=None,
            entity_type="lead",
            entity_id=lead.id,
            event_type="task.speed_to_lead_created",
            summary=f"Speed-to-lead task created for {contact.legal_name}.",
        )
    )
    return task


def list_speed_to_lead_queue(
    db: Session,
    principal: Principal,
    limit: int = 25,
) -> list[TaskQueueItemRead]:
    rows = get_open_task_rows(
        db,
        principal,
        limit=limit,
        task_type=SPEED_TO_LEAD_TASK_TYPE,
    )
    now = datetime.now(UTC)
    return [task_queue_item_read(row, now) for row in rows]


def list_open_task_queue(
    db: Session,
    principal: Principal,
    limit: int = 50,
) -> list[TaskQueueItemRead]:
    rows = get_open_task_rows(db, principal, limit=limit)
    now = datetime.now(UTC)
    return [task_queue_item_read(row, now) for row in rows]


def get_open_task_rows(
    db: Session,
    principal: Principal,
    *,
    limit: int,
    task_type: str | None = None,
) -> list[Any]:
    filters = [
        Task.organization_id == principal.organization_id,
        Task.status.in_(OPEN_TASK_STATUSES),
    ]
    if task_type is not None:
        filters.append(Task.task_type == task_type)
    rows = db.execute(
        select(Task, Lead, Contact, Property, User)
        .join(Lead, Lead.id == Task.lead_id)
        .join(Contact, Contact.id == Lead.contact_id)
        .join(Property, Property.id == Lead.property_id)
        .outerjoin(User, User.id == Task.responsible_user_id)
        .where(*filters)
        .order_by(Task.due_at.is_(None), Task.due_at.asc(), Task.created_at.asc())
        .limit(limit)
    ).all()
    return list(rows)


def task_queue_item_read(
    row: Any,
    now: datetime,
) -> TaskQueueItemRead:
    task, lead, contact, property_record, user = row
    return TaskQueueItemRead(
        task_id=task.id,
        lead_id=lead.id,
        task_type=task.task_type,
        title=task.title,
        seller_name=contact.legal_name,
        property_address=(
            f"{property_record.street_address}, {property_record.city}, "
            f"{property_record.state} {property_record.postal_code}"
        ),
        source=lead.source,
        stage_key=lead.stage_key,
        priority=task.priority,
        status=task.status,
        due_at=task.due_at,
        created_at=task.created_at,
        assigned_user_email=user.email if user else None,
        due_status=get_due_status(task, now),
    )


def complete_task(
    db: Session,
    principal: Principal,
    task_id: UUID,
    *,
    reason: str | None,
) -> TaskRead | None:
    task = db.scalar(
        select(Task).where(
            Task.organization_id == principal.organization_id,
            Task.id == task_id,
        )
    )
    if task is None:
        return None
    if task.status == "completed":
        return task_to_read(task)

    previous_status = task.status
    task.status = "completed"
    task.completed_at = datetime.now(UTC)
    db.add(
        ActivityEvent(
            organization_id=principal.organization_id,
            actor_user_id=principal.user_id,
            entity_type="task",
            entity_id=task.id,
            event_type="task.completed",
            summary=f"Task completed: {task.title}.",
        )
    )
    db.add(
        AuditEvent(
            organization_id=principal.organization_id,
            actor_user_id=principal.user_id,
            actor_type="user",
            action="task.complete",
            entity_type="task",
            entity_id=task.id,
            previous_value={"status": previous_status},
            new_value={"status": task.status, "completed_at": task.completed_at.isoformat()},
            reason=reason,
        )
    )
    db.commit()
    db.refresh(task)
    return task_to_read(task)


def get_due_status(task: Task, now: datetime) -> str:
    if task.due_at is None:
        return "unscheduled"
    due_at = task.due_at if task.due_at.tzinfo else task.due_at.replace(tzinfo=UTC)
    if due_at <= now:
        return "overdue"
    return "due"


def task_to_read(task: Task) -> TaskRead:
    return TaskRead(
        id=task.id,
        lead_id=task.lead_id,
        task_type=task.task_type,
        title=task.title,
        status=task.status,
        priority=task.priority,
        due_at=task.due_at,
        completed_at=task.completed_at,
    )
