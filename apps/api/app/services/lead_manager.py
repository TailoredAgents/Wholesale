from collections import defaultdict
from collections.abc import Mapping
from datetime import UTC, datetime, time, timedelta
from uuid import UUID

from sqlalchemy import distinct, func, select
from sqlalchemy.orm import Session

from app.core.auth import Principal
from app.core.config import Settings
from app.domain.rbac import PermissionKeys
from app.models.foundation import (
    Appointment,
    AuditEvent,
    Contact,
    ConversationAssignmentEvent,
    Lead,
    LeadManagementCase,
    LeadQualificationScriptVersion,
    LeadQualificationSession,
    Permission,
    Property,
    Role,
    RoleAssignment,
    RolePermission,
    Task,
    Transaction,
    User,
)
from app.schemas.lead_manager import (
    LeadManagerCaseRead,
    LeadManagerMetrics,
    LeadManagerOverview,
    LeadManagerScorecard,
    QualificationCompleteRequest,
    QualificationQuestion,
    QualificationScriptCreate,
    QualificationScriptRead,
    QualificationSessionRead,
)
from app.schemas.prospecting import ProspectHandoffDecision
from app.services.acquisition_operations import (
    create_notification,
    upsert_internal_calendar_event,
)
from app.services.inbox import add_automatic_owner_watchers, ensure_primary_conversation

DEFAULT_COMPLETION_RULES = {
    "require_all_required_questions": True,
    "require_dated_next_action": True,
}
LEAD_FIELD_MAP = {
    "motivation": "motivation",
    "timeline": "desired_timeline",
    "property_condition": "property_condition",
    "occupancy": "occupancy_status",
    "asking_price": "asking_price",
    "mortgage_balance": "mortgage_balance",
}
TERMINAL_STAGES = {"dead", "disqualified", "lost", "closed"}


def can_manage(principal: Principal) -> bool:
    return PermissionKeys.MANAGE_ACQUISITION_OPERATIONS in principal.permission_keys


def create_case_for_handoff(
    db: Session,
    *,
    organization_id: UUID,
    lead_id: UUID,
    handoff_id: UUID,
    assigned_user_id: UUID,
    submitted_at: datetime,
    sla_minutes: int,
) -> LeadManagementCase:
    existing = db.scalar(select(LeadManagementCase).where(LeadManagementCase.lead_id == lead_id))
    if existing is not None:
        existing.handoff_id = handoff_id
        existing.assigned_user_id = assigned_user_id
        existing.status = "awaiting_acceptance"
        existing.acceptance_due_at = submitted_at + timedelta(minutes=sla_minutes)
        existing.accepted_at = None
        existing.accepted_by_user_id = None
        existing.escalated_at = None
        return existing
    case = LeadManagementCase(
        organization_id=organization_id,
        lead_id=lead_id,
        handoff_id=handoff_id,
        assigned_user_id=assigned_user_id,
        status="awaiting_acceptance",
        acceptance_due_at=submitted_at + timedelta(minutes=sla_minutes),
        accepted_at=None,
        accepted_by_user_id=None,
        escalated_at=None,
        qualification_script_version_id=None,
        qualification_started_at=None,
        qualification_completed_at=None,
        qualification_quality_basis_points=None,
        next_action_type=None,
        next_action_due_at=None,
        last_contact_at=None,
        closed_at=None,
    )
    db.add(case)
    db.flush()
    return case


