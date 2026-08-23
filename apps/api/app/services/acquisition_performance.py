from collections import defaultdict
from datetime import UTC, datetime, timedelta
from statistics import median
from typing import Any, Literal
from uuid import UUID

from pydantic import ValidationError
from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session

from app.core.auth import Principal
from app.models.foundation import (
    Appointment,
    CallRecord,
    CallRecording,
    CallTranscript,
    CommunicationRecord,
    ContactMethod,
    FieldInspection,
    FieldNegotiationSession,
    Lead,
    LeadQualificationSession,
    Role,
    RoleAssignment,
    RoleCredit,
    Task,
    Transaction,
    User,
)
from app.schemas.acquisition_performance import (
    AcquisitionPerformanceDimension,
    AcquisitionPerformanceDimensionKey,
    AcquisitionPerformanceOverview,
    AcquisitionPerformanceScorecard,
)
from app.schemas.voice import AcquisitionSalesCallQuality
from app.services.call_intelligence import ACQUISITION_SALES_QUALITY_POLICY_VERSION
from app.services.field_operations import ELIGIBLE_CLOSER_ROLES
from app.services.lead_lifecycle import INACTIVE_LEAD_STAGES

POLICY_VERSION = "acquisitions-performance-v1-shadow"
POLICY_WEIGHTS: dict[AcquisitionPerformanceDimensionKey, int] = {
    "speed_to_lead": 2_000,
    "follow_up_discipline": 2_000,
    "conversation_quality": 2_000,
    "qualification_quality": 1_500,
    "crm_hygiene": 1_000,
    "appointment_execution": 500,
    "mature_outcomes": 1_000,
}
MINIMUM_SAMPLES: dict[AcquisitionPerformanceDimensionKey, int] = {
    "speed_to_lead": 5,
    "follow_up_discipline": 5,
    "conversation_quality": 3,
    "qualification_quality": 3,
    "crm_hygiene": 5,
    "appointment_execution": 3,
    "mature_outcomes": 3,
}
CONVERSATION_SCORE_WEIGHTS = {
    "active_listening_score": 25,
    "discovery_score": 20,
    "objection_handling_score": 20,
    "next_step_clarity_score": 15,
    "professionalism_score": 10,
    "compliance_score": 10,
}
ACTIVE_ROLE_CREDIT_STATUSES = {"approved", "earned", "payable", "paid"}
ACQUISITION_ROLE_CREDIT_KEYS = {"lead_manager", "acquisitions_closer"}
SUCCESSFUL_TRANSACTION_STATUSES = {"executed", "funded", "closed"}
CANCELLED_TRANSACTION_STATUSES = {"cancelled", "canceled"}
ELIGIBLE_OUTBOUND_COMMUNICATION_CHANNELS = {"call", "phone", "sms", "email"}
INELIGIBLE_OUTBOUND_COMMUNICATION_STATUSES = {
    "blocked",
    "cancelled",
    "canceled",
    "draft",
    "failed",
    "rejected",
    "undelivered",
}
ELIGIBLE_OUTBOUND_CALL_STATUSES = {
    "answered",
    "busy",
    "completed",
    "in-progress",
    "initiated",
    "no-answer",
    "ringing",
}


