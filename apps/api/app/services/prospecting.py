from collections import defaultdict
from collections.abc import Mapping
from datetime import UTC, date, datetime, timedelta
from uuid import UUID

from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.auth import Principal
from app.core.config import get_settings
from app.domain.rbac import PermissionKeys
from app.models.foundation import (
    ActivityEvent,
    Appointment,
    AttributionTouch,
    AuditEvent,
    Campaign,
    Contact,
    ContactMethod,
    Lead,
    Property,
    Prospect,
    ProspectCallingBatch,
    ProspectCallingBatchEntry,
    ProspectHandoff,
    ProspectingAttempt,
    ProspectingScriptVersion,
    Role,
    RoleAssignment,
    SuppressionRecord,
    User,
)
from app.schemas.operations import OperationsUserRead
from app.schemas.prospecting import (
    ProspectHandoffDecision,
    ProspectHandoffRead,
    ProspectingAttemptComplete,
    ProspectingAttemptRead,
    ProspectingEntryRead,
    ProspectingQueueSummary,
    ProspectingScorecardRead,
    ProspectingScriptCreate,
    ProspectingScriptRead,
    ProspectingWorkbenchOverview,
    ScriptQuestion,
)
from app.services.acquisition_operations import (
    create_notification,
    operations_user_read,
    upsert_internal_calendar_event,
)
from app.services.inbox import add_automatic_owner_watchers, ensure_primary_conversation
from app.services.lead_manager import create_case_for_handoff, sync_case_handoff_decision
from app.services.property_validation import canonical_address_key

ACQUISITION_ROLE_KEYS = {
    "owner",
    "founder_operator",
    "ceo",
    "administrator",
    "acquisition_manager",
    "acquisition_rep",
}
WARM_OUTCOMES = {"interested", "appointment_set"}
CALLBACK_OUTCOMES = {"callback_requested", "follow_up"}
CONTACT_OUTCOMES = {
    "callback_requested",
    "follow_up",
    "interested",
    "appointment_set",
    "not_interested",
    "do_not_call",
}
FINAL_OUTCOMES = {"not_interested", "wrong_number", "do_not_call"}
DEFAULT_DISPOSITION_RULES = {
    "warm_outcomes": sorted(WARM_OUTCOMES),
    "callback_outcomes": sorted(CALLBACK_OUTCOMES),
    "final_outcomes": sorted(FINAL_OUTCOMES),
    "warm_handoff_requires_all_required_answers": True,
}


def can_manage(principal: Principal) -> bool:
    return PermissionKeys.MANAGE_ACQUISITION_OPERATIONS in principal.permission_keys


def get_prospecting_overview(
    db: Session,
    principal: Principal,
) -> ProspectingWorkbenchOverview:
    user = db.get(User, principal.user_id)
    if user is None:
        raise ValueError("Workspace user is unavailable.")
    manageable = can_manage(principal)
    scripts = list_scripts(db, principal) if manageable else []
    current_entry = get_current_entry(db, principal)
    active_script = get_active_script(db, principal.organization_id)
    if current_entry and current_entry.active_attempt:
        active_script = db.get(
            ProspectingScriptVersion,
            current_entry.active_attempt.script_version_id,
        )
    return ProspectingWorkbenchOverview(
        current_user_id=user.id,
        current_user_name=user.display_name,
        can_manage=manageable,
        active_script=script_read(db, active_script) if active_script else None,
        scripts=scripts,
        current_entry=current_entry,
        queue=queue_summary(db, principal, manageable=manageable),
        acquisition_users=list_acquisition_users(db, principal.organization_id),
        pending_handoffs=list_handoffs(
            db,
            principal,
            statuses={"pending"},
            manager_scope=manageable,
        ),
        returned_handoffs=list_handoffs(
            db,
            principal,
            statuses={"needs_correction"},
            manager_scope=False,
        ),
        scorecards=build_scorecards(db, principal, manageable=manageable),
    )


def create_script(
    db: Session,
    principal: Principal,
    payload: ProspectingScriptCreate,
) -> ProspectingScriptRead:
    next_version = int(
        db.scalar(
            select(func.max(ProspectingScriptVersion.version_number)).where(
                ProspectingScriptVersion.organization_id == principal.organization_id
            )
        )
        or 0
    ) + 1
    script = ProspectingScriptVersion(
        organization_id=principal.organization_id,
        version_number=next_version,
        title=payload.title.strip(),
        status="draft",
        opening_script=payload.opening_script.strip(),
        qualification_questions=[
            item.model_dump(mode="json") for item in payload.qualification_questions
        ],
        disposition_rules=DEFAULT_DISPOSITION_RULES,
        created_by_user_id=principal.user_id,
        approved_by_user_id=None,
        approved_at=None,
    )
    db.add(script)
    db.flush()
    add_audit(
        db,
        principal,
        action="prospecting.script_created",
        entity_type="prospecting_script_version",
        entity_id=script.id,
        previous=None,
        new={"version_number": script.version_number, "status": script.status},
        reason="Caller script draft created",
    )
    db.commit()
    return script_read(db, script)