def ensure_inbound_case(
    db: Session,
    *,
    organization_id: UUID,
    lead: Lead,
    submitted_at: datetime,
    sla_minutes: int,
) -> LeadManagementCase | None:
    existing = db.scalar(select(LeadManagementCase).where(LeadManagementCase.lead_id == lead.id))
    if existing is not None:
        return existing
    assignee = select_inbound_assignee(db, organization_id)
    if assignee is None:
        return None
    lead.assigned_user_id = assignee.id
    contact = db.get(Contact, lead.contact_id)
    if contact is not None:
        contact.assigned_user_id = assignee.id
    conversation = ensure_primary_conversation(db, lead, queue_key="qualified")
    previous_assigned_user_id = conversation.assigned_user_id
    previous_queue_key = conversation.queue_key
    conversation.assigned_user_id = assignee.id
    conversation.queue_key = "qualified"
    db.add(
        ConversationAssignmentEvent(
            organization_id=organization_id,
            conversation_id=conversation.id,
            lead_id=lead.id,
            actor_user_id=None,
            previous_assigned_user_id=previous_assigned_user_id,
            assigned_user_id=assignee.id,
            previous_queue_key=previous_queue_key,
            queue_key="qualified",
            reason="Website inquiry routed to the Lead Manager queue.",
        )
    )
    add_automatic_owner_watchers(db, conversation)
    case = LeadManagementCase(
        organization_id=organization_id,
        lead_id=lead.id,
        handoff_id=None,
        assigned_user_id=assignee.id,
        status="awaiting_acceptance",
        acceptance_due_at=submitted_at + timedelta(minutes=sla_minutes),
        accepted_at=None,
        accepted_by_user_id=None,
        escalated_at=None,
        qualification_script_version_id=None,
        qualification_started_at=None,
        qualification_completed_at=None,
        qualification_quality_basis_points=None,
        next_action_type=None,
        next_action_due_at=None,
        last_contact_at=None,
        closed_at=None,
    )
    db.add(case)
    db.flush()
    create_notification(
        db,
        organization_id=organization_id,
        recipient_user_id=assignee.id,
        notification_type="lead_manager_inbound",
        title="New website lead awaiting acceptance",
        body="A seller submitted property information and needs immediate follow-up.",
        entity_type="lead_management_case",
        entity_id=case.id,
        action_url="/os/lead-manager",
        dedupe_key=f"lead-manager-inbound:{case.id}",
    )
    return case


def sync_case_handoff_decision(
    db: Session,
    *,
    handoff_id: UUID,
    decision: str,
    reviewer_user_id: UUID,
    reviewed_at: datetime,
) -> None:
    case = db.scalar(select(LeadManagementCase).where(LeadManagementCase.handoff_id == handoff_id))
    if case is None:
        return
    if decision == "accepted":
        case.status = "active"
        case.accepted_at = reviewed_at
        case.accepted_by_user_id = reviewer_user_id
        case.qualification_started_at = case.qualification_started_at or reviewed_at
    else:
        case.status = "correction_requested"
        case.accepted_at = None
        case.accepted_by_user_id = None


