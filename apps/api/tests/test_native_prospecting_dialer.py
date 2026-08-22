from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, cast
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from pytest import MonkeyPatch
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.main import app
from app.models.foundation import (
    AuditEvent,
    Campaign,
    Market,
    Organization,
    Prospect,
    ProspectCallingBatch,
    ProspectCallingBatchEntry,
    ProspectingAttempt,
    ProspectingDialerProfile,
    ProspectingDialLeg,
    ProspectingDialSession,
    ProspectingProviderEvent,
    ProspectingQualificationResponse,
    ProspectingScriptVersion,
    User,
    VoiceLine,
)
from app.services.bootstrap import bootstrap_foundation
from app.services.prospecting_dialer import record_dial_provider_event

OWNER_EMAIL = "native-dialer-owner@example.com"
VA_EMAIL = "native-dialer-va@example.com"
OTHER_VA_EMAIL = "native-dialer-other-va@example.com"


@dataclass(frozen=True)
class DialerGraph:
    organization: Organization
    owner: User
    va: User
    other_va: User
    campaign: Campaign
    batch: ProspectCallingBatch
    prospects: tuple[Prospect, Prospect, Prospect]
    entries: tuple[ProspectCallingBatchEntry, ProspectCallingBatchEntry, ProspectCallingBatchEntry]
    script: ProspectingScriptVersion


def create_user(
    client: TestClient,
    headers: dict[str, str],
    *,
    email: str,
    name: str,
    role_key: str,
    calling_enabled: bool = False,
) -> dict[str, Any]:
    response = client.post(
        "/api/v1/operations/users",
        headers=headers,
        json={
            "email": email,
            "display_name": name,
            "role_key": role_key,
            "calling_enabled": calling_enabled,
        },
    )
    assert response.status_code == 201, response.text
    return cast(dict[str, Any], response.json())


def seed_users(db: Session) -> tuple[TestClient, dict[str, str], Organization, User, User, User]:
    foundation = bootstrap_foundation(
        db,
        organization_name="Native Dialer Test Workspace",
        admin_email=OWNER_EMAIL,
        admin_name="Dialer Owner",
    )
    assert foundation.admin_user is not None
    client = TestClient(app)
    owner_headers = {"X-Dev-User-Email": OWNER_EMAIL}
    va_payload = create_user(
        client,
        owner_headers,
        email=VA_EMAIL,
        name="Primary Dialer VA",
        role_key="prospecting_caller",
    )
    other_va_payload = create_user(
        client,
        owner_headers,
        email=OTHER_VA_EMAIL,
        name="Other Dialer VA",
        role_key="prospecting_caller",
    )
    va = db.get(User, UUID(va_payload["id"]))
    other_va = db.get(User, UUID(other_va_payload["id"]))
    assert va is not None
    assert other_va is not None
    return (
        client,
        owner_headers,
        foundation.organization,
        foundation.admin_user,
        va,
        other_va,
    )


