from datetime import UTC, date, datetime, timedelta
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from pytest import MonkeyPatch
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.auth import Principal
from app.core.config import Settings, get_settings
from app.domain.rbac import PermissionKeys
from app.main import app
from app.models.foundation import (
    CallRecord,
    Campaign,
    Prospect,
    ProspectCallingBatchEntry,
    ProspectingAttempt,
    ProspectingDialerPilot,
    ProspectingDialerPilotShiftReview,
    ProspectingDialerProfile,
    ProspectingDialLeg,
    ProspectingDialSession,
    ProspectingProviderEvent,
    VoiceCallIntent,
    VoiceLine,
)
from app.schemas.prospecting import ProspectingDialSessionStart
from app.schemas.prospecting_dialer_acceptance import (
    ProspectingDialerPilotAttemptReviewCreate,
    ProspectingDialerPilotCreate,
    ProspectingDialerPilotProviderCostItem,
    ProspectingDialerPilotRevoke,
    ProspectingDialerPilotRollback,
    ProspectingDialerPilotShiftReviewCreate,
    ProspectingDialerPilotStart,
)
from app.services.prospecting_dialer import load_runtime_graph, start_dial_session
from app.services.prospecting_dialer_acceptance import (
    PILOT_REVOKE_PHRASE,
    PILOT_ROLLBACK_PHRASE,
    ProspectingDialerAcceptanceConflictError,
    _attempt_membership,
    _attempt_review_queue,
    _attempt_snapshot,
    _attempt_snapshot_passed,
    _batch_membership_snapshot,
    _contact_disposition_evidence,
    _global_pilot_call_integrity,
    _recording_identity_snapshot,
    _recording_matches_pilot_leg,
    _shift_snapshot,
    create_prospecting_dialer_pilot,
    matching_active_pilot,
    pilot_configuration_fingerprint,
    review_prospecting_dialer_pilot_attempt,
    review_prospecting_dialer_pilot_shift,
    revoke_prospecting_dialer_pilot,
    rollback_prospecting_dialer_pilot,
    start_prospecting_dialer_pilot,
)
from tests.test_prospecting_call_evidence import seed_eligible_recording
from tests.test_prospecting_dialer_coordinator import (
    CoordinatorGraph,
    seed_coordinator_graph,
)


@pytest.fixture
def d10_settings(monkeypatch: MonkeyPatch) -> Settings:
    values = {
        "PROSPECTING_NATIVE_DIALER_ENABLED": "true",
        "PROSPECTING_NATIVE_DIALER_MAX_LINES": "1",
        "PROSPECTING_NATIVE_DIALER_LEASE_SECONDS": "90",
        "PROSPECTING_NATIVE_DIALER_STALE_AFTER_SECONDS": "60",
        "PROSPECTING_NATIVE_DIALER_ORPHAN_GRACE_SECONDS": "60",
        "PROSPECTING_NATIVE_DIALER_RESERVED_COST_CENTS": "5",
        "TWILIO_VOICE_ENABLED": "true",
        "TWILIO_ACCOUNT_SID": "AC00000000000000000000000000000000",
        "TWILIO_AUTH_TOKEN": "d10-acceptance-test-auth-token",
        "TWILIO_WEBHOOK_BASE_URL": "https://api.stonegate.test",
        "TWILIO_VALIDATE_WEBHOOK_SIGNATURES": "true",
        "TWILIO_API_KEY_SID": "SK00000000000000000000000000000000",
        "TWILIO_API_KEY_SECRET": "d10-browser-key-secret",
        "TWILIO_TWIML_APP_SID": "AP00000000000000000000000000000000",
        "TWILIO_VOICE_RECORDING_ENABLED": "true",
        "CALL_RECORDING_RETENTION_DAYS": "180",
        "CALL_TRANSCRIPTION_ENABLED": "true",
    }
    for key, value in values.items():
        monkeypatch.setenv(key, value)
    get_settings.cache_clear()
    settings = get_settings()
    yield settings
    get_settings.cache_clear()


def _manager_principal(graph: CoordinatorGraph) -> Principal:
    return Principal(
        user_id=graph.owner.id,
        organization_id=graph.organization.id,
        email=graph.owner.email,
        permission_keys=frozenset({PermissionKeys.MANAGE_ACQUISITION_OPERATIONS}),
    )


def _owner_principal(graph: CoordinatorGraph) -> Principal:
    return Principal(
        user_id=graph.owner.id,
        organization_id=graph.organization.id,
        email=graph.owner.email,
        permission_keys=frozenset(),
    )


def _non_owner_manager_principal(graph: CoordinatorGraph) -> Principal:
    return Principal(
        user_id=graph.caller.id,
        organization_id=graph.organization.id,
        email=graph.caller.email,
        permission_keys=frozenset({PermissionKeys.MANAGE_ACQUISITION_OPERATIONS}),
    )


def _d10_graph(db: Session) -> tuple[CoordinatorGraph, Prospect, Prospect]:
    graph = seed_coordinator_graph(db, record_count=75)
    line = db.scalar(
        select(VoiceLine).where(
            VoiceLine.organization_id == graph.organization.id,
            VoiceLine.assigned_user_id == graph.caller.id,
        )
    )
    profile = db.scalar(
        select(ProspectingDialerProfile).where(
            ProspectingDialerProfile.organization_id == graph.organization.id,
            ProspectingDialerProfile.user_id == graph.caller.id,
        )
    )
    assert line is not None
    assert profile is not None
    first = db.get(Prospect, graph.entries[0].prospect_id)
    second = db.get(Prospect, graph.entries[1].prospect_id)
    assert first is not None
    assert second is not None

    graph.organization.prospecting_dialer_max_concurrent_legs = 1
    graph.organization.prospecting_dialer_acceptance_required = True
    graph.campaign.prospecting_dialer_max_concurrent_legs = 1
    line.prospecting_dialer_max_concurrent_legs = 1
    profile.default_line_count = 1
    profile.max_line_count = 1
    profile.daily_dial_limit = 50
    profile.daily_spend_limit_cents = 1000
    graph.caller.voice_forwarding_number = first.normalized_phone
    db.commit()
    return graph, first, second


def _create_payload(
    db: Session,
    graph: CoordinatorGraph,
    *,
    key: str,
) -> ProspectingDialerPilotCreate:
    line = db.scalar(
        select(VoiceLine).where(
            VoiceLine.organization_id == graph.organization.id,
            VoiceLine.assigned_user_id == graph.caller.id,
        )
    )
    assert line is not None
    return ProspectingDialerPilotCreate(
        expected_revision=0,
        idempotency_key=key,
        caller_user_id=graph.caller.id,
        campaign_id=graph.campaign.id,
        cohort_id=graph.cohort.id,
        prospect_calling_batch_id=graph.batch.id,
        voice_line_id=line.id,
    )