def get_overview(db: Session, principal: Principal) -> LeadManagerOverview:
    now = datetime.now(UTC)
    user = db.get(User, principal.user_id)
    if user is None:
        raise ValueError("Workspace user is unavailable.")
    manageable = can_manage(principal)
    statement = select(LeadManagementCase).where(
        LeadManagementCase.organization_id == principal.organization_id
    )
    if not manageable:
        statement = statement.where(LeadManagementCase.assigned_user_id == principal.user_id)
    cases = list(db.scalars(statement.order_by(LeadManagementCase.acceptance_due_at)).all())
    case_reads = [case_read(db, case, now) for case in cases]
    case_by_lead = {item.lead_id: item for item in case_reads}
    today_start = datetime.combine(now.date(), time.min, tzinfo=UTC)
    tomorrow_start = today_start + timedelta(days=1)
    appointment_lead_ids = set(
        db.scalars(
            select(Appointment.lead_id).where(
                Appointment.organization_id == principal.organization_id,
                Appointment.scheduled_start_at >= today_start,
                Appointment.scheduled_start_at < tomorrow_start,
                Appointment.status.in_(("scheduled", "rescheduled")),
            )
        ).all()
    )
    appointments_today = [
        case_by_lead[lead_id] for lead_id in appointment_lead_ids if lead_id in case_by_lead
    ]
    awaiting = [item for item in case_reads if item.status in {"awaiting_acceptance", "overdue"}]
    qualification = [
        item
        for item in case_reads
        if item.accepted_at is not None
        and item.qualification_completed_at is None
        and item.status not in {"closed", "correction_requested"}
    ]
    follow_up = [
        item
        for item in case_reads
        if item.qualification_completed_at is not None
        and item.next_action_due_at is not None
        and as_utc(item.next_action_due_at) <= now
        and item.status != "closed"
    ]
    neglected = [
        item
        for item in case_reads
        if item.accepted_at is not None
        and item.qualification_completed_at is not None
        and item.status != "closed"
        and (
            item.next_action_due_at is None
            or as_utc(item.next_action_due_at) <= now - timedelta(hours=24)
        )
    ]
    scripts = list_scripts(db, principal) if manageable else []
    active_script = get_active_script(db, principal.organization_id)
    return LeadManagerOverview(
        current_user_id=user.id,
        current_user_name=user.display_name,
        can_manage=manageable,
        metrics=LeadManagerMetrics(
            awaiting_acceptance=len(awaiting),
            overdue_acceptance=sum(item.is_acceptance_overdue for item in awaiting),
            qualification_due=len(qualification),
            follow_up_due=len(follow_up),
            appointments_today=len(appointments_today),
            neglected_leads=len(neglected),
        ),
        active_script=script_read(active_script) if active_script else None,
        scripts=scripts,
        awaiting_acceptance=awaiting,
        qualification_queue=qualification,
        follow_up_queue=follow_up,
        appointments_today=appointments_today,
        neglected_queue=neglected,
        scorecards=build_scorecards(db, principal, cases, now),
    )


def create_script(
    db: Session, principal: Principal, payload: QualificationScriptCreate
) -> QualificationScriptRead:
    next_version = int(
        db.scalar(
            select(func.max(LeadQualificationScriptVersion.version_number)).where(
                LeadQualificationScriptVersion.organization_id == principal.organization_id
            )
        )
        or 0
    ) + 1
    script = LeadQualificationScriptVersion(
        organization_id=principal.organization_id,
        version_number=next_version,
        title=payload.title.strip(),
        status="draft",
        introduction=payload.introduction.strip(),
        questions=[question.model_dump() for question in payload.questions],
        completion_rules=DEFAULT_COMPLETION_RULES,
        created_by_user_id=principal.user_id,
        approved_by_user_id=None,
        approved_at=None,
    )
    db.add(script)
    db.flush()
    audit(
        db,
        principal,
        "lead_manager.qualification_script_created",
        "lead_qualification_script",
        script.id,
        None,
        {"version_number": next_version, "status": "draft"},
        "Versioned Lead Manager qualification script created",
    )
    db.commit()
    return script_read(script)


def approve_script(
    db: Session, principal: Principal, script_id: UUID
) -> QualificationScriptRead | None:
    script = scoped_script(db, principal.organization_id, script_id)
    if script is None:
        return None
    if script.status != "draft":
        raise ValueError("Only draft qualification scripts can be approved.")
    now = datetime.now(UTC)
    for approved in db.scalars(
        select(LeadQualificationScriptVersion).where(
            LeadQualificationScriptVersion.organization_id == principal.organization_id,
            LeadQualificationScriptVersion.status == "approved",
        )
    ):
        approved.status = "retired"
    script.status = "approved"
    script.approved_by_user_id = principal.user_id
    script.approved_at = now
    audit(
        db,
        principal,
        "lead_manager.qualification_script_approved",
        "lead_qualification_script",
        script.id,
        {"status": "draft"},
        {"status": "approved", "version_number": script.version_number},
        "Lead Manager qualification script approved",
    )
    db.commit()
    return script_read(script)


