import json
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.core.auth import Principal
from app.core.config import get_settings
from app.domain.assets import property_identity_label
from app.domain.rbac import PermissionKeys
from app.models.foundation import (
    ActivityEvent,
    AiOrchestratorEvent,
    AiRunLog,
    ApprovalRequest,
    AuditEvent,
    Contact,
    Deal,
    Lead,
    LeadManagementCase,
    Property,
    Task,
    User,
)
from app.schemas.tasks import (
    PrimaryNextActionCreate,
    PrimaryNextActionRead,
    TaskCompleteRequest,
    TaskDueStatus,
    TaskQueueItemRead,
    TaskRead,
    TaskWorkKind,
    TaskWorkspaceItemRead,
    TaskWorkspaceRead,
)
from app.services.approvals import (
    APPROVAL_DECISION_PERMISSION_KEYS,
    APPROVAL_REQUEST_PERMISSIONS,
    approval_permission_for_request_type,
    approval_to_read,
)
from app.services.lead_lifecycle import lock_organization_lead, require_lead_open_for_work

SPEED_TO_LEAD_TASK_TYPE = "speed_to_lead"
OPEN_TASK_STATUSES = ("open", "in_progress")
TERMINAL_LEAD_STAGES = {"dead", "disqualified", "closed"}
TERMINAL_DEAL_STAGES = {"funded", "closed", "cancelled", "dead"}
TEAM_PERMISSION_KEYS = {
    PermissionKeys.MANAGE_ACQUISITION_OPERATIONS,
    PermissionKeys.VIEW_AUDIT_LOGS,
    PermissionKeys.MANAGE_USERS,
    PermissionKeys.EXPORT_BUYERS,
}


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
        supersede_open_primary_tasks(db, lead_id=lead.id, excluding_task_id=existing.id)
        existing.work_kind = "primary_next_action"
        existing.responsible_user_id = lead.assigned_user_id
        return existing

    supersede_open_primary_tasks(db, lead_id=lead.id)
    due_at = datetime.now(UTC) + timedelta(minutes=get_settings().speed_to_lead_due_minutes)
    task = Task(
        organization_id=lead.organization_id,
        lead_id=lead.id,
        deal_id=None,
        responsible_user_id=lead.assigned_user_id,
        task_type=SPEED_TO_LEAD_TASK_TYPE,
        work_kind="primary_next_action",
        title=f"Contact {contact.legal_name}",
        status="open",
        priority="urgent",
        due_at=due_at,
        completed_at=None,
    )
    lead.next_follow_up_at = due_at
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


def create_initial_lead_next_action(
    db: Session,
    lead: Lead,
    *,
    actor_user_id: UUID | None,
    title: str = "Review seller lead and set the next action",
) -> Task:
    supersede_open_primary_tasks(db, lead_id=lead.id)
    due_at = lead.next_follow_up_at or (
        datetime.now(UTC) + timedelta(minutes=get_settings().speed_to_lead_due_minutes)
    )
    task = Task(
        organization_id=lead.organization_id,
        lead_id=lead.id,
        deal_id=None,
        responsible_user_id=lead.assigned_user_id or actor_user_id,
        task_type="primary_next_action",
        work_kind="primary_next_action",
        title=title,
        status="open",
        priority="high",
        due_at=due_at,
        completed_at=None,
    )
    lead.next_follow_up_at = due_at
    db.add(task)
    return task


def create_deal_next_action(
    db: Session,
    *,
    deal: Deal,
    lead: Lead,
    responsible_user_id: UUID | None,
    title: str,
    due_at: datetime | None,
) -> Task:
    supersede_open_primary_tasks(db, lead_id=lead.id)
    supersede_open_primary_tasks(db, deal_id=deal.id)
    next_due_at = due_at or datetime.now(UTC)
    task = Task(
        organization_id=deal.organization_id,
        lead_id=lead.id,
        deal_id=deal.id,
        responsible_user_id=responsible_user_id or lead.assigned_user_id,
        task_type="deal_next_action",
        work_kind="primary_next_action",
        title=title,
        status="open",
        priority="high",
        due_at=next_due_at,
        completed_at=None,
    )
    lead.next_follow_up_at = next_due_at
    db.add(task)
    return task