def get_acquisition_performance(
    db: Session,
    principal: Principal,
    *,
    period_days: Literal[30, 90],
    now: datetime | None = None,
) -> AcquisitionPerformanceOverview:
    generated_at = _as_utc(now or datetime.now(UTC))
    period_start = generated_at - timedelta(days=period_days)
    users = _eligible_users(db, principal.organization_id)
    user_ids = {user.id for user in users}

    speed_dimensions, speed_misses = _speed_dimensions(
        db,
        principal.organization_id,
        user_ids,
        period_start,
        generated_at,
    )
    follow_up_dimensions = _follow_up_dimensions(
        db,
        principal.organization_id,
        user_ids,
        period_start,
        generated_at,
    )
    conversation_dimensions, conversation_exclusions = _conversation_dimensions(
        db,
        principal.organization_id,
        user_ids,
        period_start,
        generated_at,
    )
    qualification_dimensions = _qualification_dimensions(
        db,
        principal.organization_id,
        user_ids,
        period_start,
        generated_at,
    )
    crm_dimensions = _crm_hygiene_dimensions(
        db,
        principal.organization_id,
        user_ids,
        period_start,
        generated_at,
    )
    appointment_dimensions = _appointment_dimensions(
        db,
        principal.organization_id,
        user_ids,
        period_start,
        generated_at,
    )
    outcome_dimensions = _mature_outcome_dimensions(
        db,
        principal.organization_id,
        user_ids,
        period_start,
        generated_at,
    )

    dimensions_by_user = {
        user_id: [
            speed_dimensions[user_id],
            follow_up_dimensions[user_id],
            conversation_dimensions[user_id],
            qualification_dimensions[user_id],
            crm_dimensions[user_id],
            appointment_dimensions[user_id],
            outcome_dimensions[user_id],
        ]
        for user_id in user_ids
    }
    scorecards = [
        _scorecard(
            user,
            dimensions_by_user[user.id],
            speed_misses=speed_misses.get(user.id, 0),
            conversation_exclusions=conversation_exclusions.get(user.id, 0),
        )
        for user in users
    ]
    return AcquisitionPerformanceOverview(
        period_days=period_days,
        period_start=period_start,
        period_end=generated_at,
        policy_version=POLICY_VERSION,
        shadow_mode=True,
        weights=POLICY_WEIGHTS,
        scorecards=scorecards,
        warnings=[
            "Shadow mode: use this scorecard for coaching and calibration, not pay, "
            "discipline, termination, or automated lead routing.",
            "Only Stonegate activity with usable user attribution is measured; external work "
            "and unattributed records may reduce coverage.",
            "Scores are not rankings. Compare each salesperson with their own trend and inspect "
            "the sample and evidence coverage before drawing conclusions.",
        ],
    )


def _eligible_users(db: Session, organization_id: UUID) -> list[User]:
    return list(
        db.scalars(
            select(User)
            .join(RoleAssignment, RoleAssignment.user_id == User.id)
            .join(Role, Role.id == RoleAssignment.role_id)
            .where(
                User.organization_id == organization_id,
                User.is_active.is_(True),
                Role.key.in_(ELIGIBLE_CLOSER_ROLES),
            )
            .distinct()
            .order_by(User.display_name)
        )
    )