def approve_script(
    db: Session,
    principal: Principal,
    script_id: UUID,
) -> ProspectingScriptRead | None:
    script = db.scalar(
        select(ProspectingScriptVersion).where(
            ProspectingScriptVersion.organization_id == principal.organization_id,
            ProspectingScriptVersion.id == script_id,
        )
    )
    if script is None:
        return None
    if script.status not in {"draft", "approved"}:
        raise ValueError("Only a draft caller script can be approved.")
    previous_active = db.scalars(
        select(ProspectingScriptVersion).where(
            ProspectingScriptVersion.organization_id == principal.organization_id,
            ProspectingScriptVersion.status == "approved",
            ProspectingScriptVersion.id != script.id,
        )
    ).all()
    for prior in previous_active:
        prior.status = "retired"
    previous = {"status": script.status}
    script.status = "approved"
    script.approved_by_user_id = principal.user_id
    script.approved_at = datetime.now(UTC)
    add_audit(
        db,
        principal,
        action="prospecting.script_approved",
        entity_type="prospecting_script_version",
        entity_id=script.id,
        previous=previous,
        new={"status": script.status, "version_number": script.version_number},
        reason="Caller script approved for live queue use",
    )
    db.commit()
    return script_read(db, script)


def start_attempt(
    db: Session,
    principal: Principal,
    entry_id: UUID,
) -> ProspectingEntryRead | None:
    entry = scoped_entry(db, principal, entry_id)
    if entry is None:
        return None
    existing_user_attempt = db.scalar(
        select(ProspectingAttempt).where(
            ProspectingAttempt.organization_id == principal.organization_id,
            ProspectingAttempt.caller_user_id == principal.user_id,
            ProspectingAttempt.status == "in_progress",
        )
    )
    if existing_user_attempt and existing_user_attempt.batch_entry_id != entry.id:
        raise ValueError("Finish the active prospect before opening another record.")
    existing_entry_attempt = db.scalar(
        select(ProspectingAttempt).where(
            ProspectingAttempt.batch_entry_id == entry.id,
            ProspectingAttempt.status == "in_progress",
        )
    )
    if existing_entry_attempt:
        if existing_entry_attempt.caller_user_id != principal.user_id:
            raise ValueError("This prospect is already being worked by another caller.")
        return entry_read(db, entry)
    if entry.status not in {"queued", "ready", "needs_correction"}:
        raise ValueError("This prospect is not available to start.")
    if entry.next_attempt_at and as_utc(entry.next_attempt_at) > datetime.now(UTC):
        raise ValueError("This callback is not due yet.")
    prospect = db.get(Prospect, entry.prospect_id)
    if prospect is None:
        raise ValueError("The prospect is no longer available.")
    if prospect.call_eligibility != "eligible":
        raise ValueError("This prospect is not cleared for calling.")
    script = get_active_script(db, principal.organization_id)
    if script is None:
        raise ValueError("An owner must approve a caller script before prospecting begins.")
    now = datetime.now(UTC)
    attempt = ProspectingAttempt(
        organization_id=principal.organization_id,
        batch_entry_id=entry.id,
        prospect_id=prospect.id,
        caller_user_id=principal.user_id,
        script_version_id=script.id,
        call_record_id=None,
        status="in_progress",
        outcome=None,
        contact_made=None,
        qualification_answers={},
        notes=None,
        callback_at=None,
        started_at=now,
        completed_at=None,
        required_answer_count=required_question_count(script),
        answered_required_count=0,
        quality_score_basis_points=None,
    )
    entry.status = "in_progress"
    db.add(attempt)
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise ValueError("This caller or prospect already has an active attempt.") from exc
    add_audit(
        db,
        principal,
        action="prospecting.attempt_started",
        entity_type="prospecting_attempt",
        entity_id=attempt.id,
        previous=None,
        new={"entry_id": str(entry.id), "script_version": script.version_number},
        reason="Caller opened the next assigned prospect",
    )
    db.commit()
    return entry_read(db, entry)