def _create_pilot(
    db: Session,
    graph: CoordinatorGraph,
    settings: Settings,
    *,
    key: str,
):
    result = create_prospecting_dialer_pilot(
        db,
        _manager_principal(graph),
        _create_payload(db, graph, key=key),
        settings=settings,
    )
    assert result.pilot is not None
    return result.pilot


def _start_pilot(
    db: Session,
    graph: CoordinatorGraph,
    settings: Settings,
    controlled_phone: str,
    monkeypatch: MonkeyPatch,
    *,
    key: str,
):
    monkeypatch.setattr(
        "app.services.prospecting_dialer_acceptance._launch_readiness",
        lambda *_args, **_kwargs: SimpleNamespace(
            controlled_pilot_ready=True,
            blockers=[],
        ),
    )
    pilot = _create_pilot(db, graph, settings, key=f"create-{key}")
    result = start_prospecting_dialer_pilot(
        db,
        _manager_principal(graph),
        pilot.id,
        ProspectingDialerPilotStart(
            expected_revision=pilot.revision,
            idempotency_key=f"start-{key}",
            controlled_numbers_only=True,
            controlled_phone_numbers=[controlled_phone],
            controlled_number_evidence="Controlled number belongs to active Stonegate staff.",
            batchdialer_cohort_is_separate=True,
            batchdialer_non_overlap_evidence="D10 acceptance-only test cohort.",
            reason="Start the controlled D10 acceptance test.",
        ),
        settings=settings,
    )
    assert result is not None
    assert result.pilot is not None
    return result.pilot


def test_pilot_rejects_daily_cap_below_clean_shift_minimum(
    db_session: Session,
    d10_settings: Settings,
) -> None:
    graph, _, _ = _d10_graph(db_session)
    profile = db_session.scalar(
        select(ProspectingDialerProfile).where(
            ProspectingDialerProfile.organization_id == graph.organization.id,
            ProspectingDialerProfile.user_id == graph.caller.id,
        )
    )
    assert profile is not None
    profile.daily_dial_limit = 24
    db_session.commit()

    with pytest.raises(ValueError, match="daily dial cap must be set between 25 and 50"):
        create_prospecting_dialer_pilot(
            db_session,
            _manager_principal(graph),
            _create_payload(db_session, graph, key="cap-below-clean-shift-minimum"),
            settings=d10_settings,
        )

    profile.daily_dial_limit = 25
    db_session.commit()
    created = _create_pilot(db_session, graph, d10_settings, key="cap-at-minimum")
    assert created.daily_dial_limit == 25


def _start_runtime_session(
    db: Session,
    graph: CoordinatorGraph,
    settings: Settings,
    *,
    key: str,
):
    result = start_dial_session(
        db,
        graph.principal,
        ProspectingDialSessionStart(
            campaign_id=graph.campaign.id,
            cohort_id=graph.cohort.id,
            calling_batch_id=graph.batch.id,
            browser_session_id=f"browser-{key}",
            idempotency_key=f"session-{key}",
            requested_line_count=1,
        ),
        settings=settings,
        now=datetime.now(UTC),
    )
    assert result is not None
    assert result.snapshot.current_leg is not None
    return result


def _attach_exact_provider_graph(
    db: Session,
    graph: CoordinatorGraph,
    session: ProspectingDialSession,
    leg: ProspectingDialLeg,
    attempt: ProspectingAttempt,
    *,
    root_provider_call_id: str,
    completed_at: datetime,
    child_provider_call_id: str | None = None,
    duration_seconds: int = 0,
    contact_made: bool = False,
) -> CallRecord:
    line = db.get(VoiceLine, session.voice_line_id)
    assert line is not None
    intent = VoiceCallIntent(
        organization_id=graph.organization.id,
        conversation_id=None,
        lead_id=None,
        contact_id=None,
        prospect_id=leg.prospect_id,
        prospecting_attempt_id=attempt.id,
        prospecting_dial_leg_id=leg.id,
        actor_user_id=graph.caller.id,
        voice_line_id=session.voice_line_id,
        idempotency_key=f"intent-{root_provider_call_id}",
        recipient=leg.recipient,
        status="started",
        recording_consent_status="disclosed",
        expires_at=completed_at + timedelta(minutes=5),
        consumed_at=completed_at,
        provider_call_id=root_provider_call_id,
        intent_metadata={
            "source": "native_prospecting_dialer",
            "dialer_mode": "one_line_power",
            "connection_mode": "browser_softphone",
            "provider_start_state": "started",
        },
    )
    db.add(intent)
    db.flush()
    call = CallRecord(
        organization_id=graph.organization.id,
        conversation_id=None,
        lead_id=None,
        contact_id=None,
        prospect_id=leg.prospect_id,
        prospecting_attempt_id=attempt.id,
        prospecting_dial_leg_id=leg.id,
        prospecting_inbound_callback_id=None,
        actor_user_id=graph.caller.id,
        communication_record_id=None,
        voice_line_id=session.voice_line_id,
        call_intent_id=intent.id,
        provider="twilio",
        provider_call_id=root_provider_call_id,
        child_provider_call_id=child_provider_call_id,
        direction="outbound",
        status="completed" if contact_made else leg.status,
        from_number=line.phone_number,
        to_number=leg.recipient,
        started_at=attempt.started_at,
        answered_at=completed_at if contact_made else None,
        ended_at=completed_at,
        duration_seconds=duration_seconds,
        disposition=attempt.outcome,
        recording_consent_status="disclosed",
        call_metadata={"source": "native_prospecting_dialer"},
    )
    db.add(call)
    db.flush()
    leg.call_record_id = call.id
    leg.provider = "twilio"
    leg.provider_call_id = root_provider_call_id
    attempt.call_record_id = call.id
    attempt.provider = "twilio"
    attempt.provider_call_id = root_provider_call_id
    if child_provider_call_id is not None:
        status = "completed" if contact_made else "no_answer"
        db.add(
            ProspectingProviderEvent(
                organization_id=graph.organization.id,
                provider_campaign_sync_id=None,
                provider_contact_sync_id=None,
                batch_entry_id=leg.batch_entry_id,
                attempt_id=attempt.id,
                dial_session_id=session.id,
                dial_leg_id=leg.id,
                provider="twilio",
                external_event_id=f"signed-child-{child_provider_call_id}-{status}",
                event_type=f"call.{status}",
                processing_status="processed",
                provider_call_id=child_provider_call_id,
                provider_recording_id=None,
                provider_sequence_number=None,
                occurred_at=completed_at,
                signature_verified=True,
                signature_fingerprint="a" * 64,
                payload_sha256="b" * 64,
                payload={
                    "CallSid": root_provider_call_id,
                    "DialCallSid": child_provider_call_id,
                    "DialCallStatus": status,
                    "DialCallDuration": str(duration_seconds),
                },
                retry_count=0,
                error_message=None,
                received_at=completed_at,
                processed_at=completed_at,
            )
        )
    db.flush()
    return call


