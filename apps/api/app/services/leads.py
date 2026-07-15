from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.auth import Principal
from app.models.foundation import (
    ActivityEvent,
    AttributionTouch,
    AuditEvent,
    CommunicationRecord,
    ConsentRecord,
    Contact,
    ContactMethod,
    ConversionEvent,
    Deal,
    Lead,
    Property,
    Task,
    User,
)
from app.schemas.leads import (
    ActivityEventRead,
    AttributionTouchRead,
    CommunicationRecordRead,
    ConsentRecordRead,
    ContactMethodRead,
    DashboardSummary,
    LeadAiReadySummary,
    LeadCommunicationCreate,
    LeadCreate,
    LeadDetail,
    LeadFollowUpTaskCreate,
    LeadIntelligence,
    LeadMissingField,
    LeadNextBestAction,
    LeadNoteCreate,
    LeadRead,
    LeadStaffUpdate,
    LeadStageUpdate,
    LeadTaskRead,
    PipelineStageCount,
    SourcePerformance,
)

PAID_LEAD_SOURCES = ("google_ppc", "meta_ads", "facebook_ads", "instagram_ads", "website")
COMMUNICATION_DIRECTIONS = {"inbound", "outbound", "internal"}
COMMUNICATION_CHANNELS = {"call", "sms", "email", "voicemail", "note"}
COMMUNICATION_STATUSES = {"logged", "draft", "sent", "received", "failed", "blocked"}
HIGH_URGENCY_TIMELINES = {"asap", "now", "immediately", "30_days", "30 days", "within 30 days"}
MEDIUM_URGENCY_TIMELINES = {"60_90_days", "60-90 days", "90_days", "90 days"}
QUALIFICATION_FIELDS = [
    (
        "motivation",
        "Motivation",
        "Why is the seller considering a sale now?",
        "high",
    ),
    (
        "desired_timeline",
        "Timeline",
        "When does the seller want to close or decide?",
        "high",
    ),
    (
        "property_condition",
        "Property condition",
        "What repairs, updates, or condition issues should underwriting know?",
        "medium",
    ),
    (
        "occupancy_status",
        "Occupancy",
        "Is the property vacant, owner occupied, or tenant occupied?",
        "medium",
    ),
    (
        "asking_price",
        "Asking price",
        "What price or net number is the seller hoping for?",
        "medium",
    ),
    (
        "mortgage_balance",
        "Mortgage balance",
        "Is there a mortgage, lien, or payoff amount to consider?",
        "medium",
    ),
    (
        "appointment_status",
        "Appointment status",
        "Has an appointment or walkthrough been requested or scheduled?",
        "high",
    ),
]
SELLER_PIPELINE_STAGES = {
    "new",
    "contact_attempt_due",
    "attempting_contact",
    "contacted",
    "qualification_in_progress",
    "qualified",
    "appointment_scheduled",
    "underwriting",
    "offer_pending_approval",
    "offer_ready",
    "offer_presented",
    "negotiating",
    "long_term_follow_up",
    "under_contract",
    "disqualified",
    "dead",
    "reopened",
}


def create_lead(db: Session, principal: Principal, payload: LeadCreate) -> LeadRead:
    contact = Contact(
        organization_id=principal.organization_id,
        legal_name=payload.contact.legal_name,
        preferred_name=payload.contact.preferred_name,
        contact_type=payload.contact.contact_type,
        assigned_user_id=principal.user_id,
    )
    db.add(contact)
    db.flush()

    property_record = Property(
        organization_id=principal.organization_id,
        street_address=payload.property.street_address,
        city=payload.property.city,
        state=payload.property.state.upper(),
        postal_code=payload.property.postal_code,
        county=payload.property.county,
        property_type=payload.property.property_type,
    )
    db.add(property_record)
    db.flush()

    lead = Lead(
        organization_id=principal.organization_id,
        contact_id=contact.id,
        property_id=property_record.id,
        assigned_user_id=principal.user_id,
        source=payload.source,
        stage_key=payload.stage_key,
        lead_temperature=payload.lead_temperature,
        motivation=payload.motivation,
        desired_timeline=payload.desired_timeline,
        property_condition=payload.property_condition,
        occupancy_status=payload.occupancy_status,
        asking_price=payload.asking_price,
        mortgage_balance=payload.mortgage_balance,
        appointment_status=payload.appointment_status,
        next_follow_up_at=payload.next_follow_up_at,
    )
    db.add(lead)
    db.flush()

    db.add(
        ActivityEvent(
            organization_id=principal.organization_id,
            actor_user_id=principal.user_id,
            entity_type="lead",
            entity_id=lead.id,
            event_type="lead.created",
            summary=f"Lead created for {contact.legal_name}.",
        )
    )
    db.add(
        AuditEvent(
            organization_id=principal.organization_id,
            actor_user_id=principal.user_id,
            actor_type="user",
            action="lead.create",
            entity_type="lead",
            entity_id=lead.id,
            previous_value=None,
            new_value={"source": lead.source, "stage_key": lead.stage_key},
            reason="Manual local lead creation",
        )
    )
    db.commit()
    db.refresh(lead)
    return lead_to_read(db, lead)