def seed_dialer_graph(db: Session) -> DialerGraph:
    _, _, organization, owner, va, other_va = seed_users(db)
    market = Market(
        organization_id=organization.id,
        name="Atlanta Native Dialer",
        code="atlanta-native-dialer",
        state_code="GA",
        timezone="America/New_York",
        status="active",
        is_primary=True,
    )
    db.add(market)
    db.flush()
    campaign = Campaign(
        organization_id=organization.id,
        market_id=market.id,
        owner_user_id=owner.id,
        name="Native Dialer Campaign",
        code="native-dialer-campaign",
        channel="cold_call",
        asset_class="house",
        status="active",
        prospecting_dialer_max_concurrent_legs=3,
    )
    db.add(campaign)
    db.flush()
    prospects = tuple(
        Prospect(
            organization_id=organization.id,
            campaign_id=campaign.id,
            assigned_user_id=va.id,
            source_record_key=f"native-dialer-{number}",
            status="ready",
            legal_name=f"Dialer Prospect {number}",
            phone=f"40455501{number:02d}",
            normalized_phone=f"+140455501{number:02d}",
            street_address=f"{number} Dialer Way",
            city="Atlanta",
            state_code="GA",
            postal_code="30303",
            suppression_status="clear",
            call_eligibility="eligible",
            source_payload={},
        )
        for number in range(1, 4)
    )
    db.add_all(prospects)
    db.flush()
    batch = ProspectCallingBatch(
        organization_id=organization.id,
        campaign_id=campaign.id,
        assigned_user_id=va.id,
        created_by_user_id=owner.id,
        name="Native Dialer Queue",
        status="active",
        dialer_mode="one_line_power",
    )
    db.add(batch)
    db.flush()
    entries = tuple(
        ProspectCallingBatchEntry(
            organization_id=organization.id,
            prospect_calling_batch_id=batch.id,
            prospect_id=prospect.id,
            assigned_user_id=va.id,
            sequence_number=number,
            status="ready",
            attempt_count=0,
        )
        for number, prospect in enumerate(prospects, start=1)
    )
    db.add_all(entries)
    script = ProspectingScriptVersion(
        organization_id=organization.id,
        version_number=1,
        title="Native Dialer Qualification",
        status="approved",
        opening_script="Hello, I am calling about your property.",
        qualification_questions=[
            {
                "key": "motivation",
                "label": "Motivation",
                "prompt": "What has you considering selling?",
                "required_for_handoff": True,
            }
        ],
        disposition_rules={},
        created_by_user_id=owner.id,
        approved_by_user_id=owner.id,
        approved_at=datetime.now(UTC),
    )
    db.add(script)
    db.commit()
    return DialerGraph(
        organization=organization,
        owner=owner,
        va=va,
        other_va=other_va,
        campaign=campaign,
        batch=batch,
        prospects=cast(tuple[Prospect, Prospect, Prospect], prospects),
        entries=cast(
            tuple[ProspectCallingBatchEntry, ProspectCallingBatchEntry, ProspectCallingBatchEntry],
            entries,
        ),
        script=script,
    )


def add_profile(
    db: Session,
    graph: DialerGraph,
    user: User,
    *,
    line_count: int = 3,
) -> ProspectingDialerProfile:
    profile = ProspectingDialerProfile(
        organization_id=graph.organization.id,
        user_id=user.id,
        status="active",
        default_line_count=line_count,
        max_line_count=line_count,
        recording_policy="company_policy",
        profile_metadata={},
        created_by_user_id=graph.owner.id,
        updated_by_user_id=graph.owner.id,
    )
    db.add(profile)
    db.flush()
    return profile


def add_session(
    db: Session,
    graph: DialerGraph,
    profile: ProspectingDialerProfile,
    *,
    caller: User | None = None,
    key: str,
    state: str = "ready",
    ended_at: datetime | None = None,
) -> ProspectingDialSession:
    active_caller = caller or graph.va
    now = datetime.now(UTC)
    terminal = state in {"ended", "stopped", "failed", "expired"}
    session = ProspectingDialSession(
        organization_id=graph.organization.id,
        dialer_profile_id=profile.id,
        caller_user_id=active_caller.id,
        campaign_id=graph.campaign.id,
        prospect_calling_batch_id=graph.batch.id,
        state=state,
        requested_line_count=3,
        effective_line_count=1,
        organization_line_limit=3,
        va_line_limit=3,
        campaign_line_limit=3,
        voice_line_limit=3,
        feature_line_limit=1,
        idempotency_key=key,
        browser_session_id=f"browser-{key}",
        lease_token=None if terminal else f"lease-{key}".ljust(32, "x"),
        lease_expires_at=None if terminal else now + timedelta(minutes=5),
        started_at=now,
        heartbeat_at=now,
        ended_at=ended_at,
        recovery_metadata={},
        session_metadata={},
        created_by_user_id=active_caller.id,
    )
    db.add(session)
    db.flush()
    return session


