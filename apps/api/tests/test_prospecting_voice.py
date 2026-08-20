from __future__ import annotations

from collections.abc import Iterator, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any, cast
from urllib.parse import urlencode
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from httpx import Response
from pytest import MonkeyPatch
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from twilio.request_validator import RequestValidator  # type: ignore[import-untyped]

from app.core.auth import Principal
from app.core.config import get_settings
from app.integrations.voice_call_provider import (
    VoiceCallProviderError,
    VoiceCallResult,
)
from app.main import app
from app.models.foundation import (
    CallRecord,
    CallRecording,
    CallTranscript,
    Campaign,
    CommunicationRecord,
    Contact,
    Conversation,
    Lead,
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
    ProspectingInboundCallback,
    ProspectingProviderEvent,
    ProspectingScriptVersion,
    Task,
    User,
    VoiceCallIntent,
    VoiceLine,
)
from app.services import prospecting_voice as prospecting_voice_service
from app.services.bootstrap import bootstrap_foundation

OWNER_EMAIL = "d2-voice-owner@example.com"
VA_EMAIL = "d2-voice-va@example.com"
OTHER_VA_EMAIL = "d2-voice-other-va@example.com"
AUTH_TOKEN = "d2-test-voice-auth-token"
ACCOUNT_SID = "AC00000000000000000000000000000000"
API_KEY_SID = "SK00000000000000000000000000000000"
TWIML_APP_SID = "AP00000000000000000000000000000000"
WEBHOOK_BASE_URL = "https://api.stonegate.test"
PROSPECTING_NUMBER = "+16785550101"
PROSPECT_NUMBER = "+14045550101"
FORWARDING_NUMBER = "+14045550999"
ROOT_CALL_SID = "CA00000000000000000000000000000201"
CHILD_CALL_SID = "CA00000000000000000000000000000202"


@pytest.fixture
def prospecting_voice_settings(monkeypatch: MonkeyPatch) -> Iterator[None]:
    values = {
        "PROSPECTING_NATIVE_DIALER_ENABLED": "true",
        "PROSPECTING_NATIVE_DIALER_MAX_LINES": "1",
        "TWILIO_VOICE_ENABLED": "true",
        "TWILIO_ACCOUNT_SID": ACCOUNT_SID,
        "TWILIO_AUTH_TOKEN": AUTH_TOKEN,
        "TWILIO_API_KEY_SID": API_KEY_SID,
        "TWILIO_API_KEY_SECRET": "d2-test-api-key-secret-with-at-least-32-bytes",
        "TWILIO_TWIML_APP_SID": TWIML_APP_SID,
        "TWILIO_WEBHOOK_BASE_URL": WEBHOOK_BASE_URL,
        "TWILIO_VALIDATE_WEBHOOK_SIGNATURES": "true",
        "TWILIO_VOICE_ALLOWED_START_HOUR": "0",
        "TWILIO_VOICE_ALLOWED_END_HOUR": "24",
    }
    for key, value in values.items():
        monkeypatch.setenv(key, value)
    get_settings.cache_clear()
    try:
        yield
    finally:
        get_settings.cache_clear()


@dataclass(frozen=True)
class ColdCallGraph:
    organization: Organization
    owner: User
    caller: User
    other_caller: User
    line: VoiceLine
    prospect: Prospect
    batch: ProspectCallingBatch
    entry: ProspectCallingBatchEntry
    attempt: ProspectingAttempt
    profile: ProspectingDialerProfile
    session: ProspectingDialSession
    leg: ProspectingDialLeg


@dataclass
class FakeVoiceProvider:
    start_result: VoiceCallResult = field(
        default_factory=lambda: VoiceCallResult(sid=ROOT_CALL_SID, status="queued")
    )
    fetch_result: VoiceCallResult | None = None
    cancel_failures_remaining: int = 0
    start_calls: list[dict[str, Any]] = field(default_factory=list)
    fetch_calls: list[str] = field(default_factory=list)
    cancel_calls: list[str] = field(default_factory=list)
    hangup_calls: list[str] = field(default_factory=list)

    def start(
        self,
        *,
        to: str,
        from_number: str,
        twiml: str,
        status_callback: str,
        status_callback_events: Sequence[str] = ("completed",),
    ) -> VoiceCallResult:
        self.start_calls.append(
            {
                "to": to,
                "from_number": from_number,
                "twiml": twiml,
                "status_callback": status_callback,
                "status_callback_events": tuple(status_callback_events),
            }
        )
        return self.start_result

    def fetch(self, call_id: str) -> VoiceCallResult:
        self.fetch_calls.append(call_id)
        return self.fetch_result or self.start_result

    def cancel(self, call_id: str) -> VoiceCallResult:
        self.cancel_calls.append(call_id)
        if self.cancel_failures_remaining:
            self.cancel_failures_remaining -= 1
            raise VoiceCallProviderError("Temporary provider cancel failure.")
        return VoiceCallResult(sid=call_id, status="canceled")

    def hangup(self, call_id: str) -> VoiceCallResult:
        self.hangup_calls.append(call_id)
        return VoiceCallResult(sid=call_id, status="completed")


def test_locked_graph_rejects_changed_d10_pilot_identity(
    db_session: Session,
    api_db_override: None,
    prospecting_voice_settings: None,
    monkeypatch: MonkeyPatch,
) -> None:
    graph = seed_cold_call_graph(db_session, TestClient(app))
    unexpected_pilot_id = UUID("00000000-0000-0000-0000-000000000999")
    monkeypatch.setattr(
        prospecting_voice_service,
        "lock_expected_session_pilot",
        lambda *args, **kwargs: unexpected_pilot_id,
    )
    principal = Principal(
        user_id=graph.caller.id,
        organization_id=graph.organization.id,
        email=graph.caller.email,
        permission_keys=frozenset(),
    )

    with pytest.raises(
        prospecting_voice_service.ProspectingVoiceConflictError,
        match="authorization changed",
    ):
        prospecting_voice_service.load_authorized_graph(
            db_session,
            principal,
            graph.leg.id,
            lock=True,
        )


class FailingStartProvider(FakeVoiceProvider):
    def start(
        self,
        *,
        to: str,
        from_number: str,
        twiml: str,
        status_callback: str,
        status_callback_events: Sequence[str] = ("completed",),
    ) -> VoiceCallResult:
        raise VoiceCallProviderError("Temporary provider start failure.")


def create_user(
    client: TestClient,
    headers: dict[str, str],
    *,
    email: str,
    name: str,
) -> UUID:
    response = client.post(
        "/api/v1/operations/users",
        headers=headers,
        json={
            "email": email,
            "display_name": name,
            "role_key": "prospecting_caller",
            "calling_enabled": True,
        },
    )
    assert response.status_code == 201, response.text
    return UUID(response.json()["id"])


