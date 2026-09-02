from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from runpy import run_path
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from pytest import MonkeyPatch
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.auth import principal_for_user
from app.core.config import get_settings
from app.integrations.communications import OutboundMessageRequest, OutboundMessageResult
from app.integrations.twilio_voice_calls import TwilioVoiceCallResult
from app.main import app
from app.models.foundation import (
    Buyer,
    BuyerEngagement,
    ConsentRecord,
    DispositionBuyerPoolCandidate,
    DispositionBuyerPoolEntry,
    DispositionBuyerPoolRun,
    DispositionCampaignRecipient,
    DispositionCase,
    DispositionExecutionSession,
    Lead,
    SuppressionRecord,
    Task,
    User,
    VoiceCallIntent,
    VoiceLine,
)
from app.services import disposition_execution
from app.services.inbox import ensure_buyer_conversation
from tests.test_dispositions import (
    HEADERS,
    create_active_buyer,
    create_approved_disposition_case,
    put_verified_buy_box,
    setup_case_foundation,
    upload_received_proof,
    verify_proof,
)

CELL_FORWARD_OWNER_EMAIL = HEADERS["X-Dev-User-Email"]


class FakeSmsProvider:
    provider_name = "twilio"

    def __init__(self) -> None:
        self.requests: list[OutboundMessageRequest] = []

    def send(
        self,
        request: OutboundMessageRequest,
        *,
        dry_run: bool = True,
    ) -> OutboundMessageResult:
        assert dry_run is False
        self.requests.append(request)
        return OutboundMessageResult(
            provider="twilio",
            provider_message_id=f"SM{len(self.requests):032d}",
            status="queued",
            raw_payload={"status": "queued", "to": request.recipient},
        )


@pytest.fixture
def cellphone_voice_settings(monkeypatch: MonkeyPatch) -> Iterator[None]:
    values = {
        "TWILIO_VOICE_ENABLED": "true",
        "TWILIO_ACCOUNT_SID": "AC00000000000000000000000000000000",
        "TWILIO_AUTH_TOKEN": "test-voice-auth-token",
        "TWILIO_VOICE_FROM_NUMBER": "+16785417725",
        "TWILIO_WEBHOOK_BASE_URL": "https://api.stonegate.test",
        "TWILIO_VALIDATE_WEBHOOK_SIGNATURES": "true",
        "TWILIO_VOICE_ALLOWED_START_HOUR": "0",
        "TWILIO_VOICE_ALLOWED_END_HOUR": "24",
    }
    for key, value in values.items():
        monkeypatch.setenv(key, value)
    for key in ("TWILIO_API_KEY_SID", "TWILIO_API_KEY_SECRET", "TWILIO_TWIML_APP_SID"):
        monkeypatch.delenv(key, raising=False)
    get_settings.cache_clear()
    try:
        yield
    finally:
        get_settings.cache_clear()


@pytest.fixture
def sms_settings(monkeypatch: MonkeyPatch) -> Iterator[None]:
    values = {
        "TWILIO_SMS_ENABLED": "true",
        "TWILIO_ACCOUNT_SID": "AC00000000000000000000000000000000",
        "TWILIO_AUTH_TOKEN": "test-sms-auth-token",
        "TWILIO_SMS_FROM_NUMBER": "+16785417725",
        "TWILIO_WEBHOOK_BASE_URL": "https://api.stonegate.test",
        "TWILIO_VALIDATE_WEBHOOK_SIGNATURES": "true",
        "TWILIO_SMS_ALLOWED_START_HOUR": "0",
        "TWILIO_SMS_ALLOWED_END_HOUR": "24",
    }
    for key, value in values.items():
        monkeypatch.setenv(key, value)
    get_settings.cache_clear()
    try:
        yield
    finally:
        get_settings.cache_clear()


def _ready_execution_case(db: Session, client: TestClient) -> tuple[str, str]:
    _, transaction_id, buyer_id = setup_case_foundation(db, client)
    case_id = create_approved_disposition_case(client, transaction_id)
    put_verified_buy_box(client, buyer_id)
    proof = upload_received_proof(client, buyer_id)
    verify_proof(client, proof["id"])
    refreshed = client.post(
        f"/api/v1/dispositions/cases/{case_id}/buyer-pool/runs",
        headers=HEADERS,
    )
    assert refreshed.status_code == 200, refreshed.text
    candidate = next(
        item for item in refreshed.json()["entries"] if item["buyer_id"] == buyer_id
    )
    return case_id, candidate["candidate_id"]


def _unranked_execution_case(db: Session, client: TestClient) -> tuple[str, str]:
    _, transaction_id, buyer_id = setup_case_foundation(db, client)
    return create_approved_disposition_case(client, transaction_id), buyer_id


def _draft_unranked_execution_case(db: Session, client: TestClient) -> tuple[str, str]:
    _, transaction_id, buyer_id = setup_case_foundation(db, client)
    created = client.post(
        "/api/v1/dispositions/cases",
        headers=HEADERS,
        json={
            "transaction_id": transaction_id,
            "strategy": "assignment",
            "asking_price_cents": 19000000,
            "minimum_acceptable_cents": 18000000,
            "operating_mode_key": "human_led",
        },
    )
    assert created.status_code == 201, created.text
    return created.json()["id"], buyer_id


def _add_execution_sms_line(db: Session, owner: User) -> VoiceLine:
    line = VoiceLine(
        organization_id=owner.organization_id,
        assigned_user_id=owner.id,
        fallback_user_id=None,
        assigned_team_id=None,
        provider="twilio",
        provider_phone_number_id="PN-disposition-execution-sms",
        phone_number="+14705550199",
        label="Dispositions execution SMS",
        department_key="dispositions",
        purpose_key="buyer_relations",
        status="active",
        is_default=True,
        inbound_route="conversation_owner",
        ring_strategy="everyone_at_once",
        coverage_timezone="America/New_York",
        coverage_start_hour=0,
        coverage_end_hour=24,
        prospecting_dialer_max_concurrent_legs=1,
        missed_call_action="fallback_then_voicemail",
        line_metadata={"test": True},
    )
    db.add(line)
    return line


