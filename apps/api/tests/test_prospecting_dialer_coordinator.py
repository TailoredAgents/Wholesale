from collections.abc import Callable, Iterator
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from pytest import MonkeyPatch
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.auth import Principal
from app.core.config import Settings, get_settings
from app.domain.rbac import PermissionKeys
from app.models.foundation import (
    Appointment,
    Campaign,
    ContactMethod,
    Lead,
    Market,
    Organization,
    Prospect,
    ProspectCallingBatch,
    ProspectCallingBatchEntry,
    ProspectContactPoint,
    ProspectHandoff,
    ProspectingAttempt,
    ProspectingCohort,
    ProspectingDialerProfile,
    ProspectingDialLeg,
    ProspectingDialSession,
    ProspectingScriptVersion,
    SuppressionRecord,
    User,
    VoiceLine,
)
from app.schemas.prospecting import (
    ProspectingAttemptComplete,
    ProspectingDialSessionEndCommand,
    ProspectingDialSessionLeaseCommand,
    ProspectingDialSessionRecoveryCommand,
    ProspectingDialSessionStart,
    ProspectingQualificationAutosaveRequest,
    ProspectingTechnicalFailureComplete,
)
from app.services.bootstrap import bootstrap_foundation
from app.services.prospecting import (
    ProspectingCompletionConflictError,
    autosave_attempt_qualification,
    complete_attempt,
    complete_technical_failure,
)
from app.services.prospecting_dialer import (
    ProspectingDialerConfigurationError,
    ProspectingDialerConflictError,
    as_utc,
    end_dial_session,
    load_runtime_graph,
    pause_dial_session,
    process_next_prospecting_dialer_recovery,
    record_dial_provider_event,
    recover_dial_session,
    reserve_next_dial_record,
    resume_dial_session,
    runtime_policy_blockers,
    select_ranked_phone,
    start_dial_session,
    validate_reserved_dial_leg_policy,
)


@dataclass(frozen=True)
class CoordinatorGraph:
    organization: Organization
    owner: User
    caller: User
    principal: Principal
    campaign: Campaign
    cohort: ProspectingCohort
    batch: ProspectCallingBatch
    entries: tuple[ProspectCallingBatchEntry, ...]


@pytest.fixture
def settings_factory(
    monkeypatch: MonkeyPatch,
) -> Iterator[Callable[..., Settings]]:
    def build(*, enabled: bool = True) -> Settings:
        values = {
            "PROSPECTING_NATIVE_DIALER_ENABLED": "true" if enabled else "false",
            "PROSPECTING_NATIVE_DIALER_MAX_LINES": "3",
            "PROSPECTING_NATIVE_DIALER_LEASE_SECONDS": "90",
            "PROSPECTING_NATIVE_DIALER_STALE_AFTER_SECONDS": "60",
            "PROSPECTING_NATIVE_DIALER_ORPHAN_GRACE_SECONDS": "60",
            "PROSPECTING_NATIVE_DIALER_RESERVED_COST_CENTS": "5",
            "TWILIO_VOICE_ENABLED": "true",
            "TWILIO_ACCOUNT_SID": "AC00000000000000000000000000000000",
            "TWILIO_AUTH_TOKEN": "coordinator-test-auth-token",
            "TWILIO_WEBHOOK_BASE_URL": "https://api.stonegate.test",
            "TWILIO_VALIDATE_WEBHOOK_SIGNATURES": "true",
        }
        for key, value in values.items():
            monkeypatch.setenv(key, value)
        get_settings.cache_clear()
        return get_settings()

    yield build
    get_settings.cache_clear()


def seed_coordinator_graph(db: Session, *, record_count: int = 3) -> CoordinatorGraph:
    foundation = bootstrap_foundation(
        db,
        organization_name="D3 Coordinator Workspace",
        admin_email="d3-coordinator-owner@example.com",
        admin_name="D3 Coordinator Owner",
    )
    assert foundation.admin_user is not None
    organization = foundation.organization
    organization.prospecting_dialer_enabled = True
    organization.prospecting_dialer_max_concurrent_legs = 3
    # D3 coordinator tests isolate lease, reservation, and recovery behavior.
    # D10 acceptance enforcement has its own fail-closed contract suite.
    organization.prospecting_dialer_acceptance_required = False
    caller = User(
        organization_id=organization.id,
        email="d3-coordinator-caller@example.com",
        display_name="D3 Coordinator Caller",
        is_active=True,
        calling_enabled=True,
    )
    market = Market(
        organization_id=organization.id,
        name="D3 Atlanta",
        code="d3-atlanta",
        state_code="GA",
        timezone="UTC",
        status="active",
        is_primary=True,
    )
    db.add_all([caller, market])
    db.flush()
    campaign = Campaign(
        organization_id=organization.id,
        market_id=market.id,
        owner_user_id=foundation.admin_user.id,
        name="D3 Controlled Calling",
        code="d3-controlled-calling",
        channel="cold_call",
        asset_class="house",
        status="active",
        prospecting_dialer_enabled=True,
        prospecting_dialer_max_concurrent_legs=3,
    )
    line = VoiceLine(
        organization_id=organization.id,
        assigned_user_id=caller.id,
        provider="twilio",
        phone_number="+16785550111",
        label="D3 prospecting outbound",
        department_key="acquisitions",
        purpose_key="prospecting_outbound",
        status="active",
        is_default=False,
        inbound_route="conversation_owner",
        ring_strategy="simultaneous",
        coverage_timezone="UTC",
        coverage_start_hour=0,
        coverage_end_hour=24,
        prospecting_dialer_max_concurrent_legs=3,
        missed_call_action="fallback_then_voicemail",
        line_metadata={},
    )
    script = ProspectingScriptVersion(
        organization_id=organization.id,
        asset_class="house",
        version_number=1,
        title="D3 Coordinator Script",
        status="approved",
        opening_script="Hello, I am calling about your property.",
        qualification_questions=[],
        disposition_rules={},
        created_by_user_id=foundation.admin_user.id,
        approved_by_user_id=foundation.admin_user.id,
        approved_at=datetime.now(UTC),
    )
    db.add_all([campaign, line, script])
    db.flush()
    now = datetime.now(UTC)
    cohort = ProspectingCohort(
        organization_id=organization.id,
        campaign_id=campaign.id,
        script_version_id=script.id,
        created_by_user_id=foundation.admin_user.id,
        name="D3 Coordinator Cohort",
        code="d3-coordinator-cohort",
        status="active",
        source_name="D3 test data",
        list_type="distressed_homeowners",
        market_label="Atlanta",
        dialer_mode="one_line_power",
        call_window_start_hour=0,
        call_window_end_hour=24,
        timezone="UTC",
        starts_on=now.date() - timedelta(days=1),
        ends_on=now.date() + timedelta(days=1),
        cohort_metadata={},
    )
    profile = ProspectingDialerProfile(
        organization_id=organization.id,
        user_id=caller.id,
        voice_line_id=line.id,
        status="active",
        default_line_count=3,
        max_line_count=3,
        recording_policy="company_policy",
        daily_dial_limit=500,
        daily_spend_limit_cents=10_000,
        profile_metadata={},
        created_by_user_id=foundation.admin_user.id,
        updated_by_user_id=foundation.admin_user.id,
    )
    db.add_all([cohort, profile])
    db.flush()
    batch = ProspectCallingBatch(
        organization_id=organization.id,
        campaign_id=campaign.id,
        cohort_id=cohort.id,
        assigned_user_id=caller.id,
        created_by_user_id=foundation.admin_user.id,
        name="D3 Coordinator Queue",
        status="active",
        dialer_mode="one_line_power",
    )
    db.add(batch)
    db.flush()
    prospects = tuple(
        Prospect(
            organization_id=organization.id,
            campaign_id=campaign.id,
            assigned_user_id=caller.id,
            source_record_key=f"d3-coordinator-{number}",
            status="ready",
            legal_name=f"D3 Prospect {number}",
            phone=f"+14045551{number:04d}",
            normalized_phone=f"+14045551{number:04d}",
            street_address=f"{number} Coordinator Way",
            city="Atlanta",
            state_code="GA",
            postal_code="30303",
            suppression_status="clear",
            phone_validation_status="verified",
            call_eligibility="eligible",
            source_payload={},
        )
        for number in range(1, record_count + 1)
    )
    db.add_all(prospects)
    db.flush()
    entries = tuple(
        ProspectCallingBatchEntry(
            organization_id=organization.id,
            prospect_calling_batch_id=batch.id,
            prospect_id=prospect.id,
            assigned_user_id=caller.id,
            sequence_number=number,
            status="ready",
            attempt_count=0,
        )
        for number, prospect in enumerate(prospects, start=1)
    )
    db.add_all(entries)
    db.commit()
    principal = Principal(
        user_id=caller.id,
        organization_id=organization.id,
        email=caller.email,
        permission_keys=frozenset({PermissionKeys.WORK_ASSIGNED_CALLING_LISTS}),
    )
    return CoordinatorGraph(
        organization=organization,
        owner=foundation.admin_user,
        caller=caller,
        principal=principal,
        campaign=campaign,
        cohort=cohort,
        batch=batch,
        entries=entries,
    )