def supersede_open_primary_tasks(
    db: Session,
    *,
    lead_id: UUID | None = None,
    deal_id: UUID | None = None,
    excluding_task_id: UUID | None = None,
) -> None:
    if lead_id is None and deal_id is None:
        return
    filters = [
        Task.work_kind == "primary_next_action",
        Task.status.in_(OPEN_TASK_STATUSES),
    ]
    filters.append(Task.deal_id == deal_id if deal_id is not None else Task.lead_id == lead_id)
    if excluding_task_id is not None:
        filters.append(Task.id != excluding_task_id)
    now = datetime.now(UTC)
    changed = False
    for task in db.scalars(select(Task).where(*filters)).all():
        task.status = "cancelled"
        task.completed_at = now
        task.outcome = "superseded"
        changed = True
    if changed:
        db.flush()


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
    limit: int = 100,
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
        Lead.archived_at.is_(None),
    ]
    if task_type is not None:
        filters.append(Task.task_type == task_type)
    if (
        PermissionKeys.VIEW_LEADS not in principal.permission_keys
        and PermissionKeys.EDIT_LEADS not in principal.permission_keys
    ):
        filters.append(
            or_(
                Task.responsible_user_id == principal.user_id,
                Lead.assigned_user_id == principal.user_id,
            )
        )
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


def task_queue_item_read(row: Any, now: datetime) -> TaskQueueItemRead:
    task, lead, contact, property_record, user = row
    return TaskQueueItemRead(
        task_id=task.id,
        lead_id=lead.id,
        deal_id=task.deal_id,
        task_type=task.task_type,
        work_kind=task.work_kind,
        title=task.title,
        seller_name=contact.legal_name,
        property_address=format_property_address(property_record),
        source=lead.source,
        stage_key=lead.stage_key,
        priority=task.priority,
        status=task.status,
        due_at=task.due_at,
        created_at=task.created_at,
        completed_at=task.completed_at,
        assigned_user_id=task.responsible_user_id,
        assigned_user_email=user.email if user else None,
        due_status=get_due_status(task, now),
    )


def list_task_workspace(db: Session, principal: Principal) -> TaskWorkspaceRead:
    now = datetime.now(UTC)
    can_manage_team = bool(TEAM_PERMISSION_KEYS & principal.permission_keys)
    task_rows = db.execute(
        select(Task, Lead, Contact, Property, Deal, User)
        .outerjoin(Lead, Lead.id == Task.lead_id)
        .outerjoin(Contact, Contact.id == Lead.contact_id)
        .outerjoin(Property, Property.id == Lead.property_id)
        .outerjoin(Deal, Deal.id == Task.deal_id)
        .outerjoin(User, User.id == Task.responsible_user_id)
        .where(
            Task.organization_id == principal.organization_id,
            Task.status.in_(("open", "in_progress", "completed")),
        )
        .order_by(
            Task.status == "completed",
            Task.due_at.is_(None),
            Task.due_at.asc(),
            Task.created_at.desc(),
        )
        .limit(400)
    ).all()
    items = [
        task_workspace_item(row, principal, now)
        for row in task_rows
        if task_visible_to_principal(
            row[0],
            row[1],
            principal,
            can_manage_team=can_manage_team,
        )
    ]
    has_broad_approval_access = PermissionKeys.VIEW_AUDIT_LOGS in principal.permission_keys
    has_type_scoped_approval_access = bool(
        APPROVAL_DECISION_PERMISSION_KEYS & principal.permission_keys
    )
    can_review_call_notes = (
        PermissionKeys.ACCESS_RECORDINGS in principal.permission_keys
        and PermissionKeys.EDIT_LEADS in principal.permission_keys
    )
    allowed_approval_request_types = [
        request_type
        for request_type, permission in APPROVAL_REQUEST_PERMISSIONS.items()
        if permission in principal.permission_keys
    ]
    if can_review_call_notes:
        allowed_approval_request_types.append("call_notes_review")
    can_access_approvals = (
        has_broad_approval_access
        or has_type_scoped_approval_access
        or can_review_call_notes
    )
    if can_access_approvals:
        approval_query = (
            select(ApprovalRequest, User)
            .outerjoin(User, User.id == ApprovalRequest.assigned_to_user_id)
            .where(ApprovalRequest.organization_id == principal.organization_id)
        )
        if not has_broad_approval_access:
            approval_query = approval_query.where(
                ApprovalRequest.request_type.in_(allowed_approval_request_types)
            )
        approval_rows = db.execute(
            approval_query
            .order_by(
                ApprovalRequest.status != "pending",
                ApprovalRequest.due_at.is_(None),
                ApprovalRequest.due_at.asc(),
                ApprovalRequest.created_at.desc(),
            )
            .limit(150)
        ).all()
        items.extend(
            approval_workspace_item(request, assigned_user, principal, now)
            for request, assigned_user in approval_rows
            if approval_visible_to_principal(
                db,
                request,
                principal,
                can_manage_team=can_manage_team,
                has_broad_access=has_broad_approval_access,
            )
        )
    items.extend(
        list_ai_workspace_items(
            db,
            principal,
            now=now,
            can_manage_team=can_manage_team,
        )
    )
    items.sort(key=workspace_sort_key)
    return TaskWorkspaceRead(
        items=items,
        can_manage_team=can_manage_team,
        can_decide_approvals=can_access_approvals,
        current_user_id=principal.user_id,
        current_user_email=principal.email,
    )