def test_disposition_cellphone_forwarding_remains_available_without_browser_credentials(
    db_session: Session,
    api_db_override: None,
    cellphone_voice_settings: None,
    monkeypatch: MonkeyPatch,
) -> None:
    class FakeVoiceProvider:
        def start(self, **kwargs: str) -> TwilioVoiceCallResult:
            return TwilioVoiceCallResult(
                sid="CA00000000000000000000000000000088",
                status="queued",
            )

    monkeypatch.setattr(
        "app.services.voice.get_twilio_voice_call_provider",
        lambda: FakeVoiceProvider(),
    )
    client = TestClient(app)
    case_id, buyer_id = _unranked_execution_case(db_session, client)
    buyer = db_session.get(Buyer, UUID(buyer_id))
    assert buyer is not None
    buyer.phone = "+14045550189"
    buyer.normalized_phone = "+14045550189"
    owner = db_session.scalar(select(User).where(User.email == CELL_FORWARD_OWNER_EMAIL))
    assert owner is not None
    owner.voice_forwarding_number = "+14045550100"
    owner.voice_forwarding_enabled = True
    line = db_session.scalar(select(VoiceLine))
    assert line is not None
    line.department_key = "dispositions"
    line.purpose_key = "buyer_relations"
    line.assigned_user_id = owner.id
    ensure_buyer_conversation(db_session, buyer, actor_user_id=owner.id)
    db_session.commit()
    workspace = client.get(
        f"/api/v1/dispositions/cases/{case_id}/execution",
        headers=HEADERS,
    )
    assert workspace.status_code == 200, workspace.text
    current_candidate = workspace.json()["current_candidate"]
    assert current_candidate["candidate_id"] is None
    assert current_candidate["buyer_id"] == buyer_id
    assert current_candidate["ranking_status"] == "unranked"
    assert current_candidate["voice"]["status"] == "missing"
    assert current_candidate["voice"]["allowed"] is True
    payload = {
        "buyer_id": buyer_id,
        "idempotency_key": "disposition-cellphone-fallback-001",
    }

    browser = client.post(
        f"/api/v1/dispositions/cases/{case_id}/execution/calls",
        headers=HEADERS,
        json=payload,
    )
    forwarded = client.post(
        f"/api/v1/dispositions/cases/{case_id}/execution/forwarded-calls",
        headers=HEADERS,
        json={**payload, "idempotency_key": "disposition-cellphone-fallback-002"},
    )

    assert browser.status_code == 503, browser.text
    assert "TWILIO_API_KEY_SID" in browser.text
    assert forwarded.status_code == 201, forwarded.text
    assert forwarded.json()["status"] == "started"
    intent = db_session.get(VoiceCallIntent, UUID(forwarded.json()["id"]))
    assert intent is not None
    assert intent.intent_metadata["source"] == "forwarded_cellphone"


def test_disposition_one_to_one_sms_treats_recorded_permission_as_advisory(
    db_session: Session,
    api_db_override: None,
    sms_settings: None,
    monkeypatch: MonkeyPatch,
) -> None:
    fake_provider = FakeSmsProvider()
    monkeypatch.setattr(
        "app.services.messaging.get_twilio_messaging_provider",
        lambda: fake_provider,
    )
    client = TestClient(app)
    case_id, buyer_id = _unranked_execution_case(db_session, client)
    buyer = db_session.get(Buyer, UUID(buyer_id))
    assert buyer is not None
    buyer.phone = "+14045550190"
    buyer.normalized_phone = "+14045550190"
    owner = db_session.scalar(select(User).where(User.email == CELL_FORWARD_OWNER_EMAIL))
    assert owner is not None
    _add_execution_sms_line(db_session, owner)
    conversation = ensure_buyer_conversation(db_session, buyer, actor_user_id=owner.id)
    db_session.commit()

    missing_workspace = client.get(
        f"/api/v1/dispositions/cases/{case_id}/execution",
        headers=HEADERS,
    )
    assert missing_workspace.status_code == 200, missing_workspace.text
    missing_sms = missing_workspace.json()["current_candidate"]["sms"]
    assert missing_workspace.json()["current_candidate"]["ranking_status"] == "unranked"
    assert missing_sms["status"] == "missing"
    assert missing_sms["allowed"] is True

    missing_send = client.post(
        f"/api/v1/dispositions/cases/{case_id}/execution/sms",
        headers=HEADERS,
        json={
            "buyer_id": buyer_id,
            "body": "Manual buyer introduction without a recorded permission label.",
            "idempotency_key": "dispo-sms-missing-001",
        },
    )
    assert missing_send.status_code == 201, missing_send.text
    assert len(fake_provider.requests) == 1

    db_session.add(
        ConsentRecord(
            organization_id=buyer.organization_id,
            contact_id=conversation.contact_id,
            channel="sms",
            status="revoked",
            source="phone_call",
            wording_version="manual-v1",
            wording="Buyer declined SMS permission during a phone call.",
            normalized_address="+14045550190",
            captured_ip=None,
            user_agent=None,
        )
    )
    db_session.commit()

    revoked_workspace = client.get(
        f"/api/v1/dispositions/cases/{case_id}/execution",
        headers=HEADERS,
    )
    assert revoked_workspace.status_code == 200, revoked_workspace.text
    revoked_sms = revoked_workspace.json()["current_candidate"]["sms"]
    assert revoked_sms["status"] == "revoked"
    assert revoked_sms["allowed"] is True

    revoked_send = client.post(
        f"/api/v1/dispositions/cases/{case_id}/execution/sms",
        headers=HEADERS,
        json={
            "buyer_id": buyer_id,
            "body": "Manual buyer follow-up with the advisory label preserved.",
            "idempotency_key": "dispo-sms-revoked-001",
        },
    )
    assert revoked_send.status_code == 201, revoked_send.text
    assert len(fake_provider.requests) == 2