def list_leads(db: Session, principal: Principal, limit: int = 25) -> list[LeadRead]:
    leads = db.scalars(
        select(Lead)
        .where(Lead.organization_id == principal.organization_id)
        .order_by(Lead.created_at.desc())
        .limit(limit)
    ).all()
    return [lead_to_read(db, lead) for lead in leads]


def get_lead_detail(db: Session, principal: Principal, lead_id: UUID) -> LeadDetail | None:
    lead = get_scoped_lead(db, principal, lead_id)
    if lead is None:
        return None
    base = lead_to_read(db, lead)
    contact_methods = db.scalars(
        select(ContactMethod)
        .where(
            ContactMethod.organization_id == principal.organization_id,
            ContactMethod.contact_id == lead.contact_id,
        )
        .order_by(ContactMethod.created_at.asc())
    ).all()
    consent_records = db.scalars(
        select(ConsentRecord)
        .where(
            ConsentRecord.organization_id == principal.organization_id,
            ConsentRecord.contact_id == lead.contact_id,
        )
        .order_by(ConsentRecord.created_at.desc())
    ).all()
    attribution_touches = db.scalars(
        select(AttributionTouch)
        .where(
            AttributionTouch.organization_id == principal.organization_id,
            AttributionTouch.lead_id == lead.id,
        )
        .order_by(AttributionTouch.created_at.desc())
    ).all()
    recent_activity = db.scalars(
        select(ActivityEvent)
        .where(
            ActivityEvent.organization_id == principal.organization_id,
            ActivityEvent.entity_type == "lead",
            ActivityEvent.entity_id == lead.id,
        )
        .order_by(ActivityEvent.created_at.desc(), ActivityEvent.id.desc())
        .limit(20)
    ).all()
    open_tasks = db.scalars(
        select(Task)
        .where(
            Task.organization_id == principal.organization_id,
            Task.lead_id == lead.id,
            Task.status.in_(("open", "in_progress")),
        )
        .order_by(Task.due_at.is_(None), Task.due_at.asc(), Task.created_at.asc())
        .limit(20)
    ).all()
    communications = db.scalars(
        select(CommunicationRecord)
        .where(
            CommunicationRecord.organization_id == principal.organization_id,
            CommunicationRecord.lead_id == lead.id,
        )
        .order_by(CommunicationRecord.occurred_at.desc(), CommunicationRecord.created_at.desc())
        .limit(20)
    ).all()

    return LeadDetail(
        **base.model_dump(),
        contact_methods=[
            ContactMethodRead(
                method_type=method.method_type,
                value=method.value,
                is_primary=method.is_primary,
            )
            for method in contact_methods
        ],
        consent_records=[
            ConsentRecordRead(
                channel=record.channel,
                status=record.status,
                source=record.source,
                wording_version=record.wording_version,
                captured_ip=record.captured_ip,
                created_at=record.created_at,
            )
            for record in consent_records
        ],
        attribution_touches=[
            AttributionTouchRead(
                touch_type=touch.touch_type,
                source=touch.source,
                medium=touch.medium,
                campaign=touch.campaign,
                term=touch.term,
                content=touch.content,
                gclid=touch.gclid,
                fbclid=touch.fbclid,
                landing_page=touch.landing_page,
                referrer=touch.referrer,
                created_at=touch.created_at,
            )
            for touch in attribution_touches
        ],
        open_tasks=[
            LeadTaskRead(
                id=task.id,
                task_type=task.task_type,
                title=task.title,
                status=task.status,
                priority=task.priority,
                due_at=task.due_at,
                completed_at=task.completed_at,
            )
            for task in open_tasks
        ],
        communications=[
            CommunicationRecordRead(
                id=communication.id,
                direction=communication.direction,
                channel=communication.channel,
                status=communication.status,
                provider=communication.provider,
                provider_message_id=communication.provider_message_id,
                subject=communication.subject,
                body=communication.body,
                occurred_at=communication.occurred_at,
                created_at=communication.created_at,
            )
            for communication in communications
        ],
        recent_activity=[
            ActivityEventRead(
                event_type=activity.event_type,
                summary=activity.summary,
                created_at=activity.created_at,
            )
            for activity in recent_activity
        ],
        intelligence=build_lead_intelligence(
            lead=lead,
            contact_methods=list(contact_methods),
            open_tasks=list(open_tasks),
        ),
    )