def _speed_dimensions(
    db: Session,
    organization_id: UUID,
    user_ids: set[UUID],
    period_start: datetime,
    now: datetime,
) -> tuple[dict[UUID, AcquisitionPerformanceDimension], dict[UUID, int]]:
    leads = list(
        db.scalars(
            select(Lead).where(
                Lead.organization_id == organization_id,
                Lead.created_at >= period_start,
                Lead.created_at <= now,
            )
        )
    )
    lead_ids = {lead.id for lead in leads}
    lead_created_at_by_id = {lead.id: _as_utc(lead.created_at) for lead in leads}
    contactable_contacts = (
        set(
            db.scalars(
                select(ContactMethod.contact_id)
                .where(
                    ContactMethod.organization_id == organization_id,
                    ContactMethod.contact_id.in_({lead.contact_id for lead in leads}),
                    ContactMethod.method_type.in_(("phone", "email")),
                    ContactMethod.normalized_value != "",
                )
                .distinct()
            )
        )
        if leads
        else set()
    )
    first_event_by_lead: dict[UUID, tuple[datetime, UUID]] = {}
    if lead_ids and user_ids:
        communications = db.scalars(
            select(CommunicationRecord).where(
                CommunicationRecord.organization_id == organization_id,
                CommunicationRecord.lead_id.in_(lead_ids),
                CommunicationRecord.actor_user_id.in_(user_ids),
                CommunicationRecord.direction == "outbound",
                CommunicationRecord.channel.in_(ELIGIBLE_OUTBOUND_COMMUNICATION_CHANNELS),
                CommunicationRecord.provider != "manual",
                CommunicationRecord.status.not_in(
                    INELIGIBLE_OUTBOUND_COMMUNICATION_STATUSES
                ),
                CommunicationRecord.occurred_at >= period_start,
                CommunicationRecord.occurred_at <= now,
            )
        )
        for record in communications:
            if (
                record.lead_id is not None
                and record.actor_user_id is not None
                and _as_utc(record.occurred_at) >= lead_created_at_by_id[record.lead_id]
            ):
                _keep_first_event(
                    first_event_by_lead,
                    record.lead_id,
                    record.occurred_at,
                    record.actor_user_id,
                )
        calls = db.scalars(
            select(CallRecord).where(
                CallRecord.organization_id == organization_id,
                CallRecord.lead_id.in_(lead_ids),
                CallRecord.actor_user_id.in_(user_ids),
                CallRecord.direction == "outbound",
                CallRecord.status.in_(ELIGIBLE_OUTBOUND_CALL_STATUSES),
                or_(
                    and_(CallRecord.started_at.is_not(None), CallRecord.started_at >= period_start),
                    and_(CallRecord.started_at.is_(None), CallRecord.created_at >= period_start),
                ),
                or_(CallRecord.started_at.is_(None), CallRecord.started_at <= now),
            )
        )
        for call in calls:
            event_at = call.started_at or call.created_at
            if (
                call.lead_id is not None
                and call.actor_user_id is not None
                and _as_utc(event_at) >= lead_created_at_by_id[call.lead_id]
            ):
                _keep_first_event(
                    first_event_by_lead,
                    call.lead_id,
                    event_at,
                    call.actor_user_id,
                )

    total: dict[UUID, int] = defaultdict(int)
    timing_points: dict[UUID, int] = defaultdict(int)
    within_five: dict[UUID, int] = defaultdict(int)
    response_minutes: dict[UUID, list[float]] = defaultdict(list)
    missed: dict[UUID, int] = defaultdict(int)
    for lead in leads:
        if lead.contact_id not in contactable_contacts:
            continue
        lead_created_at = _as_utc(lead.created_at)
        event = first_event_by_lead.get(lead.id)
        if event is not None and _as_utc(event[0]) >= lead_created_at:
            event_at, actor_user_id = event
            elapsed = max(0.0, (_as_utc(event_at) - lead_created_at).total_seconds() / 60)
            if actor_user_id in user_ids:
                total[actor_user_id] += 1
                response_minutes[actor_user_id].append(elapsed)
                timing_points[actor_user_id] += _speed_points(elapsed)
                if elapsed <= 5:
                    within_five[actor_user_id] += 1
        elif lead.assigned_user_id in user_ids and now - lead_created_at > timedelta(minutes=60):
            assigned_user_id = lead.assigned_user_id
            if assigned_user_id is not None:
                total[assigned_user_id] += 1
                missed[assigned_user_id] += 1

    result: dict[UUID, AcquisitionPerformanceDimension] = {}
    for user_id in user_ids:
        sample = total[user_id]
        numerator = timing_points[user_id]
        median_minutes = (
            round(median(response_minutes[user_id]), 1) if response_minutes[user_id] else None
        )
        detail = (
            f"Median recorded first response: {median_minutes:g} minutes. "
            if median_minutes is not None
            else "No attributed outbound response time is available. "
        )
        detail += (
            f"{missed[user_id]} currently assigned contactable lead(s) older than 60 "
            "minutes had no outbound evidence. Timing tiers are 100 points within 5 minutes, "
            "90 within 10, 80 within 15, 60 within 30, 30 within 60, and 0 after 60."
        )
        result[user_id] = _ratio_dimension(
            key="speed_to_lead",
            label="Speed to lead",
            numerator=numerator,
            denominator=sample * 100,
            sample_size=sample,
            display=(
                f"{round(numerator / sample)}/100 timing score; median "
                f"{median_minutes:g} minutes; {within_five[user_id]}/{sample} within 5 minutes"
                if sample and median_minutes is not None
                else f"{round(numerator / sample)}/100 timing score; no recorded response median"
                if sample
                else "No attributable contactable leads"
            ),
            detail=detail,
        )
    return result, dict(missed)