def add_leg(
    db: Session,
    graph: DialerGraph,
    session: ProspectingDialSession,
    *,
    prospect_index: int,
    entry_index: int,
    slot: int,
    key: str,
    status: str = "queued",
    connected_at: datetime | None = None,
    completed_at: datetime | None = None,
) -> ProspectingDialLeg:
    leg = ProspectingDialLeg(
        organization_id=graph.organization.id,
        dial_session_id=session.id,
        prospect_id=graph.prospects[prospect_index].id,
        batch_entry_id=graph.entries[entry_index].id,
        line_slot=slot,
        recipient=graph.prospects[prospect_index].normalized_phone or "+14045550100",
        provider="twilio",
        provider_call_id=f"CA-{key}",
        idempotency_key=key,
        status=status,
        last_provider_event_sequence=0,
        queued_at=datetime.now(UTC),
        connected_at=connected_at,
        completed_at=completed_at,
        answer_classification="unknown",
        party_classification="unknown",
        leg_metadata={},
    )
    db.add(leg)
    db.flush()
    return leg


def add_attempt(
    db: Session,
    graph: DialerGraph,
    *,
    entry_index: int,
    caller: User,
    status: str = "in_progress",
    completed_at: datetime | None = None,
) -> ProspectingAttempt:
    attempt = ProspectingAttempt(
        organization_id=graph.organization.id,
        batch_entry_id=graph.entries[entry_index].id,
        prospect_id=graph.prospects[entry_index].id,
        caller_user_id=caller.id,
        script_version_id=graph.script.id,
        status=status,
        measurement_metadata={},
        qualification_answers={},
        started_at=datetime.now(UTC),
        completed_at=completed_at,
    )
    db.add(attempt)
    db.flush()
    return attempt


def assert_integrity_error(db: Session, model: object) -> None:
    with pytest.raises(IntegrityError), db.begin_nested():
        db.add(model)
        db.flush()