def task_visible_to_principal(
    task: Task,
    lead: Lead | None,
    principal: Principal,
    *,
    can_manage_team: bool,
) -> bool:
    permissions = principal.permission_keys
    if task.responsible_user_id == principal.user_id:
        return True
    if lead is not None and lead.assigned_user_id == principal.user_id:
        return True
    if can_manage_team and (
        PermissionKeys.VIEW_LEADS in permissions or PermissionKeys.EDIT_LEADS in permissions
    ):
        return True
    return bool(
        can_manage_team
        and task.deal_id is not None
        and (
            PermissionKeys.VIEW_DEALS in permissions
            or PermissionKeys.EDIT_DEALS in permissions
            or PermissionKeys.VIEW_FINANCIALS in permissions
        )
    )


def task_workspace_item(row: Any, principal: Principal, now: datetime) -> TaskWorkspaceItemRead:
    task, lead, contact, property_record, deal, assigned_user = row
    source_record_type = "deal" if deal is not None else "lead" if lead is not None else "task"
    source_record_id = deal.id if deal is not None else lead.id if lead is not None else task.id
    seller_name = contact.legal_name if contact is not None else "Operational work"
    source_label = f"Deal · {seller_name}" if deal is not None else seller_name
    detail = format_property_address(property_record) if property_record is not None else None
    source_url = (
        f"/os/deals?deal={deal.id}"
        if deal is not None
        else f"/os/leads/{lead.id}"
        if lead is not None
        else None
    )
    flags: list[str] = []
    if task.status in OPEN_TASK_STATUSES:
        if task.responsible_user_id is None:
            flags.append("unassigned")
        if task.due_at is None:
            flags.append("unscheduled")
        if get_due_status(task, now) == "overdue":
            flags.append("overdue")
    if task.work_kind == "operational_exception":
        flags.append("operational_exception")
    return TaskWorkspaceItemRead(
        id=f"task:{task.id}",
        item_type="task",
        work_kind=normalized_work_kind(task.work_kind),
        source_record_type=source_record_type,
        source_record_id=source_record_id,
        source_record_label=source_label,
        source_record_detail=detail,
        source_url=source_url,
        task_id=task.id,
        task_type=task.task_type,
        title=task.title,
        summary=None,
        status=task.status,
        priority=task.priority,
        due_at=task.due_at,
        due_status=workspace_due_status(task.status, task.due_at, now),
        created_at=task.created_at,
        completed_at=task.completed_at,
        assigned_user_id=task.responsible_user_id,
        assigned_user_name=assigned_user.display_name if assigned_user else None,
        assigned_user_email=assigned_user.email if assigned_user else None,
        outcome=task.outcome,
        completion_notes=task.completion_notes,
        attention_flags=flags,
        can_complete=can_complete_task(task, principal),
    )