def accept_case(
    db: Session, principal: Principal, case_id: UUID, reason: str | None
) -> LeadManagerCaseRead | None:
    case = scoped_case(db, principal, case_id)
    if case is None:
        return None
    ensure_case_access(principal, case)
    if case.status not in {"awaiting_acceptance", "overdue"}:
        raise ValueError("This warm lead has already been accepted or returned.")
    if case.handoff_id is not None:
        from app.services.prospecting import decide_handoff

        handoff = decide_handoff(
            db,
            principal,
            case.handoff_id,
            ProspectHandoffDecision(decision="accepted", reason=reason),
        )
        if handoff is None:
            raise ValueError("The warm handoff could not be found.")
        db.refresh(case)
    else:
        now = datetime.now(UTC)
        previous = {"status": case.status}
        case.status = "active"
        case.accepted_at = now
        case.accepted_by_user_id = principal.user_id
        case.qualification_started_at = now
        lead = db.get(Lead, case.lead_id)
        if lead is not None:
            lead.stage_key = "qualification_in_progress"
        audit(
            db,
            principal,
            "lead_manager.inbound_accepted",
            "lead_management_case",
            case.id,
            previous,
            {"status": "active", "reason": reason},
            "Lead Manager accepted an inbound seller inquiry",
        )
        db.commit()
    return case_read(db, case, datetime.now(UTC))


def complete_qualification(
    db: Session,
    principal: Principal,
    case_id: UUID,
    payload: QualificationCompleteRequest,
) -> QualificationSessionRead | None:
    case = scoped_case(db, principal, case_id)
    if case is None:
        return None
    ensure_case_access(principal, case)
    if case.accepted_at is None:
        raise ValueError("Accept the warm handoff before completing qualification.")
    if case.status == "closed":
        raise ValueError("A closed Lead Manager case cannot be qualified again.")
    script = get_active_script(db, principal.organization_id)
    if script is None:
        raise ValueError("Approve a Lead Manager qualification script first.")
    answers = clean_answers(payload.answers)
    missing = [
        str(question["key"])
        for question in script.questions
        if bool(question.get("required", True))
        and not has_answer(answers.get(str(question["key"])))
    ]
    if missing:
        raise ValueError(f"Answer the required qualification questions: {', '.join(missing)}.")
    now = datetime.now(UTC)
    if payload.next_action_due_at and as_utc(payload.next_action_due_at) <= now:
        raise ValueError("The next action must be scheduled in the future.")
    question_by_key = {str(question["key"]): question for question in script.questions}
    unknown_keys = sorted(set(answers) - set(question_by_key))
    if unknown_keys:
        raise ValueError(f"Unknown qualification answers: {', '.join(unknown_keys)}.")
    for key, answer in answers.items():
        question = question_by_key[key]
        if question.get("answer_type") == "choice" and answer not in question.get("choices", []):
            raise ValueError(f"Select an approved answer for {key}.")
    answered_count = sum(has_answer(answers.get(key)) for key in question_by_key)
    quality = round(answered_count / len(script.questions) * 10000) if script.questions else 0
    lead = db.get(Lead, case.lead_id)
    if lead is None:
        raise ValueError("The Lead Manager case points to a missing lead.")
    for answer_key, lead_field in LEAD_FIELD_MAP.items():
        value = answers.get(answer_key)
        if has_answer(value):
            setattr(lead, lead_field, str(value))
    apply_next_action(db, case, lead, payload, now)
    session = LeadQualificationSession(
        organization_id=principal.organization_id,
        case_id=case.id,
        lead_id=lead.id,
        script_version_id=script.id,
        completed_by_user_id=principal.user_id,
        status="completed",
        answers=answers,
        missing_required_keys=[],
        quality_score_basis_points=quality,
        next_action_type=payload.next_action_type,
        next_action_due_at=payload.next_action_due_at,
        completed_at=now,
    )
    db.add(session)
    case.qualification_script_version_id = script.id
    case.qualification_started_at = case.qualification_started_at or now
    case.qualification_completed_at = now
    case.qualification_quality_basis_points = quality
    case.next_action_type = payload.next_action_type
    case.next_action_due_at = payload.next_action_due_at
    audit(
        db,
        principal,
        "lead_manager.qualification_completed",
        "lead_management_case",
        case.id,
        None,
        {
            "script_version": script.version_number,
            "quality_basis_points": quality,
            "next_action_type": payload.next_action_type,
            "next_action_due_at": (
                payload.next_action_due_at.isoformat() if payload.next_action_due_at else None
            ),
        },
        "Guided seller qualification completed with a dated next action",
    )
    db.commit()
    return session_read(session, script.version_number)