def session_start(
    graph: CoordinatorGraph,
    *,
    suffix: str = "primary",
) -> ProspectingDialSessionStart:
    return ProspectingDialSessionStart(
        campaign_id=graph.campaign.id,
        cohort_id=graph.cohort.id,
        calling_batch_id=graph.batch.id,
        browser_session_id=f"browser-{suffix}",
        idempotency_key=f"session-{suffix}",
        requested_line_count=3,
    )


def lease_command(
    start: ProspectingDialSessionStart,
    lease_token: str,
) -> ProspectingDialSessionLeaseCommand:
    return ProspectingDialSessionLeaseCommand(
        browser_session_id=start.browser_session_id,
        lease_token=lease_token,
    )


def terminalize_test_leg(
    db: Session,
    graph: CoordinatorGraph,
    leg: ProspectingDialLeg,
    *,
    key: str,
    final_status: str,
    connected: bool = False,
) -> None:
    now = datetime.now(UTC)
    if connected:
        record_dial_provider_event(
            db,
            organization_id=graph.organization.id,
            provider="twilio",
            external_event_id=f"{key}-connected",
            event_type="call.connected",
            payload={"CallStatus": "in-progress"},
            dial_leg=leg,
            target_status="connected",
            occurred_at=now + timedelta(seconds=1),
            signature_verified=True,
            signature="verified-test-signature",
        )
    record_dial_provider_event(
        db,
        organization_id=graph.organization.id,
        provider="twilio",
        external_event_id=f"{key}-{final_status}",
        event_type=f"call.{final_status}",
        payload={"CallStatus": final_status.replace("_", "-")},
        dial_leg=leg,
        target_status=final_status,
        occurred_at=now + timedelta(seconds=2 if connected else 1),
        signature_verified=True,
        signature="verified-test-signature",
    )
    db.commit()


def test_native_qualification_autosave_requires_current_live_lease(
    db_session: Session,
    settings_factory: Callable[..., Settings],
) -> None:
    graph = seed_coordinator_graph(db_session)
    settings = settings_factory()
    script = db_session.scalar(
        select(ProspectingScriptVersion).where(
            ProspectingScriptVersion.organization_id == graph.organization.id
        )
    )
    assert script is not None
    script.qualification_questions = [
        {
            "key": "motivation",
            "label": "Motivation",
            "prompt": "Why are you considering selling?",
            "answer_type": "text",
            "choices": [],
            "required_for_handoff": True,
        }
    ]
    db_session.commit()
    now = datetime.now(UTC)
    start_payload = session_start(graph, suffix="qualification")
    started = start_dial_session(
        db_session,
        graph.principal,
        start_payload,
        settings=settings,
        now=now,
    )
    assert started is not None
    assert started.lease_token is not None
    attempt_id = started.snapshot.session.current_attempt_id
    assert attempt_id is not None
    base_payload = {
        "state": "answered",
        "answer_value": "Inherited property",
        "expected_revision": 0,
        "mutation_id": "ca12d33d-887f-481d-b37f-0d9dbf300f45",
    }
    with pytest.raises(ProspectingDialerConflictError, match="active dialer lease"):
        autosave_attempt_qualification(
            db_session,
            graph.principal,
            attempt_id,
            "motivation",
            ProspectingQualificationAutosaveRequest(**base_payload),
        )
    db_session.rollback()
    with pytest.raises(ProspectingDialerConflictError, match="browser session"):
        autosave_attempt_qualification(
            db_session,
            graph.principal,
            attempt_id,
            "motivation",
            ProspectingQualificationAutosaveRequest(
                **base_payload,
                browser_session_id="browser-stale-qualification",
                lease_token=started.lease_token,
            ),
        )
    db_session.rollback()
    saved = autosave_attempt_qualification(
        db_session,
        graph.principal,
        attempt_id,
        "motivation",
        ProspectingQualificationAutosaveRequest(
            **base_payload,
            browser_session_id=start_payload.browser_session_id,
            lease_token=started.lease_token,
        ),
    )
    assert saved is not None
    assert saved.state == "answered"
    assert saved.revision == 1

    session = db_session.get(ProspectingDialSession, started.snapshot.session.id)
    assert session is not None
    session.lease_expires_at = datetime.now(UTC) - timedelta(seconds=1)
    db_session.commit()
    with pytest.raises(ProspectingDialerConflictError, match="lease expired"):
        autosave_attempt_qualification(
            db_session,
            graph.principal,
            attempt_id,
            "motivation",
            ProspectingQualificationAutosaveRequest(
                state="needs_follow_up",
                answer_value="Seller deferred",
                expected_revision=1,
                mutation_id="4ad9dd18-279f-4cf5-ae88-03b7de4516d8",
                browser_session_id=start_payload.browser_session_id,
                lease_token=started.lease_token,
            ),
        )
    db_session.rollback()