def _set_exact_provider_costs(
    leg: ProspectingDialLeg,
    provider_call_ids: list[str],
) -> None:
    items = sorted(
        [
            {
                "provider_call_id": provider_call_id,
                "actual_cost_cents": 0,
                "currency": "USD",
                "provider_reference": f"provider-row-{provider_call_id}",
            }
            for provider_call_id in provider_call_ids
        ],
        key=lambda item: item["provider_call_id"],
    )
    leg.leg_metadata = {
        **(leg.leg_metadata or {}),
        "d10_provider_cost_items": items,
    }
    leg.actual_cost_cents = 0


def _accepted_pilot(
    db: Session,
    graph: CoordinatorGraph,
    settings: Settings,
) -> ProspectingDialerPilot:
    runtime_graph = load_runtime_graph(
        db,
        graph.principal,
        campaign_id=graph.campaign.id,
        cohort_id=graph.cohort.id,
        batch_id=graph.batch.id,
    )
    assert runtime_graph is not None
    now = datetime.now(UTC)
    membership = _batch_membership_snapshot(
        db,
        graph.organization.id,
        graph.batch.id,
    )
    pilot = ProspectingDialerPilot(
        organization_id=graph.organization.id,
        caller_user_id=graph.caller.id,
        campaign_id=graph.campaign.id,
        cohort_id=graph.cohort.id,
        prospect_calling_batch_id=graph.batch.id,
        voice_line_id=runtime_graph.line.id,
        status="accepted",
        revision=7,
        effective_line_count=1,
        timezone=graph.cohort.timezone,
        required_clean_shift_count=3,
        minimum_attempts_per_shift=25,
        minimum_productive_minutes_per_shift=60,
        minimum_total_attempts=75,
        minimum_batch_size=75,
        maximum_batch_size=250,
        daily_dial_limit=50,
        daily_spend_limit_cents=1000,
        configuration_fingerprint=pilot_configuration_fingerprint(runtime_graph, settings),
        start_attestation={
            "controlled_phone_numbers": [graph.caller.voice_forwarding_number],
            "controlled_number_staff_owners": {
                graph.caller.voice_forwarding_number: [str(graph.caller.id)]
            },
            "batch_entry_count": membership["entry_count"],
            "batch_membership_hash": membership["membership_hash"],
        },
        smoke_test_evidence={},
        kill_switch_evidence={},
        batchdialer_comparison_evidence={},
        rollback_evidence={},
        final_evidence_snapshot={"policy_version": "d10-test"},
        evidence_hash="e" * 64,
        created_by_user_id=graph.owner.id,
        updated_by_user_id=graph.owner.id,
        started_by_user_id=graph.owner.id,
        started_at=now - timedelta(days=4),
        submitted_by_user_id=graph.owner.id,
        submitted_at=now - timedelta(days=1),
        submission_reason="Controlled evidence submitted.",
        accepted_by_user_id=graph.owner.id,
        accepted_at=now,
        acceptance_reason="Owner accepted the controlled single-line scope.",
    )
    db.add(pilot)
    db.commit()
    db.refresh(pilot)
    return pilot


def test_draft_rollback_is_a_durable_cancel_and_allows_replacement(
    db_session: Session,
    d10_settings: Settings,
) -> None:
    graph, _, _ = _d10_graph(db_session)
    manager = _manager_principal(graph)
    pilot = _create_pilot(db_session, graph, d10_settings, key="draft-one")

    with pytest.raises(ValueError, match="Type exactly"):
        rollback_prospecting_dialer_pilot(
            db_session,
            manager,
            pilot.id,
            ProspectingDialerPilotRollback(
                expected_revision=pilot.revision,
                idempotency_key="cancel-draft-wrong-phrase",
                confirmation_phrase="ROLLBACK",
                return_unworked_cohort_to_batchdialer=True,
                preserve_native_evidence_read_only=True,
                reason="Cancel the unused draft.",
            ),
            settings=d10_settings,
        )

    payload = ProspectingDialerPilotRollback(
        expected_revision=pilot.revision,
        idempotency_key="cancel-draft",
        confirmation_phrase=PILOT_ROLLBACK_PHRASE,
        return_unworked_cohort_to_batchdialer=True,
        preserve_native_evidence_read_only=True,
        reason="Cancel the unused draft without pretending a live rollback occurred.",
    )
    cancelled = rollback_prospecting_dialer_pilot(
        db_session,
        manager,
        pilot.id,
        payload,
        settings=d10_settings,
    )
    assert cancelled is not None
    assert cancelled.pilot is not None
    assert cancelled.pilot.status == "cancelled"
    assert cancelled.pilot.cancelled_at is not None
    assert cancelled.pilot.cancellation_reason == payload.reason

    replay = rollback_prospecting_dialer_pilot(
        db_session,
        manager,
        pilot.id,
        payload,
        settings=d10_settings,
    )
    assert replay is not None
    assert replay.pilot is not None
    assert replay.pilot.revision == cancelled.pilot.revision

    replacement = _create_pilot(db_session, graph, d10_settings, key="draft-two")
    assert replacement.status == "draft"
    assert replacement.id != pilot.id