def _follow_up_dimensions(
    db: Session,
    organization_id: UUID,
    user_ids: set[UUID],
    period_start: datetime,
    now: datetime,
) -> dict[UUID, AcquisitionPerformanceDimension]:
    total: dict[UUID, int] = defaultdict(int)
    on_time: dict[UUID, int] = defaultdict(int)
    tasks = db.scalars(
        select(Task).where(
            Task.organization_id == organization_id,
            Task.lead_id.is_not(None),
            Task.work_kind == "primary_next_action",
            Task.status.not_in(("cancelled", "superseded")),
            Task.due_at.is_not(None),
            Task.due_at >= period_start,
            Task.due_at <= now,
        )
    )
    for task in tasks:
        actor_user_id = task.completed_by_user_id or task.responsible_user_id
        if actor_user_id not in user_ids or task.due_at is None:
            continue
        total[actor_user_id] += 1
        if (
            task.status == "completed"
            and task.completed_at is not None
            and _as_utc(task.completed_at) <= _as_utc(task.due_at)
        ):
            on_time[actor_user_id] += 1
    return {
        user_id: _ratio_dimension(
            key="follow_up_discipline",
            label="Follow-up discipline",
            numerator=on_time[user_id],
            denominator=total[user_id],
            sample_size=total[user_id],
            display=(
                f"{on_time[user_id]}/{total[user_id]} due follow-ups completed on time"
                if total[user_id]
                else "No matured follow-up tasks"
            ),
            detail=(
                "Uses lead-linked tasks whose due date has passed. Completion is credited to the "
                "recorded completer, falling back to the responsible user when no completer "
                "is saved. Only primary next-action work is eligible."
            ),
        )
        for user_id in user_ids
    }


def _conversation_dimensions(
    db: Session,
    organization_id: UUID,
    user_ids: set[UUID],
    period_start: datetime,
    now: datetime,
) -> tuple[dict[UUID, AcquisitionPerformanceDimension], dict[UUID, int]]:
    scores: dict[UUID, list[float]] = defaultdict(list)
    excluded: dict[UUID, int] = defaultdict(int)
    if user_ids:
        rows = db.execute(
            select(CallTranscript, CallRecord)
            .join(CallRecording, CallRecording.id == CallTranscript.recording_id)
            .join(CallRecord, CallRecord.id == CallRecording.call_record_id)
            .where(
                CallTranscript.organization_id == organization_id,
                CallRecord.lead_id.is_not(None),
                CallRecord.actor_user_id.in_(user_ids),
                or_(
                    and_(CallRecord.started_at.is_not(None), CallRecord.started_at >= period_start),
                    and_(CallRecord.started_at.is_(None), CallRecord.created_at >= period_start),
                ),
                or_(CallRecord.started_at.is_(None), CallRecord.started_at <= now),
            )
        )
        for transcript, call in rows:
            actor_user_id = call.actor_user_id
            if actor_user_id is None:
                continue
            score = _conversation_score(transcript.transcript_metadata)
            if score is None:
                excluded[actor_user_id] += 1
            else:
                scores[actor_user_id].append(score)

    result: dict[UUID, AcquisitionPerformanceDimension] = {}
    for user_id in user_ids:
        values = scores[user_id]
        sample = len(values)
        average = round(sum(values) / sample) if sample else None
        result[user_id] = _average_dimension(
            key="conversation_quality",
            label="Conversation quality",
            total_score=sum(values) if values else None,
            sample_size=sample,
            display=(
                f"{average}/100 across {sample} evidence-reviewed call(s)"
                if average is not None
                else "No eligible evidence-reviewed calls"
            ),
            detail=(
                "Weighted from listening (25%), discovery (20%), objection handling (20%), "
                "next-step clarity (15%), professionalism (10%), and compliance (10%). "
                f"{excluded[user_id]} missing or ambiguous review(s) were excluded, not "
                "scored zero."
            ),
        )
    return result, dict(excluded)


def _conversation_score(metadata: dict[str, Any] | None) -> float | None:
    if not isinstance(metadata, dict):
        return None
    if (
        metadata.get("acquisition_sales_quality_status") != "scored"
        or metadata.get("acquisition_sales_quality_policy_version")
        != ACQUISITION_SALES_QUALITY_POLICY_VERSION
        or metadata.get("acquisition_sales_quality_evidence_validated") is not True
    ):
        return None
    try:
        quality = AcquisitionSalesCallQuality.model_validate(
            metadata.get("acquisition_sales_quality")
        )
    except ValidationError:
        return None
    if (
        not quality.evaluable
        or quality.speaker_attribution_confidence < 60
        or quality.confidence < 60
    ):
        return None
    cited_fields = {item.field for item in quality.evidence}
    weighted_total = 0.0
    for key, weight in CONVERSATION_SCORE_WEIGHTS.items():
        value = getattr(quality, key)
        if value is None or key not in cited_fields:
            return None
        weighted_total += value * weight
    return weighted_total / 100


