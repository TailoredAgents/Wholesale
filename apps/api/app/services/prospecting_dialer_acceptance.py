import hashlib
import json
from datetime import UTC, date, datetime, timedelta
from typing import Any
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.auth import Principal
from app.core.config import Settings, get_settings
from app.domain.rbac import PermissionKeys
from app.models.foundation import (
    AuditEvent,
    CallRecord,
    CallRecording,
    CallTranscript,
    Campaign,
    Organization,
    Prospect,
    ProspectCallingBatch,
    ProspectCallingBatchEntry,
    ProspectHandoff,
    ProspectingAttempt,
    ProspectingCohort,
    ProspectingDialerPilot,
    ProspectingDialerPilotAttemptReview,
    ProspectingDialerPilotShiftReview,
    ProspectingDialLeg,
    ProspectingDialSession,
    ProspectingProviderEvent,
    Role,
    RoleAssignment,
    User,
    VoiceCallIntent,
    VoiceLine,
)
from app.schemas.prospecting_dialer_acceptance import (
    ProspectingDialerPilotAttemptQueueRead,
    ProspectingDialerPilotAttemptReviewCreate,
    ProspectingDialerPilotAttemptReviewRead,
    ProspectingDialerPilotBatchComparisonEvidence,
    ProspectingDialerPilotCreate,
    ProspectingDialerPilotDecision,
    ProspectingDialerPilotEvidenceUpdate,
    ProspectingDialerPilotGateRead,
    ProspectingDialerPilotKillSwitchEvidence,
    ProspectingDialerPilotOverviewRead,
    ProspectingDialerPilotRead,
    ProspectingDialerPilotRevoke,
    ProspectingDialerPilotRollback,
    ProspectingDialerPilotRollbackEvidence,
    ProspectingDialerPilotShiftReviewCreate,
    ProspectingDialerPilotShiftReviewRead,
    ProspectingDialerPilotSmokeTestEvidence,
    ProspectingDialerPilotStart,
    ProspectingDialerPilotSubmit,
)
from app.services.call_intelligence import (
    PROSPECTING_TRANSCRIPT_CONTACT_OUTCOMES,
    prospecting_transcript_eligibility,
)
from app.services.communication_compliance import format_e164
from app.services.prospecting_dialer import (
    CALLBACK_DISPOSITIONS,
    DIAL_LEG_TERMINAL_STATUSES,
    TERMINAL_DIAL_SESSION_STATES,
    DialerRuntimeGraph,
    can_manage_dialer,
    candidate_entry_statement,
    load_runtime_graph,
    release_unstarted_reservation,
    require_native_dialer_activation_enabled,
    runtime_policy_blockers,
    select_ranked_phone,
)
from app.services.prospecting_dialer_analytics import _launch_readiness
from app.services.prospecting_measurement import classify_outcome

PILOT_POLICY_VERSION = "d10-single-line-v1"
PILOT_ACCEPTANCE_PHRASE = "ACCEPT SINGLE-LINE DIALER"
PILOT_REJECTION_PHRASE = "REJECT SINGLE-LINE DIALER"
PILOT_ROLLBACK_PHRASE = "ROLL BACK SINGLE-LINE PILOT"
PILOT_REVOKE_PHRASE = "REVOKE SINGLE-LINE DIALER"
PILOT_OPEN_STATUSES = {"draft", "smoke_testing", "running", "ready_for_owner_review"}
PILOT_RUNTIME_STATUSES = {"smoke_testing", "running", "accepted"}
PILOT_MUTABLE_STATUSES = {"draft", "smoke_testing", "running"}
PILOT_OWNER_ROLE_KEYS = {"owner", "founder_operator"}
PILOT_MAX_DIALS_PER_DAY = 50
PILOT_MAX_SPEND_CENTS_PER_DAY = 1000
PILOT_MIN_BATCH_SIZE = 75
PILOT_MAX_BATCH_SIZE = 250
PILOT_REQUIRED_SHIFTS = 3
PILOT_MIN_ATTEMPTS_PER_SHIFT = 25
PILOT_MIN_MINUTES_PER_SHIFT = 60
PILOT_MIN_TOTAL_ATTEMPTS = 75


class ProspectingDialerAcceptanceConflictError(RuntimeError):
    """The requested acceptance mutation conflicts with durable pilot state."""


def _exact_provider_call_record(
    db: Session,
    pilot: ProspectingDialerPilot,
    leg: ProspectingDialLeg,
) -> CallRecord | None:
    """Return the reciprocal root provider graph for one exact pilot leg."""

    if (
        leg.provider_call_id is None
        or leg.call_record_id is None
        or leg.attempt_id is None
    ):
        return None
    call = db.scalar(
        select(CallRecord).where(
            CallRecord.id == leg.call_record_id,
            CallRecord.organization_id == pilot.organization_id,
            CallRecord.prospect_id == leg.prospect_id,
            CallRecord.prospecting_attempt_id == leg.attempt_id,
            CallRecord.prospecting_dial_leg_id == leg.id,
            CallRecord.voice_line_id == pilot.voice_line_id,
            CallRecord.provider == leg.provider,
            CallRecord.provider_call_id == leg.provider_call_id,
        )
    )
    if call is None or call.call_intent_id is None:
        return None
    attempt = db.scalar(
        select(ProspectingAttempt).where(
            ProspectingAttempt.id == leg.attempt_id,
            ProspectingAttempt.organization_id == pilot.organization_id,
            ProspectingAttempt.prospect_id == leg.prospect_id,
            ProspectingAttempt.provider == leg.provider,
            ProspectingAttempt.provider_call_id == leg.provider_call_id,
        )
    )
    intent = db.scalar(
        select(VoiceCallIntent).where(
            VoiceCallIntent.id == call.call_intent_id,
            VoiceCallIntent.organization_id == pilot.organization_id,
            VoiceCallIntent.prospect_id == leg.prospect_id,
            VoiceCallIntent.prospecting_attempt_id == leg.attempt_id,
            VoiceCallIntent.prospecting_dial_leg_id == leg.id,
            VoiceCallIntent.voice_line_id == pilot.voice_line_id,
            VoiceCallIntent.provider_call_id == leg.provider_call_id,
        )
    )
    return call if attempt is not None and intent is not None else None


def _billable_provider_call_ids(
    db: Session,
    pilot: ProspectingDialerPilot,
    leg: ProspectingDialLeg,
) -> tuple[str, ...]:
    """Return the root + optional seller-child IDs for one reciprocal call graph."""

    call = _exact_provider_call_record(db, pilot, leg)
    if call is None or call.provider_call_id is None:
        return ()
    values = [call.provider_call_id]
    if call.child_provider_call_id:
        values.append(call.child_provider_call_id)
    return tuple(values)


def _provider_identity_graph(
    db: Session,
    pilot: ProspectingDialerPilot,
    legs: list[ProspectingDialLeg],
) -> tuple[list[ProspectingDialLeg], tuple[str, ...], bool]:
    """Split provider-started legs from their exact, collision-free billing IDs."""

    provider_started_legs = [leg for leg in legs if leg.provider_call_id is not None]
    provider_call_ids: list[str] = []
    complete = True
    for leg in provider_started_legs:
        leg_provider_ids = _billable_provider_call_ids(db, pilot, leg)
        if (
            not leg_provider_ids
            or leg_provider_ids[0] != leg.provider_call_id
            or len(leg_provider_ids) != len(set(leg_provider_ids))
        ):
            complete = False
        call_records = db.scalars(
            select(CallRecord).where(
                CallRecord.organization_id == pilot.organization_id,
                CallRecord.prospecting_dial_leg_id == leg.id,
            )
        ).all()
        intents = db.scalars(
            select(VoiceCallIntent).where(
                VoiceCallIntent.organization_id == pilot.organization_id,
                VoiceCallIntent.prospecting_dial_leg_id == leg.id,
            )
        ).all()
        event_provider_ids = set(
            db.scalars(
                select(ProspectingProviderEvent.provider_call_id).where(
                    ProspectingProviderEvent.organization_id == pilot.organization_id,
                    ProspectingProviderEvent.dial_leg_id == leg.id,
                    ProspectingProviderEvent.provider_call_id.is_not(None),
                )
            ).all()
        )
        if (
            len(call_records) != 1
            or call_records[0].id != leg.call_record_id
            or len(intents) != 1
            or call_records[0].call_intent_id != intents[0].id
            or not event_provider_ids.issubset(set(leg_provider_ids))
        ):
            complete = False
        provider_call_ids.extend(leg_provider_ids)
    if len(provider_call_ids) != len(set(provider_call_ids)):
        complete = False
    return provider_started_legs, tuple(provider_call_ids), complete


def _signed_child_event_matches(
    event: ProspectingProviderEvent,
    *,
    root_provider_call_id: str,
    child_provider_call_id: str,
) -> bool:
    payload = event.payload or {}
    call_sid = str(payload.get("CallSid") or "").strip()
    parent_sid = str(payload.get("ParentCallSid") or "").strip()
    dial_sid = str(payload.get("DialCallSid") or "").strip()
    return bool(
        event.signature_verified is True
        and event.signature_fingerprint
        and event.payload_sha256
        and event.event_type.startswith("call.")
        and event.provider_call_id == child_provider_call_id
        and (
            (call_sid == child_provider_call_id and parent_sid == root_provider_call_id)
            or (
                dial_sid == child_provider_call_id
                and root_provider_call_id in {call_sid, parent_sid}
            )
        )
    )


def _nonnegative_provider_duration(payload: dict[str, Any]) -> int | None:
    for key in ("DialCallDuration", "CallDuration", "Duration"):
        raw = payload.get(key)
        if raw is None:
            continue
        try:
            value = int(str(raw))
        except (TypeError, ValueError):
            continue
        if value >= 0:
            return value
    return None


def _seller_child_evidence(
    db: Session,
    pilot: ProspectingDialerPilot,
    leg: ProspectingDialLeg,
    *,
    captured_at: datetime,
) -> dict[str, Any] | None:
    """Return signed seller-child identity and defensible provider duration."""

    call = _exact_provider_call_record(db, pilot, leg)
    if (
        call is None
        or call.provider_call_id is None
        or not call.child_provider_call_id
        or call.child_provider_call_id == call.provider_call_id
    ):
        return None
    child_id = call.child_provider_call_id
    root_id = call.provider_call_id
    events = db.scalars(
        select(ProspectingProviderEvent)
        .where(
            ProspectingProviderEvent.organization_id == pilot.organization_id,
            ProspectingProviderEvent.provider == leg.provider,
            ProspectingProviderEvent.dial_session_id == leg.dial_session_id,
            ProspectingProviderEvent.dial_leg_id == leg.id,
            ProspectingProviderEvent.attempt_id == leg.attempt_id,
            ProspectingProviderEvent.provider_call_id == child_id,
            ProspectingProviderEvent.signature_verified.is_(True),
            ProspectingProviderEvent.received_at <= _as_utc(captured_at),
        )
        .order_by(
            ProspectingProviderEvent.occurred_at.asc(),
            ProspectingProviderEvent.id.asc(),
        )
    ).all()
    events = [
        item
        for item in events
        if _signed_child_event_matches(
            item,
            root_provider_call_id=root_id,
            child_provider_call_id=child_id,
        )
    ]
    if not events:
        return None
    terminal_statuses = {
        "busy",
        "canceled",
        "cancelled",
        "completed",
        "failed",
        "no_answer",
        "no-answer",
    }
    start_statuses = {"initiated", "queued", "ringing", "answered", "connected", "in_progress"}

    def event_status(event: ProspectingProviderEvent) -> str:
        payload = event.payload or {}
        raw = (
            payload.get("DialCallStatus")
            or payload.get("CallStatus")
            or event.event_type.removeprefix("call.")
        )
        return str(raw or "").strip().lower().replace("-", "_")

    terminal_events = [
        item
        for item in events
        if event_status(item) in {value.replace("-", "_") for value in terminal_statuses}
    ]
    if not terminal_events:
        return None
    provider_durations = [
        value
        for item in events
        if (value := _nonnegative_provider_duration(item.payload or {})) is not None
    ]
    duration_seconds: int | None = max(provider_durations) if provider_durations else None
    timing_source = "signed_provider_duration" if provider_durations else None
    connection_statuses = {"answered", "connected", "in_progress"}
    connection_events = [
        item
        for item in events
        if event_status(item) in connection_statuses and item.occurred_at is not None
    ]
    if duration_seconds is None:
        started_events = [
            item
            for item in events
            if event_status(item) in start_statuses and item.occurred_at is not None
        ]
        ended_events = [item for item in terminal_events if item.occurred_at is not None]
        interval_start_events = connection_events or started_events
        if interval_start_events and ended_events:
            started_at = min(
                _as_utc(item.occurred_at) for item in interval_start_events
            )
            ended_at = max(_as_utc(item.occurred_at) for item in ended_events)
            if ended_at >= started_at:
                duration_seconds = int((ended_at - started_at).total_seconds())
                timing_source = (
                    "signed_connected_event_interval"
                    if connection_events
                    else "signed_child_event_interval"
                )
    contact_evidence = bool(
        any(value > 0 for value in provider_durations) or connection_events
    )
    return {
        "dial_leg_id": str(leg.id),
        "call_record_id": str(call.id),
        "root_provider_call_id": root_id,
        "child_provider_call_id": child_id,
        "signed_event_ids": [str(item.id) for item in events],
        "signed_event_external_ids": [item.external_event_id for item in events],
        "signed_event_payload_hashes": [item.payload_sha256 for item in events],
        "signed_event_signature_fingerprints": [
            item.signature_fingerprint for item in events
        ],
        "duration_seconds": duration_seconds,
        "timing_source": timing_source,
        "contact_evidence": contact_evidence,
        "connection_evidence_source": (
            "signed_provider_duration"
            if any(value > 0 for value in provider_durations)
            else "signed_connection_status"
            if connection_events
            else None
        ),
    }


def _contact_disposition_evidence(
    attempt: ProspectingAttempt,
    leg: ProspectingDialLeg,
    seller_evidence: dict[str, Any] | None,
) -> dict[str, object]:
    """Reconcile provider connection truth with the caller's disposition.

    A provider-connected seller child can be a machine or a wrong party.  It is
    not automatically a right-party seller conversation and therefore does not
    automatically require transcription or count as productive talk time.
    """

    canonical = classify_outcome(attempt.outcome or "")
    canonical_attempt = bool(
        attempt.answer_classification == canonical.answer
        and attempt.party_classification == canonical.party
        and attempt.interest_classification == canonical.interest
        and attempt.follow_up_permission == canonical.follow_up_permission
    )
    provider_connection = bool(
        seller_evidence and seller_evidence.get("contact_evidence") is True
    )
    base_complete = bool(
        attempt.status == "completed"
        and attempt.completed_at is not None
        and leg.status in DIAL_LEG_TERMINAL_STATUSES
        and leg.completed_at is not None
    )
    if attempt.outcome == "no_answer":
        classification = "no_connection"
        reconciled = bool(
            base_complete
            and canonical_attempt
            and attempt.contact_made is False
            and leg.status in {"no_answer", "busy"}
            and leg.answered_at is None
            and leg.connected_at is None
            and not provider_connection
        )
    elif attempt.outcome == "left_voicemail":
        classification = "machine"
        reconciled = bool(
            base_complete
            and canonical_attempt
            and attempt.contact_made is False
            and leg.status == "completed"
            and leg.connected_at is not None
            and provider_connection
        )
    elif attempt.outcome == "wrong_number":
        classification = "wrong_party"
        reconciled = bool(
            base_complete
            and canonical_attempt
            and attempt.contact_made is False
            and leg.status == "completed"
            and leg.connected_at is not None
            and provider_connection
        )
    elif attempt.outcome in PROSPECTING_TRANSCRIPT_CONTACT_OUTCOMES:
        classification = "right_party"
        reconciled = bool(
            base_complete
            and canonical_attempt
            and attempt.contact_made is True
            and canonical.answer == "live_person"
            and canonical.party == "right_party"
            and leg.status == "completed"
            and leg.connected_at is not None
            and leg.party_classification != "wrong_party"
            and provider_connection
        )
    elif attempt.outcome == "technical_failure":
        classification = "technical_failure"
        reconciled = bool(
            attempt.status in {"completed", "cancelled"}
            and attempt.completed_at is not None
            and attempt.contact_made is False
            and attempt.answer_classification == "unknown"
            and attempt.party_classification == "unknown"
            and attempt.interest_classification == "not_assessed"
            and attempt.follow_up_permission == "not_recorded"
            and leg.status in {"failed", "cancelled"}
            and leg.completed_at is not None
            and leg.answered_at is None
            and leg.connected_at is None
            and not provider_connection
        )
    else:
        classification = "unsupported"
        reconciled = False
    return {
        "classification": classification,
        "provider_connection": provider_connection,
        "right_party_contact": classification == "right_party" and reconciled,
        "reconciled": reconciled,
    }


def _is_placed_leg(
    db: Session,
    pilot: ProspectingDialerPilot,
    leg: ProspectingDialLeg,
    *,
    captured_at: datetime,
) -> bool:
    """Count only a signed seller-child call in D10 seller outcome KPIs."""

    return _seller_child_evidence(db, pilot, leg, captured_at=captured_at) is not None


def _pilot_active_runtime_counts(
    db: Session,
    pilot: ProspectingDialerPilot,
) -> tuple[int, int]:
    """Return active sessions and legs across the entire exact pilot scope."""

    sessions = db.scalars(
        select(ProspectingDialSession)
        .where(
            ProspectingDialSession.organization_id == pilot.organization_id,
            ProspectingDialSession.pilot_id == pilot.id,
            ProspectingDialSession.ended_at.is_(None),
        )
        .with_for_update()
    ).all()
    legs = db.scalars(
        select(ProspectingDialLeg)
        .join(
            ProspectingDialSession,
            ProspectingDialSession.id == ProspectingDialLeg.dial_session_id,
        )
        .where(
            ProspectingDialSession.organization_id == pilot.organization_id,
            ProspectingDialSession.pilot_id == pilot.id,
            ProspectingDialLeg.completed_at.is_(None),
        )
        .with_for_update()
    ).all()
    return len(sessions), len(legs)


def _require_decision_confirmation(payload: ProspectingDialerPilotDecision) -> None:
    expected = (
        PILOT_ACCEPTANCE_PHRASE
        if payload.decision == "accept"
        else PILOT_REJECTION_PHRASE
    )
    if payload.confirmation_phrase != expected:
        raise ValueError(f'Type exactly "{expected}" to {payload.decision} the pilot.')


def pilot_configuration_fingerprint(
    graph: DialerRuntimeGraph,
    settings: Settings,
) -> str:
    """Hash only the durable D10 scope and controls that affect authorization."""

    contract = {
        "policy_version": PILOT_POLICY_VERSION,
        "scope": {
            "organization_id": str(graph.organization.id),
            "caller_user_id": str(graph.caller.id),
            "dialer_profile_id": str(graph.profile.id),
            "campaign_id": str(graph.campaign.id),
            "cohort_id": str(graph.cohort.id),
            "prospect_calling_batch_id": str(graph.batch.id),
            "voice_line_id": str(graph.line.id),
        },
        "line_caps": {
            "organization": graph.organization.prospecting_dialer_max_concurrent_legs,
            "profile_default": graph.profile.default_line_count,
            "profile_max": graph.profile.max_line_count,
            "campaign": graph.campaign.prospecting_dialer_max_concurrent_legs,
            "voice_line": graph.line.prospecting_dialer_max_concurrent_legs,
            "runtime_effective": settings.prospecting_native_dialer_effective_line_cap,
        },
        "profile_policy": {
            "daily_dial_limit": graph.profile.daily_dial_limit,
            "daily_spend_limit_cents": graph.profile.daily_spend_limit_cents,
            "recording_policy": graph.profile.recording_policy,
        },
        "recording_policy": {
            "provider_recording_enabled": settings.twilio_voice_recording_enabled,
            "provider_recording_configured": settings.twilio_voice_recording_configured,
            "retention_days": settings.call_recording_retention_days,
            "transcription_enabled": settings.call_transcription_enabled,
            "transcription_model": settings.openai_transcription_model,
            "disclosure_present": bool(
                (settings.twilio_voice_recording_disclosure or "").strip()
            ),
            "disclosure_hash": _hash_json(
                (settings.twilio_voice_recording_disclosure or "").strip()
            ),
        },
        "batch_policy": {
            "dialer_mode": graph.batch.dialer_mode,
            "assigned_user_id": str(graph.batch.assigned_user_id),
        },
        "campaign_policy": {
            "market_id": str(graph.campaign.market_id),
            "territory_id": (
                str(graph.campaign.territory_id) if graph.campaign.territory_id else None
            ),
            "channel": graph.campaign.channel,
            "asset_class": graph.campaign.asset_class,
            "starts_on": graph.campaign.starts_on,
            "ends_on": graph.campaign.ends_on,
        },
        "cohort_policy": {
            "dialer_mode": graph.cohort.dialer_mode,
            "script_version_id": (
                str(graph.cohort.script_version_id)
                if graph.cohort.script_version_id is not None
                else None
            ),
            "timezone": graph.cohort.timezone,
            "call_window_start_hour": graph.cohort.call_window_start_hour,
            "call_window_end_hour": graph.cohort.call_window_end_hour,
            "starts_on": graph.cohort.starts_on,
            "ends_on": graph.cohort.ends_on,
        },
        "line_policy": {
            "phone_number": graph.line.phone_number,
            "provider": graph.line.provider,
            "department_key": graph.line.department_key,
            "purpose_key": graph.line.purpose_key,
            "assigned_user_id": (
                str(graph.line.assigned_user_id) if graph.line.assigned_user_id else None
            ),
        },
    }
    return _hash_json(contract)


def _batch_membership_snapshot(
    db: Session,
    organization_id: UUID,
    batch_id: UUID,
) -> dict[str, Any]:
    rows = db.execute(
        select(
            ProspectCallingBatchEntry.id,
            ProspectCallingBatchEntry.prospect_id,
            ProspectCallingBatchEntry.assigned_user_id,
            ProspectCallingBatchEntry.sequence_number,
        )
        .where(
            ProspectCallingBatchEntry.organization_id == organization_id,
            ProspectCallingBatchEntry.prospect_calling_batch_id == batch_id,
        )
        .order_by(
            ProspectCallingBatchEntry.sequence_number.asc(),
            ProspectCallingBatchEntry.id.asc(),
        )
    ).all()
    members = [
        {
            "entry_id": str(entry_id),
            "prospect_id": str(prospect_id),
            "assigned_user_id": str(assigned_user_id),
            "sequence_number": sequence_number,
        }
        for entry_id, prospect_id, assigned_user_id, sequence_number in rows
    ]
    return {
        "entry_count": len(members),
        "membership_hash": _hash_json(members),
    }


def _pilot_batch_membership_matches(db: Session, pilot: ProspectingDialerPilot) -> bool:
    attestation = pilot.start_attestation or {}
    expected_count = attestation.get("batch_entry_count")
    expected_hash = attestation.get("batch_membership_hash")
    current = _batch_membership_snapshot(
        db,
        pilot.organization_id,
        pilot.prospect_calling_batch_id,
    )
    return bool(
        isinstance(expected_count, int)
        and PILOT_MIN_BATCH_SIZE <= expected_count <= PILOT_MAX_BATCH_SIZE
        and current["entry_count"] == expected_count
        and current["membership_hash"] == expected_hash
    )


def matching_active_pilot(
    db: Session,
    graph: DialerRuntimeGraph,
    settings: Settings,
) -> ProspectingDialerPilot | None:
    """Return an authorized pilot only when the exact runtime contract still matches."""

    fingerprint = pilot_configuration_fingerprint(graph, settings)
    matches = db.scalars(
        select(ProspectingDialerPilot)
        .where(
            ProspectingDialerPilot.organization_id == graph.organization.id,
            ProspectingDialerPilot.caller_user_id == graph.caller.id,
            ProspectingDialerPilot.campaign_id == graph.campaign.id,
            ProspectingDialerPilot.cohort_id == graph.cohort.id,
            ProspectingDialerPilot.prospect_calling_batch_id == graph.batch.id,
            ProspectingDialerPilot.voice_line_id == graph.line.id,
            ProspectingDialerPilot.configuration_fingerprint == fingerprint,
            ProspectingDialerPilot.status.in_(PILOT_RUNTIME_STATUSES),
        )
        .with_for_update()
    ).all()
    exact_matches = [
        item
        for item in matches
        if _pilot_batch_membership_matches(db, item)
        and (
            item.status != "smoke_testing"
            or _pilot_controlled_staff_mapping_matches(db, item)
        )
    ]
    return exact_matches[0] if len(exact_matches) == 1 else None


def pilot_authorizes_recipient(
    pilot: ProspectingDialerPilot,
    recipient: str | None,
) -> bool:
    """Authorize only persisted controlled numbers until the smoke test passes."""

    normalized = format_e164(recipient or "")
    if normalized is None or pilot.status not in PILOT_RUNTIME_STATUSES:
        return False
    if pilot.status in {"running", "accepted"}:
        return True
    return normalized in _pilot_controlled_numbers(pilot)