def test_smoke_number_must_be_current_active_staff_and_runtime_rechecks_ownership(
    db_session: Session,
    d10_settings: Settings,
    monkeypatch: MonkeyPatch,
) -> None:
    graph, first, second = _d10_graph(db_session)
    monkeypatch.setattr(
        "app.services.prospecting_dialer_acceptance._launch_readiness",
        lambda *_args, **_kwargs: SimpleNamespace(
            controlled_pilot_ready=True,
            blockers=[],
        ),
    )
    pilot = _create_pilot(db_session, graph, d10_settings, key="staff-proof")

    with pytest.raises(ValueError, match="active Stonegate staff"):
        start_prospecting_dialer_pilot(
            db_session,
            _manager_principal(graph),
            pilot.id,
            ProspectingDialerPilotStart(
                expected_revision=pilot.revision,
                idempotency_key="reject-non-staff",
                controlled_numbers_only=True,
                controlled_phone_numbers=[second.normalized_phone],
                controlled_number_evidence="This is deliberately not a staff number.",
                batchdialer_cohort_is_separate=True,
                batchdialer_non_overlap_evidence="Separate test cohort.",
                reason="Prove non-staff smoke calls fail closed.",
            ),
            settings=d10_settings,
        )

    started = start_prospecting_dialer_pilot(
        db_session,
        _manager_principal(graph),
        pilot.id,
        ProspectingDialerPilotStart(
            expected_revision=pilot.revision,
            idempotency_key="accept-current-staff",
            controlled_numbers_only=True,
            controlled_phone_numbers=[first.normalized_phone],
            controlled_number_evidence="Current active caller forwarding number.",
            batchdialer_cohort_is_separate=True,
            batchdialer_non_overlap_evidence="Separate test cohort.",
            reason="Begin a staff-owned smoke test.",
        ),
        settings=d10_settings,
    )
    assert started is not None
    assert started.pilot is not None
    runtime_graph = load_runtime_graph(
        db_session,
        graph.principal,
        campaign_id=graph.campaign.id,
        cohort_id=graph.cohort.id,
        batch_id=graph.batch.id,
    )
    assert runtime_graph is not None
    assert matching_active_pilot(db_session, runtime_graph, d10_settings) is not None

    graph.caller.voice_forwarding_number = second.normalized_phone
    db_session.commit()
    assert matching_active_pilot(db_session, runtime_graph, d10_settings) is None


def test_attempt_review_rejects_a_leg_from_another_batch_entry(
    db_session: Session,
    d10_settings: Settings,
    monkeypatch: MonkeyPatch,
) -> None:
    graph, first, _ = _d10_graph(db_session)
    pilot_read = _start_pilot(
        db_session,
        graph,
        d10_settings,
        first.normalized_phone,
        monkeypatch,
        key="cross-membership",
    )
    started = _start_runtime_session(
        db_session,
        graph,
        d10_settings,
        key="cross-membership",
    )
    leg = db_session.get(ProspectingDialLeg, started.snapshot.current_leg.id)
    attempt = db_session.get(
        ProspectingAttempt,
        started.snapshot.session.current_attempt_id,
    )
    pilot = db_session.get(ProspectingDialerPilot, pilot_read.id)
    assert leg is not None
    assert attempt is not None
    assert pilot is not None
    leg.provider_call_id = "CA-cross-membership"
    leg.batch_entry_id = graph.entries[1].id
    db_session.commit()

    found_attempt, found_session, legs = _attempt_membership(
        db_session,
        pilot,
        attempt.id,
    )
    assert found_attempt is None
    assert found_session is None
    assert [item.id for item in legs] == [leg.id]


def test_voicemail_attempt_passes_without_recording_or_transcript(
    db_session: Session,
    d10_settings: Settings,
    monkeypatch: MonkeyPatch,
) -> None:
    graph, first, _ = _d10_graph(db_session)
    pilot_read = _start_pilot(
        db_session,
        graph,
        d10_settings,
        first.normalized_phone,
        monkeypatch,
        key="voicemail",
    )
    started = _start_runtime_session(db_session, graph, d10_settings, key="voicemail")
    session = db_session.get(ProspectingDialSession, started.snapshot.session.id)
    leg = db_session.get(ProspectingDialLeg, started.snapshot.current_leg.id)
    attempt = db_session.get(
        ProspectingAttempt,
        started.snapshot.session.current_attempt_id,
    )
    pilot = db_session.get(ProspectingDialerPilot, pilot_read.id)
    assert session is not None
    assert leg is not None
    assert attempt is not None
    assert pilot is not None
    entry = db_session.get(ProspectCallingBatchEntry, attempt.batch_entry_id)
    assert entry is not None
    completed_at = datetime.now(UTC)
    leg.status = "completed"
    leg.connected_at = completed_at - timedelta(seconds=45)
    leg.actual_cost_cents = 5
    leg.completed_at = completed_at
    attempt.status = "completed"
    attempt.outcome = "left_voicemail"
    attempt.contact_made = False
    attempt.answer_classification = "machine"
    attempt.party_classification = "unknown"
    attempt.interest_classification = "not_assessed"
    attempt.follow_up_permission = "not_recorded"
    attempt.completed_at = completed_at
    entry.status = "completed"
    entry.disposition = "left_voicemail"
    _attach_exact_provider_graph(
        db_session,
        graph,
        session,
        leg,
        attempt,
        root_provider_call_id="CA-voicemail",
        child_provider_call_id="CA-voicemail-child",
        completed_at=completed_at,
        duration_seconds=45,
        contact_made=True,
    )
    db_session.flush()

    snapshot = _attempt_snapshot(
        db_session,
        pilot,
        attempt,
        session,
        [leg],
        ProspectingDialerPilotAttemptReviewCreate(
            expected_revision=pilot.revision,
            idempotency_key="review-voicemail",
            recording_reviewed=False,
            provider_cost_verified=True,
            compliance_clear=True,
            reason="Voicemail has no seller conversation to transcribe.",
        ),
        completed_at,
    )
    assert snapshot["recording_review_required"] is False
    assert snapshot["recording_count"] == 0
    assert snapshot["transcript_ids"] == []
    assert snapshot["connected_transcript_and_notes_complete"] is True
    assert _attempt_snapshot_passed(snapshot) is True

    # A signed terminal child proves that Twilio placed the seller leg, but a
    # no-answer result is not an answered smoke call and must never appear in
    # the UI's smoke-evidence selector.
    session.state = "ended"
    session.ended_at = completed_at
    session.lease_token = None
    session.lease_expires_at = None
    session.current_prospect_id = None
    session.current_batch_entry_id = None
    session.current_attempt_id = None
    db_session.flush()
    queue = _attempt_review_queue(db_session, pilot, [])
    queue_item = next(item for item in queue if item.attempt_id == attempt.id)
    assert queue_item.placed_call is True
    assert queue_item.smoke_test_eligible is False
    assert queue_item.provider_call_ids == ["CA-voicemail", "CA-voicemail-child"]