def test_unranked_sms_candidate_collision_reuses_winner_and_replays_once(
    db_session: Session,
    api_db_override: None,
    sms_settings: None,
    monkeypatch: MonkeyPatch,
) -> None:
    fake_provider = FakeSmsProvider()
    monkeypatch.setattr(
        "app.services.messaging.get_twilio_messaging_provider",
        lambda: fake_provider,
    )
    client = TestClient(app)
    case_id, buyer_id = _draft_unranked_execution_case(db_session, client)
    case = db_session.get(DispositionCase, UUID(case_id))
    buyer = db_session.get(Buyer, UUID(buyer_id))
    owner = db_session.scalar(select(User).where(User.email == CELL_FORWARD_OWNER_EMAIL))
    assert case is not None and buyer is not None and owner is not None
    buyer.phone = "+14045550174"
    buyer.normalized_phone = "+14045550174"
    _add_execution_sms_line(db_session, owner)
    ensure_buyer_conversation(db_session, buyer, actor_user_id=owner.id)
    winner = disposition_execution._ensure_case_candidate(
        db_session,
        principal_for_user(db_session, owner),
        case,
        buyer,
    )
    db_session.commit()

    original_case_candidate = disposition_execution._case_candidate
    stale_read_pending = True

    def stale_once(*args: object, **kwargs: object):
        nonlocal stale_read_pending
        if stale_read_pending:
            stale_read_pending = False
            return None
        return original_case_candidate(*args, **kwargs)

    monkeypatch.setattr(disposition_execution, "_case_candidate", stale_once)
    payload = {
        "buyer_id": buyer_id,
        "body": "Direct Buyer Network introduction after a simulated insert race.",
        "idempotency_key": "unranked-sms-collision-001",
    }
    sent = client.post(
        f"/api/v1/dispositions/cases/{case_id}/execution/sms",
        headers=HEADERS,
        json=payload,
    )
    replayed = client.post(
        f"/api/v1/dispositions/cases/{case_id}/execution/sms",
        headers=HEADERS,
        json=payload,
    )
    conflicting = client.post(
        f"/api/v1/dispositions/cases/{case_id}/execution/sms",
        headers=HEADERS,
        json={**payload, "body": "Conflicting content must not reuse the same key."},
    )
    forged_buyer_id = create_active_buyer(
        client,
        name="Forged Idempotency Buyer",
        email="forged-idempotency@example.com",
    )
    forged_buyer = client.post(
        f"/api/v1/dispositions/cases/{case_id}/execution/sms",
        headers=HEADERS,
        json={**payload, "buyer_id": forged_buyer_id},
    )

    assert sent.status_code == 201, sent.text
    assert replayed.status_code == 201, replayed.text
    assert conflicting.status_code == 422, conflicting.text
    assert forged_buyer.status_code == 422, forged_buyer.text
    assert "different disposition action" in conflicting.json()["detail"]
    assert len(fake_provider.requests) == 1
    assert (
        db_session.scalar(
            select(func.count(DispositionBuyerPoolCandidate.id)).where(
                DispositionBuyerPoolCandidate.disposition_case_id == case.id,
                DispositionBuyerPoolCandidate.buyer_id == buyer.id,
            )
        )
        == 1
    )
    assert db_session.get(DispositionBuyerPoolCandidate, winner.id) is not None
    assert (
        db_session.scalar(
            select(func.count(DispositionBuyerPoolCandidate.id)).where(
                DispositionBuyerPoolCandidate.disposition_case_id == case.id,
                DispositionBuyerPoolCandidate.buyer_id == UUID(forged_buyer_id),
            )
        )
        == 0
    )
    assert (
        db_session.scalar(
            select(func.count(BuyerEngagement.id)).where(
                BuyerEngagement.idempotency_key == payload["idempotency_key"]
            )
        )
        == 1
    )


@pytest.mark.parametrize("dnc_field", ["status", "relationship_status"])
def test_execution_disables_channels_and_rejects_contact_for_buyer_dnc(
    db_session: Session,
    api_db_override: None,
    dnc_field: str,
) -> None:
    client = TestClient(app)
    case_id, candidate_id = _ready_execution_case(db_session, client)
    candidate = db_session.get(DispositionBuyerPoolCandidate, UUID(candidate_id))
    assert candidate is not None and candidate.buyer_id is not None
    buyer = db_session.get(Buyer, candidate.buyer_id)
    assert buyer is not None
    setattr(buyer, dnc_field, "do_not_contact")
    db_session.commit()

    workspace = client.get(
        f"/api/v1/dispositions/cases/{case_id}/execution",
        headers=HEADERS,
    )
    assert workspace.status_code == 200, workspace.text
    candidate_read = next(
        item
        for item in workspace.json()["candidates"]
        if item["candidate_id"] == candidate_id
    )
    for channel in ("sms", "voice"):
        permission = candidate_read[channel]
        assert permission["allowed"] is False
        assert any("do not contact" in item.lower() for item in permission["blockers"])

    sms = client.post(
        f"/api/v1/dispositions/cases/{case_id}/execution/sms",
        headers=HEADERS,
        json={
            "candidate_id": candidate_id,
            "body": "This message must never reach a DNC buyer.",
            "idempotency_key": f"dnc-{dnc_field}-sms-001",
        },
    )
    call = client.post(
        f"/api/v1/dispositions/cases/{case_id}/execution/calls",
        headers=HEADERS,
        json={
            "candidate_id": candidate_id,
            "idempotency_key": f"dnc-{dnc_field}-call-001",
        },
    )

    assert sms.status_code == 422, sms.text
    assert call.status_code == 422, call.text
    assert "do not contact" in sms.json()["detail"].lower()
    assert "do not contact" in call.json()["detail"].lower()


@pytest.mark.parametrize(
    ("advisory_field", "advisory_value"),
    [
        ("status", "paused"),
        ("status", "inactive"),
        ("relationship_status", "paused"),
        ("relationship_status", "inactive"),
    ],
)
def test_execution_treats_paused_and_inactive_buyer_states_as_advisory(
    db_session: Session,
    api_db_override: None,
    advisory_field: str,
    advisory_value: str,
) -> None:
    client = TestClient(app)
    case_id, candidate_id = _ready_execution_case(db_session, client)
    baseline = client.get(
        f"/api/v1/dispositions/cases/{case_id}/execution",
        headers=HEADERS,
    )
    assert baseline.status_code == 200, baseline.text
    baseline_candidate = next(
        item
        for item in baseline.json()["candidates"]
        if item["candidate_id"] == candidate_id
    )

    candidate = db_session.get(DispositionBuyerPoolCandidate, UUID(candidate_id))
    assert candidate is not None and candidate.buyer_id is not None
    buyer = db_session.get(Buyer, candidate.buyer_id)
    assert buyer is not None
    setattr(buyer, advisory_field, advisory_value)
    db_session.commit()

    workspace = client.get(
        f"/api/v1/dispositions/cases/{case_id}/execution",
        headers=HEADERS,
    )
    assert workspace.status_code == 200, workspace.text
    candidate_read = next(
        item
        for item in workspace.json()["candidates"]
        if item["candidate_id"] == candidate_id
    )
    assert candidate_read["sms"] == baseline_candidate["sms"]
    assert candidate_read["voice"] == baseline_candidate["voice"]

    worked = client.post(
        f"/api/v1/dispositions/cases/{case_id}/execution/outcomes",
        headers=HEADERS,
        json={
            "candidate_id": candidate_id,
            "outcome": "interested",
            "notes": "Paused and inactive labels remain advisory for active deal work.",
            "idempotency_key": f"advisory-{advisory_field}-{advisory_value}",
        },
    )
    assert worked.status_code == 200, worked.text