def test_native_warm_completion_requires_persisted_qualification_rows(
    db_session: Session,
    settings_factory: Callable[..., Settings],
) -> None:
    graph = seed_coordinator_graph(db_session)
    settings = settings_factory()
    script = db_session.scalar(
        select(ProspectingScriptVersion).where(
            ProspectingScriptVersion.organization_id == graph.organization.id
        )
    )
    assert script is not None
    script.qualification_questions = [
        {
            "key": "motivation",
            "label": "Motivation",
            "prompt": "Why are you considering selling?",
            "answer_type": "text",
            "choices": [],
            "required_for_handoff": True,
        }
    ]
    db_session.commit()
    now = datetime.now(UTC)
    start_payload = session_start(graph, suffix="persisted-warm")
    started = start_dial_session(
        db_session,
        graph.principal,
        start_payload,
        settings=settings,
        now=now,
    )
    assert started is not None
    assert started.lease_token is not None
    assert started.snapshot.current_leg is not None
    attempt_id = started.snapshot.session.current_attempt_id
    assert attempt_id is not None
    leg = db_session.get(ProspectingDialLeg, started.snapshot.current_leg.id)
    assert leg is not None
    record_dial_provider_event(
        db_session,
        organization_id=graph.organization.id,
        provider="twilio",
        external_event_id="d5-persisted-warm-connected",
        event_type="call.connected",
        payload={"CallStatus": "in-progress"},
        dial_leg=leg,
        target_status="connected",
        occurred_at=now + timedelta(seconds=1),
        signature_verified=True,
        signature="verified-test-signature",
    )
    record_dial_provider_event(
        db_session,
        organization_id=graph.organization.id,
        provider="twilio",
        external_event_id="d5-persisted-warm-terminal",
        event_type="call.completed",
        payload={"CallStatus": "completed"},
        dial_leg=leg,
        target_status="completed",
        occurred_at=now + timedelta(seconds=2),
        signature_verified=True,
        signature="verified-test-signature",
    )
    db_session.commit()

    completion = ProspectingAttemptComplete(
        outcome="interested",
        idempotency_key="complete-persisted-warm",
        browser_session_id=start_payload.browser_session_id,
        lease_token=started.lease_token,
        handoff_user_id=graph.owner.id,
        qualification_answers={"motivation": "Unaudited browser-only answer"},
    )
    with pytest.raises(ValueError, match="required warm-handoff"):
        complete_attempt(db_session, graph.principal, attempt_id, completion)
    db_session.rollback()

    saved = autosave_attempt_qualification(
        db_session,
        graph.principal,
        attempt_id,
        "motivation",
        ProspectingQualificationAutosaveRequest(
            state="answered",
            answer_value="Inherited property",
            expected_revision=0,
            mutation_id="00518c02-dfe4-4f03-8bb1-3c05fb4c9579",
            browser_session_id=start_payload.browser_session_id,
            lease_token=started.lease_token,
        ),
    )
    assert saved is not None
    completed = complete_attempt(db_session, graph.principal, attempt_id, completion)
    assert completed is not None
    saved_attempt = next(item for item in completed.attempts if item.id == attempt_id)
    assert saved_attempt.qualification_answers == {"motivation": "Inherited property"}


@pytest.mark.parametrize(
    ("blocker", "message"),
    [
        ("environment", "launch flag"),
        ("company", "company prospecting dialer switch"),
        ("campaign", "campaign prospecting dialer switch"),
    ],
)
def test_session_start_fails_closed_for_each_launch_switch(
    db_session: Session,
    settings_factory: Callable[..., Settings],
    blocker: str,
    message: str,
) -> None:
    graph = seed_coordinator_graph(db_session)
    settings = settings_factory(enabled=blocker != "environment")
    if blocker == "company":
        graph.organization.prospecting_dialer_enabled = False
    elif blocker == "campaign":
        graph.campaign.prospecting_dialer_enabled = False
    db_session.commit()

    with pytest.raises(ProspectingDialerConfigurationError, match=message):
        start_dial_session(
            db_session,
            graph.principal,
            session_start(graph),
            settings=settings,
            now=datetime.now(UTC),
        )

    assert db_session.scalar(select(func.count()).select_from(ProspectingDialSession)) == 0


def test_start_is_idempotent_and_one_line_reservation_is_stable(
    db_session: Session,
    settings_factory: Callable[..., Settings],
) -> None:
    graph = seed_coordinator_graph(db_session)
    settings = settings_factory()
    started_at = datetime.now(UTC)
    payload = session_start(graph)

    started = start_dial_session(
        db_session,
        graph.principal,
        payload,
        settings=settings,
        now=started_at,
    )
    assert started is not None
    assert started.queue_status == "reserved"
    assert started.snapshot.session.requested_line_count == 3
    assert started.snapshot.session.effective_line_count == 1
    assert started.snapshot.current_leg is not None
    assert started.snapshot.current_leg.line_slot == 1
    assert started.lease_token is not None

    replay = start_dial_session(
        db_session,
        graph.principal,
        payload,
        settings=settings,
        now=started_at + timedelta(seconds=1),
    )
    assert replay is not None
    assert replay.replayed is True
    assert replay.snapshot.session.id == started.snapshot.session.id
    assert replay.lease_token == started.lease_token

    stable = reserve_next_dial_record(
        db_session,
        graph.principal,
        started.snapshot.session.id,
        lease_command(payload, started.lease_token),
        settings=settings,
        now=started_at + timedelta(seconds=2),
    )
    assert stable is not None
    assert stable.replayed is True
    assert stable.queue_status == "unchanged"
    assert stable.snapshot.current_leg is not None
    assert stable.snapshot.current_leg.id == started.snapshot.current_leg.id
    assert db_session.scalar(select(func.count()).select_from(ProspectingAttempt)) == 1
    assert db_session.scalar(select(func.count()).select_from(ProspectingDialLeg)) == 1

    with pytest.raises(ProspectingDialerConflictError, match="current dialer session"):
        start_dial_session(
            db_session,
            graph.principal,
            session_start(graph, suffix="second"),
            settings=settings,
            now=started_at + timedelta(seconds=3),
        )


def test_due_callback_is_reserved_before_a_new_record(
    db_session: Session,
    settings_factory: Callable[..., Settings],
) -> None:
    graph = seed_coordinator_graph(db_session)
    settings = settings_factory()
    now = datetime.now(UTC)
    callback = graph.entries[1]
    callback.disposition = "follow_up"
    callback.next_attempt_at = now - timedelta(minutes=5)
    db_session.commit()

    started = start_dial_session(
        db_session,
        graph.principal,
        session_start(graph),
        settings=settings,
        now=now,
    )

    assert started is not None
    assert started.snapshot.session.current_batch_entry_id == callback.id
    assert started.snapshot.current_leg is not None
    leg = db_session.get(ProspectingDialLeg, started.snapshot.current_leg.id)
    assert leg is not None
    assert leg.leg_metadata["queue_priority"] == "callback"


def test_returned_handoff_correction_can_reserve_its_linked_prospect(
    db_session: Session,
    settings_factory: Callable[..., Settings],
) -> None:
    graph = seed_coordinator_graph(db_session)
    settings = settings_factory()
    now = datetime.now(UTC)
    correction = graph.entries[1]
    correction.status = "needs_correction"
    prospect = db_session.get(Prospect, correction.prospect_id)
    assert prospect is not None
    # SQLite's focused coordinator fixture does not enforce FKs. The non-null
    # identifier models the real warm lead created by the earlier handoff.
    prospect.converted_lead_id = uuid4()
    db_session.commit()

    started = start_dial_session(
        db_session,
        graph.principal,
        session_start(graph),
        settings=settings,
        now=now,
    )

    assert started is not None
    assert started.snapshot.session.current_batch_entry_id == correction.id
    assert started.snapshot.current_leg is not None
    leg = db_session.get(ProspectingDialLeg, started.snapshot.current_leg.id)
    assert leg is not None
    assert leg.leg_metadata["queue_priority"] == "correction"
    validate_reserved_dial_leg_policy(
        db_session,
        graph.principal,
        leg,
        settings,
        now=now,
    )