def complete_attempt(
    db: Session,
    principal: Principal,
    attempt_id: UUID,
    payload: ProspectingAttemptComplete,
) -> ProspectingEntryRead | None:
    attempt = db.scalar(
        select(ProspectingAttempt).where(
            ProspectingAttempt.organization_id == principal.organization_id,
            ProspectingAttempt.id == attempt_id,
        )
    )
    if attempt is None:
        return None
    if attempt.status != "in_progress":
        raise ValueError("This attempt has already been completed.")
    if attempt.caller_user_id != principal.user_id and not can_manage(principal):
        raise PermissionError("Only the caller who started this attempt can complete it.")
    entry = db.get(ProspectCallingBatchEntry, attempt.batch_entry_id)
    prospect = db.get(Prospect, attempt.prospect_id)
    script = db.get(ProspectingScriptVersion, attempt.script_version_id)
    if entry is None or prospect is None or script is None:
        raise ValueError("The prospecting record is incomplete.")
    answers = clean_answers(payload.qualification_answers)
    known_keys = {question.key for question in script_questions(script)}
    unknown = set(answers) - known_keys
    if unknown:
        raise ValueError(f"Unknown caller-script answers: {', '.join(sorted(unknown))}.")
    required_keys = {
        question.key for question in script_questions(script) if question.required_for_handoff
    }
    answered_required = sum(bool(answers.get(key)) for key in required_keys)
    if payload.outcome in WARM_OUTCOMES:
        missing = sorted(key for key in required_keys if not answers.get(key))
        if missing:
            raise ValueError(
                "Complete every required warm-handoff question: " + ", ".join(missing) + "."
            )
        if not all(
            (prospect.street_address, prospect.city, prospect.state_code, prospect.postal_code)
        ):
            raise ValueError("A complete property address is required before a warm handoff.")
        validate_acquisition_user(db, principal.organization_id, payload.handoff_user_id)
    now = datetime.now(UTC)
    callback_at = as_utc(payload.callback_at) if payload.callback_at else None
    if callback_at and callback_at <= now:
        raise ValueError("Schedule callbacks in the future.")
    attempt.status = "completed"
    attempt.outcome = payload.outcome
    attempt.contact_made = payload.outcome in CONTACT_OUTCOMES
    attempt.qualification_answers = answers
    attempt.notes = clean_text(payload.notes)
    attempt.callback_at = callback_at
    attempt.completed_at = now
    attempt.required_answer_count = len(required_keys)
    attempt.answered_required_count = answered_required
    attempt.quality_score_basis_points = rate_basis_points(answered_required, len(required_keys))
    entry.attempt_count += 1
    entry.disposition = payload.outcome
    entry.last_attempt_at = now
    entry.next_attempt_at = None
    entry.completed_at = None
    prospect.last_contacted_at = now

    if payload.outcome == "no_answer":
        entry.status = "queued"
        entry.next_attempt_at = now + timedelta(days=1)
    elif payload.outcome == "left_voicemail":
        entry.status = "queued"
        entry.next_attempt_at = now + timedelta(days=2)
    elif payload.outcome in CALLBACK_OUTCOMES:
        entry.status = "queued"
        entry.next_attempt_at = callback_at
    elif payload.outcome in WARM_OUTCOMES:
        create_warm_handoff(db, principal, attempt, entry, prospect, payload, answers, now)
    else:
        entry.status = "completed"
        entry.completed_at = now
        prospect.status = payload.outcome
        if payload.outcome == "wrong_number":
            prospect.phone_validation_status = "invalid"
            prospect.call_eligibility = "blocked"
        elif payload.outcome == "do_not_call":
            prospect.call_eligibility = "blocked"
            prospect.suppression_status = "suppressed"
            record_dnc_suppression(db, principal, prospect, now)

    add_audit(
        db,
        principal,
        action="prospecting.attempt_completed",
        entity_type="prospecting_attempt",
        entity_id=attempt.id,
        previous={"status": "in_progress"},
        new={
            "status": attempt.status,
            "outcome": attempt.outcome,
            "entry_status": entry.status,
            "callback_at": callback_at.isoformat() if callback_at else None,
            "quality_score_basis_points": attempt.quality_score_basis_points,
        },
        reason="Guided prospecting outcome recorded",
    )
    refresh_batch_status(db, entry.prospect_calling_batch_id)
    db.commit()
    return entry_read(db, entry)


def decide_handoff(
    db: Session,
    principal: Principal,
    handoff_id: UUID,
    payload: ProspectHandoffDecision,
) -> ProspectHandoffRead | None:
    handoff = db.scalar(
        select(ProspectHandoff).where(
            ProspectHandoff.organization_id == principal.organization_id,
            ProspectHandoff.id == handoff_id,
        )
    )
    if handoff is None:
        return None
    if handoff.status != "pending":
        raise ValueError("This handoff has already been reviewed.")
    entry = db.scalar(
        select(ProspectCallingBatchEntry)
        .join(
            ProspectingAttempt,
            ProspectingAttempt.batch_entry_id == ProspectCallingBatchEntry.id,
        )
        .where(ProspectingAttempt.id == handoff.attempt_id)
    )
    lead = db.get(Lead, handoff.lead_id)
    prospect = db.get(Prospect, handoff.prospect_id)
    if entry is None or lead is None or prospect is None:
        raise ValueError("The handoff record is incomplete.")
    now = datetime.now(UTC)
    handoff.status = payload.decision
    handoff.reviewed_by_user_id = principal.user_id
    handoff.reviewed_at = now
    handoff.review_reason = clean_text(payload.reason)
    if payload.decision == "accepted":
        has_appointment = db.scalar(
            select(Appointment.id).where(
                Appointment.organization_id == principal.organization_id,
                Appointment.lead_id == lead.id,
                Appointment.status == "scheduled",
            )
        )
        lead.stage_key = "appointment_scheduled" if has_appointment else "qualified"
        entry.status = "completed"
        entry.completed_at = now
        prospect.status = "converted"
    else:
        lead.stage_key = "qualification_in_progress"
        entry.status = "needs_correction"
        entry.completed_at = None
        prospect.status = "handoff_correction"
    sync_case_handoff_decision(
        db,
        handoff_id=handoff.id,
        decision=payload.decision,
        reviewer_user_id=principal.user_id,
        reviewed_at=now,
    )
    create_notification(
        db,
        organization_id=principal.organization_id,
        recipient_user_id=handoff.submitted_by_user_id,
        notification_type="prospect_handoff_reviewed",
        title=(
            "Warm handoff accepted"
            if payload.decision == "accepted"
            else "Handoff needs correction"
        ),
        body=(
            "The acquisitions team accepted the seller handoff."
            if payload.decision == "accepted"
            else f"Review requested: {handoff.review_reason}"
        ),
        entity_type="prospect_handoff",
        entity_id=handoff.id,
        action_url="/os/prospecting",
        dedupe_key=f"prospect-handoff-review:{handoff.id}",
    )
    add_audit(
        db,
        principal,
        action=f"prospecting.handoff_{payload.decision}",
        entity_type="prospect_handoff",
        entity_id=handoff.id,
        previous={"status": "pending"},
        new={"status": handoff.status, "reason": handoff.review_reason},
        reason="Acquisitions reviewed the VA warm-lead handoff",
    )
    refresh_batch_status(db, entry.prospect_calling_batch_id)
    db.commit()
    return handoff_read(db, handoff)