def approval_workspace_item(
    request: ApprovalRequest,
    assigned_user: User | None,
    principal: Principal,
    now: datetime,
) -> TaskWorkspaceItemRead:
    approval = approval_to_read(request)
    metadata = request.approval_metadata or {}
    source_label = str(
        metadata.get("seller_name")
        or metadata.get("property_address")
        or f"{request.entity_type.replace('_', ' ').title()} review"
    )
    flags = []
    if request.status == "pending" and request.assigned_to_user_id is None:
        flags.append("unassigned")
    if request.status == "pending" and request.due_at is None:
        flags.append("unscheduled")
    if request.status == "pending" and request.due_at and as_utc(request.due_at) < now:
        flags.append("overdue")
    is_ai_review = request.request_type == "call_notes_review"
    return TaskWorkspaceItemRead(
        id=f"approval:{request.id}",
        item_type="approval",
        work_kind="ai_review" if is_ai_review else "approval",
        source_record_type=request.entity_type,
        source_record_id=request.entity_id,
        source_record_label=source_label,
        source_record_detail=str(metadata.get("property_address") or request.summary),
        source_url=approval.review_url,
        approval_id=request.id,
        task_type=request.request_type,
        title=request.title,
        summary=request.summary,
        status=request.status,
        priority="high",
        due_at=request.due_at,
        due_status=workspace_due_status(
            "completed" if request.status != "pending" else "open",
            request.due_at,
            now,
        ),
        created_at=request.created_at,
        completed_at=request.decided_at,
        assigned_user_id=request.assigned_to_user_id,
        assigned_user_name=assigned_user.display_name if assigned_user else None,
        assigned_user_email=assigned_user.email if assigned_user else None,
        outcome=request.status if request.status != "pending" else None,
        completion_notes=request.decision_notes,
        attention_flags=flags,
        can_decide=can_decide_approval(request, principal),
        review_url=approval.review_url,
        approval_metadata=approval.approval_metadata,
    )


def approval_visible_to_principal(
    db: Session,
    request: ApprovalRequest,
    principal: Principal,
    *,
    can_manage_team: bool,
    has_broad_access: bool,
) -> bool:
    if request.request_type != "call_notes_review":
        required_permission = approval_permission_for_request_type(request.request_type)
        return has_broad_access or (
            required_permission is not None
            and required_permission in principal.permission_keys
        )
    if (
        PermissionKeys.ACCESS_RECORDINGS not in principal.permission_keys
        or PermissionKeys.EDIT_LEADS not in principal.permission_keys
    ):
        return False
    if request.assigned_to_user_id == principal.user_id:
        return True
    lead_id = parsed_uuid((request.approval_metadata or {}).get("lead_id"))
    lead = db.get(Lead, lead_id) if lead_id else None
    if lead is not None and lead.assigned_user_id == principal.user_id:
        return True
    return can_manage_team