def _pilot_controlled_numbers(pilot: ProspectingDialerPilot) -> set[str]:
    raw_numbers = (pilot.start_attestation or {}).get("controlled_phone_numbers")
    if not isinstance(raw_numbers, list):
        return set()
    return {
        formatted
        for value in raw_numbers
        if isinstance(value, str)
        and (formatted := format_e164(value)) is not None
    }


def _pilot_controlled_staff_mapping_matches(
    db: Session,
    pilot: ProspectingDialerPilot,
) -> bool:
    controlled_numbers = _pilot_controlled_numbers(pilot)
    raw_owners = (pilot.start_attestation or {}).get("controlled_number_staff_owners")
    if not controlled_numbers or not isinstance(raw_owners, dict):
        return False
    try:
        expected_owners = {
            number: {UUID(str(user_id)) for user_id in owner_ids}
            for number, owner_ids in raw_owners.items()
            if isinstance(number, str) and isinstance(owner_ids, list)
        }
    except ValueError:
        return False
    if set(expected_owners) != controlled_numbers or any(
        not owner_ids for owner_ids in expected_owners.values()
    ):
        return False
    users = db.scalars(
        select(User).where(
            User.organization_id == pilot.organization_id,
            User.id.in_(
                {
                    user_id
                    for owner_ids in expected_owners.values()
                    for user_id in owner_ids
                }
            ),
            User.is_active.is_(True),
        )
    ).all()
    current_numbers_by_user = {
        item.id: format_e164(item.voice_forwarding_number or "") for item in users
    }
    return all(
        any(current_numbers_by_user.get(user_id) == number for user_id in owner_ids)
        for number, owner_ids in expected_owners.items()
    )


def _persist_reconciled_provider_costs(
    db: Session,
    pilot: ProspectingDialerPilot,
    legs: list[ProspectingDialLeg],
    provider_cost_items: list[dict[str, Any]],
) -> None:
    items_by_provider_call_id = {
        str(item.get("provider_call_id")): item for item in provider_cost_items
    }
    if len(items_by_provider_call_id) != len(provider_cost_items):
        raise ValueError("Provider cost evidence contains a duplicate provider call ID.")
    _, expected_provider_id_list, identity_complete = (
        _provider_identity_graph(db, pilot, legs)
    )
    expected_provider_ids = set(expected_provider_id_list)
    if (
        not identity_complete
        or len(expected_provider_id_list) != len(expected_provider_ids)
        or set(items_by_provider_call_id) != expected_provider_ids
    ):
        raise ValueError(
            "Provider cost evidence must include every billable root and seller-child "
            "call ID exactly once, with no extra, missing, or reused IDs."
        )
    for leg in legs:
        provider_call_ids = _billable_provider_call_ids(db, pilot, leg)
        if not provider_call_ids:
            continue
        leg_items = sorted(
            [items_by_provider_call_id[value] for value in provider_call_ids],
            key=lambda item: str(item["provider_call_id"]),
        )
        reconciled_cost = sum(int(item["actual_cost_cents"]) for item in leg_items)
        metadata = dict(leg.leg_metadata or {})
        existing_items = metadata.get("d10_provider_cost_items")
        if existing_items is not None and existing_items != leg_items:
            raise ProspectingDialerAcceptanceConflictError(
                f"Provider cost graph for dial leg {leg.id} conflicts with an earlier review."
            )
        if leg.actual_cost_cents is not None and leg.actual_cost_cents != reconciled_cost:
            raise ProspectingDialerAcceptanceConflictError(
                f"Provider cost rollup for dial leg {leg.id} conflicts with an earlier review."
            )
        metadata["d10_provider_cost_items"] = leg_items
        leg.leg_metadata = metadata
        leg.actual_cost_cents = reconciled_cost


def _persisted_provider_cost_graph(
    db: Session,
    pilot: ProspectingDialerPilot,
    legs: list[ProspectingDialLeg],
) -> tuple[bool, int]:
    """Verify exact per-ID provider exports and return their persisted rollup."""

    provider_started_legs, _, identity_complete = _provider_identity_graph(
        db,
        pilot,
        legs,
    )
    if not identity_complete:
        return False, 0
    total = 0
    for leg in provider_started_legs:
        provider_ids = _billable_provider_call_ids(db, pilot, leg)
        items = (leg.leg_metadata or {}).get("d10_provider_cost_items")
        if not provider_ids or not isinstance(items, list):
            return False, 0
        item_ids = [
            str(item.get("provider_call_id"))
            for item in items
            if isinstance(item, dict)
        ]
        try:
            item_costs = [int(item.get("actual_cost_cents")) for item in items]
        except (AttributeError, TypeError, ValueError):
            return False, 0
        if (
            len(item_ids) != len(items)
            or len(item_ids) != len(set(item_ids))
            or set(item_ids) != set(provider_ids)
            or any(value < 0 for value in item_costs)
            or any(
                not str(item.get("provider_reference") or "").strip()
                for item in items
            )
            or leg.actual_cost_cents != sum(item_costs)
        ):
            return False, 0
        total += sum(item_costs)
    return True, total


def get_prospecting_dialer_pilot_overview(
    db: Session,
    principal: Principal,
    *,
    settings: Settings | None = None,
    now: datetime | None = None,
) -> ProspectingDialerPilotOverviewRead:
    _require_manager(principal)
    current = _as_utc(now or datetime.now(UTC))
    pilot = db.scalar(
        select(ProspectingDialerPilot)
        .where(
            ProspectingDialerPilot.organization_id == principal.organization_id,
            ProspectingDialerPilot.status.in_(PILOT_OPEN_STATUSES | {"accepted"}),
        )
        .order_by(ProspectingDialerPilot.created_at.desc())
        .limit(1)
    )
    if pilot is None:
        pilot = db.scalar(
            select(ProspectingDialerPilot)
            .where(ProspectingDialerPilot.organization_id == principal.organization_id)
            .order_by(ProspectingDialerPilot.created_at.desc())
            .limit(1)
        )
    if pilot is None:
        return ProspectingDialerPilotOverviewRead(
            pilot=None,
            gates=[],
            attempt_review_queue=[],
            attempt_reviews=[],
            shift_reviews=[],
            current_configuration_fingerprint=None,
            configuration_matches=False,
            batch_entry_count=0,
            total_reviewed_attempts=0,
            total_passed_attempts=0,
            passed_shift_count=0,
            allowed_actions=["create"],
        )
    return _overview(db, principal, pilot, settings=settings or get_settings(), now=current)


def create_prospecting_dialer_pilot(
    db: Session,
    principal: Principal,
    payload: ProspectingDialerPilotCreate,
    *,
    settings: Settings | None = None,
) -> ProspectingDialerPilotOverviewRead:
    _require_manager(principal)
    active_settings = settings or get_settings()
    require_native_dialer_activation_enabled(active_settings)
    organization = db.scalar(
        select(Organization)
        .where(Organization.id == principal.organization_id)
        .with_for_update()
    )
    if organization is None:
        raise ValueError("The pilot organization is unavailable.")
    replay = _idempotent_pilot_replay(
        db,
        principal,
        action="prospecting.dialer_pilot_created",
        payload=payload,
    )
    if replay is not None:
        return _overview(db, principal, replay, settings=active_settings, now=datetime.now(UTC))

    open_pilot = db.scalar(
        select(ProspectingDialerPilot).where(
            ProspectingDialerPilot.organization_id == principal.organization_id,
            ProspectingDialerPilot.status.in_(PILOT_OPEN_STATUSES),
        )
    )
    if open_pilot is not None:
        raise ProspectingDialerAcceptanceConflictError(
            "Finish or roll back the current D10 pilot before creating another."
        )

    accepted_pilot = db.scalar(
        select(ProspectingDialerPilot).where(
            ProspectingDialerPilot.organization_id == principal.organization_id,
            ProspectingDialerPilot.status == "accepted",
        )
    )
    if accepted_pilot is not None:
        raise ProspectingDialerAcceptanceConflictError(
            "Revoke the current owner-accepted D10 authorization before creating another pilot."
        )

    graph = _pilot_graph(
        db,
        principal,
        caller_user_id=payload.caller_user_id,
        campaign_id=payload.campaign_id,
        cohort_id=payload.cohort_id,
        batch_id=payload.prospect_calling_batch_id,
    )
    if graph is None:
        raise ValueError("The selected pilot scope is incomplete or unavailable.")
    if graph.line.id != payload.voice_line_id:
        raise ValueError("The selected line is not the caller's dedicated prospecting line.")
    batch_entry_count = _batch_entry_count(db, graph.batch.id, graph.organization.id)
    blockers = _configuration_blockers(graph, active_settings, batch_entry_count)
    if blockers:
        raise ValueError(" ".join(blockers))

    fingerprint = pilot_configuration_fingerprint(graph, active_settings)
    pilot = ProspectingDialerPilot(
        organization_id=principal.organization_id,
        caller_user_id=graph.caller.id,
        campaign_id=graph.campaign.id,
        cohort_id=graph.cohort.id,
        prospect_calling_batch_id=graph.batch.id,
        voice_line_id=graph.line.id,
        status="draft",
        revision=1,
        effective_line_count=1,
        timezone=graph.cohort.timezone,
        required_clean_shift_count=PILOT_REQUIRED_SHIFTS,
        minimum_attempts_per_shift=PILOT_MIN_ATTEMPTS_PER_SHIFT,
        minimum_productive_minutes_per_shift=PILOT_MIN_MINUTES_PER_SHIFT,
        minimum_total_attempts=PILOT_MIN_TOTAL_ATTEMPTS,
        minimum_batch_size=PILOT_MIN_BATCH_SIZE,
        maximum_batch_size=PILOT_MAX_BATCH_SIZE,
        daily_dial_limit=graph.profile.daily_dial_limit,
        daily_spend_limit_cents=graph.profile.daily_spend_limit_cents,
        configuration_fingerprint=fingerprint,
        start_attestation={},
        smoke_test_evidence={},
        kill_switch_evidence={},
        batchdialer_comparison_evidence={},
        rollback_evidence={},
        final_evidence_snapshot={},
        created_by_user_id=principal.user_id,
        updated_by_user_id=principal.user_id,
    )
    db.add(pilot)
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise ProspectingDialerAcceptanceConflictError(
            "Another D10 pilot was created for this workspace at the same time."
        ) from exc
    _audit_mutation(
        db,
        principal,
        pilot,
        action="prospecting.dialer_pilot_created",
        payload=payload,
        previous=None,
        new={"status": pilot.status, "revision": pilot.revision},
        reason="Created controlled single-line D10 pilot.",
    )
    _commit_or_conflict(db, "The D10 pilot could not be created because its scope changed.")
    db.refresh(pilot)
    return _overview(db, principal, pilot, settings=active_settings, now=datetime.now(UTC))


def start_prospecting_dialer_pilot(
    db: Session,
    principal: Principal,
    pilot_id: UUID,
    payload: ProspectingDialerPilotStart,
    *,
    settings: Settings | None = None,
    now: datetime | None = None,
) -> ProspectingDialerPilotOverviewRead | None:
    _require_manager(principal)
    active_settings = settings or get_settings()
    require_native_dialer_activation_enabled(active_settings)
    current = _as_utc(now or datetime.now(UTC))
    replay = _idempotent_pilot_replay(
        db,
        principal,
        action="prospecting.dialer_pilot_started",
        payload=payload,
        context={"pilot_id": str(pilot_id)},
    )
    if replay is not None:
        return _overview(db, principal, replay, settings=active_settings, now=current)
    pilot = _locked_pilot(db, principal.organization_id, pilot_id)
    if pilot is None:
        return None
    replay = _idempotent_pilot_replay(
        db, principal, action="prospecting.dialer_pilot_started", payload=payload,
        context={"pilot_id": str(pilot_id)},
    )
    if replay is not None:
        return _overview(db, principal, replay, settings=active_settings, now=current)
    _expect_revision(pilot, payload.expected_revision)
    if pilot.status != "draft":
        raise ProspectingDialerAcceptanceConflictError("Only a draft D10 pilot can be started.")
    graph = _graph_for_pilot(db, principal, pilot)
    if graph is None:
        raise ValueError("The pilot's exact runtime scope is no longer available.")
    entry_count = _batch_entry_count(db, pilot.prospect_calling_batch_id, pilot.organization_id)
    blockers = _configuration_blockers(graph, active_settings, entry_count)
    blockers.extend(
        runtime_policy_blockers(
            db,
            graph,
            active_settings,
            now=current,
            for_reservation=False,
            enforce_acceptance=False,
        )
    )
    readiness = _launch_readiness(db, pilot.organization_id, active_settings, current)
    if not readiness.controlled_pilot_ready:
        blockers.extend(readiness.blockers)
    blockers = list(dict.fromkeys(blockers))
    if blockers:
        raise ValueError("Pilot start is blocked: " + " ".join(blockers))
    if pilot.configuration_fingerprint != pilot_configuration_fingerprint(graph, active_settings):
        raise ProspectingDialerAcceptanceConflictError(
            "The pilot configuration changed; create a new acceptance record."
        )
    accepted_same_configuration = db.scalar(
        select(ProspectingDialerPilot).where(
            ProspectingDialerPilot.organization_id == pilot.organization_id,
            ProspectingDialerPilot.id != pilot.id,
            ProspectingDialerPilot.caller_user_id == pilot.caller_user_id,
            ProspectingDialerPilot.campaign_id == pilot.campaign_id,
            ProspectingDialerPilot.cohort_id == pilot.cohort_id,
            ProspectingDialerPilot.prospect_calling_batch_id == pilot.prospect_calling_batch_id,
            ProspectingDialerPilot.voice_line_id == pilot.voice_line_id,
            ProspectingDialerPilot.configuration_fingerprint == pilot.configuration_fingerprint,
            ProspectingDialerPilot.status == "accepted",
        )
    )
    if accepted_same_configuration is not None:
        raise ProspectingDialerAcceptanceConflictError(
            "This exact scope and configuration is already owner-accepted. "
            "Change the controlled configuration before starting a replacement pilot."
        )

    controlled_numbers: list[str] = []
    for raw_number in payload.controlled_phone_numbers:
        normalized = format_e164(raw_number)
        if normalized is None:
            raise ValueError(
                "Every controlled smoke-test phone number must be a valid E.164 number."
            )
        if normalized not in controlled_numbers:
            controlled_numbers.append(normalized)
    if not controlled_numbers:
        raise ValueError("Provide at least one controlled smoke-test phone number.")
    active_staff = db.scalars(
        select(User).where(
            User.organization_id == pilot.organization_id,
            User.is_active.is_(True),
            User.voice_forwarding_number.is_not(None),
        )
    ).all()
    staff_number_owners: dict[str, list[str]] = {}
    for staff_user in active_staff:
        normalized_staff_number = format_e164(staff_user.voice_forwarding_number or "")
        if normalized_staff_number is not None:
            staff_number_owners.setdefault(normalized_staff_number, []).append(
                str(staff_user.id)
            )
    non_staff_numbers = sorted(set(controlled_numbers) - set(staff_number_owners))
    if non_staff_numbers:
        raise ValueError(
            "Every controlled smoke-test number must be an active Stonegate staff "
            "forwarding number. Not staff-owned: " + ", ".join(non_staff_numbers)
        )
    eligible_controlled_numbers = _eligible_batch_recipients(db, graph, current)
    missing_controlled_numbers = sorted(set(controlled_numbers) - eligible_controlled_numbers)
    if missing_controlled_numbers:
        raise ValueError(
            "Every controlled smoke-test number must be an eligible record in the exact "
            "pilot batch. Missing: " + ", ".join(missing_controlled_numbers)
        )

    previous = _pilot_state(pilot)
    batch_membership = _batch_membership_snapshot(
        db,
        pilot.organization_id,
        pilot.prospect_calling_batch_id,
    )
    pilot.status = "smoke_testing"
    pilot.started_at = current
    pilot.started_by_user_id = principal.user_id
    pilot.start_attestation = {
        "policy_version": PILOT_POLICY_VERSION,
        "controlled_numbers_only": True,
        "controlled_phone_numbers": controlled_numbers,
        "controlled_number_staff_owners": {
            number: sorted(staff_number_owners[number]) for number in controlled_numbers
        },
        "controlled_number_evidence": payload.controlled_number_evidence,
        "batchdialer_cohort_is_separate": True,
        "batchdialer_non_overlap_evidence": payload.batchdialer_non_overlap_evidence,
        "batch_entry_count": batch_membership["entry_count"],
        "batch_membership_hash": batch_membership["membership_hash"],
        "recorded_at": current.isoformat(),
        "recorded_by_user_id": str(principal.user_id),
    }
    pilot.updated_by_user_id = principal.user_id
    _increment_revision(pilot)
    organization = db.get(Organization, pilot.organization_id)
    if organization is not None:
        organization.prospecting_dialer_acceptance_required = True
    _audit_mutation(
        db,
        principal,
        pilot,
        action="prospecting.dialer_pilot_started",
        payload=payload,
        context={"pilot_id": str(pilot_id)},
        previous=previous,
        new={
            **_pilot_state(pilot),
            "start_attestation": pilot.start_attestation,
        },
        reason=payload.reason,
    )
    db.commit()
    return _overview(db, principal, pilot, settings=active_settings, now=current)


def update_prospecting_dialer_pilot_evidence(
    db: Session,
    principal: Principal,
    pilot_id: UUID,
    payload: ProspectingDialerPilotEvidenceUpdate,
    *,
    settings: Settings | None = None,
    now: datetime | None = None,
) -> ProspectingDialerPilotOverviewRead | None:
    _require_manager(principal)
    active_settings = settings or get_settings()
    require_native_dialer_activation_enabled(active_settings)
    current = _as_utc(now or datetime.now(UTC))
    replay = _idempotent_pilot_replay(
        db,
        principal,
        action="prospecting.dialer_pilot_evidence_updated",
        payload=payload,
        context={"pilot_id": str(pilot_id)},
    )
    if replay is not None:
        return _overview(db, principal, replay, settings=active_settings, now=current)
    pilot = _locked_pilot(db, principal.organization_id, pilot_id)
    if pilot is None:
        return None
    replay = _idempotent_pilot_replay(
        db, principal, action="prospecting.dialer_pilot_evidence_updated", payload=payload,
        context={"pilot_id": str(pilot_id)},
    )
    if replay is not None:
        return _overview(db, principal, replay, settings=active_settings, now=current)
    _expect_revision(pilot, payload.expected_revision)
    if pilot.status not in PILOT_MUTABLE_STATUSES:
        raise ProspectingDialerAcceptanceConflictError(
            "Evidence is locked after the pilot is submitted or closed."
        )
    previous = _pilot_state(pilot)
    updates: dict[str, object] = {}
    for field_name, value in (
        ("smoke_test_evidence", payload.smoke_test),
        ("kill_switch_evidence", payload.kill_switch),
        ("batchdialer_comparison_evidence", payload.batchdialer_comparison),
        ("rollback_evidence", payload.rollback),
    ):
        if value is not None:
            evidence = value.model_dump(mode="json")
            if field_name == "smoke_test_evidence" and not _valid_smoke_test_evidence(
                db,
                pilot,
                evidence,
                now=current,
            ):
                raise ValueError(
                    "Smoke-test call IDs must be durable call records from this exact pilot."
                )
            if field_name == "smoke_test_evidence":
                assert isinstance(value, ProspectingDialerPilotSmokeTestEvidence)
                smoke_sessions = db.scalars(
                    select(ProspectingDialSession).where(
                        ProspectingDialSession.organization_id == pilot.organization_id,
                        ProspectingDialSession.pilot_id == pilot.id,
                    )
                ).all()
                smoke_session_ids = {
                    item.id
                    for item in smoke_sessions
                    if (item.session_metadata or {}).get("acceptance_stage")
                    == "smoke_testing"
                }
                smoke_legs = (
                    db.scalars(
                        select(ProspectingDialLeg)
                        .where(
                            ProspectingDialLeg.organization_id == pilot.organization_id,
                            ProspectingDialLeg.dial_session_id.in_(smoke_session_ids),
                            ProspectingDialLeg.provider_call_id.is_not(None),
                        )
                        .with_for_update()
                    ).all()
                    if smoke_session_ids
                    else []
                )
                _persist_reconciled_provider_costs(
                    db,
                    pilot,
                    smoke_legs,
                    [item.model_dump(mode="json") for item in value.provider_cost_items],
                )
            if field_name == "kill_switch_evidence" and not _valid_kill_switch_evidence(
                db,
                pilot,
                evidence,
                now=current,
            ):
                raise ValueError(
                    "Kill-switch evidence must match audited company and campaign off/on tests."
                )
            if field_name == "kill_switch_evidence":
                assert isinstance(value, ProspectingDialerPilotKillSwitchEvidence)
                observation = _kill_switch_observation(db, pilot, value)
                if observation is None:
                    raise ValueError(
                        "Kill-switch and low dial-cap behavior could not be verified."
                    )
                evidence["server_observation"] = observation
                db.add(
                    AuditEvent(
                        organization_id=pilot.organization_id,
                        actor_user_id=principal.user_id,
                        actor_type="user",
                        action="prospecting.dialer_pilot_safety_drill_verified",
                        entity_type="prospecting_dialer_pilot",
                        entity_id=pilot.id,
                        previous_value=None,
                        new_value=observation,
                        reason=value.summary[:500],
                    )
                )
            if field_name == "rollback_evidence":
                assert isinstance(value, ProspectingDialerPilotRollbackEvidence)
                observation = _rollback_observation(db, pilot, value)
                if observation is None:
                    raise ValueError(
                        "Rollback evidence requires a later audited campaign pause/re-enable, "
                        "drained pilot session, preserved reviews, and unworked batch records."
                    )
                evidence["server_observation"] = observation
                evidence["recorded_at"] = current.isoformat()
                db.add(
                    AuditEvent(
                        organization_id=pilot.organization_id,
                        actor_user_id=principal.user_id,
                        actor_type="user",
                        action="prospecting.dialer_pilot_rollback_drill_verified",
                        entity_type="prospecting_dialer_pilot",
                        entity_id=pilot.id,
                        previous_value=None,
                        new_value=observation,
                        reason=value.summary[:500],
                    )
                )
            setattr(pilot, field_name, evidence)
            updates[field_name] = evidence
    if "smoke_test_evidence" in updates and pilot.status == "smoke_testing":
        active_sessions, active_legs = _pilot_active_runtime_counts(db, pilot)
        if active_sessions or active_legs:
            raise ProspectingDialerAcceptanceConflictError(
                "End every smoke-test session and call leg before enabling production "
                f"({active_sessions} active session(s), {active_legs} active leg(s))."
            )
        pilot.status = "running"
    pilot.updated_by_user_id = principal.user_id
    _increment_revision(pilot)
    _audit_mutation(
        db,
        principal,
        pilot,
        action="prospecting.dialer_pilot_evidence_updated",
        payload=payload,
        context={"pilot_id": str(pilot_id)},
        previous=previous,
        new={
            "status": pilot.status,
            "revision": pilot.revision,
            "evidence_sections": sorted(updates),
        },
        reason="Updated structured D10 evidence.",
    )
    db.commit()
    return _overview(db, principal, pilot, settings=active_settings, now=current)