def build_lead_intelligence(
    *,
    lead: Lead,
    contact_methods: list[ContactMethod],
    open_tasks: list[Task],
) -> LeadIntelligence:
    missing_fields = get_missing_fields(lead, contact_methods)
    quality_score = get_quality_score(missing_fields)
    urgency_score = get_urgency_score(lead, open_tasks)
    next_best_action = get_next_best_action(lead, missing_fields, open_tasks, quality_score)
    return LeadIntelligence(
        quality_score=quality_score,
        urgency_score=urgency_score,
        priority_label=get_priority_label(urgency_score),
        missing_fields=missing_fields,
        next_best_action=next_best_action,
        ai_ready_summary=get_ai_ready_summary(
            lead,
            missing_fields,
            next_best_action,
            urgency_score,
        ),
    )


def get_missing_fields(lead: Lead, contact_methods: list[ContactMethod]) -> list[LeadMissingField]:
    missing_fields: list[LeadMissingField] = []
    if not contact_methods:
        missing_fields.append(
            LeadMissingField(
                field_key="contact_method",
                label="Contact method",
                question="What is the best phone number or email for seller follow-up?",
                severity="high",
            )
        )
    for field_key, label, question, severity in QUALIFICATION_FIELDS:
        value = getattr(lead, field_key)
        if value is None or (isinstance(value, str) and not value.strip()):
            missing_fields.append(
                LeadMissingField(
                    field_key=field_key,
                    label=label,
                    question=question,
                    severity=severity,
                )
            )
    return missing_fields


def get_quality_score(missing_fields: list[LeadMissingField]) -> int:
    total_fields = len(QUALIFICATION_FIELDS) + 1
    high_penalty = sum(15 for field in missing_fields if field.severity == "high")
    medium_penalty = sum(10 for field in missing_fields if field.severity == "medium")
    raw_score = 100 - high_penalty - medium_penalty
    if len(missing_fields) == total_fields:
        return 0
    return max(0, min(100, raw_score))


def get_urgency_score(lead: Lead, open_tasks: list[Task]) -> int:
    score = 0
    if lead.lead_temperature == "hot":
        score += 30
    elif lead.lead_temperature == "warm":
        score += 18

    timeline = (lead.desired_timeline or "").strip().lower()
    if timeline in HIGH_URGENCY_TIMELINES or "asap" in timeline or "30" in timeline:
        score += 30
    elif timeline in MEDIUM_URGENCY_TIMELINES or "60" in timeline or "90" in timeline:
        score += 15

    now = datetime.now(UTC)
    for task in open_tasks:
        if task.due_at is None:
            continue
        due_at = task.due_at if task.due_at.tzinfo else task.due_at.replace(tzinfo=UTC)
        if due_at <= now:
            score += 25
            break

    if lead.stage_key in {"new", "contact_attempt_due", "attempting_contact"}:
        score += 12
    if lead.source in PAID_LEAD_SOURCES:
        score += 8
    if lead.next_follow_up_at is None and lead.stage_key not in {"dead", "disqualified"}:
        score += 8
    return max(0, min(100, score))


def get_priority_label(urgency_score: int) -> str:
    if urgency_score >= 80:
        return "critical"
    if urgency_score >= 60:
        return "high"
    if urgency_score >= 35:
        return "medium"
    return "routine"


def get_next_best_action(
    lead: Lead,
    missing_fields: list[LeadMissingField],
    open_tasks: list[Task],
    quality_score: int,
) -> LeadNextBestAction:
    overdue_task = get_first_overdue_task(open_tasks)
    if overdue_task is not None:
        return LeadNextBestAction(
            action_type="complete_overdue_task",
            label="Complete overdue follow-up",
            description=f"Work the overdue task: {overdue_task.title}.",
            priority="urgent",
        )

    high_missing_field = next(
        (field for field in missing_fields if field.severity == "high"),
        None,
    )
    if high_missing_field is not None:
        return LeadNextBestAction(
            action_type="ask_missing_question",
            label=f"Ask about {high_missing_field.label.lower()}",
            description=high_missing_field.question,
            priority="high",
        )

    if lead.appointment_status in {None, "", "not_scheduled", "appointment_requested"}:
        return LeadNextBestAction(
            action_type="schedule_appointment",
            label="Schedule seller appointment",
            description=(
                "Qualification is strong enough to move toward a walkthrough or seller call."
            ),
            priority="high" if quality_score >= 70 else "normal",
        )

    if lead.stage_key in {"qualified", "appointment_scheduled", "underwriting"}:
        return LeadNextBestAction(
            action_type="prepare_underwriting",
            label="Prepare underwriting review",
            description="Move known property facts into offer analysis and identify pricing gaps.",
            priority="normal",
        )

    return LeadNextBestAction(
        action_type="create_follow_up",
        label="Create next follow-up",
        description="Set the next dated task so the lead does not fall through the cracks.",
        priority="normal",
    )