def list_ai_workspace_items(
    db: Session,
    principal: Principal,
    *,
    now: datetime,
    can_manage_team: bool,
) -> list[TaskWorkspaceItemRead]:
    events = list(
        db.scalars(
            select(AiOrchestratorEvent)
            .where(
                AiOrchestratorEvent.organization_id == principal.organization_id,
                AiOrchestratorEvent.event_type.in_(("lead.created", "call.notes.ready")),
                AiOrchestratorEvent.status.in_(
                    (
                        "queued",
                        "processing",
                        "needs_review",
                        "completed",
                        "failed",
                        "blocked",
                    )
                ),
            )
            .order_by(AiOrchestratorEvent.created_at.desc())
            .limit(150)
        ).all()
    )
    if not events:
        return []
    event_ids = [event.id for event in events]
    runs_by_event: dict[UUID, AiRunLog] = {}
    for candidate_run in db.scalars(
        select(AiRunLog)
        .where(AiRunLog.orchestrator_event_id.in_(event_ids))
        .order_by(AiRunLog.created_at.desc())
    ).all():
        if candidate_run.orchestrator_event_id is not None:
            runs_by_event.setdefault(candidate_run.orchestrator_event_id, candidate_run)

    items: list[TaskWorkspaceItemRead] = []
    for event in events:
        payload = event.payload or {}
        if (
            event.event_type == "call.notes.ready"
            and event.status == "needs_review"
            and payload.get("approval_request_id")
        ):
            continue
        lead = db.get(Lead, event.entity_id) if event.entity_type == "lead" else None
        if lead is None or lead.archived_at is not None:
            continue
        assigned_user_id = parsed_uuid(payload.get("assigned_user_id"))
        if not ai_event_visible_to_principal(
            principal,
            lead,
            assigned_user_id=assigned_user_id,
            can_manage_team=can_manage_team,
        ):
            continue
        contact = db.get(Contact, lead.contact_id)
        property_record = db.get(Property, lead.property_id)
        assigned_user = db.get(User, assigned_user_id) if assigned_user_id else None
        run = runs_by_event.get(event.id)
        output = parse_ai_run_output(run.output_summary if run else None)
        due_at = parsed_datetime(payload.get("due_at"))
        work_kind = ai_work_kind(event.status)
        event_is_complete = work_kind == "ai_completed"
        summary = output.get("summary") or payload.get("summary")
        flags: list[str] = []
        if event.status in {"failed", "blocked"}:
            flags.extend(("operational_exception", f"ai_{event.status}"))
        elif assigned_user_id is None:
            flags.append("unassigned")
        source_label = contact.legal_name if contact else "Seller lead"
        detail = format_property_address(property_record) if property_record else None
        can_review = (
            event.status == "needs_review"
            and event.event_type == "lead.created"
            and PermissionKeys.EDIT_LEADS in principal.permission_keys
            and (
                assigned_user_id == principal.user_id
                or lead.assigned_user_id == principal.user_id
                or can_manage_team
            )
        )
        items.append(
            TaskWorkspaceItemRead(
                id=f"ai:{event.id}",
                item_type="ai_work",
                work_kind=work_kind,
                source_record_type="lead",
                source_record_id=lead.id,
                source_record_label=source_label,
                source_record_detail=detail,
                source_url=str(payload.get("source_url") or f"/os/leads/{lead.id}"),
                ai_event_id=event.id,
                ai_run_id=run.id if run else None,
                capability_key=str(payload.get("capability_key") or "") or None,
                ai_output=output,
                task_type=str(payload.get("capability_key") or event.event_type),
                title=str(payload.get("title") or "AI operations work"),
                summary=str(summary) if summary else event.last_error,
                status=event.status,
                priority=str(payload.get("priority") or "normal"),
                due_at=due_at,
                due_status=(
                    "completed" if event_is_complete else workspace_due_status("open", due_at, now)
                ),
                created_at=event.created_at,
                completed_at=event.processed_at if event_is_complete else None,
                assigned_user_id=assigned_user_id,
                assigned_user_name=assigned_user.display_name if assigned_user else None,
                assigned_user_email=assigned_user.email if assigned_user else None,
                outcome=str(payload.get("review_outcome"))
                if payload.get("review_outcome")
                else None,
                completion_notes=str(payload.get("review_notes"))
                if payload.get("review_notes")
                else None,
                attention_flags=flags,
                can_decide=can_review,
                approval_metadata={},
            )
        )
    return items


def ai_event_visible_to_principal(
    principal: Principal,
    lead: Lead,
    *,
    assigned_user_id: UUID | None,
    can_manage_team: bool,
) -> bool:
    return (
        assigned_user_id == principal.user_id
        or lead.assigned_user_id == principal.user_id
        or can_manage_team
    )