def test_unranked_buyer_can_record_outcome_and_showing_after_failed_pool_run(
    db_session: Session,
    api_db_override: None,
) -> None:
    client = TestClient(app)
    case_id, buyer_id = _draft_unranked_execution_case(db_session, client)
    case = db_session.get(DispositionCase, UUID(case_id))
    owner = db_session.scalar(select(User).where(User.email == CELL_FORWARD_OWNER_EMAIL))
    assert case is not None and owner is not None
    db_session.add(
        DispositionBuyerPoolRun(
            organization_id=case.organization_id,
            disposition_case_id=case.id,
            generated_by_user_id=owner.id,
            version_number=1,
            asset_class="house",
            matcher_version="failed-test-v1",
            score_policy_version="failed-test-v1",
            status="failed",
            input_snapshot={"test": "failed run must remain advisory"},
            input_fingerprint="f" * 64,
            source_counts={},
            started_at=datetime.now(UTC),
            completed_at=datetime.now(UTC),
        )
    )
    db_session.commit()

    workspace = client.get(
        f"/api/v1/dispositions/cases/{case_id}/execution",
        headers=HEADERS,
    )
    assert workspace.status_code == 200, workspace.text
    candidate = workspace.json()["current_candidate"]
    assert candidate["buyer_id"] == buyer_id
    assert candidate["candidate_id"] is None
    assert candidate["ranking_status"] == "unranked"
    assert candidate["rank"] is None
    assert candidate["score_basis_points"] is None
    assert candidate["actionable"] is True
    assert workspace.json()["package_status"] == "draft"
    assert workspace.json()["package_pdf_path"] is None
    assert workspace.json()["ready"] is True

    outcome = client.post(
        f"/api/v1/dispositions/cases/{case_id}/execution/outcomes",
        headers=HEADERS,
        json={
            "buyer_id": buyer_id,
            "outcome": "interested",
            "notes": "Worked directly from the canonical Buyer Network.",
            "idempotency_key": "unranked-network-outcome-001",
        },
    )
    assert outcome.status_code == 200, outcome.text
    persisted = next(
        item for item in outcome.json()["candidates"] if item["buyer_id"] == buyer_id
    )
    assert persisted["candidate_id"] is not None
    assert persisted["ranking_status"] == "unranked"

    showing = client.post(
        f"/api/v1/dispositions/cases/{case_id}/execution/showings",
        headers=HEADERS,
        json={
            "buyer_id": buyer_id,
            "scheduled_at": (datetime.now(UTC) + timedelta(days=1)).isoformat(),
            "access_status": "pending",
            "notes": "Showing scheduled without ranked-pool authority.",
            "idempotency_key": "unranked-network-showing-001",
        },
    )
    assert showing.status_code == 201, showing.text
    assert showing.json()["showings"][0]["buyer_id"] == buyer_id
    assert (
        db_session.scalar(
            select(func.count(DispositionBuyerPoolCandidate.id)).where(
                DispositionBuyerPoolCandidate.disposition_case_id == UUID(case_id),
                DispositionBuyerPoolCandidate.buyer_id == UUID(buyer_id),
            )
        )
        == 1
    )


def test_campaign_can_prepare_full_buyer_network_before_any_rank_run(
    db_session: Session,
    api_db_override: None,
) -> None:
    client = TestClient(app)
    case_id, buyer_id = _unranked_execution_case(db_session, client)

    released = client.post(
        f"/api/v1/dispositions/cases/{case_id}/campaigns/release",
        headers=HEADERS,
    )
    assert released.status_code == 200, released.text
    recipients = db_session.scalars(
        select(DispositionCampaignRecipient).where(
            DispositionCampaignRecipient.disposition_case_id == UUID(case_id)
        )
    ).all()
    assert [str(recipient.buyer_id) for recipient in recipients] == [buyer_id]


def test_new_canonical_buyer_is_immediately_actionable_after_ranked_run(
    db_session: Session,
    api_db_override: None,
) -> None:
    client = TestClient(app)
    case_id, ranked_candidate_id = _ready_execution_case(db_session, client)
    buyer_id = create_active_buyer(
        client,
        name="New Buyer Network Contact",
        email="new-network-contact@example.com",
    )

    workspace = client.get(
        f"/api/v1/dispositions/cases/{case_id}/execution",
        headers=HEADERS,
    )
    assert workspace.status_code == 200, workspace.text
    ranked = next(
        item
        for item in workspace.json()["candidates"]
        if item["candidate_id"] == ranked_candidate_id
    )
    assert ranked["ranking_status"] == "ranked"
    assert ranked["rank"] is not None
    assert ranked["score_basis_points"] is not None
    unranked = next(
        item for item in workspace.json()["candidates"] if item["buyer_id"] == buyer_id
    )
    assert unranked["candidate_id"] is None
    assert unranked["ranking_status"] == "unranked"
    assert unranked["rank"] is None
    assert unranked["score_basis_points"] is None
    assert unranked["actionable"] is True

    released = client.post(
        f"/api/v1/dispositions/cases/{case_id}/campaigns/release",
        headers=HEADERS,
    )
    assert released.status_code == 200, released.text
    recipient_buyer_ids = {
        str(buyer_id)
        for buyer_id in db_session.scalars(
            select(DispositionCampaignRecipient.buyer_id).where(
                DispositionCampaignRecipient.disposition_case_id == UUID(case_id)
            )
        ).all()
        if buyer_id is not None
    }
    assert buyer_id in recipient_buyer_ids

    worked = client.post(
        f"/api/v1/dispositions/cases/{case_id}/execution/outcomes",
        headers=HEADERS,
        json={
            "buyer_id": buyer_id,
            "outcome": "interested",
            "notes": "New canonical buyer worked without reranking.",
            "idempotency_key": "new-network-buyer-outcome-001",
        },
    )
    assert worked.status_code == 200, worked.text
    created_candidate = next(
        item for item in worked.json()["candidates"] if item["buyer_id"] == buyer_id
    )
    assert created_candidate["candidate_id"] is not None
    assert created_candidate["ranking_status"] == "unranked"

    mismatched = client.post(
        f"/api/v1/dispositions/cases/{case_id}/execution/showings",
        headers=HEADERS,
        json={
            "candidate_id": ranked_candidate_id,
            "buyer_id": buyer_id,
            "scheduled_at": (datetime.now(UTC) + timedelta(days=2)).isoformat(),
            "access_status": "pending",
            "idempotency_key": "mismatched-execution-reference-001",
        },
    )
    assert mismatched.status_code == 422, mismatched.text
    assert "do not match" in mismatched.json()["detail"].lower()