def create_warm_handoff(
    db: Session,
    principal: Principal,
    attempt: ProspectingAttempt,
    entry: ProspectCallingBatchEntry,
    prospect: Prospect,
    payload: ProspectingAttemptComplete,
    answers: dict[str, str],
    now: datetime,
) -> None:
    assert payload.handoff_user_id is not None
    lead = convert_prospect_to_lead(
        db,
        principal,
        prospect,
        payload.handoff_user_id,
        answers,
    )
    prior_returns = db.scalars(
        select(ProspectHandoff).where(
            ProspectHandoff.organization_id == principal.organization_id,
            ProspectHandoff.prospect_id == prospect.id,
            ProspectHandoff.status == "needs_correction",
        )
    ).all()
    for prior in prior_returns:
        prior.status = "superseded"
    handoff = ProspectHandoff(
        organization_id=principal.organization_id,
        prospect_id=prospect.id,
        attempt_id=attempt.id,
        lead_id=lead.id,
        assigned_user_id=payload.handoff_user_id,
        submitted_by_user_id=principal.user_id,
        reviewed_by_user_id=None,
        status="pending",
        submitted_at=now,
        reviewed_at=None,
        review_reason=None,
    )
    db.add(handoff)
    entry.status = "handoff_pending"
    prospect.status = "warm_handoff"
    if payload.outcome == "appointment_set" and payload.appointment_start_at:
        create_handoff_appointment(db, lead, payload, now)
    db.flush()
    create_case_for_handoff(
        db,
        organization_id=principal.organization_id,
        lead_id=lead.id,
        handoff_id=handoff.id,
        assigned_user_id=payload.handoff_user_id,
        submitted_at=now,
        sla_minutes=get_settings().lead_manager_handoff_sla_minutes,
    )
    create_notification(
        db,
        organization_id=principal.organization_id,
        recipient_user_id=payload.handoff_user_id,
        notification_type="prospect_handoff",
        title="Warm seller handoff awaiting review",
        body=f"{prospect.legal_name} was qualified by the prospecting team.",
        entity_type="prospect_handoff",
        entity_id=handoff.id,
        action_url="/os/prospecting",
        dedupe_key=f"prospect-handoff:{handoff.id}",
    )