def test_session_start_rejects_an_outside_hours_queue(
    db_session: Session,
    settings_factory: Callable[..., Settings],
) -> None:
    graph = seed_coordinator_graph(db_session)
    settings = settings_factory()
    graph.cohort.call_window_start_hour = 8
    graph.cohort.call_window_end_hour = 9
    db_session.commit()
    outside_window = datetime.combine(
        datetime.now(UTC).date(),
        datetime.min.time(),
        tzinfo=UTC,
    ) + timedelta(hours=12)

    with pytest.raises(ProspectingDialerConfigurationError, match="outside"):
        start_dial_session(
            db_session,
            graph.principal,
            session_start(graph),
            settings=settings,
            now=outside_window,
        )


def test_feature_line_cap_limits_every_stored_aggregate_capacity(
    db_session: Session,
    settings_factory: Callable[..., Settings],
) -> None:
    graph = seed_coordinator_graph(db_session)
    settings = settings_factory()
    profile = db_session.scalar(
        select(ProspectingDialerProfile).where(ProspectingDialerProfile.user_id == graph.caller.id)
    )
    assert profile is not None and profile.voice_line_id is not None
    line = db_session.get(VoiceLine, profile.voice_line_id)
    assert line is not None
    assert settings.prospecting_native_dialer_effective_line_cap == 1
    assert graph.organization.prospecting_dialer_max_concurrent_legs == 3
    assert graph.campaign.prospecting_dialer_max_concurrent_legs == 3
    assert profile.max_line_count == 3
    assert line.prospecting_dialer_max_concurrent_legs == 3
    now = datetime.now(UTC)

    started = start_dial_session(
        db_session,
        graph.principal,
        session_start(graph),
        settings=settings,
        now=now,
    )
    assert started is not None
    assert started.snapshot.session.effective_line_count == 1
    runtime_graph = load_runtime_graph(
        db_session,
        graph.principal,
        campaign_id=graph.campaign.id,
        cohort_id=graph.cohort.id,
        batch_id=graph.batch.id,
    )
    assert runtime_graph is not None

    blockers = runtime_policy_blockers(
        db_session,
        runtime_graph,
        settings,
        now=now,
        for_reservation=True,
    )

    assert "The company prospecting line capacity is already in use." in blockers
    assert "The campaign prospecting line capacity is already in use." in blockers
    assert "The caller's prospecting line capacity is already in use." in blockers
    assert "The assigned Twilio line is already at capacity." in blockers


def test_pause_resume_and_end_release_an_unstarted_reservation(
    db_session: Session,
    settings_factory: Callable[..., Settings],
) -> None:
    graph = seed_coordinator_graph(db_session)
    settings = settings_factory()
    now = datetime.now(UTC)
    payload = session_start(graph)
    started = start_dial_session(
        db_session,
        graph.principal,
        payload,
        settings=settings,
        now=now,
    )
    assert started is not None
    assert started.lease_token is not None
    assert started.snapshot.session.pause_after_current is False
    assert started.snapshot.session.stop_after_current is False
    command = lease_command(payload, started.lease_token)
    attempt_id = started.snapshot.session.current_attempt_id
    leg_id = started.snapshot.current_leg.id if started.snapshot.current_leg else None
    entry_id = started.snapshot.session.current_batch_entry_id
    assert attempt_id is not None
    assert leg_id is not None
    assert entry_id is not None

    paused = pause_dial_session(
        db_session,
        graph.principal,
        started.snapshot.session.id,
        command,
        settings=settings,
        now=now + timedelta(seconds=1),
    )
    assert paused is not None
    assert paused.snapshot.session.state == "paused"

    resumed = resume_dial_session(
        db_session,
        graph.principal,
        started.snapshot.session.id,
        command,
        settings=settings,
        now=now + timedelta(seconds=2),
    )
    assert resumed is not None
    assert resumed.snapshot.session.state == "ready"
    assert resumed.snapshot.session.current_attempt_id == attempt_id

    ended = end_dial_session(
        db_session,
        graph.principal,
        started.snapshot.session.id,
        ProspectingDialSessionEndCommand(
            browser_session_id=payload.browser_session_id,
            lease_token=started.lease_token,
            reason="Caller ended the controlled test shift.",
        ),
        settings=settings,
        now=now + timedelta(seconds=3),
    )
    assert ended is not None
    assert ended.snapshot.session.state == "ended"
    assert ended.lease_token is None
    assert ended.snapshot.session.current_attempt_id is None
    attempt = db_session.get(ProspectingAttempt, attempt_id)
    leg = db_session.get(ProspectingDialLeg, leg_id)
    entry = db_session.get(ProspectCallingBatchEntry, entry_id)
    assert attempt is not None and attempt.status == "cancelled"
    assert leg is not None and leg.status == "cancelled"
    assert leg.reserved_cost_cents == 0
    assert entry is not None and entry.status == "ready"


@pytest.mark.parametrize("operation", ["resume", "reserve", "recover"])
def test_dormant_flag_blocks_caller_control_reactivation(
    db_session: Session,
    settings_factory: Callable[..., Settings],
    operation: str,
) -> None:
    graph = seed_coordinator_graph(db_session)
    active_settings = settings_factory()
    now = datetime.now(UTC)
    start_payload = session_start(graph, suffix=f"dormant-{operation}")
    started = start_dial_session(
        db_session,
        graph.principal,
        start_payload,
        settings=active_settings,
        now=now,
    )
    assert started is not None
    assert started.lease_token is not None
    dormant_settings = settings_factory(enabled=False)

    with pytest.raises(ProspectingDialerConfigurationError, match="dialer is dormant"):
        if operation == "resume":
            resume_dial_session(
                db_session,
                graph.principal,
                started.snapshot.session.id,
                lease_command(start_payload, started.lease_token),
                settings=dormant_settings,
                now=now + timedelta(seconds=1),
            )
        elif operation == "reserve":
            reserve_next_dial_record(
                db_session,
                graph.principal,
                started.snapshot.session.id,
                lease_command(start_payload, started.lease_token),
                settings=dormant_settings,
                now=now + timedelta(seconds=1),
            )
        else:
            recover_dial_session(
                db_session,
                graph.principal,
                started.snapshot.session.id,
                ProspectingDialSessionRecoveryCommand(
                    previous_browser_session_id=start_payload.browser_session_id,
                    new_browser_session_id=f"browser-dormant-{operation}",
                    lease_token=started.lease_token,
                ),
                settings=dormant_settings,
                now=now + timedelta(seconds=1),
            )


@pytest.mark.parametrize("operation", ["resume", "reserve", "recover"])
def test_session_mutations_revalidate_d10_pilot_identity_before_control(
    db_session: Session,
    settings_factory: Callable[..., Settings],
    monkeypatch: MonkeyPatch,
    operation: str,
) -> None:
    graph = seed_coordinator_graph(db_session)
    settings = settings_factory()
    now = datetime.now(UTC)
    start_payload = session_start(graph, suffix=f"pilot-lock-{operation}")
    started = start_dial_session(
        db_session,
        graph.principal,
        start_payload,
        settings=settings,
        now=now,
    )
    assert started is not None
    assert started.lease_token is not None
    unexpected_pilot_id = uuid4()
    monkeypatch.setattr(
        "app.services.prospecting_dialer.lock_expected_session_pilot",
        lambda *args, **kwargs: unexpected_pilot_id,
    )
    session_id = started.snapshot.session.id

    with pytest.raises(ProspectingDialerConflictError, match="authorization changed"):
        if operation == "resume":
            resume_dial_session(
                db_session,
                graph.principal,
                session_id,
                lease_command(start_payload, started.lease_token),
                settings=settings,
                now=now + timedelta(seconds=1),
            )
        elif operation == "reserve":
            reserve_next_dial_record(
                db_session,
                graph.principal,
                session_id,
                lease_command(start_payload, started.lease_token),
                settings=settings,
                now=now + timedelta(seconds=1),
            )
        else:
            recover_dial_session(
                db_session,
                graph.principal,
                session_id,
                ProspectingDialSessionRecoveryCommand(
                    previous_browser_session_id=start_payload.browser_session_id,
                    new_browser_session_id=f"browser-pilot-lock-{operation}",
                    lease_token=started.lease_token,
                ),
                settings=settings,
                now=now + timedelta(seconds=1),
            )