def test_manager_profile_controls_va_context_and_workspace_guards(
    db_session: Session,
    api_db_override: None,
    monkeypatch: MonkeyPatch,
) -> None:
    monkeypatch.setenv("PROSPECTING_NATIVE_DIALER_ENABLED", "true")
    monkeypatch.setenv("PROSPECTING_NATIVE_DIALER_MAX_LINES", "3")
    get_settings.cache_clear()
    try:
        client, owner_headers, organization, _, va, other_va = seed_users(db_session)
        organization.prospecting_dialer_max_concurrent_legs = 3
        voice_line = VoiceLine(
            organization_id=organization.id,
            provider="twilio",
            phone_number="+16785550101",
            label="Native dialer test line",
            department_key="acquisitions",
            purpose_key="prospecting_outbound",
            status="active",
            is_default=False,
            inbound_route="conversation_owner",
            ring_strategy="simultaneous",
            coverage_timezone="America/New_York",
            coverage_start_hour=0,
            coverage_end_hour=24,
            prospecting_dialer_max_concurrent_legs=3,
            missed_call_action="fallback_then_voicemail",
            line_metadata={},
        )
        db_session.add(voice_line)
        db_session.commit()

        payload = {
            "status": "active",
            "voice_line_id": str(voice_line.id),
            "default_line_count": 3,
            "max_line_count": 3,
            "recording_policy": "company_policy",
            "daily_dial_limit": 500,
            "daily_spend_limit_cents": 2500,
            "metadata": {"shift": "morning"},
        }
        create_response = client.put(
            f"/api/v1/prospecting/dialer/profiles/{va.id}",
            headers=owner_headers,
            json=payload,
        )
        assert create_response.status_code == 200, create_response.text
        created = create_response.json()
        assert created["default_line_count"] == 3
        assert created["max_line_count"] == 3
        assert created["effective_line_count"] == 1
        profile_id = UUID(created["id"])

        persisted = db_session.get(ProspectingDialerProfile, profile_id)
        assert persisted is not None
        assert persisted.default_line_count == 3
        assert persisted.max_line_count == 3
        audits = list(
            db_session.scalars(
                select(AuditEvent).where(
                    AuditEvent.organization_id == organization.id,
                    AuditEvent.action == "prospecting.dialer_profile_upserted",
                    AuditEvent.entity_id == profile_id,
                )
            )
        )
        assert len(audits) == 1
        assert audits[0].previous_value is None
        assert audits[0].new_value is not None
        assert audits[0].new_value["max_line_count"] == 3

        second_response = client.put(
            f"/api/v1/prospecting/dialer/profiles/{other_va.id}",
            headers=owner_headers,
            json={**payload, "metadata": {"shift": "afternoon"}},
        )
        assert second_response.status_code == 200, second_response.text
        profiles_response = client.get(
            "/api/v1/prospecting/dialer/profiles",
            headers=owner_headers,
        )
        assert profiles_response.status_code == 200, profiles_response.text
        assert {item["user_id"] for item in profiles_response.json()} == {
            str(va.id),
            str(other_va.id),
        }

        va_headers = {"X-Dev-User-Email": VA_EMAIL}
        context_response = client.get(
            "/api/v1/prospecting/dialer/context",
            headers=va_headers,
        )
        assert context_response.status_code == 200, context_response.text
        context = context_response.json()
        assert context["configured_line_cap"] == 3
        assert context["implemented_line_cap"] == 1
        assert context["effective_line_cap"] == 1
        assert context["can_manage"] is False
        assert context["profile"]["user_id"] == str(va.id)
        assert context["profile"]["metadata"] == {"shift": "morning"}
        assert "native-dialer-other-va@example.com" not in context_response.text
        assert (
            client.get("/api/v1/prospecting/dialer/profiles", headers=va_headers).status_code == 403
        )
        assert (
            client.put(
                f"/api/v1/prospecting/dialer/profiles/{other_va.id}",
                headers=va_headers,
                json=payload,
            ).status_code
            == 403
        )

        injected_response = client.put(
            f"/api/v1/prospecting/dialer/profiles/{va.id}",
            headers=owner_headers,
            json={**payload, "effective_line_count": 3, "effective_line_cap": 3},
        )
        assert injected_response.status_code == 422
        db_session.refresh(persisted)
        assert persisted.max_line_count == 3

        noncaller = create_user(
            client,
            owner_headers,
            email="native-dialer-noncaller@example.com",
            name="Noncaller",
            role_key="disposition_rep",
        )
        noncaller_response = client.put(
            f"/api/v1/prospecting/dialer/profiles/{noncaller['id']}",
            headers=owner_headers,
            json=payload,
        )
        assert noncaller_response.status_code == 422
        assert "Enable cold calling" in noncaller_response.json()["detail"]

        inactive = create_user(
            client,
            owner_headers,
            email="native-dialer-inactive@example.com",
            name="Inactive Caller",
            role_key="prospecting_caller",
        )
        deactivate_response = client.patch(
            f"/api/v1/operations/users/{inactive['id']}",
            headers=owner_headers,
            json={
                "is_active": False,
                "reason": "Validate native dialer inactive-user protections.",
            },
        )
        assert deactivate_response.status_code == 200, deactivate_response.text
        assert (
            client.put(
                f"/api/v1/prospecting/dialer/profiles/{inactive['id']}",
                headers=owner_headers,
                json=payload,
            ).status_code
            == 404
        )

        other_organization = Organization(
            name="Other Native Dialer Workspace",
            slug="other-native-dialer-workspace",
        )
        db_session.add(other_organization)
        db_session.flush()
        external_user = User(
            organization_id=other_organization.id,
            email="external-native-dialer@example.com",
            display_name="External Caller",
            is_active=True,
            calling_enabled=True,
        )
        db_session.add(external_user)
        db_session.commit()
        assert (
            client.put(
                f"/api/v1/prospecting/dialer/profiles/{external_user.id}",
                headers=owner_headers,
                json=payload,
            ).status_code
            == 404
        )
    finally:
        get_settings.cache_clear()