def convert_prospect_to_lead(
    db: Session,
    principal: Principal,
    prospect: Prospect,
    assigned_user_id: UUID,
    answers: dict[str, str],
) -> Lead:
    if prospect.converted_lead_id:
        existing = db.get(Lead, prospect.converted_lead_id)
        if existing is None:
            raise ValueError("The prospect points to a missing CRM lead.")
        existing.assigned_user_id = assigned_user_id
        update_lead_qualification(existing, answers)
        conversation = ensure_primary_conversation(db, existing, queue_key="qualified")
        conversation.assigned_user_id = assigned_user_id
        conversation.queue_key = "qualified"
        add_automatic_owner_watchers(db, conversation)
        return existing
    street_address = prospect.street_address
    city = prospect.city
    state_code = prospect.state_code
    postal_code = prospect.postal_code
    if not all((street_address, city, state_code, postal_code)):
        raise ValueError("A complete property address is required before a warm handoff.")
    assert street_address and city and state_code and postal_code
    contact = Contact(
        organization_id=principal.organization_id,
        legal_name=prospect.legal_name,
        preferred_name=None,
        contact_type="seller",
        assigned_user_id=assigned_user_id,
    )
    db.add(contact)
    db.flush()
    if prospect.phone and prospect.normalized_phone:
        db.add(
            ContactMethod(
                organization_id=principal.organization_id,
                contact_id=contact.id,
                method_type="phone",
                value=prospect.phone,
                normalized_value=prospect.normalized_phone,
                is_primary=True,
            )
        )
    if prospect.email and prospect.normalized_email:
        db.add(
            ContactMethod(
                organization_id=principal.organization_id,
                contact_id=contact.id,
                method_type="email",
                value=prospect.email,
                normalized_value=prospect.normalized_email,
                is_primary=not bool(prospect.phone),
            )
        )
    property_record = Property(
        organization_id=principal.organization_id,
        street_address=street_address,
        city=city,
        state=state_code,
        postal_code=postal_code,
        county=None,
        property_type=None,
        normalized_address_key=prospect.normalized_address_key
        or canonical_address_key(
            street_address,
            city,
            state_code,
            postal_code,
        ),
        address_validation_status=prospect.address_validation_status,
    )
    db.add(property_record)
    db.flush()
    campaign = db.get(Campaign, prospect.campaign_id)
    lead = Lead(
        organization_id=principal.organization_id,
        contact_id=contact.id,
        property_id=property_record.id,
        assigned_user_id=assigned_user_id,
        source="cold_call",
        stage_key="qualification_in_progress",
        lead_temperature="warm",
        motivation=None,
        desired_timeline=None,
        property_condition=None,
        occupancy_status=None,
        asking_price=None,
        mortgage_balance=None,
        appointment_status=None,
        next_follow_up_at=None,
    )
    update_lead_qualification(lead, answers)
    db.add(lead)
    db.flush()
    prospect.converted_lead_id = lead.id
    db.add(
        AttributionTouch(
            organization_id=principal.organization_id,
            lead_id=lead.id,
            touch_type="lead_creation",
            source="cold_call",
            medium="va_prospecting",
            campaign=campaign.name if campaign else None,
            term=None,
            content=None,
            gclid=None,
            fbclid=None,
            landing_page=None,
            referrer=None,
        )
    )
    db.add(
        ActivityEvent(
            organization_id=principal.organization_id,
            actor_user_id=principal.user_id,
            entity_type="lead",
            entity_id=lead.id,
            event_type="lead.created_from_prospect",
            summary="Warm seller lead created from an audited prospecting handoff.",
        )
    )
    conversation = ensure_primary_conversation(db, lead, queue_key="qualified")
    conversation.assigned_user_id = assigned_user_id
    conversation.queue_key = "qualified"
    conversation.conversation_metadata = {
        "source": "prospect_handoff",
        "prospect_id": str(prospect.id),
        "campaign_id": str(prospect.campaign_id),
        "unified_timeline": True,
    }
    add_automatic_owner_watchers(db, conversation)
    return lead


def create_handoff_appointment(
    db: Session,
    lead: Lead,
    payload: ProspectingAttemptComplete,
    now: datetime,
) -> None:
    assert payload.appointment_start_at is not None
    appointment_start_at = as_utc(payload.appointment_start_at)
    existing = db.scalar(
        select(Appointment).where(
            Appointment.organization_id == lead.organization_id,
            Appointment.lead_id == lead.id,
            Appointment.status == "scheduled",
        )
    )
    if existing:
        return
    appointment = Appointment(
        organization_id=lead.organization_id,
        lead_id=lead.id,
        contact_id=lead.contact_id,
        property_id=lead.property_id,
        owner_user_id=lead.assigned_user_id,
        appointment_type="acquisition_consultation",
        status="scheduled",
        scheduled_start_at=appointment_start_at,
        scheduled_end_at=appointment_start_at + timedelta(hours=1),
        location_type=payload.appointment_location_type or "seller_property",
        location=payload.appointment_location,
        notes=clean_text(payload.notes),
        outcome=None,
        external_calendar_id=None,
        appointment_metadata={"source": "va_handoff", "calendar_synced": False},
    )
    db.add(appointment)
    db.flush()
    upsert_internal_calendar_event(db, appointment)
    lead.appointment_status = "scheduled"
    lead.next_follow_up_at = appointment_start_at
    db.add(
        ActivityEvent(
            organization_id=lead.organization_id,
            actor_user_id=None,
            entity_type="lead",
            entity_id=lead.id,
            event_type="lead.appointment_scheduled_from_handoff",
            summary=(
                "Seller appointment scheduled for "
                f"{appointment_start_at.isoformat()}."
            ),
        )
    )


def update_lead_qualification(lead: Lead, answers: dict[str, str]) -> None:
    lead.motivation = answers.get("motivation") or lead.motivation
    lead.desired_timeline = answers.get("timeline") or lead.desired_timeline
    lead.property_condition = answers.get("property_condition") or lead.property_condition
    lead.occupancy_status = answers.get("occupancy") or lead.occupancy_status
    lead.asking_price = answers.get("asking_price") or lead.asking_price
    lead.mortgage_balance = answers.get("mortgage_balance") or lead.mortgage_balance