def review_prospecting_dialer_pilot_attempt(
    db: Session,
    principal: Principal,
    pilot_id: UUID,
    attempt_id: UUID,
    payload: ProspectingDialerPilotAttemptReviewCreate,
    *,
    settings: Settings | None = None,
    now: datetime | None = None,
) -> ProspectingDialerPilotOverviewRead | None:
    _require_manager(principal)
    active_settings = settings or get_settings()
    require_native_dialer_activation_enabled(active_settings)
    current = _as_utc(now or datetime.now(UTC))
    context = {"pilot_id": str(pilot_id), "attempt_id": str(attempt_id)}
    replay = _idempotent_pilot_replay(
        db,
        principal,
        action="prospecting.dialer_pilot_attempt_reviewed",
        payload=payload,
        context=context,
    )
    if replay is not None:
        return _overview(db, principal, replay, settings=active_settings, now=current)
    pilot = _locked_pilot(db, principal.organization_id, pilot_id)
    if pilot is None:
        return None
    replay = _idempotent_pilot_replay(
        db, principal, action="prospecting.dialer_pilot_attempt_reviewed", payload=payload,
        context=context,
    )
    if replay is not None:
        return _overview(db, principal, replay, settings=active_settings, now=current)
    _expect_revision(pilot, payload.expected_revision)
    if pilot.status != "running":
        raise ProspectingDialerAcceptanceConflictError(
            "Attempt evidence can only be reviewed while the pilot is running."
        )
    attempt, session, legs = _attempt_membership(db, pilot, attempt_id)
    if attempt is None or session is None:
        raise ValueError("The attempt does not belong to this pilot's exact scope.")
    if db.scalar(
        select(ProspectingDialerPilotAttemptReview).where(
            ProspectingDialerPilotAttemptReview.organization_id == pilot.organization_id,
            ProspectingDialerPilotAttemptReview.pilot_id == pilot.id,
            ProspectingDialerPilotAttemptReview.attempt_id == attempt_id,
        )
    ):
        raise ProspectingDialerAcceptanceConflictError(
            "This attempt already has an immutable D10 review."
        )
    snapshot = _attempt_snapshot(db, pilot, attempt, session, legs, payload, current)
    if (
        snapshot["recording_review_required"]
        and PermissionKeys.ACCESS_RECORDINGS not in principal.permission_keys
    ):
        raise PermissionError(
            "Recording access is required to attest that this call recording was reviewed."
        )
    evidence_blockers: list[str] = []
    if snapshot["server_dial_leg_count"] != 1:
        evidence_blockers.append("The attempt must contain exactly one call leg.")
    if snapshot["server_terminal_leg_count"] != snapshot["server_dial_leg_count"]:
        evidence_blockers.append("The call leg must be terminal before review.")
    if not snapshot["disposition_complete"]:
        evidence_blockers.append("Save the final disposition before review.")
    if (
        snapshot["recording_review_required"]
        and not snapshot["connected_transcript_and_notes_complete"]
    ):
        evidence_blockers.append(
            "Wait for the durable recording, transcript, and structured notes before review."
        )
    if snapshot["callback_required"] and not snapshot["callback_reconciled"]:
        evidence_blockers.append("The callback schedule is not canonically reconciled.")
    if snapshot["handoff_required"] and not snapshot["handoff_reconciled"]:
        evidence_blockers.append("The exact warm handoff is not durable yet.")
    if evidence_blockers:
        raise ProspectingDialerAcceptanceConflictError(" ".join(evidence_blockers))
    passed = _attempt_snapshot_passed(snapshot)
    review = ProspectingDialerPilotAttemptReview(
        organization_id=pilot.organization_id,
        pilot_id=pilot.id,
        attempt_id=attempt.id,
        dial_session_id=session.id,
        status="passed" if passed else "failed",
        server_dial_leg_count=snapshot["server_dial_leg_count"],
        server_terminal_leg_count=snapshot["server_terminal_leg_count"],
        disposition_complete=snapshot["disposition_complete"],
        recording_review_required=snapshot["recording_review_required"],
        recording_reviewed=snapshot["recording_reviewed"],
        callback_required=snapshot["callback_required"],
        callback_reconciled=snapshot["callback_reconciled"],
        handoff_required=snapshot["handoff_required"],
        handoff_reconciled=snapshot["handoff_reconciled"],
        provider_cost_verified=snapshot["provider_cost_verified"],
        compliance_clear=snapshot["compliance_clear"],
        evidence_snapshot=snapshot,
        evidence_hash=_hash_json(snapshot),
        reviewed_by_user_id=principal.user_id,
        reviewed_at=current,
        review_reason=payload.reason,
    )
    db.add(review)
    _increment_revision(pilot)
    pilot.updated_by_user_id = principal.user_id
    _audit_mutation(
        db,
        principal,
        pilot,
        action="prospecting.dialer_pilot_attempt_reviewed",
        payload=payload,
        context=context,
        previous={"revision": payload.expected_revision},
        new={
            "revision": pilot.revision,
            "attempt_id": str(attempt.id),
            "review_status": review.status,
            "evidence_hash": review.evidence_hash,
        },
        reason=payload.reason,
    )
    _commit_or_conflict(db, "This attempt was reviewed concurrently.")
    return _overview(db, principal, pilot, settings=active_settings, now=current)


def review_prospecting_dialer_pilot_shift(
    db: Session,
    principal: Principal,
    pilot_id: UUID,
    session_id: UUID,
    payload: ProspectingDialerPilotShiftReviewCreate,
    *,
    settings: Settings | None = None,
    now: datetime | None = None,
) -> ProspectingDialerPilotOverviewRead | None:
    _require_manager(principal)
    active_settings = settings or get_settings()
    require_native_dialer_activation_enabled(active_settings)
    current = _as_utc(now or datetime.now(UTC))
    context = {"pilot_id": str(pilot_id), "session_id": str(session_id)}
    replay = _idempotent_pilot_replay(
        db,
        principal,
        action="prospecting.dialer_pilot_shift_reviewed",
        payload=payload,
        context=context,
    )
    if replay is not None:
        return _overview(db, principal, replay, settings=active_settings, now=current)
    pilot = _locked_pilot(db, principal.organization_id, pilot_id)
    if pilot is None:
        return None
    replay = _idempotent_pilot_replay(
        db, principal, action="prospecting.dialer_pilot_shift_reviewed", payload=payload,
        context=context,
    )
    if replay is not None:
        return _overview(db, principal, replay, settings=active_settings, now=current)
    _expect_revision(pilot, payload.expected_revision)
    if pilot.status != "running":
        raise ProspectingDialerAcceptanceConflictError(
            "Shift evidence can only be reviewed while the pilot is running."
        )
    if db.scalar(
        select(ProspectingDialerPilotShiftReview).where(
            ProspectingDialerPilotShiftReview.pilot_id == pilot.id,
            ProspectingDialerPilotShiftReview.shift_date == payload.shift_date,
        )
    ):
        raise ProspectingDialerAcceptanceConflictError(
            "This pilot-local shift date already has an immutable D10 review."
        )
    session = db.scalar(
        select(ProspectingDialSession).where(
            ProspectingDialSession.id == session_id,
            ProspectingDialSession.organization_id == pilot.organization_id,
            ProspectingDialSession.pilot_id == pilot.id,
        )
    )
    if session is None or not _session_matches_pilot(session, pilot):
        raise ValueError("The shift does not belong to this pilot's exact scope.")
    snapshot = _shift_snapshot(db, pilot, session, payload, current)
    if str(session.id) not in snapshot["dial_session_ids"]:
        raise ValueError(
            "The representative session has no exact pilot call on the selected local shift date."
        )
    review_ids = [UUID(value) for value in snapshot["attempt_ids"]]
    session_attempt_reviews = (
        db.scalars(
            select(ProspectingDialerPilotAttemptReview).where(
                ProspectingDialerPilotAttemptReview.organization_id
                == pilot.organization_id,
                ProspectingDialerPilotAttemptReview.pilot_id == pilot.id,
                ProspectingDialerPilotAttemptReview.attempt_id.in_(review_ids),
            )
        ).all()
        if review_ids
        else []
    )
    evidence_blockers: list[str] = []
    if not snapshot["server_session_terminal"] or not snapshot["all_legs_terminal"]:
        evidence_blockers.append("End the shift and every provider call before review.")
    if not snapshot["all_attempts_reviewed"]:
        evidence_blockers.append("Every shift attempt must pass review first.")
    if not snapshot["seller_timing_complete"]:
        evidence_blockers.append(
            "Every counted seller-child call needs signed provider duration or exact "
            "signed child start/terminal timestamps."
        )
    if not all(
        _attempt_review_live_integrity(db, pilot, item)
        for item in session_attempt_reviews
    ):
        evidence_blockers.append("An attempt review no longer matches durable evidence.")
    if not snapshot["provider_costs_reconciled"]:
        evidence_blockers.append("Provide one exact cost item for every provider call.")
    if not snapshot["daily_provider_costs_complete"]:
        evidence_blockers.append(
            "Reconcile all other provider calls on this local day before reviewing the shift."
        )
    if evidence_blockers:
        raise ProspectingDialerAcceptanceConflictError(" ".join(evidence_blockers))
    if snapshot["provider_costs_reconciled"]:
        reviewed_leg_ids = [UUID(value) for value in snapshot["dial_leg_ids"]]
        session_legs = db.scalars(
            select(ProspectingDialLeg).where(
                ProspectingDialLeg.organization_id == pilot.organization_id,
                ProspectingDialLeg.id.in_(reviewed_leg_ids),
            )
            .with_for_update()
        ).all()
        _persist_reconciled_provider_costs(
            db,
            pilot,
            session_legs,
            snapshot["provider_cost_items"],
        )
    passed = _shift_snapshot_passed(snapshot, pilot)
    review = ProspectingDialerPilotShiftReview(
        organization_id=pilot.organization_id,
        pilot_id=pilot.id,
        dial_session_id=session.id,
        shift_date=date.fromisoformat(snapshot["shift_date"]),
        timezone=pilot.timezone,
        status="passed" if passed else "failed",
        server_attempt_count=snapshot["server_attempt_count"],
        server_reviewed_attempt_count=snapshot["server_reviewed_attempt_count"],
        server_passed_attempt_count=snapshot["server_passed_attempt_count"],
        productive_minutes=snapshot["productive_minutes"],
        all_attempts_reviewed=snapshot["all_attempts_reviewed"],
        all_legs_terminal=snapshot["all_legs_terminal"],
        no_duplicate_calls=snapshot["no_duplicate_calls"],
        no_lost_answers=snapshot["no_lost_answers"],
        no_stuck_sessions=snapshot["no_stuck_sessions"],
        callbacks_reconciled=snapshot["callbacks_reconciled"],
        handoffs_reconciled=snapshot["handoffs_reconciled"],
        provider_billing_verified=snapshot["provider_billing_verified"],
        daily_caps_respected=snapshot["daily_caps_respected"],
        kill_switches_verified=snapshot["kill_switches_verified"],
        recordings_reviewed=snapshot["recordings_reviewed"],
        compliance_clear=snapshot["compliance_clear"],
        evidence_snapshot=snapshot,
        evidence_hash=_hash_json(snapshot),
        reviewed_by_user_id=principal.user_id,
        reviewed_at=current,
        review_reason=payload.reason,
    )
    db.add(review)
    _increment_revision(pilot)
    pilot.updated_by_user_id = principal.user_id
    _audit_mutation(
        db,
        principal,
        pilot,
        action="prospecting.dialer_pilot_shift_reviewed",
        payload=payload,
        context=context,
        previous={"revision": payload.expected_revision},
        new={
            "revision": pilot.revision,
            "dial_session_id": str(session.id),
            "review_status": review.status,
            "evidence_hash": review.evidence_hash,
        },
        reason=payload.reason,
    )
    _commit_or_conflict(db, "This shift was reviewed concurrently.")
    return _overview(db, principal, pilot, settings=active_settings, now=current)


def submit_prospecting_dialer_pilot(
    db: Session,
    principal: Principal,
    pilot_id: UUID,
    payload: ProspectingDialerPilotSubmit,
    *,
    settings: Settings | None = None,
    now: datetime | None = None,
) -> ProspectingDialerPilotOverviewRead | None:
    _require_manager(principal)
    active_settings = settings or get_settings()
    require_native_dialer_activation_enabled(active_settings)
    current = _as_utc(now or datetime.now(UTC))
    replay = _idempotent_pilot_replay(
        db,
        principal,
        action="prospecting.dialer_pilot_submitted",
        payload=payload,
        context={"pilot_id": str(pilot_id)},
    )
    if replay is not None:
        return _overview(db, principal, replay, settings=active_settings, now=current)
    pilot = _locked_pilot(db, principal.organization_id, pilot_id)
    if pilot is None:
        return None
    replay = _idempotent_pilot_replay(
        db, principal, action="prospecting.dialer_pilot_submitted", payload=payload,
        context={"pilot_id": str(pilot_id)},
    )
    if replay is not None:
        return _overview(db, principal, replay, settings=active_settings, now=current)
    _expect_revision(pilot, payload.expected_revision)
    if pilot.status != "running":
        raise ProspectingDialerAcceptanceConflictError("Only a running pilot can be submitted.")
    overview = _overview(db, principal, pilot, settings=active_settings, now=current)
    blockers = [gate.detail for gate in overview.gates if gate.status == "block"]
    if blockers:
        raise ProspectingDialerAcceptanceConflictError(
            "The D10 pilot is not ready for owner review: " + " ".join(blockers)
        )
    snapshot = _acceptance_snapshot(db, pilot, active_settings, current)
    evidence_hash = _hash_json(snapshot)
    previous = _pilot_state(pilot)
    pilot.final_evidence_snapshot = snapshot
    pilot.evidence_hash = evidence_hash
    pilot.status = "ready_for_owner_review"
    pilot.submitted_by_user_id = principal.user_id
    pilot.submitted_at = current
    pilot.submission_reason = payload.reason
    pilot.updated_by_user_id = principal.user_id
    _increment_revision(pilot)
    _audit_mutation(
        db,
        principal,
        pilot,
        action="prospecting.dialer_pilot_submitted",
        payload=payload,
        context={"pilot_id": str(pilot_id)},
        previous=previous,
        new={
            "status": pilot.status,
            "revision": pilot.revision,
            "evidence_hash": pilot.evidence_hash,
        },
        reason=payload.reason,
    )
    db.commit()
    return _overview(db, principal, pilot, settings=active_settings, now=current)


def rollback_prospecting_dialer_pilot(
    db: Session,
    principal: Principal,
    pilot_id: UUID,
    payload: ProspectingDialerPilotRollback,
    *,
    settings: Settings | None = None,
    now: datetime | None = None,
) -> ProspectingDialerPilotOverviewRead | None:
    _require_manager(principal)
    active_settings = settings or get_settings()
    current = _as_utc(now or datetime.now(UTC))
    replay = _idempotent_pilot_replay(
        db,
        principal,
        action="prospecting.dialer_pilot_rolled_back",
        payload=payload,
        context={"pilot_id": str(pilot_id)},
    )
    if replay is not None:
        return _overview(db, principal, replay, settings=active_settings, now=current)
    pilot = _locked_pilot(db, principal.organization_id, pilot_id)
    if pilot is None:
        return None
    replay = _idempotent_pilot_replay(
        db, principal, action="prospecting.dialer_pilot_rolled_back", payload=payload,
        context={"pilot_id": str(pilot_id)},
    )
    if replay is not None:
        return _overview(db, principal, replay, settings=active_settings, now=current)
    _expect_revision(pilot, payload.expected_revision)
    if pilot.status not in PILOT_OPEN_STATUSES:
        raise ProspectingDialerAcceptanceConflictError("This pilot is already closed.")
    if payload.confirmation_phrase != PILOT_ROLLBACK_PHRASE:
        raise ValueError(f'Type exactly "{PILOT_ROLLBACK_PHRASE}" to roll back the pilot.')
    previous = _pilot_state(pilot)
    if pilot.status == "draft":
        pilot.status = "cancelled"
        pilot.cancelled_by_user_id = principal.user_id
        pilot.cancelled_at = current
        pilot.cancellation_reason = payload.reason
    else:
        _disable_pilot_scope(
            db,
            principal,
            pilot,
            current,
            payload.reason,
            release_reason="d10_pilot_rollback",
        )
        if not pilot.final_evidence_snapshot or pilot.evidence_hash is None:
            snapshot = _acceptance_snapshot(db, pilot, active_settings, current)
            pilot.final_evidence_snapshot = snapshot
            pilot.evidence_hash = _hash_json(snapshot)
        pilot.status = "rolled_back"
        pilot.rolled_back_by_user_id = principal.user_id
        pilot.rolled_back_at = current
        pilot.rollback_reason = payload.reason
    pilot.updated_by_user_id = principal.user_id
    _increment_revision(pilot)
    organization = db.get(Organization, pilot.organization_id)
    if organization is not None:
        organization.prospecting_dialer_acceptance_required = True
    _audit_mutation(
        db,
        principal,
        pilot,
        action="prospecting.dialer_pilot_rolled_back",
        payload=payload,
        context={"pilot_id": str(pilot_id)},
        previous=previous,
        new=_pilot_state(pilot),
        reason=payload.reason,
    )
    db.commit()
    return _overview(db, principal, pilot, settings=active_settings, now=current)


def decide_prospecting_dialer_pilot(
    db: Session,
    principal: Principal,
    pilot_id: UUID,
    payload: ProspectingDialerPilotDecision,
    *,
    settings: Settings | None = None,
    now: datetime | None = None,
) -> ProspectingDialerPilotOverviewRead | None:
    _require_owner(db, principal)
    active_settings = settings or get_settings()
    if payload.decision == "accept":
        require_native_dialer_activation_enabled(active_settings)
    current = _as_utc(now or datetime.now(UTC))
    replay = _idempotent_pilot_replay(
        db,
        principal,
        action="prospecting.dialer_pilot_decided",
        payload=payload,
        context={"pilot_id": str(pilot_id)},
    )
    if replay is not None:
        return _overview(db, principal, replay, settings=active_settings, now=current)
    pilot = _locked_pilot(db, principal.organization_id, pilot_id)
    if pilot is None:
        return None
    replay = _idempotent_pilot_replay(
        db, principal, action="prospecting.dialer_pilot_decided", payload=payload,
        context={"pilot_id": str(pilot_id)},
    )
    if replay is not None:
        return _overview(db, principal, replay, settings=active_settings, now=current)
    _expect_revision(pilot, payload.expected_revision)
    if pilot.status != "ready_for_owner_review":
        raise ProspectingDialerAcceptanceConflictError(
            "Only a submitted D10 pilot can receive an owner decision."
        )
    previous = _pilot_state(pilot)
    _require_decision_confirmation(payload)
    if payload.decision == "accept":
        overview = _overview(db, principal, pilot, settings=active_settings, now=current)
        blockers = [gate.detail for gate in overview.gates if gate.status == "block"]
        if blockers:
            raise ProspectingDialerAcceptanceConflictError(
                "The evidence changed after submission: " + " ".join(blockers)
            )
        if _hash_json(pilot.final_evidence_snapshot) != pilot.evidence_hash:
            raise ProspectingDialerAcceptanceConflictError(
                "The stored final evidence snapshot no longer matches its signed hash."
            )
        recomputed = _acceptance_snapshot(db, pilot, active_settings, current)
        if _hash_json(recomputed) != pilot.evidence_hash:
            raise ProspectingDialerAcceptanceConflictError(
                "The immutable evidence snapshot no longer matches server records."
            )
        previous_acceptances = db.scalars(
            select(ProspectingDialerPilot)
            .where(
                ProspectingDialerPilot.organization_id == pilot.organization_id,
                ProspectingDialerPilot.id != pilot.id,
                ProspectingDialerPilot.caller_user_id == pilot.caller_user_id,
                ProspectingDialerPilot.campaign_id == pilot.campaign_id,
                ProspectingDialerPilot.cohort_id == pilot.cohort_id,
                ProspectingDialerPilot.prospect_calling_batch_id
                == pilot.prospect_calling_batch_id,
                ProspectingDialerPilot.voice_line_id == pilot.voice_line_id,
                ProspectingDialerPilot.status == "accepted",
            )
            .with_for_update()
        ).all()
        for previous_pilot in previous_acceptances:
            previous_pilot.status = "revoked"
            previous_pilot.revoked_by_user_id = principal.user_id
            previous_pilot.revoked_at = current
            previous_pilot.revocation_reason = (
                f"Superseded by accepted D10 pilot {pilot.id}: {payload.reason}"
            )
            previous_pilot.updated_by_user_id = principal.user_id
            _increment_revision(previous_pilot)
            db.add(
                AuditEvent(
                    organization_id=principal.organization_id,
                    actor_user_id=principal.user_id,
                    actor_type="user",
                    action="prospecting.dialer_pilot_acceptance_revoked",
                    entity_type="prospecting_dialer_pilot",
                    entity_id=previous_pilot.id,
                    previous_value={"status": "accepted"},
                    new_value={
                        "status": "revoked",
                        "replacement_pilot_id": str(pilot.id),
                    },
                    reason=previous_pilot.revocation_reason[:500],
                )
            )
        pilot.status = "accepted"
        pilot.accepted_by_user_id = principal.user_id
        pilot.accepted_at = current
        pilot.acceptance_reason = payload.reason
        organization = db.get(Organization, pilot.organization_id)
        if organization is not None:
            # Acceptance is exact-scope. The organization gate must stay on so
            # another VA/campaign/batch cannot inherit this authorization.
            organization.prospecting_dialer_acceptance_required = True
    else:
        _disable_pilot_scope(
            db,
            principal,
            pilot,
            current,
            payload.reason,
            release_reason="d10_pilot_rejection",
        )
        pilot.status = "rejected"
        pilot.rejected_by_user_id = principal.user_id
        pilot.rejected_at = current
        pilot.rejection_reason = payload.reason
        organization = db.get(Organization, pilot.organization_id)
        if organization is not None:
            organization.prospecting_dialer_acceptance_required = True
    pilot.updated_by_user_id = principal.user_id
    _increment_revision(pilot)
    _audit_mutation(
        db,
        principal,
        pilot,
        action="prospecting.dialer_pilot_decided",
        payload=payload,
        context={"pilot_id": str(pilot_id)},
        previous=previous,
        new=_pilot_state(pilot),
        reason=payload.reason,
    )
    db.commit()
    return _overview(db, principal, pilot, settings=active_settings, now=current)


def revoke_prospecting_dialer_pilot(
    db: Session,
    principal: Principal,
    pilot_id: UUID,
    payload: ProspectingDialerPilotRevoke,
    *,
    settings: Settings | None = None,
    now: datetime | None = None,
) -> ProspectingDialerPilotOverviewRead | None:
    """Owner-only emergency revocation for an exact accepted scope."""

    _require_owner(db, principal)
    active_settings = settings or get_settings()
    current = _as_utc(now or datetime.now(UTC))
    context = {"pilot_id": str(pilot_id)}
    replay = _idempotent_pilot_replay(
        db,
        principal,
        action="prospecting.dialer_pilot_acceptance_revoked",
        payload=payload,
        context=context,
    )
    if replay is not None:
        return _overview(db, principal, replay, settings=active_settings, now=current)
    pilot = _locked_pilot(db, principal.organization_id, pilot_id)
    if pilot is None:
        return None
    replay = _idempotent_pilot_replay(
        db, principal, action="prospecting.dialer_pilot_acceptance_revoked", payload=payload,
        context=context,
    )
    if replay is not None:
        return _overview(db, principal, replay, settings=active_settings, now=current)
    _expect_revision(pilot, payload.expected_revision)
    if pilot.status != "accepted":
        raise ProspectingDialerAcceptanceConflictError(
            "Only an accepted D10 authorization can be revoked."
        )
    if payload.confirmation_phrase != PILOT_REVOKE_PHRASE:
        raise ValueError(f'Type exactly "{PILOT_REVOKE_PHRASE}" to revoke the pilot.')
    previous = _pilot_state(pilot)
    drain_observation = _disable_pilot_scope(
        db,
        principal,
        pilot,
        current,
        payload.reason,
        release_reason="d10_pilot_revocation",
        drain_active_provider_calls=True,
    )
    pilot.status = "revoked"
    pilot.revoked_by_user_id = principal.user_id
    pilot.revoked_at = current
    pilot.revocation_reason = payload.reason
    pilot.updated_by_user_id = principal.user_id
    _increment_revision(pilot)
    organization = db.get(Organization, pilot.organization_id)
    if organization is not None:
        organization.prospecting_dialer_acceptance_required = True
    _audit_mutation(
        db,
        principal,
        pilot,
        action="prospecting.dialer_pilot_acceptance_revoked",
        payload=payload,
        context=context,
        previous=previous,
        new={**_pilot_state(pilot), "revocation_drain": drain_observation},
        reason=payload.reason,
    )
    db.commit()
    return _overview(db, principal, pilot, settings=active_settings, now=current)


def _overview(
    db: Session,
    principal: Principal,
    pilot: ProspectingDialerPilot,
    *,
    settings: Settings,
    now: datetime,
) -> ProspectingDialerPilotOverviewRead:
    graph = _graph_for_pilot(db, principal, pilot)
    current_fingerprint = (
        pilot_configuration_fingerprint(graph, settings) if graph is not None else None
    )
    configuration_matches = bool(
        current_fingerprint == pilot.configuration_fingerprint
        and (
            pilot.status == "draft"
            or _pilot_batch_membership_matches(db, pilot)
        )
    )
    attempt_reviews = db.scalars(
        select(ProspectingDialerPilotAttemptReview)
        .where(ProspectingDialerPilotAttemptReview.pilot_id == pilot.id)
        .order_by(ProspectingDialerPilotAttemptReview.reviewed_at.asc())
    ).all()
    shift_reviews = db.scalars(
        select(ProspectingDialerPilotShiftReview)
        .where(ProspectingDialerPilotShiftReview.pilot_id == pilot.id)
        .order_by(ProspectingDialerPilotShiftReview.shift_date.asc())
    ).all()
    queue = _attempt_review_queue(db, pilot, attempt_reviews)
    batch_entry_count = _batch_entry_count(
        db,
        pilot.prospect_calling_batch_id,
        pilot.organization_id,
    )
    gates = _pilot_gates(
        db,
        pilot,
        configuration_matches=configuration_matches,
        batch_entry_count=batch_entry_count,
        attempt_reviews=attempt_reviews,
        shift_reviews=shift_reviews,
        now=now,
    )
    return ProspectingDialerPilotOverviewRead(
        pilot=_pilot_read(db, pilot),
        gates=gates,
        attempt_review_queue=queue,
        attempt_reviews=[_attempt_review_read(item) for item in attempt_reviews],
        shift_reviews=[_shift_review_read(item) for item in shift_reviews],
        current_configuration_fingerprint=current_fingerprint,
        configuration_matches=configuration_matches,
        batch_entry_count=batch_entry_count,
        total_reviewed_attempts=len(attempt_reviews),
        total_passed_attempts=sum(item.status == "passed" for item in attempt_reviews),
        passed_shift_count=sum(item.status == "passed" for item in shift_reviews),
        allowed_actions=_allowed_actions(db, principal, pilot, gates),
    )