def test_attempt_recording_attestation_requires_recording_access(
    db_session: Session,
    d10_settings: Settings,
    monkeypatch: MonkeyPatch,
) -> None:
    graph, first, _ = _d10_graph(db_session)
    pilot_read = _start_pilot(
        db_session,
        graph,
        d10_settings,
        first.normalized_phone,
        monkeypatch,
        key="recording-auth",
    )
    pilot = db_session.get(ProspectingDialerPilot, pilot_read.id)
    assert pilot is not None
    pilot.status = "running"
    db_session.commit()
    started = _start_runtime_session(
        db_session,
        graph,
        d10_settings,
        key="recording-auth",
    )
    attempt_id = started.snapshot.session.current_attempt_id
    assert attempt_id is not None
    monkeypatch.setattr(
        "app.services.prospecting_dialer_acceptance._attempt_snapshot",
        lambda *args, **kwargs: {"recording_review_required": True},
    )

    with pytest.raises(PermissionError, match="Recording access"):
        review_prospecting_dialer_pilot_attempt(
            db_session,
            _manager_principal(graph),
            pilot.id,
            attempt_id,
            ProspectingDialerPilotAttemptReviewCreate(
                expected_revision=pilot.revision,
                idempotency_key="recording-auth-review",
                recording_reviewed=True,
                provider_cost_verified=True,
                compliance_clear=True,
                reason="Manager cannot attest to audio they cannot access.",
            ),
            settings=d10_settings,
        )


def test_provider_started_technical_failure_is_reviewable_without_fake_contact() -> None:
    completed_at = datetime.now(UTC)
    attempt = SimpleNamespace(
        outcome="technical_failure",
        status="cancelled",
        completed_at=completed_at,
        contact_made=False,
        answer_classification="unknown",
        party_classification="unknown",
        interest_classification="not_assessed",
        follow_up_permission="not_recorded",
    )
    leg = SimpleNamespace(
        status="failed",
        completed_at=completed_at,
        answered_at=None,
        connected_at=None,
    )
    evidence = _contact_disposition_evidence(attempt, leg, None)
    assert evidence == {
        "classification": "technical_failure",
        "provider_connection": False,
        "right_party_contact": False,
        "reconciled": True,
    }
    attempt.interest_classification = "interested"
    assert _contact_disposition_evidence(attempt, leg, None)["reconciled"] is False


def test_final_integrity_ignores_calls_queued_after_submission_cutoff(
    db_session: Session,
    d10_settings: Settings,
    monkeypatch: MonkeyPatch,
) -> None:
    graph, first, _ = _d10_graph(db_session)
    pilot_read = _start_pilot(
        db_session,
        graph,
        d10_settings,
        first.normalized_phone,
        monkeypatch,
        key="submit-cutoff",
    )
    started = _start_runtime_session(db_session, graph, d10_settings, key="submit-cutoff")
    leg = db_session.get(ProspectingDialLeg, started.snapshot.current_leg.id)
    pilot = db_session.get(ProspectingDialerPilot, pilot_read.id)
    assert leg is not None
    assert pilot is not None
    submitted_at = datetime.now(UTC)
    pilot.submitted_at = submitted_at
    leg.provider_call_id = "CA-post-submit"
    leg.actual_cost_cents = None
    leg.queued_at = submitted_at + timedelta(seconds=1)
    db_session.flush()

    costs_complete, caps_clear = _global_pilot_call_integrity(db_session, pilot)
    assert costs_complete is True
    assert caps_clear is True

    leg.queued_at = submitted_at - timedelta(seconds=1)
    db_session.flush()
    costs_complete, _ = _global_pilot_call_integrity(db_session, pilot)
    assert costs_complete is False


def test_final_integrity_detects_duplicate_normalized_recipient(
    db_session: Session,
    d10_settings: Settings,
    monkeypatch: MonkeyPatch,
) -> None:
    graph, first, second = _d10_graph(db_session)
    pilot_read = _start_pilot(
        db_session,
        graph,
        d10_settings,
        first.normalized_phone,
        monkeypatch,
        key="duplicate-phone",
    )
    pilot = db_session.get(ProspectingDialerPilot, pilot_read.id)
    assert pilot is not None
    pilot.status = "running"
    db_session.commit()

    first_session = _start_runtime_session(db_session, graph, d10_settings, key="duplicate-one")
    first_leg = db_session.get(ProspectingDialLeg, first_session.snapshot.current_leg.id)
    first_session_row = db_session.get(
        ProspectingDialSession,
        first_session.snapshot.session.id,
    )
    assert first_leg is not None
    assert first_session_row is not None
    first_attempt = db_session.get(
        ProspectingAttempt,
        first_session.snapshot.session.current_attempt_id,
    )
    assert first_attempt is not None
    first_entry = db_session.get(ProspectCallingBatchEntry, first_attempt.batch_entry_id)
    assert first_entry is not None
    # Keep both signed provider events inside the integrity capture window.  The
    # second leg is intentionally one second later, so anchor the pair in the
    # recent past instead of manufacturing a future provider event.
    completed_at = datetime.now(UTC) - timedelta(seconds=2)
    first_leg.status = "no_answer"
    first_leg.completed_at = completed_at
    first_attempt.status = "completed"
    first_attempt.outcome = "no_answer"
    first_attempt.contact_made = False
    first_attempt.completed_at = completed_at
    first_entry.status = "completed"
    first_entry.disposition = "no_answer"
    _attach_exact_provider_graph(
        db_session,
        graph,
        first_session_row,
        first_leg,
        first_attempt,
        root_provider_call_id="CA-duplicate-one",
        child_provider_call_id="CA-duplicate-one-child",
        completed_at=completed_at,
    )
    _set_exact_provider_costs(
        first_leg,
        ["CA-duplicate-one", "CA-duplicate-one-child"],
    )
    first_session_row.state = "ended"
    first_session_row.ended_at = completed_at
    first_session_row.lease_token = None
    first_session_row.lease_expires_at = None
    first_session_row.current_prospect_id = None
    first_session_row.current_batch_entry_id = None
    first_session_row.current_attempt_id = None
    db_session.commit()

    second_runtime = _start_runtime_session(
        db_session,
        graph,
        d10_settings,
        key="duplicate-two",
    )
    second_session = db_session.get(
        ProspectingDialSession,
        second_runtime.snapshot.session.id,
    )
    second_leg = db_session.get(
        ProspectingDialLeg,
        second_runtime.snapshot.current_leg.id,
    )
    second_attempt = db_session.get(
        ProspectingAttempt,
        second_runtime.snapshot.session.current_attempt_id,
    )
    assert second_session is not None
    assert second_leg is not None
    assert second_attempt is not None
    assert second_leg.prospect_id == second.id
    second_entry = db_session.get(ProspectCallingBatchEntry, second_attempt.batch_entry_id)
    assert second_entry is not None
    second_completed_at = completed_at + timedelta(seconds=1)
    second_leg.recipient = first_leg.recipient.removeprefix("+")
    second_leg.status = "no_answer"
    second_leg.completed_at = second_completed_at
    second_attempt.status = "completed"
    second_attempt.outcome = "no_answer"
    second_attempt.contact_made = False
    second_attempt.completed_at = second_completed_at
    second_entry.status = "completed"
    second_entry.disposition = "no_answer"
    _attach_exact_provider_graph(
        db_session,
        graph,
        second_session,
        second_leg,
        second_attempt,
        root_provider_call_id="CA-duplicate-two",
        child_provider_call_id="CA-duplicate-two-child",
        completed_at=second_completed_at,
    )
    _set_exact_provider_costs(
        second_leg,
        ["CA-duplicate-two", "CA-duplicate-two-child"],
    )
    second_session.state = "ended"
    second_session.ended_at = second_completed_at
    second_session.lease_token = None
    second_session.lease_expires_at = None
    second_session.current_prospect_id = None
    second_session.current_batch_entry_id = None
    second_session.current_attempt_id = None
    db_session.flush()

    costs_complete, caps_and_duplicates_clear = _global_pilot_call_integrity(
        db_session,
        pilot,
    )
    assert costs_complete is True
    assert caps_and_duplicates_clear is False