def record_dnc_suppression(
    db: Session,
    principal: Principal,
    prospect: Prospect,
    now: datetime,
) -> None:
    if not prospect.normalized_phone:
        return
    existing = db.scalar(
        select(SuppressionRecord).where(
            SuppressionRecord.organization_id == principal.organization_id,
            SuppressionRecord.channel == "phone",
            SuppressionRecord.normalized_address == prospect.normalized_phone,
        )
    )
    if existing:
        existing.status = "active"
        existing.reason = "Seller requested no further calls"
        existing.source = "prospecting_disposition"
        existing.suppressed_at = now
        existing.lifted_at = None
        return
    db.add(
        SuppressionRecord(
            organization_id=principal.organization_id,
            contact_id=None,
            channel="phone",
            normalized_address=prospect.normalized_phone,
            status="active",
            reason="Seller requested no further calls",
            source="prospecting_disposition",
            provider=None,
            external_event_id=None,
            suppressed_at=now,
            lifted_at=None,
            suppression_metadata={"prospect_id": str(prospect.id)},
        )
    )


def get_current_entry(db: Session, principal: Principal) -> ProspectingEntryRead | None:
    active_attempt = db.scalar(
        select(ProspectingAttempt).where(
            ProspectingAttempt.organization_id == principal.organization_id,
            ProspectingAttempt.caller_user_id == principal.user_id,
            ProspectingAttempt.status == "in_progress",
        )
    )
    if active_attempt:
        entry = db.get(ProspectCallingBatchEntry, active_attempt.batch_entry_id)
        return entry_read(db, entry) if entry else None
    now = datetime.now(UTC)
    entry = db.scalar(
        select(ProspectCallingBatchEntry)
        .join(
            ProspectCallingBatch,
            ProspectCallingBatch.id == ProspectCallingBatchEntry.prospect_calling_batch_id,
        )
        .join(Prospect, Prospect.id == ProspectCallingBatchEntry.prospect_id)
        .where(
            ProspectCallingBatchEntry.organization_id == principal.organization_id,
            ProspectCallingBatchEntry.assigned_user_id == principal.user_id,
            ProspectCallingBatch.assigned_user_id == principal.user_id,
            ProspectCallingBatchEntry.status.in_(("queued", "ready", "needs_correction")),
            Prospect.call_eligibility == "eligible",
            or_(
                ProspectCallingBatchEntry.next_attempt_at.is_(None),
                ProspectCallingBatchEntry.next_attempt_at <= now,
            ),
        )
        .order_by(
            ProspectCallingBatchEntry.next_attempt_at.asc().nulls_first(),
            ProspectCallingBatchEntry.sequence_number,
        )
    )
    return entry_read(db, entry) if entry else None


def scoped_entry(
    db: Session,
    principal: Principal,
    entry_id: UUID,
) -> ProspectCallingBatchEntry | None:
    statement = select(ProspectCallingBatchEntry).where(
        ProspectCallingBatchEntry.organization_id == principal.organization_id,
        ProspectCallingBatchEntry.id == entry_id,
    )
    if not can_manage(principal):
        statement = statement.where(
            ProspectCallingBatchEntry.assigned_user_id == principal.user_id
        )
    return db.scalar(statement)


def entry_read(db: Session, entry: ProspectCallingBatchEntry) -> ProspectingEntryRead:
    prospect = db.get(Prospect, entry.prospect_id)
    batch = db.get(ProspectCallingBatch, entry.prospect_calling_batch_id)
    campaign = db.get(Campaign, batch.campaign_id) if batch else None
    attempts = db.scalars(
        select(ProspectingAttempt)
        .where(ProspectingAttempt.batch_entry_id == entry.id)
        .order_by(ProspectingAttempt.started_at.desc())
    ).all()
    active = next((attempt for attempt in attempts if attempt.status == "in_progress"), None)
    if prospect is None or batch is None:
        raise ValueError("The calling-batch entry is incomplete.")
    return ProspectingEntryRead(
        id=entry.id,
        batch_id=batch.id,
        batch_name=batch.name,
        campaign_name=campaign.name if campaign else "Unknown campaign",
        prospect_id=prospect.id,
        legal_name=prospect.legal_name,
        phone=prospect.phone,
        email=prospect.email,
        property_address=format_property_address(prospect),
        sequence_number=entry.sequence_number,
        status=entry.status,
        attempt_count=entry.attempt_count,
        disposition=entry.disposition,
        next_attempt_at=entry.next_attempt_at,
        active_attempt=attempt_read(db, active) if active else None,
        attempts=[attempt_read(db, attempt) for attempt in attempts],
    )


def attempt_read(db: Session, attempt: ProspectingAttempt) -> ProspectingAttemptRead:
    script = db.get(ProspectingScriptVersion, attempt.script_version_id)
    return ProspectingAttemptRead(
        id=attempt.id,
        script_version_id=attempt.script_version_id,
        script_version_number=script.version_number if script else 0,
        status=attempt.status,
        outcome=attempt.outcome,
        contact_made=attempt.contact_made,
        qualification_answers=attempt.qualification_answers,
        notes=attempt.notes,
        callback_at=attempt.callback_at,
        started_at=attempt.started_at,
        completed_at=attempt.completed_at,
        quality_score_basis_points=attempt.quality_score_basis_points,
    )


def list_scripts(db: Session, principal: Principal) -> list[ProspectingScriptRead]:
    scripts = db.scalars(
        select(ProspectingScriptVersion)
        .where(ProspectingScriptVersion.organization_id == principal.organization_id)
        .order_by(ProspectingScriptVersion.version_number.desc())
    ).all()
    return [script_read(db, script) for script in scripts]


