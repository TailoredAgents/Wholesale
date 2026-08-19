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
    Campaign,
    Market,
    Organization,
    Prospect,
    ProspectCallingBatch,
    ProspectCallingBatchEntry,
    ProspectingAttempt,
    ProspectingCohort,
    ProspectingDialerProfile,
    ProspectingDialLeg,
    ProspectingDialSession,
    ProspectingScriptVersion,
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
)
from app.services.bootstrap import bootstrap_foundation
from app.services.prospecting import autosave_attempt_qualification, complete_attempt
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
        external_event_id="d5-persisted-warm-terminal",
        event_type="call.completed",
        payload={"CallStatus": "completed"},
        dial_leg=leg,
        target_status="completed",
        occurred_at=now + timedelta(seconds=1),
        signature_verified=True,
        signature="verified-test-signature",
    )
    db_session.commit()

    completion = ProspectingAttemptComplete(
        outcome="interested",
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


def test_one_active_leg_consumes_each_single_line_capacity(
    db_session: Session,
    settings_factory: Callable[..., Settings],
) -> None:
    graph = seed_coordinator_graph(db_session)
    settings = settings_factory()
    graph.organization.prospecting_dialer_max_concurrent_legs = 1
    graph.campaign.prospecting_dialer_max_concurrent_legs = 1
    # Resolve the assigned line through the profile because its UUID intentionally
    # differs from the caller UUID.
    profile = db_session.scalar(
        select(ProspectingDialerProfile).where(ProspectingDialerProfile.user_id == graph.caller.id)
    )
    assert profile is not None and profile.voice_line_id is not None
    line = db_session.get(VoiceLine, profile.voice_line_id)
    assert line is not None
    line.prospecting_dialer_max_concurrent_legs = 1
    profile.default_line_count = 1
    profile.max_line_count = 1
    db_session.commit()
    now = datetime.now(UTC)

    started = start_dial_session(
        db_session,
        graph.principal,
        session_start(graph),
        settings=settings,
        now=now,
    )
    assert started is not None
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