def test_native_wrap_up_revalidates_d10_pilot_identity_before_auto_advance(
    db_session: Session,
    settings_factory: Callable[..., Settings],
    monkeypatch: MonkeyPatch,
) -> None:
    graph = seed_coordinator_graph(db_session)
    settings = settings_factory()
    now = datetime.now(UTC)
    start_payload = session_start(graph, suffix="pilot-lock-wrap-up")
    started = start_dial_session(
        db_session,
        graph.principal,
        start_payload,
        settings=settings,
        now=now,
    )
    assert started is not None
    assert started.lease_token is not None
    assert started.snapshot.current_leg is not None
    attempt_id = started.snapshot.session.current_attempt_id
    assert attempt_id is not None
    leg = db_session.get(ProspectingDialLeg, started.snapshot.current_leg.id)
    assert leg is not None
    record_dial_provider_event(
        db_session,
        organization_id=graph.organization.id,
        provider="twilio",
        external_event_id="d10-wrap-up-pilot-lock-terminal",
        event_type="call.no_answer",
        payload={"CallStatus": "no-answer"},
        dial_leg=leg,
        target_status="no_answer",
        occurred_at=now + timedelta(seconds=1),
        signature_verified=True,
        signature="verified-test-signature",
    )
    db_session.commit()
    monkeypatch.setattr(
        "app.services.prospecting_dialer.lock_expected_session_pilot",
        lambda *args, **kwargs: uuid4(),
    )

    with pytest.raises(ProspectingDialerConflictError, match="authorization changed"):
        complete_attempt(
            db_session,
            graph.principal,
            attempt_id,
            ProspectingAttemptComplete(
                outcome="no_answer",
                idempotency_key="d10-wrap-up-pilot-lock",
                browser_session_id=start_payload.browser_session_id,
                lease_token=started.lease_token,
            ),
        )

    db_session.rollback()
    attempt = db_session.get(ProspectingAttempt, attempt_id)
    assert attempt is not None
    assert attempt.status == "in_progress"


def test_live_call_deferred_pause_and_stop_are_exposed_in_session_read(
    db_session: Session,
    settings_factory: Callable[..., Settings],
) -> None:
    graph = seed_coordinator_graph(db_session)
    settings = settings_factory()
    now = datetime.now(UTC)
    payload = session_start(graph)
    started = start_dial_session(
        db_session,
        graph.principal,
        payload,
        settings=settings,
        now=now,
    )
    assert started is not None
    assert started.lease_token is not None
    assert started.snapshot.current_leg is not None
    leg = db_session.get(ProspectingDialLeg, started.snapshot.current_leg.id)
    assert leg is not None
    _, applied = record_dial_provider_event(
        db_session,
        organization_id=graph.organization.id,
        provider="twilio",
        external_event_id="d3-live-call-deferred-controls",
        event_type="call.ringing",
        payload={"CallStatus": "ringing"},
        dial_leg=leg,
        target_status="ringing",
        occurred_at=now + timedelta(seconds=1),
        signature_verified=True,
        signature="verified-test-signature",
    )
    assert applied is True
    db_session.commit()

    paused = pause_dial_session(
        db_session,
        graph.principal,
        started.snapshot.session.id,
        lease_command(payload, started.lease_token),
        settings=settings,
        now=now + timedelta(seconds=2),
    )
    assert paused is not None
    assert paused.snapshot.session.pause_after_current is True
    assert paused.snapshot.session.stop_after_current is False

    ended = end_dial_session(
        db_session,
        graph.principal,
        started.snapshot.session.id,
        ProspectingDialSessionEndCommand(
            browser_session_id=payload.browser_session_id,
            lease_token=started.lease_token,
            reason="Caller ended after the active seller call.",
        ),
        settings=settings,
        now=now + timedelta(seconds=3),
    )
    assert ended is not None
    assert ended.snapshot.session.pause_after_current is True
    assert ended.snapshot.session.stop_after_current is True


def test_terminal_provider_event_enters_wrap_up_and_completion_advances_queue(
    db_session: Session,
    settings_factory: Callable[..., Settings],
) -> None:
    graph = seed_coordinator_graph(db_session)
    settings = settings_factory()
    now = datetime.now(UTC)
    start_payload = session_start(graph)
    started = start_dial_session(
        db_session,
        graph.principal,
        start_payload,
        settings=settings,
        now=now,
    )
    assert started is not None
    assert started.snapshot.current_leg is not None
    first_attempt_id = started.snapshot.session.current_attempt_id
    first_entry_id = started.snapshot.session.current_batch_entry_id
    leg = db_session.get(ProspectingDialLeg, started.snapshot.current_leg.id)
    assert first_attempt_id is not None
    assert first_entry_id is not None
    assert leg is not None

    _, applied = record_dial_provider_event(
        db_session,
        organization_id=graph.organization.id,
        provider="twilio",
        external_event_id="d3-terminal-no-answer",
        event_type="call.no_answer",
        payload={"CallStatus": "no-answer"},
        dial_leg=leg,
        target_status="no_answer",
        occurred_at=now + timedelta(seconds=1),
        signature_verified=True,
        signature="verified-test-signature",
    )
    assert applied is True
    db_session.commit()
    session = db_session.get(ProspectingDialSession, started.snapshot.session.id)
    assert session is not None
    assert leg.status == "no_answer"
    assert session.state == "wrap_up"

    completed = complete_attempt(
        db_session,
        graph.principal,
        first_attempt_id,
        ProspectingAttemptComplete(
            outcome="no_answer",
            idempotency_key="complete-terminal-no-answer",
            browser_session_id=start_payload.browser_session_id,
            lease_token=started.lease_token,
        ),
    )
    assert completed is not None
    db_session.refresh(session)
    assert session.state == "ready"
    assert session.current_attempt_id is not None
    assert session.current_attempt_id != first_attempt_id
    assert session.current_batch_entry_id is not None
    assert session.current_batch_entry_id != first_entry_id
    next_leg = db_session.scalar(
        select(ProspectingDialLeg).where(
            ProspectingDialLeg.attempt_id == session.current_attempt_id
        )
    )
    assert next_leg is not None
    assert next_leg.status == "queued"