def script_read(db: Session, script: ProspectingScriptVersion) -> ProspectingScriptRead:
    creator = db.get(User, script.created_by_user_id)
    approver = db.get(User, script.approved_by_user_id) if script.approved_by_user_id else None
    return ProspectingScriptRead(
        id=script.id,
        version_number=script.version_number,
        title=script.title,
        status=script.status,
        opening_script=script.opening_script,
        qualification_questions=script_questions(script),
        created_by_name=creator.display_name if creator else "Unknown user",
        approved_by_name=approver.display_name if approver else None,
        approved_at=script.approved_at,
        created_at=script.created_at,
    )


def script_questions(script: ProspectingScriptVersion) -> list[ScriptQuestion]:
    return [ScriptQuestion.model_validate(item) for item in script.qualification_questions]


def required_question_count(script: ProspectingScriptVersion) -> int:
    return sum(question.required_for_handoff for question in script_questions(script))


def get_active_script(
    db: Session,
    organization_id: UUID,
) -> ProspectingScriptVersion | None:
    return db.scalar(
        select(ProspectingScriptVersion)
        .where(
            ProspectingScriptVersion.organization_id == organization_id,
            ProspectingScriptVersion.status == "approved",
        )
        .order_by(ProspectingScriptVersion.version_number.desc())
    )


def list_acquisition_users(
    db: Session,
    organization_id: UUID,
) -> list[OperationsUserRead]:
    users = db.scalars(
        select(User)
        .join(RoleAssignment, RoleAssignment.user_id == User.id)
        .join(Role, Role.id == RoleAssignment.role_id)
        .where(
            User.organization_id == organization_id,
            User.is_active.is_(True),
            Role.key.in_(ACQUISITION_ROLE_KEYS),
        )
        .distinct()
        .order_by(User.display_name)
    ).all()
    return [operations_user_read(db, user) for user in users]


def validate_acquisition_user(
    db: Session,
    organization_id: UUID,
    user_id: UUID | None,
) -> User:
    if user_id is None:
        raise ValueError("Select an acquisitions handoff owner.")
    user = db.scalar(
        select(User)
        .join(RoleAssignment, RoleAssignment.user_id == User.id)
        .join(Role, Role.id == RoleAssignment.role_id)
        .where(
            User.organization_id == organization_id,
            User.id == user_id,
            User.is_active.is_(True),
            Role.key.in_(ACQUISITION_ROLE_KEYS),
        )
    )
    if user is None:
        raise ValueError("Handoffs must be assigned to an active acquisitions user.")
    return user


def list_handoffs(
    db: Session,
    principal: Principal,
    *,
    statuses: set[str],
    manager_scope: bool,
) -> list[ProspectHandoffRead]:
    statement = select(ProspectHandoff).where(
        ProspectHandoff.organization_id == principal.organization_id,
        ProspectHandoff.status.in_(statuses),
    )
    if not manager_scope:
        statement = statement.where(ProspectHandoff.submitted_by_user_id == principal.user_id)
    handoffs = db.scalars(statement.order_by(ProspectHandoff.submitted_at.desc()).limit(100)).all()
    return [handoff_read(db, handoff) for handoff in handoffs]


def handoff_read(db: Session, handoff: ProspectHandoff) -> ProspectHandoffRead:
    prospect = db.get(Prospect, handoff.prospect_id)
    attempt = db.get(ProspectingAttempt, handoff.attempt_id)
    caller = db.get(User, handoff.submitted_by_user_id)
    assignee = db.get(User, handoff.assigned_user_id)
    reviewer = db.get(User, handoff.reviewed_by_user_id) if handoff.reviewed_by_user_id else None
    if prospect is None or attempt is None:
        raise ValueError("The prospect handoff is incomplete.")
    return ProspectHandoffRead(
        id=handoff.id,
        prospect_id=handoff.prospect_id,
        attempt_id=handoff.attempt_id,
        lead_id=handoff.lead_id,
        seller_name=prospect.legal_name,
        property_address=format_property_address(prospect),
        caller_name=caller.display_name if caller else "Unknown caller",
        assigned_user_id=handoff.assigned_user_id,
        assigned_user_name=assignee.display_name if assignee else "Unknown owner",
        status=handoff.status,
        outcome=attempt.outcome or "interested",
        qualification_answers=attempt.qualification_answers,
        notes=attempt.notes,
        submitted_at=handoff.submitted_at,
        reviewed_by_name=reviewer.display_name if reviewer else None,
        reviewed_at=handoff.reviewed_at,
        review_reason=handoff.review_reason,
    )


