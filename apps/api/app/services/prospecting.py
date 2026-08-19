import hashlib
import json
import secrets
from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import cast
from uuid import UUID

from sqlalchemy import case, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.auth import Principal
from app.core.config import get_settings
from app.domain.assets import (
    HOUSE_ASSET_CLASS,
    LAND_ASSET_CLASS,
    normalize_asset_class,
    property_identity_label,
)
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
    ProspectContactPoint,
    ProspectHandoff,
    ProspectImportBatch,
    ProspectingAttempt,
    ProspectingCohort,
    ProspectingDialLeg,
    ProspectingQualificationResponse,
    ProspectingScriptVersion,
    Role,
    RoleAssignment,
    SuppressionRecord,
    User,
)
from app.schemas.leads import LeadCloseOutRequest
from app.schemas.operations import OperationsUserRead
from app.schemas.prospecting import (
    ProspectHandoffDecision,
    ProspectHandoffRead,
    ProspectingAttemptComplete,
    ProspectingAttemptRead,
    ProspectingBatchQueueRead,
    ProspectingContactPointRead,
    ProspectingEntryRead,
    ProspectingQualificationAutosaveRequest,
    ProspectingQualificationChecklistItemRead,
    ProspectingQualificationChecklistRead,
    ProspectingQueueSummary,
    ProspectingScorecardRead,
    ProspectingScriptCreate,
    ProspectingScriptRead,
    ProspectingTechnicalFailureComplete,
    ProspectingWorkbenchOverview,
    QualificationResponseState,
    ScriptQuestion,
)
from app.services.acquisition_operations import (
    create_notification,
    operations_user_read,
    prospect_property_metadata,
    upsert_internal_calendar_event,
)
from app.services.call_recording_evidence import select_preferred_call_recording
from app.services.communication_compliance import format_e164
from app.services.inbox import add_automatic_owner_watchers, ensure_primary_conversation
from app.services.lead_lifecycle import require_lead_open_for_work
from app.services.lead_manager import create_case_for_handoff, sync_case_handoff_decision
from app.services.leads import (
    apply_lead_close_out_transition,
)
from app.services.property_identity import (
    find_property_by_identity,
    refresh_property_identity_keys,
    require_valid_property_identity,
)
from app.services.prospecting_measurement import (
    apply_outcome_measurement,
    default_handoff_decision_code,
    has_accepted_warm_evidence,
    is_accepted_warm_lead,
)

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
RETRY_OUTCOMES = {"no_answer", "left_voicemail", "technical_failure", "wrong_number"}
DEFAULT_DISPOSITION_RULES = {
    "warm_outcomes": sorted(WARM_OUTCOMES),
    "callback_outcomes": sorted(CALLBACK_OUTCOMES),
    "final_outcomes": sorted(FINAL_OUTCOMES),
    "warm_handoff_requires_all_required_answers": True,
    "no_answer_retry_delay_hours": 24,
    "voicemail_retry_delay_hours": 48,
    "technical_failure_retry_delay_minutes": 15,
    "maximum_seller_attempts": 6,
}


class ProspectingQualificationConflictError(RuntimeError):
    """An autosave mutation conflicts with the durable checklist revision."""


class ProspectingCompletionConflictError(RuntimeError):
    """A completion replay conflicts with the durable disposition receipt."""


@dataclass(frozen=True)
class ProspectingReadContext:
    """Organization-scoped objects preloaded for one queue serialization pass."""

    now: datetime
    prospects: Mapping[UUID, Prospect]
    batches: Mapping[UUID, ProspectCallingBatch]
    campaigns: Mapping[UUID, Campaign]
    cohorts: Mapping[UUID, ProspectingCohort]
    users: Mapping[UUID, User]
    contact_points_by_prospect: Mapping[UUID, Sequence[ProspectContactPoint]]
    attempts_by_entry: Mapping[UUID, Sequence[ProspectingAttempt]]
    import_batches: Mapping[UUID, ProspectImportBatch]
    scripts: Mapping[UUID, ProspectingScriptVersion]
    approved_scripts_by_asset_class: Mapping[str, ProspectingScriptVersion]
    qualification_responses_by_attempt: Mapping[UUID, Sequence[ProspectingQualificationResponse]]


def can_manage(principal: Principal) -> bool:
    return PermissionKeys.MANAGE_ACQUISITION_OPERATIONS in principal.permission_keys


def get_prospecting_overview(
    db: Session,
    principal: Principal,
) -> ProspectingWorkbenchOverview:
    from app.services.prospecting_copilot import get_copilot_overview

    user = db.get(User, principal.user_id)
    if user is None:
        raise ValueError("Workspace user is unavailable.")
    manageable = can_manage(principal)
    scripts = list_scripts(db, principal) if manageable else []
    current_entry = get_current_entry(db, principal)
    queue_entries = list_queue_entries(db, principal, manageable=manageable)
    active_script = get_active_script(
        db,
        principal.organization_id,
        current_entry.asset_class if current_entry else HOUSE_ASSET_CLASS,
    )
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
        queue_entries=queue_entries,
        queue=queue_summary(db, principal, manageable=manageable),
        batch_queues=build_batch_queues(queue_entries),
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
        copilot=get_copilot_overview(db, principal),
    )


def create_script(
    db: Session,
    principal: Principal,
    payload: ProspectingScriptCreate,
) -> ProspectingScriptRead:
    next_version = (
        int(
            db.scalar(
                select(func.max(ProspectingScriptVersion.version_number)).where(
                    ProspectingScriptVersion.organization_id == principal.organization_id
                )
            )
            or 0
        )
        + 1
    )
    script = ProspectingScriptVersion(
        organization_id=principal.organization_id,
        asset_class=normalize_asset_class(payload.asset_class),
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
        new={
            "version_number": script.version_number,
            "asset_class": script.asset_class,
            "status": script.status,
        },
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
            ProspectingScriptVersion.asset_class == normalize_asset_class(script.asset_class),
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
        new={
            "status": script.status,
            "version_number": script.version_number,
            "asset_class": script.asset_class,
        },
        reason="Caller script approved for live queue use",
    )
    db.commit()
    return script_read(db, script)


def get_attempt_qualification(
    db: Session,
    principal: Principal,
    attempt_id: UUID,
) -> ProspectingQualificationChecklistRead | None:
    attempt = db.scalar(
        select(ProspectingAttempt).where(
            ProspectingAttempt.organization_id == principal.organization_id,
            ProspectingAttempt.id == attempt_id,
        )
    )
    if attempt is None:
        return None
    if attempt.caller_user_id != principal.user_id and not can_manage(principal):
        raise PermissionError(
            "Only the assigned caller or an acquisitions manager can view this checklist."
        )
    script = scoped_attempt_script(db, principal.organization_id, attempt)
    return qualification_checklist_read(db, attempt, script)