def _qualification_dimensions(
    db: Session,
    organization_id: UUID,
    user_ids: set[UUID],
    period_start: datetime,
    now: datetime,
) -> dict[UUID, AcquisitionPerformanceDimension]:
    scores: dict[UUID, list[float]] = defaultdict(list)
    sessions = db.scalars(
        select(LeadQualificationSession).where(
            LeadQualificationSession.organization_id == organization_id,
            LeadQualificationSession.completed_by_user_id.in_(user_ids),
            LeadQualificationSession.completed_at >= period_start,
            LeadQualificationSession.completed_at <= now,
        )
    )
    for session in sessions:
        scores[session.completed_by_user_id].append(
            max(0.0, min(100.0, session.quality_score_basis_points / 100))
        )
    result: dict[UUID, AcquisitionPerformanceDimension] = {}
    for user_id in user_ids:
        values = scores[user_id]
        sample = len(values)
        average = round(sum(values) / sample) if sample else None
        result[user_id] = _average_dimension(
            key="qualification_quality",
            label="Qualification quality",
            total_score=sum(values) if values else None,
            sample_size=sample,
            display=(
                f"{average}/100 average across {sample} completed qualification(s)"
                if average is not None
                else "No completed qualifications"
            ),
            detail=(
                "Uses the saved guided-qualification quality score and credits the user who "
                "completed the qualification."
            ),
        )
    return result


def _crm_hygiene_dimensions(
    db: Session,
    organization_id: UUID,
    user_ids: set[UUID],
    period_start: datetime,
    now: datetime,
) -> dict[UUID, AcquisitionPerformanceDimension]:
    leads = list(
        db.scalars(
            select(Lead).where(
                Lead.organization_id == organization_id,
                Lead.assigned_user_id.in_(user_ids),
                Lead.created_at >= period_start,
                Lead.created_at <= now,
                Lead.archived_at.is_(None),
            )
        )
    )
    active_leads = [lead for lead in leads if lead.stage_key not in INACTIVE_LEAD_STAGES]
    protected_actions = (
        set(
            db.execute(
                select(Task.lead_id, Task.responsible_user_id)
                .where(
                    Task.organization_id == organization_id,
                    Task.lead_id.in_({lead.id for lead in active_leads}),
                    Task.responsible_user_id.in_(user_ids),
                    Task.work_kind == "primary_next_action",
                    Task.status.in_(("open", "in_progress")),
                    Task.due_at.is_not(None),
                    Task.due_at > now,
                )
                .distinct()
            ).all()
        )
        if active_leads
        else set()
    )
    sample: dict[UUID, int] = defaultdict(int)
    passed_checks: dict[UUID, int] = defaultdict(int)
    for lead in active_leads:
        user_id = lead.assigned_user_id
        if user_id is None:
            continue
        sample[user_id] += 1
        qualification_values = (
            lead.motivation,
            lead.desired_timeline,
            lead.property_condition,
            lead.occupancy_status,
            lead.asking_price,
            lead.mortgage_balance,
        )
        if sum(bool(value and value.strip()) for value in qualification_values) >= 3:
            passed_checks[user_id] += 1
        has_future_action = (
            lead.next_follow_up_at is not None and _as_utc(lead.next_follow_up_at) > now
        ) or (lead.id, user_id) in protected_actions
        if has_future_action:
            passed_checks[user_id] += 1
    return {
        user_id: _ratio_dimension(
            key="crm_hygiene",
            label="CRM hygiene",
            numerator=passed_checks[user_id],
            denominator=sample[user_id] * 2,
            sample_size=sample[user_id],
            display=(
                f"{passed_checks[user_id]}/{sample[user_id] * 2} record-hygiene checks complete"
                if sample[user_id]
                else "No active period leads currently assigned"
            ),
            detail=(
                "Each active lead earns one check for at least three core seller facts and one "
                "for a protected future follow-up. Current ownership is used for this snapshot."
            ),
        )
        for user_id in user_ids
    }