def _attempt_snapshot_passed(snapshot: dict[str, Any]) -> bool:
    return all(
        (
            snapshot.get("server_dial_leg_count") == 1,
            snapshot.get("server_terminal_leg_count")
            == snapshot.get("server_dial_leg_count"),
            snapshot.get("provider_identity_reconciled") is True,
            snapshot.get("contact_evidence_reconciled") is True,
            snapshot.get("disposition_complete") is True,
            snapshot.get("recording_review_required") is not True
            or snapshot.get("recording_reviewed") is True,
            snapshot.get("callback_required") is not True
            or snapshot.get("callback_reconciled") is True,
            snapshot.get("handoff_required") is not True
            or snapshot.get("handoff_reconciled") is True,
            snapshot.get("provider_cost_verified") is True,
            snapshot.get("compliance_clear") is True,
        )
    )


def _shift_snapshot_passed(
    snapshot: dict[str, Any],
    pilot: ProspectingDialerPilot,
) -> bool:
    return all(
        (
            int(snapshot.get("server_attempt_count") or 0)
            >= pilot.minimum_attempts_per_shift,
            int(snapshot.get("productive_minutes") or 0)
            >= pilot.minimum_productive_minutes_per_shift,
            snapshot.get("seller_timing_complete") is True,
            snapshot.get("all_attempts_reviewed") is True,
            snapshot.get("all_legs_terminal") is True,
            snapshot.get("no_duplicate_calls") is True,
            snapshot.get("no_lost_answers") is True,
            snapshot.get("no_stuck_sessions") is True,
            snapshot.get("callbacks_reconciled") is True,
            snapshot.get("handoffs_reconciled") is True,
            snapshot.get("provider_billing_verified") is True,
            snapshot.get("daily_caps_respected") is True,
            snapshot.get("kill_switches_verified") is True,
            snapshot.get("recordings_reviewed") is True,
            snapshot.get("compliance_clear") is True,
        )
    )


def _attempt_review_snapshot_integrity(
    review: ProspectingDialerPilotAttemptReview,
) -> bool:
    snapshot = review.evidence_snapshot or {}
    expected_columns = {
        "server_dial_leg_count": review.server_dial_leg_count,
        "server_terminal_leg_count": review.server_terminal_leg_count,
        "disposition_complete": review.disposition_complete,
        "recording_review_required": review.recording_review_required,
        "recording_reviewed": review.recording_reviewed,
        "callback_required": review.callback_required,
        "callback_reconciled": review.callback_reconciled,
        "handoff_required": review.handoff_required,
        "handoff_reconciled": review.handoff_reconciled,
        "provider_cost_verified": review.provider_cost_verified,
        "compliance_clear": review.compliance_clear,
        "review_reason": review.review_reason,
    }
    return bool(
        review.reviewed_at is not None
        and snapshot.get("pilot_id") == str(review.pilot_id)
        and snapshot.get("attempt_id") == str(review.attempt_id)
        and snapshot.get("dial_session_id") == str(review.dial_session_id)
        and snapshot.get("reviewed_at") == _as_utc(review.reviewed_at).isoformat()
        and _hash_json(snapshot) == review.evidence_hash
        and all(snapshot.get(key) == value for key, value in expected_columns.items())
        and review.status
        == ("passed" if _attempt_snapshot_passed(snapshot) else "failed")
    )


def _shift_review_snapshot_integrity(
    review: ProspectingDialerPilotShiftReview,
    pilot: ProspectingDialerPilot,
) -> bool:
    snapshot = review.evidence_snapshot or {}
    expected_columns = {
        "shift_date": review.shift_date.isoformat(),
        "timezone": review.timezone,
        "server_attempt_count": review.server_attempt_count,
        "server_reviewed_attempt_count": review.server_reviewed_attempt_count,
        "server_passed_attempt_count": review.server_passed_attempt_count,
        "productive_minutes": review.productive_minutes,
        "all_attempts_reviewed": review.all_attempts_reviewed,
        "all_legs_terminal": review.all_legs_terminal,
        "no_duplicate_calls": review.no_duplicate_calls,
        "no_lost_answers": review.no_lost_answers,
        "no_stuck_sessions": review.no_stuck_sessions,
        "callbacks_reconciled": review.callbacks_reconciled,
        "handoffs_reconciled": review.handoffs_reconciled,
        "provider_billing_verified": review.provider_billing_verified,
        "daily_caps_respected": review.daily_caps_respected,
        "kill_switches_verified": review.kill_switches_verified,
        "recordings_reviewed": review.recordings_reviewed,
        "compliance_clear": review.compliance_clear,
        "review_reason": review.review_reason,
    }
    return bool(
        review.reviewed_at is not None
        and snapshot.get("pilot_id") == str(review.pilot_id)
        and snapshot.get("dial_session_id") == str(review.dial_session_id)
        and snapshot.get("reviewed_at") == _as_utc(review.reviewed_at).isoformat()
        and _hash_json(snapshot) == review.evidence_hash
        and all(snapshot.get(key) == value for key, value in expected_columns.items())
        and review.status
        == ("passed" if _shift_snapshot_passed(snapshot, pilot) else "failed")
    )


def _attempt_review_live_integrity(
    db: Session,
    pilot: ProspectingDialerPilot,
    review: ProspectingDialerPilotAttemptReview,
) -> bool:
    if not _attempt_review_snapshot_integrity(review):
        return False
    snapshot = review.evidence_snapshot or {}
    attempt, session, legs = _attempt_membership(db, pilot, review.attempt_id)
    if attempt is None or session is None or review.dial_session_id != session.id:
        return False
    entry = db.get(ProspectCallingBatchEntry, attempt.batch_entry_id)
    released_before_provider_start = _released_before_provider_start(
        db,
        pilot,
        attempt,
        session,
        entry,
        legs,
    )
    seller_evidence_by_leg = {
        leg.id: evidence
        for leg in legs
        if (
            evidence := _seller_child_evidence(
                db,
                pilot,
                leg,
                captured_at=review.reviewed_at,
            )
        )
        is not None
    }
    placed_legs = [leg for leg in legs if leg.id in seller_evidence_by_leg]
    leg_ids = sorted(str(item.id) for item in legs)
    (
        provider_started_legs,
        raw_provider_call_ids,
        provider_identity_complete,
    ) = _provider_identity_graph(db, pilot, legs)
    provider_call_ids = sorted(raw_provider_call_ids)
    provider_identity_reconciled = bool(
        len(legs) == 1
        and released_before_provider_start != bool(provider_started_legs)
        and (
            released_before_provider_start
            or (
                provider_identity_complete
                and len(provider_started_legs) == 1
                and all(
                    (call := _exact_provider_call_record(db, pilot, leg)) is not None
                    and (
                        call.child_provider_call_id is None
                        or leg.id in seller_evidence_by_leg
                    )
                    for leg in provider_started_legs
                )
            )
        )
    )
    seller_child_evidence = [seller_evidence_by_leg[item.id] for item in placed_legs]
    contact_disposition = (
        _contact_disposition_evidence(
            attempt,
            legs[0],
            seller_evidence_by_leg.get(legs[0].id),
        )
        if len(legs) == 1 and not released_before_provider_start
        else {
            "classification": "pre_provider_release",
            "provider_connection": False,
            "right_party_contact": False,
            "reconciled": released_before_provider_start,
        }
    )
    contact_evidence_reconciled = contact_disposition["reconciled"] is True
    call_record_ids = sorted(str(item.call_record_id) for item in legs if item.call_record_id)
    if (
        sorted(snapshot.get("dial_leg_ids") or []) != leg_ids
        or snapshot.get("provider_call_ids") != provider_call_ids
        or sorted(snapshot.get("call_record_ids") or []) != call_record_ids
        or snapshot.get("released_before_provider_start")
        is not released_before_provider_start
        or snapshot.get("provider_started") is not bool(provider_started_legs)
        or snapshot.get("provider_identity_reconciled")
        is not provider_identity_reconciled
        or snapshot.get("placed_call") is not bool(placed_legs)
        or snapshot.get("seller_child_evidence") != seller_child_evidence
        or snapshot.get("contact_classification")
        != contact_disposition["classification"]
        or snapshot.get("provider_connection_evidence")
        is not contact_disposition["provider_connection"]
        or snapshot.get("right_party_contact")
        is not contact_disposition["right_party_contact"]
        or snapshot.get("contact_evidence_reconciled")
        is not contact_evidence_reconciled
        or attempt.status != snapshot.get("attempt_status")
        or attempt.outcome != snapshot.get("attempt_outcome")
        or attempt.completed_at is None
        or review.reviewed_at is None
        or _as_utc(attempt.completed_at) > _as_utc(review.reviewed_at)
        or any(
            leg.status not in DIAL_LEG_TERMINAL_STATUSES
            or leg.completed_at is None
            or _as_utc(leg.completed_at) > _as_utc(review.reviewed_at)
            for leg in legs
        )
    ):
        return False
    if snapshot.get("callback_required"):
        callback_at = _as_utc(attempt.callback_at) if attempt.callback_at else None
        callback_schedule = (attempt.measurement_metadata or {}).get("callback_schedule")
        schedule_at = (
            _evidence_datetime(callback_schedule, "callback_at")
            if isinstance(callback_schedule, dict)
            else None
        )
        if (
            callback_at is None
            or callback_at.isoformat() != snapshot.get("callback_at")
            or schedule_at != callback_at
            or callback_schedule.get("priority") != "due_callback_before_retry_or_new"
        ):
            return False
    if snapshot.get("handoff_required"):
        handoff_count = (
            db.scalar(
                select(func.count(ProspectHandoff.id)).where(
                    ProspectHandoff.organization_id == pilot.organization_id,
                    ProspectHandoff.attempt_id == attempt.id,
                )
            )
            or 0
        )
        if handoff_count != snapshot.get("handoff_count"):
            return False
    if snapshot.get("recording_review_required"):
        expected_call_record_ids = {item.call_record_id for item in legs if item.call_record_id}
        recordings = db.scalars(
            select(CallRecording).where(
                CallRecording.organization_id == pilot.organization_id,
                CallRecording.call_record_id.in_(expected_call_record_ids),
                CallRecording.deleted_at.is_(None),
            )
        ).all()
        recordings = sorted(recordings, key=lambda item: str(item.id))
        if {item.call_record_id for item in recordings} != expected_call_record_ids:
            return False
        if [str(item.id) for item in recordings] != snapshot.get("recording_ids"):
            return False
        legs_by_call_record_id = {
            item.call_record_id: item for item in legs if item.call_record_id is not None
        }
        if _recording_identity_snapshot(
            db,
            pilot,
            recordings,
            legs_by_call_record_id,
            captured_at=review.reviewed_at,
        ) != snapshot.get("recording_identities"):
            return False
        if any(
            item.call_record_id not in legs_by_call_record_id
            or not _recording_matches_pilot_leg(
                db,
                pilot,
                item,
                legs_by_call_record_id[item.call_record_id],
                captured_at=review.reviewed_at,
            )
            for item in recordings
        ):
            return False
        transcripts = db.scalars(
            select(CallTranscript).where(
                CallTranscript.organization_id == pilot.organization_id,
                CallTranscript.recording_id.in_([item.id for item in recordings]),
                CallTranscript.status.in_(("completed", "approved")),
                CallTranscript.transcript_text.is_not(None),
            )
        ).all()
        transcripts = sorted(transcripts, key=lambda item: str(item.id))
        if len(transcripts) != len(recordings) or any(
            not (item.transcript_text or "").strip()
            or not (item.transcript_metadata or {}).get("structured_notes")
            for item in transcripts
        ):
            return False
        if (
            [str(item.id) for item in transcripts] != snapshot.get("transcript_ids")
            or [item.status for item in transcripts]
            != snapshot.get("transcript_statuses")
        ):
            return False
    return True


def _shift_review_live_integrity(
    db: Session,
    pilot: ProspectingDialerPilot,
    review: ProspectingDialerPilotShiftReview,
    attempt_reviews_by_id: dict[UUID, ProspectingDialerPilotAttemptReview],
) -> bool:
    if not _shift_review_snapshot_integrity(review, pilot):
        return False
    snapshot = review.evidence_snapshot or {}
    session = db.scalar(
        select(ProspectingDialSession).where(
            ProspectingDialSession.id == review.dial_session_id,
            ProspectingDialSession.organization_id == pilot.organization_id,
            ProspectingDialSession.pilot_id == pilot.id,
        )
    )
    if session is None or not _session_matches_pilot(session, pilot):
        return False
    snapshot_session_ids = {
        UUID(value) for value in (snapshot.get("dial_session_ids") or [])
    }
    sessions = (
        db.scalars(
            select(ProspectingDialSession).where(
                ProspectingDialSession.organization_id == pilot.organization_id,
                ProspectingDialSession.pilot_id == pilot.id,
                ProspectingDialSession.id.in_(snapshot_session_ids),
            )
        ).all()
        if snapshot_session_ids
        else []
    )
    legs = db.scalars(
        select(ProspectingDialLeg).where(
            ProspectingDialLeg.organization_id == pilot.organization_id,
            ProspectingDialLeg.dial_session_id.in_(snapshot_session_ids),
            ProspectingDialLeg.id.in_(
                [UUID(value) for value in (snapshot.get("dial_leg_ids") or [])]
            ),
        )
    ).all()
    _, day_start, day_end = _local_date_bounds(review.shift_date, pilot.timezone)
    daily_reservation_legs = db.scalars(
        select(ProspectingDialLeg)
        .join(
            ProspectingDialSession,
            ProspectingDialSession.id == ProspectingDialLeg.dial_session_id,
        )
        .where(
            ProspectingDialSession.organization_id == pilot.organization_id,
            ProspectingDialSession.pilot_id == pilot.id,
            ProspectingDialLeg.queued_at >= day_start,
            ProspectingDialLeg.queued_at < day_end,
        )
    ).all()
    attempt_ids = {item.attempt_id for item in legs if item.attempt_id is not None}
    seller_evidence_by_leg = {
        item.id: evidence
        for item in legs
        if (
            evidence := _seller_child_evidence(
                db,
                pilot,
                item,
                captured_at=review.reviewed_at,
            )
        )
        is not None
    }
    placed_legs = [item for item in legs if item.id in seller_evidence_by_leg]
    (
        provider_started_legs,
        raw_billable_provider_call_ids,
        provider_identity_complete,
    ) = _provider_identity_graph(db, pilot, legs)
    billable_provider_call_ids = set(raw_billable_provider_call_ids)
    (
        _,
        raw_daily_billable_provider_call_ids,
        daily_provider_identity_complete,
    ) = _provider_identity_graph(db, pilot, daily_reservation_legs)
    daily_billable_provider_call_ids = set(raw_daily_billable_provider_call_ids)
    placed_attempt_ids = {
        item.attempt_id for item in placed_legs if item.attempt_id is not None
    }
    if (
        sorted(snapshot.get("dial_leg_ids") or []) != sorted(str(item.id) for item in legs)
        or sorted(snapshot.get("daily_reservation_dial_leg_ids") or [])
        != sorted(str(item.id) for item in daily_reservation_legs)
        or sorted(snapshot.get("attempt_ids") or []) != sorted(str(item) for item in attempt_ids)
        or sorted(snapshot.get("placed_dial_leg_ids") or [])
        != sorted(str(item.id) for item in placed_legs)
        or sorted(snapshot.get("placed_attempt_ids") or [])
        != sorted(str(item) for item in placed_attempt_ids)
        or sorted(snapshot.get("provider_started_dial_leg_ids") or [])
        != sorted(str(item.id) for item in provider_started_legs)
        or sorted(snapshot.get("billable_provider_call_ids") or [])
        != sorted(billable_provider_call_ids)
        or sorted(snapshot.get("daily_billable_provider_call_ids") or [])
        != sorted(daily_billable_provider_call_ids)
        or snapshot.get("provider_identity_complete") is not provider_identity_complete
        or snapshot.get("daily_provider_identity_complete")
        is not daily_provider_identity_complete
        or len(raw_billable_provider_call_ids) != len(billable_provider_call_ids)
        or len(raw_daily_billable_provider_call_ids)
        != len(daily_billable_provider_call_ids)
        or snapshot.get("seller_child_evidence")
        != [
            seller_evidence_by_leg[item.id]
            for item in sorted(placed_legs, key=lambda value: str(value.id))
        ]
        or len(sessions) != len(snapshot_session_ids)
        or review.dial_session_id not in snapshot_session_ids
        or any(
            (item.session_metadata or {}).get("acceptance_stage") != "running"
            for item in sessions
        )
        or snapshot.get("reserved_attempt_count") != len(attempt_ids)
        or snapshot.get("reserved_dial_leg_count") != len(legs)
        or snapshot.get("provider_started_attempt_count")
        != len(
            {
                item.attempt_id
                for item in provider_started_legs
                if item.attempt_id is not None
            }
        )
        or snapshot.get("placed_call_count") != len(placed_legs)
        or snapshot.get("daily_reserved_dial_count") != len(daily_reservation_legs)
        or snapshot.get("daily_dial_count") != len(daily_reservation_legs)
        or any(item.attempt_id is None for item in daily_reservation_legs)
        or any(
            item.state not in TERMINAL_DIAL_SESSION_STATES or item.ended_at is None
            for item in sessions
        )
        or any(
            item.attempt_id is None
            or item.status not in DIAL_LEG_TERMINAL_STATUSES
            or item.completed_at is None
            or not (day_start <= _as_utc(item.queued_at) < day_end)
            for item in legs
        )
    ):
        return False
    provider_items = snapshot.get("provider_cost_items") or []
    if not isinstance(provider_items, list):
        return False
    expected_costs = {
        item.get("provider_call_id"): item.get("actual_cost_cents")
        for item in provider_items
        if isinstance(item, dict)
    }
    if (
        len(expected_costs) != len(provider_items)
        or set(expected_costs) != billable_provider_call_ids
        or any(
            not str(item.get("provider_reference") or "").strip()
            for item in provider_items
            if isinstance(item, dict)
        )
    ):
        return False
    for item in provider_started_legs:
        provider_ids = _billable_provider_call_ids(db, pilot, item)
        expected_items = sorted(
            [
                provider_item
                for provider_item in provider_items
                if provider_item.get("provider_call_id") in provider_ids
            ],
            key=lambda provider_item: str(provider_item.get("provider_call_id")),
        )
        if (
            (item.leg_metadata or {}).get("d10_provider_cost_items") != expected_items
            or item.actual_cost_cents
            != sum(int(provider_item["actual_cost_cents"]) for provider_item in expected_items)
        ):
            return False
    daily_costs_complete, daily_spend = _persisted_provider_cost_graph(
        db,
        pilot,
        daily_reservation_legs,
    )
    daily_caps_respected = bool(
        daily_costs_complete
        and len(daily_reservation_legs) <= pilot.daily_dial_limit
        and daily_spend <= pilot.daily_spend_limit_cents
    )
    if (
        snapshot.get("daily_provider_costs_complete") is not daily_costs_complete
        or snapshot.get("daily_spend_cents") != daily_spend
        or snapshot.get("daily_caps_respected") is not daily_caps_respected
    ):
        return False
    return all(
        attempt_id in attempt_reviews_by_id
        and _attempt_review_live_integrity(db, pilot, attempt_reviews_by_id[attempt_id])
        for attempt_id in attempt_ids
    )


def _pilot_session_evidence(
    db: Session,
    pilot: ProspectingDialerPilot,
) -> tuple[list[ProspectingDialSession], list[ProspectingDialSession], bool]:
    statement = (
        select(ProspectingDialSession)
        .join(
            ProspectingDialLeg,
            ProspectingDialLeg.dial_session_id == ProspectingDialSession.id,
        )
        .where(
            ProspectingDialSession.organization_id == pilot.organization_id,
            ProspectingDialSession.pilot_id == pilot.id,
        )
        .distinct()
    )
    if pilot.submitted_at is not None:
        statement = statement.where(
            ProspectingDialLeg.queued_at <= _as_utc(pilot.submitted_at)
        )
    sessions = db.scalars(statement).all()
    smoke_completed_at = _evidence_datetime(pilot.smoke_test_evidence, "completed_at")
    if smoke_completed_at is None:
        return sessions, [], False
    smoke_call_ids = {
        str(value) for value in (pilot.smoke_test_evidence or {}).get("call_record_ids", [])
    }
    smoke_sessions: list[ProspectingDialSession] = []
    production_sessions: list[ProspectingDialSession] = []
    safely_partitioned = True
    for session in sessions:
        stage = (session.session_metadata or {}).get("acceptance_stage")
        if stage == "smoke_testing":
            smoke_sessions.append(session)
        elif stage == "running" or _as_utc(session.started_at) > smoke_completed_at:
            production_sessions.append(session)
        else:
            smoke_sessions.append(session)
        if session in smoke_sessions:
            legs = db.scalars(
                select(ProspectingDialLeg).where(
                    ProspectingDialLeg.organization_id == pilot.organization_id,
                    ProspectingDialLeg.dial_session_id == session.id,
                )
            ).all()

            def smoke_leg_safely_partitioned(item: ProspectingDialLeg) -> bool:
                seller_evidence = _seller_child_evidence(
                    db,
                    pilot,
                    item,
                    captured_at=smoke_completed_at,
                )
                has_contact_evidence = bool(
                    seller_evidence
                    and seller_evidence.get("contact_evidence") is True
                )
                selected_for_smoke = bool(
                    item.call_record_id is not None
                    and str(item.call_record_id) in smoke_call_ids
                )
                return bool(
                    item.status in DIAL_LEG_TERMINAL_STATUSES
                    and item.completed_at is not None
                    and (
                        (
                            not has_contact_evidence
                            and item.answered_at is None
                            and item.connected_at is None
                        )
                        or selected_for_smoke
                    )
                    and format_e164(item.recipient) in _pilot_controlled_numbers(pilot)
                )

            safely_partitioned = bool(
                safely_partitioned
                and session.state in TERMINAL_DIAL_SESSION_STATES
                and session.ended_at is not None
                and _as_utc(session.ended_at) <= smoke_completed_at
                and all(smoke_leg_safely_partitioned(item) for item in legs)
            )
    return smoke_sessions, production_sessions, safely_partitioned


def _global_pilot_call_integrity(
    db: Session,
    pilot: ProspectingDialerPilot,
) -> tuple[bool, bool]:
    statement = (
        select(ProspectingDialLeg)
        .join(
            ProspectingDialSession,
            ProspectingDialSession.id == ProspectingDialLeg.dial_session_id,
        )
        .where(
            ProspectingDialSession.organization_id == pilot.organization_id,
            ProspectingDialSession.pilot_id == pilot.id,
        )
    )
    if pilot.submitted_at is not None:
        statement = statement.where(
            ProspectingDialLeg.queued_at <= _as_utc(pilot.submitted_at)
        )
    legs = db.scalars(statement).all()
    captured_at = _as_utc(pilot.submitted_at or datetime.now(UTC))
    session_ids = {leg.dial_session_id for leg in legs}
    sessions_by_id = {
        session.id: session
        for session in (
            db.scalars(
                select(ProspectingDialSession).where(
                    ProspectingDialSession.organization_id == pilot.organization_id,
                    ProspectingDialSession.id.in_(session_ids),
                )
            ).all()
            if session_ids
            else []
        )
    }
    by_date: dict[date, list[ProspectingDialLeg]] = {}
    for leg in legs:
        shift_date, _, _ = _local_shift_bounds(leg.queued_at, pilot.timezone)
        by_date.setdefault(shift_date, []).append(leg)
    costs_complete, _ = _persisted_provider_cost_graph(db, pilot, legs)
    caps_and_duplicates_clear = True
    for day_legs in by_date.values():
        day_provider_legs = [
            leg for leg in day_legs if leg.provider_call_id is not None
        ]
        seller_legs = [
            leg
            for leg in day_legs
            if (
                leg.dial_session_id in sessions_by_id
                and (sessions_by_id[leg.dial_session_id].session_metadata or {}).get(
                    "acceptance_stage"
                )
                == "running"
                and _is_placed_leg(db, pilot, leg, captured_at=captured_at)
            )
        ]
        normalized_recipients = [format_e164(leg.recipient) for leg in seller_legs]
        if not (
            all(leg.attempt_id is not None for leg in day_legs)
            and len(day_legs) <= pilot.daily_dial_limit
            and sum(leg.actual_cost_cents or 0 for leg in day_provider_legs)
            <= pilot.daily_spend_limit_cents
            and len({leg.prospect_id for leg in seller_legs}) == len(seller_legs)
            and len({leg.batch_entry_id for leg in seller_legs}) == len(seller_legs)
            and all(normalized_recipients)
            and len(normalized_recipients) == len(set(normalized_recipients))
        ):
            caps_and_duplicates_clear = False
            break
    return costs_complete, caps_and_duplicates_clear