def test_unranked_terminal_pass_can_be_replayed_and_cleared_without_ranking(
    db_session: Session,
    api_db_override: None,
) -> None:
    client = TestClient(app)
    case_id, buyer_id = _unranked_execution_case(db_session, client)
    payload = {
        "buyer_id": buyer_id,
        "outcome": "not_interested",
        "notes": "Buyer passed for this deal after direct network outreach.",
        "idempotency_key": "unranked-terminal-pass-001",
    }

    recorded = client.post(
        f"/api/v1/dispositions/cases/{case_id}/execution/outcomes",
        headers=HEADERS,
        json=payload,
    )
    recorded_candidate = next(
        item for item in recorded.json()["candidates"] if item["buyer_id"] == buyer_id
    )
    replayed = client.post(
        f"/api/v1/dispositions/cases/{case_id}/execution/outcomes",
        headers=HEADERS,
        json={
            **payload,
            "buyer_id": None,
            "candidate_id": recorded_candidate["candidate_id"],
        },
    )
    assert recorded.status_code == 200, recorded.text
    assert replayed.status_code == 200, replayed.text
    passed = next(
        item for item in replayed.json()["candidates"] if item["buyer_id"] == buyer_id
    )
    assert passed["candidate_id"] is not None
    assert passed["decision_status"] == "passed"
    assert passed["actionable"] is False
    assert replayed.json()["current_candidate"] is None
    assert (
        db_session.scalar(
            select(func.count(BuyerEngagement.id)).where(
                BuyerEngagement.idempotency_key == payload["idempotency_key"]
            )
        )
        == 1
    )

    cleared = client.patch(
        f"/api/v1/dispositions/cases/{case_id}/buyer-pool/candidates/{passed['candidate_id']}",
        headers=HEADERS,
        json={
            "expected_version": passed["lock_version"],
            "decision_status": "undecided",
            "reason": "Buyer re-engaged; clear the deal-specific pass without a rank run.",
        },
    )
    assert cleared.status_code == 200, cleared.text
    assert cleared.json()["run"] is None
    restored = client.get(
        f"/api/v1/dispositions/cases/{case_id}/execution",
        headers=HEADERS,
    )
    assert restored.status_code == 200, restored.text
    restored_candidate = next(
        item for item in restored.json()["candidates"] if item["buyer_id"] == buyer_id
    )
    assert restored_candidate["decision_status"] == "undecided"
    assert restored_candidate["actionable"] is True


def test_do_not_contact_outcome_updates_canonical_suppression_and_blocks_later_work(
    db_session: Session,
    api_db_override: None,
) -> None:
    client = TestClient(app)
    case_id, buyer_id = _unranked_execution_case(db_session, client)
    buyer = db_session.get(Buyer, UUID(buyer_id))
    assert buyer is not None
    buyer.phone = "+14045550173"
    buyer.normalized_phone = "+14045550173"
    db_session.commit()
    payload = {
        "buyer_id": buyer_id,
        "outcome": "do_not_contact",
        "notes": "Buyer expressly requested no further calls or messages.",
        "idempotency_key": "unranked-dnc-outcome-001",
    }

    recorded = client.post(
        f"/api/v1/dispositions/cases/{case_id}/execution/outcomes",
        headers=HEADERS,
        json=payload,
    )
    replayed = client.post(
        f"/api/v1/dispositions/cases/{case_id}/execution/outcomes",
        headers=HEADERS,
        json=payload,
    )
    assert recorded.status_code == 200, recorded.text
    assert replayed.status_code == 200, replayed.text
    db_session.refresh(buyer)
    assert buyer.relationship_status == "do_not_contact"
    suppressions = db_session.scalars(
        select(SuppressionRecord)
        .where(
            SuppressionRecord.organization_id == buyer.organization_id,
            SuppressionRecord.normalized_address == buyer.normalized_phone,
            SuppressionRecord.status == "active",
        )
        .order_by(SuppressionRecord.channel)
    ).all()
    assert [(item.channel, item.source) for item in suppressions] == [
        ("phone", "buyer_lifecycle"),
        ("sms", "buyer_lifecycle"),
    ]
    assert (
        db_session.scalar(
            select(func.count(BuyerEngagement.id)).where(
                BuyerEngagement.idempotency_key == payload["idempotency_key"]
            )
        )
        == 1
    )
    candidate = next(
        item for item in replayed.json()["candidates"] if item["buyer_id"] == buyer_id
    )
    assert candidate["actionable"] is False
    assert any("do not contact" in item.lower() for item in candidate["action_blockers"])

    blocked_requests = [
        client.post(
            f"/api/v1/dispositions/cases/{case_id}/execution/sms",
            headers=HEADERS,
            json={
                "buyer_id": buyer_id,
                "body": "This must be blocked by canonical DNC.",
                "idempotency_key": "post-dnc-sms-001",
            },
        ),
        client.post(
            f"/api/v1/dispositions/cases/{case_id}/execution/calls",
            headers=HEADERS,
            json={
                "buyer_id": buyer_id,
                "idempotency_key": "post-dnc-call-001",
            },
        ),
        client.post(
            f"/api/v1/dispositions/cases/{case_id}/execution/outcomes",
            headers=HEADERS,
            json={
                "buyer_id": buyer_id,
                "outcome": "interested",
                "idempotency_key": "post-dnc-outcome-001",
            },
        ),
        client.post(
            f"/api/v1/dispositions/cases/{case_id}/execution/showings",
            headers=HEADERS,
            json={
                "buyer_id": buyer_id,
                "scheduled_at": (datetime.now(UTC) + timedelta(days=1)).isoformat(),
                "access_status": "pending",
                "idempotency_key": "post-dnc-showing-001",
            },
        ),
    ]
    assert [response.status_code for response in blocked_requests] == [422, 422, 422, 422]
    assert all(
        "do not contact" in response.json()["detail"].lower()
        for response in blocked_requests
    )

    refreshed = client.post(
        f"/api/v1/dispositions/cases/{case_id}/buyer-pool/runs",
        headers=HEADERS,
    )
    assert refreshed.status_code == 200, refreshed.text
    bulk = client.post(
        f"/api/v1/dispositions/cases/{case_id}/campaigns/release",
        headers=HEADERS,
    )
    assert bulk.status_code == 422, bulk.text
    assert "non-suppressed buyers" in bulk.json()["detail"].lower()