def _appointment_dimensions(
    db: Session,
    organization_id: UUID,
    user_ids: set[UUID],
    period_start: datetime,
    now: datetime,
) -> dict[UUID, AcquisitionPerformanceDimension]:
    appointments = list(
        db.scalars(
            select(Appointment).where(
                Appointment.organization_id == organization_id,
                Appointment.owner_user_id.in_(user_ids),
                Appointment.scheduled_start_at >= period_start,
                Appointment.scheduled_start_at <= now,
            )
        )
    )
    appointment_ids = {appointment.id for appointment in appointments}
    inspections = (
        {
            item.appointment_id: item
            for item in db.scalars(
                select(FieldInspection).where(
                    FieldInspection.organization_id == organization_id,
                    FieldInspection.appointment_id.in_(appointment_ids),
                )
            )
        }
        if appointment_ids
        else {}
    )
    negotiations = (
        {
            item.appointment_id: item
            for item in db.scalars(
                select(FieldNegotiationSession).where(
                    FieldNegotiationSession.organization_id == organization_id,
                    FieldNegotiationSession.appointment_id.in_(appointment_ids),
                )
            )
        }
        if appointment_ids
        else {}
    )
    total: dict[UUID, int] = defaultdict(int)
    documented: dict[UUID, int] = defaultdict(int)
    for appointment in appointments:
        owner_user_id = appointment.owner_user_id
        if owner_user_id is None:
            continue
        total[owner_user_id] += 1
        inspection = inspections.get(appointment.id)
        negotiation = negotiations.get(appointment.id)
        completed_evidence = appointment.status == "completed" and (
            bool((appointment.outcome or "").strip())
            or (inspection is not None and inspection.status in {"submitted", "reviewed"})
            or (negotiation is not None and negotiation.outcome != "pending")
        )
        terminal_documentation = appointment.status in {"cancelled", "no_show"}
        if completed_evidence or terminal_documentation:
            documented[owner_user_id] += 1
    return {
        user_id: _ratio_dimension(
            key="appointment_execution",
            label="Appointment execution",
            numerator=documented[user_id],
            denominator=total[user_id],
            sample_size=total[user_id],
            display=(
                f"{documented[user_id]}/{total[user_id]} matured appointments documented"
                if total[user_id]
                else "No matured appointments"
            ),
            detail=(
                "Uses the appointment owner. Completed appointments require a saved outcome, "
                "submitted inspection, or recorded negotiation; cancelled and no-show statuses "
                "count as documented outcomes rather than seller failures."
            ),
        )
        for user_id in user_ids
    }