def test_owner_revocation_is_rbac_revision_phrase_and_idempotency_guarded(
    db_session: Session,
    d10_settings: Settings,
) -> None:
    graph, _, _ = _d10_graph(db_session)
    pilot = _accepted_pilot(db_session, graph, d10_settings)
    payload = ProspectingDialerPilotRevoke(
        expected_revision=pilot.revision,
        idempotency_key="owner-revoke",
        confirmation_phrase=PILOT_REVOKE_PHRASE,
        reason="Emergency owner revocation of the exact accepted scope.",
    )

    with pytest.raises(PermissionError, match="Only an owner"):
        revoke_prospecting_dialer_pilot(
            db_session,
            _non_owner_manager_principal(graph),
            pilot.id,
            payload,
            settings=d10_settings,
        )
    with pytest.raises(ProspectingDialerAcceptanceConflictError, match="Stale pilot revision"):
        revoke_prospecting_dialer_pilot(
            db_session,
            _owner_principal(graph),
            pilot.id,
            payload.model_copy(update={"expected_revision": pilot.revision - 1}),
            settings=d10_settings,
        )
    with pytest.raises(ValueError, match="Type exactly"):
        revoke_prospecting_dialer_pilot(
            db_session,
            _owner_principal(graph),
            pilot.id,
            payload.model_copy(update={"confirmation_phrase": "REVOKE"}),
            settings=d10_settings,
        )

    revoked = revoke_prospecting_dialer_pilot(
        db_session,
        _owner_principal(graph),
        pilot.id,
        payload,
        settings=d10_settings,
    )
    assert revoked is not None
    assert revoked.pilot is not None
    assert revoked.pilot.status == "revoked"
    assert revoked.pilot.revoked_at is not None
    assert revoked.pilot.revocation_reason == payload.reason
    campaign = db_session.get(Campaign, graph.campaign.id)
    assert campaign is not None
    assert campaign.prospecting_dialer_enabled is False

    replay = revoke_prospecting_dialer_pilot(
        db_session,
        _owner_principal(graph),
        pilot.id,
        payload,
        settings=d10_settings,
    )
    assert replay is not None
    assert replay.pilot is not None
    assert replay.pilot.revision == revoked.pilot.revision


def test_owner_revocation_disables_scope_and_safely_drains_active_provider_call(
    db_session: Session,
    d10_settings: Settings,
) -> None:
    graph, _, _ = _d10_graph(db_session)
    pilot = _accepted_pilot(db_session, graph, d10_settings)
    started = _start_runtime_session(
        db_session,
        graph,
        d10_settings,
        key="emergency-revoke-drain",
    )
    session = db_session.get(ProspectingDialSession, started.snapshot.session.id)
    leg = db_session.get(ProspectingDialLeg, started.snapshot.current_leg.id)
    assert session is not None
    assert leg is not None
    leg.provider_call_id = "CA-emergency-revoke-drain"
    leg.status = "ringing"
    session.state = "ringing"
    db_session.commit()

    revoked = revoke_prospecting_dialer_pilot(
        db_session,
        _owner_principal(graph),
        pilot.id,
        ProspectingDialerPilotRevoke(
            expected_revision=pilot.revision,
            idempotency_key="emergency-revoke-with-live-call",
            confirmation_phrase=PILOT_REVOKE_PHRASE,
            reason="Disable authorization immediately and drain the live provider call.",
        ),
        settings=d10_settings,
    )
    assert revoked is not None
    assert revoked.pilot is not None
    assert revoked.pilot.status == "revoked"
    db_session.refresh(session)
    db_session.refresh(leg)
    assert session.ended_at is None
    assert session.session_metadata["authorization_revoked"] is True
    assert session.session_metadata["stop_after_current"] is True
    assert leg.status == "ringing"
    assert leg.completed_at is None
    campaign = db_session.get(Campaign, graph.campaign.id)
    assert campaign is not None
    assert campaign.prospecting_dialer_enabled is False

    runtime_graph = load_runtime_graph(
        db_session,
        graph.principal,
        campaign_id=graph.campaign.id,
        cohort_id=graph.cohort.id,
        batch_id=graph.batch.id,
    )
    assert runtime_graph is not None
    assert matching_active_pilot(db_session, runtime_graph, d10_settings) is None