def test_stale_browser_cannot_complete_native_wrap_up(
    db_session: Session,
    settings_factory: Callable[..., Settings],
) -> None:
    graph = seed_coordinator_graph(db_session)
    settings = settings_factory()
    now = datetime.now(UTC)
    start_payload = session_start(graph)
    started = start_dial_session(
        db_session,
        graph.principal,
        start_payload,
        settings=settings,
        now=now,
    )
    assert started is not None
    assert started.lease_token is not None
    assert started.snapshot.current_leg is not None
    attempt_id = started.snapshot.session.current_attempt_id
    assert attempt_id is not None
    leg = db_session.get(ProspectingDialLeg, started.snapshot.current_leg.id)
    assert leg is not None
    record_dial_provider_event(
        db_session,
        organization_id=graph.organization.id,
        provider="twilio",
        external_event_id="d3-stale-browser-terminal",
        event_type="call.no_answer",
        payload={"CallStatus": "no-answer"},
        dial_leg=leg,
        target_status="no_answer",
        occurred_at=now + timedelta(seconds=1),
        signature_verified=True,
        signature="verified-test-signature",
    )
    db_session.commit()

    with pytest.raises(ProspectingDialerConflictError, match="browser session"):
        complete_attempt(
            db_session,
            graph.principal,
            attempt_id,
            ProspectingAttemptComplete(
                outcome="no_answer",
                browser_session_id="browser-stale-tab",
                lease_token=started.lease_token,
            ),
        )

    db_session.rollback()
    attempt = db_session.get(ProspectingAttempt, attempt_id)
    session = db_session.get(ProspectingDialSession, started.snapshot.session.id)
    assert attempt is not None and attempt.status == "in_progress"
    assert session is not None and session.state == "wrap_up"
    assert session.current_attempt_id == attempt_id

    session.lease_expires_at = datetime.now(UTC) - timedelta(seconds=1)
    db_session.commit()
    with pytest.raises(ProspectingDialerConflictError, match="lease expired"):
        complete_attempt(
            db_session,
            graph.principal,
            attempt_id,
            ProspectingAttemptComplete(
                outcome="no_answer",
                browser_session_id=start_payload.browser_session_id,
                lease_token=started.lease_token,
            ),
        )
    db_session.rollback()


def test_manager_cannot_complete_another_callers_native_attempt(
    db_session: Session,
    settings_factory: Callable[..., Settings],
) -> None:
    graph = seed_coordinator_graph(db_session)
    settings = settings_factory()
    now = datetime.now(UTC)
    started = start_dial_session(
        db_session,
        graph.principal,
        session_start(graph),
        settings=settings,
        now=now,
    )
    assert started is not None
    assert started.snapshot.current_leg is not None
    attempt_id = started.snapshot.session.current_attempt_id
    assert attempt_id is not None
    leg = db_session.get(ProspectingDialLeg, started.snapshot.current_leg.id)
    assert leg is not None
    record_dial_provider_event(
        db_session,
        organization_id=graph.organization.id,
        provider="twilio",
        external_event_id="d3-manager-terminal",
        event_type="call.no_answer",
        payload={"CallStatus": "no-answer"},
        dial_leg=leg,
        target_status="no_answer",
        occurred_at=now + timedelta(seconds=1),
        signature_verified=True,
        signature="verified-test-signature",
    )
    db_session.commit()
    manager = Principal(
        user_id=graph.owner.id,
        organization_id=graph.organization.id,
        email=graph.owner.email,
        permission_keys=frozenset({PermissionKeys.MANAGE_ACQUISITION_OPERATIONS}),
    )

    with pytest.raises(PermissionError, match="assigned caller"):
        complete_attempt(
            db_session,
            manager,
            attempt_id,
            ProspectingAttemptComplete(outcome="no_answer"),
        )
    db_session.rollback()

    session = db_session.get(ProspectingDialSession, started.snapshot.session.id)
    assert session is not None
    assert session.state == "wrap_up"
    assert session.current_attempt_id == attempt_id
    assert db_session.scalar(select(func.count()).select_from(ProspectingDialLeg)) == 1


def test_stale_recovery_preserves_provider_evidence(
    db_session: Session,
    settings_factory: Callable[..., Settings],
) -> None:
    graph = seed_coordinator_graph(db_session)
    settings = settings_factory()
    start_payload = session_start(graph)
    started = start_dial_session(
        db_session,
        graph.principal,
        start_payload,
        settings=settings,
        now=datetime.now(UTC),
    )
    assert started is not None
    assert started.lease_token is not None
    assert started.snapshot.current_leg is not None
    session_id = started.snapshot.session.id
    attempt_id = started.snapshot.session.current_attempt_id
    session = db_session.get(ProspectingDialSession, session_id)
    leg = db_session.get(ProspectingDialLeg, started.snapshot.current_leg.id)
    assert session is not None
    assert leg is not None
    stale = datetime.now(UTC) - timedelta(minutes=5)
    session.state = "dialing"
    session.heartbeat_at = stale
    session.lease_expires_at = stale
    leg.status = "dialing"
    leg.dialing_at = stale
    leg.provider_call_id = "CA00000000000000000000000000000301"
    db_session.commit()

    assert process_next_prospecting_dialer_recovery(db_session, settings) == session_id
    db_session.refresh(session)
    db_session.refresh(leg)
    assert session.state == "reconnecting"
    assert session.current_attempt_id == attempt_id
    assert session.ended_at is None
    assert session.lease_token is not None
    assert session.lease_expires_at is not None
    assert leg.status == "dialing"
    assert leg.provider_call_id == "CA00000000000000000000000000000301"
    assert "provider_work_preserved_at" in session.recovery_metadata
    assert session.lease_expires_at is not None
    assert as_utc(session.lease_expires_at) <= datetime.now(UTC)

    recovered = recover_dial_session(
        db_session,
        graph.principal,
        session_id,
        ProspectingDialSessionRecoveryCommand(
            previous_browser_session_id=start_payload.browser_session_id,
            new_browser_session_id="browser-recovered-provider-call",
            lease_token=started.lease_token,
        ),
        settings=settings,
        now=datetime.now(UTC),
    )
    assert recovered is not None
    assert recovered.snapshot.session.state == "dialing"
    assert recovered.lease_token is not None
    assert recovered.lease_token != started.lease_token
    db_session.refresh(session)
    assert session.browser_session_id == "browser-recovered-provider-call"


def test_stale_queued_orphan_is_released_after_grace(
    db_session: Session,
    settings_factory: Callable[..., Settings],
) -> None:
    graph = seed_coordinator_graph(db_session)
    settings = settings_factory()
    started = start_dial_session(
        db_session,
        graph.principal,
        session_start(graph),
        settings=settings,
        now=datetime.now(UTC),
    )
    assert started is not None
    assert started.snapshot.current_leg is not None
    session_id = started.snapshot.session.id
    attempt_id = started.snapshot.session.current_attempt_id
    entry_id = started.snapshot.session.current_batch_entry_id
    session = db_session.get(ProspectingDialSession, session_id)
    leg = db_session.get(ProspectingDialLeg, started.snapshot.current_leg.id)
    assert attempt_id is not None
    assert entry_id is not None
    assert session is not None
    assert leg is not None
    stale = datetime.now(UTC) - timedelta(minutes=5)
    session.heartbeat_at = stale
    session.lease_expires_at = stale
    db_session.commit()

    assert process_next_prospecting_dialer_recovery(db_session, settings) == session_id
    db_session.refresh(session)
    assert session.state == "reconnecting"
    recovery = dict(session.recovery_metadata)
    recovery["queued_orphan_first_seen_at"] = (datetime.now(UTC) - timedelta(minutes=2)).isoformat()
    session.recovery_metadata = recovery
    session.heartbeat_at = stale
    session.lease_expires_at = stale
    db_session.commit()

    assert process_next_prospecting_dialer_recovery(db_session, settings) == session_id
    db_session.refresh(session)
    db_session.refresh(leg)
    attempt = db_session.get(ProspectingAttempt, attempt_id)
    entry = db_session.get(ProspectCallingBatchEntry, entry_id)
    assert session.state == "expired"
    assert session.current_attempt_id is None
    assert session.lease_token is None
    assert session.lease_expires_at is None
    assert leg.status == "cancelled"
    assert leg.provider_call_id is None
    assert leg.reserved_cost_cents == 0
    assert attempt is not None and attempt.status == "cancelled"
    assert entry is not None and entry.status == "ready"