def _mature_outcome_dimensions(
    db: Session,
    organization_id: UUID,
    user_ids: set[UUID],
    period_start: datetime,
    now: datetime,
) -> dict[UUID, AcquisitionPerformanceDimension]:
    transactions = list(
        db.scalars(
            select(Transaction).where(
                Transaction.organization_id == organization_id,
                or_(
                    _timestamp_in_period(Transaction.contract_executed_at, period_start, now),
                    _timestamp_in_period(Transaction.funded_at, period_start, now),
                    _timestamp_in_period(Transaction.closed_at, period_start, now),
                    _timestamp_in_period(Transaction.cancelled_at, period_start, now),
                    and_(
                        Transaction.updated_at >= period_start,
                        Transaction.updated_at <= now,
                        or_(
                            and_(
                                Transaction.status == "executed",
                                Transaction.contract_executed_at.is_(None),
                            ),
                            and_(
                                Transaction.status == "funded",
                                Transaction.funded_at.is_(None),
                            ),
                            and_(
                                Transaction.status == "closed",
                                Transaction.closed_at.is_(None),
                            ),
                            and_(
                                Transaction.status.in_(CANCELLED_TRANSACTION_STATUSES),
                                Transaction.cancelled_at.is_(None),
                            ),
                        ),
                    ),
                ),
            )
        )
    )
    transaction_ids = {transaction.id for transaction in transactions}
    lead_ids = {transaction.lead_id for transaction in transactions}
    credits = (
        list(
            db.scalars(
                select(RoleCredit).where(
                    RoleCredit.organization_id == organization_id,
                    RoleCredit.status.in_(ACTIVE_ROLE_CREDIT_STATUSES),
                    RoleCredit.role_key.in_(ACQUISITION_ROLE_CREDIT_KEYS),
                    or_(
                        RoleCredit.transaction_id.in_(transaction_ids),
                        and_(
                            RoleCredit.transaction_id.is_(None),
                            RoleCredit.lead_id.in_(lead_ids),
                        ),
                    ),
                )
            )
        )
        if transactions
        else []
    )
    denominator: dict[UUID, float] = defaultdict(float)
    numerator: dict[UUID, float] = defaultdict(float)
    samples: dict[UUID, int] = defaultdict(int)
    for transaction in transactions:
        succeeded = _mature_transaction_outcome(transaction, period_start, now)
        if succeeded is None:
            continue
        transaction_credits: dict[UUID, int] = {}
        for credit in credits:
            if credit.user_id not in user_ids:
                continue
            if credit.transaction_id == transaction.id or (
                credit.transaction_id is None and credit.lead_id == transaction.lead_id
            ):
                transaction_credits[credit.user_id] = max(
                    transaction_credits.get(credit.user_id, 0),
                    credit.credit_basis_points,
                )
        if not transaction_credits and transaction.owner_user_id in user_ids:
            owner_user_id = transaction.owner_user_id
            if owner_user_id is not None:
                transaction_credits[owner_user_id] = 10_000
        for user_id, basis_points in transaction_credits.items():
            share = max(0.0, min(1.0, basis_points / 10_000))
            denominator[user_id] += share
            samples[user_id] += 1
            if succeeded:
                numerator[user_id] += share
    result: dict[UUID, AcquisitionPerformanceDimension] = {}
    for user_id in user_ids:
        total_share = denominator[user_id]
        mature_share = numerator[user_id]
        result[user_id] = _ratio_dimension(
            key="mature_outcomes",
            label="Mature outcomes",
            numerator=round(mature_share, 4),
            denominator=round(total_share, 4),
            sample_size=samples[user_id],
            display=(
                f"{mature_share:.2f}/{total_share:.2f} credited contract outcome(s) matured"
                if total_share
                else "No attributable transaction outcomes"
            ),
            detail=(
                "Uses approved or earned lead-manager/acquisitions-closer role-credit shares, "
                "falling back to transaction ownership only when no qualifying credit exists."
            ),
        )
    return result


def _mature_transaction_outcome(
    transaction: Transaction,
    period_start: datetime,
    now: datetime,
) -> bool | None:
    successful_events = [
        _as_utc(value)
        for value in (
            transaction.contract_executed_at,
            transaction.funded_at,
            transaction.closed_at,
        )
        if value is not None and period_start <= _as_utc(value) <= now
    ]
    cancelled_at = (
        _as_utc(transaction.cancelled_at)
        if transaction.cancelled_at is not None
        and period_start <= _as_utc(transaction.cancelled_at) <= now
        else None
    )
    if successful_events or cancelled_at is not None:
        latest_success = max(successful_events) if successful_events else None
        return not (
            cancelled_at is not None
            and (latest_success is None or cancelled_at >= latest_success)
        )

    updated_at = _as_utc(transaction.updated_at)
    if not period_start <= updated_at <= now:
        return None
    if transaction.status in CANCELLED_TRANSACTION_STATUSES:
        return False
    if transaction.status in SUCCESSFUL_TRANSACTION_STATUSES:
        return True
    return None


def _timestamp_in_period(column: Any, period_start: datetime, now: datetime) -> Any:
    return and_(column.is_not(None), column >= period_start, column <= now)


def _ratio_dimension(
    *,
    key: AcquisitionPerformanceDimensionKey,
    label: str,
    numerator: int | float,
    denominator: int | float,
    sample_size: int,
    display: str,
    detail: str,
) -> AcquisitionPerformanceDimension:
    score = round(numerator / denominator * 100) if denominator > 0 else None
    return _dimension(
        key=key,
        label=label,
        score=score,
        sample_size=sample_size,
        numerator=float(numerator) if denominator > 0 else None,
        denominator=float(denominator) if denominator > 0 else None,
        display=display,
        detail=detail,
    )


def _average_dimension(
    *,
    key: AcquisitionPerformanceDimensionKey,
    label: str,
    total_score: float | None,
    sample_size: int,
    display: str,
    detail: str,
) -> AcquisitionPerformanceDimension:
    score = round(total_score / sample_size) if total_score is not None and sample_size else None
    return _dimension(
        key=key,
        label=label,
        score=score,
        sample_size=sample_size,
        numerator=round(total_score, 2) if total_score is not None else None,
        denominator=float(sample_size) if sample_size else None,
        display=display,
        detail=detail,
    )