def test_owner_revocation_cancels_browser_prepared_call_without_draining(
    db_session: Session,
    d10_settings: Settings,
) -> None:
    graph, _, _ = _d10_graph(db_session)
    pilot = _accepted_pilot(db_session, graph, d10_settings)
    started = _start_runtime_session(
        db_session,
        graph,
        d10_settings,
        key="prepared-revoke",
    )
    session = db_session.get(ProspectingDialSession, started.snapshot.session.id)
    leg = db_session.get(ProspectingDialLeg, started.snapshot.current_leg.id)
    attempt = db_session.get(
        ProspectingAttempt,
        started.snapshot.session.current_attempt_id,
    )
    assert session is not None
    assert leg is not None
    assert attempt is not None
    line = db_session.get(VoiceLine, leg.voice_line_id)
    assert line is not None
    now = datetime.now(UTC)
    intent = VoiceCallIntent(
        organization_id=graph.organization.id,
        conversation_id=None,
        lead_id=None,
        contact_id=None,
        prospect_id=leg.prospect_id,
        prospecting_attempt_id=attempt.id,
        prospecting_dial_leg_id=leg.id,
        actor_user_id=graph.caller.id,
        voice_line_id=leg.voice_line_id,
        idempotency_key="prepared-revoke-intent",
        recipient=leg.recipient,
        status="pending",
        recording_consent_status="not_required",
        expires_at=now + timedelta(minutes=5),
        consumed_at=None,
        provider_call_id=None,
        intent_metadata={
            "source": "native_prospecting_dialer",
            "connection_mode": "browser_softphone",
            "provider_start_state": "prepared",
        },
    )
    db_session.add(intent)
    db_session.flush()
    call = CallRecord(
        organization_id=graph.organization.id,
        conversation_id=None,
        lead_id=None,
        contact_id=None,
        prospect_id=leg.prospect_id,
        prospecting_attempt_id=attempt.id,
        prospecting_dial_leg_id=leg.id,
        prospecting_inbound_callback_id=None,
        actor_user_id=graph.caller.id,
        communication_record_id=None,
        voice_line_id=leg.voice_line_id,
        call_intent_id=intent.id,
        provider="twilio",
        provider_call_id=None,
        child_provider_call_id=None,
        direction="outbound",
        status="queued",
        from_number=line.phone_number,
        to_number=leg.recipient,
        started_at=now,
        answered_at=None,
        ended_at=None,
        duration_seconds=None,
        disposition=None,
        recording_consent_status="not_required",
        call_metadata={"source": "native_prospecting_dialer"},
    )
    db_session.add(call)
    db_session.flush()
    leg.call_record_id = call.id
    attempt.call_record_id = call.id
    attempt.provider = "twilio"
    db_session.commit()

    revoked = revoke_prospecting_dialer_pilot(
        db_session,
        _owner_principal(graph),
        pilot.id,
        ProspectingDialerPilotRevoke(
            expected_revision=pilot.revision,
            idempotency_key="prepared-revoke-owner",
            confirmation_phrase=PILOT_REVOKE_PHRASE,
            reason="Cancel the exact local prepared call before revoking authorization.",
        ),
        settings=d10_settings,
        now=now,
    )
    assert revoked is not None
    db_session.refresh(session)
    db_session.refresh(leg)
    db_session.refresh(attempt)
    db_session.refresh(intent)
    db_session.refresh(call)
    assert session.state == "stopped"
    assert session.ended_at is not None
    assert session.ended_at.replace(tzinfo=UTC) == now
    assert leg.status == "cancelled"
    assert leg.provider_call_id is None
    assert attempt.status == "cancelled"
    assert attempt.outcome == "technical_failure"
    assert intent.status == "cancelled"
    assert call.status == "cancelled"
    assert intent.intent_metadata["browser_pre_provider_terminal_reason"] == (
        "d10_pilot_revocation"
    )


def test_recording_evidence_requires_exact_signed_canonical_call_graph(
    db_session: Session,
    api_db_override: None,
) -> None:
    client = TestClient(app)
    evidence = seed_eligible_recording(db_session, client)
    graph = evidence.cold_call
    now = datetime.now(UTC)
    evidence.recording.retention_expires_at = now + timedelta(days=180)
    pilot = ProspectingDialerPilot(
        organization_id=graph.organization.id,
        caller_user_id=graph.caller.id,
        campaign_id=graph.prospect.campaign_id,
        cohort_id=uuid4(),
        prospect_calling_batch_id=graph.batch.id,
        voice_line_id=graph.line.id,
        status="running",
        revision=2,
        effective_line_count=1,
        timezone="UTC",
        required_clean_shift_count=3,
        minimum_attempts_per_shift=25,
        minimum_productive_minutes_per_shift=60,
        minimum_total_attempts=75,
        minimum_batch_size=75,
        maximum_batch_size=250,
        daily_dial_limit=50,
        daily_spend_limit_cents=1000,
        configuration_fingerprint="f" * 64,
        start_attestation={},
        smoke_test_evidence={},
        kill_switch_evidence={},
        batchdialer_comparison_evidence={},
        rollback_evidence={},
        final_evidence_snapshot={},
        created_by_user_id=graph.owner.id,
        updated_by_user_id=graph.owner.id,
        started_by_user_id=graph.owner.id,
        started_at=now - timedelta(minutes=5),
    )
    db_session.flush()

    intent = VoiceCallIntent(
        organization_id=graph.organization.id,
        conversation_id=None,
        lead_id=None,
        contact_id=None,
        prospect_id=graph.prospect.id,
        prospecting_attempt_id=graph.attempt.id,
        prospecting_dial_leg_id=graph.leg.id,
        actor_user_id=graph.caller.id,
        voice_line_id=graph.line.id,
        idempotency_key="recording-acceptance-intent",
        recipient=graph.leg.recipient,
        status="started",
        recording_consent_status="disclosed",
        expires_at=now + timedelta(minutes=5),
        consumed_at=now,
        provider_call_id=evidence.call.provider_call_id,
        intent_metadata={"provider_start_state": "started"},
    )
    db_session.add(intent)
    db_session.flush()
    evidence.call.call_intent_id = intent.id
    signed_event = db_session.scalar(
        select(ProspectingProviderEvent).where(
            ProspectingProviderEvent.provider_recording_id
            == evidence.recording.provider_recording_id
        )
    )
    assert signed_event is not None
    signed_event.payload = {
        **(signed_event.payload or {}),
        "CallSid": evidence.call.provider_call_id,
    }
    db_session.flush()

    assert _recording_matches_pilot_leg(
        db_session,
        pilot,
        evidence.recording,
        graph.leg,
        captured_at=now,
    )
    identity = _recording_identity_snapshot(
        db_session,
        pilot,
        [evidence.recording],
        {evidence.recording.call_record_id: graph.leg},
        captured_at=now,
    )
    assert len(identity) == 1
    assert identity[0]["provider_recording_id"] == evidence.recording.provider_recording_id
    assert identity[0]["signed_event_ids"]
    assert identity[0]["signed_event_payload_hashes"] == ["b" * 64]

    signed_event.signature_verified = False
    db_session.flush()
    assert not _recording_matches_pilot_leg(
        db_session,
        pilot,
        evidence.recording,
        graph.leg,
        captured_at=now,
    )

    signed_event.signature_verified = True
    graph.attempt.provider_call_id = "CA-conflicting-provider-identity"
    db_session.flush()
    assert not _recording_matches_pilot_leg(
        db_session,
        pilot,
        evidence.recording,
        graph.leg,
        captured_at=now,
    )