def seed_cold_call_graph(db: Session, client: TestClient) -> ColdCallGraph:
    foundation = bootstrap_foundation(
        db,
        organization_name="D2 Voice Test Workspace",
        admin_email=OWNER_EMAIL,
        admin_name="D2 Voice Owner",
    )
    assert foundation.admin_user is not None
    foundation.organization.prospecting_dialer_enabled = True
    # D2-D8 voice tests isolate provider/callback behavior. D10 acceptance is
    # covered by its dedicated suite and remains fail-closed by default.
    foundation.organization.prospecting_dialer_acceptance_required = False
    owner_headers = {"X-Dev-User-Email": OWNER_EMAIL}
    caller_id = create_user(
        client,
        owner_headers,
        email=VA_EMAIL,
        name="D2 Voice Caller",
    )
    other_caller_id = create_user(
        client,
        owner_headers,
        email=OTHER_VA_EMAIL,
        name="D2 Other Voice Caller",
    )
    caller = db.get(User, caller_id)
    other_caller = db.get(User, other_caller_id)
    assert caller is not None
    assert other_caller is not None
    caller.voice_forwarding_number = FORWARDING_NUMBER
    caller.voice_forwarding_enabled = True

    market = Market(
        organization_id=foundation.organization.id,
        name="D2 Atlanta Voice",
        code="d2-atlanta-voice",
        state_code="GA",
        timezone="America/New_York",
        status="active",
        is_primary=True,
    )
    db.add(market)
    db.flush()
    campaign = Campaign(
        organization_id=foundation.organization.id,
        market_id=market.id,
        owner_user_id=foundation.admin_user.id,
        name="D2 Controlled Calling",
        code="d2-controlled-calling",
        channel="cold_call",
        asset_class="house",
        status="active",
        prospecting_dialer_enabled=True,
        prospecting_dialer_max_concurrent_legs=1,
    )
    line = VoiceLine(
        organization_id=foundation.organization.id,
        provider="twilio",
        phone_number=PROSPECTING_NUMBER,
        label="D2 prospecting outbound",
        department_key="acquisitions",
        purpose_key="prospecting_outbound",
        assigned_user_id=caller.id,
        status="active",
        is_default=False,
        inbound_route="conversation_owner",
        ring_strategy="simultaneous",
        coverage_timezone="America/New_York",
        coverage_start_hour=0,
        coverage_end_hour=24,
        prospecting_dialer_max_concurrent_legs=1,
        missed_call_action="fallback_then_voicemail",
        line_metadata={},
    )
    db.add_all([campaign, line])
    db.flush()
    prospect = Prospect(
        organization_id=foundation.organization.id,
        campaign_id=campaign.id,
        assigned_user_id=caller.id,
        source_record_key="d2-controlled-prospect",
        status="ready",
        legal_name="D2 Cold Prospect",
        phone=PROSPECT_NUMBER,
        normalized_phone=PROSPECT_NUMBER,
        street_address="101 Dialer Way",
        city="Atlanta",
        state_code="GA",
        postal_code="30303",
        suppression_status="clear",
        phone_validation_status="verified",
        call_eligibility="eligible",
        source_payload={},
    )
    batch = ProspectCallingBatch(
        organization_id=foundation.organization.id,
        campaign_id=campaign.id,
        assigned_user_id=caller.id,
        created_by_user_id=foundation.admin_user.id,
        name="D2 Controlled Queue",
        status="active",
        dialer_mode="one_line_power",
    )
    db.add_all([prospect, batch])
    db.flush()
    entry = ProspectCallingBatchEntry(
        organization_id=foundation.organization.id,
        prospect_calling_batch_id=batch.id,
        prospect_id=prospect.id,
        assigned_user_id=caller.id,
        sequence_number=1,
        status="in_progress",
        attempt_count=1,
    )
    script = ProspectingScriptVersion(
        organization_id=foundation.organization.id,
        version_number=1,
        title="D2 Controlled Script",
        status="approved",
        opening_script="Hello, I am calling about your property.",
        qualification_questions=[],
        disposition_rules={},
        created_by_user_id=foundation.admin_user.id,
        approved_by_user_id=foundation.admin_user.id,
        approved_at=datetime.now(UTC),
    )
    profile = ProspectingDialerProfile(
        organization_id=foundation.organization.id,
        user_id=caller.id,
        voice_line_id=line.id,
        status="active",
        default_line_count=1,
        max_line_count=1,
        recording_policy="company_policy",
        profile_metadata={},
        created_by_user_id=foundation.admin_user.id,
        updated_by_user_id=foundation.admin_user.id,
    )
    db.add_all([entry, script, profile])
    db.flush()
    now = datetime.now(UTC)
    cohort = ProspectingCohort(
        organization_id=foundation.organization.id,
        campaign_id=campaign.id,
        script_version_id=script.id,
        created_by_user_id=foundation.admin_user.id,
        name="D2 Controlled Cohort",
        code="d2-controlled-cohort",
        status="active",
        source_name="D2 test data",
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
    db.add(cohort)
    db.flush()
    batch.cohort_id = cohort.id
    attempt = ProspectingAttempt(
        organization_id=foundation.organization.id,
        batch_entry_id=entry.id,
        prospect_id=prospect.id,
        caller_user_id=caller.id,
        script_version_id=script.id,
        status="in_progress",
        measurement_metadata={},
        qualification_answers={},
        started_at=datetime.now(UTC),
    )
    db.add(attempt)
    db.flush()
    session = ProspectingDialSession(
        organization_id=foundation.organization.id,
        dialer_profile_id=profile.id,
        caller_user_id=caller.id,
        campaign_id=campaign.id,
        cohort_id=cohort.id,
        prospect_calling_batch_id=batch.id,
        voice_line_id=line.id,
        current_prospect_id=prospect.id,
        current_batch_entry_id=entry.id,
        current_attempt_id=attempt.id,
        state="ready",
        requested_line_count=1,
        effective_line_count=1,
        organization_line_limit=1,
        va_line_limit=1,
        campaign_line_limit=1,
        voice_line_limit=1,
        feature_line_limit=1,
        idempotency_key="d2-controlled-session",
        browser_session_id="d2-controlled-browser",
        lease_token="d2-controlled-lease-token-xxxxxxxx",
        lease_expires_at=datetime.now(UTC) + timedelta(minutes=5),
        started_at=datetime.now(UTC),
        heartbeat_at=datetime.now(UTC),
        recovery_metadata={},
        session_metadata={},
        created_by_user_id=caller.id,
    )
    db.add(session)
    db.flush()
    leg = ProspectingDialLeg(
        organization_id=foundation.organization.id,
        dial_session_id=session.id,
        prospect_id=prospect.id,
        batch_entry_id=entry.id,
        attempt_id=attempt.id,
        voice_line_id=line.id,
        line_slot=1,
        recipient=PROSPECT_NUMBER,
        provider="twilio",
        provider_call_id=None,
        idempotency_key="d2-controlled-leg",
        status="queued",
        last_provider_event_sequence=0,
        queued_at=datetime.now(UTC),
        answer_classification="unknown",
        party_classification="unknown",
        leg_metadata={},
    )
    db.add(leg)
    db.commit()
    return ColdCallGraph(
        organization=foundation.organization,
        owner=foundation.admin_user,
        caller=caller,
        other_caller=other_caller,
        line=line,
        prospect=prospect,
        batch=batch,
        entry=entry,
        attempt=attempt,
        profile=profile,
        session=session,
        leg=leg,
    )


def signed_headers(path: str, payload: dict[str, str]) -> dict[str, str]:
    signature = RequestValidator(AUTH_TOKEN).compute_signature(
        f"{WEBHOOK_BASE_URL}{path}",
        payload,
    )
    return {
        "Content-Type": "application/x-www-form-urlencoded",
        "X-Twilio-Signature": signature,
    }


def post_signed(client: TestClient, path: str, payload: dict[str, str]) -> Response:
    return cast(
        Response,
        client.post(
            path,
            content=urlencode(payload),
            headers=signed_headers(path, payload),
        ),
    )


def attach_exact_dialed_number_evidence(
    db: Session,
    graph: ColdCallGraph,
    *,
    attempt: ProspectingAttempt | None = None,
    leg: ProspectingDialLeg | None = None,
    provider_call_id: str,
    child_provider_call_id: str,
) -> CallRecord:
    selected_attempt = attempt or graph.attempt
    selected_leg = leg or graph.leg
    call = CallRecord(
        organization_id=graph.organization.id,
        conversation_id=None,
        lead_id=None,
        contact_id=None,
        prospect_id=selected_attempt.prospect_id,
        prospecting_attempt_id=selected_attempt.id,
        prospecting_dial_leg_id=selected_leg.id,
        prospecting_inbound_callback_id=None,
        actor_user_id=selected_attempt.caller_user_id,
        communication_record_id=None,
        voice_line_id=graph.line.id,
        call_intent_id=None,
        provider="twilio",
        provider_call_id=provider_call_id,
        child_provider_call_id=child_provider_call_id,
        direction="outbound",
        status="completed",
        from_number=PROSPECTING_NUMBER,
        to_number=PROSPECT_NUMBER,
        started_at=selected_attempt.started_at,
        answered_at=None,
        ended_at=datetime.now(UTC),
        duration_seconds=0,
        disposition="no_answer",
        recording_consent_status="not_requested",
        call_metadata={"source": "controlled_d8_callback_match_test"},
    )
    db.add(call)
    db.flush()
    selected_attempt.call_record_id = call.id
    selected_attempt.provider = "twilio"
    selected_attempt.provider_call_id = provider_call_id
    selected_leg.call_record_id = call.id
    selected_leg.provider_call_id = provider_call_id
    return call


def start_call(
    client: TestClient,
    graph: ColdCallGraph,
    monkeypatch: MonkeyPatch,
    provider: FakeVoiceProvider,
    *,
    idempotency_key: str = "d2-call-request-0001",
) -> Response:
    monkeypatch.setattr(
        "app.services.prospecting_voice.get_twilio_voice_call_provider",
        lambda: provider,
    )
    return cast(
        Response,
        client.post(
            f"/api/v1/prospecting/dialer/legs/{graph.leg.id}/call",
            headers={"X-Dev-User-Email": VA_EMAIL},
            json={
                "idempotency_key": idempotency_key,
                "browser_session_id": graph.session.browser_session_id,
                "lease_token": graph.session.lease_token,
            },
        ),
    )


def browser_lease_payload(graph: ColdCallGraph) -> dict[str, str]:
    assert graph.session.browser_session_id is not None
    assert graph.session.lease_token is not None
    return {
        "browser_session_id": graph.session.browser_session_id,
        "lease_token": graph.session.lease_token,
    }


def assert_private_no_store(response: Response) -> None:
    directives = {
        directive.strip().lower()
        for directive in response.headers.get("cache-control", "").split(",")
        if directive.strip()
    }
    assert {"private", "no-store"}.issubset(directives)


def prepare_browser_call(
    client: TestClient,
    graph: ColdCallGraph,
    *,
    idempotency_key: str = "d4-browser-call-request-0001",
) -> Response:
    return cast(
        Response,
        client.post(
            f"/api/v1/prospecting/dialer/legs/{graph.leg.id}/browser-call",
            headers={"X-Dev-User-Email": VA_EMAIL},
            json={
                **browser_lease_payload(graph),
                "idempotency_key": idempotency_key,
            },
        ),
    )


def test_browser_voice_session_is_lease_bound_dedicated_and_not_cached(
    db_session: Session,
    api_db_override: None,
    prospecting_voice_settings: None,
) -> None:
    client = TestClient(app)
    graph = seed_cold_call_graph(db_session, client)
    path = f"/api/v1/prospecting/dialer/sessions/{graph.session.id}/voice-session"

    response = client.post(
        path,
        headers={"X-Dev-User-Email": VA_EMAIL},
        json=browser_lease_payload(graph),
    )

    assert response.status_code == 200, response.text
    assert_private_no_store(response)
    body = response.json()
    assert body["can_initialize"] is True
    assert body["token"]
    assert body["expires_at"]
    assert body["dial_session_id"] == str(graph.session.id)
    assert body["effective_line_count"] == 1
    assert body["line"] == {
        "id": str(graph.line.id),
        "phone_number": PROSPECTING_NUMBER,
        "label": "D2 prospecting outbound",
        "provider": "twilio",
        "status": "active",
        "department_key": "acquisitions",
        "purpose_key": "prospecting_outbound",
    }
    assert body["identity"].startswith(f"stonegate_p_{graph.caller.id.hex}_")

    stale = client.post(
        path,
        headers={"X-Dev-User-Email": VA_EMAIL},
        json={
            "browser_session_id": graph.session.browser_session_id,
            "lease_token": "stale-d4-lease-token-xxxxxxxxxxxxx",
        },
    )
    assert stale.status_code == 409

    wrong_user = client.post(
        path,
        headers={"X-Dev-User-Email": OTHER_VA_EMAIL},
        json=browser_lease_payload(graph),
    )
    assert wrong_user.status_code == 403


def test_all_lease_or_jwt_session_responses_are_private_and_not_cached(
    db_session: Session,
    api_db_override: None,
    prospecting_voice_settings: None,
) -> None:
    client = TestClient(app)
    graph = seed_cold_call_graph(db_session, client)
    headers = {"X-Dev-User-Email": VA_EMAIL}
    lease = browser_lease_payload(graph)
    start = client.post(
        "/api/v1/prospecting/dialer/sessions",
        headers=headers,
        json={
            "campaign_id": str(graph.prospect.campaign_id),
            "cohort_id": str(graph.session.cohort_id),
            "calling_batch_id": str(graph.batch.id),
            "browser_session_id": graph.session.browser_session_id,
            "idempotency_key": graph.session.idempotency_key,
            "requested_line_count": 1,
        },
    )
    assert start.status_code == 201, start.text
    assert_private_no_store(start)

    session_path = f"/api/v1/prospecting/dialer/sessions/{graph.session.id}"
    for action in ("heartbeat", "pause", "resume", "reserve-next"):
        controlled = client.post(
            f"{session_path}/{action}",
            headers=headers,
            json=lease,
        )
        assert controlled.status_code == 200, controlled.text
        assert_private_no_store(controlled)

    voice_session = client.post(
        f"{session_path}/voice-session",
        headers=headers,
        json=lease,
    )
    assert voice_session.status_code == 200, voice_session.text
    assert_private_no_store(voice_session)

    previous_browser = graph.session.browser_session_id
    graph.session.lease_expires_at = datetime.now(UTC) - timedelta(seconds=1)
    db_session.commit()
    recovered = client.post(
        f"{session_path}/recover",
        headers=headers,
        json={
            "previous_browser_session_id": previous_browser,
            "new_browser_session_id": "d4-cache-recovered-browser",
            "lease_token": lease["lease_token"],
        },
    )
    assert recovered.status_code == 200, recovered.text
    assert_private_no_store(recovered)
    recovered_lease = {
        "browser_session_id": "d4-cache-recovered-browser",
        "lease_token": recovered.json()["lease_token"],
    }
    ended = client.post(
        f"{session_path}/end",
        headers=headers,
        json={**recovered_lease, "reason": "Controlled cache acceptance ended."},
    )
    assert ended.status_code == 200, ended.text
    assert_private_no_store(ended)


def test_recover_exact_replay_returns_same_lease_after_lost_response(
    db_session: Session,
    api_db_override: None,
    prospecting_voice_settings: None,
) -> None:
    client = TestClient(app)
    graph = seed_cold_call_graph(db_session, client)
    old_browser_session_id = graph.session.browser_session_id
    old_lease_token = graph.session.lease_token
    assert old_browser_session_id is not None
    assert old_lease_token is not None
    graph.session.lease_expires_at = datetime.now(UTC) - timedelta(seconds=1)
    db_session.commit()
    path = f"/api/v1/prospecting/dialer/sessions/{graph.session.id}/recover"
    payload = {
        "previous_browser_session_id": old_browser_session_id,
        "new_browser_session_id": "d4-response-loss-recovered-browser",
        "lease_token": old_lease_token,
    }

    first = client.post(
        path,
        headers={"X-Dev-User-Email": VA_EMAIL},
        json=payload,
    )
    replay = client.post(
        path,
        headers={"X-Dev-User-Email": VA_EMAIL},
        json=payload,
    )

    assert first.status_code == 200, first.text
    assert replay.status_code == 200, replay.text
    assert first.json()["replayed"] is False
    assert replay.json()["replayed"] is True
    assert replay.json()["lease_token"] == first.json()["lease_token"]
    assert (
        replay.json()["snapshot"]["session"]["lease_expires_at"]
        == first.json()["snapshot"]["session"]["lease_expires_at"]
    )
    assert_private_no_store(first)
    assert_private_no_store(replay)
    db_session.expire_all()
    session = db_session.get(ProspectingDialSession, graph.session.id)
    assert session is not None
    recovery = session.recovery_metadata
    assert recovery["recovery_digest_version"] == "hmac-sha256-v1"
    assert recovery["previous_browser_session_id"] == old_browser_session_id
    assert recovery["recovered_browser_session_id"] == payload["new_browser_session_id"]
    assert isinstance(recovery["recovered_at"], str)
    assert len(recovery["previous_lease_token_digest"]) == 64
    assert all(old_lease_token not in str(value) for value in recovery.values())


@pytest.mark.parametrize(
    ("changed_field", "changed_value"),
    [
        ("lease_token", "different-old-lease-token-xxxxxxxxxxxxxxxx"),
        ("previous_browser_session_id", "different-previous-browser"),
        ("new_browser_session_id", "different-recovered-browser"),
    ],
)
def test_recover_replay_rejects_changed_request_credentials(
    db_session: Session,
    api_db_override: None,
    prospecting_voice_settings: None,
    changed_field: str,
    changed_value: str,
) -> None:
    client = TestClient(app)
    graph = seed_cold_call_graph(db_session, client)
    old_browser_session_id = graph.session.browser_session_id
    old_lease_token = graph.session.lease_token
    assert old_browser_session_id is not None
    assert old_lease_token is not None
    graph.session.lease_expires_at = datetime.now(UTC) - timedelta(seconds=1)
    db_session.commit()
    path = f"/api/v1/prospecting/dialer/sessions/{graph.session.id}/recover"
    payload = {
        "previous_browser_session_id": old_browser_session_id,
        "new_browser_session_id": "d4-response-loss-recovered-browser",
        "lease_token": old_lease_token,
    }
    first = client.post(
        path,
        headers={"X-Dev-User-Email": VA_EMAIL},
        json=payload,
    )
    assert first.status_code == 200, first.text
    rotated_lease_token = first.json()["lease_token"]
    changed_payload = {**payload, changed_field: changed_value}

    rejected = client.post(
        path,
        headers={"X-Dev-User-Email": VA_EMAIL},
        json=changed_payload,
    )

    assert rejected.status_code == 409, rejected.text
    db_session.expire_all()
    session = db_session.get(ProspectingDialSession, graph.session.id)
    assert session is not None
    assert session.lease_token == rotated_lease_token
    assert session.browser_session_id == payload["new_browser_session_id"]


def test_browser_call_prepare_is_idempotent_and_device_connects_without_fake_crm_records(
    db_session: Session,
    api_db_override: None,
    prospecting_voice_settings: None,
) -> None:
    client = TestClient(app)
    graph = seed_cold_call_graph(db_session, client)
    voice_session = client.post(
        f"/api/v1/prospecting/dialer/sessions/{graph.session.id}/voice-session",
        headers={"X-Dev-User-Email": VA_EMAIL},
        json=browser_lease_payload(graph),
    ).json()

    prepared = prepare_browser_call(client, graph)
    replayed = prepare_browser_call(client, graph)

    assert prepared.status_code == 201, prepared.text
    assert replayed.status_code == 201, replayed.text
    body = prepared.json()
    assert body["control_action"] == "prepared"
    assert body["provider_call_id"] is None
    assert body["provider_status"] == "queued"
    assert body["leg"]["status"] == "queued"
    assert replayed.json()["control_action"] == "replayed"
    assert replayed.json()["call_intent_id"] == body["call_intent_id"]
    assert db_session.scalar(select(func.count()).select_from(VoiceCallIntent)) == 1
    assert db_session.scalar(select(func.count()).select_from(CallRecord)) == 1

    path = "/api/v1/webhooks/twilio/voice/outbound"
    outbound = post_signed(
        client,
        path,
        {
            "From": f"client:{voice_session['identity']}",
            "CallSid": ROOT_CALL_SID,
            "CallStatus": "initiated",
            "CallIntentId": body["call_intent_id"],
        },
    )
    duplicate = post_signed(
        client,
        path,
        {
            "From": f"client:{voice_session['identity']}",
            "CallSid": ROOT_CALL_SID,
            "CallStatus": "initiated",
            "CallIntentId": body["call_intent_id"],
        },
    )

    assert outbound.status_code == 200, outbound.text
    assert duplicate.status_code == 200, duplicate.text
    assert f'callerId="{PROSPECTING_NUMBER}"' in outbound.text
    assert PROSPECT_NUMBER in outbound.text
    db_session.expire_all()
    call = db_session.get(CallRecord, UUID(body["call_record_id"]))
    intent = db_session.get(VoiceCallIntent, UUID(body["call_intent_id"]))
    leg = db_session.get(ProspectingDialLeg, graph.leg.id)
    session = db_session.get(ProspectingDialSession, graph.session.id)
    assert call is not None and call.provider_call_id == ROOT_CALL_SID
    assert call.call_metadata["bridge"] == "browser_softphone"
    assert intent is not None and intent.provider_call_id == ROOT_CALL_SID
    assert intent.status == "started"
    assert leg is not None and leg.provider_call_id == ROOT_CALL_SID
    assert leg.status == "dialing"
    assert session is not None and session.state == "dialing"
    assert db_session.scalar(select(func.count()).select_from(Contact)) == 0
    assert db_session.scalar(select(func.count()).select_from(Conversation)) == 0
    assert db_session.scalar(select(func.count()).select_from(CommunicationRecord)) == 0


def test_browser_fetch_never_treats_root_in_progress_as_seller_connected(
    db_session: Session,
    api_db_override: None,
    prospecting_voice_settings: None,
    monkeypatch: MonkeyPatch,
) -> None:
    client = TestClient(app)
    graph = seed_cold_call_graph(db_session, client)
    voice_session = client.post(
        f"/api/v1/prospecting/dialer/sessions/{graph.session.id}/voice-session",
        headers={"X-Dev-User-Email": VA_EMAIL},
        json=browser_lease_payload(graph),
    ).json()
    prepared = prepare_browser_call(client, graph).json()
    outbound = post_signed(
        client,
        "/api/v1/webhooks/twilio/voice/outbound",
        {
            "From": f"client:{voice_session['identity']}",
            "CallSid": ROOT_CALL_SID,
            "CallStatus": "in-progress",
            "CallIntentId": prepared["call_intent_id"],
        },
    )
    assert outbound.status_code == 200, outbound.text
    provider = FakeVoiceProvider(
        fetch_result=VoiceCallResult(sid=ROOT_CALL_SID, status="in-progress")
    )
    monkeypatch.setattr(
        "app.services.prospecting_voice.get_twilio_voice_call_provider",
        lambda: provider,
    )

    refreshed = client.get(
        f"/api/v1/prospecting/dialer/legs/{graph.leg.id}/call",
        headers={"X-Dev-User-Email": VA_EMAIL},
    )

    assert refreshed.status_code == 200, refreshed.text
    assert refreshed.json()["control_action"] == "replayed"
    assert refreshed.json()["leg"]["status"] == "dialing"
    assert provider.fetch_calls == []


def test_browser_prepare_retry_and_pre_provider_cancel_are_idempotent_and_endable(
    db_session: Session,
    api_db_override: None,
    prospecting_voice_settings: None,
    monkeypatch: MonkeyPatch,
) -> None:
    client = TestClient(app)
    graph = seed_cold_call_graph(db_session, client)
    provider = FakeVoiceProvider()
    monkeypatch.setattr(
        "app.services.prospecting_voice.get_twilio_voice_call_provider",
        lambda: provider,
    )
    prepared = prepare_browser_call(client, graph)
    retried = prepare_browser_call(client, graph)
    assert prepared.status_code == 201, prepared.text
    assert retried.status_code == 201, retried.text
    assert retried.json()["control_action"] == "replayed"
    assert retried.json()["call_intent_id"] == prepared.json()["call_intent_id"]

    path = f"/api/v1/prospecting/dialer/legs/{graph.leg.id}/call/cancel"
    payload = {
        **browser_lease_payload(graph),
        "reason": "Browser could not connect before Twilio started.",
    }
    cancelled = client.post(path, headers={"X-Dev-User-Email": VA_EMAIL}, json=payload)
    replayed = client.post(path, headers={"X-Dev-User-Email": VA_EMAIL}, json=payload)

    assert cancelled.status_code == 200, cancelled.text
    assert cancelled.json()["control_action"] == "cancelled"
    assert cancelled.json()["leg"]["status"] == "cancelled"
    assert replayed.status_code == 200, replayed.text
    assert replayed.json()["control_action"] == "replayed"
    assert provider.cancel_calls == []
    assert provider.hangup_calls == []

    db_session.expire_all()
    intent = db_session.get(VoiceCallIntent, UUID(prepared.json()["call_intent_id"]))
    call = db_session.get(CallRecord, UUID(prepared.json()["call_record_id"]))
    attempt = db_session.get(ProspectingAttempt, graph.attempt.id)
    session = db_session.get(ProspectingDialSession, graph.session.id)
    assert intent is not None and intent.status == "cancelled"
    assert call is not None and call.status == "cancelled"
    assert attempt is not None and attempt.status == "cancelled"
    assert session is not None
    assert session.state == "ready"
    assert session.current_attempt_id is None

    ended = client.post(
        f"/api/v1/prospecting/dialer/sessions/{graph.session.id}/end",
        headers={"X-Dev-User-Email": VA_EMAIL},
        json={**browser_lease_payload(graph), "reason": "Controlled shift ended."},
    )
    assert ended.status_code == 200, ended.text
    assert ended.json()["snapshot"]["session"]["state"] == "ended"


def test_fetch_expires_untouched_browser_call_without_contacting_provider(
    db_session: Session,
    api_db_override: None,
    prospecting_voice_settings: None,
    monkeypatch: MonkeyPatch,
) -> None:
    client = TestClient(app)
    graph = seed_cold_call_graph(db_session, client)
    provider = FakeVoiceProvider()
    monkeypatch.setattr(
        "app.services.prospecting_voice.get_twilio_voice_call_provider",
        lambda: provider,
    )
    prepared = prepare_browser_call(client, graph)
    assert prepared.status_code == 201, prepared.text
    intent = db_session.get(VoiceCallIntent, UUID(prepared.json()["call_intent_id"]))
    assert intent is not None
    intent.expires_at = datetime.now(UTC) - timedelta(seconds=1)
    db_session.commit()

    refreshed = client.get(
        f"/api/v1/prospecting/dialer/legs/{graph.leg.id}/call",
        headers={"X-Dev-User-Email": VA_EMAIL},
    )

    assert refreshed.status_code == 200, refreshed.text
    assert refreshed.json()["control_action"] == "fetched"
    assert refreshed.json()["provider_status"] == "failed"
    assert refreshed.json()["leg"]["status"] == "cancelled"
    assert provider.fetch_calls == []
    db_session.expire_all()
    session = db_session.get(ProspectingDialSession, graph.session.id)
    db_session.refresh(intent)
    assert intent.status == "expired"
    assert session is not None
    assert session.state == "ready"
    assert session.current_attempt_id is None


def test_browser_stop_ringing_cancels_contact_child_not_browser_root(
    db_session: Session,
    api_db_override: None,
    prospecting_voice_settings: None,
    monkeypatch: MonkeyPatch,
) -> None:
    client = TestClient(app)
    graph = seed_cold_call_graph(db_session, client)
    voice_session = client.post(
        f"/api/v1/prospecting/dialer/sessions/{graph.session.id}/voice-session",
        headers={"X-Dev-User-Email": VA_EMAIL},
        json=browser_lease_payload(graph),
    ).json()
    prepared = prepare_browser_call(client, graph).json()
    assert post_signed(
        client,
        "/api/v1/webhooks/twilio/voice/outbound",
        {
            "From": f"client:{voice_session['identity']}",
            "CallSid": ROOT_CALL_SID,
            "CallStatus": "initiated",
            "CallIntentId": prepared["call_intent_id"],
        },
    ).status_code == 200
    status_path = (
        f"/api/v1/webhooks/twilio/voice/status?intent_id={prepared['call_intent_id']}"
    )
    ringing = post_signed(
        client,
        status_path,
        {
            "CallSid": CHILD_CALL_SID,
            "ParentCallSid": ROOT_CALL_SID,
            "CallStatus": "ringing",
        },
    )
    assert ringing.status_code == 204, ringing.text
    provider = FakeVoiceProvider()
    monkeypatch.setattr(
        "app.services.prospecting_voice.get_twilio_voice_call_provider",
        lambda: provider,
    )

    stopped = client.post(
        f"/api/v1/prospecting/dialer/legs/{graph.leg.id}/call/cancel",
        headers={"X-Dev-User-Email": VA_EMAIL},
        json={
            **browser_lease_payload(graph),
            "reason": "Operator stopped ringing",
        },
    )

    assert stopped.status_code == 200, stopped.text
    assert stopped.json()["leg"]["status"] == "cancelled"
    assert provider.cancel_calls == [CHILD_CALL_SID]
    assert provider.hangup_calls == []


def test_browser_stop_before_child_callback_safely_terminates_root(
    db_session: Session,
    api_db_override: None,
    prospecting_voice_settings: None,
    monkeypatch: MonkeyPatch,
) -> None:
    client = TestClient(app)
    graph = seed_cold_call_graph(db_session, client)
    voice_session = client.post(
        f"/api/v1/prospecting/dialer/sessions/{graph.session.id}/voice-session",
        headers={"X-Dev-User-Email": VA_EMAIL},
        json=browser_lease_payload(graph),
    ).json()
    prepared = prepare_browser_call(client, graph).json()
    assert post_signed(
        client,
        "/api/v1/webhooks/twilio/voice/outbound",
        {
            "From": f"client:{voice_session['identity']}",
            "CallSid": ROOT_CALL_SID,
            "CallStatus": "initiated",
            "CallIntentId": prepared["call_intent_id"],
        },
    ).status_code == 200
    provider = FakeVoiceProvider()
    monkeypatch.setattr(
        "app.services.prospecting_voice.get_twilio_voice_call_provider",
        lambda: provider,
    )

    stopped = client.post(
        f"/api/v1/prospecting/dialer/legs/{graph.leg.id}/call/cancel",
        headers={"X-Dev-User-Email": VA_EMAIL},
        json={
            **browser_lease_payload(graph),
            "reason": "Operator stopped before seller leg appeared",
        },
    )

    assert stopped.status_code == 200, stopped.text
    assert stopped.json()["leg"]["status"] == "cancelled"
    assert provider.cancel_calls == []
    assert provider.hangup_calls == [ROOT_CALL_SID]


def test_browser_stop_accepts_root_result_when_child_attaches_during_provider_call(
    db_session: Session,
    api_db_override: None,
    prospecting_voice_settings: None,
    monkeypatch: MonkeyPatch,
) -> None:
    client = TestClient(app)
    graph = seed_cold_call_graph(db_session, client)
    voice_session = client.post(
        f"/api/v1/prospecting/dialer/sessions/{graph.session.id}/voice-session",
        headers={"X-Dev-User-Email": VA_EMAIL},
        json=browser_lease_payload(graph),
    ).json()
    prepared = prepare_browser_call(client, graph).json()
    assert post_signed(
        client,
        "/api/v1/webhooks/twilio/voice/outbound",
        {
            "From": f"client:{voice_session['identity']}",
            "CallSid": ROOT_CALL_SID,
            "CallStatus": "initiated",
            "CallIntentId": prepared["call_intent_id"],
        },
    ).status_code == 200
    status_path = (
        f"/api/v1/webhooks/twilio/voice/status?intent_id={prepared['call_intent_id']}"
    )
    provider = FakeVoiceProvider()

    def hangup_after_child_attaches(call_id: str) -> VoiceCallResult:
        provider.hangup_calls.append(call_id)
        child_ringing = post_signed(
            client,
            status_path,
            {
                "CallSid": CHILD_CALL_SID,
                "ParentCallSid": ROOT_CALL_SID,
                "CallStatus": "ringing",
            },
        )
        assert child_ringing.status_code == 204, child_ringing.text
        return VoiceCallResult(sid=call_id, status="completed")

    monkeypatch.setattr(provider, "hangup", hangup_after_child_attaches)
    monkeypatch.setattr(
        "app.services.prospecting_voice.get_twilio_voice_call_provider",
        lambda: provider,
    )

    stopped = client.post(
        f"/api/v1/prospecting/dialer/legs/{graph.leg.id}/call/cancel",
        headers={"X-Dev-User-Email": VA_EMAIL},
        json={
            **browser_lease_payload(graph),
            "reason": "Operator stopped while the seller leg was attaching",
        },
    )

    assert stopped.status_code == 200, stopped.text
    assert stopped.json()["leg"]["status"] == "cancelled"
    assert provider.cancel_calls == []
    assert provider.hangup_calls == [ROOT_CALL_SID]
    db_session.expire_all()
    call = db_session.get(CallRecord, UUID(prepared["call_record_id"]))
    assert call is not None
    assert call.provider_call_id == ROOT_CALL_SID
    assert call.child_provider_call_id == CHILD_CALL_SID


def test_recovered_browser_lease_invalidates_prepared_voice_identity(
    db_session: Session,
    api_db_override: None,
    prospecting_voice_settings: None,
) -> None:
    client = TestClient(app)
    graph = seed_cold_call_graph(db_session, client)
    voice_session = client.post(
        f"/api/v1/prospecting/dialer/sessions/{graph.session.id}/voice-session",
        headers={"X-Dev-User-Email": VA_EMAIL},
        json=browser_lease_payload(graph),
    ).json()
    prepared = prepare_browser_call(client, graph).json()
    graph.session.browser_session_id = "d4-recovered-browser-session"
    graph.session.lease_token = "d4-recovered-lease-token-xxxxxxxxx"
    graph.session.lease_expires_at = datetime.now(UTC) + timedelta(minutes=5)
    db_session.commit()

    outbound = post_signed(
        client,
        "/api/v1/webhooks/twilio/voice/outbound",
        {
            "From": f"client:{voice_session['identity']}",
            "CallSid": ROOT_CALL_SID,
            "CallStatus": "initiated",
            "CallIntentId": prepared["call_intent_id"],
        },
    )

    assert outbound.status_code == 422
    assert "stale browser session" in outbound.json()["detail"].lower()
    db_session.expire_all()
    call = db_session.get(CallRecord, UUID(prepared["call_record_id"]))
    leg = db_session.get(ProspectingDialLeg, graph.leg.id)
    assert call is not None and call.provider_call_id is None
    assert leg is not None and leg.provider_call_id is None
    assert leg.status == "queued"

    recovered_lease = {
        "browser_session_id": "d4-recovered-browser-session",
        "lease_token": "d4-recovered-lease-token-xxxxxxxxx",
    }
    recovered_voice_session = client.post(
        f"/api/v1/prospecting/dialer/sessions/{graph.session.id}/voice-session",
        headers={"X-Dev-User-Email": VA_EMAIL},
        json=recovered_lease,
    )
    rebound = client.post(
        f"/api/v1/prospecting/dialer/legs/{graph.leg.id}/browser-call",
        headers={"X-Dev-User-Email": VA_EMAIL},
        json={
            **recovered_lease,
            "idempotency_key": "d4-browser-call-request-0001",
        },
    )
    assert recovered_voice_session.status_code == 200, recovered_voice_session.text
    assert rebound.status_code == 201, rebound.text
    assert rebound.json()["control_action"] == "replayed"
    assert rebound.json()["call_intent_id"] == prepared["call_intent_id"]

    replaced_identity = post_signed(
        client,
        "/api/v1/webhooks/twilio/voice/outbound",
        {
            "From": f"client:{voice_session['identity']}",
            "CallSid": ROOT_CALL_SID,
            "CallStatus": "initiated",
            "CallIntentId": prepared["call_intent_id"],
        },
    )
    assert replaced_identity.status_code == 403

    recovered_outbound = post_signed(
        client,
        "/api/v1/webhooks/twilio/voice/outbound",
        {
            "From": f"client:{recovered_voice_session.json()['identity']}",
            "CallSid": ROOT_CALL_SID,
            "CallStatus": "initiated",
            "CallIntentId": prepared["call_intent_id"],
        },
    )
    assert recovered_outbound.status_code == 200, recovered_outbound.text


def test_controlled_cold_start_and_signed_lifecycle_do_not_make_warm_crm_records(
    db_session: Session,
    api_db_override: None,
    prospecting_voice_settings: None,
    monkeypatch: MonkeyPatch,
) -> None:
    client = TestClient(app)
    graph = seed_cold_call_graph(db_session, client)
    provider = FakeVoiceProvider()

    response = start_call(client, graph, monkeypatch, provider)

    assert response.status_code == 201, response.text
    body = response.json()
    assert body["context_type"] == "prospecting"
    assert body["prospect_id"] == str(graph.prospect.id)
    assert body["dial_leg_id"] == str(graph.leg.id)
    assert body["leg"]["status"] == "dialing"
    assert provider.start_calls == [
        {
            "to": FORWARDING_NUMBER,
            "from_number": PROSPECTING_NUMBER,
            "twiml": provider.start_calls[0]["twiml"],
            "status_callback": provider.start_calls[0]["status_callback"],
            "status_callback_events": ("initiated", "ringing", "answered", "completed"),
        }
    ]
    assert f"intent_id={body['call_intent_id']}" in provider.start_calls[0]["status_callback"]
    assert db_session.scalar(select(func.count()).select_from(Contact)) == 0
    assert db_session.scalar(select(func.count()).select_from(Conversation)) == 0
    assert db_session.scalar(select(func.count()).select_from(CommunicationRecord)) == 0

    call = db_session.get(CallRecord, UUID(body["call_record_id"]))
    intent = db_session.get(VoiceCallIntent, UUID(body["call_intent_id"]))
    assert call is not None
    assert intent is not None
    assert call.conversation_id is None
    assert call.contact_id is None
    assert call.communication_record_id is None
    assert call.prospect_id == graph.prospect.id
    assert intent.conversation_id is None
    assert intent.contact_id is None

    status_path = f"/api/v1/webhooks/twilio/voice/status?intent_id={body['call_intent_id']}"
    callbacks = [
        {
            "CallSid": ROOT_CALL_SID,
            "CallStatus": "initiated",
            "SequenceNumber": "0",
        },
        {
            "CallSid": ROOT_CALL_SID,
            "CallStatus": "ringing",
            "SequenceNumber": "1",
        },
        {
            "CallSid": CHILD_CALL_SID,
            "ParentCallSid": ROOT_CALL_SID,
            "CallStatus": "ringing",
            "SequenceNumber": "0",
        },
        {
            "CallSid": CHILD_CALL_SID,
            "ParentCallSid": ROOT_CALL_SID,
            "CallStatus": "in-progress",
            "SequenceNumber": "1",
        },
        {
            "CallSid": CHILD_CALL_SID,
            "ParentCallSid": ROOT_CALL_SID,
            "CallStatus": "completed",
            "CallDuration": "47",
            "SequenceNumber": "2",
        },
    ]
    for payload in callbacks:
        first = post_signed(client, status_path, payload)
        duplicate = post_signed(client, status_path, payload)
        assert first.status_code == 204, first.text
        assert duplicate.status_code == 204, duplicate.text

    db_session.expire_all()
    updated_leg = db_session.get(ProspectingDialLeg, graph.leg.id)
    updated_call = db_session.get(CallRecord, call.id)
    assert updated_leg is not None
    assert updated_call is not None
    assert updated_leg.status == "completed"
    assert updated_leg.connected_at is not None
    assert updated_leg.completed_at is not None
    assert updated_call.status == "completed"
    assert updated_call.child_provider_call_id == CHILD_CALL_SID
    assert updated_call.duration_seconds == 47
    assert db_session.scalar(
        select(func.count())
        .select_from(ProspectingProviderEvent)
        .where(ProspectingProviderEvent.external_event_id.like("voice:status:%"))
    ) == len(callbacks)


def test_provider_start_failure_terminalizes_only_leg_and_preserves_retry_context(
    db_session: Session,
    api_db_override: None,
    prospecting_voice_settings: None,
    monkeypatch: MonkeyPatch,
) -> None:
    client = TestClient(app)
    graph = seed_cold_call_graph(db_session, client)

    response = start_call(client, graph, monkeypatch, FailingStartProvider())

    assert response.status_code == 502, response.text
    db_session.expire_all()
    leg = db_session.get(ProspectingDialLeg, graph.leg.id)
    attempt = db_session.get(ProspectingAttempt, graph.attempt.id)
    session = db_session.get(ProspectingDialSession, graph.session.id)
    call = db_session.scalar(
        select(CallRecord).where(CallRecord.prospecting_dial_leg_id == graph.leg.id)
    )
    intent = db_session.scalar(
        select(VoiceCallIntent).where(VoiceCallIntent.prospecting_dial_leg_id == graph.leg.id)
    )
    assert leg is not None
    assert attempt is not None
    assert session is not None
    assert call is not None
    assert intent is not None
    assert leg.status == "failed"
    assert leg.failed_at is not None
    assert call.status == "failed"
    assert intent.status == "failed"
    assert attempt.status == "in_progress"
    assert attempt.completed_at is None
    assert session.state == "wrap_up"
    assert session.ended_at is None


def test_prepared_start_survives_local_crash_and_retries_without_duplicate_provider_call(
    db_session: Session,
    api_db_override: None,
    prospecting_voice_settings: None,
    monkeypatch: MonkeyPatch,
) -> None:
    client = TestClient(app)
    graph = seed_cold_call_graph(db_session, client)
    provider = FakeVoiceProvider()
    original_dispatch = prospecting_voice_service.dispatch_prepared_voice_call

    def simulate_crash(*args: Any, **kwargs: Any) -> Any:
        raise prospecting_voice_service.ProspectingVoiceConflictError(
            "Simulated crash after the prepared commit."
        )

    monkeypatch.setattr(prospecting_voice_service, "dispatch_prepared_voice_call", simulate_crash)
    interrupted = start_call(client, graph, monkeypatch, provider)
    assert interrupted.status_code == 409, interrupted.text
    assert provider.start_calls == []
    intent = db_session.scalar(
        select(VoiceCallIntent).where(VoiceCallIntent.prospecting_dial_leg_id == graph.leg.id)
    )
    assert intent is not None
    assert (intent.intent_metadata or {}).get("provider_start_state") == "prepared"

    monkeypatch.setattr(
        prospecting_voice_service,
        "dispatch_prepared_voice_call",
        original_dispatch,
    )
    retried = start_call(client, graph, monkeypatch, provider)
    replayed = start_call(client, graph, monkeypatch, provider)

    assert retried.status_code == 201, retried.text
    assert replayed.status_code == 201, replayed.text
    assert replayed.json()["control_action"] == "replayed"
    assert len(provider.start_calls) == 1


def test_cellphone_pre_provider_cancel_remains_blocked(
    db_session: Session,
    api_db_override: None,
    prospecting_voice_settings: None,
    monkeypatch: MonkeyPatch,
) -> None:
    client = TestClient(app)
    graph = seed_cold_call_graph(db_session, client)
    provider = FakeVoiceProvider()

    def simulate_crash(*args: Any, **kwargs: Any) -> Any:
        raise prospecting_voice_service.ProspectingVoiceConflictError(
            "Simulated cellphone preparation boundary."
        )

    monkeypatch.setattr(prospecting_voice_service, "dispatch_prepared_voice_call", simulate_crash)
    prepared = start_call(client, graph, monkeypatch, provider)
    assert prepared.status_code == 409, prepared.text

    blocked = client.post(
        f"/api/v1/prospecting/dialer/legs/{graph.leg.id}/call/cancel",
        headers={"X-Dev-User-Email": VA_EMAIL},
        json={
            **browser_lease_payload(graph),
            "reason": "Cellphone mode keeps its existing provider-start boundary.",
        },
    )
    assert blocked.status_code == 409, blocked.text
    assert "provider call has not started" in blocked.json()["detail"].lower()


def test_stale_browser_cannot_start_cancel_or_hang_up_recovered_session(
    db_session: Session,
    api_db_override: None,
    prospecting_voice_settings: None,
    monkeypatch: MonkeyPatch,
) -> None:
    client = TestClient(app)
    graph = seed_cold_call_graph(db_session, client)
    provider = FakeVoiceProvider()
    old_browser = graph.session.browser_session_id
    old_token = graph.session.lease_token
    assert old_token is not None
    graph.session.browser_session_id = "d3-recovered-browser"
    graph.session.lease_token = "d3-recovered-lease-token-xxxxxxxx"
    db_session.commit()
    monkeypatch.setattr(
        "app.services.prospecting_voice.get_twilio_voice_call_provider",
        lambda: provider,
    )
    stale_start = client.post(
        f"/api/v1/prospecting/dialer/legs/{graph.leg.id}/call",
        headers={"X-Dev-User-Email": VA_EMAIL},
        json={
            "idempotency_key": "d3-stale-browser-start",
            "browser_session_id": old_browser,
            "lease_token": old_token,
        },
    )
    assert stale_start.status_code == 409, stale_start.text
    assert provider.start_calls == []

    started = start_call(client, graph, monkeypatch, provider)
    assert started.status_code == 201, started.text
    stale_control = {
        "reason": "A stale tab must not control this call.",
        "browser_session_id": old_browser,
        "lease_token": old_token,
    }
    for action in ("cancel", "hangup"):
        rejected = client.post(
            f"/api/v1/prospecting/dialer/legs/{graph.leg.id}/call/{action}",
            headers={"X-Dev-User-Email": VA_EMAIL},
            json=stale_control,
        )
        assert rejected.status_code == 409, rejected.text
    assert provider.cancel_calls == []
    assert provider.hangup_calls == []


def test_provider_dispatch_revalidates_runtime_switch_after_prepared_commit(
    db_session: Session,
    api_db_override: None,
    prospecting_voice_settings: None,
    monkeypatch: MonkeyPatch,
) -> None:
    client = TestClient(app)
    graph = seed_cold_call_graph(db_session, client)
    provider = FakeVoiceProvider()
    original_dispatch = prospecting_voice_service.dispatch_prepared_voice_call

    def pause_after_prepare(*args: Any, **kwargs: Any) -> Any:
        raise prospecting_voice_service.ProspectingVoiceConflictError(
            "Pause after prepared commit."
        )

    monkeypatch.setattr(
        prospecting_voice_service, "dispatch_prepared_voice_call", pause_after_prepare
    )
    prepared = start_call(client, graph, monkeypatch, provider)
    assert prepared.status_code == 409, prepared.text
    graph.organization.prospecting_dialer_enabled = False
    db_session.commit()
    monkeypatch.setattr(
        prospecting_voice_service,
        "dispatch_prepared_voice_call",
        original_dispatch,
    )

    blocked = start_call(client, graph, monkeypatch, provider)

    assert blocked.status_code == 503, blocked.text
    assert "company prospecting dialer switch is off" in blocked.json()["detail"]
    assert provider.start_calls == []


def test_cellphone_connect_dials_seller_once_from_exact_in_flight_root_call(
    db_session: Session,
    api_db_override: None,
    prospecting_voice_settings: None,
    monkeypatch: MonkeyPatch,
) -> None:
    client = TestClient(app)
    graph = seed_cold_call_graph(db_session, client)
    provider = FakeVoiceProvider()

    started = start_call(client, graph, monkeypatch, provider)

    assert started.status_code == 201, started.text
    intent = db_session.scalar(
        select(VoiceCallIntent).where(
            VoiceCallIntent.prospecting_dial_leg_id == graph.leg.id
        )
    )
    assert intent is not None
    db_session.expire_all()
    call = db_session.scalar(
        select(CallRecord).where(CallRecord.call_intent_id == intent.id)
    )
    leg = db_session.get(ProspectingDialLeg, graph.leg.id)
    attempt = db_session.get(ProspectingAttempt, graph.attempt.id)
    assert call is not None and leg is not None and attempt is not None
    assert {
        "intent_status": intent.status,
        "intent_provider": intent.provider_call_id,
        "call_status": call.status,
        "call_provider": call.provider_call_id,
        "call_ended": call.ended_at,
        "call_child": call.child_provider_call_id,
        "leg_status": leg.status,
        "leg_provider": leg.provider_call_id,
        "attempt_status": attempt.status,
        "attempt_provider": attempt.provider_call_id,
    } == {
        "intent_status": "started",
        "intent_provider": ROOT_CALL_SID,
        "call_status": "dialing",
        "call_provider": ROOT_CALL_SID,
        "call_ended": None,
        "call_child": None,
        "leg_status": "dialing",
        "leg_provider": ROOT_CALL_SID,
        "attempt_status": "in_progress",
        "attempt_provider": ROOT_CALL_SID,
    }
    connect_path = (
        "/api/v1/webhooks/twilio/voice/forwarded-connect"
        f"?intent_id={intent.id}"
    )
    payload = {"CallSid": ROOT_CALL_SID, "Digits": "1"}

    connected = post_signed(client, connect_path, payload)
    replayed = post_signed(client, connect_path, payload)

    assert connected.status_code == 200, connected.text
    assert PROSPECT_NUMBER in connected.text
    assert f'callerId="{PROSPECTING_NUMBER}"' in connected.text
    assert replayed.status_code == 422, replayed.text
    assert "already authorized" in replayed.json()["detail"]


def test_cellphone_connect_revalidates_runtime_switch_before_dialing_seller(
    db_session: Session,
    api_db_override: None,
    prospecting_voice_settings: None,
    monkeypatch: MonkeyPatch,
) -> None:
    client = TestClient(app)
    graph = seed_cold_call_graph(db_session, client)
    provider = FakeVoiceProvider()

    started = start_call(client, graph, monkeypatch, provider)

    assert started.status_code == 201, started.text
    intent = db_session.scalar(
        select(VoiceCallIntent).where(
            VoiceCallIntent.prospecting_dial_leg_id == graph.leg.id
        )
    )
    assert intent is not None
    assert intent.status == "started"
    assert provider.start_calls[0]["to"] == FORWARDING_NUMBER

    # The VA's cellphone is already ringing, but the seller has not been dialed.
    # A manager kill switch at this boundary must still stop the second leg.
    graph.organization.prospecting_dialer_enabled = False
    db_session.commit()
    connect_path = (
        "/api/v1/webhooks/twilio/voice/forwarded-connect"
        f"?intent_id={intent.id}"
    )
    connected = post_signed(
        client,
        connect_path,
        {"CallSid": ROOT_CALL_SID, "Digits": "1"},
    )

    assert connected.status_code == 422, connected.text
    assert "company prospecting dialer switch is off" in connected.json()["detail"]
    assert PROSPECT_NUMBER not in connected.text


def test_immediate_provider_callback_completes_dispatch_marker_before_rest_response(
    db_session: Session,
    api_db_override: None,
    prospecting_voice_settings: None,
    monkeypatch: MonkeyPatch,
) -> None:
    client = TestClient(app)
    graph = seed_cold_call_graph(db_session, client)
    provider = FakeVoiceProvider()

    def pause_after_prepare(*args: Any, **kwargs: Any) -> Any:
        raise prospecting_voice_service.ProspectingVoiceConflictError(
            "Simulate a process boundary before the REST response."
        )

    monkeypatch.setattr(
        prospecting_voice_service, "dispatch_prepared_voice_call", pause_after_prepare
    )
    prepared = start_call(client, graph, monkeypatch, provider)
    assert prepared.status_code == 409, prepared.text
    intent = db_session.scalar(
        select(VoiceCallIntent).where(VoiceCallIntent.prospecting_dial_leg_id == graph.leg.id)
    )
    assert intent is not None
    metadata = dict(intent.intent_metadata or {})
    metadata["provider_start_state"] = "dispatching"
    intent.intent_metadata = metadata
    db_session.commit()

    status_path = f"/api/v1/webhooks/twilio/voice/status?intent_id={intent.id}"
    callback = post_signed(
        client,
        status_path,
        {"CallSid": ROOT_CALL_SID, "CallStatus": "initiated", "SequenceNumber": "0"},
    )

    assert callback.status_code == 204, callback.text
    db_session.refresh(intent)
    assert intent.status == "started"
    assert intent.provider_call_id == ROOT_CALL_SID
    assert (intent.intent_metadata or {}).get("provider_start_state") == "started"


def test_cancel_failure_is_retryable_and_success_is_idempotent(
    db_session: Session,
    api_db_override: None,
    prospecting_voice_settings: None,
    monkeypatch: MonkeyPatch,
) -> None:
    client = TestClient(app)
    graph = seed_cold_call_graph(db_session, client)
    provider = FakeVoiceProvider(cancel_failures_remaining=1)
    started = start_call(client, graph, monkeypatch, provider)
    assert started.status_code == 201, started.text
    path = f"/api/v1/prospecting/dialer/legs/{graph.leg.id}/call/cancel"
    request = {
        "reason": "Caller stopped the controlled test call.",
        "browser_session_id": graph.session.browser_session_id,
        "lease_token": graph.session.lease_token,
    }

    failed = client.post(path, headers={"X-Dev-User-Email": VA_EMAIL}, json=request)
    assert failed.status_code == 502, failed.text
    db_session.expire_all()
    leg = db_session.get(ProspectingDialLeg, graph.leg.id)
    assert leg is not None
    assert leg.status == "dialing"
    assert leg.completed_at is None

    retried = client.post(path, headers={"X-Dev-User-Email": VA_EMAIL}, json=request)
    replayed = client.post(path, headers={"X-Dev-User-Email": VA_EMAIL}, json=request)
    assert retried.status_code == 200, retried.text
    assert retried.json()["control_action"] == "cancelled"
    assert replayed.status_code == 200, replayed.text
    assert replayed.json()["control_action"] == "replayed"
    assert len(provider.cancel_calls) == 2
    db_session.expire_all()
    leg = db_session.get(ProspectingDialLeg, graph.leg.id)
    assert leg is not None
    assert leg.status == "cancelled"
    assert leg.completed_at is not None


def test_fetch_reconciles_missed_terminal_provider_state(
    db_session: Session,
    api_db_override: None,
    prospecting_voice_settings: None,
    monkeypatch: MonkeyPatch,
) -> None:
    client = TestClient(app)
    graph = seed_cold_call_graph(db_session, client)
    provider = FakeVoiceProvider(
        fetch_result=VoiceCallResult(sid=ROOT_CALL_SID, status="completed")
    )
    started = start_call(client, graph, monkeypatch, provider)
    assert started.status_code == 201, started.text
    count_before = db_session.scalar(select(func.count()).select_from(ProspectingProviderEvent))

    response = client.get(
        f"/api/v1/prospecting/dialer/legs/{graph.leg.id}/call",
        headers={"X-Dev-User-Email": VA_EMAIL},
    )

    assert response.status_code == 200, response.text
    assert response.json()["provider_status"] == "completed"
    assert response.json()["leg"]["status"] == "completed"
    assert provider.fetch_calls == [ROOT_CALL_SID]
    db_session.expire_all()
    leg = db_session.get(ProspectingDialLeg, graph.leg.id)
    call = db_session.scalar(
        select(CallRecord).where(CallRecord.prospecting_dial_leg_id == graph.leg.id)
    )
    session = db_session.get(ProspectingDialSession, graph.session.id)
    assert leg is not None
    assert call is not None
    assert session is not None
    assert leg.status == "completed"
    assert call.status == "completed"
    assert session.state == "wrap_up"
    assert db_session.scalar(select(func.count()).select_from(ProspectingProviderEvent)) == (
        count_before + 1
    )


@pytest.mark.parametrize(
    ("mutation", "email", "expected_status", "detail"),
    [
        ("other_caller", OTHER_VA_EMAIL, 403, "assigned to another caller"),
        ("wrong_line", VA_EMAIL, 503, "dedicated acquisitions line"),
        ("wrong_prospect", VA_EMAIL, 409, "does not belong to this prospect"),
    ],
)
def test_start_rejects_wrong_caller_line_or_prospect(
    db_session: Session,
    api_db_override: None,
    prospecting_voice_settings: None,
    monkeypatch: MonkeyPatch,
    mutation: str,
    email: str,
    expected_status: int,
    detail: str,
) -> None:
    client = TestClient(app)
    graph = seed_cold_call_graph(db_session, client)
    if mutation == "wrong_line":
        graph.line.purpose_key = "seller_conversations"
    elif mutation == "wrong_prospect":
        graph.leg.recipient = "+14045550888"
    db_session.commit()
    provider = FakeVoiceProvider()
    monkeypatch.setattr(
        "app.services.prospecting_voice.get_twilio_voice_call_provider",
        lambda: provider,
    )

    response = client.post(
        f"/api/v1/prospecting/dialer/legs/{graph.leg.id}/call",
        headers={"X-Dev-User-Email": email},
        json={
            "idempotency_key": f"d2-rejected-{mutation}",
            "browser_session_id": graph.session.browser_session_id,
            "lease_token": graph.session.lease_token,
        },
    )

    assert response.status_code == expected_status, response.text
    assert detail in response.json()["detail"]
    assert provider.start_calls == []
    assert db_session.scalar(select(func.count()).select_from(CallRecord)) == 0


def test_prospecting_line_records_cold_callback_without_manufacturing_warm_lead(
    db_session: Session,
    api_db_override: None,
    prospecting_voice_settings: None,
) -> None:
    client = TestClient(app)
    seed_cold_call_graph(db_session, client)
    payload = {
        "From": "+14045550777",
        "To": PROSPECTING_NUMBER,
        "CallSid": "CA00000000000000000000000000000299",
    }
    path = "/api/v1/webhooks/twilio/voice/incoming"

    response = post_signed(client, path, payload)

    assert response.status_code == 200, response.text
    assert "<Record" in response.text
    assert db_session.scalar(select(func.count()).select_from(Lead)) == 0
    assert db_session.scalar(select(func.count()).select_from(Contact)) == 0
    assert db_session.scalar(select(func.count()).select_from(Conversation)) == 0
    assert db_session.scalar(select(func.count()).select_from(CallRecord)) == 1
    callback = db_session.scalar(select(ProspectingInboundCallback))
    assert callback is not None
    assert callback.match_status == "unknown"
    assert callback.matched_prospect_id is None
    assert callback.matched_attempt_id is None
    call = db_session.scalar(select(CallRecord))
    assert call is not None
    assert call.prospecting_inbound_callback_id == callback.id
    assert call.prospect_id is None
    assert call.prospecting_attempt_id is None
    assert call.conversation_id is None
    assert call.lead_id is None
    assert call.contact_id is None


def test_exact_recent_same_line_callback_matches_cold_prospect_and_replay_is_idempotent(
    db_session: Session,
    api_db_override: None,
    prospecting_voice_settings: None,
) -> None:
    client = TestClient(app)
    graph = seed_cold_call_graph(db_session, client)
    attach_exact_dialed_number_evidence(
        db_session,
        graph,
        provider_call_id="CA00000000000000000000000000000301",
        child_provider_call_id="CA00000000000000000000000000001301",
    )
    db_session.commit()
    payload = {
        "From": PROSPECT_NUMBER,
        "To": PROSPECTING_NUMBER,
        "CallSid": "CA00000000000000000000000000000302",
    }
    path = "/api/v1/webhooks/twilio/voice/incoming"

    first = post_signed(client, path, payload)
    replay = post_signed(client, path, payload)

    assert first.status_code == 200, first.text
    assert replay.status_code == 200, replay.text
    assert "<Dial" in first.text
    assert FORWARDING_NUMBER in first.text
    callbacks = list(db_session.scalars(select(ProspectingInboundCallback)))
    calls = list(db_session.scalars(select(CallRecord)))
    assert len(callbacks) == 1
    assert len(calls) == 2
    callback = callbacks[0]
    call = next(item for item in calls if item.prospecting_inbound_callback_id is not None)
    assert callback.match_status == "matched"
    assert callback.match_strategy == "exact_phone_recent_same_line"
    assert callback.match_confidence_basis_points == 8000
    assert callback.candidate_count == 1
    assert callback.matched_prospect_id == graph.prospect.id
    assert callback.matched_attempt_id == graph.attempt.id
    assert callback.assigned_user_id == graph.caller.id
    assert call.prospect_id == graph.prospect.id
    assert call.prospecting_attempt_id == graph.attempt.id
    assert call.prospecting_dial_leg_id is None
    assert call.prospecting_inbound_callback_id == callback.id
    assert call.conversation_id is None
    assert call.lead_id is None
    assert call.contact_id is None
    assert db_session.scalar(select(func.count()).select_from(Lead)) == 0
    assert db_session.scalar(select(func.count()).select_from(Contact)) == 0
    assert db_session.scalar(select(func.count()).select_from(Conversation)) == 0


def test_root_provider_call_without_dialed_number_child_evidence_does_not_match(
    db_session: Session,
    api_db_override: None,
    prospecting_voice_settings: None,
) -> None:
    client = TestClient(app)
    graph = seed_cold_call_graph(db_session, client)
    graph.leg.provider_call_id = "CA00000000000000000000000000000305"
    graph.attempt.provider = "twilio"
    graph.attempt.provider_call_id = "CA00000000000000000000000000000305"
    db_session.commit()

    response = post_signed(
        client,
        "/api/v1/webhooks/twilio/voice/incoming",
        {
            "From": PROSPECT_NUMBER,
            "To": PROSPECTING_NUMBER,
            "CallSid": "CA00000000000000000000000000000306",
        },
    )

    assert response.status_code == 200, response.text
    callback = db_session.scalar(select(ProspectingInboundCallback))
    assert callback is not None
    assert callback.match_status == "unknown"
    assert callback.match_strategy == "exact_phone_no_recent_line_attempt"
    assert callback.matched_prospect_id is None
    assert callback.matched_attempt_id is None


def test_ambiguous_exact_callback_never_promotes_a_warm_record(
    db_session: Session,
    api_db_override: None,
    prospecting_voice_settings: None,
) -> None:
    client = TestClient(app)
    graph = seed_cold_call_graph(db_session, client)
    attach_exact_dialed_number_evidence(
        db_session,
        graph,
        provider_call_id="CA00000000000000000000000000000311",
        child_provider_call_id="CA00000000000000000000000000001311",
    )
    now = datetime.now(UTC)
    second = Prospect(
        organization_id=graph.organization.id,
        campaign_id=graph.prospect.campaign_id,
        assigned_user_id=graph.other_caller.id,
        source_record_key="d8-ambiguous-prospect",
        status="ready",
        legal_name="D8 Same Number Prospect",
        phone=PROSPECT_NUMBER,
        normalized_phone=PROSPECT_NUMBER,
        street_address="202 Callback Court",
        city="Atlanta",
        state_code="GA",
        postal_code="30303",
        suppression_status="clear",
        phone_validation_status="verified",
        call_eligibility="eligible",
        source_payload={},
    )
    db_session.add(second)
    db_session.flush()
    second_entry = ProspectCallingBatchEntry(
        organization_id=graph.organization.id,
        prospect_calling_batch_id=graph.batch.id,
        prospect_id=second.id,
        assigned_user_id=graph.other_caller.id,
        sequence_number=2,
        status="completed",
        attempt_count=1,
    )
    db_session.add(second_entry)
    db_session.flush()
    second_attempt = ProspectingAttempt(
        organization_id=graph.organization.id,
        batch_entry_id=second_entry.id,
        prospect_id=second.id,
        caller_user_id=graph.other_caller.id,
        script_version_id=graph.attempt.script_version_id,
        status="completed",
        outcome="no_answer",
        measurement_metadata={},
        qualification_answers={},
        started_at=now - timedelta(minutes=5),
        completed_at=now - timedelta(minutes=4),
    )
    db_session.add(second_attempt)
    db_session.flush()
    second_leg = ProspectingDialLeg(
        organization_id=graph.organization.id,
        dial_session_id=graph.session.id,
        prospect_id=second.id,
        batch_entry_id=second_entry.id,
        attempt_id=second_attempt.id,
        voice_line_id=graph.line.id,
        line_slot=1,
        recipient=PROSPECT_NUMBER,
        provider="twilio",
        provider_call_id="CA00000000000000000000000000000312",
        idempotency_key="d8-ambiguous-second-leg",
        status="completed",
        last_provider_event_sequence=2,
        queued_at=now - timedelta(minutes=5),
        completed_at=now - timedelta(minutes=4),
        answer_classification="unknown",
        party_classification="unknown",
        leg_metadata={},
    )
    db_session.add(second_leg)
    db_session.flush()
    attach_exact_dialed_number_evidence(
        db_session,
        graph,
        attempt=second_attempt,
        leg=second_leg,
        provider_call_id="CA00000000000000000000000000000312",
        child_provider_call_id="CA00000000000000000000000000001312",
    )
    db_session.commit()

    response = post_signed(
        client,
        "/api/v1/webhooks/twilio/voice/incoming",
        {
            "From": PROSPECT_NUMBER,
            "To": PROSPECTING_NUMBER,
            "CallSid": "CA00000000000000000000000000000313",
        },
    )

    assert response.status_code == 200, response.text
    callback = db_session.scalar(select(ProspectingInboundCallback))
    call = db_session.scalar(
        select(CallRecord).where(CallRecord.prospecting_inbound_callback_id.is_not(None))
    )
    assert callback is not None
    assert callback.match_status == "ambiguous"
    assert callback.candidate_count == 2
    assert callback.matched_prospect_id is None
    assert callback.matched_attempt_id is None
    assert call is not None
    assert call.prospect_id is None
    assert call.prospecting_attempt_id is None
    assert db_session.scalar(select(func.count()).select_from(Lead)) == 0
    assert db_session.scalar(select(func.count()).select_from(Contact)) == 0
    assert db_session.scalar(select(func.count()).select_from(Conversation)) == 0


def test_callback_routing_prefers_fresh_same_line_va_then_manager_fallback_and_scopes_list(
    db_session: Session,
    api_db_override: None,
    prospecting_voice_settings: None,
) -> None:
    client = TestClient(app)
    graph = seed_cold_call_graph(db_session, client)
    attach_exact_dialed_number_evidence(
        db_session,
        graph,
        provider_call_id="CA00000000000000000000000000000321",
        child_provider_call_id="CA00000000000000000000000000001321",
    )
    db_session.commit()
    first = post_signed(
        client,
        "/api/v1/webhooks/twilio/voice/incoming",
        {
            "From": PROSPECT_NUMBER,
            "To": PROSPECTING_NUMBER,
            "CallSid": "CA00000000000000000000000000000322",
        },
    )
    assert first.status_code == 200, first.text
    first_callback = db_session.scalar(
        select(ProspectingInboundCallback).where(
            ProspectingInboundCallback.provider_call_id
            == "CA00000000000000000000000000000322"
        )
    )
    assert first_callback is not None
    assert first_callback.assigned_user_id == graph.caller.id
    assert first_callback.fallback_user_id == graph.owner.id

    graph.owner.voice_forwarding_number = "+14045550888"
    graph.owner.voice_forwarding_enabled = True
    graph.line.assigned_user_id = graph.owner.id
    graph.session.heartbeat_at = datetime.now(UTC) - timedelta(minutes=10)
    graph.session.lease_expires_at = datetime.now(UTC) - timedelta(minutes=5)
    db_session.commit()
    second = post_signed(
        client,
        "/api/v1/webhooks/twilio/voice/incoming",
        {
            "From": PROSPECT_NUMBER,
            "To": PROSPECTING_NUMBER,
            "CallSid": "CA00000000000000000000000000000323",
        },
    )
    assert second.status_code == 200, second.text
    assert "+14045550888" in second.text
    second_callback = db_session.scalar(
        select(ProspectingInboundCallback).where(
            ProspectingInboundCallback.provider_call_id
            == "CA00000000000000000000000000000323"
        )
    )
    assert second_callback is not None
    assert second_callback.assigned_user_id == graph.owner.id

    va_list = client.get(
        "/api/v1/prospecting/dialer/callbacks",
        headers={"X-Dev-User-Email": VA_EMAIL},
    )
    manager_list = client.get(
        "/api/v1/prospecting/dialer/callbacks",
        headers={"X-Dev-User-Email": OWNER_EMAIL},
    )
    assert va_list.status_code == 200, va_list.text
    assert va_list.json()["total"] == 1
    assert len(va_list.json()["items"]) == 1
    assert va_list.json()["items"][0]["can_open"] is True
    assert va_list.json()["items"][0]["batch_entry_id"] == str(graph.entry.id)
    assert manager_list.status_code == 200, manager_list.text
    assert manager_list.json()["total"] == 2
    assert len(manager_list.json()["items"]) == 2
    assert all(item["can_open"] is True for item in manager_list.json()["items"])

    # Callback access is captured when the call arrives; closing and reassigning
    # the historical queue entry must not make that callback unusable.
    graph.entry.status = "completed"
    graph.entry.assigned_user_id = graph.other_caller.id
    db_session.commit()
    callback_path = f"/api/v1/prospecting/dialer/callbacks/{first_callback.id}/prospect"
    assigned_access = client.get(
        callback_path,
        headers={"X-Dev-User-Email": VA_EMAIL},
    )
    manager_access = client.get(
        callback_path,
        headers={"X-Dev-User-Email": OWNER_EMAIL},
    )
    unrelated_access = client.get(
        callback_path,
        headers={"X-Dev-User-Email": OTHER_VA_EMAIL},
    )
    assert assigned_access.status_code == 200, assigned_access.text
    assert assigned_access.json()["id"] == str(graph.entry.id)
    assert manager_access.status_code == 200, manager_access.text
    assert unrelated_access.status_code == 404, unrelated_access.text

    other_foundation = bootstrap_foundation(
        db_session,
        organization_name="D8 Isolated Callback Workspace",
        admin_email="d8-isolated-owner@example.com",
        admin_name="D8 Isolated Owner",
    )
    assert other_foundation.admin_user is not None
    db_session.commit()
    cross_org_access = client.get(
        callback_path,
        headers={"X-Dev-User-Email": "d8-isolated-owner@example.com"},
    )
    assert cross_org_access.status_code == 404, cross_org_access.text


def test_explicit_line_fallback_can_open_callback_even_when_another_va_owns_batch(
    db_session: Session,
    api_db_override: None,
    prospecting_voice_settings: None,
) -> None:
    client = TestClient(app)
    graph = seed_cold_call_graph(db_session, client)
    attach_exact_dialed_number_evidence(
        db_session,
        graph,
        provider_call_id="CA00000000000000000000000000000325",
        child_provider_call_id="CA00000000000000000000000000001325",
    )
    graph.other_caller.voice_forwarding_number = "+14045550778"
    graph.other_caller.voice_forwarding_enabled = True
    graph.line.fallback_user_id = graph.other_caller.id
    graph.session.heartbeat_at = datetime.now(UTC) - timedelta(minutes=10)
    graph.session.lease_expires_at = datetime.now(UTC) - timedelta(minutes=5)
    db_session.commit()

    response = post_signed(
        client,
        "/api/v1/webhooks/twilio/voice/incoming",
        {
            "From": PROSPECT_NUMBER,
            "To": PROSPECTING_NUMBER,
            "CallSid": "CA00000000000000000000000000000326",
        },
    )

    assert response.status_code == 200, response.text
    assert "+14045550778" in response.text
    callback = db_session.scalar(select(ProspectingInboundCallback))
    assert callback is not None
    assert callback.assigned_user_id == graph.other_caller.id
    assert graph.entry.assigned_user_id == graph.caller.id
    callback_list = client.get(
        "/api/v1/prospecting/dialer/callbacks",
        headers={"X-Dev-User-Email": OTHER_VA_EMAIL},
    )
    callback_context = client.get(
        f"/api/v1/prospecting/dialer/callbacks/{callback.id}/prospect",
        headers={"X-Dev-User-Email": OTHER_VA_EMAIL},
    )
    assert callback_list.status_code == 200, callback_list.text
    assert callback_list.json()["total"] == 1
    assert callback_list.json()["items"][0]["can_open"] is True
    assert callback_context.status_code == 200, callback_context.text
    assert callback_context.json()["id"] == str(graph.entry.id)


def test_child_no_answer_does_not_close_callback_but_final_dial_result_creates_one_task(
    db_session: Session,
    api_db_override: None,
    prospecting_voice_settings: None,
) -> None:
    client = TestClient(app)
    graph = seed_cold_call_graph(db_session, client)
    attach_exact_dialed_number_evidence(
        db_session,
        graph,
        provider_call_id="CA00000000000000000000000000000331",
        child_provider_call_id="CA00000000000000000000000000001331",
    )
    graph.owner.voice_forwarding_number = "+14045550888"
    graph.owner.voice_forwarding_enabled = True
    graph.line.assigned_user_id = graph.owner.id
    graph.line.missed_call_action = "task_only"
    db_session.commit()
    inbound_sid = "CA00000000000000000000000000000332"
    response = post_signed(
        client,
        "/api/v1/webhooks/twilio/voice/incoming",
        {"From": PROSPECT_NUMBER, "To": PROSPECTING_NUMBER, "CallSid": inbound_sid},
    )
    assert response.status_code == 200, response.text
    callback = db_session.scalar(select(ProspectingInboundCallback))
    call = db_session.scalar(
        select(CallRecord).where(CallRecord.prospecting_inbound_callback_id.is_not(None))
    )
    assert callback is not None
    assert call is not None
    assert (call.call_metadata or {}).get("ring_target_count") == 2

    child_path = f"/api/v1/webhooks/twilio/voice/status?call_id={call.id}"
    child = post_signed(
        client,
        child_path,
        {
            "CallSid": "CA00000000000000000000000000000333",
            "ParentCallSid": inbound_sid,
            "CallStatus": "no-answer",
        },
    )
    assert child.status_code == 204, child.text
    db_session.expire_all()
    callback = db_session.get(ProspectingInboundCallback, callback.id)
    assert callback is not None
    assert callback.status == "ringing"
    assert db_session.scalar(select(func.count()).select_from(Task)) == 0

    final_path = f"/api/v1/webhooks/twilio/voice/dial-result?call_id={call.id}"
    final_payload = {
        "CallSid": inbound_sid,
        "DialCallSid": "CA00000000000000000000000000000334",
        "DialCallStatus": "no-answer",
    }
    final = post_signed(client, final_path, final_payload)
    replay = post_signed(client, final_path, final_payload)
    terminal_inbound_replay = post_signed(
        client,
        "/api/v1/webhooks/twilio/voice/incoming",
        {"From": PROSPECT_NUMBER, "To": PROSPECTING_NUMBER, "CallSid": inbound_sid},
    )
    assert final.status_code == 200, final.text
    assert replay.status_code == 200, replay.text
    assert terminal_inbound_replay.status_code == 200, terminal_inbound_replay.text
    assert "<Hangup" in terminal_inbound_replay.text
    db_session.expire_all()
    callback = db_session.get(ProspectingInboundCallback, callback.id)
    assert callback is not None
    assert callback.status == "missed"
    tasks = list(db_session.scalars(select(Task)))
    assert len(tasks) == 1
    assert db_session.scalar(select(func.count()).select_from(ProspectingInboundCallback)) == 1
    assert (
        db_session.scalar(
            select(func.count())
            .select_from(CallRecord)
            .where(CallRecord.prospecting_inbound_callback_id.is_not(None))
        )
        == 1
    )
    assert tasks[0].task_type == "missed_prospecting_callback"
    assert tasks[0].prospecting_inbound_callback_id == callback.id
    assert tasks[0].prospect_id == graph.prospect.id
    assert tasks[0].call_record_id == call.id


def test_callback_recording_is_retained_without_creating_a_malformed_warm_transcript(
    db_session: Session,
    api_db_override: None,
    prospecting_voice_settings: None,
) -> None:
    client = TestClient(app)
    graph = seed_cold_call_graph(db_session, client)
    attach_exact_dialed_number_evidence(
        db_session,
        graph,
        provider_call_id="CA00000000000000000000000000000341",
        child_provider_call_id="CA00000000000000000000000000001341",
    )
    db_session.commit()
    response = post_signed(
        client,
        "/api/v1/webhooks/twilio/voice/incoming",
        {
            "From": PROSPECT_NUMBER,
            "To": PROSPECTING_NUMBER,
            "CallSid": "CA00000000000000000000000000000342",
        },
    )
    assert response.status_code == 200, response.text
    call = db_session.scalar(
        select(CallRecord).where(CallRecord.prospecting_inbound_callback_id.is_not(None))
    )
    assert call is not None
    recording_path = f"/api/v1/webhooks/twilio/voice/recording?call_id={call.id}"
    recording_payload = {
        "CallSid": call.provider_call_id or "",
        "RecordingSid": "RE00000000000000000000000000000342",
        "RecordingStatus": "completed",
        "RecordingDuration": "42",
        "RecordingChannels": "2",
        "RecordingSource": "DialVerb",
    }

    recorded = post_signed(client, recording_path, recording_payload)
    replay = post_signed(client, recording_path, recording_payload)

    assert recorded.status_code == 204, recorded.text
    assert replay.status_code == 204, replay.text
    recordings = list(db_session.scalars(select(CallRecording)))
    assert len(recordings) == 1
    assert recordings[0].call_record_id == call.id
    assert recordings[0].status == "completed"
    assert db_session.scalar(select(func.count()).select_from(CallTranscript)) == 0


def test_operations_overview_is_manager_only_and_never_exposes_control_secrets(
    db_session: Session,
    api_db_override: None,
    prospecting_voice_settings: None,
) -> None:
    client = TestClient(app)
    graph = seed_cold_call_graph(db_session, client)
    graph.leg.provider_error_code = "provider_failed"
    graph.leg.provider_error_message = (
        "Bearer token=super-secret-provider-token-1234567890 failed for 14045550101"
    )
    db_session.commit()

    forbidden = client.get(
        "/api/v1/prospecting/dialer/operations",
        headers={"X-Dev-User-Email": VA_EMAIL},
    )
    allowed = client.get(
        "/api/v1/prospecting/dialer/operations",
        headers={"X-Dev-User-Email": OWNER_EMAIL},
    )

    assert forbidden.status_code == 403, forbidden.text
    assert allowed.status_code == 200, allowed.text
    body = allowed.json()
    serialized = allowed.text.lower()
    assert body["health"]["active_session_count"] == 1
    assert body["sessions"][0]["session"]["id"] == str(graph.session.id)
    assert body["recent_errors"]
    assert "lease_token" not in serialized
    assert "d2-controlled-lease-token" not in serialized
    assert "super-secret-provider-token" not in serialized
    assert "14045550101" not in serialized
    assert "[redacted]" in body["recent_errors"][0]["message"]


def test_manager_cancel_failure_can_retry_then_replay_completed_command(
    db_session: Session,
    api_db_override: None,
    prospecting_voice_settings: None,
    monkeypatch: MonkeyPatch,
) -> None:
    client = TestClient(app)
    graph = seed_cold_call_graph(db_session, client)
    graph.leg.status = "ringing"
    graph.leg.provider_call_id = "CA00000000000000000000000000000351"
    graph.leg.ringing_at = datetime.now(UTC)
    db_session.commit()
    provider = FakeVoiceProvider(cancel_failures_remaining=1)
    monkeypatch.setattr(
        "app.services.prospecting_dialer_operations.get_twilio_voice_call_provider",
        lambda: provider,
    )
    path = f"/api/v1/prospecting/dialer/operations/sessions/{graph.session.id}/stop"
    payload = {
        "mode": "cancel_unanswered",
        "reason": "Manager ended the unanswered test call.",
        "idempotency_key": "d8-manager-stop-retry-0001",
    }

    failed = client.post(path, headers={"X-Dev-User-Email": OWNER_EMAIL}, json=payload)
    retried = client.post(path, headers={"X-Dev-User-Email": OWNER_EMAIL}, json=payload)
    replayed = client.post(path, headers={"X-Dev-User-Email": OWNER_EMAIL}, json=payload)

    assert failed.status_code == 502, failed.text
    assert retried.status_code == 200, retried.text
    assert replayed.status_code == 200, replayed.text
    assert provider.cancel_calls == [
        "CA00000000000000000000000000000351",
        "CA00000000000000000000000000000351",
    ]
    db_session.expire_all()
    session = db_session.get(ProspectingDialSession, graph.session.id)
    leg = db_session.get(ProspectingDialLeg, graph.leg.id)
    assert session is not None
    assert leg is not None
    commands = (session.session_metadata or {}).get("manager_commands") or []
    assert commands[-1]["status"] == "completed"
    assert commands[-1]["retry_count"] == "1"
    assert leg.status == "cancelled"


def test_manager_pending_stop_command_is_not_replayed_blindly(
    db_session: Session,
    api_db_override: None,
    prospecting_voice_settings: None,
) -> None:
    client = TestClient(app)
    graph = seed_cold_call_graph(db_session, client)
    graph.session.session_metadata = {
        "manager_commands": [
            {
                "key": "d8-pending-manager-stop",
                "kind": "stop",
                "value": "safe_drain",
                "reason": "Controlled pending action.",
                "status": "pending",
                "requested_at": datetime.now(UTC).isoformat(),
            }
        ]
    }
    db_session.commit()

    response = client.post(
        f"/api/v1/prospecting/dialer/operations/sessions/{graph.session.id}/stop",
        headers={"X-Dev-User-Email": OWNER_EMAIL},
        json={
            "mode": "safe_drain",
            "reason": "Controlled pending action.",
            "idempotency_key": "d8-pending-manager-stop",
        },
    )

    assert response.status_code == 409, response.text
    assert "may still be in progress" in response.json()["detail"]


def test_manager_release_orphan_recovery_is_scoped_safe_and_idempotent(
    db_session: Session,
    api_db_override: None,
    prospecting_voice_settings: None,
) -> None:
    client = TestClient(app)
    graph = seed_cold_call_graph(db_session, client)
    path = f"/api/v1/prospecting/dialer/operations/sessions/{graph.session.id}/recover"
    payload = {
        "action": "release_orphan",
        "reason": "Release the untouched test reservation.",
        "idempotency_key": "d8-release-orphan-0001",
    }

    forbidden = client.post(path, headers={"X-Dev-User-Email": VA_EMAIL}, json=payload)
    released = client.post(path, headers={"X-Dev-User-Email": OWNER_EMAIL}, json=payload)
    replayed = client.post(path, headers={"X-Dev-User-Email": OWNER_EMAIL}, json=payload)

    assert forbidden.status_code == 403, forbidden.text
    assert released.status_code == 200, released.text
    assert replayed.status_code == 200, replayed.text
    assert released.json()["session"]["state"] == "failed"
    assert replayed.json()["session"]["state"] == "failed"
    db_session.expire_all()
    session = db_session.get(ProspectingDialSession, graph.session.id)
    leg = db_session.get(ProspectingDialLeg, graph.leg.id)
    attempt = db_session.get(ProspectingAttempt, graph.attempt.id)
    entry = db_session.get(ProspectCallingBatchEntry, graph.entry.id)
    assert session is not None
    assert leg is not None
    assert attempt is not None
    assert entry is not None
    assert session.state == "failed"
    assert session.ended_at is not None
    assert session.lease_token is None
    assert session.lease_expires_at is None
    assert session.current_prospect_id is None
    assert session.current_batch_entry_id is None
    assert session.current_attempt_id is None
    assert leg.status == "cancelled"
    assert leg.completed_at is not None
    assert leg.provider_call_id is None
    assert attempt.status == "cancelled"
    assert attempt.outcome == "technical_failure"
    assert entry.status == "queued"
    commands = (session.session_metadata or {}).get("manager_commands") or []
    assert len(commands) == 1
    assert commands[0]["status"] == "completed"


def test_manager_reconcile_fetches_provider_and_repairs_terminal_state_once(
    db_session: Session,
    api_db_override: None,
    prospecting_voice_settings: None,
    monkeypatch: MonkeyPatch,
) -> None:
    client = TestClient(app)
    graph = seed_cold_call_graph(db_session, client)
    root_call_sid = "CA00000000000000000000000000000361"
    child_call_sid = "CA00000000000000000000000000001361"
    call = attach_exact_dialed_number_evidence(
        db_session,
        graph,
        provider_call_id=root_call_sid,
        child_provider_call_id=child_call_sid,
    )
    observed_at = datetime.now(UTC)
    graph.leg.status = "ringing"
    graph.leg.ringing_at = observed_at
    graph.leg.completed_at = None
    call.status = "ringing"
    call.ended_at = None
    db_session.commit()
    provider = FakeVoiceProvider(
        fetch_result=VoiceCallResult(sid=child_call_sid, status="completed")
    )
    monkeypatch.setattr(
        "app.services.prospecting_dialer_operations.get_twilio_voice_call_provider",
        lambda: provider,
    )
    path = f"/api/v1/prospecting/dialer/operations/sessions/{graph.session.id}/recover"
    payload = {
        "action": "reconcile",
        "reason": "Repair the stale provider terminal state.",
        "idempotency_key": "d8-reconcile-provider-0001",
    }

    repaired = client.post(path, headers={"X-Dev-User-Email": OWNER_EMAIL}, json=payload)
    replayed = client.post(path, headers={"X-Dev-User-Email": OWNER_EMAIL}, json=payload)

    assert repaired.status_code == 200, repaired.text
    assert replayed.status_code == 200, replayed.text
    assert provider.fetch_calls == [child_call_sid]
    assert repaired.json()["current_leg_status"] == "completed"
    assert repaired.json()["session"]["state"] == "wrap_up"
    db_session.expire_all()
    session = db_session.get(ProspectingDialSession, graph.session.id)
    leg = db_session.get(ProspectingDialLeg, graph.leg.id)
    call = db_session.get(CallRecord, call.id)
    assert session is not None
    assert leg is not None
    assert call is not None
    assert session.state == "wrap_up"
    assert session.ended_at is None
    assert leg.status == "completed"
    assert leg.completed_at is not None
    assert call.status == "completed"
    assert call.ended_at is not None
    commands = (session.session_metadata or {}).get("manager_commands") or []
    assert len(commands) == 1
    assert commands[0]["status"] == "completed"