def test_no_answer_creates_retry_task_before_queue_advances(
    db_session: Session,
    api_db_override: None,
) -> None:
    client = TestClient(app)
    case_id, candidate_id = _ready_execution_case(db_session, client)

    workspace = client.get(
        f"/api/v1/dispositions/cases/{case_id}/execution",
        headers=HEADERS,
    )
    assert workspace.status_code == 200, workspace.text
    assert workspace.json()["current_candidate"]["candidate_id"] == candidate_id
    assert workspace.json()["package_pdf_path"].endswith("/package.pdf")

    started = datetime.now(UTC)
    recorded = client.post(
        f"/api/v1/dispositions/cases/{case_id}/execution/outcomes",
        headers=HEADERS,
        json={
            "candidate_id": candidate_id,
            "outcome": "no_answer",
            "notes": "Buyer did not answer the first one-to-one call.",
            "idempotency_key": "outcome-no-answer-001",
        },
    )

    assert recorded.status_code == 200, recorded.text
    assert recorded.json()["current_candidate"] is None
    task = db_session.scalar(
        select(Task).where(Task.task_type == "disposition_buyer_follow_up")
    )
    assert task is not None
    assert task.status == "open"
    assert task.due_at is not None
    due_at = task.due_at.replace(tzinfo=UTC) if task.due_at.tzinfo is None else task.due_at
    assert started + timedelta(hours=3, minutes=59) <= due_at
    assert due_at <= datetime.now(UTC) + timedelta(hours=4, minutes=1)

    replayed = client.post(
        f"/api/v1/dispositions/cases/{case_id}/execution/outcomes",
        headers=HEADERS,
        json={
            "candidate_id": candidate_id,
            "outcome": "no_answer",
            "notes": "Buyer did not answer the first one-to-one call.",
            "idempotency_key": "outcome-no-answer-001",
        },
    )
    assert replayed.status_code == 200, replayed.text
    assert (
        db_session.scalar(
            select(func.count(Task.id)).where(
                Task.task_type == "disposition_buyer_follow_up"
            )
        )
        == 1
    )
    assert (
        db_session.scalar(
            select(func.count(BuyerEngagement.id)).where(
                BuyerEngagement.idempotency_key == "outcome-no-answer-001"
            )
        )
        == 1
    )
    conflicting_replay = client.post(
        f"/api/v1/dispositions/cases/{case_id}/execution/outcomes",
        headers=HEADERS,
        json={
            "candidate_id": candidate_id,
            "outcome": "voicemail",
            "idempotency_key": "outcome-no-answer-001",
        },
    )
    assert conflicting_replay.status_code == 422, conflicting_replay.text
    assert "different disposition action" in conflicting_replay.json()["detail"]

    engagement = db_session.scalar(
        select(BuyerEngagement).where(
            BuyerEngagement.idempotency_key == "outcome-no-answer-001"
        )
    )
    assert engagement is not None
    task.due_at = datetime.now(UTC) - timedelta(minutes=1)
    engagement.engagement_metadata = {
        **(engagement.engagement_metadata or {}),
        "follow_up_at": task.due_at.isoformat(),
    }
    db_session.commit()

    due_workspace = client.get(
        f"/api/v1/dispositions/cases/{case_id}/execution",
        headers=HEADERS,
    )
    assert due_workspace.status_code == 200, due_workspace.text
    assert due_workspace.json()["current_candidate"]["candidate_id"] == candidate_id

    recontacted = client.post(
        f"/api/v1/dispositions/cases/{case_id}/execution/outcomes",
        headers=HEADERS,
        json={
            "candidate_id": candidate_id,
            "outcome": "interested",
            "notes": "Buyer answered the scheduled retry and requested the packet.",
            "idempotency_key": "outcome-interested-retry-001",
        },
    )
    assert recontacted.status_code == 200, recontacted.text
    db_session.refresh(task)
    assert task.status == "completed"
    assert task.completed_at is not None
    assert (
        db_session.scalar(
            select(func.count(BuyerEngagement.id)).where(
                BuyerEngagement.engagement_type == "call"
            )
        )
        == 2
    )


def test_callback_requires_time_and_preserves_future_work(
    db_session: Session,
    api_db_override: None,
) -> None:
    client = TestClient(app)
    case_id, candidate_id = _ready_execution_case(db_session, client)

    blocked = client.post(
        f"/api/v1/dispositions/cases/{case_id}/execution/outcomes",
        headers=HEADERS,
        json={
            "candidate_id": candidate_id,
            "outcome": "callback",
            "idempotency_key": "outcome-callback-missing-001",
        },
    )
    assert blocked.status_code == 422, blocked.text
    assert "follow-up date" in blocked.json()["detail"]

    past = client.post(
        f"/api/v1/dispositions/cases/{case_id}/execution/outcomes",
        headers=HEADERS,
        json={
            "candidate_id": candidate_id,
            "outcome": "callback",
            "follow_up_at": (datetime.now(UTC) - timedelta(minutes=1)).isoformat(),
            "idempotency_key": "outcome-callback-past-001",
        },
    )
    assert past.status_code == 422, past.text
    assert "must be in the future" in past.json()["detail"]

    callback_at = datetime.now(UTC) + timedelta(days=2)
    recorded = client.post(
        f"/api/v1/dispositions/cases/{case_id}/execution/outcomes",
        headers=HEADERS,
        json={
            "candidate_id": candidate_id,
            "outcome": "callback",
            "follow_up_at": callback_at.isoformat(),
            "idempotency_key": "outcome-callback-001",
        },
    )
    assert recorded.status_code == 200, recorded.text
    task = db_session.scalar(
        select(Task).where(Task.task_type == "disposition_buyer_follow_up")
    )
    assert task is not None and task.due_at is not None
    due_at = task.due_at.replace(tzinfo=UTC) if task.due_at.tzinfo is None else task.due_at
    assert abs((due_at - callback_at).total_seconds()) < 1


def test_completed_showing_creates_one_24_hour_follow_up_task(
    db_session: Session,
    api_db_override: None,
) -> None:
    client = TestClient(app)
    case_id, candidate_id = _ready_execution_case(db_session, client)
    scheduled_at = datetime.now(UTC) + timedelta(days=1)

    past = client.post(
        f"/api/v1/dispositions/cases/{case_id}/execution/showings",
        headers=HEADERS,
        json={
            "candidate_id": candidate_id,
            "scheduled_at": (datetime.now(UTC) - timedelta(minutes=1)).isoformat(),
            "access_status": "pending",
            "idempotency_key": "showing-create-past-001",
        },
    )
    assert past.status_code == 422, past.text
    assert "must be in the future" in past.json()["detail"]

    create_payload = {
        "candidate_id": candidate_id,
        "scheduled_at": scheduled_at.isoformat(),
        "access_status": "pending",
        "notes": "Access instructions will be shared privately.",
        "idempotency_key": "showing-create-001",
    }
    created = client.post(
        f"/api/v1/dispositions/cases/{case_id}/execution/showings",
        headers=HEADERS,
        json=create_payload,
    )
    assert created.status_code == 201, created.text
    showing = created.json()["showings"][0]
    assert showing["access_status"] == "pending"
    assert "code" not in showing
    replayed = client.post(
        f"/api/v1/dispositions/cases/{case_id}/execution/showings",
        headers=HEADERS,
        json=create_payload,
    )
    assert replayed.status_code == 201, replayed.text
    assert (
        db_session.scalar(
            select(func.count(BuyerEngagement.id)).where(
                BuyerEngagement.idempotency_key == "showing-create-001"
            )
        )
        == 1
    )

    invalid_reschedule = client.patch(
        f"/api/v1/dispositions/cases/{case_id}/execution/showings/{showing['id']}",
        headers=HEADERS,
        json={
            "status": "confirmed",
            "access_status": "confirmed",
            "scheduled_at": (datetime.now(UTC) - timedelta(minutes=1)).isoformat(),
            "notes": "Invalid past reschedule.",
        },
    )
    assert invalid_reschedule.status_code == 422, invalid_reschedule.text
    assert "must be in the future" in invalid_reschedule.json()["detail"]

    payload = {
        "status": "completed",
        "access_status": "shared_privately",
        "scheduled_at": scheduled_at.isoformat(),
        "notes": "Buyer completed the walkthrough.",
    }
    completed = client.patch(
        f"/api/v1/dispositions/cases/{case_id}/execution/showings/{showing['id']}",
        headers=HEADERS,
        json=payload,
    )
    assert completed.status_code == 200, completed.text
    assert completed.json()["showings"][0]["follow_up_task_id"] is not None
    repeated = client.patch(
        f"/api/v1/dispositions/cases/{case_id}/execution/showings/{showing['id']}",
        headers=HEADERS,
        json=payload,
    )
    assert repeated.status_code == 200, repeated.text
    reopened = client.patch(
        f"/api/v1/dispositions/cases/{case_id}/execution/showings/{showing['id']}",
        headers=HEADERS,
        json={**payload, "status": "confirmed"},
    )
    assert reopened.status_code == 422, reopened.text
    assert "cannot be reopened" in reopened.json()["detail"]
    assert (
        db_session.scalar(
            select(func.count(Task.id)).where(
                Task.task_type == "buyer_showing_follow_up"
            )
        )
        == 1
    )