def _has_clean_shift_after_rollback(
    passed_shifts: list[ProspectingDialerPilotShiftReview],
    rollback_tested_at: datetime | None,
    timezone_name: str,
) -> bool:
    """Require a full passed local operating date after the rollback drill date."""

    if rollback_tested_at is None:
        return False
    rollback_local_date, _, _ = _local_shift_bounds(
        rollback_tested_at,
        timezone_name,
    )
    return any(item.shift_date > rollback_local_date for item in passed_shifts)


def _pilot_gates(
    db: Session,
    pilot: ProspectingDialerPilot,
    *,
    configuration_matches: bool,
    batch_entry_count: int,
    attempt_reviews: list[ProspectingDialerPilotAttemptReview],
    shift_reviews: list[ProspectingDialerPilotShiftReview],
    now: datetime,
) -> list[ProspectingDialerPilotGateRead]:
    _, production_sessions, sessions_safely_partitioned = _pilot_session_evidence(db, pilot)
    production_session_ids = {item.id for item in production_sessions}
    attempt_reviews_by_id = {item.attempt_id: item for item in attempt_reviews}
    review_integrity = bool(
        all(_attempt_review_live_integrity(db, pilot, item) for item in attempt_reviews)
        and all(
            _shift_review_live_integrity(db, pilot, item, attempt_reviews_by_id)
            for item in shift_reviews
        )
    )
    passed_shifts = [
        item
        for item in shift_reviews
        if item.status == "passed" and item.dial_session_id in production_session_ids
    ]
    passed_dates = {item.shift_date for item in passed_shifts}
    total_attempts = sum(item.server_attempt_count for item in passed_shifts)
    reviewed_production_session_ids = {
        UUID(session_id)
        for item in passed_shifts
        for session_id in (item.evidence_snapshot or {}).get("dial_session_ids", [])
    }
    every_production_session_passed = bool(
        production_session_ids
        and reviewed_production_session_ids == production_session_ids
    )
    provider_costs_complete, global_caps_and_duplicates_clear = _global_pilot_call_integrity(
        db,
        pilot,
    )
    rollback_tested_at = _evidence_datetime(pilot.rollback_evidence, "tested_at")
    clean_after_rollback = _has_clean_shift_after_rollback(
        passed_shifts,
        rollback_tested_at,
        pilot.timezone,
    )
    active_session_statement = select(func.count(ProspectingDialSession.id)).where(
        ProspectingDialSession.organization_id == pilot.organization_id,
        ProspectingDialSession.pilot_id == pilot.id,
        ProspectingDialSession.ended_at.is_(None),
    )
    active_leg_statement = (
        select(func.count(ProspectingDialLeg.id))
        .join(
            ProspectingDialSession,
            ProspectingDialSession.id == ProspectingDialLeg.dial_session_id,
        )
        .where(
            ProspectingDialSession.organization_id == pilot.organization_id,
            ProspectingDialSession.pilot_id == pilot.id,
            ProspectingDialLeg.completed_at.is_(None),
        )
    )
    attempt_count_statement = (
        select(func.count(func.distinct(ProspectingAttempt.id)))
        .join(ProspectingDialLeg, ProspectingDialLeg.attempt_id == ProspectingAttempt.id)
        .join(
            ProspectingDialSession,
            ProspectingDialSession.id == ProspectingDialLeg.dial_session_id,
        )
        .where(
            ProspectingAttempt.organization_id == pilot.organization_id,
            ProspectingDialSession.organization_id == pilot.organization_id,
            ProspectingDialSession.pilot_id == pilot.id,
        )
    )
    if pilot.submitted_at is not None:
        cutoff = _as_utc(pilot.submitted_at)
        active_session_statement = active_session_statement.where(
            ProspectingDialSession.started_at <= cutoff
        )
        active_leg_statement = active_leg_statement.where(
            ProspectingDialLeg.queued_at <= cutoff
        )
        attempt_count_statement = attempt_count_statement.where(
            ProspectingDialLeg.queued_at <= cutoff
        )
    active_sessions = db.scalar(active_session_statement) or 0
    active_legs = db.scalar(active_leg_statement) or 0
    pilot_attempt_count = db.scalar(attempt_count_statement) or 0
    every_attempt_passed = bool(
        pilot_attempt_count
        and len(attempt_reviews) == pilot_attempt_count
        and all(item.status == "passed" for item in attempt_reviews)
    )

    def gate(key: str, label: str, passed: bool, yes: str, no: str):
        return ProspectingDialerPilotGateRead(
            key=key,
            label=label,
            status="pass" if passed else "block",
            detail=yes if passed else no,
        )

    return [
        gate(
            "configuration",
            "Exact one-line configuration",
            configuration_matches,
            "The current runtime configuration matches the pilot fingerprint.",
            "The VA, campaign, cohort, batch, line, caps, or recording policy changed.",
        ),
        gate(
            "batch_size",
            "Controlled batch size",
            pilot.minimum_batch_size <= batch_entry_count <= pilot.maximum_batch_size,
            f"The controlled batch contains {batch_entry_count} records.",
            f"The controlled batch must contain {pilot.minimum_batch_size}–"
            f"{pilot.maximum_batch_size} records; it currently has {batch_entry_count}.",
        ),
        gate(
            "smoke_test",
            "Controlled-number smoke test",
            _valid_smoke_test_evidence(db, pilot, pilot.smoke_test_evidence, now=now),
            "Controlled-number smoke-test evidence is present.",
            "Add a completed controlled-number smoke test with durable call record IDs.",
        ),
        gate(
            "kill_switches",
            "Kill switches",
            _valid_kill_switch_evidence(db, pilot, pilot.kill_switch_evidence, now=now),
            "Company and campaign kill-switch evidence is present.",
            "Test and document both company and campaign kill switches.",
        ),
        gate(
            "batchdialer_separation",
            "BatchDialer separation",
            _valid_batch_comparison_evidence(pilot.batchdialer_comparison_evidence),
            "A separate, non-overlapping BatchDialer comparison is documented.",
            "Document a separate BatchDialer cohort with zero overlapping records.",
        ),
        gate(
            "rollback_drill",
            "Rollback drill",
            _valid_rollback_evidence(db, pilot, pilot.rollback_evidence, now=now),
            "The rollback procedure is documented and tested.",
            "Document the campaign pause, session stop, cohort return, and "
            "evidence retention drill.",
        ),
        gate(
            "every_attempt_reviewed",
            "Every pilot attempt reviewed",
            every_attempt_passed and review_integrity,
            f"All {pilot_attempt_count} pilot attempts have passed immutable review.",
            f"Every pilot attempt must pass review; {len(attempt_reviews)} of "
            f"{pilot_attempt_count} have a review.",
        ),
        gate(
            "review_integrity",
            "Immutable review evidence",
            review_integrity,
            "Every attempt and shift review matches its hash, stored columns, and durable facts.",
            "A review no longer matches its immutable snapshot or durable call evidence.",
        ),
        gate(
            "session_stage_separation",
            "Smoke and production sessions separated",
            sessions_safely_partitioned,
            "Controlled smoke sessions ended before production sessions began.",
            "A smoke session crossed into production or includes unlisted call evidence.",
        ),
        gate(
            "every_production_session_reviewed",
            "Every production session reviewed",
            every_production_session_passed,
            f"All {len(production_session_ids)} production sessions passed shift review.",
            "Every production session containing calls must pass an immutable shift review.",
        ),
        gate(
            "provider_cost_reconciliation",
            "Provider cost reconciliation",
            provider_costs_complete and global_caps_and_duplicates_clear,
            "Every production call has reconciled provider cost and global daily caps pass.",
            "Reconcile every production call cost and resolve daily spend or "
            "duplicate-call issues.",
        ),
        gate(
            "clean_shifts",
            "Three clean shifts",
            len(passed_shifts) >= pilot.required_clean_shift_count
            and len(passed_dates) >= pilot.required_clean_shift_count,
            f"{len(passed_shifts)} clean shifts passed on distinct local dates.",
            f"Complete {pilot.required_clean_shift_count} passed shifts on distinct local dates; "
            f"{len(passed_shifts)} currently pass.",
        ),
        gate(
            "attempt_volume",
            "Minimum reviewed attempt volume",
            total_attempts >= pilot.minimum_total_attempts,
            f"Passed shifts include {total_attempts} fully reviewed attempts.",
            f"Passed shifts need at least {pilot.minimum_total_attempts} attempts; "
            f"{total_attempts} currently qualify.",
        ),
        gate(
            "post_rollback_shift",
            "Clean shift after rollback drill",
            clean_after_rollback,
            "At least one passed shift occurred on a later local date than the rollback drill.",
            "Run and pass a complete local-date shift after the documented rollback drill day.",
        ),
        gate(
            "sessions_terminal",
            "No active pilot calls",
            active_sessions == 0 and active_legs == 0,
            "All pilot sessions and call legs are terminal.",
            f"Finish the remaining {active_sessions} session(s) and {active_legs} call leg(s).",
        ),
    ]


def _datetime_matches_reservation_snapshot(
    actual: datetime | None,
    raw: object,
) -> bool:
    if raw is None:
        return actual is None
    if not isinstance(raw, str):
        return False
    try:
        expected = _as_utc(datetime.fromisoformat(raw))
    except ValueError:
        return False
    return actual is not None and _as_utc(actual) == expected


def _released_before_provider_start(
    db: Session,
    pilot: ProspectingDialerPilot,
    attempt: ProspectingAttempt,
    session: ProspectingDialSession,
    entry: ProspectCallingBatchEntry | None,
    legs: list[ProspectingDialLeg],
) -> bool:
    """Recognize only the coordinator's exact, reversible pre-provider release.

    These reservations remain part of the immutable every-attempt audit, but they
    are never provider-started calls and therefore never increase placed-call,
    productivity, billing, or duplicate-call outcome metrics.
    """

    if entry is None or len(legs) != 1:
        return False
    leg = legs[0]
    metadata = leg.leg_metadata or {}
    snapshot = metadata.get("reservation_snapshot")
    release_reason = metadata.get("reservation_release_reason")
    released_at = _evidence_datetime(metadata, "reservation_released_at")
    if not isinstance(snapshot, dict) or not isinstance(release_reason, str):
        return False
    if not release_reason.strip() or released_at is None:
        return False
    required_snapshot_keys = {
        "status",
        "disposition",
        "next_attempt_at",
        "completed_at",
        "attempt_count",
    }
    snapshot_attempt_count = snapshot.get("attempt_count")
    entry_restored = bool(
        required_snapshot_keys.issubset(snapshot)
        and isinstance(snapshot.get("status"), str)
        and snapshot.get("status") in {"queued", "ready", "needs_correction"}
        and (
            snapshot.get("disposition") is None
            or isinstance(snapshot.get("disposition"), str)
        )
        and isinstance(snapshot_attempt_count, int)
        and snapshot_attempt_count >= 0
        and entry.status == snapshot.get("status")
        and entry.disposition == snapshot.get("disposition")
        and entry.attempt_count == snapshot_attempt_count
        and _datetime_matches_reservation_snapshot(
            entry.next_attempt_at,
            snapshot.get("next_attempt_at"),
        )
        and _datetime_matches_reservation_snapshot(
            entry.completed_at,
            snapshot.get("completed_at"),
        )
    )
    release_terminal = bool(
        attempt.status == "cancelled"
        and attempt.outcome == "technical_failure"
        and attempt.contact_made is False
        and attempt.callback_at is None
        and attempt.completed_at is not None
        and _as_utc(attempt.completed_at) == released_at
        and attempt.notes
        == f"Reservation released before provider start: {release_reason}"[:2000]
        and leg.status == "cancelled"
        and leg.completed_at is not None
        and _as_utc(leg.completed_at) == released_at
        and leg.cancelled_at is not None
        and _as_utc(leg.cancelled_at) == released_at
        and leg.terminal_result == "cancelled"
        and leg.cancellation_reason == release_reason[:255]
        and leg.provider_error_code is None
        and leg.provider_error_message is None
        and leg.reserved_cost_cents == 0
        and leg.actual_cost_cents == 0
    )
    no_provider_evidence = bool(
        attempt.provider_call_id is None
        and attempt.provider_recording_id is None
        and attempt.provider_agent_id is None
        and attempt.answered_at is None
        and attempt.right_party_confirmed_at is None
        and attempt.interest_confirmed_at is None
        and leg.provider_call_id is None
        and leg.provider_recording_id is None
        and leg.last_provider_event_sequence == 0
        and leg.last_provider_event_at is None
        and leg.dialing_at is None
        and leg.ringing_at is None
        and leg.answered_at is None
        and leg.connected_at is None
        and session.current_attempt_id != attempt.id
        and session.current_batch_entry_id != attempt.batch_entry_id
        and session.current_prospect_id != attempt.prospect_id
        and not db.scalar(
            select(func.count(ProspectingProviderEvent.id)).where(
                ProspectingProviderEvent.organization_id == pilot.organization_id,
                or_(
                    ProspectingProviderEvent.attempt_id == attempt.id,
                    ProspectingProviderEvent.dial_leg_id == leg.id,
                ),
            )
        )
    )
    if not (entry_restored and release_terminal and no_provider_evidence):
        return False

    # D4 may have prepared a local call graph before Twilio dispatch. That graph
    # is allowed only when every node proves it terminated without provider IDs.
    if leg.call_record_id is None:
        linked_call_count = db.scalar(
            select(func.count(CallRecord.id)).where(
                CallRecord.organization_id == pilot.organization_id,
                or_(
                    CallRecord.prospecting_attempt_id == attempt.id,
                    CallRecord.prospecting_dial_leg_id == leg.id,
                ),
            )
        )
        linked_intent_count = db.scalar(
            select(func.count(VoiceCallIntent.id)).where(
                VoiceCallIntent.organization_id == pilot.organization_id,
                or_(
                    VoiceCallIntent.prospecting_attempt_id == attempt.id,
                    VoiceCallIntent.prospecting_dial_leg_id == leg.id,
                ),
            )
        )
        return bool(
            attempt.call_record_id is None
            and not linked_call_count
            and not linked_intent_count
        )
    if attempt.call_record_id != leg.call_record_id:
        return False
    call = db.scalar(
        select(CallRecord).where(
            CallRecord.id == leg.call_record_id,
            CallRecord.organization_id == pilot.organization_id,
            CallRecord.prospect_id == attempt.prospect_id,
            CallRecord.prospecting_attempt_id == attempt.id,
            CallRecord.prospecting_dial_leg_id == leg.id,
        )
    )
    if (
        call is None
        or call.provider_call_id is not None
        or call.child_provider_call_id is not None
        or call.status not in {"cancelled", "failed"}
        or call.answered_at is not None
        or call.duration_seconds is not None
        or call.disposition is not None
        or call.ended_at is None
        or _as_utc(call.ended_at) != released_at
        or call.call_intent_id is None
    ):
        return False
    intent = db.scalar(
        select(VoiceCallIntent).where(
            VoiceCallIntent.id == call.call_intent_id,
            VoiceCallIntent.organization_id == pilot.organization_id,
            VoiceCallIntent.prospect_id == attempt.prospect_id,
            VoiceCallIntent.prospecting_attempt_id == attempt.id,
            VoiceCallIntent.prospecting_dial_leg_id == leg.id,
        )
    )
    recording_count = db.scalar(
        select(func.count(CallRecording.id)).where(
            CallRecording.organization_id == pilot.organization_id,
            CallRecording.call_record_id == call.id,
            CallRecording.deleted_at.is_(None),
        )
    )
    return bool(
        intent is not None
        and intent.provider_call_id is None
        and intent.status in {"cancelled", "expired"}
        and intent.consumed_at is not None
        and _as_utc(intent.consumed_at) == released_at
        and (
            intent.status != "expired" or _as_utc(intent.expires_at) <= released_at
        )
        and (intent.intent_metadata or {}).get("provider_start_state") == "failed"
        and (intent.intent_metadata or {}).get("source") == "native_prospecting_dialer"
        and (intent.intent_metadata or {}).get("dialer_mode") == "one_line_power"
        and (intent.intent_metadata or {}).get("campaign_id") == str(pilot.campaign_id)
        and (intent.intent_metadata or {}).get("batch_id")
        == str(pilot.prospect_calling_batch_id)
        and (intent.intent_metadata or {}).get("connection_mode") == "browser_softphone"
        and _evidence_datetime(
            intent.intent_metadata or {},
            "browser_pre_provider_terminal_at",
        )
        == released_at
        and (intent.intent_metadata or {}).get("browser_pre_provider_terminal_reason")
        == release_reason
        and (call.call_metadata or {}).get("bridge") == "browser_softphone"
        and _evidence_datetime(
            call.call_metadata or {},
            "browser_pre_provider_terminal_at",
        )
        == released_at
        and (call.call_metadata or {}).get("browser_pre_provider_terminal_reason")
        == release_reason
        and call.status == ("cancelled" if intent.status == "cancelled" else "failed")
        and not recording_count
    )


def _attempt_snapshot(
    db: Session,
    pilot: ProspectingDialerPilot,
    attempt: ProspectingAttempt,
    session: ProspectingDialSession,
    legs: list[ProspectingDialLeg],
    payload: ProspectingDialerPilotAttemptReviewCreate,
    reviewed_at: datetime,
) -> dict[str, Any]:
    entry = db.get(ProspectCallingBatchEntry, attempt.batch_entry_id)
    released_before_provider_start = _released_before_provider_start(
        db,
        pilot,
        attempt,
        session,
        entry,
        legs,
    )
    seller_evidence_by_leg = {
        leg.id: evidence
        for leg in legs
        if (
            evidence := _seller_child_evidence(
                db,
                pilot,
                leg,
                captured_at=reviewed_at,
            )
        )
        is not None
    }
    placed_legs = [leg for leg in legs if leg.id in seller_evidence_by_leg]
    (
        provider_started_legs,
        raw_billable_provider_call_ids,
        provider_identity_complete,
    ) = _provider_identity_graph(db, pilot, legs)
    billable_provider_call_ids = sorted(raw_billable_provider_call_ids)
    provider_identity_reconciled = bool(
        len(legs) == 1
        and released_before_provider_start != bool(provider_started_legs)
        and (
            released_before_provider_start
            or (
                provider_identity_complete
                and len(provider_started_legs) == 1
                and all(
                    (call := _exact_provider_call_record(db, pilot, leg)) is not None
                    and (
                        call.child_provider_call_id is None
                        or leg.id in seller_evidence_by_leg
                    )
                    for leg in provider_started_legs
                )
            )
        )
    )
    seller_child_evidence = [seller_evidence_by_leg[leg.id] for leg in placed_legs]
    terminal_count = sum(
        leg.status in DIAL_LEG_TERMINAL_STATUSES and leg.completed_at is not None for leg in legs
    )
    call_record_ids = [leg.call_record_id for leg in legs if leg.call_record_id is not None]
    recordings = (
        db.scalars(
            select(CallRecording).where(
                CallRecording.organization_id == pilot.organization_id,
                CallRecording.call_record_id.in_(call_record_ids),
                CallRecording.deleted_at.is_(None),
            )
        ).all()
        if call_record_ids
        else []
    )
    recording_call_ids = {item.call_record_id for item in recordings}
    recordings = sorted(recordings, key=lambda item: str(item.id))
    recording_ids = [item.id for item in recordings]
    transcripts = (
        db.scalars(
            select(CallTranscript).where(
                CallTranscript.organization_id == pilot.organization_id,
                CallTranscript.recording_id.in_(recording_ids),
            )
        ).all()
        if recording_ids
        else []
    )
    transcripts = sorted(transcripts, key=lambda item: str(item.id))
    usable_transcripts = [
        item
        for item in transcripts
        if item.status in {"completed", "approved"}
        and bool((item.transcript_text or "").strip())
        and bool((item.transcript_metadata or {}).get("structured_notes"))
    ]
    contact_disposition = (
        _contact_disposition_evidence(
            attempt,
            legs[0],
            seller_evidence_by_leg.get(legs[0].id),
        )
        if len(legs) == 1 and not released_before_provider_start
        else {
            "classification": "pre_provider_release",
            "provider_connection": False,
            "right_party_contact": False,
            "reconciled": released_before_provider_start,
        }
    )
    contact_evidence_reconciled = contact_disposition["reconciled"] is True
    recording_required = contact_disposition["right_party_contact"] is True
    legs_by_call_record_id = {
        item.call_record_id: item for item in legs if item.call_record_id is not None
    }
    connected_evidence_complete = bool(
        not recording_required
        or (
            call_record_ids
            and recording_call_ids == set(call_record_ids)
            and len(recordings) == len(call_record_ids)
            and all(
                item.call_record_id in legs_by_call_record_id
                and prospecting_transcript_eligibility(db, item).eligible
                and _recording_matches_pilot_leg(
                    db,
                    pilot,
                    item,
                    legs_by_call_record_id[item.call_record_id],
                    captured_at=reviewed_at,
                )
                for item in recordings
            )
            and len(usable_transcripts) == len(recording_ids)
        )
    )
    callback_required = bool(
        attempt.callback_at is not None or (attempt.outcome or "") in CALLBACK_DISPOSITIONS
    )
    callback_at = _as_utc(attempt.callback_at) if attempt.callback_at is not None else None
    entry_callback_at = (
        _as_utc(entry.next_attempt_at)
        if entry is not None and entry.next_attempt_at is not None
        else None
    )
    callback_schedule = (attempt.measurement_metadata or {}).get("callback_schedule")
    callback_schedule_at = (
        _evidence_datetime(callback_schedule, "callback_at")
        if isinstance(callback_schedule, dict)
        else None
    )
    callback_reconciled = bool(
        not callback_required
        or (
            callback_at is not None
            and attempt.completed_at is not None
            and callback_at > _as_utc(attempt.completed_at)
            and entry is not None
            and entry.status == "queued"
            and entry.disposition in CALLBACK_DISPOSITIONS
            and entry_callback_at == callback_at
            and callback_schedule_at == callback_at
            and callback_schedule.get("priority") == "due_callback_before_retry_or_new"
        )
    )
    handoff_required = bool(
        attempt.interest_classification == "interested"
        or (attempt.outcome or "")
        in {"interested", "qualified", "qualified_seller", "appointment_set"}
    )
    handoff_count = (
        db.scalar(
            select(func.count(ProspectHandoff.id)).where(
                ProspectHandoff.organization_id == pilot.organization_id,
                ProspectHandoff.attempt_id == attempt.id,
            )
        )
        or 0
    )
    disposition_complete = bool(
        released_before_provider_start
        or (
            attempt.status in {"completed", "cancelled"}
            and attempt.completed_at is not None
            and attempt.outcome
            and entry is not None
            and entry.disposition
        )
    )
    return {
        "policy_version": PILOT_POLICY_VERSION,
        "pilot_id": str(pilot.id),
        "attempt_id": str(attempt.id),
        "dial_session_id": str(session.id),
        "reviewed_at": reviewed_at.isoformat(),
        "server_dial_leg_count": len(legs),
        "server_terminal_leg_count": terminal_count,
        "dial_leg_ids": sorted(str(leg.id) for leg in legs),
        "provider_call_ids": sorted(
            billable_provider_call_ids
        ),
        "call_record_ids": sorted(str(item) for item in call_record_ids),
        "attempt_status": attempt.status,
        "attempt_outcome": attempt.outcome,
        "released_before_provider_start": released_before_provider_start,
        "provider_started": bool(provider_started_legs),
        "provider_identity_reconciled": provider_identity_reconciled,
        "placed_call": bool(placed_legs),
        "seller_child_evidence": seller_child_evidence,
        "contact_classification": contact_disposition["classification"],
        "provider_connection_evidence": contact_disposition["provider_connection"],
        "right_party_contact": contact_disposition["right_party_contact"],
        "contact_evidence_reconciled": contact_evidence_reconciled,
        "attempt_completed_at": (
            _as_utc(attempt.completed_at).isoformat()
            if attempt.completed_at is not None
            else None
        ),
        "disposition_complete": disposition_complete,
        "recording_review_required": recording_required,
        "recording_count": len(recordings),
        "recording_ids": [str(item) for item in recording_ids],
        "recording_identities": _recording_identity_snapshot(
            db,
            pilot,
            recordings,
            legs_by_call_record_id,
            captured_at=reviewed_at,
        ),
        "transcript_ids": [str(item.id) for item in transcripts],
        "transcript_statuses": [item.status for item in transcripts],
        "connected_transcript_and_notes_complete": connected_evidence_complete,
        "recording_reviewed": bool(
            payload.recording_reviewed and connected_evidence_complete
        ),
        "callback_required": callback_required,
        "callback_reconciled": callback_reconciled,
        "callback_at": callback_at.isoformat() if callback_at is not None else None,
        "callback_schedule_at": (
            callback_schedule_at.isoformat() if callback_schedule_at is not None else None
        ),
        "handoff_required": handoff_required,
        "handoff_reconciled": not handoff_required or handoff_count == 1,
        "handoff_count": handoff_count,
        "provider_cost_verified": payload.provider_cost_verified,
        "provider_cost_applicable": bool(provider_started_legs),
        "provider_actual_cost_count": sum(
            leg.actual_cost_cents is not None for leg in provider_started_legs
        ),
        "provider_actual_cost_cents": sum(
            leg.actual_cost_cents or 0 for leg in provider_started_legs
        ),
        "compliance_clear": payload.compliance_clear,
        "review_reason": payload.reason,
    }