def test_dormant_flag_blocks_activation_but_allows_disable_controls(
    db_session: Session,
    api_db_override: None,
    monkeypatch: MonkeyPatch,
) -> None:
    monkeypatch.setenv("PROSPECTING_NATIVE_DIALER_ENABLED", "false")
    get_settings.cache_clear()
    try:
        graph = seed_dialer_graph(db_session)
        graph.va.calling_enabled = True
        graph.organization.prospecting_dialer_enabled = False
        graph.campaign.prospecting_dialer_enabled = False
        profile = add_profile(db_session, graph, graph.va, line_count=1)
        db_session.commit()

        client = TestClient(app)
        owner_headers = {"X-Dev-User-Email": OWNER_EMAIL}
        reason = "Keep the native dialer dormant during BatchDialer operation."

        for url in (
            "/api/v1/prospecting/dialer/switches/company",
            f"/api/v1/prospecting/dialer/switches/campaigns/{graph.campaign.id}",
        ):
            response = client.put(
                url,
                headers=owner_headers,
                json={"enabled": True, "reason": reason},
            )
            assert response.status_code == 503, response.text
            assert "dormant" in response.json()["detail"].lower()

        activation = client.put(
            f"/api/v1/prospecting/dialer/profiles/{graph.va.id}",
            headers=owner_headers,
            json={
                "status": "active",
                "voice_line_id": None,
                "default_line_count": 1,
                "max_line_count": 1,
                "recording_policy": "company_policy",
                "daily_dial_limit": 50,
                "daily_spend_limit_cents": 1000,
                "metadata": {},
            },
        )
        assert activation.status_code == 503, activation.text
        assert "dormant" in activation.json()["detail"].lower()

        graph.organization.prospecting_dialer_enabled = True
        graph.campaign.prospecting_dialer_enabled = True
        db_session.commit()
        for url in (
            "/api/v1/prospecting/dialer/switches/company",
            f"/api/v1/prospecting/dialer/switches/campaigns/{graph.campaign.id}",
        ):
            response = client.put(
                url,
                headers=owner_headers,
                json={"enabled": False, "reason": reason},
            )
            assert response.status_code == 200, response.text
            assert response.json()["enabled"] is False

        deactivation = client.put(
            f"/api/v1/prospecting/dialer/profiles/{graph.va.id}",
            headers=owner_headers,
            json={
                "status": "inactive",
                "voice_line_id": None,
                "default_line_count": 1,
                "max_line_count": 1,
                "recording_policy": "company_policy",
                "daily_dial_limit": 50,
                "daily_spend_limit_cents": 1000,
                "metadata": {},
            },
        )
        assert deactivation.status_code == 200, deactivation.text
        assert deactivation.json()["status"] == "inactive"
        db_session.refresh(profile)
        assert profile.status == "inactive"
    finally:
        get_settings.cache_clear()


def test_only_one_active_session_per_va_and_terminal_session_releases_lock(
    db_session: Session,
    api_db_override: None,
) -> None:
    graph = seed_dialer_graph(db_session)
    profile = add_profile(db_session, graph, graph.va)
    first = add_session(db_session, graph, profile, key="active-session-one")
    assert first.requested_line_count == 3
    assert first.effective_line_count == 1

    duplicate = ProspectingDialSession(
        organization_id=graph.organization.id,
        dialer_profile_id=profile.id,
        caller_user_id=graph.va.id,
        campaign_id=graph.campaign.id,
        state="ready",
        requested_line_count=3,
        effective_line_count=1,
        organization_line_limit=3,
        va_line_limit=3,
        campaign_line_limit=3,
        voice_line_limit=3,
        feature_line_limit=1,
        idempotency_key="active-session-two",
        browser_session_id="browser-active-session-two",
        lease_token="lease-active-session-two-xxxxxxxx",
        lease_expires_at=datetime.now(UTC) + timedelta(minutes=5),
        started_at=datetime.now(UTC),
        heartbeat_at=datetime.now(UTC),
        recovery_metadata={},
        session_metadata={},
        created_by_user_id=graph.va.id,
    )
    assert_integrity_error(db_session, duplicate)

    ended_at = datetime.now(UTC)
    first.state = "ended"
    first.ended_at = ended_at
    first.lease_token = None
    first.lease_expires_at = None
    db_session.flush()
    replacement = add_session(
        db_session,
        graph,
        profile,
        key="active-session-replacement",
    )
    assert replacement.id != first.id
    assert replacement.ended_at is None