def get_first_overdue_task(open_tasks: list[Task]) -> Task | None:
    now = datetime.now(UTC)
    for task in open_tasks:
        if task.due_at is None:
            continue
        due_at = task.due_at if task.due_at.tzinfo else task.due_at.replace(tzinfo=UTC)
        if due_at <= now:
            return task
    return None


def get_ai_ready_summary(
    lead: Lead,
    missing_fields: list[LeadMissingField],
    next_best_action: LeadNextBestAction,
    urgency_score: int,
) -> LeadAiReadySummary:
    known_facts = [
        f"Stage: {lead.stage_key}.",
        f"Source: {lead.source}.",
    ]
    optional_facts = [
        ("Temperature", lead.lead_temperature),
        ("Motivation", lead.motivation),
        ("Timeline", lead.desired_timeline),
        ("Condition", lead.property_condition),
        ("Occupancy", lead.occupancy_status),
        ("Asking price", lead.asking_price),
        ("Mortgage balance", lead.mortgage_balance),
        ("Appointment", lead.appointment_status),
    ]
    known_facts.extend(
        f"{label}: {value}." for label, value in optional_facts if value is not None and value != ""
    )
    if urgency_score >= 60:
        urgency = "High urgency lead."
    elif urgency_score >= 35:
        urgency = "Moderate urgency lead."
    else:
        urgency = "Routine urgency lead."
    situation = lead.motivation or "Seller motivation has not been captured yet."
    return LeadAiReadySummary(
        situation=situation,
        urgency=urgency,
        known_facts=known_facts,
        missing_questions=[field.question for field in missing_fields],
        recommended_next_action=next_best_action.label,
    )


def update_lead_stage(
    db: Session,
    principal: Principal,
    lead_id: UUID,
    payload: LeadStageUpdate,
) -> LeadDetail | None:
    if payload.stage_key not in SELLER_PIPELINE_STAGES:
        raise ValueError(f"Unsupported seller pipeline stage: {payload.stage_key}")

    lead = get_scoped_lead(db, principal, lead_id)
    if lead is None:
        return None
    previous_stage = lead.stage_key
    if previous_stage == payload.stage_key:
        return get_lead_detail(db, principal, lead_id)

    lead.stage_key = payload.stage_key
    db.add(
        ActivityEvent(
            organization_id=principal.organization_id,
            actor_user_id=principal.user_id,
            entity_type="lead",
            entity_id=lead.id,
            event_type="lead.stage_changed",
            summary=f"Lead stage changed from {previous_stage} to {payload.stage_key}.",
        )
    )
    db.add(
        AuditEvent(
            organization_id=principal.organization_id,
            actor_user_id=principal.user_id,
            actor_type="user",
            action="lead.stage_update",
            entity_type="lead",
            entity_id=lead.id,
            previous_value={"stage_key": previous_stage},
            new_value={"stage_key": payload.stage_key},
            reason=payload.reason,
        )
    )
    db.commit()
    db.refresh(lead)
    return get_lead_detail(db, principal, lead_id)


def add_lead_note(
    db: Session,
    principal: Principal,
    lead_id: UUID,
    payload: LeadNoteCreate,
) -> LeadDetail | None:
    lead = get_scoped_lead(db, principal, lead_id)
    if lead is None:
        return None

    db.add(
        ActivityEvent(
            organization_id=principal.organization_id,
            actor_user_id=principal.user_id,
            entity_type="lead",
            entity_id=lead.id,
            event_type="lead.note_added",
            summary=payload.note,
        )
    )
    db.add(
        AuditEvent(
            organization_id=principal.organization_id,
            actor_user_id=principal.user_id,
            actor_type="user",
            action="lead.note_create",
            entity_type="lead",
            entity_id=lead.id,
            previous_value=None,
            new_value={"note": payload.note},
            reason="Lead note added",
        )
    )
    db.commit()
    return get_lead_detail(db, principal, lead_id)