def ai_work_kind(status: str) -> TaskWorkKind:
    if status == "needs_review":
        return "ai_review"
    if status == "completed":
        return "ai_completed"
    if status in {"failed", "blocked"}:
        return "operational_exception"
    return "ai_in_progress"


def parse_ai_run_output(raw_output: str | None) -> dict[str, object]:
    if not raw_output:
        return {}
    try:
        output = json.loads(raw_output)
    except json.JSONDecodeError:
        return {"summary": raw_output}
    return output if isinstance(output, dict) else {"summary": raw_output}


def parsed_uuid(value: object) -> UUID | None:
    if not isinstance(value, str):
        return None
    try:
        return UUID(value)
    except ValueError:
        return None


def parsed_datetime(value: object) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def can_decide_approval(request: ApprovalRequest, principal: Principal) -> bool:
    if request.status != "pending" or request.request_type == "call_notes_review":
        return False
    required_permission = approval_permission_for_request_type(request.request_type)
    return bool(required_permission and required_permission in principal.permission_keys)


def can_complete_task(task: Task, principal: Principal) -> bool:
    if task.status not in OPEN_TASK_STATUSES:
        return False
    permissions = principal.permission_keys
    if task.deal_id is not None:
        return (
            PermissionKeys.EDIT_DEALS in permissions
            or PermissionKeys.MANAGE_ACQUISITION_OPERATIONS in permissions
        )
    return PermissionKeys.EDIT_LEADS in permissions or task.responsible_user_id == principal.user_id


def create_primary_next_action(
    db: Session,
    principal: Principal,
    payload: PrimaryNextActionCreate,
) -> TaskRead:
    responsible_user_id = payload.responsible_user_id or principal.user_id
    responsible_user = db.scalar(
        select(User).where(
            User.organization_id == principal.organization_id,
            User.id == responsible_user_id,
            User.is_active.is_(True),
        )
    )
    if responsible_user is None:
        raise ValueError("Select an active Stonegate team member.")

    lead: Lead | None = None
    deal: Deal | None = None
    if payload.source_record_type == "lead":
        if PermissionKeys.EDIT_LEADS not in principal.permission_keys:
            raise PermissionError("Your role cannot change seller next actions.")
        lead = db.scalar(
            select(Lead)
            .where(
                Lead.organization_id == principal.organization_id,
                Lead.id == payload.source_record_id,
            )
            .execution_options(populate_existing=True)
            .with_for_update()
        )
        if lead is None:
            raise ValueError("Seller lead not found.")
        require_lead_open_for_work(lead)
        supersede_open_primary_tasks(db, lead_id=lead.id)
    else:
        if (
            PermissionKeys.EDIT_DEALS not in principal.permission_keys
            and PermissionKeys.MANAGE_ACQUISITION_OPERATIONS not in principal.permission_keys
        ):
            raise PermissionError("Your role cannot change deal next actions.")
        deal_identity = db.execute(
            select(Deal.id, Deal.lead_id).where(
                Deal.organization_id == principal.organization_id,
                Deal.id == payload.source_record_id,
            )
        ).one_or_none()
        if deal_identity is None:
            raise ValueError("Deal not found.")
        lead = lock_organization_lead(
            db,
            organization_id=principal.organization_id,
            lead_id=deal_identity.lead_id,
        )
        if lead is None:
            raise ValueError("The deal's seller lead is unavailable.")
        require_lead_open_for_work(lead)
        deal = db.scalar(
            select(Deal).where(
                Deal.organization_id == principal.organization_id,
                Deal.id == payload.source_record_id,
            ).with_for_update()
        )
        if deal is None:
            raise ValueError("Deal not found.")
        supersede_open_primary_tasks(db, deal_id=deal.id)

    task = Task(
        organization_id=principal.organization_id,
        lead_id=lead.id if lead else None,
        deal_id=deal.id if deal else None,
        responsible_user_id=responsible_user.id,
        task_type=payload.action_type,
        work_kind="primary_next_action",
        title=payload.title,
        status="open",
        priority=payload.priority,
        due_at=payload.due_at,
        completed_at=None,
    )
    db.add(task)
    db.flush()
    sync_lead_next_action(db, lead, task)
    db.add(
        AuditEvent(
            organization_id=principal.organization_id,
            actor_user_id=principal.user_id,
            actor_type="user",
            action="task.primary_next_action_set",
            entity_type=payload.source_record_type,
            entity_id=payload.source_record_id,
            previous_value=None,
            new_value={
                "task_id": str(task.id),
                "title": task.title,
                "due_at": task.due_at.isoformat() if task.due_at else None,
                "responsible_user_id": str(task.responsible_user_id),
            },
            reason=payload.reason,
        )
    )
    db.commit()
    db.refresh(task)
    return task_to_read(task)