def test_active_dial_leg_reservations_and_single_connected_leg_are_enforced(
    db_session: Session,
    api_db_override: None,
) -> None:
    graph = seed_dialer_graph(db_session)
    profile = add_profile(db_session, graph, graph.va)
    session = add_session(db_session, graph, profile, key="leg-constraint-session")
    first = add_leg(
        db_session,
        graph,
        session,
        prospect_index=0,
        entry_index=0,
        slot=1,
        key="first-leg",
    )

    for conflict in (
        ProspectingDialLeg(
            organization_id=graph.organization.id,
            dial_session_id=session.id,
            prospect_id=graph.prospects[0].id,
            batch_entry_id=graph.entries[1].id,
            line_slot=2,
            recipient="+14045550102",
            provider="twilio",
            provider_call_id="CA-active-prospect-conflict",
            idempotency_key="active-prospect-conflict",
            status="queued",
            queued_at=datetime.now(UTC),
            leg_metadata={},
        ),
        ProspectingDialLeg(
            organization_id=graph.organization.id,
            dial_session_id=session.id,
            prospect_id=graph.prospects[1].id,
            batch_entry_id=graph.entries[0].id,
            line_slot=2,
            recipient="+14045550102",
            provider="twilio",
            provider_call_id="CA-active-entry-conflict",
            idempotency_key="active-entry-conflict",
            status="queued",
            queued_at=datetime.now(UTC),
            leg_metadata={},
        ),
        ProspectingDialLeg(
            organization_id=graph.organization.id,
            dial_session_id=session.id,
            prospect_id=graph.prospects[1].id,
            batch_entry_id=graph.entries[1].id,
            line_slot=1,
            recipient="+14045550102",
            provider="twilio",
            provider_call_id="CA-active-slot-conflict",
            idempotency_key="active-slot-conflict",
            status="queued",
            queued_at=datetime.now(UTC),
            leg_metadata={},
        ),
    ):
        assert_integrity_error(db_session, conflict)

    connected_without_timestamp = ProspectingDialLeg(
        organization_id=graph.organization.id,
        dial_session_id=session.id,
        prospect_id=graph.prospects[1].id,
        batch_entry_id=graph.entries[1].id,
        line_slot=2,
        recipient="+14045550102",
        provider="twilio",
        provider_call_id="CA-connected-without-timestamp",
        idempotency_key="connected-without-timestamp",
        status="connected",
        queued_at=datetime.now(UTC),
        leg_metadata={},
    )
    assert_integrity_error(db_session, connected_without_timestamp)

    connected_at = datetime.now(UTC)
    first.status = "connected"
    first.connected_at = connected_at
    db_session.flush()
    connected_conflict = ProspectingDialLeg(
        organization_id=graph.organization.id,
        dial_session_id=session.id,
        prospect_id=graph.prospects[1].id,
        batch_entry_id=graph.entries[1].id,
        line_slot=2,
        recipient="+14045550102",
        provider="twilio",
        provider_call_id="CA-connected-conflict",
        idempotency_key="connected-conflict",
        status="connected",
        queued_at=connected_at,
        connected_at=connected_at,
        leg_metadata={},
    )
    assert_integrity_error(db_session, connected_conflict)

    first.status = "completed"
    first.completed_at = datetime.now(UTC)
    db_session.flush()
    replacement = add_leg(
        db_session,
        graph,
        session,
        prospect_index=0,
        entry_index=0,
        slot=1,
        key="replacement-leg",
    )
    assert replacement.completed_at is None