def autosave_attempt_qualification(
    db: Session,
    principal: Principal,
    attempt_id: UUID,
    question_key: str,
    payload: ProspectingQualificationAutosaveRequest,
) -> ProspectingQualificationChecklistItemRead | None:
    now = datetime.now(UTC)
    from app.services.prospecting_dialer import validate_native_attempt_write_lease

    validate_native_attempt_write_lease(
        db,
        principal,
        attempt_id,
        browser_session_id=payload.browser_session_id,
        lease_token=payload.lease_token,
        now=now,
    )
    attempt = db.scalar(
        select(ProspectingAttempt)
        .where(
            ProspectingAttempt.organization_id == principal.organization_id,
            ProspectingAttempt.id == attempt_id,
        )
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if attempt is None:
        return None
    if attempt.caller_user_id != principal.user_id:
        raise PermissionError("Only the assigned caller can update this checklist.")
    if attempt.status != "in_progress":
        raise ProspectingQualificationConflictError(
            "Qualification answers can only be changed while the attempt is active."
        )

    script = scoped_attempt_script(db, principal.organization_id, attempt)
    question_by_key = {question.key: question for question in script_questions(script)}
    question = question_by_key.get(question_key)
    if question is None:
        raise ValueError("The question is not part of this attempt's pinned script.")
    answer_value = normalize_qualification_answer(question, payload.state, payload.answer_value)
    mutation_hash = qualification_mutation_hash(
        state=payload.state,
        answer_value=answer_value,
        expected_revision=payload.expected_revision,
    )
    response = db.scalar(
        select(ProspectingQualificationResponse)
        .where(
            ProspectingQualificationResponse.attempt_id == attempt.id,
            ProspectingQualificationResponse.question_key == question.key,
        )
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if response is not None and (
        response.organization_id != principal.organization_id
        or response.script_version_id != script.id
    ):
        raise ValueError("The saved qualification response does not match this attempt.")
    metadata = dict(response.response_metadata or {}) if response is not None else {}
    revision = qualification_revision(metadata)
    last_mutation_id = str(metadata.get("last_mutation_id") or "")
    mutation_id = str(payload.mutation_id)
    if last_mutation_id == mutation_id:
        if metadata.get("last_mutation_hash") != mutation_hash:
            raise ProspectingQualificationConflictError(
                "This mutation ID was already used with different qualification data."
            )
        assert response is not None
        return qualification_item_read(question, response=response, fallback_value=None)
    if payload.expected_revision != revision:
        raise ProspectingQualificationConflictError(
            "Qualification answer revision changed "
            f"(expected {payload.expected_revision}, current {revision})."
        )

    previous = qualification_response_snapshot(response)
    if response is None:
        response = ProspectingQualificationResponse(
            organization_id=principal.organization_id,
            attempt_id=attempt.id,
            script_version_id=script.id,
            question_key=question.key,
            state=payload.state,
            answer_value=answer_value,
            source="va_entry",
            actor_user_id=principal.user_id,
            is_required=question.required_for_handoff,
            captured_at=None if payload.state == "not_covered" else now,
            transcript_evidence=None,
            response_metadata={},
        )
        db.add(response)
    else:
        response.state = payload.state
        response.answer_value = answer_value
        response.source = "va_entry"
        response.actor_user_id = principal.user_id
        response.is_required = question.required_for_handoff
        if response.captured_at is None and payload.state != "not_covered":
            response.captured_at = now
    response.response_metadata = {
        **metadata,
        "revision": revision + 1,
        "last_mutation_id": mutation_id,
        "last_mutation_hash": mutation_hash,
    }
    answers = dict(attempt.qualification_answers or {})
    if payload.state == "answered" and answer_value:
        answers[question.key] = answer_value
    else:
        answers.pop(question.key, None)
    attempt.qualification_answers = answers
    required_keys = {item.key for item in question_by_key.values() if item.required_for_handoff}
    attempt.required_answer_count = len(required_keys)
    attempt.answered_required_count = sum(bool(answers.get(key)) for key in required_keys)
    attempt.quality_score_basis_points = rate_basis_points(
        attempt.answered_required_count,
        attempt.required_answer_count,
    )
    db.flush()
    add_audit(
        db,
        principal,
        action="prospecting.qualification_response_saved",
        entity_type="prospecting_qualification_response",
        entity_id=response.id,
        previous=previous,
        new=qualification_response_snapshot(response) or {},
        reason="Caller qualification checklist response autosaved",
    )
    db.commit()
    db.refresh(response)
    return qualification_item_read(question, response=response, fallback_value=None)


def start_attempt(
    db: Session,
    principal: Principal,
    entry_id: UUID,
) -> ProspectingEntryRead | None:
    entry = scoped_entry(db, principal, entry_id)
    if entry is None:
        return None
    if entry.assigned_user_id != principal.user_id:
        raise PermissionError("Only the assigned caller can start this prospecting attempt.")
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
    script = get_active_script(db, principal.organization_id, prospect.asset_class)
    if script is None:
        raise ValueError("An owner must approve a caller script before prospecting begins.")
    batch = db.get(ProspectCallingBatch, entry.prospect_calling_batch_id)
    if batch is None:
        raise ValueError("The prospect calling batch is unavailable.")
    now = datetime.now(UTC)
    attempt = ProspectingAttempt(
        organization_id=principal.organization_id,
        batch_entry_id=entry.id,
        prospect_id=prospect.id,
        caller_user_id=principal.user_id,
        script_version_id=script.id,
        call_record_id=None,
        cohort_id=batch.cohort_id,
        status="in_progress",
        outcome=None,
        contact_made=None,
        dialer_mode=batch.dialer_mode,
        answer_classification="unknown",
        party_classification="unknown",
        interest_classification="not_assessed",
        follow_up_permission="not_recorded",
        classification_source="manual_outcome",
        dial_started_at=now,
        answered_at=None,
        right_party_confirmed_at=None,
        interest_confirmed_at=None,
        measurement_metadata={},
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
    now = datetime.now(UTC)
    completion_fingerprint = completion_payload_fingerprint(payload)
    from app.services.prospecting_dialer import (
        complete_native_wrap_up,
        validate_native_attempt_can_complete,
        validate_native_attempt_terminal,
    )

    native_session, native_attempt = validate_native_attempt_can_complete(
        db,
        principal,
        attempt_id,
        browser_session_id=payload.browser_session_id,
        lease_token=payload.lease_token,
        now=now,
    )
    attempt = db.scalar(
        select(ProspectingAttempt)
        .where(
            ProspectingAttempt.organization_id == principal.organization_id,
            ProspectingAttempt.id == attempt_id,
        )
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if attempt is None:
        return None
    if attempt.caller_user_id != principal.user_id:
        raise PermissionError("Only the caller who started this attempt can complete it.")
    if attempt.status != "in_progress":
        return replayed_completion_entry(
            db,
            principal,
            attempt,
            payload,
            completion_fingerprint=completion_fingerprint,
            native_attempt=native_attempt,
        )
    if native_attempt and native_session is None:
        raise ProspectingCompletionConflictError(
            "The native dialer lease changed before this disposition was saved."
        )
    if native_attempt and payload.idempotency_key is None:
        raise ValueError("Native dialer completion requires a stable idempotency key.")
    if not native_attempt and (
        payload.browser_session_id is not None or payload.lease_token is not None
    ):
        raise ValueError("Dialer lease credentials apply only to native dialer attempts.")
    native_leg = validate_native_attempt_terminal(
        db,
        principal.organization_id,
        attempt_id,
        native_attempt=native_attempt,
    )
    validate_native_seller_disposition(native_leg, payload.outcome)
    entry = db.scalar(
        select(ProspectCallingBatchEntry).where(
            ProspectCallingBatchEntry.organization_id == principal.organization_id,
            ProspectCallingBatchEntry.id == attempt.batch_entry_id,
        )
    )
    prospect = db.scalar(
        select(Prospect)
        .where(
            Prospect.organization_id == principal.organization_id,
            Prospect.id == attempt.prospect_id,
        )
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    script = scoped_attempt_script(db, principal.organization_id, attempt)
    if entry is None or prospect is None or script is None:
        raise ValueError("The prospecting record is incomplete.")
    questions = script_questions(script)
    question_by_key = {question.key: question for question in questions}
    legacy_answers = clean_answers(payload.qualification_answers) if not native_attempt else {}
    unknown = set(legacy_answers) - set(question_by_key)
    if unknown:
        raise ValueError(f"Unknown caller-script answers: {', '.join(sorted(unknown))}.")
    saved_responses = db.scalars(
        select(ProspectingQualificationResponse)
        .where(
            ProspectingQualificationResponse.attempt_id == attempt.id,
        )
        .with_for_update()
        .execution_options(populate_existing=True)
    ).all()
    if any(
        response.organization_id != principal.organization_id
        or response.script_version_id != script.id
        or response.question_key not in question_by_key
        for response in saved_responses
    ):
        raise ValueError("Saved qualification evidence does not match the pinned caller script.")
    saved_by_key = {response.question_key: response for response in saved_responses}
    materialized_responses: list[ProspectingQualificationResponse] = []
    for key, value in legacy_answers.items():
        if key not in saved_by_key:
            question = question_by_key[key]
            normalized_value = normalize_qualification_answer(question, "answered", value)
            response = ProspectingQualificationResponse(
                organization_id=principal.organization_id,
                attempt_id=attempt.id,
                script_version_id=script.id,
                question_key=question.key,
                state="answered",
                answer_value=normalized_value,
                source="legacy_completion",
                actor_user_id=principal.user_id,
                is_required=question.required_for_handoff,
                captured_at=now,
                transcript_evidence=None,
                response_metadata={
                    "revision": 1,
                    "materialized_during_completion": True,
                },
            )
            db.add(response)
            saved_by_key[key] = response
            materialized_responses.append(response)
    if materialized_responses:
        db.flush()
        for response in materialized_responses:
            add_audit(
                db,
                principal,
                action="prospecting.qualification_response_materialized",
                entity_type="prospecting_qualification_response",
                entity_id=response.id,
                previous=None,
                new=qualification_response_snapshot(response) or {},
                reason="Legacy completion answer materialized before attempt completion",
            )
    answers: dict[str, str] = {}
    for question in questions:
        saved_response = saved_by_key.get(question.key)
        if saved_response is not None:
            if saved_response.state == "answered" and saved_response.answer_value is not None:
                saved_value = str(saved_response.answer_value).strip()
                if saved_value:
                    answers[question.key] = (
                        normalize_qualification_answer(
                            question,
                            "answered",
                            saved_value,
                        )
                        or ""
                    )
            continue
    required_keys = {question.key for question in questions if question.required_for_handoff}
    answered_required = sum(bool(answers.get(key)) for key in required_keys)
    if payload.outcome in WARM_OUTCOMES:
        missing = sorted(key for key in required_keys if not answers.get(key))
        if missing:
            raise ValueError(
                "Complete every required warm-handoff question: " + ", ".join(missing) + "."
            )
        has_address = all(
            (prospect.street_address, prospect.city, prospect.state_code, prospect.postal_code)
        )
        parcel_id, county, _ = prospect_property_metadata(prospect)
        has_land_parcel_identity = bool(
            normalize_asset_class(prospect.asset_class) == LAND_ASSET_CLASS
            and parcel_id
            and county
            and prospect.state_code
        )
        if not has_address and not has_land_parcel_identity:
            if normalize_asset_class(prospect.asset_class) == LAND_ASSET_CLASS:
                raise ValueError(
                    "A Land warm handoff requires a complete address or APN with county and state."
                )
            raise ValueError("A complete property address is required before a warm handoff.")
        validate_acquisition_user(db, principal.organization_id, payload.handoff_user_id)
    callback_at = as_utc(payload.callback_at) if payload.callback_at else None
    if payload.outcome in CALLBACK_OUTCOMES and callback_at is None:
        raise ValueError("Callback and follow-up outcomes require a callback date and time.")
    if callback_at and callback_at <= now:
        raise ValueError("Schedule callbacks in the future.")
    appointment_start_at = (
        as_utc(payload.appointment_start_at) if payload.appointment_start_at else None
    )
    if appointment_start_at is not None and appointment_start_at <= now:
        raise ValueError("Schedule appointments in the future.")
    seller_attempt_number = completed_seller_attempt_count(db, attempt.batch_entry_id) + 1
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
    if native_leg is not None:
        attempt.dial_started_at = (
            attempt.dial_started_at or native_leg.dialing_at or native_leg.queued_at
        )
        attempt.answered_at = (
            attempt.answered_at or native_leg.answered_at or native_leg.connected_at
        )
    apply_outcome_measurement(
        attempt,
        outcome=payload.outcome,
        completed_at=now,
        provider_evidence=native_leg is not None,
    )
    attempt.measurement_metadata = {
        **dict(attempt.measurement_metadata),
        **(
            {
                "provider_terminal": provider_terminal_receipt(native_leg),
            }
            if native_leg is not None
            else {}
        ),
        "completion_receipt": completion_receipt(
            payload,
            completion_fingerprint=completion_fingerprint,
            native_attempt=native_attempt,
            completed_at=now,
        ),
    }
    entry.attempt_count += 1
    entry.disposition = payload.outcome
    entry.last_attempt_at = now
    entry.next_attempt_at = None
    entry.completed_at = None
    if attempt.contact_made:
        prospect.last_contacted_at = now

    if payload.outcome in {"no_answer", "left_voicemail"}:
        apply_retry_cadence(
            attempt,
            entry,
            prospect,
            script,
            outcome=payload.outcome,
            seller_attempt_number=seller_attempt_number,
            now=now,
        )
    elif payload.outcome in CALLBACK_OUTCOMES:
        entry.status = "queued"
        entry.next_attempt_at = callback_at
        attempt.measurement_metadata = {
            **dict(attempt.measurement_metadata),
            "callback_schedule": {
                "requested_at": now.isoformat(),
                "callback_at": callback_at.isoformat() if callback_at else None,
                "priority": "due_callback_before_retry_or_new",
            },
        }
    elif payload.outcome in WARM_OUTCOMES:
        create_warm_handoff(
            db,
            principal,
            attempt,
            entry,
            prospect,
            payload,
            answers,
            now,
            connected_phone=dialed_phone(native_leg, prospect),
        )
    else:
        entry.status = "completed"
        entry.completed_at = now
        prospect.status = payload.outcome
        if payload.outcome == "wrong_number":
            apply_wrong_number_disposition(
                db,
                principal,
                attempt,
                entry,
                prospect,
                native_leg=native_leg,
                now=now,
            )
        elif payload.outcome == "do_not_call":
            prospect.call_eligibility = "blocked"
            prospect.suppression_status = "suppressed"
            record_dnc_suppression(
                db,
                principal,
                prospect,
                now,
                attempted_phone=dialed_phone(native_leg, prospect),
                attempt_id=attempt.id,
                contact_point_id=native_leg.contact_point_id if native_leg else None,
            )

    # The coordinator's reservation query runs in this transaction and must see the
    # completed attempt before it can immediately select a ranked fallback number.
    db.flush()
    complete_native_wrap_up(
        db,
        principal,
        attempt,
        session=native_session,
        now=now,
    )

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
    from app.services.prospecting_copilot import ensure_call_quality_review

    ensure_call_quality_review(db, principal, attempt, payload.compliance_flags)
    if attempt.call_record_id is not None:
        from app.services.call_intelligence import (
            enqueue_eligible_prospecting_call_transcript,
        )

        recording = select_preferred_call_recording(
            db,
            organization_id=attempt.organization_id,
            call_record_id=attempt.call_record_id,
        )
        if recording is not None:
            enqueue_eligible_prospecting_call_transcript(
                db,
                recording,
                model_name=get_settings().openai_transcription_model,
            )
    refresh_batch_status(db, entry.prospect_calling_batch_id)
    db.commit()
    return entry_read(db, entry)


def complete_technical_failure(
    db: Session,
    principal: Principal,
    attempt_id: UUID,
    payload: ProspectingTechnicalFailureComplete,
) -> ProspectingEntryRead | None:
    """Close failed provider work without manufacturing a seller disposition."""

    from app.services.prospecting_dialer import (
        ProspectingDialerConfigurationError,
        complete_native_wrap_up,
        validate_native_attempt_can_complete,
        validate_native_attempt_terminal,
    )

    now = datetime.now(UTC)
    native_session, native_attempt = validate_native_attempt_can_complete(
        db,
        principal,
        attempt_id,
        browser_session_id=payload.browser_session_id,
        lease_token=payload.lease_token,
        now=now,
    )
    attempt = db.scalar(
        select(ProspectingAttempt)
        .where(
            ProspectingAttempt.organization_id == principal.organization_id,
            ProspectingAttempt.id == attempt_id,
        )
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if attempt is None:
        return None
    if attempt.caller_user_id != principal.user_id:
        raise PermissionError("Only the caller who started this attempt can resolve it.")
    if attempt.status != "in_progress":
        if attempt.status == "completed" and attempt.outcome == "technical_failure":
            validate_technical_failure_receipt(
                attempt,
                idempotency_key=payload.idempotency_key,
                browser_session_id=payload.browser_session_id,
                lease_token=payload.lease_token,
            )
            entry = scoped_attempt_entry(db, principal.organization_id, attempt)
            return entry_read(db, entry)
        raise ProspectingCompletionConflictError(
            "This attempt already has a different final disposition."
        )
    if not native_attempt or native_session is None:
        raise ProspectingDialerConfigurationError(
            "Technical-failure completion is available only for the active native dialer call."
        )
    native_leg = validate_native_attempt_terminal(
        db,
        principal.organization_id,
        attempt.id,
        native_attempt=True,
    )
    if native_leg is None or native_leg.status not in {"failed", "cancelled"}:
        raise ValueError(
            "Only a failed or cancelled provider call can be resolved as a technical failure."
        )
    entry = scoped_attempt_entry(db, principal.organization_id, attempt, lock=True)
    prospect = db.scalar(
        select(Prospect)
        .where(
            Prospect.organization_id == principal.organization_id,
            Prospect.id == attempt.prospect_id,
        )
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    script = scoped_attempt_script(db, principal.organization_id, attempt)
    if prospect is None or script is None:
        raise ValueError("The prospecting record is incomplete.")

    delay_minutes = disposition_rule_int(
        script,
        "technical_failure_retry_delay_minutes",
        default=15,
        minimum=1,
        maximum=24 * 60,
    )
    next_attempt_at = now + timedelta(minutes=delay_minutes)
    attempt.status = "completed"
    attempt.outcome = "technical_failure"
    attempt.contact_made = False
    attempt.notes = clean_text(native_leg.provider_error_message) or "Provider call failed."
    attempt.callback_at = None
    attempt.completed_at = now
    attempt.answer_classification = "unknown"
    attempt.party_classification = "unknown"
    attempt.interest_classification = "not_assessed"
    attempt.follow_up_permission = "not_recorded"
    attempt.classification_source = "provider_terminal"
    attempt.measurement_metadata = {
        **dict(attempt.measurement_metadata),
        "provider_terminal": {
            **provider_terminal_receipt(native_leg),
            "seller_disposition_recorded": False,
        },
        "cadence": {
            "outcome": "technical_failure",
            "delay_seconds": delay_minutes * 60,
            "next_attempt_at": next_attempt_at.isoformat(),
            "consumes_seller_attempt": False,
            "exhausted": False,
            "script_version_id": str(script.id),
            "script_version_number": script.version_number,
        },
        "completion_receipt": {
            "kind": "technical_failure",
            "idempotency_key": payload.idempotency_key,
            "payload_sha256": technical_failure_payload_fingerprint(attempt.id),
            "browser_session_id": payload.browser_session_id,
            "lease_token_sha256": token_sha256(payload.lease_token),
            "completed_at": now.isoformat(),
        },
    }
    entry.disposition = "technical_failure"
    entry.last_attempt_at = now
    entry.next_attempt_at = next_attempt_at
    entry.completed_at = None
    entry.status = "queued"

    complete_native_wrap_up(db, principal, attempt, session=native_session, now=now)
    add_audit(
        db,
        principal,
        action="prospecting.attempt_technical_failure_completed",
        entity_type="prospecting_attempt",
        entity_id=attempt.id,
        previous={"status": "in_progress"},
        new={
            "status": "completed",
            "outcome": "technical_failure",
            "provider_status": native_leg.status,
            "entry_status": entry.status,
            "next_attempt_at": next_attempt_at.isoformat(),
        },
        reason="Provider failure preserved without creating a seller disposition",
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
        select(ProspectHandoff)
        .where(
            ProspectHandoff.organization_id == principal.organization_id,
            ProspectHandoff.id == handoff_id,
        )
        .with_for_update()
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
    lead = db.scalar(
        select(Lead)
        .where(
            Lead.organization_id == principal.organization_id,
            Lead.id == handoff.lead_id,
        )
        .execution_options(populate_existing=True)
        .with_for_update()
    )
    prospect = db.get(Prospect, handoff.prospect_id)
    if entry is None or lead is None or prospect is None:
        raise ValueError("The handoff record is incomplete.")
    require_lead_open_for_work(lead)
    now = datetime.now(UTC)
    attempt = db.get(ProspectingAttempt, handoff.attempt_id)
    decision_code = payload.reason_code or default_handoff_decision_code(
        payload.decision,
        attempt.outcome if attempt else None,
    )
    if payload.decision == "accepted" and (
        attempt is None or not has_accepted_warm_evidence(attempt)
    ):
        raise ValueError(
            "This handoff lacks the required right-party, interest, permission, "
            "or qualification evidence."
        )
    handoff.status = payload.decision
    handoff.reviewed_by_user_id = principal.user_id
    handoff.reviewed_at = now
    handoff.decision_code = decision_code
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
    elif payload.decision == "needs_correction":
        lead.stage_key = "qualification_in_progress"
        entry.status = "needs_correction"
        entry.completed_at = None
        prospect.status = "handoff_correction"
    else:
        result = apply_lead_close_out_transition(
            db,
            principal,
            lead.id,
            LeadCloseOutRequest(
                disposition="disqualified",
                reason=(f"Prospecting handoff rejected ({decision_code}): {handoff.review_reason}")[
                    :500
                ],
            ),
            commit=False,
        )
        if result is None:
            raise ValueError("The handoff's seller lead is no longer available.")
        handoff.status = payload.decision
        handoff.reviewed_by_user_id = principal.user_id
        handoff.reviewed_at = now
        handoff.decision_code = decision_code
        handoff.review_reason = clean_text(payload.reason)
        entry.status = "completed"
        entry.completed_at = now
        prospect.status = "handoff_rejected"
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
            else (
                "Handoff needs correction"
                if payload.decision == "needs_correction"
                else "Warm handoff rejected"
            )
        ),
        body=(
            "The acquisitions team accepted the seller handoff."
            if payload.decision == "accepted"
            else (
                f"Review requested: {handoff.review_reason}"
                if payload.decision == "needs_correction"
                else f"Rejected: {handoff.review_reason}"
            )
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
        new={
            "status": handoff.status,
            "decision_code": handoff.decision_code,
            "reason": handoff.review_reason,
        },
        reason="Acquisitions reviewed the VA warm-lead handoff",
    )
    if attempt is not None:
        from app.services.prospecting_copilot import ensure_call_quality_review

        ensure_call_quality_review(db, principal, attempt, [])
        if payload.decision == "accepted":
            from app.services.call_intelligence import (
                link_accepted_prospecting_evidence_for_attempt,
            )

            db.flush()
            link_accepted_prospecting_evidence_for_attempt(db, attempt.id)
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
    *,
    connected_phone: str | None,
) -> None:
    assert payload.handoff_user_id is not None
    lead = convert_prospect_to_lead(
        db,
        principal,
        prospect,
        payload.handoff_user_id,
        answers,
        connected_phone=connected_phone,
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
        decision_code=None,
        review_reason=None,
    )
    db.add(handoff)
    entry.status = "handoff_pending"
    prospect.status = "warm_handoff"
    if payload.outcome == "appointment_set" and payload.appointment_start_at:
        create_handoff_appointment(db, lead, attempt.id, payload, now)
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
    *,
    connected_phone: str | None,
) -> Lead:
    locked_prospect = db.scalar(
        select(Prospect)
        .where(
            Prospect.organization_id == principal.organization_id,
            Prospect.id == prospect.id,
        )
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if locked_prospect is None:
        raise ValueError("The prospect is no longer available for handoff.")
    prospect = locked_prospect
    if prospect.converted_lead_id:
        existing = db.scalar(
            select(Lead)
            .where(
                Lead.organization_id == principal.organization_id,
                Lead.id == prospect.converted_lead_id,
            )
            .execution_options(populate_existing=True)
            .with_for_update()
        )
        if existing is None:
            raise ValueError("The prospect points to a missing CRM lead.")
        require_lead_open_for_work(existing)
        existing.assigned_user_id = assigned_user_id
        update_lead_qualification(existing, answers)
        sync_contact_phone_methods(
            db,
            organization_id=principal.organization_id,
            contact_id=existing.contact_id,
            connected_phone=connected_phone,
            fallback_phone=prospect.phone or prospect.normalized_phone,
        )
        conversation = ensure_primary_conversation(db, existing, queue_key="qualified")
        conversation.assigned_user_id = assigned_user_id
        conversation.queue_key = "qualified"
        add_automatic_owner_watchers(db, conversation)
        return existing
    street_address = prospect.street_address or ""
    city = prospect.city or ""
    state_code = prospect.state_code or ""
    postal_code = prospect.postal_code or ""
    asset_class = normalize_asset_class(prospect.asset_class)
    parcel_id, county, source_property_type = prospect_property_metadata(prospect)
    has_address = all((street_address, city, state_code, postal_code))
    has_parcel_identity = bool(parcel_id and county and state_code)
    if asset_class == LAND_ASSET_CLASS and not (has_address or has_parcel_identity):
        raise ValueError(
            "A Land warm handoff requires a complete address or APN with county and state."
        )
    if asset_class != LAND_ASSET_CLASS and not has_address:
        raise ValueError("A complete property address is required before a warm handoff.")
    contact = Contact(
        organization_id=principal.organization_id,
        legal_name=prospect.legal_name,
        preferred_name=None,
        contact_type="seller",
        assigned_user_id=assigned_user_id,
    )
    db.add(contact)
    db.flush()
    has_phone = sync_contact_phone_methods(
        db,
        organization_id=principal.organization_id,
        contact_id=contact.id,
        connected_phone=connected_phone,
        fallback_phone=prospect.phone or prospect.normalized_phone,
    )
    if prospect.email and prospect.normalized_email:
        db.add(
            ContactMethod(
                organization_id=principal.organization_id,
                contact_id=contact.id,
                method_type="email",
                value=prospect.email,
                normalized_value=prospect.normalized_email,
                is_primary=not has_phone,
            )
        )
    property_type = source_property_type or (
        LAND_ASSET_CLASS if asset_class == LAND_ASSET_CLASS else None
    )
    property_record, normalized_property_key, normalized_parcel_key = find_property_by_identity(
        db,
        organization_id=principal.organization_id,
        street_address=street_address,
        city=city,
        state=state_code,
        postal_code=postal_code,
        parcel_id=parcel_id,
        county=county,
    )
    if property_record is None:
        property_record = Property(
            organization_id=principal.organization_id,
            street_address=street_address,
            city=city,
            state=state_code,
            postal_code=postal_code,
            county=county,
            property_type=property_type,
            parcel_id=parcel_id,
            normalized_parcel_key=normalized_parcel_key,
            normalized_address_key=normalized_property_key,
            address_validation_status=prospect.address_validation_status,
        )
        db.add(property_record)
        db.flush()
    else:
        if parcel_id and not property_record.parcel_id:
            property_record.parcel_id = parcel_id
        if county and not property_record.county:
            property_record.county = county
        if property_type and not property_record.property_type:
            property_record.property_type = property_type
        refresh_property_identity_keys(property_record)
    require_valid_property_identity(property_record, asset_class=asset_class)
    campaign = db.get(Campaign, prospect.campaign_id)
    lead = Lead(
        organization_id=principal.organization_id,
        contact_id=contact.id,
        property_id=property_record.id,
        assigned_user_id=assigned_user_id,
        source="cold_call",
        asset_class=asset_class,
        qualification_context={},
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
    from app.services.ai_operations import enqueue_lead_created_ai_work

    enqueue_lead_created_ai_work(db, lead, source="prospecting_handoff")
    from app.services.property_intelligence import enqueue_property_research

    enqueue_property_research(
        db,
        property_record,
        source_lead_id=lead.id,
        trigger_source="prospecting_handoff",
    )
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
        "asset_class": asset_class,
        "unified_timeline": True,
    }
    add_automatic_owner_watchers(db, conversation)
    return lead


def create_handoff_appointment(
    db: Session,
    lead: Lead,
    attempt_id: UUID,
    payload: ProspectingAttemptComplete,
    now: datetime,
) -> None:
    assert payload.appointment_start_at is not None
    appointment_start_at = as_utc(payload.appointment_start_at)
    location_type = payload.appointment_location_type or "seller_property"
    location = clean_text(payload.appointment_location)
    if location_type == "seller_property" and location is None:
        property_record = db.scalar(
            select(Property).where(
                Property.organization_id == lead.organization_id,
                Property.id == lead.property_id,
            )
        )
        if property_record is None:
            raise ValueError("The seller property's appointment address is unavailable.")
        address_parts = (
            property_record.street_address,
            property_record.city,
            property_record.state,
            property_record.postal_code,
        )
        if not all(clean_text(part) for part in address_parts):
            raise ValueError(
                "Seller-property appointments require a complete property address or "
                "an explicit location."
            )
        location = (
            f"{property_record.street_address}, {property_record.city}, "
            f"{property_record.state} {property_record.postal_code}"
        )
    existing = db.scalar(
        select(Appointment).where(
            Appointment.organization_id == lead.organization_id,
            Appointment.prospecting_attempt_id == attempt_id,
        )
    )
    if existing:
        return
    appointment = Appointment(
        organization_id=lead.organization_id,
        lead_id=lead.id,
        contact_id=lead.contact_id,
        property_id=lead.property_id,
        prospecting_attempt_id=attempt_id,
        owner_user_id=lead.assigned_user_id,
        appointment_type="acquisition_consultation",
        status="scheduled",
        scheduled_start_at=appointment_start_at,
        scheduled_end_at=appointment_start_at + timedelta(hours=1),
        location_type=location_type,
        location=location,
        notes=clean_text(payload.notes),
        outcome=None,
        external_calendar_id=None,
        appointment_metadata={"source": "va_handoff", "calendar_synced": False},
    )
    db.add(appointment)
    db.flush()
    from app.services.marketing import enqueue_meta_schedule_conversion

    enqueue_meta_schedule_conversion(db, appointment=appointment, lead=lead)
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
            summary=(f"Seller appointment scheduled for {appointment_start_at.isoformat()}."),
        )
    )


def update_lead_qualification(lead: Lead, answers: dict[str, str]) -> None:
    lead.motivation = answers.get("motivation") or lead.motivation
    lead.desired_timeline = answers.get("timeline") or lead.desired_timeline
    lead.property_condition = answers.get("property_condition") or lead.property_condition
    lead.occupancy_status = answers.get("occupancy") or lead.occupancy_status
    lead.asking_price = answers.get("asking_price") or lead.asking_price
    lead.mortgage_balance = answers.get("mortgage_balance") or lead.mortgage_balance


def completion_payload_fingerprint(payload: ProspectingAttemptComplete) -> str:
    canonical = json.dumps(
        payload.model_dump(
            mode="json",
            exclude={"browser_session_id", "lease_token", "idempotency_key"},
        ),
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def technical_failure_payload_fingerprint(attempt_id: UUID) -> str:
    canonical = json.dumps(
        {"attempt_id": str(attempt_id), "kind": "technical_failure"},
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def token_sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def completion_receipt(
    payload: ProspectingAttemptComplete,
    *,
    completion_fingerprint: str,
    native_attempt: bool,
    completed_at: datetime,
) -> dict[str, object]:
    receipt: dict[str, object] = {
        "kind": "seller_disposition",
        "idempotency_key": payload.idempotency_key,
        "payload_sha256": completion_fingerprint,
        "completed_at": completed_at.isoformat(),
    }
    if native_attempt:
        assert payload.browser_session_id is not None
        assert payload.lease_token is not None
        receipt.update(
            {
                "browser_session_id": payload.browser_session_id,
                "lease_token_sha256": token_sha256(payload.lease_token),
            }
        )
    return receipt


def completion_receipt_for_attempt(attempt: ProspectingAttempt) -> Mapping[str, object]:
    receipt = (attempt.measurement_metadata or {}).get("completion_receipt")
    if not isinstance(receipt, Mapping):
        raise ProspectingCompletionConflictError(
            "This attempt was already finalized without a replay receipt."
        )
    return receipt


def validate_completion_lease_receipt(
    receipt: Mapping[str, object],
    *,
    browser_session_id: str | None,
    lease_token: str | None,
) -> None:
    stored_browser = receipt.get("browser_session_id")
    stored_lease_digest = receipt.get("lease_token_sha256")
    if (
        not isinstance(stored_browser, str)
        or not isinstance(stored_lease_digest, str)
        or browser_session_id is None
        or lease_token is None
        or not secrets.compare_digest(stored_browser, browser_session_id)
        or not secrets.compare_digest(stored_lease_digest, token_sha256(lease_token))
    ):
        raise ProspectingCompletionConflictError(
            "The original dialer lease is required to replay this completion."
        )


def replayed_completion_entry(
    db: Session,
    principal: Principal,
    attempt: ProspectingAttempt,
    payload: ProspectingAttemptComplete,
    *,
    completion_fingerprint: str,
    native_attempt: bool,
) -> ProspectingEntryRead:
    if attempt.status != "completed":
        raise ProspectingCompletionConflictError("This attempt cannot be completed again.")
    receipt = completion_receipt_for_attempt(attempt)
    if receipt.get("kind") != "seller_disposition":
        raise ProspectingCompletionConflictError(
            "This attempt already has a different final completion type."
        )
    stored_key = receipt.get("idempotency_key")
    if stored_key != payload.idempotency_key:
        raise ProspectingCompletionConflictError(
            "This completion idempotency key does not match the original request."
        )
    stored_fingerprint = receipt.get("payload_sha256")
    if not isinstance(stored_fingerprint, str) or not secrets.compare_digest(
        stored_fingerprint,
        completion_fingerprint,
    ):
        raise ProspectingCompletionConflictError(
            "This completion payload does not match the original request."
        )
    if native_attempt:
        validate_completion_lease_receipt(
            receipt,
            browser_session_id=payload.browser_session_id,
            lease_token=payload.lease_token,
        )
    elif payload.browser_session_id is not None or payload.lease_token is not None:
        raise ProspectingCompletionConflictError(
            "Dialer lease credentials do not belong to this manual attempt."
        )
    entry = scoped_attempt_entry(db, principal.organization_id, attempt, lock=True)
    return entry_read(db, entry)


def validate_technical_failure_receipt(
    attempt: ProspectingAttempt,
    *,
    idempotency_key: str,
    browser_session_id: str,
    lease_token: str,
) -> None:
    receipt = completion_receipt_for_attempt(attempt)
    if receipt.get("kind") != "technical_failure":
        raise ProspectingCompletionConflictError(
            "This attempt already has a different final completion type."
        )
    if receipt.get("idempotency_key") != idempotency_key:
        raise ProspectingCompletionConflictError(
            "This technical-failure idempotency key does not match the original request."
        )
    expected_fingerprint = technical_failure_payload_fingerprint(attempt.id)
    stored_fingerprint = receipt.get("payload_sha256")
    if not isinstance(stored_fingerprint, str) or not secrets.compare_digest(
        stored_fingerprint,
        expected_fingerprint,
    ):
        raise ProspectingCompletionConflictError("The stored technical-failure receipt is invalid.")
    validate_completion_lease_receipt(
        receipt,
        browser_session_id=browser_session_id,
        lease_token=lease_token,
    )


def scoped_attempt_entry(
    db: Session,
    organization_id: UUID,
    attempt: ProspectingAttempt,
    *,
    lock: bool = False,
) -> ProspectCallingBatchEntry:
    statement = select(ProspectCallingBatchEntry).where(
        ProspectCallingBatchEntry.organization_id == organization_id,
        ProspectCallingBatchEntry.id == attempt.batch_entry_id,
    )
    if lock:
        statement = statement.with_for_update().execution_options(populate_existing=True)
    entry = db.scalar(statement)
    if entry is None:
        raise ValueError("The prospecting queue entry is unavailable.")
    return entry


def validate_native_seller_disposition(
    leg: ProspectingDialLeg | None,
    outcome: str,
) -> None:
    if leg is None:
        return
    if leg.status in {"failed", "cancelled"}:
        raise ValueError(
            "The provider call failed before a seller outcome was known. "
            "Use Resolve technical failure."
        )
    if leg.status in {"no_answer", "busy"}:
        if outcome != "no_answer":
            raise ValueError("Provider no-answer evidence can only be saved as No answer.")
        return
    if leg.status != "completed":
        raise ValueError("The provider call has no compatible terminal result.")
    if outcome == "no_answer":
        raise ValueError("A completed provider call cannot be saved as No answer.")
    if outcome in CONTACT_OUTCOMES | {"wrong_number"} and leg.connected_at is None:
        raise ValueError(
            "A seller-contact disposition requires provider evidence that the call connected."
        )


def provider_terminal_receipt(leg: ProspectingDialLeg) -> dict[str, object | None]:
    def serialized(value: datetime | None) -> str | None:
        return as_utc(value).isoformat() if value is not None else None

    return {
        "dial_leg_id": str(leg.id),
        "contact_point_id": str(leg.contact_point_id) if leg.contact_point_id else None,
        "recipient": leg.recipient,
        "provider": leg.provider,
        "provider_call_id": leg.provider_call_id,
        "status": leg.status,
        "terminal_result": leg.terminal_result,
        "provider_error_code": leg.provider_error_code,
        "queued_at": serialized(leg.queued_at),
        "dialing_at": serialized(leg.dialing_at),
        "ringing_at": serialized(leg.ringing_at),
        "answered_at": serialized(leg.answered_at),
        "connected_at": serialized(leg.connected_at),
        "completed_at": serialized(leg.completed_at),
        "last_provider_event_at": serialized(leg.last_provider_event_at),
    }


def completed_seller_attempt_count(db: Session, batch_entry_id: UUID) -> int:
    return int(
        db.scalar(
            select(func.count(ProspectingAttempt.id)).where(
                ProspectingAttempt.batch_entry_id == batch_entry_id,
                ProspectingAttempt.status == "completed",
                ProspectingAttempt.outcome.is_not(None),
                ProspectingAttempt.outcome != "technical_failure",
            )
        )
        or 0
    )


def disposition_rule_int(
    script: ProspectingScriptVersion,
    key: str,
    *,
    default: int,
    minimum: int,
    maximum: int,
) -> int:
    raw = (script.disposition_rules or {}).get(key, default)
    if isinstance(raw, bool) or not isinstance(raw, int) or not minimum <= raw <= maximum:
        raise ValueError(
            f"Caller-script disposition rule {key} must be an integer from "
            f"{minimum} through {maximum}."
        )
    return raw


def apply_retry_cadence(
    attempt: ProspectingAttempt,
    entry: ProspectCallingBatchEntry,
    prospect: Prospect,
    script: ProspectingScriptVersion,
    *,
    outcome: str,
    seller_attempt_number: int,
    now: datetime,
) -> None:
    maximum_attempts = disposition_rule_int(
        script,
        "maximum_seller_attempts",
        default=6,
        minimum=1,
        maximum=100,
    )
    delay_hours = disposition_rule_int(
        script,
        "no_answer_retry_delay_hours" if outcome == "no_answer" else "voicemail_retry_delay_hours",
        default=24 if outcome == "no_answer" else 48,
        minimum=1,
        maximum=24 * 30,
    )
    exhausted = seller_attempt_number >= maximum_attempts
    next_attempt_at = None if exhausted else now + timedelta(hours=delay_hours)
    if exhausted:
        entry.status = "completed"
        entry.completed_at = now
        prospect.status = "cadence_exhausted"
    else:
        entry.status = "queued"
        entry.next_attempt_at = next_attempt_at
        prospect.status = "ready"
    attempt.measurement_metadata = {
        **dict(attempt.measurement_metadata),
        "cadence": {
            "outcome": outcome,
            "seller_attempt_number": seller_attempt_number,
            "maximum_seller_attempts": maximum_attempts,
            "delay_seconds": delay_hours * 60 * 60,
            "next_attempt_at": next_attempt_at.isoformat() if next_attempt_at else None,
            "consumes_seller_attempt": True,
            "exhausted": exhausted,
            "script_version_id": str(script.id),
            "script_version_number": script.version_number,
        },
    }


def dialed_phone(leg: ProspectingDialLeg | None, prospect: Prospect) -> str | None:
    return format_e164(
        leg.recipient if leg is not None else (prospect.normalized_phone or prospect.phone)
    )


def sync_contact_phone_methods(
    db: Session,
    *,
    organization_id: UUID,
    contact_id: UUID,
    connected_phone: str | None,
    fallback_phone: str | None,
) -> bool:
    connected = format_e164(connected_phone)
    fallback = format_e164(fallback_phone)
    primary = connected or fallback
    if primary is None:
        return False
    desired = [primary]
    if fallback is not None and fallback != primary:
        desired.append(fallback)
    rows = list(
        db.scalars(
            select(ContactMethod).where(
                ContactMethod.organization_id == organization_id,
                ContactMethod.contact_id == contact_id,
                ContactMethod.method_type == "phone",
            )
        )
    )
    by_normalized = {
        format_e164(row.normalized_value or row.value): row
        for row in rows
        if format_e164(row.normalized_value or row.value) is not None
    }
    for normalized in desired:
        row = by_normalized.get(normalized)
        if row is None:
            row = ContactMethod(
                organization_id=organization_id,
                contact_id=contact_id,
                method_type="phone",
                value=normalized,
                normalized_value=normalized,
                is_primary=normalized == primary,
            )
            db.add(row)
            rows.append(row)
        else:
            row.is_primary = normalized == primary
    for row in rows:
        row_phone = format_e164(row.normalized_value or row.value)
        if row_phone != primary:
            row.is_primary = False
    return True


def upsert_phone_suppression(
    db: Session,
    principal: Principal,
    *,
    normalized_phone: str,
    reason: str,
    source: str,
    now: datetime,
    metadata: Mapping[str, object],
) -> SuppressionRecord:
    existing = db.scalar(
        select(SuppressionRecord)
        .where(
            SuppressionRecord.organization_id == principal.organization_id,
            SuppressionRecord.channel == "phone",
            SuppressionRecord.normalized_address == normalized_phone,
        )
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if existing is not None:
        existing.status = "active"
        existing.reason = reason
        existing.source = source
        existing.suppressed_at = now
        existing.lifted_at = None
        existing.suppression_metadata = {
            **(existing.suppression_metadata or {}),
            **metadata,
        }
        return existing
    record = SuppressionRecord(
        organization_id=principal.organization_id,
        contact_id=None,
        channel="phone",
        normalized_address=normalized_phone,
        status="active",
        reason=reason,
        source=source,
        provider=None,
        external_event_id=None,
        suppressed_at=now,
        lifted_at=None,
        suppression_metadata=dict(metadata),
    )
    db.add(record)
    return record


def apply_wrong_number_disposition(
    db: Session,
    principal: Principal,
    attempt: ProspectingAttempt,
    entry: ProspectCallingBatchEntry,
    prospect: Prospect,
    *,
    native_leg: ProspectingDialLeg | None,
    now: datetime,
) -> None:
    from app.services.prospecting_dialer import select_ranked_phone

    attempted_phone = dialed_phone(native_leg, prospect)
    if attempted_phone is None:
        raise ValueError("The attempted phone number is unavailable.")
    matching_points = list(
        db.scalars(
            select(ProspectContactPoint)
            .where(
                ProspectContactPoint.organization_id == principal.organization_id,
                ProspectContactPoint.prospect_id == prospect.id,
                ProspectContactPoint.contact_type == "phone",
            )
            .with_for_update()
            .execution_options(populate_existing=True)
        )
    )
    invalidated_ids: list[str] = []
    for point in matching_points:
        if format_e164(point.normalized_value or point.value) != attempted_phone:
            continue
        point.validation_status = "invalid"
        point.contact_metadata = {
            **(point.contact_metadata or {}),
            "wrong_number_at": now.isoformat(),
            "wrong_number_attempt_id": str(attempt.id),
        }
        invalidated_ids.append(str(point.id))
    if (
        native_leg is not None
        and native_leg.contact_point_id is not None
        and str(native_leg.contact_point_id) not in invalidated_ids
    ):
        raise ValueError("The dialed contact point does not match the provider recipient.")
    if format_e164(prospect.normalized_phone or prospect.phone) == attempted_phone:
        prospect.phone_validation_status = "invalid"
    upsert_phone_suppression(
        db,
        principal,
        normalized_phone=attempted_phone,
        reason="Confirmed wrong number",
        source="prospecting_wrong_number",
        now=now,
        metadata={
            "prospect_id": str(prospect.id),
            "attempt_id": str(attempt.id),
            "contact_point_id": (
                str(native_leg.contact_point_id)
                if native_leg is not None and native_leg.contact_point_id is not None
                else None
            ),
            "dial_leg_id": str(native_leg.id) if native_leg is not None else None,
        },
    )
    db.flush()
    fallback = select_ranked_phone(db, prospect)
    if fallback is None:
        entry.status = "completed"
        entry.completed_at = now
        entry.next_attempt_at = None
        prospect.status = "wrong_number"
        prospect.call_eligibility = "blocked"
    else:
        fallback_point, fallback_phone = fallback
        entry.status = "queued"
        entry.completed_at = None
        entry.next_attempt_at = now
        prospect.status = "ready"
        prospect.call_eligibility = "eligible"
        attempt.measurement_metadata = {
            **dict(attempt.measurement_metadata),
            "number_resolution": {
                "attempted_phone": attempted_phone,
                "invalidated_contact_point_ids": invalidated_ids,
                "fallback_contact_point_id": (
                    str(fallback_point.id) if fallback_point is not None else None
                ),
                "fallback_phone": fallback_phone,
                "retry_queued": True,
            },
        }
        return
    attempt.measurement_metadata = {
        **dict(attempt.measurement_metadata),
        "number_resolution": {
            "attempted_phone": attempted_phone,
            "invalidated_contact_point_ids": invalidated_ids,
            "fallback_contact_point_id": None,
            "fallback_phone": None,
            "retry_queued": False,
        },
    }


def record_dnc_suppression(
    db: Session,
    principal: Principal,
    prospect: Prospect,
    now: datetime,
    *,
    attempted_phone: str | None,
    attempt_id: UUID,
    contact_point_id: UUID | None,
) -> None:
    normalized_phone = format_e164(attempted_phone)
    if normalized_phone is None:
        return
    points = list(
        db.scalars(
            select(ProspectContactPoint)
            .where(
                ProspectContactPoint.organization_id == principal.organization_id,
                ProspectContactPoint.prospect_id == prospect.id,
                ProspectContactPoint.contact_type == "phone",
            )
            .with_for_update()
            .execution_options(populate_existing=True)
        )
    )
    for point in points:
        if format_e164(point.normalized_value or point.value) != normalized_phone:
            continue
        point.contact_metadata = {
            **(point.contact_metadata or {}),
            "source_dnc": True,
            "dnc_recorded_at": now.isoformat(),
            "dnc_attempt_id": str(attempt_id),
        }
    upsert_phone_suppression(
        db,
        principal,
        normalized_phone=normalized_phone,
        reason="Seller requested no further calls",
        source="prospecting_disposition",
        now=now,
        metadata={
            "prospect_id": str(prospect.id),
            "attempt_id": str(attempt_id),
            "contact_point_id": str(contact_point_id) if contact_point_id else None,
            "exact_dialed_number": normalized_phone,
        },
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
            case(
                (ProspectCallingBatchEntry.status == "needs_correction", 0),
                (ProspectCallingBatchEntry.next_attempt_at.is_not(None), 1),
                else_=2,
            ),
            ProspectCallingBatchEntry.next_attempt_at.asc().nulls_last(),
            ProspectCallingBatchEntry.sequence_number,
        )
    )
    return entry_read(db, entry) if entry else None


def list_queue_entries(
    db: Session,
    principal: Principal,
    *,
    manageable: bool,
) -> list[ProspectingEntryRead]:
    now = datetime.now(UTC)
    statement = (
        select(ProspectCallingBatchEntry)
        .join(
            ProspectCallingBatch,
            ProspectCallingBatch.id == ProspectCallingBatchEntry.prospect_calling_batch_id,
        )
        .join(Prospect, Prospect.id == ProspectCallingBatchEntry.prospect_id)
        .where(
            ProspectCallingBatchEntry.organization_id == principal.organization_id,
            ProspectCallingBatchEntry.status.in_(
                ("queued", "ready", "needs_correction", "in_progress", "handoff_pending")
            ),
        )
    )
    if not manageable:
        statement = statement.where(
            ProspectCallingBatchEntry.assigned_user_id == principal.user_id,
            ProspectCallingBatch.assigned_user_id == principal.user_id,
        )
    entries = db.scalars(
        statement.order_by(
            case(
                (ProspectCallingBatchEntry.status == "in_progress", 0),
                (ProspectCallingBatchEntry.status == "needs_correction", 1),
                (
                    ProspectCallingBatchEntry.next_attempt_at.is_not(None)
                    & (ProspectCallingBatchEntry.next_attempt_at <= now),
                    2,
                ),
                (ProspectCallingBatchEntry.status == "handoff_pending", 5),
                (ProspectCallingBatchEntry.next_attempt_at.is_(None), 3),
                else_=4,
            ),
            ProspectCallingBatchEntry.next_attempt_at.asc().nulls_first(),
            ProspectCallingBatchEntry.sequence_number,
        ).limit(250)
    ).all()
    if not entries:
        return []
    context = build_prospecting_read_context(db, entries)
    return [entry_read(db, entry, context=context) for entry in entries]


def build_prospecting_read_context(
    db: Session,
    entries: Sequence[ProspectCallingBatchEntry],
) -> ProspectingReadContext:
    """Bulk-load every relationship needed to serialize a bounded queue page."""

    organization_ids = {entry.organization_id for entry in entries}
    if len(organization_ids) != 1:
        raise ValueError("Prospecting queue entries must belong to one organization.")
    organization_id = next(iter(organization_ids))
    prospect_ids = {entry.prospect_id for entry in entries}
    batch_ids = {entry.prospect_calling_batch_id for entry in entries}
    entry_ids = {entry.id for entry in entries}

    prospects = db.scalars(
        select(Prospect).where(
            Prospect.organization_id == organization_id,
            Prospect.id.in_(prospect_ids),
        )
    ).all()
    batches = db.scalars(
        select(ProspectCallingBatch).where(
            ProspectCallingBatch.organization_id == organization_id,
            ProspectCallingBatch.id.in_(batch_ids),
        )
    ).all()
    campaign_ids = {batch.campaign_id for batch in batches}
    cohort_ids = {batch.cohort_id for batch in batches if batch.cohort_id is not None}
    campaigns = db.scalars(
        select(Campaign).where(
            Campaign.organization_id == organization_id,
            Campaign.id.in_(campaign_ids),
        )
    ).all()
    cohorts = (
        db.scalars(
            select(ProspectingCohort).where(
                ProspectingCohort.organization_id == organization_id,
                ProspectingCohort.id.in_(cohort_ids),
            )
        ).all()
        if cohort_ids
        else []
    )
    attempts = db.scalars(
        select(ProspectingAttempt)
        .where(
            ProspectingAttempt.organization_id == organization_id,
            ProspectingAttempt.batch_entry_id.in_(entry_ids),
        )
        .order_by(ProspectingAttempt.batch_entry_id, ProspectingAttempt.started_at.desc())
    ).all()
    import_batch_ids = {
        prospect.import_batch_id for prospect in prospects if prospect.import_batch_id is not None
    }
    import_batches = (
        db.scalars(
            select(ProspectImportBatch).where(
                ProspectImportBatch.organization_id == organization_id,
                ProspectImportBatch.id.in_(import_batch_ids),
            )
        ).all()
        if import_batch_ids
        else []
    )
    scripts = db.scalars(
        select(ProspectingScriptVersion)
        .where(ProspectingScriptVersion.organization_id == organization_id)
        .order_by(ProspectingScriptVersion.version_number.desc())
    ).all()
    user_ids = {entry.assigned_user_id for entry in entries}
    user_ids.update(script.created_by_user_id for script in scripts)
    user_ids.update(
        script.approved_by_user_id for script in scripts if script.approved_by_user_id is not None
    )
    users = db.scalars(
        select(User).where(
            User.organization_id == organization_id,
            User.id.in_(user_ids),
        )
    ).all()
    contact_points = db.scalars(
        select(ProspectContactPoint)
        .where(
            ProspectContactPoint.organization_id == organization_id,
            ProspectContactPoint.prospect_id.in_(prospect_ids),
        )
        .order_by(
            ProspectContactPoint.prospect_id,
            ProspectContactPoint.contact_type.desc(),
            ProspectContactPoint.rank,
            ProspectContactPoint.created_at,
        )
    ).all()
    qualification_responses = (
        db.scalars(
            select(ProspectingQualificationResponse)
            .join(
                ProspectingAttempt,
                ProspectingAttempt.id == ProspectingQualificationResponse.attempt_id,
            )
            .where(
                ProspectingQualificationResponse.organization_id == organization_id,
                ProspectingAttempt.organization_id == organization_id,
                ProspectingAttempt.batch_entry_id.in_(entry_ids),
            )
            .order_by(
                ProspectingQualificationResponse.attempt_id,
                ProspectingQualificationResponse.question_key,
            )
        ).all()
        if attempts
        else []
    )

    contact_points_by_prospect: dict[UUID, list[ProspectContactPoint]] = defaultdict(list)
    for contact_point in contact_points:
        contact_points_by_prospect[contact_point.prospect_id].append(contact_point)
    attempts_by_entry: dict[UUID, list[ProspectingAttempt]] = defaultdict(list)
    for attempt in attempts:
        attempts_by_entry[attempt.batch_entry_id].append(attempt)
    qualification_responses_by_attempt: dict[UUID, list[ProspectingQualificationResponse]] = (
        defaultdict(list)
    )
    for response in qualification_responses:
        qualification_responses_by_attempt[response.attempt_id].append(response)
    approved_scripts_by_asset_class: dict[str, ProspectingScriptVersion] = {}
    for script in scripts:
        asset_class = normalize_asset_class(script.asset_class)
        if script.status == "approved" and asset_class not in approved_scripts_by_asset_class:
            approved_scripts_by_asset_class[asset_class] = script

    return ProspectingReadContext(
        now=datetime.now(UTC),
        prospects={prospect.id: prospect for prospect in prospects},
        batches={batch.id: batch for batch in batches},
        campaigns={campaign.id: campaign for campaign in campaigns},
        cohorts={cohort.id: cohort for cohort in cohorts},
        users={user.id: user for user in users},
        contact_points_by_prospect=contact_points_by_prospect,
        attempts_by_entry=attempts_by_entry,
        import_batches={batch.id: batch for batch in import_batches},
        scripts={script.id: script for script in scripts},
        approved_scripts_by_asset_class=approved_scripts_by_asset_class,
        qualification_responses_by_attempt=qualification_responses_by_attempt,
    )


def build_batch_queues(
    entries: list[ProspectingEntryRead],
) -> list[ProspectingBatchQueueRead]:
    grouped: dict[UUID, list[ProspectingEntryRead]] = defaultdict(list)
    for entry in entries:
        grouped[entry.batch_id].append(entry)
    summaries: list[ProspectingBatchQueueRead] = []
    for batch_entries in grouped.values():
        first = batch_entries[0]
        summaries.append(
            ProspectingBatchQueueRead(
                batch_id=first.batch_id,
                batch_name=first.batch_name,
                campaign_name=first.campaign_name,
                cohort_name=first.cohort_name,
                dialer_mode=first.dialer_mode,
                provider_sync_status=first.provider_sync_status,
                ready=sum(item.queue_kind == "ready" for item in batch_entries),
                callbacks_due=sum(item.queue_kind == "callback_due" for item in batch_entries),
                callbacks_scheduled=sum(
                    item.queue_kind == "callback_scheduled" for item in batch_entries
                ),
                retries_due=sum(item.queue_kind == "retry_due" for item in batch_entries),
                retries_scheduled=sum(
                    item.queue_kind == "retry_scheduled" for item in batch_entries
                ),
                corrections=sum(item.queue_kind == "correction_required" for item in batch_entries),
                in_progress=sum(item.queue_kind == "in_progress" for item in batch_entries),
                handoff_pending=sum(item.queue_kind == "handoff_pending" for item in batch_entries),
            )
        )
    return sorted(summaries, key=lambda item: (item.campaign_name, item.batch_name))


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
        statement = statement.where(ProspectCallingBatchEntry.assigned_user_id == principal.user_id)
    return db.scalar(statement)


def entry_read(
    db: Session,
    entry: ProspectCallingBatchEntry,
    *,
    context: ProspectingReadContext | None = None,
) -> ProspectingEntryRead:
    prospect = (
        context.prospects.get(entry.prospect_id)
        if context is not None
        else db.scalar(
            select(Prospect).where(
                Prospect.organization_id == entry.organization_id,
                Prospect.id == entry.prospect_id,
            )
        )
    )
    batch = (
        context.batches.get(entry.prospect_calling_batch_id)
        if context is not None
        else db.scalar(
            select(ProspectCallingBatch).where(
                ProspectCallingBatch.organization_id == entry.organization_id,
                ProspectCallingBatch.id == entry.prospect_calling_batch_id,
            )
        )
    )
    if prospect is None or batch is None:
        raise ValueError("The calling-batch entry is incomplete.")
    campaign = (
        context.campaigns.get(batch.campaign_id)
        if context is not None
        else db.scalar(
            select(Campaign).where(
                Campaign.organization_id == entry.organization_id,
                Campaign.id == batch.campaign_id,
            )
        )
    )
    cohort = (
        context.cohorts.get(batch.cohort_id)
        if context is not None and batch.cohort_id is not None
        else (
            db.scalar(
                select(ProspectingCohort).where(
                    ProspectingCohort.organization_id == entry.organization_id,
                    ProspectingCohort.id == batch.cohort_id,
                )
            )
            if batch.cohort_id
            else None
        )
    )
    assignee = (
        context.users.get(entry.assigned_user_id)
        if context is not None
        else db.scalar(
            select(User).where(
                User.organization_id == entry.organization_id,
                User.id == entry.assigned_user_id,
            )
        )
    )
    contact_points = (
        list(context.contact_points_by_prospect.get(entry.prospect_id, ()))
        if context is not None
        else db.scalars(
            select(ProspectContactPoint)
            .where(
                ProspectContactPoint.organization_id == entry.organization_id,
                ProspectContactPoint.prospect_id == entry.prospect_id,
            )
            .order_by(
                ProspectContactPoint.contact_type.desc(),
                ProspectContactPoint.rank,
                ProspectContactPoint.created_at,
            )
        ).all()
    )
    attempts = (
        list(context.attempts_by_entry.get(entry.id, ()))
        if context is not None
        else db.scalars(
            select(ProspectingAttempt)
            .where(
                ProspectingAttempt.organization_id == entry.organization_id,
                ProspectingAttempt.batch_entry_id == entry.id,
            )
            .order_by(ProspectingAttempt.started_at.desc())
        ).all()
    )
    active = next((attempt for attempt in attempts if attempt.status == "in_progress"), None)
    if active is not None:
        script = (
            context.scripts.get(active.script_version_id)
            if context is not None
            else scoped_attempt_script(db, entry.organization_id, active)
        )
        if script is None:
            raise ValueError("The attempt's pinned caller script is unavailable.")
    else:
        script = (
            context.approved_scripts_by_asset_class.get(normalize_asset_class(prospect.asset_class))
            if context is not None
            else get_active_script(db, entry.organization_id, prospect.asset_class)
        )
    import_batch = (
        context.import_batches.get(prospect.import_batch_id)
        if context is not None and prospect.import_batch_id is not None
        else (
            db.scalar(
                select(ProspectImportBatch).where(
                    ProspectImportBatch.organization_id == entry.organization_id,
                    ProspectImportBatch.id == prospect.import_batch_id,
                )
            )
            if prospect.import_batch_id
            else None
        )
    )
    source_name = (
        clean_text(import_batch.source_list_name) if import_batch is not None else None
    ) or (clean_text(import_batch.source_name) if import_batch is not None else None)
    source_name = source_name or (campaign.name if campaign else "Unknown campaign")
    now = context.now if context is not None else datetime.now(UTC)
    queue_kind = entry_queue_kind(entry, now)
    attempt_reads = [attempt_read(db, attempt, context=context) for attempt in attempts]
    active_attempt_read = next(
        (item for item in attempt_reads if active is not None and item.id == active.id),
        None,
    )
    return ProspectingEntryRead(
        id=entry.id,
        batch_id=batch.id,
        batch_name=batch.name,
        campaign_id=batch.campaign_id,
        cohort_id=batch.cohort_id,
        cohort_name=cohort.name if cohort else None,
        campaign_name=campaign.name if campaign else "Unknown campaign",
        assigned_user_id=entry.assigned_user_id,
        assigned_user_name=assignee.display_name if assignee else "Unassigned caller",
        prospect_id=prospect.id,
        asset_class=normalize_asset_class(prospect.asset_class),
        script=script_read(db, script, context=context) if script else None,
        source_name=source_name[:255],
        warnings=prospecting_entry_warnings(prospect, contact_points),
        legal_name=prospect.legal_name,
        phone=prospect.phone,
        email=prospect.email,
        contact_points=[
            ProspectingContactPointRead(
                contact_type=contact.contact_type,
                value=contact.value,
                rank=contact.rank,
                is_primary=contact.is_primary,
                validation_status=contact.validation_status,
            )
            for contact in contact_points
        ],
        property_address=format_property_address(prospect),
        sequence_number=entry.sequence_number,
        status=entry.status,
        queue_kind=queue_kind,
        is_actionable=queue_kind
        in {"ready", "callback_due", "retry_due", "correction_required", "in_progress"},
        dialer_mode=batch.dialer_mode,
        provider_sync_status=provider_sync_status(),
        attempt_count=entry.attempt_count,
        disposition=entry.disposition,
        next_attempt_at=entry.next_attempt_at,
        active_attempt=active_attempt_read,
        attempts=attempt_reads,
    )


def entry_queue_kind(
    entry: ProspectCallingBatchEntry,
    now: datetime,
) -> str:
    if entry.status == "in_progress":
        return "in_progress"
    if entry.status == "needs_correction":
        return "correction_required"
    if entry.status == "handoff_pending":
        return "handoff_pending"
    if entry.status == "completed":
        return "completed"
    if entry.next_attempt_at is not None:
        due = as_utc(entry.next_attempt_at) <= now
        if entry.disposition in CALLBACK_OUTCOMES:
            return "callback_due" if due else "callback_scheduled"
        if entry.disposition in RETRY_OUTCOMES:
            return "retry_due" if due else "retry_scheduled"
    return "ready"


def provider_sync_status() -> str:
    return "stonegate_direct"


def attempt_read(
    db: Session,
    attempt: ProspectingAttempt,
    *,
    context: ProspectingReadContext | None = None,
) -> ProspectingAttemptRead:
    script = (
        context.scripts.get(attempt.script_version_id)
        if context is not None
        else scoped_attempt_script(db, attempt.organization_id, attempt)
    )
    if script is None:
        raise ValueError("The attempt's pinned caller script is unavailable.")
    qualification_rows = (
        context.qualification_responses_by_attempt.get(attempt.id, ())
        if context is not None
        else None
    )
    return ProspectingAttemptRead(
        id=attempt.id,
        script_version_id=attempt.script_version_id,
        script_version_number=script.version_number,
        cohort_id=attempt.cohort_id,
        dialer_mode=attempt.dialer_mode,
        status=attempt.status,
        outcome=attempt.outcome,
        contact_made=attempt.contact_made,
        answer_classification=attempt.answer_classification,
        party_classification=attempt.party_classification,
        interest_classification=attempt.interest_classification,
        follow_up_permission=attempt.follow_up_permission,
        classification_source=attempt.classification_source,
        dial_started_at=attempt.dial_started_at,
        answered_at=attempt.answered_at,
        right_party_confirmed_at=attempt.right_party_confirmed_at,
        interest_confirmed_at=attempt.interest_confirmed_at,
        measurement_metadata=attempt.measurement_metadata,
        qualification_answers=attempt.qualification_answers,
        notes=attempt.notes,
        callback_at=attempt.callback_at,
        started_at=attempt.started_at,
        completed_at=attempt.completed_at,
        quality_score_basis_points=attempt.quality_score_basis_points,
        qualification_checklist=qualification_checklist_read(
            db,
            attempt,
            script,
            rows=qualification_rows,
        ),
    )


def list_scripts(db: Session, principal: Principal) -> list[ProspectingScriptRead]:
    scripts = db.scalars(
        select(ProspectingScriptVersion)
        .where(ProspectingScriptVersion.organization_id == principal.organization_id)
        .order_by(ProspectingScriptVersion.version_number.desc())
    ).all()
    return [script_read(db, script) for script in scripts]


def script_read(
    db: Session,
    script: ProspectingScriptVersion,
    *,
    context: ProspectingReadContext | None = None,
) -> ProspectingScriptRead:
    creator = (
        context.users.get(script.created_by_user_id)
        if context is not None
        else db.get(User, script.created_by_user_id)
    )
    approver = (
        context.users.get(script.approved_by_user_id)
        if context is not None and script.approved_by_user_id is not None
        else (db.get(User, script.approved_by_user_id) if script.approved_by_user_id else None)
    )
    return ProspectingScriptRead(
        id=script.id,
        version_number=script.version_number,
        asset_class=normalize_asset_class(script.asset_class),
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


def scoped_attempt_script(
    db: Session,
    organization_id: UUID,
    attempt: ProspectingAttempt,
) -> ProspectingScriptVersion:
    script = db.scalar(
        select(ProspectingScriptVersion).where(
            ProspectingScriptVersion.organization_id == organization_id,
            ProspectingScriptVersion.id == attempt.script_version_id,
        )
    )
    if script is None:
        raise ValueError("The attempt's pinned caller script is unavailable.")
    return script


def qualification_checklist_read(
    db: Session,
    attempt: ProspectingAttempt,
    script: ProspectingScriptVersion,
    *,
    rows: Sequence[ProspectingQualificationResponse] | None = None,
) -> ProspectingQualificationChecklistRead:
    if rows is None:
        rows = db.scalars(
            select(ProspectingQualificationResponse).where(
                ProspectingQualificationResponse.attempt_id == attempt.id,
            )
        ).all()
    known_keys = {question.key for question in script_questions(script)}
    if any(
        row.organization_id != attempt.organization_id
        or row.script_version_id != script.id
        or row.question_key not in known_keys
        for row in rows
    ):
        raise ValueError("Saved qualification evidence does not match the pinned caller script.")
    row_by_key = {row.question_key: row for row in rows}
    legacy_answers = attempt.qualification_answers or {}
    items = [
        qualification_item_read(
            question,
            response=row_by_key.get(question.key),
            fallback_value=(
                str(legacy_answers[question.key]).strip()
                if question.key in legacy_answers and str(legacy_answers[question.key]).strip()
                else None
            ),
        )
        for question in script_questions(script)
    ]
    answered_count = sum(item.state == "answered" and bool(item.answer_value) for item in items)
    required_items = [item for item in items if item.is_required]
    required_answered_count = sum(
        item.state == "answered" and bool(item.answer_value) for item in required_items
    )
    missing_required_keys = [
        item.question_key
        for item in required_items
        if item.state != "answered" or not item.answer_value
    ]
    return ProspectingQualificationChecklistRead(
        attempt_id=attempt.id,
        script_version_id=script.id,
        items=items,
        answered_count=answered_count,
        total_count=len(items),
        required_answered_count=required_answered_count,
        required_count=len(required_items),
        missing_required_keys=missing_required_keys,
        complete=not missing_required_keys,
    )


def qualification_item_read(
    question: ScriptQuestion,
    *,
    response: ProspectingQualificationResponse | None,
    fallback_value: str | None,
) -> ProspectingQualificationChecklistItemRead:
    if response is not None:
        answer_value = (
            str(response.answer_value).strip() if response.answer_value is not None else None
        )
        answer_value = answer_value or None
        state = cast(QualificationResponseState, response.state)
        source = response.source
        revision = qualification_revision(response.response_metadata or {})
        captured_at = response.captured_at
        updated_at = response.updated_at
    elif fallback_value:
        answer_value = fallback_value
        state = "answered"
        source = "legacy_completion"
        revision = 0
        captured_at = None
        updated_at = None
    else:
        answer_value = None
        state = "not_covered"
        source = "not_recorded"
        revision = 0
        captured_at = None
        updated_at = None
    return ProspectingQualificationChecklistItemRead(
        question_key=question.key,
        label=question.label,
        prompt=question.prompt,
        answer_type=question.answer_type,
        choices=list(question.choices),
        is_required=question.required_for_handoff,
        state=state,
        answer_value=answer_value,
        source=source,
        revision=revision,
        captured_at=captured_at,
        updated_at=updated_at,
    )


def normalize_qualification_answer(
    question: ScriptQuestion,
    state: QualificationResponseState,
    answer_value: str | None,
) -> str | None:
    value = clean_text(answer_value)
    if state in {"answered", "needs_follow_up", "conflict"} and value is None:
        raise ValueError(
            "Answered, follow-up, and conflict qualification states require a usable response."
        )
    if state == "not_covered":
        return None
    if (
        state == "answered"
        and value is not None
        and question.answer_type == "choice"
        and value not in question.choices
    ):
        raise ValueError("Select one of the approved answers for this qualification question.")
    return value


def qualification_revision(metadata: Mapping[str, object]) -> int:
    value = metadata.get("revision", 0)
    return value if isinstance(value, int) and value >= 0 else 0


def qualification_mutation_hash(
    *,
    state: QualificationResponseState,
    answer_value: str | None,
    expected_revision: int,
) -> str:
    canonical = json.dumps(
        {
            "state": state,
            "answer_value": answer_value,
            "expected_revision": expected_revision,
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def qualification_response_snapshot(
    response: ProspectingQualificationResponse | None,
) -> dict[str, object] | None:
    if response is None:
        return None
    return {
        "attempt_id": str(response.attempt_id),
        "script_version_id": str(response.script_version_id),
        "question_key": response.question_key,
        "state": response.state,
        "answer_value": response.answer_value,
        "source": response.source,
        "actor_user_id": str(response.actor_user_id) if response.actor_user_id else None,
        "is_required": response.is_required,
        "revision": qualification_revision(response.response_metadata or {}),
    }


def required_question_count(script: ProspectingScriptVersion) -> int:
    return sum(question.required_for_handoff for question in script_questions(script))


def get_active_script(
    db: Session,
    organization_id: UUID,
    asset_class: str = HOUSE_ASSET_CLASS,
) -> ProspectingScriptVersion | None:
    return db.scalar(
        select(ProspectingScriptVersion)
        .where(
            ProspectingScriptVersion.organization_id == organization_id,
            ProspectingScriptVersion.asset_class == normalize_asset_class(asset_class),
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
        asset_class=normalize_asset_class(prospect.asset_class),
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
        decision_code=handoff.decision_code,
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
        statement = statement.where(ProspectCallingBatchEntry.assigned_user_id == principal.user_id)
    entries = db.scalars(statement).all()
    now = datetime.now(UTC)
    queue_kinds = [entry_queue_kind(entry, now) for entry in entries]
    return ProspectingQueueSummary(
        ready=sum(kind == "ready" for kind in queue_kinds),
        callbacks_due=sum(kind == "callback_due" for kind in queue_kinds),
        callbacks_scheduled=sum(kind == "callback_scheduled" for kind in queue_kinds),
        retries_due=sum(kind == "retry_due" for kind in queue_kinds),
        retries_scheduled=sum(kind == "retry_scheduled" for kind in queue_kinds),
        corrections=sum(kind == "correction_required" for kind in queue_kinds),
        in_progress=sum(kind == "in_progress" for kind in queue_kinds),
        handoff_pending=sum(kind == "handoff_pending" for kind in queue_kinds),
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
        db.scalars(select(ProspectHandoff).where(ProspectHandoff.attempt_id.in_(attempt_ids))).all()
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
            is_accepted_warm_lead(row, handoff_by_attempt[row.id])
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
                accepted_handoff_rate_basis_points=rate_basis_points(accepted_count, handoff_count),
                script_completion_rate_basis_points=rate_basis_points(
                    answered_required, required_answers
                ),
                data_quality_issue_rate_basis_points=rate_basis_points(wrong_numbers, len(rows)),
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
    parcel_id, county, _ = prospect_property_metadata(prospect)
    return (
        property_identity_label(
            street_address=prospect.street_address,
            city=prospect.city,
            state=prospect.state_code,
            postal_code=prospect.postal_code,
            parcel_id=parcel_id,
            county=county,
        )
        or None
    )


def prospecting_entry_warnings(
    prospect: Prospect,
    contact_points: Sequence[ProspectContactPoint],
) -> list[str]:
    warnings: list[str] = []
    if prospect.call_eligibility != "eligible":
        warnings.append(
            f"Calling eligibility requires review ({display_status(prospect.call_eligibility)})."
        )
    if prospect.suppression_status != "clear":
        warnings.append(
            f"Suppression status requires review ({display_status(prospect.suppression_status)})."
        )
    has_phone = bool(prospect.phone) or any(
        item.contact_type == "phone" and item.value.strip() for item in contact_points
    )
    if not has_phone:
        warnings.append("No callable phone number is on file.")
    elif prospect.phone_validation_status not in {"valid", "verified"}:
        warnings.append(
            f"Primary phone validation is {display_status(prospect.phone_validation_status)}."
        )
    if not format_property_address(prospect):
        warnings.append("Property identity is incomplete.")
    elif prospect.address_validation_status not in {"valid", "verified", "provider_confirmed"}:
        warnings.append(
            f"Property address validation is {display_status(prospect.address_validation_status)}."
        )
    if not prospect.legal_name.strip():
        warnings.append("The property owner name is missing.")
    return warnings[:8]


def display_status(value: str) -> str:
    return value.replace("_", " ").strip().lower()[:80]


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