def create_lead_follow_up_task(
    db: Session,
    principal: Principal,
    lead_id: UUID,
    payload: LeadFollowUpTaskCreate,
) -> LeadDetail | None:
    lead = get_scoped_lead(db, principal, lead_id)
    if lead is None:
        return None

    task = Task(
        organization_id=principal.organization_id,
        lead_id=lead.id,
        responsible_user_id=lead.assigned_user_id or principal.user_id,
        task_type="follow_up",
        title=payload.title,
        status="open",
        priority=payload.priority,
        due_at=payload.due_at,
        completed_at=None,
    )
    db.add(task)
    if payload.due_at is not None:
        previous_follow_up = lead.next_follow_up_at
        lead.next_follow_up_at = payload.due_at
    else:
        previous_follow_up = None
    db.flush()
    db.add(
        ActivityEvent(
            organization_id=principal.organization_id,
            actor_user_id=principal.user_id,
            entity_type="lead",
            entity_id=lead.id,
            event_type="task.follow_up_created",
            summary=f"Follow-up task created: {task.title}.",
        )
    )
    db.add(
        AuditEvent(
            organization_id=principal.organization_id,
            actor_user_id=principal.user_id,
            actor_type="user",
            action="task.follow_up_create",
            entity_type="task",
            entity_id=task.id,
            previous_value={"next_follow_up_at": previous_follow_up.isoformat()}
            if previous_follow_up
            else None,
            new_value={
                "lead_id": str(lead.id),
                "title": task.title,
                "priority": task.priority,
                "due_at": task.due_at.isoformat() if task.due_at else None,
            },
            reason="Manual lead follow-up task",
        )
    )
    db.commit()
    return get_lead_detail(db, principal, lead_id)


def add_lead_communication(
    db: Session,
    principal: Principal,
    lead_id: UUID,
    payload: LeadCommunicationCreate,
) -> LeadDetail | None:
    if payload.direction not in COMMUNICATION_DIRECTIONS:
        raise ValueError(f"Unsupported communication direction: {payload.direction}")
    if payload.channel not in COMMUNICATION_CHANNELS:
        raise ValueError(f"Unsupported communication channel: {payload.channel}")
    if payload.status not in COMMUNICATION_STATUSES:
        raise ValueError(f"Unsupported communication status: {payload.status}")

    lead = get_scoped_lead(db, principal, lead_id)
    if lead is None:
        return None

    communication = CommunicationRecord(
        organization_id=principal.organization_id,
        lead_id=lead.id,
        contact_id=lead.contact_id,
        actor_user_id=principal.user_id,
        direction=payload.direction,
        channel=payload.channel,
        status=payload.status,
        provider="manual",
        provider_message_id=None,
        subject=payload.subject,
        body=payload.body,
        occurred_at=payload.occurred_at or datetime.now(UTC),
        external_payload=None,
        communication_metadata={
            "source": "manual_log",
            "automation_allowed": False,
        },
    )
    db.add(communication)
    db.flush()

    summary = (
        f"{payload.direction.title()} {payload.channel} {payload.status}: "
        f"{payload.body[:160]}"
    )
    db.add(
        ActivityEvent(
            organization_id=principal.organization_id,
            actor_user_id=principal.user_id,
            entity_type="lead",
            entity_id=lead.id,
            event_type="lead.communication_logged",
            summary=summary,
        )
    )
    db.add(
        AuditEvent(
            organization_id=principal.organization_id,
            actor_user_id=principal.user_id,
            actor_type="user",
            action="communication.log",
            entity_type="communication_record",
            entity_id=communication.id,
            previous_value=None,
            new_value={
                "lead_id": str(lead.id),
                "direction": communication.direction,
                "channel": communication.channel,
                "status": communication.status,
                "provider": communication.provider,
                "occurred_at": communication.occurred_at.isoformat(),
            },
            reason="Manual communication log",
        )
    )
    db.commit()
    return get_lead_detail(db, principal, lead_id)