def process_next_escalation(db: Session, _settings: Settings) -> UUID | None:
    now = datetime.now(UTC)
    case = db.scalar(
        select(LeadManagementCase)
        .where(
            LeadManagementCase.status == "awaiting_acceptance",
            LeadManagementCase.acceptance_due_at <= now,
            LeadManagementCase.escalated_at.is_(None),
        )
        .order_by(LeadManagementCase.acceptance_due_at)
        .limit(1)
    )
    if case is None:
        return None
    case.status = "overdue"
    case.escalated_at = now
    recipients = manager_user_ids(db, case.organization_id) | {case.assigned_user_id}
    for user_id in recipients:
        create_notification(
            db,
            organization_id=case.organization_id,
            recipient_user_id=user_id,
            notification_type="lead_manager_handoff_overdue",
            title="Warm lead acceptance overdue",
            body="A qualified seller handoff exceeded the Lead Manager response SLA.",
            entity_type="lead_management_case",
            entity_id=case.id,
            action_url="/os/lead-manager",
            dedupe_key=f"lead-manager-overdue:{case.id}:{user_id}",
        )
    db.add(
        AuditEvent(
            organization_id=case.organization_id,
            actor_user_id=None,
            actor_type="system",
            action="lead_manager.handoff_escalated",
            entity_type="lead_management_case",
            entity_id=case.id,
            previous_value={"status": "awaiting_acceptance"},
            new_value={"status": "overdue", "escalated_at": now.isoformat()},
            reason="Warm handoff acceptance SLA exceeded",
        )
    )
    db.commit()
    return case.id


def apply_next_action(
    db: Session,
    case: LeadManagementCase,
    lead: Lead,
    payload: QualificationCompleteRequest,
    now: datetime,
) -> None:
    if payload.next_action_type == "disqualify":
        case.status = "closed"
        case.closed_at = now
        lead.stage_key = "disqualified"
        lead.next_follow_up_at = None
        return
    assert payload.next_action_due_at is not None
    lead.next_follow_up_at = payload.next_action_due_at
    case.status = "nurture" if payload.next_action_type == "nurture" else "active"
    title = f"Lead Manager {payload.next_action_type} follow-up"
    task = db.scalar(
        select(Task).where(
            Task.organization_id == case.organization_id,
            Task.lead_id == lead.id,
            Task.task_type == "lead_manager_next_action",
            Task.status == "open",
        )
    )
    if task is None:
        task = Task(
            organization_id=case.organization_id,
            lead_id=lead.id,
            responsible_user_id=case.assigned_user_id,
            task_type="lead_manager_next_action",
            title=title,
            status="open",
            priority="high" if payload.next_action_type == "appointment" else "normal",
            due_at=payload.next_action_due_at,
            completed_at=None,
        )
        db.add(task)
    else:
        task.responsible_user_id = case.assigned_user_id
        task.title = title
        task.due_at = payload.next_action_due_at
    if payload.next_action_type == "appointment":
        appointment = db.scalar(
            select(Appointment)
            .where(
                Appointment.organization_id == case.organization_id,
                Appointment.lead_id == lead.id,
                Appointment.status.in_(("scheduled", "rescheduled")),
            )
            .order_by(Appointment.scheduled_start_at)
        )
        if appointment is None:
            appointment = Appointment(
                organization_id=case.organization_id,
                lead_id=lead.id,
                contact_id=lead.contact_id,
                property_id=lead.property_id,
                owner_user_id=case.assigned_user_id,
                appointment_type="seller_appointment",
                status="scheduled",
                scheduled_start_at=payload.next_action_due_at,
                scheduled_end_at=payload.next_action_due_at + timedelta(hours=1),
                location_type="seller_property",
                location=None,
                notes="Scheduled from guided Lead Manager qualification.",
                outcome=None,
                external_calendar_id=None,
                appointment_metadata={"source": "lead_manager_qualification"},
            )
            db.add(appointment)
        else:
            appointment.owner_user_id = case.assigned_user_id
            appointment.scheduled_start_at = payload.next_action_due_at
            appointment.scheduled_end_at = payload.next_action_due_at + timedelta(hours=1)
        db.flush()
        upsert_internal_calendar_event(db, appointment)
        case.status = "appointment_set"
        lead.stage_key = "appointment_scheduled"
        lead.appointment_status = "scheduled"
    elif payload.next_action_type == "nurture":
        lead.stage_key = "long_term_follow_up"
    else:
        lead.stage_key = "qualified"