def _shift_snapshot(
    db: Session,
    pilot: ProspectingDialerPilot,
    session: ProspectingDialSession,
    payload: ProspectingDialerPilotShiftReviewCreate,
    reviewed_at: datetime,
) -> dict[str, Any]:
    shift_date, day_start, day_end = _local_date_bounds(payload.shift_date, pilot.timezone)
    # Every reserved attempt stays in the auditable shift boundary, including a
    # reservation safely released before provider start. Only provider-started
    # legs drive placed-call volume, productivity, billing, and duplicate KPIs.
    candidate_legs = db.scalars(
        select(ProspectingDialLeg)
        .join(
            ProspectingDialSession,
            ProspectingDialSession.id == ProspectingDialLeg.dial_session_id,
        )
        .where(
            ProspectingDialSession.organization_id == pilot.organization_id,
            ProspectingDialSession.pilot_id == pilot.id,
            ProspectingDialLeg.queued_at >= day_start,
            ProspectingDialLeg.queued_at < day_end,
        )
    ).all()
    candidate_session_ids = {leg.dial_session_id for leg in candidate_legs}
    candidate_sessions = (
        db.scalars(
            select(ProspectingDialSession).where(
                ProspectingDialSession.organization_id == pilot.organization_id,
                ProspectingDialSession.pilot_id == pilot.id,
                ProspectingDialSession.id.in_(candidate_session_ids),
            )
        ).all()
        if candidate_session_ids
        else []
    )
    production_session_ids = {
        item.id
        for item in candidate_sessions
        if (item.session_metadata or {}).get("acceptance_stage") == "running"
    }
    all_legs = [
        leg
        for leg in candidate_legs
        if leg.dial_session_id in production_session_ids and leg.attempt_id is not None
    ]
    seller_evidence_by_leg = {
        leg.id: evidence
        for leg in all_legs
        if (
            evidence := _seller_child_evidence(
                db,
                pilot,
                leg,
                captured_at=reviewed_at,
            )
        )
        is not None
    }
    placed_legs = [leg for leg in all_legs if leg.id in seller_evidence_by_leg]
    (
        provider_started_legs,
        raw_billable_provider_call_ids,
        provider_identity_complete,
    ) = _provider_identity_graph(db, pilot, all_legs)
    billable_provider_call_ids = set(raw_billable_provider_call_ids)
    (
        daily_provider_started_legs,
        raw_daily_billable_provider_call_ids,
        daily_provider_identity_complete,
    ) = _provider_identity_graph(db, pilot, candidate_legs)
    daily_billable_provider_call_ids = set(raw_daily_billable_provider_call_ids)
    session_ids = {leg.dial_session_id for leg in all_legs}
    sessions = (
        db.scalars(
            select(ProspectingDialSession).where(
                ProspectingDialSession.organization_id == pilot.organization_id,
                ProspectingDialSession.pilot_id == pilot.id,
                ProspectingDialSession.id.in_(session_ids),
            )
        ).all()
        if session_ids
        else []
    )
    attempt_ids = list({leg.attempt_id for leg in all_legs if leg.attempt_id is not None})
    placed_attempt_ids = {
        leg.attempt_id for leg in placed_legs if leg.attempt_id is not None
    }
    attempts = (
        db.scalars(
            select(ProspectingAttempt).where(
                ProspectingAttempt.organization_id == pilot.organization_id,
                ProspectingAttempt.id.in_(attempt_ids),
            )
        ).all()
        if attempt_ids
        else []
    )
    attempts_by_id = {item.id: item for item in attempts}
    contact_disposition_by_leg = {
        leg.id: _contact_disposition_evidence(
            attempts_by_id[leg.attempt_id],
            leg,
            seller_evidence_by_leg.get(leg.id),
        )
        for leg in provider_started_legs
        if leg.attempt_id in attempts_by_id
    }
    reviews = (
        db.scalars(
            select(ProspectingDialerPilotAttemptReview).where(
                ProspectingDialerPilotAttemptReview.pilot_id == pilot.id,
                ProspectingDialerPilotAttemptReview.attempt_id.in_(attempt_ids),
            )
        ).all()
        if attempt_ids
        else []
    )
    passed_reviews = [item for item in reviews if item.status == "passed"]
    placed_reviews = [item for item in reviews if item.attempt_id in placed_attempt_ids]
    passed_placed_reviews = [item for item in placed_reviews if item.status == "passed"]
    seller_timing_complete = bool(
        placed_legs
        and all(
            seller_evidence_by_leg[leg.id].get("duration_seconds") is not None
            for leg in placed_legs
        )
    )
    productive_seconds = sum(
        int(seller_evidence_by_leg[leg.id].get("duration_seconds") or 0)
        for leg in placed_legs
        if contact_disposition_by_leg.get(leg.id, {}).get("right_party_contact") is True
    )
    productive_minutes = productive_seconds // 60
    unique_prospects = {leg.prospect_id for leg in placed_legs}
    unique_entries = {leg.batch_entry_id for leg in placed_legs}
    normalized_recipients = [format_e164(leg.recipient) for leg in placed_legs]
    no_session_duplicates = (
        len(placed_legs)
        == len(placed_attempt_ids)
        == len(unique_prospects)
        == len(unique_entries)
        and all(normalized_recipients)
        and len(normalized_recipients) == len(set(normalized_recipients))
    )
    no_server_lost_answers = all(
        leg.id in contact_disposition_by_leg
        and contact_disposition_by_leg[leg.id].get("reconciled") is True
        for leg in provider_started_legs
    )
    all_legs_terminal = all(
        leg.status in DIAL_LEG_TERMINAL_STATUSES and leg.completed_at is not None
        for leg in all_legs
    )
    all_sessions_terminal = bool(
        sessions
        and len(sessions) == len(session_ids)
        and all(
            item.state in TERMINAL_DIAL_SESSION_STATES and item.ended_at is not None
            for item in sessions
        )
    )
    no_stuck_sessions = bool(
        all_sessions_terminal and all_legs_terminal and payload.no_stuck_sessions
    )
    daily_prospect_ids = [leg.prospect_id for leg in placed_legs]
    daily_entry_ids = [leg.batch_entry_id for leg in placed_legs]
    daily_recipients = [format_e164(leg.recipient) for leg in placed_legs]
    no_cross_session_duplicates = bool(
        len(daily_prospect_ids) == len(set(daily_prospect_ids))
        and len(daily_entry_ids) == len(set(daily_entry_ids))
        and all(daily_recipients)
        and len(daily_recipients) == len(set(daily_recipients))
    )
    provider_cost_items = [item.model_dump(mode="json") for item in payload.provider_cost_items]
    provider_costs_by_call_id = {
        item["provider_call_id"]: item["actual_cost_cents"] for item in provider_cost_items
    }
    provider_costs_reconciled = bool(
        provider_started_legs
        and provider_identity_complete
        and len(raw_billable_provider_call_ids) == len(billable_provider_call_ids)
        and len(provider_costs_by_call_id)
        == len(provider_cost_items)
        == len(billable_provider_call_ids)
        and set(provider_costs_by_call_id) == billable_provider_call_ids
    )
    production_leg_ids = {leg.id for leg in all_legs}
    nonproduction_daily_legs = [
        leg for leg in candidate_legs if leg.id not in production_leg_ids
    ]
    other_daily_costs_complete, other_daily_spend = _persisted_provider_cost_graph(
        db,
        pilot,
        nonproduction_daily_legs,
    )
    daily_provider_costs_complete = bool(
        provider_costs_reconciled
        and daily_provider_identity_complete
        and len(raw_daily_billable_provider_call_ids)
        == len(daily_billable_provider_call_ids)
        and other_daily_costs_complete
    )
    daily_spend = sum(provider_costs_by_call_id.values()) + other_daily_spend
    all_attempts_reviewed = bool(
        attempt_ids
        and len(reviews) == len(attempt_ids)
        and len(passed_reviews) == len(attempt_ids)
    )
    return {
        "policy_version": PILOT_POLICY_VERSION,
        "pilot_id": str(pilot.id),
        "dial_session_id": str(session.id),
        "dial_session_ids": sorted(str(item) for item in session_ids),
        "dial_leg_ids": sorted(str(leg.id) for leg in all_legs),
        "daily_reservation_dial_leg_ids": sorted(
            str(leg.id) for leg in candidate_legs
        ),
        "placed_dial_leg_ids": sorted(str(leg.id) for leg in placed_legs),
        "provider_started_dial_leg_ids": sorted(
            str(leg.id) for leg in provider_started_legs
        ),
        "billable_provider_call_ids": sorted(billable_provider_call_ids),
        "daily_billable_provider_call_ids": sorted(
            daily_billable_provider_call_ids
        ),
        "seller_child_evidence": [
            seller_evidence_by_leg[leg.id]
            for leg in sorted(placed_legs, key=lambda item: str(item.id))
        ],
        "attempt_ids": sorted(str(item) for item in attempt_ids),
        "placed_attempt_ids": sorted(str(item) for item in placed_attempt_ids),
        "shift_date": shift_date.isoformat(),
        "timezone": pilot.timezone,
        "reviewed_at": reviewed_at.isoformat(),
        "server_attempt_count": len(placed_attempt_ids),
        "server_reviewed_attempt_count": len(placed_reviews),
        "server_passed_attempt_count": len(passed_placed_reviews),
        "all_attempt_count": len(attempt_ids),
        "reserved_attempt_count": len(attempt_ids),
        "reserved_dial_leg_count": len(all_legs),
        "provider_started_attempt_count": len(
            {leg.attempt_id for leg in provider_started_legs if leg.attempt_id is not None}
        ),
        "placed_call_count": len(placed_legs),
        "all_reviewed_attempt_count": len(reviews),
        "all_passed_attempt_count": len(passed_reviews),
        "productive_minutes": productive_minutes,
        "seller_productive_seconds": productive_seconds,
        "seller_timing_complete": seller_timing_complete,
        "all_attempts_reviewed": all_attempts_reviewed,
        "all_legs_terminal": bool(all_legs) and all_legs_terminal,
        "server_no_session_duplicates": no_session_duplicates,
        "server_no_cross_session_duplicates": no_cross_session_duplicates,
        "server_no_lost_answers": no_server_lost_answers,
        "server_session_terminal": all_sessions_terminal and all_legs_terminal,
        "no_duplicate_calls": bool(
            no_session_duplicates
            and no_cross_session_duplicates
            and payload.no_duplicate_calls
        ),
        "no_cross_session_duplicates": no_cross_session_duplicates,
        "no_lost_answers": no_server_lost_answers and payload.no_lost_answers,
        "no_stuck_sessions": no_stuck_sessions,
        "callbacks_reconciled": all(item.callback_reconciled for item in reviews),
        "handoffs_reconciled": all(item.handoff_reconciled for item in reviews),
        "provider_billing_verified": bool(
            payload.provider_billing_verified
            and reviews
            and all(item.provider_cost_verified for item in reviews)
            and provider_costs_reconciled
        ),
        "billing_evidence_reference": payload.billing_evidence_reference,
        "provider_cost_evidence_type": "human_attested_per_call_provider_export",
        "provider_costs_reconciled": provider_costs_reconciled,
        "provider_identity_complete": provider_identity_complete,
        "daily_provider_identity_complete": daily_provider_identity_complete,
        "provider_cost_items": provider_cost_items,
        "provider_actual_cost_cents": sum(provider_costs_by_call_id.values()),
        "daily_dial_count": len(candidate_legs),
        "daily_reserved_dial_count": len(candidate_legs),
        "daily_seller_call_count": len(placed_legs),
        "daily_spend_cents": daily_spend,
        "daily_provider_costs_complete": daily_provider_costs_complete,
        "daily_caps_respected": (
            daily_provider_costs_complete
            and all(leg.attempt_id is not None for leg in candidate_legs)
            and len(candidate_legs) <= pilot.daily_dial_limit
            and daily_spend <= pilot.daily_spend_limit_cents
        ),
        "kill_switches_verified": bool(
            payload.kill_switches_verified
            and _valid_kill_switch_evidence(
                db,
                pilot,
                pilot.kill_switch_evidence,
                now=reviewed_at,
            )
        ),
        "recordings_reviewed": bool(
            reviews
            and all(
                not item.recording_review_required or item.recording_reviewed for item in reviews
            )
        ),
        "compliance_clear": bool(
            payload.compliance_clear and reviews and all(item.compliance_clear for item in reviews)
        ),
        "review_reason": payload.reason,
    }


def _acceptance_snapshot(
    db: Session,
    pilot: ProspectingDialerPilot,
    settings: Settings,
    now: datetime,
) -> dict[str, Any]:
    reviews = db.scalars(
        select(ProspectingDialerPilotAttemptReview)
        .where(ProspectingDialerPilotAttemptReview.pilot_id == pilot.id)
        .order_by(ProspectingDialerPilotAttemptReview.attempt_id.asc())
    ).all()
    shifts = db.scalars(
        select(ProspectingDialerPilotShiftReview)
        .where(ProspectingDialerPilotShiftReview.pilot_id == pilot.id)
        .order_by(ProspectingDialerPilotShiftReview.shift_date.asc())
    ).all()
    return {
        "policy_version": PILOT_POLICY_VERSION,
        "pilot_id": str(pilot.id),
        "scope": {
            "organization_id": str(pilot.organization_id),
            "caller_user_id": str(pilot.caller_user_id),
            "campaign_id": str(pilot.campaign_id),
            "cohort_id": str(pilot.cohort_id),
            "prospect_calling_batch_id": str(pilot.prospect_calling_batch_id),
            "voice_line_id": str(pilot.voice_line_id),
            "configuration_fingerprint": pilot.configuration_fingerprint,
            "start_attestation": pilot.start_attestation,
        },
        "thresholds": {
            "required_clean_shift_count": pilot.required_clean_shift_count,
            "minimum_attempts_per_shift": pilot.minimum_attempts_per_shift,
            "minimum_productive_minutes_per_shift": (
                pilot.minimum_productive_minutes_per_shift
            ),
            "minimum_total_attempts": pilot.minimum_total_attempts,
            "daily_dial_limit": pilot.daily_dial_limit,
            "daily_spend_limit_cents": pilot.daily_spend_limit_cents,
        },
        "evidence": {
            "smoke_test": pilot.smoke_test_evidence,
            "kill_switch": pilot.kill_switch_evidence,
            "batchdialer_comparison": pilot.batchdialer_comparison_evidence,
            "rollback": pilot.rollback_evidence,
        },
        "attempt_reviews": [
            {
                "review_id": str(item.id),
                "attempt_id": str(item.attempt_id),
                "evidence_hash": item.evidence_hash,
                "evidence_snapshot": item.evidence_snapshot,
            }
            for item in reviews
        ],
        "shift_reviews": [
            {
                "review_id": str(item.id),
                "dial_session_id": str(item.dial_session_id),
                "evidence_hash": item.evidence_hash,
                "evidence_snapshot": item.evidence_snapshot,
            }
            for item in shifts
        ],
    }


def _attempt_membership(
    db: Session,
    pilot: ProspectingDialerPilot,
    attempt_id: UUID,
) -> tuple[ProspectingAttempt | None, ProspectingDialSession | None, list[ProspectingDialLeg]]:
    attempt = db.scalar(
        select(ProspectingAttempt).where(
            ProspectingAttempt.id == attempt_id,
            ProspectingAttempt.organization_id == pilot.organization_id,
            ProspectingAttempt.caller_user_id == pilot.caller_user_id,
            ProspectingAttempt.cohort_id == pilot.cohort_id,
        )
    )
    if attempt is None:
        return None, None, []
    entry = db.scalar(
        select(ProspectCallingBatchEntry).where(
            ProspectCallingBatchEntry.id == attempt.batch_entry_id,
            ProspectCallingBatchEntry.organization_id == pilot.organization_id,
            ProspectCallingBatchEntry.prospect_calling_batch_id
            == pilot.prospect_calling_batch_id,
        )
    )
    if entry is None:
        return None, None, []
    legs = db.scalars(
        select(ProspectingDialLeg).where(
            ProspectingDialLeg.organization_id == pilot.organization_id,
            ProspectingDialLeg.attempt_id == attempt.id,
        )
    ).all()
    if any(
        leg.batch_entry_id != attempt.batch_entry_id
        or leg.prospect_id != attempt.prospect_id
        or entry.prospect_id != attempt.prospect_id
        for leg in legs
    ):
        return None, None, legs
    session_ids = {leg.dial_session_id for leg in legs}
    if len(session_ids) != 1:
        return None, None, legs
    session = db.scalar(
        select(ProspectingDialSession).where(
            ProspectingDialSession.id == next(iter(session_ids)),
            ProspectingDialSession.organization_id == pilot.organization_id,
            ProspectingDialSession.pilot_id == pilot.id,
        )
    )
    if session is None or not _session_matches_pilot(session, pilot):
        return None, None, legs
    return attempt, session, legs


def _smoke_test_eligible_leg(
    db: Session,
    pilot: ProspectingDialerPilot,
    session: ProspectingDialSession,
    leg: ProspectingDialLeg,
    *,
    captured_at: datetime,
) -> bool:
    """Return true only for a call that can be selected as smoke evidence.

    ``placed_call`` deliberately describes provider placement, including busy
    and no-answer child legs.  Smoke evidence is narrower: the controlled
    seller leg must have answered/connected, have signed contact duration, and
    carry one exact retained recording with signed provider lineage.
    """

    if (
        (session.session_metadata or {}).get("acceptance_stage") != "smoke_testing"
        or session.state not in TERMINAL_DIAL_SESSION_STATES
        or session.ended_at is None
        or _as_utc(session.ended_at) > _as_utc(captured_at)
        or leg.status not in DIAL_LEG_TERMINAL_STATUSES
        or leg.completed_at is None
        or _as_utc(leg.completed_at) > _as_utc(captured_at)
        or leg.attempt_id is None
        or leg.call_record_id is None
        or (leg.answered_at is None and leg.connected_at is None)
        or format_e164(leg.recipient) not in _pilot_controlled_numbers(pilot)
    ):
        return False
    seller_evidence = _seller_child_evidence(
        db,
        pilot,
        leg,
        captured_at=captured_at,
    )
    attempt = db.scalar(
        select(ProspectingAttempt).where(
            ProspectingAttempt.id == leg.attempt_id,
            ProspectingAttempt.organization_id == pilot.organization_id,
        )
    )
    contact_disposition = (
        _contact_disposition_evidence(attempt, leg, seller_evidence)
        if attempt is not None
        else None
    )
    provider_started_legs, provider_ids, provider_identity_complete = (
        _provider_identity_graph(db, pilot, [leg])
    )
    recordings = db.scalars(
        select(CallRecording).where(
            CallRecording.organization_id == pilot.organization_id,
            CallRecording.call_record_id == leg.call_record_id,
            CallRecording.deleted_at.is_(None),
        )
    ).all()
    return bool(
        seller_evidence is not None
        and contact_disposition is not None
        and contact_disposition.get("right_party_contact") is True
        and seller_evidence.get("duration_seconds") is not None
        and seller_evidence.get("contact_evidence") is True
        and provider_identity_complete
        and provider_started_legs == [leg]
        and provider_ids
        and len(provider_ids) == len(set(provider_ids))
        and len(recordings) == 1
        and _recording_matches_pilot_leg(
            db,
            pilot,
            recordings[0],
            leg,
            captured_at=captured_at,
        )
    )


def _attempt_review_queue(
    db: Session,
    pilot: ProspectingDialerPilot,
    reviews: list[ProspectingDialerPilotAttemptReview],
) -> list[ProspectingDialerPilotAttemptQueueRead]:
    reviewed = {item.attempt_id: item.status for item in reviews}
    statement = (
        select(ProspectingAttempt, ProspectingDialSession)
        .join(ProspectingDialLeg, ProspectingDialLeg.attempt_id == ProspectingAttempt.id)
        .join(
            ProspectingDialSession,
            ProspectingDialSession.id == ProspectingDialLeg.dial_session_id,
        )
        .join(
            ProspectCallingBatchEntry,
            ProspectCallingBatchEntry.id == ProspectingAttempt.batch_entry_id,
        )
        .where(
            ProspectingAttempt.organization_id == pilot.organization_id,
            ProspectingAttempt.caller_user_id == pilot.caller_user_id,
            ProspectingAttempt.cohort_id == pilot.cohort_id,
            ProspectingDialSession.pilot_id == pilot.id,
            ProspectCallingBatchEntry.prospect_calling_batch_id
            == pilot.prospect_calling_batch_id,
        )
        .distinct()
        .order_by(ProspectingAttempt.started_at.asc())
    )
    if pilot.submitted_at is not None:
        statement = statement.where(
            ProspectingDialLeg.queued_at <= _as_utc(pilot.submitted_at)
        )
    rows = db.execute(statement).all()
    captured_at = _as_utc(pilot.submitted_at or datetime.now(UTC))
    queue: list[ProspectingDialerPilotAttemptQueueRead] = []
    for attempt, session in rows:
        session_id = session.id
        raw_acceptance_stage = (session.session_metadata or {}).get("acceptance_stage")
        acceptance_stage = (
            raw_acceptance_stage
            if raw_acceptance_stage in {"smoke_testing", "running", "accepted"}
            else None
        )
        queue_legs = db.scalars(
            select(ProspectingDialLeg).where(
                ProspectingDialLeg.organization_id == pilot.organization_id,
                ProspectingDialLeg.dial_session_id == session_id,
                ProspectingDialLeg.attempt_id == attempt.id,
            )
        ).all()
        queue.append(
            ProspectingDialerPilotAttemptQueueRead(
            attempt_id=attempt.id,
            dial_session_id=session_id,
            acceptance_stage=acceptance_stage,
            counts_toward_production_shift=acceptance_stage == "running",
            call_record_ids=[
                leg.call_record_id for leg in queue_legs if leg.call_record_id is not None
            ],
            # Preserve the exact provider identity universe in stable leg/root/child
            # order.  Do not deduplicate here: repeated SIDs are evidence of an
            # invalid cross-leg identity graph and must remain visible to both the
            # reviewer and the independent reconciliation checks.
            provider_call_ids=[
                provider_call_id
                for queue_leg in sorted(queue_legs, key=lambda item: str(item.id))
                for provider_call_id in _billable_provider_call_ids(
                    db,
                    pilot,
                    queue_leg,
                )
            ],
            placed_call=any(
                _is_placed_leg(
                    db,
                    pilot,
                    queue_leg,
                    captured_at=captured_at,
                )
                for queue_leg in queue_legs
            ),
            smoke_test_eligible=any(
                _smoke_test_eligible_leg(
                    db,
                    pilot,
                    session,
                    queue_leg,
                    captured_at=captured_at,
                )
                for queue_leg in queue_legs
            ),
            started_at=attempt.started_at,
            completed_at=attempt.completed_at,
            outcome=attempt.outcome,
            review_status=reviewed.get(attempt.id, "pending"),
            blocker=(
                None
                if attempt.completed_at is not None
                else "Complete the attempt before reviewing its evidence."
            ),
        )
        )
    return queue