def update_lead_staff_details(
    db: Session,
    principal: Principal,
    lead_id: UUID,
    payload: LeadStaffUpdate,
) -> LeadDetail | None:
    lead = get_scoped_lead(db, principal, lead_id)
    if lead is None:
        return None

    contact = db.get(Contact, lead.contact_id)
    property_record = db.get(Property, lead.property_id)
    if contact is None or property_record is None:
        raise RuntimeError("lead is missing required contact or property")

    previous_values: dict[str, Any] = {}
    new_values: dict[str, Any] = {}

    provided_fields = payload.model_fields_set

    update_value(previous_values, new_values, contact, "legal_name", payload.seller_name)
    update_nullable_value(
        previous_values,
        new_values,
        contact,
        "preferred_name",
        payload.preferred_name,
        provided_fields,
    )
    update_value(previous_values, new_values, lead, "source", payload.source)
    update_nullable_value(
        previous_values,
        new_values,
        lead,
        "lead_temperature",
        payload.lead_temperature,
        provided_fields,
    )
    update_nullable_value(
        previous_values,
        new_values,
        lead,
        "motivation",
        payload.motivation,
        provided_fields,
    )
    update_nullable_value(
        previous_values,
        new_values,
        lead,
        "desired_timeline",
        payload.desired_timeline,
        provided_fields,
    )
    update_nullable_value(
        previous_values,
        new_values,
        lead,
        "property_condition",
        payload.property_condition,
        provided_fields,
    )
    update_nullable_value(
        previous_values,
        new_values,
        lead,
        "occupancy_status",
        payload.occupancy_status,
        provided_fields,
    )
    update_nullable_value(
        previous_values,
        new_values,
        lead,
        "asking_price",
        payload.asking_price,
        provided_fields,
    )
    update_nullable_value(
        previous_values,
        new_values,
        lead,
        "mortgage_balance",
        payload.mortgage_balance,
        provided_fields,
    )
    update_nullable_value(
        previous_values,
        new_values,
        lead,
        "appointment_status",
        payload.appointment_status,
        provided_fields,
    )
    update_nullable_raw_value(
        previous_values,
        new_values,
        lead,
        "next_follow_up_at",
        payload.next_follow_up_at,
        provided_fields,
    )
    update_value(
        previous_values,
        new_values,
        property_record,
        "street_address",
        payload.property_street_address,
    )
    update_value(previous_values, new_values, property_record, "city", payload.property_city)
    if payload.property_state is not None:
        update_value(
            previous_values,
            new_values,
            property_record,
            "state",
            payload.property_state.upper(),
        )
    update_value(
        previous_values,
        new_values,
        property_record,
        "postal_code",
        payload.property_postal_code,
    )
    update_nullable_value(
        previous_values,
        new_values,
        property_record,
        "county",
        payload.property_county,
        provided_fields,
        provided_field_name="property_county",
    )
    update_nullable_value(
        previous_values,
        new_values,
        property_record,
        "property_type",
        payload.property_type,
        provided_fields,
    )

    phone_changed = update_contact_method(
        db,
        principal,
        contact,
        previous_values,
        new_values,
        method_type="phone",
        value=payload.phone,
    )
    email_changed = update_contact_method(
        db,
        principal,
        contact,
        previous_values,
        new_values,
        method_type="email",
        value=payload.email,
    )

    if property_fields_changed(previous_values) or property_fields_changed(new_values):
        property_record.normalized_address_key = normalize_address_key(
            property_record.street_address,
            property_record.city,
            property_record.state,
            property_record.postal_code,
        )

    if previous_values or new_values or phone_changed or email_changed:
        db.add(
            ActivityEvent(
                organization_id=principal.organization_id,
                actor_user_id=principal.user_id,
                entity_type="lead",
                entity_id=lead.id,
                event_type="lead.staff_updated",
                summary=f"Lead details updated for {contact.legal_name}.",
            )
        )
        db.add(
            AuditEvent(
                organization_id=principal.organization_id,
                actor_user_id=principal.user_id,
                actor_type="user",
                action="lead.staff_update",
                entity_type="lead",
                entity_id=lead.id,
                previous_value=previous_values,
                new_value=new_values,
                reason=payload.reason,
            )
        )
        db.commit()
        db.refresh(lead)

    return get_lead_detail(db, principal, lead_id)


def get_dashboard_summary(db: Session, principal: Principal) -> DashboardSummary:
    total_leads = count_scalar(db, select(func.count(Lead.id)).where(
        Lead.organization_id == principal.organization_id
    ))
    new_paid_leads = count_scalar(db, select(func.count(Lead.id)).where(
        Lead.organization_id == principal.organization_id,
        Lead.stage_key == "new",
        Lead.source.in_(PAID_LEAD_SOURCES),
    ))
    active_contracts = count_scalar(db, select(func.count(Deal.id)).where(
        Deal.organization_id == principal.organization_id,
        Deal.stage_key == "under_contract",
    ))
    collected_revenue_cents = int(
        db.scalar(
            select(func.coalesce(func.sum(Deal.assignment_fee_cents), 0)).where(
                Deal.organization_id == principal.organization_id,
                Deal.stage_key == "closed",
            )
        )
        or 0
    )
    pipeline_rows = db.execute(
        select(Lead.stage_key, func.count(Lead.id))
        .where(Lead.organization_id == principal.organization_id)
        .group_by(Lead.stage_key)
        .order_by(Lead.stage_key)
    ).all()

    return DashboardSummary(
        total_leads=total_leads,
        new_paid_leads=new_paid_leads,
        active_contracts=active_contracts,
        offers_pending=0,
        collected_revenue_cents=collected_revenue_cents,
        pipeline=[
            PipelineStageCount(stage_key=str(stage_key), count=int(count))
            for stage_key, count in pipeline_rows
        ],
        source_performance=get_source_performance(db, principal),
    )