def build_scorecards(
    db: Session,
    principal: Principal,
    visible_cases: list[LeadManagementCase],
    now: datetime,
) -> list[LeadManagerScorecard]:
    since = now - timedelta(days=30)
    cases = [case for case in visible_cases if as_utc(case.created_at) >= since]
    grouped: dict[UUID, list[LeadManagementCase]] = defaultdict(list)
    for case in cases:
        grouped[case.assigned_user_id].append(case)
    users = {
        user.id: user
        for user in db.scalars(
            select(User).where(
                User.organization_id == principal.organization_id,
                User.id.in_(grouped.keys()),
            )
        )
    }
    result: list[LeadManagerScorecard] = []
    for user_id, user_cases in grouped.items():
        lead_ids = [case.lead_id for case in user_cases]
        accepted = [case for case in user_cases if case.accepted_at is not None]
        acceptance_minutes = [
            max(0, round((as_utc(case.accepted_at) - as_utc(case.created_at)).total_seconds() / 60))
            for case in accepted
            if case.accepted_at is not None
        ]
        appointments = list(
            db.scalars(
                select(Appointment).where(
                    Appointment.organization_id == principal.organization_id,
                    Appointment.lead_id.in_(lead_ids),
                    Appointment.created_at >= since,
                )
            ).all()
        ) if lead_ids else []
        contracts = int(
            db.scalar(
                select(func.count()).select_from(Transaction).where(
                    Transaction.organization_id == principal.organization_id,
                    Transaction.lead_id.in_(lead_ids),
                    Transaction.created_at >= since,
                )
            )
            or 0
        ) if lead_ids else 0
        active = [
            case
            for case in user_cases
            if case.status != "closed" and case.qualification_completed_at is not None
        ]
        protected = [
            case
            for case in active
            if case.next_action_due_at is not None and as_utc(case.next_action_due_at) > now
        ]
        result.append(
            LeadManagerScorecard(
                user_id=user_id,
                user_name=users[user_id].display_name if user_id in users else "Inactive user",
                handoffs_received=len(user_cases),
                handoffs_accepted=len(accepted),
                accepted_within_sla=sum(
                    1
                    for case in accepted
                    if case.accepted_at is not None
                    and as_utc(case.accepted_at) <= as_utc(case.acceptance_due_at)
                ),
                average_acceptance_minutes=(
                    round(sum(acceptance_minutes) / len(acceptance_minutes))
                    if acceptance_minutes
                    else None
                ),
                qualifications_completed=sum(
                    case.qualification_completed_at is not None for case in user_cases
                ),
                appointments_set=len(appointments),
                appointments_held=sum(item.status == "completed" for item in appointments),
                appointment_no_shows=sum(item.status == "no_show" for item in appointments),
                contracts_created=contracts,
                follow_up_quality_basis_points=(
                    round(len(protected) / len(active) * 10000) if active else 10000
                ),
            )
        )
    return sorted(result, key=lambda item: item.user_name.lower())