def _dimension(
    *,
    key: AcquisitionPerformanceDimensionKey,
    label: str,
    score: int | None,
    sample_size: int,
    numerator: float | None,
    denominator: float | None,
    display: str,
    detail: str,
) -> AcquisitionPerformanceDimension:
    minimum = MINIMUM_SAMPLES[key]
    status: Literal["unavailable", "building", "ready"]
    if score is None:
        status = "unavailable"
    elif sample_size < minimum:
        status = "building"
    else:
        status = "ready"
    published_score = score if status == "ready" else None
    return AcquisitionPerformanceDimension(
        key=key,
        label=label,
        weight_basis_points=POLICY_WEIGHTS[key],
        score=published_score,
        status=status,
        sample_size=sample_size,
        minimum_sample_size=minimum,
        numerator=numerator,
        denominator=denominator,
        display_value=display,
        detail=detail,
    )


def _scorecard(
    user: User,
    dimensions: list[AcquisitionPerformanceDimension],
    *,
    speed_misses: int,
    conversation_exclusions: int,
) -> AcquisitionPerformanceScorecard:
    eligible = [dimension for dimension in dimensions if dimension.status == "ready"]
    coverage = sum(dimension.weight_basis_points for dimension in eligible)
    overall_score = (
        round(
            sum((dimension.score or 0) * dimension.weight_basis_points for dimension in eligible)
            / coverage
        )
        if coverage >= 6_000
        else None
    )
    reliability: Literal["building", "provisional", "reliable"]
    if coverage < 6_000:
        reliability = "building"
    elif coverage >= 8_000:
        reliability = "reliable"
    else:
        reliability = "provisional"

    strengths = [
        f"{item.label}: {item.score}/100"
        for item in sorted(
            (dimension for dimension in eligible if (dimension.score or 0) >= 75),
            key=lambda dimension: dimension.score or 0,
            reverse=True,
        )[:2]
    ]
    focus = [
        f"{item.label}: {item.score}/100"
        for item in sorted(
            (dimension for dimension in eligible if (dimension.score or 0) < 70),
            key=lambda dimension: dimension.score or 0,
        )[:2]
    ]
    warnings = [
        f"{dimension.label} needs {dimension.minimum_sample_size} observations; "
        f"{dimension.sample_size} are available."
        for dimension in dimensions
        if dimension.status != "ready"
    ]
    if coverage < 6_000:
        warnings.insert(
            0,
            f"Overall score withheld: {coverage / 100:g}% of base policy weight has usable "
            "evidence; "
            "60% is required.",
        )
    if speed_misses:
        warnings.append(
            f"{speed_misses} currently assigned contactable lead(s) had no outbound evidence "
            "after 60 minutes and count as missed speed-to-lead observations. Current ownership "
            "is fallback attribution because no actor exists for an unattempted lead."
        )
    if conversation_exclusions:
        warnings.append(
            f"{conversation_exclusions} call review(s) were excluded because evidence, model "
            "confidence, or speaker attribution was incomplete."
        )
    return AcquisitionPerformanceScorecard(
        user_id=user.id,
        user_name=user.display_name,
        overall_score=overall_score,
        coverage_basis_points=coverage,
        reliability_status=reliability,
        dimensions=dimensions,
        strengths=strengths,
        focus_areas=focus,
        warnings=warnings,
    )


def _keep_first_event(
    target: dict[UUID, tuple[datetime, UUID]],
    lead_id: UUID,
    occurred_at: datetime,
    actor_user_id: UUID,
) -> None:
    current = target.get(lead_id)
    if current is None or _as_utc(occurred_at) < _as_utc(current[0]):
        target[lead_id] = (occurred_at, actor_user_id)


def _numeric_score(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    number = float(value)
    return number if 0 <= number <= 100 else None


def _speed_points(elapsed_minutes: float) -> int:
    if elapsed_minutes <= 5:
        return 100
    if elapsed_minutes <= 10:
        return 90
    if elapsed_minutes <= 15:
        return 80
    if elapsed_minutes <= 30:
        return 60
    if elapsed_minutes <= 60:
        return 30
    return 0


def _as_utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)