def test_technical_failure_is_replay_safe_and_does_not_consume_seller_cadence(
    db_session: Session,
    settings_factory: Callable[..., Settings],
) -> None:
    graph = seed_coordinator_graph(db_session, record_count=2)
    settings = settings_factory()
    start_payload = session_start(graph, suffix="technical-failure")
    started = start_dial_session(
        db_session,
        graph.principal,
        start_payload,
        settings=settings,
        now=datetime.now(UTC),
    )
    assert started is not None
    assert started.lease_token is not None
    assert started.snapshot.current_leg is not None
    attempt_id = started.snapshot.session.current_attempt_id
    assert attempt_id is not None
    leg = db_session.get(ProspectingDialLeg, started.snapshot.current_leg.id)
    assert leg is not None
    leg.provider_error_code = "provider_unavailable"
    leg.provider_error_message = "Provider could not place the call."
    terminalize_test_leg(
        db_session,
        graph,
        leg,
        key="d6-technical",
        final_status="failed",
    )
    command = ProspectingTechnicalFailureComplete(
        browser_session_id=start_payload.browser_session_id,
        lease_token=started.lease_token,
        idempotency_key=f"technical-failure:{attempt_id}",
    )

    completed = complete_technical_failure(
        db_session,
        graph.principal,
        attempt_id,
        command,
    )
    assert completed is not None
    first_entry = db_session.get(ProspectCallingBatchEntry, graph.entries[0].id)
    attempt = db_session.get(ProspectingAttempt, attempt_id)
    assert first_entry is not None
    assert attempt is not None
    assert first_entry.attempt_count == 0
    assert first_entry.status == "queued"
    assert first_entry.next_attempt_at is not None
    assert attempt.outcome == "technical_failure"
    assert attempt.contact_made is False
    assert attempt.measurement_metadata["cadence"]["consumes_seller_attempt"] is False
    assert attempt.measurement_metadata["provider_terminal"]["status"] == "failed"

    replay = complete_technical_failure(
        db_session,
        graph.principal,
        attempt_id,
        command,
    )
    assert replay is not None
    db_session.refresh(first_entry)
    assert first_entry.attempt_count == 0
    with pytest.raises(ProspectingCompletionConflictError, match="idempotency key"):
        complete_technical_failure(
            db_session,
            graph.principal,
            attempt_id,
            command.model_copy(update={"idempotency_key": f"different:{attempt_id}"}),
        )
    db_session.rollback()


@pytest.mark.parametrize("location_type", ["phone", "video", "office"])
def test_appointment_completion_requires_non_property_location(location_type: str) -> None:
    with pytest.raises(ValueError, match="explicit location"):
        ProspectingAttemptComplete(
            outcome="appointment_set",
            handoff_user_id=uuid4(),
            appointment_start_at=datetime.now(UTC) + timedelta(days=1),
            appointment_location_type=location_type,
        )


def test_native_appointment_completion_replays_once_and_uses_connected_phone(
    db_session: Session,
    settings_factory: Callable[..., Settings],
) -> None:
    graph = seed_coordinator_graph(db_session, record_count=1)
    settings = settings_factory()
    prospect = db_session.get(Prospect, graph.entries[0].prospect_id)
    assert prospect is not None
    now = datetime.now(UTC)
    alternate_phone = "+14045559991"
    point = ProspectContactPoint(
        organization_id=graph.organization.id,
        prospect_id=prospect.id,
        source_membership_id=None,
        contact_type="phone",
        value=alternate_phone,
        normalized_value=alternate_phone,
        rank=1,
        is_primary=False,
        validation_status="verified",
        first_seen_at=now,
        last_seen_at=now,
        contact_metadata={"source": "d6_test"},
    )
    db_session.add(point)
    db_session.commit()
    start_payload = session_start(graph, suffix="appointment-replay")
    started = start_dial_session(
        db_session,
        graph.principal,
        start_payload,
        settings=settings,
        now=now,
    )
    assert started is not None
    assert started.lease_token is not None
    assert started.snapshot.current_leg is not None
    attempt_id = started.snapshot.session.current_attempt_id
    assert attempt_id is not None
    leg = db_session.get(ProspectingDialLeg, started.snapshot.current_leg.id)
    assert leg is not None
    assert leg.contact_point_id == point.id
    assert leg.recipient == alternate_phone
    terminalize_test_leg(
        db_session,
        graph,
        leg,
        key="d6-appointment-replay",
        final_status="completed",
        connected=True,
    )
    provider_answered_at = leg.answered_at
    payload = ProspectingAttemptComplete(
        outcome="appointment_set",
        idempotency_key=f"appointment-complete:{attempt_id}",
        browser_session_id=start_payload.browser_session_id,
        lease_token=started.lease_token,
        handoff_user_id=graph.owner.id,
        appointment_start_at=now + timedelta(days=1),
        appointment_location_type="seller_property",
        notes="Seller requested an in-person visit.",
    )

    completed = complete_attempt(db_session, graph.principal, attempt_id, payload)
    assert completed is not None
    replay = complete_attempt(db_session, graph.principal, attempt_id, payload)
    assert replay is not None
    assert db_session.scalar(select(func.count(Lead.id))) == 1
    assert db_session.scalar(select(func.count(ProspectHandoff.id))) == 1
    assert db_session.scalar(select(func.count(Appointment.id))) == 1
    appointment = db_session.scalar(select(Appointment))
    converted_prospect = db_session.get(Prospect, prospect.id)
    attempt = db_session.get(ProspectingAttempt, attempt_id)
    assert appointment is not None
    assert converted_prospect is not None
    assert attempt is not None
    assert appointment.prospecting_attempt_id == attempt_id
    assert appointment.location_type == "seller_property"
    assert appointment.location == "1 Coordinator Way, Atlanta, GA 30303"
    assert converted_prospect.converted_lead_id is not None
    assert attempt.answered_at == provider_answered_at
    assert attempt.classification_source == "provider_plus_manual_outcome"
    lead = db_session.get(Lead, converted_prospect.converted_lead_id)
    assert lead is not None
    phones = list(
        db_session.scalars(
            select(ContactMethod).where(
                ContactMethod.contact_id == lead.contact_id,
                ContactMethod.method_type == "phone",
            )
        )
    )
    assert {phone.normalized_value for phone in phones} == {
        alternate_phone,
        prospect.normalized_phone,
    }
    assert next(phone for phone in phones if phone.is_primary).normalized_value == alternate_phone
    with pytest.raises(ProspectingCompletionConflictError, match="payload"):
        complete_attempt(
            db_session,
            graph.principal,
            attempt_id,
            payload.model_copy(update={"notes": "A different completion body."}),
        )
    db_session.rollback()