def case_read(db: Session, case: LeadManagementCase, now: datetime) -> LeadManagerCaseRead:
    lead = db.get(Lead, case.lead_id)
    if lead is None:
        raise ValueError("Lead Manager case points to a missing lead.")
    contact = db.get(Contact, lead.contact_id)
    property_record = db.get(Property, lead.property_id)
    user = db.get(User, case.assigned_user_id)
    if contact is None or property_record is None or user is None:
        raise ValueError("Lead Manager case has incomplete seller ownership data.")
    created_at = as_utc(case.created_at)
    accepted_at = as_utc(case.accepted_at) if case.accepted_at else None
    acceptance_minutes = (
        max(0, round((accepted_at - created_at).total_seconds() / 60)) if accepted_at else None
    )
    due = as_utc(case.acceptance_due_at)
    next_due = as_utc(case.next_action_due_at) if case.next_action_due_at else None
    return LeadManagerCaseRead(
        id=case.id,
        lead_id=lead.id,
        handoff_id=case.handoff_id,
        seller_name=contact.preferred_name or contact.legal_name,
        property_address=(
            f"{property_record.street_address}, {property_record.city}, "
            f"{property_record.state} {property_record.postal_code}"
        ),
        source=lead.source,
        stage_key=lead.stage_key,
        assigned_user_id=case.assigned_user_id,
        assigned_user_name=user.display_name,
        status=case.status,
        acceptance_due_at=case.acceptance_due_at,
        accepted_at=case.accepted_at,
        escalated_at=case.escalated_at,
        acceptance_minutes=acceptance_minutes,
        is_acceptance_overdue=case.accepted_at is None and due <= now,
        qualification_completed_at=case.qualification_completed_at,
        qualification_quality_basis_points=case.qualification_quality_basis_points,
        next_action_type=case.next_action_type,
        next_action_due_at=case.next_action_due_at,
        is_next_action_overdue=next_due is not None and next_due <= now and case.status != "closed",
        age_hours=max(0, round((now - created_at).total_seconds() / 3600)),
        lead_url=f"/os/leads/{lead.id}",
    )


def list_scripts(db: Session, principal: Principal) -> list[QualificationScriptRead]:
    return [
        script_read(script)
        for script in db.scalars(
            select(LeadQualificationScriptVersion)
            .where(LeadQualificationScriptVersion.organization_id == principal.organization_id)
            .order_by(LeadQualificationScriptVersion.version_number.desc())
        )
    ]


def get_active_script(
    db: Session, organization_id: UUID
) -> LeadQualificationScriptVersion | None:
    return db.scalar(
        select(LeadQualificationScriptVersion).where(
            LeadQualificationScriptVersion.organization_id == organization_id,
            LeadQualificationScriptVersion.status == "approved",
        )
    )


def script_read(script: LeadQualificationScriptVersion) -> QualificationScriptRead:
    return QualificationScriptRead(
        id=script.id,
        version_number=script.version_number,
        title=script.title,
        status=script.status,
        introduction=script.introduction,
        questions=[QualificationQuestion.model_validate(question) for question in script.questions],
        approved_at=script.approved_at,
        created_at=script.created_at,
    )


def session_read(
    session: LeadQualificationSession, version_number: int
) -> QualificationSessionRead:
    return QualificationSessionRead(
        id=session.id,
        case_id=session.case_id,
        lead_id=session.lead_id,
        script_version_id=session.script_version_id,
        script_version_number=version_number,
        answers=session.answers,
        missing_required_keys=session.missing_required_keys,
        quality_score_basis_points=session.quality_score_basis_points,
        next_action_type=session.next_action_type,
        next_action_due_at=session.next_action_due_at,
        completed_at=session.completed_at,
    )