def get_source_performance(db: Session, principal: Principal) -> list[SourcePerformance]:
    source_rows: dict[tuple[str, str, str], dict[str, int | str]] = {}
    event_rows = db.execute(
        select(
            ConversionEvent.source,
            ConversionEvent.medium,
            ConversionEvent.campaign,
            ConversionEvent.event_type,
            func.count(ConversionEvent.id),
        )
        .where(ConversionEvent.organization_id == principal.organization_id)
        .group_by(
            ConversionEvent.source,
            ConversionEvent.medium,
            ConversionEvent.campaign,
            ConversionEvent.event_type,
        )
    ).all()

    for source, medium, campaign, event_type, count in event_rows:
        row = ensure_source_performance_row(source_rows, source, medium, campaign)
        count_value = int(count)
        if event_type == "page_view":
            row["page_views"] = int(row["page_views"]) + count_value
        elif event_type == "form_start":
            row["form_starts"] = int(row["form_starts"]) + count_value
        elif event_type == "form_abandon":
            row["form_abandons"] = int(row["form_abandons"]) + count_value
        elif event_type == "form_submit":
            row["form_submits"] = int(row["form_submits"]) + count_value
        elif event_type == "call_click":
            row["call_clicks"] = int(row["call_clicks"]) + count_value

    lead_rows = db.execute(
        select(Lead.source, func.count(Lead.id))
        .where(Lead.organization_id == principal.organization_id)
        .group_by(Lead.source)
    ).all()
    for source, count in lead_rows:
        row = ensure_source_performance_row(source_rows, source, None, None)
        row["leads_created"] = int(row["leads_created"]) + int(count)

    return [
        SourcePerformance(
            source=str(row["source"]),
            medium=str(row["medium"]),
            campaign=str(row["campaign"]),
            page_views=int(row["page_views"]),
            form_starts=int(row["form_starts"]),
            form_abandons=int(row["form_abandons"]),
            form_submits=int(row["form_submits"]),
            call_clicks=int(row["call_clicks"]),
            leads_created=int(row["leads_created"]),
        )
        for row in sorted(
            source_rows.values(),
            key=lambda item: (
                -int(item["leads_created"]),
                -int(item["form_submits"]),
                -int(item["form_starts"]),
                -int(item["page_views"]),
                str(item["source"]),
            ),
        )
    ][:10]


def ensure_source_performance_row(
    source_rows: dict[tuple[str, str, str], dict[str, int | str]],
    source: str | None,
    medium: str | None,
    campaign: str | None,
) -> dict[str, int | str]:
    key = (
        source or "direct",
        medium or "unknown",
        campaign or "uncategorized",
    )
    if key not in source_rows:
        source_rows[key] = {
            "source": key[0],
            "medium": key[1],
            "campaign": key[2],
            "page_views": 0,
            "form_starts": 0,
            "form_abandons": 0,
            "form_submits": 0,
            "call_clicks": 0,
            "leads_created": 0,
        }
    return source_rows[key]


def count_scalar(db: Session, statement: Any) -> int:
    return int(db.scalar(statement) or 0)


def get_scoped_lead(db: Session, principal: Principal, lead_id: UUID) -> Lead | None:
    return db.scalar(
        select(Lead).where(
            Lead.organization_id == principal.organization_id,
            Lead.id == lead_id,
        )
    )


def update_value(
    previous_values: dict[str, Any],
    new_values: dict[str, Any],
    target: Any,
    field_name: str,
    value: str | None,
) -> None:
    if value is None:
        return
    cleaned_value = value.strip()
    if not cleaned_value:
        return
    current_value = getattr(target, field_name)
    if current_value == cleaned_value:
        return
    previous_values[field_name] = current_value
    new_values[field_name] = cleaned_value
    setattr(target, field_name, cleaned_value)