def test_land_case_uses_the_same_one_to_one_execution_queue(
    db_session: Session,
    api_db_override: None,
) -> None:
    client = TestClient(app)
    case_id, _ = _ready_execution_case(db_session, client)
    lead = db_session.scalar(select(Lead).limit(1))
    assert lead is not None
    lead.asset_class = "land"
    db_session.commit()

    response = client.get(
        f"/api/v1/dispositions/cases/{case_id}/execution",
        headers=HEADERS,
    )
    assert response.status_code == 200, response.text
    assert response.json()["asset_class"] == "land"
    assert response.json()["ready"] is True
    assert response.json()["current_candidate"] is not None
    assert response.json()["candidates"]
    assert not any("house deals only" in item for item in response.json()["blockers"])


def test_explicit_pass_is_visible_but_not_actionable_until_cleared(
    db_session: Session,
    api_db_override: None,
) -> None:
    client = TestClient(app)
    case_id, candidate_id = _ready_execution_case(db_session, client)
    candidate = db_session.get(DispositionBuyerPoolCandidate, UUID(candidate_id))
    assert candidate is not None
    passed = client.patch(
        f"/api/v1/dispositions/cases/{case_id}/buyer-pool/candidates/{candidate_id}",
        headers=HEADERS,
        json={
            "expected_version": candidate.lock_version,
            "decision_status": "passed",
            "reason": "The buyer explicitly declined this opportunity.",
        },
    )
    assert passed.status_code == 200, passed.text
    passed_entry = next(
        item for item in passed.json()["entries"] if item["candidate_id"] == candidate_id
    )

    workspace = client.get(
        f"/api/v1/dispositions/cases/{case_id}/execution",
        headers=HEADERS,
    )
    assert workspace.status_code == 200, workspace.text
    assert len(workspace.json()["candidates"]) == 1
    passed_candidate = workspace.json()["candidates"][0]
    assert passed_candidate["candidate_id"] == candidate_id
    assert passed_candidate["actionable"] is False
    assert passed_candidate["decision_status"] == "passed"
    assert any("explicitly passed" in item for item in passed_candidate["action_blockers"])
    assert workspace.json()["current_candidate"] is None
    blocked = client.post(
        f"/api/v1/dispositions/cases/{case_id}/execution/outcomes",
        headers=HEADERS,
        json={
            "candidate_id": candidate_id,
            "outcome": "interested",
            "notes": "A passed candidate must first be cleared by the operator.",
            "idempotency_key": "passed-candidate-action-001",
        },
    )
    assert blocked.status_code == 422, blocked.text
    assert "explicitly passed" in blocked.json()["detail"].lower()

    cleared = client.patch(
        f"/api/v1/dispositions/cases/{case_id}/buyer-pool/candidates/{candidate_id}",
        headers=HEADERS,
        json={
            "expected_version": passed_entry["lock_version"],
            "decision_status": "undecided",
            "reason": "The rep cleared the prior pass after the buyer re-engaged.",
        },
    )
    assert cleared.status_code == 200, cleared.text
    restored = client.get(
        f"/api/v1/dispositions/cases/{case_id}/execution",
        headers=HEADERS,
    )
    assert restored.status_code == 200, restored.text
    assert [item["candidate_id"] for item in restored.json()["candidates"]] == [
        candidate_id
    ]
    assert restored.json()["candidates"][0]["actionable"] is True


def test_execution_returns_and_can_work_a_ranked_buyer_beyond_first_pool_page(
    db_session: Session,
    api_db_override: None,
) -> None:
    client = TestClient(app)
    case_id, _ = _ready_execution_case(db_session, client)
    owner = db_session.scalar(select(User).where(User.email == CELL_FORWARD_OWNER_EMAIL))
    assert owner is not None

    tail_buyer = Buyer(
        organization_id=owner.organization_id,
        name="AAA Pagination Tail Buyer",
        company_name=None,
        email="pagination-tail@example.com",
        phone=None,
        normalized_email="pagination-tail@example.com",
        normalized_phone=None,
        normalized_company_name=None,
        buyer_type="cash_buyer",
        status="active",
        source_key="pagination_test",
        source_detail="Execution workspace pagination regression",
        source_external_key="pagination-tail",
        created_by_user_id=owner.id,
        relationship_owner_user_id=owner.id,
        proof_of_funds_status="unknown",
    )
    db_session.add(tail_buyer)
    for index in range(100):
        email = f"pagination-buyer-{index:03d}@example.com"
        db_session.add(
            Buyer(
                organization_id=owner.organization_id,
                name=f"ZZZ Pagination Buyer {index:03d}",
                company_name=None,
                email=email,
                phone=None,
                normalized_email=email,
                normalized_phone=None,
                normalized_company_name=None,
                buyer_type="cash_buyer",
                status="active",
                source_key="pagination_test",
                source_detail="Execution workspace pagination regression",
                source_external_key=f"pagination-{index:03d}",
                created_by_user_id=owner.id,
                relationship_owner_user_id=owner.id,
                proof_of_funds_status="unknown",
            )
        )
    db_session.commit()

    refreshed = client.post(
        f"/api/v1/dispositions/cases/{case_id}/buyer-pool/runs",
        headers=HEADERS,
    )
    assert refreshed.status_code == 200, refreshed.text
    latest_run = db_session.scalar(
        select(DispositionBuyerPoolRun)
        .where(DispositionBuyerPoolRun.disposition_case_id == UUID(case_id))
        .order_by(DispositionBuyerPoolRun.version_number.desc())
    )
    assert latest_run is not None
    tail_candidate = db_session.scalar(
        select(DispositionBuyerPoolCandidate).where(
            DispositionBuyerPoolCandidate.disposition_case_id == UUID(case_id),
            DispositionBuyerPoolCandidate.buyer_id == tail_buyer.id,
        )
    )
    assert tail_candidate is not None
    tail_entry = db_session.scalar(
        select(DispositionBuyerPoolEntry).where(
            DispositionBuyerPoolEntry.buyer_pool_run_id == latest_run.id,
            DispositionBuyerPoolEntry.buyer_pool_candidate_id == tail_candidate.id,
        )
    )
    assert tail_entry is not None
    assert tail_entry.rank > 100

    workspace = client.get(
        f"/api/v1/dispositions/cases/{case_id}/execution",
        headers=HEADERS,
    )
    assert workspace.status_code == 200, workspace.text
    candidates = workspace.json()["candidates"]
    candidate_ids = [item["candidate_id"] for item in candidates]
    assert str(tail_candidate.id) in candidate_ids
    assert len(candidate_ids) == len(set(candidate_ids))
    assert [item["rank"] for item in candidates] == sorted(
        item["rank"] for item in candidates
    )
    assert workspace.json()["remaining_candidate_count"] == len(candidates)

    worked = client.post(
        f"/api/v1/dispositions/cases/{case_id}/execution/outcomes",
        headers=HEADERS,
        json={
            "candidate_id": str(tail_candidate.id),
            "outcome": "interested",
            "notes": "Buyer beyond the first ranked-pool page requested the package.",
            "idempotency_key": "execution-pagination-tail-001",
        },
    )
    assert worked.status_code == 200, worked.text
    assert worked.json()["remaining_candidate_count"] == len(candidates) - 1