def _disable_pilot_scope(
    db: Session,
    principal: Principal,
    pilot: ProspectingDialerPilot,
    now: datetime,
    reason: str,
    *,
    release_reason: str,
    drain_active_provider_calls: bool = False,
) -> dict[str, object]:
    campaign = db.scalar(
        select(Campaign)
        .where(
            Campaign.id == pilot.campaign_id,
            Campaign.organization_id == pilot.organization_id,
        )
        .with_for_update()
    )
    sessions = db.scalars(
        select(ProspectingDialSession)
        .where(
            ProspectingDialSession.organization_id == pilot.organization_id,
            ProspectingDialSession.pilot_id == pilot.id,
            ProspectingDialSession.ended_at.is_(None),
        )
        .with_for_update()
    ).all()
    session_ids = [item.id for item in sessions]
    active_legs = (
        db.scalars(
            select(ProspectingDialLeg)
            .where(
                ProspectingDialLeg.dial_session_id.in_(session_ids),
                ProspectingDialLeg.completed_at.is_(None),
            )
            .with_for_update()
        ).all()
        if session_ids
        else []
    )
    from app.services.prospecting_voice import (
        ProspectingVoiceConfigurationError,
        ProspectingVoiceConflictError,
        abandon_untouched_browser_call,
        assemble_graph,
        load_graph_call,
        untouched_browser_call,
    )

    prepared_calls: dict[
        UUID, tuple[object, VoiceCallIntent, CallRecord]
    ] = {}
    unsafe: list[ProspectingDialLeg] = []
    for leg in active_legs:
        if leg.status != "queued" or leg.provider_call_id is not None:
            unsafe.append(leg)
            continue
        if leg.call_record_id is None:
            continue
        graph = assemble_graph(db, leg)
        try:
            intent, call = load_graph_call(db, graph, lock=True) if graph else (None, None)
        except (ProspectingVoiceConflictError, ProspectingVoiceConfigurationError):
            unsafe.append(leg)
            continue
        if (
            graph is None
            or intent is None
            or call is None
            or call.id != leg.call_record_id
            or not untouched_browser_call(graph, intent, call)
        ):
            unsafe.append(leg)
            continue
        prepared_calls[leg.id] = (graph, intent, call)
    if unsafe and not drain_active_provider_calls:
        raise ProspectingDialerAcceptanceConflictError(
            "Rollback is blocked by active provider call legs: "
            + ", ".join(str(leg.id) for leg in unsafe)
            + ". End or recover them first."
        )
    if campaign is not None:
        # Disable new reservations in the same transaction before draining any
        # already-connected provider leg.  The mutation intentionally happens
        # after the strict rollback safety check so a rejected rollback does
        # not leave a dirty in-session campaign state for callers to observe.
        campaign.prospecting_dialer_enabled = False
    sessions_by_id = {session.id: session for session in sessions}
    unsafe_leg_ids = {leg.id for leg in unsafe}
    unsafe_session_ids = {leg.dial_session_id for leg in unsafe}
    for leg in active_legs:
        if leg.id in unsafe_leg_ids:
            continue
        if leg.id in prepared_calls:
            graph, intent, call = prepared_calls[leg.id]
            abandon_untouched_browser_call(
                db,
                principal,
                graph,
                intent,
                call,
                now=now,
                reason=release_reason,
                intent_status="cancelled",
            )
            continue
        session = sessions_by_id[leg.dial_session_id]
        release_unstarted_reservation(
            db,
            session,
            leg,
            now=now,
            reason=release_reason,
        )
    for session in sessions:
        if session.id in unsafe_session_ids:
            metadata = dict(session.session_metadata or {})
            metadata["stop_after_current"] = True
            metadata["authorization_revoked"] = True
            session.session_metadata = metadata
            session.stop_reason = reason[:255]
            continue
        session.state = "stopped"
        session.ended_at = now
        session.stop_reason = reason[:255]
        session.lease_token = None
        session.lease_expires_at = None
        session.current_prospect_id = None
        session.current_batch_entry_id = None
        session.current_attempt_id = None
    return {
        "campaign_disabled": campaign is not None,
        "stopped_session_ids": sorted(
            str(item.id) for item in sessions if item.id not in unsafe_session_ids
        ),
        "draining_session_ids": sorted(str(item) for item in unsafe_session_ids),
        "draining_leg_ids": sorted(str(item.id) for item in unsafe),
    }


def _configuration_blockers(
    graph: DialerRuntimeGraph,
    settings: Settings,
    batch_entry_count: int,
) -> list[str]:
    blockers: list[str] = []
    line_caps = (
        graph.organization.prospecting_dialer_max_concurrent_legs,
        graph.profile.default_line_count,
        graph.profile.max_line_count,
        graph.campaign.prospecting_dialer_max_concurrent_legs,
        graph.line.prospecting_dialer_max_concurrent_legs,
        settings.prospecting_native_dialer_effective_line_cap,
    )
    if any(cap != 1 for cap in line_caps):
        blockers.append("Every company, VA, campaign, line, and runtime cap must equal one.")
    if graph.batch.dialer_mode != "one_line_power" or graph.cohort.dialer_mode != "one_line_power":
        blockers.append("The pilot batch and cohort must use one_line_power mode.")
    if not PILOT_MIN_BATCH_SIZE <= batch_entry_count <= PILOT_MAX_BATCH_SIZE:
        blockers.append(
            f"The pilot batch must contain {PILOT_MIN_BATCH_SIZE}–{PILOT_MAX_BATCH_SIZE} records."
        )
    if not (
        graph.profile.daily_dial_limit is not None
        and PILOT_MIN_ATTEMPTS_PER_SHIFT
        <= graph.profile.daily_dial_limit
        <= PILOT_MAX_DIALS_PER_DAY
    ):
        blockers.append(
            "The VA daily dial cap must be set between "
            f"{PILOT_MIN_ATTEMPTS_PER_SHIFT} and {PILOT_MAX_DIALS_PER_DAY}."
        )
    if (
        graph.profile.daily_spend_limit_cents is None
        or graph.profile.daily_spend_limit_cents < 1
        or graph.profile.daily_spend_limit_cents > PILOT_MAX_SPEND_CENTS_PER_DAY
    ):
        blockers.append("The VA daily provider-spend cap must be set between $0.01 and $10.00.")
    if graph.profile.recording_policy != "company_policy":
        blockers.append("The VA must use the company recording policy.")
    if not settings.twilio_voice_recording_configured:
        blockers.append("Twilio recording and a positive retention policy must be configured.")
    if not settings.call_transcription_enabled:
        blockers.append("Call transcription must be enabled for the D10 pilot.")
    return blockers


def _eligible_batch_recipients(
    db: Session,
    graph: DialerRuntimeGraph,
    now: datetime,
) -> set[str]:
    entries = db.scalars(
        candidate_entry_statement(
            organization_id=graph.organization.id,
            caller_user_id=graph.caller.id,
            campaign_id=graph.campaign.id,
            batch_id=graph.batch.id,
            now=now,
        )
    ).all()
    recipients: set[str] = set()
    for entry in entries:
        prospect = db.get(Prospect, entry.prospect_id)
        if prospect is None:
            continue
        ranked = select_ranked_phone(db, prospect)
        if ranked is not None:
            recipients.add(ranked[1])
    return recipients


def _pilot_graph(
    db: Session,
    principal: Principal,
    *,
    caller_user_id: UUID,
    campaign_id: UUID,
    cohort_id: UUID,
    batch_id: UUID,
) -> DialerRuntimeGraph | None:
    caller = db.scalar(
        select(User).where(
            User.id == caller_user_id,
            User.organization_id == principal.organization_id,
        )
    )
    if caller is None:
        return None
    caller_principal = Principal(
        user_id=caller.id,
        organization_id=principal.organization_id,
        email=caller.email,
        permission_keys=frozenset(),
    )
    return load_runtime_graph(
        db,
        caller_principal,
        campaign_id=campaign_id,
        cohort_id=cohort_id,
        batch_id=batch_id,
    )


def _graph_for_pilot(
    db: Session,
    principal: Principal,
    pilot: ProspectingDialerPilot,
) -> DialerRuntimeGraph | None:
    return _pilot_graph(
        db,
        principal,
        caller_user_id=pilot.caller_user_id,
        campaign_id=pilot.campaign_id,
        cohort_id=pilot.cohort_id,
        batch_id=pilot.prospect_calling_batch_id,
    )


def _pilot_read(db: Session, pilot: ProspectingDialerPilot) -> ProspectingDialerPilotRead:
    caller = db.scalar(
        select(User).where(
            User.id == pilot.caller_user_id,
            User.organization_id == pilot.organization_id,
        )
    )
    campaign = db.scalar(
        select(Campaign).where(
            Campaign.id == pilot.campaign_id,
            Campaign.organization_id == pilot.organization_id,
        )
    )
    cohort = db.scalar(
        select(ProspectingCohort).where(
            ProspectingCohort.id == pilot.cohort_id,
            ProspectingCohort.organization_id == pilot.organization_id,
        )
    )
    batch = db.scalar(
        select(ProspectCallingBatch).where(
            ProspectCallingBatch.id == pilot.prospect_calling_batch_id,
            ProspectCallingBatch.organization_id == pilot.organization_id,
        )
    )
    line = db.scalar(
        select(VoiceLine).where(
            VoiceLine.id == pilot.voice_line_id,
            VoiceLine.organization_id == pilot.organization_id,
        )
    )
    if any(item is None for item in (caller, campaign, cohort, batch, line)):
        raise ValueError("The pilot references deleted or unavailable configuration.")
    assert caller and campaign and cohort and batch and line
    return ProspectingDialerPilotRead(
        id=pilot.id,
        status=pilot.status,
        revision=pilot.revision,
        caller_user_id=pilot.caller_user_id,
        caller_name=caller.display_name,
        campaign_id=pilot.campaign_id,
        campaign_name=campaign.name,
        cohort_id=pilot.cohort_id,
        cohort_name=cohort.name,
        prospect_calling_batch_id=pilot.prospect_calling_batch_id,
        calling_batch_name=batch.name,
        voice_line_id=pilot.voice_line_id,
        voice_line_number=line.phone_number,
        effective_line_count=pilot.effective_line_count,
        timezone=pilot.timezone,
        required_clean_shift_count=pilot.required_clean_shift_count,
        minimum_attempts_per_shift=pilot.minimum_attempts_per_shift,
        minimum_productive_minutes_per_shift=pilot.minimum_productive_minutes_per_shift,
        minimum_total_attempts=pilot.minimum_total_attempts,
        minimum_batch_size=pilot.minimum_batch_size,
        maximum_batch_size=pilot.maximum_batch_size,
        daily_dial_limit=pilot.daily_dial_limit,
        daily_spend_limit_cents=pilot.daily_spend_limit_cents,
        configuration_fingerprint=pilot.configuration_fingerprint,
        started_at=pilot.started_at,
        start_attestation=pilot.start_attestation,
        smoke_test_evidence=pilot.smoke_test_evidence,
        kill_switch_evidence=pilot.kill_switch_evidence,
        batchdialer_comparison_evidence=pilot.batchdialer_comparison_evidence,
        rollback_evidence=pilot.rollback_evidence,
        evidence_hash=pilot.evidence_hash,
        submitted_at=pilot.submitted_at,
        accepted_at=pilot.accepted_at,
        rejected_at=pilot.rejected_at,
        rolled_back_at=pilot.rolled_back_at,
        revoked_at=pilot.revoked_at,
        revocation_reason=pilot.revocation_reason,
        cancelled_at=pilot.cancelled_at,
        cancellation_reason=pilot.cancellation_reason,
        created_at=pilot.created_at,
        updated_at=pilot.updated_at,
    )


def _attempt_review_read(
    item: ProspectingDialerPilotAttemptReview,
) -> ProspectingDialerPilotAttemptReviewRead:
    assert item.reviewed_at is not None
    return ProspectingDialerPilotAttemptReviewRead(
        id=item.id,
        attempt_id=item.attempt_id,
        dial_session_id=item.dial_session_id,
        status=item.status,
        server_dial_leg_count=item.server_dial_leg_count,
        server_terminal_leg_count=item.server_terminal_leg_count,
        disposition_complete=item.disposition_complete,
        recording_review_required=item.recording_review_required,
        recording_reviewed=item.recording_reviewed,
        callback_required=item.callback_required,
        callback_reconciled=item.callback_reconciled,
        handoff_required=item.handoff_required,
        handoff_reconciled=item.handoff_reconciled,
        provider_cost_verified=item.provider_cost_verified,
        compliance_clear=item.compliance_clear,
        reviewed_at=item.reviewed_at,
        reason=item.review_reason or "",
    )


def _shift_review_read(
    item: ProspectingDialerPilotShiftReview,
) -> ProspectingDialerPilotShiftReviewRead:
    assert item.reviewed_at is not None
    snapshot = item.evidence_snapshot or {}
    return ProspectingDialerPilotShiftReviewRead(
        id=item.id,
        dial_session_id=item.dial_session_id,
        shift_date=item.shift_date,
        timezone=item.timezone,
        status=item.status,
        server_attempt_count=item.server_attempt_count,
        server_reviewed_attempt_count=item.server_reviewed_attempt_count,
        server_passed_attempt_count=item.server_passed_attempt_count,
        reserved_attempt_count=int(snapshot.get("reserved_attempt_count") or 0),
        provider_started_attempt_count=int(
            snapshot.get("provider_started_attempt_count") or 0
        ),
        placed_call_count=int(snapshot.get("placed_call_count") or 0),
        productive_minutes=item.productive_minutes,
        all_attempts_reviewed=item.all_attempts_reviewed,
        all_legs_terminal=item.all_legs_terminal,
        no_duplicate_calls=item.no_duplicate_calls,
        no_lost_answers=item.no_lost_answers,
        no_stuck_sessions=item.no_stuck_sessions,
        callbacks_reconciled=item.callbacks_reconciled,
        handoffs_reconciled=item.handoffs_reconciled,
        provider_billing_verified=item.provider_billing_verified,
        daily_caps_respected=item.daily_caps_respected,
        kill_switches_verified=item.kill_switches_verified,
        recordings_reviewed=item.recordings_reviewed,
        compliance_clear=item.compliance_clear,
        reviewed_at=item.reviewed_at,
        reason=item.review_reason or "",
    )


def _allowed_actions(
    db: Session,
    principal: Principal,
    pilot: ProspectingDialerPilot,
    gates: list[ProspectingDialerPilotGateRead],
) -> list[str]:
    if pilot.status == "draft":
        return ["start", "update_evidence", "rollback"]
    if pilot.status == "smoke_testing":
        return ["update_evidence", "rollback"]
    if pilot.status == "running":
        actions = ["update_evidence", "review_attempt", "review_shift", "rollback"]
        if all(item.status != "block" for item in gates):
            actions.append("submit")
        return actions
    if pilot.status == "ready_for_owner_review":
        actions = ["rollback"]
        if _is_owner(db, principal):
            actions = ["accept", "reject", *actions]
        return actions
    if pilot.status == "accepted" and _is_owner(db, principal):
        return ["revoke"]
    if pilot.status in {"rejected", "rolled_back", "revoked", "cancelled"}:
        return ["create"]
    return []


def _locked_pilot(
    db: Session,
    organization_id: UUID,
    pilot_id: UUID,
) -> ProspectingDialerPilot | None:
    return db.scalar(
        select(ProspectingDialerPilot)
        .where(
            ProspectingDialerPilot.id == pilot_id,
            ProspectingDialerPilot.organization_id == organization_id,
        )
        .with_for_update()
    )


def _expect_revision(pilot: ProspectingDialerPilot, expected: int) -> None:
    if pilot.revision != expected:
        raise ProspectingDialerAcceptanceConflictError(
            f"Stale pilot revision: expected {expected}, current revision is {pilot.revision}."
        )


def _increment_revision(pilot: ProspectingDialerPilot) -> None:
    pilot.revision += 1


def _batch_entry_count(db: Session, batch_id: UUID, organization_id: UUID) -> int:
    return (
        db.scalar(
            select(func.count(ProspectCallingBatchEntry.id)).where(
                ProspectCallingBatchEntry.organization_id == organization_id,
                ProspectCallingBatchEntry.prospect_calling_batch_id == batch_id,
            )
        )
        or 0
    )


def _session_matches_pilot(
    session: ProspectingDialSession,
    pilot: ProspectingDialerPilot,
) -> bool:
    return bool(
        session.pilot_id == pilot.id
        and session.caller_user_id == pilot.caller_user_id
        and session.campaign_id == pilot.campaign_id
        and session.cohort_id == pilot.cohort_id
        and session.prospect_calling_batch_id == pilot.prospect_calling_batch_id
        and session.voice_line_id == pilot.voice_line_id
        and session.effective_line_count == 1
    )


def _is_owner(db: Session, principal: Principal) -> bool:
    return (
        db.scalar(
            select(func.count(RoleAssignment.id))
            .join(Role, Role.id == RoleAssignment.role_id)
            .join(User, User.id == RoleAssignment.user_id)
            .where(
                RoleAssignment.organization_id == principal.organization_id,
                RoleAssignment.user_id == principal.user_id,
                Role.organization_id == principal.organization_id,
                Role.key.in_(PILOT_OWNER_ROLE_KEYS),
                User.organization_id == principal.organization_id,
                User.is_active.is_(True),
            )
        )
        or 0
    ) > 0


def _require_owner(db: Session, principal: Principal) -> None:
    if not _is_owner(db, principal):
        raise PermissionError("Only an owner or founder operator can decide D10 acceptance.")


def _require_manager(principal: Principal) -> None:
    if not can_manage_dialer(principal):
        raise PermissionError("Only an acquisition manager can manage D10 acceptance.")


def _idempotent_pilot_replay(
    db: Session,
    principal: Principal,
    *,
    action: str,
    payload: Any,
    context: dict[str, object] | None = None,
) -> ProspectingDialerPilot | None:
    expected_digest = _request_digest(payload, context)
    events = db.scalars(
        select(AuditEvent)
        .where(
            AuditEvent.organization_id == principal.organization_id,
            AuditEvent.action == action,
        )
        .order_by(AuditEvent.created_at.desc())
    ).all()
    for event in events:
        value = event.new_value or {}
        if value.get("idempotency_key") != payload.idempotency_key:
            continue
        if value.get("request_digest") != expected_digest:
            raise ProspectingDialerAcceptanceConflictError(
                "This idempotency key was already used with different pilot input."
            )
        if event.entity_id is None:
            raise ProspectingDialerAcceptanceConflictError(
                "The idempotent pilot mutation has no durable entity reference."
            )
        pilot = db.scalar(
            select(ProspectingDialerPilot).where(
                ProspectingDialerPilot.id == event.entity_id,
                ProspectingDialerPilot.organization_id == principal.organization_id,
            )
        )
        if pilot is None:
            raise ProspectingDialerAcceptanceConflictError(
                "The idempotent pilot mutation references missing state."
            )
        return pilot
    return None


def _audit_mutation(
    db: Session,
    principal: Principal,
    pilot: ProspectingDialerPilot,
    *,
    action: str,
    payload: Any,
    previous: dict[str, object] | None,
    new: dict[str, object],
    reason: str,
    context: dict[str, object] | None = None,
) -> None:
    value = dict(new)
    value.update(
        {
            "idempotency_key": payload.idempotency_key,
            "request_digest": _request_digest(payload, context),
        }
    )
    db.add(
        AuditEvent(
            organization_id=principal.organization_id,
            actor_user_id=principal.user_id,
            actor_type="user",
            action=action,
            entity_type="prospecting_dialer_pilot",
            entity_id=pilot.id,
            previous_value=previous,
            new_value=value,
            reason=reason[:500],
        )
    )


def _request_digest(payload: Any, context: dict[str, object] | None = None) -> str:
    value = payload.model_dump(mode="json")
    if context:
        value["_context"] = context
    return _hash_json(value)


def _pilot_state(pilot: ProspectingDialerPilot) -> dict[str, object]:
    return {
        "status": pilot.status,
        "revision": pilot.revision,
        "evidence_hash": pilot.evidence_hash,
    }


def _hash_json(value: object) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode()
    return hashlib.sha256(encoded).hexdigest()


def _commit_or_conflict(db: Session, detail: str) -> None:
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise ProspectingDialerAcceptanceConflictError(detail) from exc


def _local_shift_bounds(value: datetime, timezone_name: str):
    try:
        timezone = ZoneInfo(timezone_name)
    except ZoneInfoNotFoundError as exc:
        raise ValueError("The pilot timezone is invalid.") from exc
    local = _as_utc(value).astimezone(timezone)
    return _local_date_bounds(local.date(), timezone_name)


def _local_date_bounds(value: date, timezone_name: str):
    try:
        timezone = ZoneInfo(timezone_name)
    except ZoneInfoNotFoundError as exc:
        raise ValueError("The pilot timezone is invalid.") from exc
    local_start = datetime(
        value.year,
        value.month,
        value.day,
        tzinfo=timezone,
    )
    return (
        value,
        local_start.astimezone(UTC),
        (local_start + timedelta(days=1)).astimezone(UTC),
    )


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _evidence_datetime(value: dict[str, Any], key: str) -> datetime | None:
    raw = value.get(key)
    if not isinstance(raw, str):
        return None
    try:
        return _as_utc(datetime.fromisoformat(raw))
    except ValueError:
        return None


def _recording_matches_pilot_leg(
    db: Session,
    pilot: ProspectingDialerPilot,
    recording: CallRecording,
    leg: ProspectingDialLeg,
    *,
    captured_at: datetime,
) -> bool:
    """Require the canonical signed recording graph for this exact pilot leg."""

    eligibility = prospecting_transcript_eligibility(db, recording)
    signed_events = _signed_recording_events(
        db,
        pilot,
        recording,
        leg,
        captured_at=captured_at,
    )
    return bool(
        eligibility.state in {"eligible", "ineligible"}
        and eligibility.call is not None
        and eligibility.attempt is not None
        and eligibility.leg is not None
        and eligibility.prospect is not None
        and eligibility.call.organization_id == pilot.organization_id
        and eligibility.call.id == leg.call_record_id
        and eligibility.call.prospecting_attempt_id == leg.attempt_id
        and eligibility.call.prospecting_dial_leg_id == leg.id
        and eligibility.attempt.id == leg.attempt_id
        and eligibility.leg.id == leg.id
        and eligibility.prospect.id == leg.prospect_id
        and recording.status == "completed"
        and bool(recording.provider_recording_id)
        and bool(recording.media_reference)
        and recording.recorded_at is not None
        and _as_utc(recording.recorded_at) <= _as_utc(captured_at)
        and recording.retention_expires_at is not None
        and _as_utc(recording.retention_expires_at) > _as_utc(captured_at)
        and signed_events
    )


def _signed_recording_events(
    db: Session,
    pilot: ProspectingDialerPilot,
    recording: CallRecording,
    leg: ProspectingDialLeg,
    *,
    captured_at: datetime,
) -> list[ProspectingProviderEvent]:
    call = _exact_provider_call_record(db, pilot, leg)
    if call is None or recording.provider_recording_id is None:
        return []
    root_id = call.provider_call_id
    child_id = call.child_provider_call_id
    allowed_call_ids = {value for value in (root_id, child_id) if value}
    events = db.scalars(
        select(ProspectingProviderEvent)
        .where(
            ProspectingProviderEvent.organization_id == pilot.organization_id,
            ProspectingProviderEvent.provider == recording.provider,
            ProspectingProviderEvent.dial_session_id == leg.dial_session_id,
            ProspectingProviderEvent.attempt_id == leg.attempt_id,
            ProspectingProviderEvent.dial_leg_id == leg.id,
            ProspectingProviderEvent.provider_recording_id
            == recording.provider_recording_id,
            ProspectingProviderEvent.event_type == "recording.completed",
            ProspectingProviderEvent.signature_verified.is_(True),
            ProspectingProviderEvent.received_at <= _as_utc(captured_at),
        )
        .order_by(ProspectingProviderEvent.id.asc())
    ).all()
    matched: list[ProspectingProviderEvent] = []
    for event in events:
        payload = event.payload or {}
        call_sid = str(payload.get("CallSid") or "").strip()
        parent_sid = str(payload.get("ParentCallSid") or "").strip()
        recording_sid = str(payload.get("RecordingSid") or "").strip()
        lineage_matches = bool(
            (parent_sid and parent_sid == root_id and call_sid == child_id)
            or (not parent_sid and call_sid in allowed_call_ids)
        )
        if (
            event.signature_fingerprint
            and event.payload_sha256
            and event.provider_call_id in allowed_call_ids
            and recording_sid == recording.provider_recording_id
            and lineage_matches
        ):
            matched.append(event)
    return matched


def _recording_identity_snapshot(
    db: Session,
    pilot: ProspectingDialerPilot,
    recordings: list[CallRecording],
    legs_by_call_record_id: dict[UUID, ProspectingDialLeg],
    *,
    captured_at: datetime,
) -> list[dict[str, object]]:
    identities: list[dict[str, object]] = []
    for recording in sorted(recordings, key=lambda item: str(item.id)):
        leg = legs_by_call_record_id.get(recording.call_record_id)
        signed_events = (
            _signed_recording_events(
                db,
                pilot,
                recording,
                leg,
                captured_at=captured_at,
            )
            if leg is not None
            else []
        )
        identities.append(
            {
                "recording_id": str(recording.id),
                "provider": recording.provider,
                "provider_recording_id": recording.provider_recording_id,
                "media_reference": recording.media_reference,
                "signed_event_ids": [str(item.id) for item in signed_events],
                "signed_event_external_ids": [item.external_event_id for item in signed_events],
                "signed_event_payload_hashes": [item.payload_sha256 for item in signed_events],
                "signed_event_signature_fingerprints": [
                    item.signature_fingerprint for item in signed_events
                ],
            }
        )
    return identities