def test_provider_events_are_idempotent_and_do_not_regress_leg_state(
    db_session: Session,
    api_db_override: None,
) -> None:
    graph = seed_dialer_graph(db_session)
    profile = add_profile(db_session, graph, graph.va)
    session = add_session(db_session, graph, profile, key="provider-event-session")
    leg = add_leg(
        db_session,
        graph,
        session,
        prospect_index=0,
        entry_index=0,
        slot=1,
        key="provider-event-leg",
    )
    base_time = datetime.now(UTC)

    with pytest.raises(ValueError, match="verified provider signature"):
        record_dial_provider_event(
            db_session,
            organization_id=graph.organization.id,
            provider="twilio",
            external_event_id="event-unverified",
            event_type="call.ringing",
            payload={"CallStatus": "ringing"},
            dial_leg=leg,
            target_status="ringing",
            provider_sequence_number=1,
            occurred_at=base_time - timedelta(seconds=1),
        )
    assert leg.status == "queued"
    assert (
        db_session.scalar(
            select(func.count())
            .select_from(ProspectingProviderEvent)
            .where(ProspectingProviderEvent.external_event_id == "event-unverified")
        )
        == 0
    )

    ringing_event, applied = record_dial_provider_event(
        db_session,
        organization_id=graph.organization.id,
        provider=" Twilio ",
        external_event_id="event-ringing",
        event_type="call.ringing",
        payload={"CallStatus": "ringing"},
        dial_leg=leg,
        target_status="ringing",
        provider_sequence_number=2,
        occurred_at=base_time,
        signature_verified=True,
        signature="valid-test-signature",
    )
    assert applied is True
    assert ringing_event.processing_status == "processed"
    assert leg.status == "ringing"
    assert leg.last_provider_event_sequence == 2
    assert ringing_event.signature_fingerprint is not None
    assert ringing_event.payload_sha256 is not None

    replay, replay_applied = record_dial_provider_event(
        db_session,
        organization_id=graph.organization.id,
        provider="twilio",
        external_event_id="event-ringing",
        event_type="call.connected",
        payload={"CallStatus": "connected"},
        dial_leg=leg,
        target_status="connected",
        provider_sequence_number=3,
        occurred_at=base_time + timedelta(seconds=1),
        signature_verified=True,
    )
    assert replay.id == ringing_event.id
    assert replay_applied is False
    assert leg.status == "ringing"
    assert (
        db_session.scalar(
            select(func.count())
            .select_from(ProspectingProviderEvent)
            .where(
                ProspectingProviderEvent.organization_id == graph.organization.id,
                ProspectingProviderEvent.external_event_id == "event-ringing",
            )
        )
        == 1
    )

    stale_sequence, stale_applied = record_dial_provider_event(
        db_session,
        organization_id=graph.organization.id,
        provider="twilio",
        external_event_id="event-stale-sequence",
        event_type="call.connected",
        payload={},
        dial_leg=leg,
        target_status="connected",
        provider_sequence_number=1,
        occurred_at=base_time + timedelta(seconds=2),
        signature_verified=True,
    )
    assert stale_applied is False
    assert stale_sequence.processing_status == "ignored_stale"

    out_of_order, out_of_order_applied = record_dial_provider_event(
        db_session,
        organization_id=graph.organization.id,
        provider="twilio",
        external_event_id="event-out-of-order",
        event_type="call.connected",
        payload={},
        dial_leg=leg,
        target_status="connected",
        provider_sequence_number=3,
        occurred_at=base_time - timedelta(seconds=1),
        signature_verified=True,
    )
    assert out_of_order_applied is False
    assert out_of_order.processing_status == "ignored_stale"

    regression, regression_applied = record_dial_provider_event(
        db_session,
        organization_id=graph.organization.id,
        provider="twilio",
        external_event_id="event-regression",
        event_type="call.dialing",
        payload={},
        dial_leg=leg,
        target_status="dialing",
        provider_sequence_number=3,
        occurred_at=base_time + timedelta(seconds=3),
        signature_verified=True,
    )
    assert regression_applied is False
    assert regression.processing_status == "ignored_regression"
    assert leg.status == "ringing"

    terminal, terminal_applied = record_dial_provider_event(
        db_session,
        organization_id=graph.organization.id,
        provider="twilio",
        external_event_id="event-completed",
        event_type="call.completed",
        payload={},
        dial_leg=leg,
        target_status="completed",
        provider_sequence_number=4,
        occurred_at=base_time + timedelta(seconds=4),
        signature_verified=True,
    )
    assert terminal_applied is True
    assert terminal.processing_status == "processed"
    assert leg.status == "completed"
    assert leg.completed_at is not None

    after_terminal, after_terminal_applied = record_dial_provider_event(
        db_session,
        organization_id=graph.organization.id,
        provider="twilio",
        external_event_id="event-after-terminal",
        event_type="call.connected",
        payload={},
        dial_leg=leg,
        target_status="connected",
        provider_sequence_number=5,
        occurred_at=base_time + timedelta(seconds=5),
        signature_verified=True,
    )
    assert after_terminal_applied is False
    assert after_terminal.processing_status == "ignored_terminal"
    assert leg.status == "completed"