def test_disposition_execution_migration_is_linear_and_reversible() -> None:
    migration = run_path(
        str(
            Path(__file__).parents[1]
            / "alembic"
            / "versions"
            / "0122_disposition_execution.py"
        )
    )
    assert migration["revision"] == "0122_disposition_execution"
    assert migration["down_revision"] == "0121_dealmachine_buyer_tiers"


def test_execution_session_restores_operator_position_drafts_and_queue_order(
    db_session: Session,
    api_db_override: None,
) -> None:
    client = TestClient(app)
    case_id, first_buyer_id = _unranked_execution_case(db_session, client)
    second_buyer_id = create_active_buyer(
        client,
        name="Second Durable Session Buyer",
        email="second-durable-session@example.com",
    )
    initial = client.get(
        f"/api/v1/dispositions/cases/{case_id}/execution",
        headers=HEADERS,
    )
    assert initial.status_code == 200, initial.text
    initial_order = [item["buyer_id"] for item in initial.json()["candidates"]]
    assert set(initial_order) == {first_buyer_id, second_buyer_id}
    active_buyer_id = initial_order[-1]
    skipped_buyer_id = initial_order[0]
    callback_at = datetime.now(UTC) + timedelta(days=3)

    saved = client.patch(
        f"/api/v1/dispositions/cases/{case_id}/execution/session",
        headers=HEADERS,
        json={
            "state": "paused",
            "current_buyer_id": active_buyer_id,
            "skipped_buyer_ids": [skipped_buyer_id],
            "buyer_id": active_buyer_id,
            "sms_draft": "Saved private one-to-one investor draft.",
            "notes_draft": "Resume with the requested terms in view.",
            "callback_at": callback_at.isoformat(),
            "selected_outcome": "callback",
            "current_step": "outcome",
        },
    )
    assert saved.status_code == 200, saved.text
    session = saved.json()["session"]
    assert session["persisted"] is True
    assert session["state"] == "paused"
    assert session["current_buyer_id"] == active_buyer_id
    assert session["skipped_buyer_ids"] == [skipped_buyer_id]
    assert session["queue_buyer_ids"] == initial_order
    buyer_state = session["buyer_states"][active_buyer_id]
    assert buyer_state["sms_draft"] == "Saved private one-to-one investor draft."
    assert buyer_state["notes_draft"] == "Resume with the requested terms in view."
    assert buyer_state["selected_outcome"] == "callback"
    assert buyer_state["current_step"] == "outcome"

    restored = client.get(
        f"/api/v1/dispositions/cases/{case_id}/execution",
        headers=HEADERS,
    )
    assert restored.status_code == 200, restored.text
    assert restored.json()["session"]["current_buyer_id"] == active_buyer_id
    restored_candidate = next(
        item for item in restored.json()["candidates"] if item["buyer_id"] == active_buyer_id
    )
    assert restored_candidate["sms_draft"] == "Saved private one-to-one investor draft."

    third_buyer_id = create_active_buyer(
        client,
        name="A Newly Ranked Buyer Must Append",
        email="newly-ranked-append@example.com",
    )
    expanded = client.get(
        f"/api/v1/dispositions/cases/{case_id}/execution",
        headers=HEADERS,
    )
    assert expanded.status_code == 200, expanded.text
    expanded_order = expanded.json()["session"]["queue_buyer_ids"]
    assert expanded_order[:2] == initial_order
    assert expanded_order[-1] == third_buyer_id
    assert [item["buyer_id"] for item in expanded.json()["candidates"]] == expanded_order
    stored_session = db_session.scalar(
        select(DispositionExecutionSession).where(
            DispositionExecutionSession.disposition_case_id == UUID(case_id)
        )
    )
    assert stored_session is not None
    assert stored_session.operator_user_id is not None


def test_execution_outcome_updates_durable_last_result_and_follow_up(
    db_session: Session,
    api_db_override: None,
) -> None:
    client = TestClient(app)
    case_id, buyer_id = _unranked_execution_case(db_session, client)
    recorded = client.post(
        f"/api/v1/dispositions/cases/{case_id}/execution/outcomes",
        headers=HEADERS,
        json={
            "buyer_id": buyer_id,
            "outcome": "no_answer",
            "notes": "Persist this retry across visits.",
            "idempotency_key": "durable-session-no-answer-001",
        },
    )
    assert recorded.status_code == 200, recorded.text
    session = recorded.json()["session"]
    assert session["persisted"] is True
    assert session["current_buyer_id"] == buyer_id
    assert session["last_outcome"] == "no_answer"
    assert session["last_outcome_buyer_id"] == buyer_id
    assert session["last_outcome_at"] is not None
    assert session["follow_up_at"] is not None
    buyer_state = session["buyer_states"][buyer_id]
    assert buyer_state["call_status"] == "completed"
    assert buyer_state["current_step"] == "outcome"
    assert buyer_state["selected_outcome"] == "no_answer"
    assert buyer_state["notes_draft"] == "Persist this retry across visits."


def test_durable_execution_session_migration_follows_advisory_workbench() -> None:
    migration = run_path(
        str(
            Path(__file__).parents[1]
            / "alembic"
            / "versions"
            / "0124_disposition_execution_sessions.py"
        )
    )
    assert migration["revision"] == "0124_disposition_sessions"
    assert migration["down_revision"] == "0123_disposition_advisory"