def complete_task(
    db: Session,
    principal: Principal,
    task_id: UUID,
    *,
    payload: TaskCompleteRequest,
) -> TaskRead | None:
    task_identity = db.execute(
        select(Task.lead_id, Task.deal_id).where(
            Task.organization_id == principal.organization_id,
            Task.id == task_id,
        )
    ).one_or_none()
    if task_identity is None:
        return None
    lead_id = task_identity.lead_id
    if lead_id is None and task_identity.deal_id is not None:
        lead_id = db.scalar(
            select(Deal.lead_id).where(
                Deal.organization_id == principal.organization_id,
                Deal.id == task_identity.deal_id,
            )
        )
    lead = (
        lock_organization_lead(
            db,
            organization_id=principal.organization_id,
            lead_id=lead_id,
        )
        if lead_id is not None
        else None
    )
    if lead is not None:
        require_lead_open_for_work(lead)
    task = db.scalar(
        select(Task)
        .where(
            Task.organization_id == principal.organization_id,
            Task.id == task_id,
        )
        .execution_options(populate_existing=True)
        .with_for_update()
    )
    if task is None:
        return None
    if task.status not in OPEN_TASK_STATUSES:
        raise ValueError("Only an open or in-progress task can be completed.")
    if not can_complete_task(task, principal):
        raise PermissionError("Your role cannot complete this task.")

    deal = db.get(Deal, task.deal_id) if task.deal_id else None
    successor: Task | None = None
    successor_owner: User | None = None
    if task.work_kind == "primary_next_action":
        if not payload.outcome or not payload.outcome.strip():
            raise ValueError("Primary next actions require an outcome.")
        if source_is_active(lead, deal) and payload.successor is None:
            raise ValueError(
                "This record is still active. Set its next action before completing "
                "the current one."
            )
        if payload.successor is not None:
            responsible_user_id = (
                payload.successor.responsible_user_id
                or task.responsible_user_id
                or principal.user_id
            )
            successor_owner = db.scalar(
                select(User).where(
                    User.organization_id == principal.organization_id,
                    User.id == responsible_user_id,
                    User.is_active.is_(True),
                )
            )
            if successor_owner is None:
                raise ValueError("Select an active owner for the successor action.")

    previous_status = task.status
    task.status = "completed"
    task.completed_at = datetime.now(UTC)
    task.completed_by_user_id = principal.user_id
    task.outcome = payload.outcome or "completed"
    task.completion_notes = payload.completion_notes or payload.reason
    db.flush()

    if task.work_kind == "primary_next_action":
        if payload.successor is not None and successor_owner is not None:
            successor = Task(
                organization_id=principal.organization_id,
                lead_id=task.lead_id,
                deal_id=task.deal_id,
                responsible_user_id=successor_owner.id,
                task_type=payload.successor.task_type,
                work_kind="primary_next_action",
                title=payload.successor.title,
                status="open",
                priority=payload.successor.priority,
                due_at=payload.successor.due_at,
                completed_at=None,
            )
            db.add(successor)
            db.flush()
            task.successor_task_id = successor.id
            sync_lead_next_action(db, lead, successor)
        else:
            sync_lead_next_action(db, lead, None)

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
            new_value={
                "status": task.status,
                "completed_at": task.completed_at.isoformat(),
                "outcome": task.outcome,
                "successor_task_id": str(successor.id) if successor else None,
            },
            reason=payload.reason or payload.completion_notes,
        )
    )
    db.commit()
    db.refresh(task)
    return task_to_read(task)