def _valid_smoke_test_evidence(
    db: Session,
    pilot: ProspectingDialerPilot,
    value: dict[str, Any],
    *,
    now: datetime,
) -> bool:
    try:
        evidence = ProspectingDialerPilotSmokeTestEvidence.model_validate(value)
    except ValueError:
        return False
    if not _evidence_time_in_pilot_window(pilot, evidence.completed_at, now):
        return False
    expected_ids = set(evidence.call_record_ids)
    if len(expected_ids) != len(evidence.call_record_ids):
        return False
    pilot_sessions = db.scalars(
        select(ProspectingDialSession).where(
            ProspectingDialSession.organization_id == pilot.organization_id,
            ProspectingDialSession.pilot_id == pilot.id,
            ProspectingDialSession.voice_line_id == pilot.voice_line_id,
        )
    ).all()
    smoke_sessions = [
        item
        for item in pilot_sessions
        if (item.session_metadata or {}).get("acceptance_stage") == "smoke_testing"
    ]
    smoke_session_ids = {item.id for item in smoke_sessions}
    smoke_legs = (
        db.scalars(
            select(ProspectingDialLeg).where(
                ProspectingDialLeg.organization_id == pilot.organization_id,
                ProspectingDialLeg.dial_session_id.in_(smoke_session_ids),
                ProspectingDialLeg.attempt_id.is_not(None),
            )
        ).all()
        if smoke_session_ids
        else []
    )
    legs = [leg for leg in smoke_legs if leg.call_record_id in expected_ids]
    found_ids = {leg.call_record_id for leg in legs}
    found_ids.discard(None)
    controlled_numbers = _pilot_controlled_numbers(pilot)
    completed_at = _as_utc(evidence.completed_at)
    provider_costs = {
        item.provider_call_id: item.actual_cost_cents for item in evidence.provider_cost_items
    }
    provider_started_legs, raw_billable_provider_ids, provider_identity_complete = (
        _provider_identity_graph(db, pilot, smoke_legs)
    )
    billable_provider_ids = set(raw_billable_provider_ids)
    seller_evidence = [
        _seller_child_evidence(db, pilot, leg, captured_at=completed_at) for leg in legs
    ]
    smoke_attempts = {
        item.id: item
        for item in db.scalars(
            select(ProspectingAttempt).where(
                ProspectingAttempt.organization_id == pilot.organization_id,
                ProspectingAttempt.id.in_(
                    [leg.attempt_id for leg in legs if leg.attempt_id is not None]
                ),
            )
        ).all()
    }
    contact_dispositions = [
        _contact_disposition_evidence(
            smoke_attempts[leg.attempt_id],
            leg,
            seller_evidence[index],
        )
        for index, leg in enumerate(legs)
        if leg.attempt_id in smoke_attempts
    ]
    recordings = db.scalars(
        select(CallRecording).where(
            CallRecording.organization_id == pilot.organization_id,
            CallRecording.call_record_id.in_(expected_ids),
            CallRecording.deleted_at.is_(None),
        )
    ).all()
    legs_by_call_record_id = {
        item.call_record_id: item for item in legs if item.call_record_id is not None
    }
    eligible_recordings = bool(
        len(recordings) == len(expected_ids)
        and {item.call_record_id for item in recordings} == expected_ids
        and all(
            item.call_record_id in legs_by_call_record_id
            and _recording_matches_pilot_leg(
                db,
                pilot,
                item,
                legs_by_call_record_id[item.call_record_id],
                captured_at=completed_at,
            )
            for item in recordings
        )
    )
    return bool(
        found_ids == expected_ids
        and bool(expected_ids)
        and len(smoke_legs) <= 50
        and eligible_recordings
        and len(legs) == len(expected_ids)
        and all(item is not None for item in seller_evidence)
        and all(item.get("duration_seconds") is not None for item in seller_evidence if item)
        and all(item.get("contact_evidence") is True for item in seller_evidence if item)
        and len(contact_dispositions) == len(legs)
        and all(
            item.get("right_party_contact") is True for item in contact_dispositions
        )
        and provider_identity_complete
        and bool(provider_started_legs)
        and len(raw_billable_provider_ids) == len(billable_provider_ids)
        and len(provider_costs) == len(evidence.provider_cost_items)
        and set(provider_costs) == billable_provider_ids
        and bool(smoke_sessions)
        and all(
            session.state in TERMINAL_DIAL_SESSION_STATES
            and session.ended_at is not None
            and _as_utc(session.ended_at) <= completed_at
            for session in smoke_sessions
        )
        and all(
            leg.completed_at is not None
            and leg.status in DIAL_LEG_TERMINAL_STATUSES
            and _as_utc(leg.completed_at) <= completed_at
            and format_e164(leg.recipient) in controlled_numbers
            for leg in smoke_legs
        )
        and all(
            leg.completed_at is not None
            and leg.status in DIAL_LEG_TERMINAL_STATUSES
            and (leg.answered_at is not None or leg.connected_at is not None)
            and _as_utc(leg.completed_at) <= completed_at
            and format_e164(leg.recipient) in controlled_numbers
            for leg in legs
        )
    )


def _valid_kill_switch_evidence(
    db: Session,
    pilot: ProspectingDialerPilot,
    value: dict[str, Any],
    *,
    now: datetime,
) -> bool:
    try:
        evidence = ProspectingDialerPilotKillSwitchEvidence.model_validate(value)
    except ValueError:
        return False
    tested_at = _as_utc(evidence.tested_at)
    if not _evidence_time_in_pilot_window(pilot, tested_at, now):
        return False
    observation = _kill_switch_observation(db, pilot, evidence)
    stored_observation = value.get("server_observation")
    return bool(
        observation is not None
        and (
            stored_observation is None
            or stored_observation == observation
        )
    )


def _ordered_switch_pair(
    events: list[AuditEvent],
    *,
    action: str,
    entity_id: UUID,
) -> tuple[AuditEvent, AuditEvent] | None:
    scoped = [
        item for item in events if item.action == action and item.entity_id == entity_id
    ]
    for disabled in reversed(scoped):
        if (disabled.new_value or {}).get("enabled") is not False:
            continue
        enabled = next(
            (
                item
                for item in scoped
                if _as_utc(item.created_at) > _as_utc(disabled.created_at)
                and (item.new_value or {}).get("enabled") is True
            ),
            None,
        )
        if enabled is not None:
            return disabled, enabled
    return None


def _switch_drill_sessions(
    db: Session,
    pilot: ProspectingDialerPilot,
    pair: tuple[AuditEvent, AuditEvent],
) -> list[ProspectingDialSession]:
    disabled, enabled = pair
    sessions = db.scalars(
        select(ProspectingDialSession).where(
            ProspectingDialSession.organization_id == pilot.organization_id,
            ProspectingDialSession.pilot_id == pilot.id,
            ProspectingDialSession.started_at <= disabled.created_at,
            ProspectingDialSession.ended_at.is_not(None),
            ProspectingDialSession.ended_at >= disabled.created_at,
            ProspectingDialSession.ended_at <= enabled.created_at,
            ProspectingDialSession.state.in_(TERMINAL_DIAL_SESSION_STATES),
        )
    ).all()
    return [
        session
        for session in sessions
        if not db.scalar(
            select(func.count(ProspectingDialLeg.id)).where(
                ProspectingDialLeg.organization_id == pilot.organization_id,
                ProspectingDialLeg.dial_session_id == session.id,
                ProspectingDialLeg.completed_at.is_(None),
            )
        )
    ]


def _kill_switch_observation(
    db: Session,
    pilot: ProspectingDialerPilot,
    evidence: ProspectingDialerPilotKillSwitchEvidence,
) -> dict[str, Any] | None:
    tested_at = _as_utc(evidence.tested_at)
    if pilot.started_at is None:
        return None
    events = db.scalars(
        select(AuditEvent)
        .where(
            AuditEvent.organization_id == pilot.organization_id,
            AuditEvent.action.in_(
                (
                    "prospecting.company_dialer_switch_updated",
                    "prospecting.campaign_dialer_switch_updated",
                )
            ),
            AuditEvent.created_at >= max(
                _as_utc(pilot.started_at),
                tested_at - timedelta(hours=12),
            ),
            AuditEvent.created_at <= tested_at,
        )
        .order_by(AuditEvent.created_at.asc(), AuditEvent.id.asc())
    ).all()
    company_pair = _ordered_switch_pair(
        events,
        action="prospecting.company_dialer_switch_updated",
        entity_id=pilot.organization_id,
    )
    campaign_pair = _ordered_switch_pair(
        events,
        action="prospecting.campaign_dialer_switch_updated",
        entity_id=pilot.campaign_id,
    )
    if company_pair is None or campaign_pair is None:
        return None
    company_sessions = _switch_drill_sessions(db, pilot, company_pair)
    campaign_sessions = _switch_drill_sessions(db, pilot, campaign_pair)
    if (
        not company_sessions
        or not campaign_sessions
        or {item.id for item in company_sessions}
        & {item.id for item in campaign_sessions}
    ):
        return None
    local_date, day_start, day_end = _local_shift_bounds(tested_at, pilot.timezone)
    observed_end = min(day_end, tested_at + timedelta(microseconds=1))
    dial_count = (
        db.scalar(
            select(func.count(ProspectingDialLeg.id))
            .join(
                ProspectingDialSession,
                ProspectingDialSession.id == ProspectingDialLeg.dial_session_id,
            )
            .where(
                ProspectingDialSession.organization_id == pilot.organization_id,
                ProspectingDialSession.pilot_id == pilot.id,
                ProspectingDialSession.caller_user_id == pilot.caller_user_id,
                ProspectingDialLeg.queued_at >= day_start,
                ProspectingDialLeg.queued_at < observed_end,
            )
        )
        or 0
    )
    if dial_count < pilot.daily_dial_limit:
        return None
    cap_block_events = db.scalars(
        select(AuditEvent)
        .where(
            AuditEvent.organization_id == pilot.organization_id,
            AuditEvent.action == "prospecting.dialer_pilot_daily_cap_blocked",
            AuditEvent.entity_type == "prospecting_dialer_pilot",
            AuditEvent.entity_id == pilot.id,
            AuditEvent.created_at >= day_start,
            AuditEvent.created_at <= tested_at,
        )
        .order_by(AuditEvent.created_at.asc(), AuditEvent.id.asc())
    ).all()
    cap_block_event = next(
        (
            item
            for item in cap_block_events
            if (item.new_value or {}).get("pilot_id") == str(pilot.id)
            and (item.new_value or {}).get("caller_user_id") == str(pilot.caller_user_id)
            and (item.new_value or {}).get("campaign_id") == str(pilot.campaign_id)
            and (item.new_value or {}).get("cohort_id") == str(pilot.cohort_id)
            and (item.new_value or {}).get("prospect_calling_batch_id")
            == str(pilot.prospect_calling_batch_id)
            and (item.new_value or {}).get("local_date") == local_date.isoformat()
            and (item.new_value or {}).get("daily_dial_limit") == pilot.daily_dial_limit
            and int((item.new_value or {}).get("observed_dial_count") or 0)
            >= pilot.daily_dial_limit
        ),
        None,
    )
    if cap_block_event is None:
        return None
    active_sessions_at_test = (
        db.scalar(
            select(func.count(ProspectingDialSession.id)).where(
                ProspectingDialSession.organization_id == pilot.organization_id,
                ProspectingDialSession.pilot_id == pilot.id,
                ProspectingDialSession.started_at <= tested_at,
                or_(
                    ProspectingDialSession.ended_at.is_(None),
                    ProspectingDialSession.ended_at > tested_at,
                ),
            )
        )
        or 0
    )
    if active_sessions_at_test:
        return None
    return {
        "company_off_audit_id": str(company_pair[0].id),
        "company_on_audit_id": str(company_pair[1].id),
        "campaign_off_audit_id": str(campaign_pair[0].id),
        "campaign_on_audit_id": str(campaign_pair[1].id),
        "company_stopped_session_ids": sorted(str(item.id) for item in company_sessions),
        "campaign_stopped_session_ids": sorted(str(item.id) for item in campaign_sessions),
        "daily_cap_block_audit_id": str(cap_block_event.id),
        "observed_daily_dial_count": dial_count,
        "enforced_daily_dial_limit": pilot.daily_dial_limit,
        "active_sessions_at_test": 0,
        "observed_at": tested_at.isoformat(),
    }


def _valid_batch_comparison_evidence(value: dict[str, Any]) -> bool:
    try:
        ProspectingDialerPilotBatchComparisonEvidence.model_validate(value)
    except ValueError:
        return False
    return True


def _rollback_observation(
    db: Session,
    pilot: ProspectingDialerPilot,
    evidence: ProspectingDialerPilotRollbackEvidence,
) -> dict[str, Any] | None:
    """Capture a later, server-observed rollback drill without mutating prior evidence."""

    tested_at = _as_utc(evidence.tested_at)
    kill_tested_at = _evidence_datetime(pilot.kill_switch_evidence, "tested_at")
    if pilot.started_at is None or kill_tested_at is None or tested_at <= kill_tested_at:
        return None
    events = db.scalars(
        select(AuditEvent)
        .where(
            AuditEvent.organization_id == pilot.organization_id,
            AuditEvent.action == "prospecting.campaign_dialer_switch_updated",
            AuditEvent.entity_id == pilot.campaign_id,
            AuditEvent.created_at > kill_tested_at,
            AuditEvent.created_at <= tested_at,
        )
        .order_by(AuditEvent.created_at.asc(), AuditEvent.id.asc())
    ).all()
    campaign_pair = _ordered_switch_pair(
        events,
        action="prospecting.campaign_dialer_switch_updated",
        entity_id=pilot.campaign_id,
    )
    if campaign_pair is None:
        return None
    kill_observation = (pilot.kill_switch_evidence or {}).get("server_observation") or {}
    if str(campaign_pair[0].id) in {
        kill_observation.get("campaign_off_audit_id"),
        kill_observation.get("campaign_on_audit_id"),
    } or str(campaign_pair[1].id) in {
        kill_observation.get("campaign_off_audit_id"),
        kill_observation.get("campaign_on_audit_id"),
    }:
        return None
    stopped_sessions = _switch_drill_sessions(db, pilot, campaign_pair)
    if not stopped_sessions:
        return None
    active_sessions = (
        db.scalar(
            select(func.count(ProspectingDialSession.id)).where(
                ProspectingDialSession.organization_id == pilot.organization_id,
                ProspectingDialSession.pilot_id == pilot.id,
                ProspectingDialSession.started_at <= tested_at,
                or_(
                    ProspectingDialSession.ended_at.is_(None),
                    ProspectingDialSession.ended_at > tested_at,
                ),
            )
        )
        or 0
    )
    active_legs = (
        db.scalar(
            select(func.count(ProspectingDialLeg.id))
            .join(
                ProspectingDialSession,
                ProspectingDialSession.id == ProspectingDialLeg.dial_session_id,
            )
            .where(
                ProspectingDialSession.organization_id == pilot.organization_id,
                ProspectingDialSession.pilot_id == pilot.id,
                ProspectingDialLeg.queued_at <= tested_at,
                or_(
                    ProspectingDialLeg.completed_at.is_(None),
                    ProspectingDialLeg.completed_at > tested_at,
                ),
            )
        )
        or 0
    )
    if active_sessions or active_legs:
        return None
    entries = db.scalars(
        select(ProspectCallingBatchEntry)
        .where(
            ProspectCallingBatchEntry.organization_id == pilot.organization_id,
            ProspectCallingBatchEntry.prospect_calling_batch_id
            == pilot.prospect_calling_batch_id,
            ProspectCallingBatchEntry.status.in_(("queued", "ready")),
            ProspectCallingBatchEntry.attempt_count == 0,
            ProspectCallingBatchEntry.completed_at.is_(None),
        )
        .order_by(
            ProspectCallingBatchEntry.sequence_number.asc(),
            ProspectCallingBatchEntry.id.asc(),
        )
    ).all()
    if not entries:
        return None
    unworked_members = [
        {
            "entry_id": str(item.id),
            "prospect_id": str(item.prospect_id),
            "assigned_user_id": str(item.assigned_user_id),
            "sequence_number": item.sequence_number,
        }
        for item in entries
    ]
    attempt_reviews = db.scalars(
        select(ProspectingDialerPilotAttemptReview)
        .where(
            ProspectingDialerPilotAttemptReview.pilot_id == pilot.id,
            ProspectingDialerPilotAttemptReview.reviewed_at <= tested_at,
        )
        .order_by(ProspectingDialerPilotAttemptReview.id.asc())
    ).all()
    shift_reviews = db.scalars(
        select(ProspectingDialerPilotShiftReview)
        .where(
            ProspectingDialerPilotShiftReview.pilot_id == pilot.id,
            ProspectingDialerPilotShiftReview.reviewed_at <= tested_at,
        )
        .order_by(ProspectingDialerPilotShiftReview.id.asc())
    ).all()
    if not attempt_reviews:
        return None
    return {
        "campaign_off_audit_id": str(campaign_pair[0].id),
        "campaign_on_audit_id": str(campaign_pair[1].id),
        "stopped_session_ids": sorted(str(item.id) for item in stopped_sessions),
        "active_sessions_at_test": 0,
        "active_legs_at_test": 0,
        "unworked_entry_count": len(unworked_members),
        "unworked_entry_ids": [item["entry_id"] for item in unworked_members],
        "unworked_membership_hash": _hash_json(unworked_members),
        "preserved_attempt_review_hashes": {
            str(item.id): item.evidence_hash for item in attempt_reviews
        },
        "preserved_shift_review_hashes": {
            str(item.id): item.evidence_hash for item in shift_reviews
        },
        "observed_at": tested_at.isoformat(),
    }


def _rollback_observation_is_valid(
    db: Session,
    pilot: ProspectingDialerPilot,
    evidence: ProspectingDialerPilotRollbackEvidence,
    observation: object,
) -> bool:
    if not isinstance(observation, dict):
        return False
    tested_at = _as_utc(evidence.tested_at)
    if observation.get("observed_at") != tested_at.isoformat():
        return False
    try:
        off_id = UUID(str(observation["campaign_off_audit_id"]))
        on_id = UUID(str(observation["campaign_on_audit_id"]))
        session_ids = {UUID(str(value)) for value in observation["stopped_session_ids"]}
        unworked_ids = [UUID(str(value)) for value in observation["unworked_entry_ids"]]
        attempt_hashes = {
            UUID(str(key)): value
            for key, value in observation["preserved_attempt_review_hashes"].items()
        }
        shift_hashes = {
            UUID(str(key)): value
            for key, value in observation["preserved_shift_review_hashes"].items()
        }
    except (KeyError, TypeError, ValueError, AttributeError):
        return False
    if not session_ids or not unworked_ids or not attempt_hashes:
        return False
    off_event = db.get(AuditEvent, off_id)
    on_event = db.get(AuditEvent, on_id)
    kill_tested_at = _evidence_datetime(pilot.kill_switch_evidence, "tested_at")
    if (
        off_event is None
        or on_event is None
        or kill_tested_at is None
        or off_event.organization_id != pilot.organization_id
        or on_event.organization_id != pilot.organization_id
        or off_event.entity_id != pilot.campaign_id
        or on_event.entity_id != pilot.campaign_id
        or off_event.action != "prospecting.campaign_dialer_switch_updated"
        or on_event.action != "prospecting.campaign_dialer_switch_updated"
        or (off_event.new_value or {}).get("enabled") is not False
        or (on_event.new_value or {}).get("enabled") is not True
        or not (
            kill_tested_at
            < _as_utc(off_event.created_at)
            < _as_utc(on_event.created_at)
            <= tested_at
        )
    ):
        return False
    sessions = db.scalars(
        select(ProspectingDialSession).where(
            ProspectingDialSession.organization_id == pilot.organization_id,
            ProspectingDialSession.pilot_id == pilot.id,
            ProspectingDialSession.id.in_(session_ids),
        )
    ).all()
    if len(sessions) != len(session_ids) or any(
        item.state not in TERMINAL_DIAL_SESSION_STATES
        or item.ended_at is None
        or not (
            _as_utc(off_event.created_at)
            <= _as_utc(item.ended_at)
            <= _as_utc(on_event.created_at)
        )
        for item in sessions
    ):
        return False
    incomplete_stopped_legs = (
        db.scalar(
            select(func.count(ProspectingDialLeg.id)).where(
                ProspectingDialLeg.organization_id == pilot.organization_id,
                ProspectingDialLeg.dial_session_id.in_(session_ids),
                ProspectingDialLeg.completed_at.is_(None),
            )
        )
        or 0
    )
    active_sessions_at_test = (
        db.scalar(
            select(func.count(ProspectingDialSession.id)).where(
                ProspectingDialSession.organization_id == pilot.organization_id,
                ProspectingDialSession.pilot_id == pilot.id,
                ProspectingDialSession.started_at <= tested_at,
                or_(
                    ProspectingDialSession.ended_at.is_(None),
                    ProspectingDialSession.ended_at > tested_at,
                ),
            )
        )
        or 0
    )
    active_legs_at_test = (
        db.scalar(
            select(func.count(ProspectingDialLeg.id))
            .join(
                ProspectingDialSession,
                ProspectingDialSession.id == ProspectingDialLeg.dial_session_id,
            )
            .where(
                ProspectingDialSession.organization_id == pilot.organization_id,
                ProspectingDialSession.pilot_id == pilot.id,
                ProspectingDialLeg.queued_at <= tested_at,
                or_(
                    ProspectingDialLeg.completed_at.is_(None),
                    ProspectingDialLeg.completed_at > tested_at,
                ),
            )
        )
        or 0
    )
    if incomplete_stopped_legs or active_sessions_at_test or active_legs_at_test:
        return False
    entries = db.scalars(
        select(ProspectCallingBatchEntry)
        .where(
            ProspectCallingBatchEntry.organization_id == pilot.organization_id,
            ProspectCallingBatchEntry.prospect_calling_batch_id
            == pilot.prospect_calling_batch_id,
            ProspectCallingBatchEntry.id.in_(unworked_ids),
        )
    ).all()
    entries_by_id = {item.id: item for item in entries}
    members = [
        {
            "entry_id": str(item.id),
            "prospect_id": str(item.prospect_id),
            "assigned_user_id": str(item.assigned_user_id),
            "sequence_number": item.sequence_number,
        }
        for entry_id in unworked_ids
        if (item := entries_by_id.get(entry_id)) is not None
    ]
    pre_drill_attempt_count = (
        db.scalar(
            select(func.count(ProspectingAttempt.id)).where(
                ProspectingAttempt.organization_id == pilot.organization_id,
                ProspectingAttempt.batch_entry_id.in_(unworked_ids),
                ProspectingAttempt.created_at <= tested_at,
            )
        )
        or 0
    )
    if (
        len(entries) != len(unworked_ids)
        or pre_drill_attempt_count != 0
        or observation.get("unworked_entry_count") != len(unworked_ids)
        or observation.get("unworked_membership_hash") != _hash_json(members)
    ):
        return False
    stored_attempts = dict(
        db.execute(
            select(
                ProspectingDialerPilotAttemptReview.id,
                ProspectingDialerPilotAttemptReview.evidence_hash,
            ).where(
                ProspectingDialerPilotAttemptReview.pilot_id == pilot.id,
                ProspectingDialerPilotAttemptReview.id.in_(attempt_hashes),
            )
        ).all()
    )
    stored_shifts = dict(
        db.execute(
            select(
                ProspectingDialerPilotShiftReview.id,
                ProspectingDialerPilotShiftReview.evidence_hash,
            ).where(
                ProspectingDialerPilotShiftReview.pilot_id == pilot.id,
                ProspectingDialerPilotShiftReview.id.in_(shift_hashes),
            )
        ).all()
    )
    return bool(
        stored_attempts == attempt_hashes
        and stored_shifts == shift_hashes
        and observation.get("active_sessions_at_test") == 0
        and observation.get("active_legs_at_test") == 0
    )


def _valid_rollback_evidence(
    db: Session,
    pilot: ProspectingDialerPilot,
    value: dict[str, Any],
    *,
    now: datetime,
) -> bool:
    try:
        evidence = ProspectingDialerPilotRollbackEvidence.model_validate(value)
    except ValueError:
        return False
    if not _evidence_time_in_pilot_window(pilot, evidence.tested_at, now):
        return False
    observation = value.get("server_observation")
    if observation is None:
        return _rollback_observation(db, pilot, evidence) is not None
    return _rollback_observation_is_valid(db, pilot, evidence, observation)


def _evidence_time_in_pilot_window(
    pilot: ProspectingDialerPilot,
    value: datetime,
    now: datetime,
) -> bool:
    if pilot.started_at is None:
        return False
    tested_at = _as_utc(value)
    return _as_utc(pilot.started_at) <= tested_at <= _as_utc(now) + timedelta(minutes=5)