def test_qualification_uniqueness_and_existing_active_attempt_locks_are_preserved(
    db_session: Session,
    api_db_override: None,
) -> None:
    graph = seed_dialer_graph(db_session)
    first = add_attempt(db_session, graph, entry_index=0, caller=graph.va)

    same_caller = ProspectingAttempt(
        organization_id=graph.organization.id,
        batch_entry_id=graph.entries[1].id,
        prospect_id=graph.prospects[1].id,
        caller_user_id=graph.va.id,
        script_version_id=graph.script.id,
        status="in_progress",
        measurement_metadata={},
        qualification_answers={},
        started_at=datetime.now(UTC),
    )
    assert_integrity_error(db_session, same_caller)
    same_entry = ProspectingAttempt(
        organization_id=graph.organization.id,
        batch_entry_id=graph.entries[0].id,
        prospect_id=graph.prospects[0].id,
        caller_user_id=graph.other_va.id,
        script_version_id=graph.script.id,
        status="in_progress",
        measurement_metadata={},
        qualification_answers={},
        started_at=datetime.now(UTC),
    )
    assert_integrity_error(db_session, same_entry)

    first.status = "completed"
    first.completed_at = datetime.now(UTC)
    db_session.flush()
    replacement = add_attempt(db_session, graph, entry_index=1, caller=graph.va)

    response = ProspectingQualificationResponse(
        organization_id=graph.organization.id,
        attempt_id=replacement.id,
        script_version_id=graph.script.id,
        question_key="motivation",
        state="answered",
        answer_value="Relocating closer to family",
        source="va_entry",
        actor_user_id=graph.va.id,
        is_required=True,
        captured_at=datetime.now(UTC),
        response_metadata={},
    )
    db_session.add(response)
    db_session.flush()
    duplicate_response = ProspectingQualificationResponse(
        organization_id=graph.organization.id,
        attempt_id=replacement.id,
        script_version_id=graph.script.id,
        question_key="motivation",
        state="conflict",
        answer_value="Conflicting answer",
        source="va_entry",
        actor_user_id=graph.va.id,
        is_required=True,
        captured_at=datetime.now(UTC),
        response_metadata={},
    )
    assert_integrity_error(db_session, duplicate_response)

    separate_attempt_response = ProspectingQualificationResponse(
        organization_id=graph.organization.id,
        attempt_id=first.id,
        script_version_id=graph.script.id,
        question_key="motivation",
        state="needs_follow_up",
        answer_value=None,
        source="va_entry",
        actor_user_id=graph.va.id,
        is_required=True,
        captured_at=datetime.now(UTC),
        response_metadata={},
    )
    db_session.add(separate_attempt_response)
    db_session.flush()
    assert separate_attempt_response.id != response.id