def test_shift_review_uses_explicit_local_date_when_session_crosses_midnight(
    db_session: Session,
    d10_settings: Settings,
    monkeypatch: MonkeyPatch,
) -> None:
    graph, first, second = _d10_graph(db_session)
    pilot_read = _start_pilot(
        db_session,
        graph,
        d10_settings,
        first.normalized_phone,
        monkeypatch,
        key="cross-midnight-shift",
    )
    pilot = db_session.get(ProspectingDialerPilot, pilot_read.id)
    assert pilot is not None
    pilot.status = "running"
    db_session.commit()

    started = _start_runtime_session(
        db_session,
        graph,
        d10_settings,
        key="cross-midnight-shift",
    )
    session = db_session.get(ProspectingDialSession, started.snapshot.session.id)
    leg = db_session.get(ProspectingDialLeg, started.snapshot.current_leg.id)
    attempt = db_session.get(
        ProspectingAttempt,
        started.snapshot.session.current_attempt_id,
    )
    assert session is not None
    assert leg is not None
    assert attempt is not None
    entry = db_session.get(ProspectCallingBatchEntry, attempt.batch_entry_id)
    assert entry is not None

    # The shift opens at 11:50 PM Eastern, but this exact attempt is queued
    # after midnight and therefore belongs to the next local operating date.
    session.started_at = datetime(2026, 8, 20, 3, 50, tzinfo=UTC)
    leg.queued_at = datetime(2026, 8, 20, 4, 10, tzinfo=UTC)
    leg.completed_at = datetime(2026, 8, 20, 4, 12, tzinfo=UTC)
    leg.status = "completed"
    leg.connected_at = leg.completed_at - timedelta(seconds=30)
    leg.actual_cost_cents = 5
    attempt.status = "completed"
    attempt.outcome = "left_voicemail"
    attempt.contact_made = False
    attempt.answer_classification = "machine"
    attempt.party_classification = "unknown"
    attempt.interest_classification = "not_assessed"
    attempt.follow_up_permission = "not_recorded"
    attempt.completed_at = leg.completed_at
    entry.status = "completed"
    entry.disposition = "left_voicemail"
    _attach_exact_provider_graph(
        db_session,
        graph,
        session,
        leg,
        attempt,
        root_provider_call_id="CA-cross-midnight",
        child_provider_call_id="CA-cross-midnight-child",
        completed_at=leg.completed_at,
        duration_seconds=30,
        contact_made=True,
    )
    session.state = "ended"
    session.ended_at = datetime(2026, 8, 20, 5, 15, tzinfo=UTC)
    session.lease_token = None
    session.lease_expires_at = None
    session.current_prospect_id = None
    session.current_batch_entry_id = None
    session.current_attempt_id = None
    released_leg = ProspectingDialLeg(
        organization_id=graph.organization.id,
        dial_session_id=session.id,
        prospect_id=second.id,
        batch_entry_id=graph.entries[1].id,
        attempt_id=None,
        contact_point_id=None,
        voice_line_id=session.voice_line_id,
        call_record_id=None,
        line_slot=1,
        recipient=second.normalized_phone,
        provider="twilio",
        provider_call_id=None,
        provider_recording_id=None,
        idempotency_key="released-cross-midnight-reservation",
        status="cancelled",
        last_provider_event_sequence=0,
        last_provider_event_at=None,
        reserved_cost_cents=5,
        actual_cost_cents=None,
        queued_at=datetime(2026, 8, 20, 4, 20, tzinfo=UTC),
        completed_at=datetime(2026, 8, 20, 4, 21, tzinfo=UTC),
        answer_classification="unknown",
        party_classification="unknown",
        terminal_result="released_before_provider_start",
        leg_metadata={"reservation_released": True},
    )
    db_session.add(released_leg)
    db_session.commit()

    correct_payload = ProspectingDialerPilotShiftReviewCreate(
        expected_revision=pilot.revision,
        idempotency_key="cross-midnight-correct-day",
        shift_date=date(2026, 8, 20),
        no_duplicate_calls=True,
        no_lost_answers=True,
        no_stuck_sessions=True,
        provider_billing_verified=True,
        kill_switches_verified=True,
        compliance_clear=True,
        billing_evidence_reference="Twilio usage row CA-cross-midnight",
        provider_cost_items=[
            ProspectingDialerPilotProviderCostItem(
                provider_call_id="CA-cross-midnight",
                actual_cost_cents=5,
                provider_reference="Twilio usage row CA-cross-midnight",
            )
        ],
        reason="Verify the explicit local date across midnight.",
    )
    snapshot = _shift_snapshot(
        db_session,
        pilot,
        session,
        correct_payload,
        datetime(2026, 8, 20, 6, 0, tzinfo=UTC),
    )
    assert snapshot["shift_date"] == "2026-08-20"
    assert snapshot["dial_session_ids"] == [str(session.id)]
    assert snapshot["dial_leg_ids"] == [str(leg.id)]
    assert str(released_leg.id) not in snapshot["dial_leg_ids"]
    assert snapshot["productive_minutes"] == 0
    assert snapshot["no_lost_answers"] is True

    wrong_payload = correct_payload.model_copy(
        update={
            "idempotency_key": "cross-midnight-wrong-day",
            "shift_date": date(2026, 8, 19),
        }
    )
    with pytest.raises(ValueError, match="no exact pilot call"):
        review_prospecting_dialer_pilot_shift(
            db_session,
            _manager_principal(graph),
            pilot.id,
            session.id,
            wrong_payload,
            settings=d10_settings,
            now=datetime(2026, 8, 20, 6, 0, tzinfo=UTC),
        )

    # The representative session is an audit anchor, not the review's unique
    # identity. A genuine cross-midnight session can anchor separate dates.
    for review_date in (date(2026, 8, 18), date(2026, 8, 19)):
        db_session.add(
            ProspectingDialerPilotShiftReview(
                organization_id=pilot.organization_id,
                pilot_id=pilot.id,
                dial_session_id=session.id,
                shift_date=review_date,
                timezone=pilot.timezone,
                status="pending",
                evidence_snapshot={},
                evidence_hash="0" * 64,
            )
        )
    db_session.flush()