def update_nullable_value(
    previous_values: dict[str, Any],
    new_values: dict[str, Any],
    target: Any,
    field_name: str,
    value: str | None,
    provided_fields: set[str],
    *,
    provided_field_name: str | None = None,
) -> None:
    if (provided_field_name or field_name) not in provided_fields:
        return
    cleaned_value = normalize_blank(value) if value is not None else None
    current_value = getattr(target, field_name)
    if current_value == cleaned_value:
        return
    previous_values[field_name] = current_value
    new_values[field_name] = cleaned_value
    setattr(target, field_name, cleaned_value)


def update_nullable_raw_value(
    previous_values: dict[str, Any],
    new_values: dict[str, Any],
    target: Any,
    field_name: str,
    value: Any,
    provided_fields: set[str],
) -> None:
    if field_name not in provided_fields:
        return
    current_value = getattr(target, field_name)
    if current_value == value:
        return
    previous_values[field_name] = serialize_audit_value(current_value)
    new_values[field_name] = serialize_audit_value(value)
    setattr(target, field_name, value)


def serialize_audit_value(value: Any) -> Any:
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return value


def update_contact_method(
    db: Session,
    principal: Principal,
    contact: Contact,
    previous_values: dict[str, Any],
    new_values: dict[str, Any],
    *,
    method_type: str,
    value: str | None,
) -> bool:
    if value is None:
        return False

    cleaned_value = value.strip()
    if not cleaned_value:
        return False

    normalized_value = (
        normalize_email(cleaned_value)
        if method_type == "email"
        else normalize_phone(cleaned_value)
    )
    if not normalized_value:
        return False

    existing = db.scalar(
        select(ContactMethod)
        .where(
            ContactMethod.organization_id == principal.organization_id,
            ContactMethod.contact_id == contact.id,
            ContactMethod.method_type == method_type,
        )
        .order_by(ContactMethod.is_primary.desc(), ContactMethod.created_at.asc())
    )
    audit_key = f"{method_type}_contact_method"
    if existing is not None:
        if existing.value == cleaned_value and existing.normalized_value == normalized_value:
            return False
        previous_values[audit_key] = existing.value
        new_values[audit_key] = cleaned_value
        existing.value = cleaned_value
        existing.normalized_value = normalized_value
        existing.is_primary = True
        return True

    db.add(
        ContactMethod(
            organization_id=principal.organization_id,
            contact_id=contact.id,
            method_type=method_type,
            value=cleaned_value,
            normalized_value=normalized_value,
            is_primary=True,
        )
    )
    previous_values[audit_key] = None
    new_values[audit_key] = cleaned_value
    return True


def normalize_blank(value: str) -> str | None:
    cleaned_value = value.strip()
    return cleaned_value or None


def normalize_email(value: str) -> str:
    return value.strip().lower()


def normalize_phone(value: str) -> str:
    return "".join(character for character in value if character.isdigit())


def normalize_address_key(
    street_address: str,
    city: str,
    state: str,
    postal_code: str,
) -> str:
    raw = "|".join([street_address, city, state, postal_code])
    normalized = "".join(character.lower() if character.isalnum() else " " for character in raw)
    return " ".join(normalized.split())


def property_fields_changed(values: dict[str, Any]) -> bool:
    property_keys = {"street_address", "city", "state", "postal_code"}
    return any(key in values for key in property_keys)


def lead_to_read(db: Session, lead: Lead) -> LeadRead:
    contact = db.get(Contact, lead.contact_id)
    property_record = db.get(Property, lead.property_id)
    assigned_user = db.get(User, lead.assigned_user_id) if lead.assigned_user_id else None
    if contact is None or property_record is None:
        raise RuntimeError("lead is missing required contact or property")

    return LeadRead(
        id=lead.id,
        contact_id=lead.contact_id,
        property_id=lead.property_id,
        source=lead.source,
        stage_key=lead.stage_key,
        lead_temperature=lead.lead_temperature,
        seller_name=contact.legal_name,
        preferred_name=contact.preferred_name,
        property_address=(
            f"{property_record.street_address}, {property_record.city}, "
            f"{property_record.state} {property_record.postal_code}"
        ),
        property_street_address=property_record.street_address,
        property_city=property_record.city,
        property_state=property_record.state,
        property_postal_code=property_record.postal_code,
        property_county=property_record.county,
        property_type=property_record.property_type,
        assigned_user_email=assigned_user.email if assigned_user else None,
        motivation=lead.motivation,
        desired_timeline=lead.desired_timeline,
        property_condition=lead.property_condition,
        occupancy_status=lead.occupancy_status,
        asking_price=lead.asking_price,
        mortgage_balance=lead.mortgage_balance,
        appointment_status=lead.appointment_status,
        next_follow_up_at=lead.next_follow_up_at,
        created_at=lead.created_at,
    )
