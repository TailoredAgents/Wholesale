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

from app.core.config import get_settings
from app.integrations.communications import OutboundMessageRequest, OutboundMessageResult
from app.integrations.twilio_voice_calls import TwilioVoiceCallResult
from app.main import app
from app.models.foundation import (
    Buyer,
    BuyerEngagement,
    ConsentRecord,
    DispositionBuyerPoolCandidate,
    Lead,
    Task,
    User,
    VoiceCallIntent,
    VoiceLine,
)
from app.services.inbox import ensure_buyer_conversation
from tests.test_dispositions import (
    HEADERS,
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
    case_id, candidate_id = _ready_execution_case(db_session, client)
    candidate = db_session.get(DispositionBuyerPoolCandidate, UUID(candidate_id))
    assert candidate is not None
    assert candidate.buyer_id is not None
    buyer = db_session.get(Buyer, candidate.buyer_id)
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
    assert current_candidate["voice"]["status"] == "missing"
    assert current_candidate["voice"]["allowed"] is True
    payload = {
        "candidate_id": candidate_id,
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
    case_id, candidate_id = _ready_execution_case(db_session, client)
    candidate = db_session.get(DispositionBuyerPoolCandidate, UUID(candidate_id))
    assert candidate is not None and candidate.buyer_id is not None
    buyer = db_session.get(Buyer, candidate.buyer_id)
    assert buyer is not None
    buyer.phone = "+14045550190"
    buyer.normalized_phone = "+14045550190"
    owner = db_session.scalar(select(User).where(User.email == CELL_FORWARD_OWNER_EMAIL))
    assert owner is not None
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
    db_session.add(line)
    conversation = ensure_buyer_conversation(db_session, buyer, actor_user_id=owner.id)
    db_session.commit()

    missing_workspace = client.get(
        f"/api/v1/dispositions/cases/{case_id}/execution",
        headers=HEADERS,
    )
    assert missing_workspace.status_code == 200, missing_workspace.text
    missing_sms = missing_workspace.json()["current_candidate"]["sms"]
    assert missing_sms["status"] == "missing"
    assert missing_sms["allowed"] is True

    missing_send = client.post(
        f"/api/v1/dispositions/cases/{case_id}/execution/sms",
        headers=HEADERS,
        json={
            "candidate_id": candidate_id,
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
            "candidate_id": candidate_id,
            "body": "Manual buyer follow-up with the advisory label preserved.",
            "idempotency_key": "dispo-sms-revoked-001",
        },
    )
    assert revoked_send.status_code == 201, revoked_send.text
    assert len(fake_provider.requests) == 2


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


def test_land_case_is_visible_but_execution_is_blocked(
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
    assert response.json()["ready"] is False
    assert response.json()["current_candidate"] is None
    assert any("house deals only" in item for item in response.json()["blockers"])


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