def scoped_case(
    db: Session, principal: Principal, case_id: UUID
) -> LeadManagementCase | None:
    return db.scalar(
        select(LeadManagementCase).where(
            LeadManagementCase.organization_id == principal.organization_id,
            LeadManagementCase.id == case_id,
        )
    )


def scoped_script(
    db: Session, organization_id: UUID, script_id: UUID
) -> LeadQualificationScriptVersion | None:
    return db.scalar(
        select(LeadQualificationScriptVersion).where(
            LeadQualificationScriptVersion.organization_id == organization_id,
            LeadQualificationScriptVersion.id == script_id,
        )
    )


def ensure_case_access(principal: Principal, case: LeadManagementCase) -> None:
    if not can_manage(principal) and case.assigned_user_id != principal.user_id:
        raise PermissionError("This warm lead is assigned to another Lead Manager.")


def manager_user_ids(db: Session, organization_id: UUID) -> set[UUID]:
    return set(
        db.scalars(
            select(distinct(RoleAssignment.user_id))
            .join(RolePermission, RolePermission.role_id == RoleAssignment.role_id)
            .join(Permission, Permission.id == RolePermission.permission_id)
            .join(User, User.id == RoleAssignment.user_id)
            .where(
                RoleAssignment.organization_id == organization_id,
                Permission.key == PermissionKeys.MANAGE_ACQUISITION_OPERATIONS,
                User.is_active.is_(True),
            )
        ).all()
    )


def select_inbound_assignee(db: Session, organization_id: UUID) -> User | None:
    candidates = db.execute(
        select(User, Role.key)
        .join(RoleAssignment, RoleAssignment.user_id == User.id)
        .join(Role, Role.id == RoleAssignment.role_id)
        .where(
            User.organization_id == organization_id,
            User.is_active.is_(True),
            Role.key.in_(
                (
                    "acquisition_manager",
                    "acquisition_rep",
                    "owner",
                    "founder_operator",
                    "administrator",
                )
            ),
        )
    ).all()
    if not candidates:
        return None
    counts: dict[UUID, int] = {
        user_id: int(case_count)
        for user_id, case_count in db.execute(
            select(LeadManagementCase.assigned_user_id, func.count())
            .where(
                LeadManagementCase.organization_id == organization_id,
                LeadManagementCase.status != "closed",
            )
            .group_by(LeadManagementCase.assigned_user_id)
        ).all()
    }
    role_priority = {
        "acquisition_manager": 0,
        "acquisition_rep": 1,
        "owner": 2,
        "founder_operator": 2,
        "administrator": 3,
    }
    users: dict[UUID, tuple[User, int]] = {}
    for user, role_key in candidates:
        priority = role_priority[role_key]
        current = users.get(user.id)
        if current is None or priority < current[1]:
            users[user.id] = (user, priority)
    return min(
        users.values(),
        key=lambda item: (item[1], int(counts.get(item[0].id, 0)), item[0].display_name.lower()),
    )[0]


def clean_answers(answers: Mapping[str, str | bool]) -> dict[str, str | bool]:
    return {
        key: value.strip() if isinstance(value, str) else value
        for key, value in answers.items()
        if has_answer(value)
    }


def has_answer(value: object) -> bool:
    return value is not None and (not isinstance(value, str) or bool(value.strip()))


def as_utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def audit(
    db: Session,
    principal: Principal,
    action: str,
    entity_type: str,
    entity_id: UUID,
    previous: Mapping[str, object] | None,
    new: Mapping[str, object],
    reason: str,
) -> None:
    db.add(
        AuditEvent(
            organization_id=principal.organization_id,
            actor_user_id=principal.user_id,
            actor_type="user",
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            previous_value=dict(previous) if previous is not None else None,
            new_value=dict(new),
            reason=reason,
        )
    )