def sync_lead_next_action(db: Session, lead: Lead | None, task: Task | None) -> None:
    if lead is None:
        return
    lead.next_follow_up_at = task.due_at if task else None
    case = db.scalar(
        select(LeadManagementCase).where(
            LeadManagementCase.organization_id == lead.organization_id,
            LeadManagementCase.lead_id == lead.id,
        )
    )
    if case is not None:
        case.next_action_type = task.task_type if task else None
        case.next_action_due_at = task.due_at if task else None


def get_primary_next_action(
    db: Session,
    *,
    organization_id: UUID,
    lead_id: UUID | None = None,
    deal_id: UUID | None = None,
) -> PrimaryNextActionRead | None:
    filters = [
        Task.organization_id == organization_id,
        Task.work_kind == "primary_next_action",
        Task.status.in_(OPEN_TASK_STATUSES),
    ]
    if deal_id is not None:
        filters.append(Task.deal_id == deal_id)
    elif lead_id is not None:
        filters.append(Task.lead_id == lead_id)
    else:
        return None
    task = db.scalar(select(Task).where(*filters).order_by(Task.created_at.desc()).limit(1))
    if task is None:
        return None
    user = db.get(User, task.responsible_user_id) if task.responsible_user_id else None
    return PrimaryNextActionRead(
        task_id=task.id,
        title=task.title,
        action_type=task.task_type,
        due_at=task.due_at,
        responsible_user_id=task.responsible_user_id,
        responsible_user_email=user.email if user else None,
        due_status=get_due_status(task, datetime.now(UTC)),
    )


def source_is_active(lead: Lead | None, deal: Deal | None) -> bool:
    if deal is not None:
        return deal.stage_key not in TERMINAL_DEAL_STAGES
    if lead is not None:
        return lead.archived_at is None and lead.stage_key not in TERMINAL_LEAD_STAGES
    return False


def get_due_status(task: Task, now: datetime) -> str:
    if task.due_at is None:
        return "unscheduled"
    due_at = as_utc(task.due_at)
    if due_at <= now:
        return "overdue"
    return "due"


def workspace_due_status(
    status: str,
    due_at: datetime | None,
    now: datetime,
) -> TaskDueStatus:
    if status not in OPEN_TASK_STATUSES:
        return "completed"
    if due_at is None:
        return "unscheduled"
    normalized = as_utc(due_at)
    if normalized < now:
        return "overdue"
    if normalized.date() == now.date():
        return "today"
    return "upcoming"


def workspace_sort_key(item: TaskWorkspaceItemRead) -> tuple[int, datetime, datetime]:
    status_order = {
        "overdue": 0,
        "today": 1,
        "upcoming": 2,
        "unscheduled": 3,
        "completed": 4,
    }
    due_at = as_utc(item.due_at) if item.due_at else datetime.max.replace(tzinfo=UTC)
    return status_order[item.due_status], due_at, as_utc(item.created_at)


def normalized_work_kind(value: str) -> TaskWorkKind:
    if value == "primary_next_action":
        return "primary_next_action"
    if value == "operational_exception":
        return "operational_exception"
    return "supporting"


def task_to_read(task: Task) -> TaskRead:
    return TaskRead(
        id=task.id,
        lead_id=task.lead_id,
        deal_id=task.deal_id,
        task_type=task.task_type,
        work_kind=task.work_kind,
        title=task.title,
        status=task.status,
        priority=task.priority,
        due_at=task.due_at,
        completed_at=task.completed_at,
        completed_by_user_id=task.completed_by_user_id,
        outcome=task.outcome,
        completion_notes=task.completion_notes,
        successor_task_id=task.successor_task_id,
    )


def format_property_address(property_record: Property) -> str:
    return property_identity_label(
        street_address=property_record.street_address,
        city=property_record.city,
        state=property_record.state,
        postal_code=property_record.postal_code,
        parcel_id=property_record.parcel_id,
        county=property_record.county,
    )


def as_utc(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=UTC)