def test_no_answer_cadence_exhausts_at_script_maximum(
    db_session: Session,
    settings_factory: Callable[..., Settings],
) -> None:
    graph = seed_coordinator_graph(db_session, record_count=1)
    settings = settings_factory()
    script = db_session.scalar(
        select(ProspectingScriptVersion).where(
            ProspectingScriptVersion.organization_id == graph.organization.id
        )
    )
    assert script is not None
    script.disposition_rules = {
        "maximum_seller_attempts": 1,
        "no_answer_retry_delay_hours": 7,
    }
    db_session.commit()
    start_payload = session_start(graph, suffix="cadence-exhausted")
    started = start_dial_session(
        db_session,
        graph.principal,
        start_payload,
        settings=settings,
        now=datetime.now(UTC),
    )
    assert started is not None
    assert started.lease_token is not None
    assert started.snapshot.current_leg is not None
    attempt_id = started.snapshot.session.current_attempt_id
    assert attempt_id is not None
    leg = db_session.get(ProspectingDialLeg, started.snapshot.current_leg.id)
    assert leg is not None
    terminalize_test_leg(
        db_session,
        graph,
        leg,
        key="d6-cadence-exhausted",
        final_status="no_answer",
    )
    completed = complete_attempt(
        db_session,
        graph.principal,
        attempt_id,
        ProspectingAttemptComplete(
            outcome="no_answer",
            idempotency_key=f"no-answer-complete:{attempt_id}",
            browser_session_id=start_payload.browser_session_id,
            lease_token=started.lease_token,
        ),
    )
    assert completed is not None
    entry = db_session.get(ProspectCallingBatchEntry, graph.entries[0].id)
    prospect = db_session.get(Prospect, graph.entries[0].prospect_id)
    attempt = db_session.get(ProspectingAttempt, attempt_id)
    assert entry is not None
    assert prospect is not None
    assert attempt is not None
    assert entry.status == "completed"
    assert entry.next_attempt_at is None
    assert prospect.status == "cadence_exhausted"
    assert attempt.measurement_metadata["cadence"] == {
        "outcome": "no_answer",
        "seller_attempt_number": 1,
        "maximum_seller_attempts": 1,
        "delay_seconds": 7 * 60 * 60,
        "next_attempt_at": None,
        "consumes_seller_attempt": True,
        "exhausted": True,
        "script_version_id": str(script.id),
        "script_version_number": script.version_number,
    }


def test_wrong_number_invalidates_exact_phone_and_reserves_ranked_fallback(
    db_session: Session,
    settings_factory: Callable[..., Settings],
) -> None:
    graph = seed_coordinator_graph(db_session, record_count=1)
    settings = settings_factory()
    prospect = db_session.get(Prospect, graph.entries[0].prospect_id)
    assert prospect is not None
    now = datetime.now(UTC)
    first = ProspectContactPoint(
        organization_id=graph.organization.id,
        prospect_id=prospect.id,
        source_membership_id=None,
        contact_type="phone",
        value="+14045559981",
        normalized_value="+14045559981",
        rank=1,
        is_primary=False,
        validation_status="verified",
        first_seen_at=now,
        last_seen_at=now,
        contact_metadata={},
    )
    second = ProspectContactPoint(
        organization_id=graph.organization.id,
        prospect_id=prospect.id,
        source_membership_id=None,
        contact_type="phone",
        value="+14045559982",
        normalized_value="+14045559982",
        rank=2,
        is_primary=False,
        validation_status="verified",
        first_seen_at=now,
        last_seen_at=now,
        contact_metadata={},
    )
    db_session.add_all([first, second])
    db_session.commit()
    start_payload = session_start(graph, suffix="wrong-fallback")
    started = start_dial_session(
        db_session,
        graph.principal,
        start_payload,
        settings=settings,
        now=now,
    )
    assert started is not None
    assert started.lease_token is not None
    assert started.snapshot.current_leg is not None
    attempt_id = started.snapshot.session.current_attempt_id
    assert attempt_id is not None
    leg = db_session.get(ProspectingDialLeg, started.snapshot.current_leg.id)
    assert leg is not None
    assert leg.contact_point_id == first.id
    terminalize_test_leg(
        db_session,
        graph,
        leg,
        key="d6-wrong-fallback",
        final_status="completed",
        connected=True,
    )
    completed = complete_attempt(
        db_session,
        graph.principal,
        attempt_id,
        ProspectingAttemptComplete(
            outcome="wrong_number",
            idempotency_key=f"wrong-number-complete:{attempt_id}",
            browser_session_id=start_payload.browser_session_id,
            lease_token=started.lease_token,
        ),
    )
    assert completed is not None
    db_session.refresh(first)
    db_session.refresh(second)
    db_session.refresh(prospect)
    assert first.validation_status == "invalid"
    assert second.validation_status == "verified"
    assert prospect.call_eligibility == "eligible"
    suppression = db_session.scalar(
        select(SuppressionRecord).where(
            SuppressionRecord.normalized_address == first.normalized_value
        )
    )
    assert suppression is not None
    session = db_session.get(ProspectingDialSession, started.snapshot.session.id)
    assert session is not None
    assert session.current_attempt_id is not None
    assert session.current_attempt_id != attempt_id
    fallback_leg = db_session.scalar(
        select(ProspectingDialLeg).where(
            ProspectingDialLeg.attempt_id == session.current_attempt_id
        )
    )
    assert fallback_leg is not None
    assert fallback_leg.contact_point_id == second.id
    assert fallback_leg.recipient == second.normalized_value


def test_dnc_suppresses_only_exact_number_across_prospects(
    db_session: Session,
    settings_factory: Callable[..., Settings],
) -> None:
    graph = seed_coordinator_graph(db_session, record_count=2)
    settings = settings_factory()
    first_prospect = db_session.get(Prospect, graph.entries[0].prospect_id)
    second_prospect = db_session.get(Prospect, graph.entries[1].prospect_id)
    assert first_prospect is not None
    assert second_prospect is not None
    shared_phone = "+14045559971"
    second_prospect.phone = shared_phone
    second_prospect.normalized_phone = shared_phone
    second_prospect.phone_validation_status = "verified"
    now = datetime.now(UTC)
    point = ProspectContactPoint(
        organization_id=graph.organization.id,
        prospect_id=first_prospect.id,
        source_membership_id=None,
        contact_type="phone",
        value=shared_phone,
        normalized_value=shared_phone,
        rank=1,
        is_primary=False,
        validation_status="verified",
        first_seen_at=now,
        last_seen_at=now,
        contact_metadata={},
    )
    db_session.add(point)
    db_session.commit()
    start_payload = session_start(graph, suffix="exact-dnc")
    started = start_dial_session(
        db_session,
        graph.principal,
        start_payload,
        settings=settings,
        now=now,
    )
    assert started is not None
    assert started.lease_token is not None
    assert started.snapshot.current_leg is not None
    attempt_id = started.snapshot.session.current_attempt_id
    assert attempt_id is not None
    leg = db_session.get(ProspectingDialLeg, started.snapshot.current_leg.id)
    assert leg is not None
    assert leg.recipient == shared_phone
    terminalize_test_leg(
        db_session,
        graph,
        leg,
        key="d6-exact-dnc",
        final_status="completed",
        connected=True,
    )
    completed = complete_attempt(
        db_session,
        graph.principal,
        attempt_id,
        ProspectingAttemptComplete(
            outcome="do_not_call",
            idempotency_key=f"dnc-complete:{attempt_id}",
            browser_session_id=start_payload.browser_session_id,
            lease_token=started.lease_token,
        ),
    )
    assert completed is not None
    db_session.refresh(first_prospect)
    db_session.refresh(second_prospect)
    assert first_prospect.call_eligibility == "blocked"
    assert first_prospect.suppression_status == "suppressed"
    assert second_prospect.call_eligibility == "eligible"
    assert select_ranked_phone(db_session, second_prospect) is None
    suppression = db_session.scalar(
        select(SuppressionRecord).where(SuppressionRecord.normalized_address == shared_phone)
    )
    assert suppression is not None
    assert suppression.suppression_metadata["contact_point_id"] == str(point.id)
    assert db_session.scalar(select(func.count(SuppressionRecord.id))) == 1