def queue_summary(
    db: Session,
    principal: Principal,
    *,
    manageable: bool,
) -> ProspectingQueueSummary:
    statement = (
        select(ProspectCallingBatchEntry)
        .join(
            ProspectCallingBatch,
            ProspectCallingBatch.id == ProspectCallingBatchEntry.prospect_calling_batch_id,
        )
        .where(ProspectCallingBatchEntry.organization_id == principal.organization_id)
    )
    if not manageable:
        statement = statement.where(
            ProspectCallingBatchEntry.assigned_user_id == principal.user_id
        )
    entries = db.scalars(statement).all()
    now = datetime.now(UTC)
    return ProspectingQueueSummary(
        ready=sum(
            entry.status in {"ready", "queued", "needs_correction"}
            and (entry.next_attempt_at is None or as_utc(entry.next_attempt_at) <= now)
            for entry in entries
        ),
        callbacks_due=sum(
            entry.status == "queued"
            and entry.next_attempt_at is not None
            and as_utc(entry.next_attempt_at) <= now
            for entry in entries
        ),
        in_progress=sum(entry.status == "in_progress" for entry in entries),
        handoff_pending=sum(entry.status == "handoff_pending" for entry in entries),
        completed=sum(entry.status == "completed" for entry in entries),
    )


def build_scorecards(
    db: Session,
    principal: Principal,
    *,
    manageable: bool,
) -> list[ProspectingScorecardRead]:
    since = datetime.now(UTC) - timedelta(days=7)
    statement = select(ProspectingAttempt).where(
        ProspectingAttempt.organization_id == principal.organization_id,
        ProspectingAttempt.status == "completed",
        ProspectingAttempt.completed_at >= since,
    )
    if not manageable:
        statement = statement.where(ProspectingAttempt.caller_user_id == principal.user_id)
    attempts = db.scalars(statement.order_by(ProspectingAttempt.completed_at.desc())).all()
    attempt_ids = [attempt.id for attempt in attempts]
    handoffs = (
        db.scalars(
            select(ProspectHandoff).where(ProspectHandoff.attempt_id.in_(attempt_ids))
        ).all()
        if attempt_ids
        else []
    )
    handoff_by_attempt = {handoff.attempt_id: handoff for handoff in handoffs}
    grouped: dict[tuple[UUID, date], list[ProspectingAttempt]] = defaultdict(list)
    for attempt in attempts:
        assert attempt.completed_at is not None
        grouped[(attempt.caller_user_id, attempt.completed_at.date())].append(attempt)
    result: list[ProspectingScorecardRead] = []
    for (caller_id, score_date), rows in grouped.items():
        caller = db.get(User, caller_id)
        contacts = sum(bool(row.contact_made) for row in rows)
        callback_count = sum(row.outcome in CALLBACK_OUTCOMES for row in rows)
        handoff_count = sum(row.id in handoff_by_attempt for row in rows)
        accepted_count = sum(
            handoff_by_attempt[row.id].status == "accepted"
            for row in rows
            if row.id in handoff_by_attempt
        )
        answered_required = sum(row.answered_required_count for row in rows)
        required_answers = sum(row.required_answer_count for row in rows)
        wrong_numbers = sum(row.outcome == "wrong_number" for row in rows)
        dnc_requests = sum(row.outcome == "do_not_call" for row in rows)
        result.append(
            ProspectingScorecardRead(
                caller_user_id=caller_id,
                caller_name=caller.display_name if caller else "Unknown caller",
                score_date=score_date,
                attempts=len(rows),
                contacts=contacts,
                callbacks=callback_count,
                handoffs=handoff_count,
                accepted_handoffs=accepted_count,
                wrong_numbers=wrong_numbers,
                dnc_requests=dnc_requests,
                contact_rate_basis_points=rate_basis_points(contacts, len(rows)),
                handoff_rate_basis_points=rate_basis_points(handoff_count, contacts),
                accepted_handoff_rate_basis_points=rate_basis_points(
                    accepted_count, handoff_count
                ),
                script_completion_rate_basis_points=rate_basis_points(
                    answered_required, required_answers
                ),
                data_quality_issue_rate_basis_points=rate_basis_points(
                    wrong_numbers, len(rows)
                ),
            )
        )
    return sorted(result, key=lambda item: (item.score_date, item.caller_name), reverse=True)


def refresh_batch_status(db: Session, batch_id: UUID) -> None:
    batch = db.get(ProspectCallingBatch, batch_id)
    if batch is None:
        return
    remaining = int(
        db.scalar(
            select(func.count())
            .select_from(ProspectCallingBatchEntry)
            .where(
                ProspectCallingBatchEntry.prospect_calling_batch_id == batch.id,
                ProspectCallingBatchEntry.status != "completed",
            )
        )
        or 0
    )
    batch.status = "completed" if remaining == 0 else "in_progress"


def format_property_address(prospect: Prospect) -> str | None:
    values = [prospect.street_address, prospect.city, prospect.state_code, prospect.postal_code]
    return ", ".join(value for value in values if value) or None


def clean_answers(values: dict[str, str]) -> dict[str, str]:
    return {key: value.strip() for key, value in values.items() if value.strip()}


def clean_text(value: str | None) -> str | None:
    cleaned = (value or "").strip()
    return cleaned or None


def rate_basis_points(numerator: int, denominator: int) -> int:
    return round(numerator / denominator * 10000) if denominator else 0


def as_utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def add_audit(
    db: Session,
    principal: Principal,
    *,
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
