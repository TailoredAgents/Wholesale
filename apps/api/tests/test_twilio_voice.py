from collections.abc import Iterator
from datetime import datetime
from typing import cast
from urllib.parse import urlencode
from uuid import UUID
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient
from httpx import Response
from pytest import MonkeyPatch
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from twilio.request_validator import RequestValidator  # type: ignore[import-untyped]

from app.core.config import get_settings
from app.integrations.twilio_voice_calls import TwilioVoiceCallResult
from app.main import app
from app.models.foundation import (
    AuditEvent,
    CallRecord,
    CallRecording,
    CallTranscript,
    CommunicationProviderEvent,
    Contact,
    Conversation,
    Lead,
    Role,
    RoleAssignment,
    Task,
    User,
    VoiceCallIntent,
    VoiceLine,
)
from app.services.bootstrap import bootstrap_foundation
from app.services.communication_compliance import (
    is_within_sms_allowed_hours,
    is_within_voice_allowed_hours,
)
from app.services.voice import purge_next_expired_recording

OWNER_EMAIL = "owner@example.com"
AUTH_TOKEN = "test-voice-auth-token"
ACCOUNT_SID = "AC00000000000000000000000000000000"
API_KEY_SID = "SK00000000000000000000000000000000"
TWIML_APP_SID = "AP00000000000000000000000000000000"
STONEGATE_NUMBER = "+16785417725"
SELLER_NUMBER = "+14045551212"
WEBHOOK_BASE_URL = "https://api.stonegate.test"


@pytest.fixture
def voice_settings(monkeypatch: MonkeyPatch) -> Iterator[None]:
    values = {
        "TWILIO_VOICE_ENABLED": "true",
        "TWILIO_ACCOUNT_SID": ACCOUNT_SID,
        "TWILIO_AUTH_TOKEN": AUTH_TOKEN,
        "TWILIO_API_KEY_SID": API_KEY_SID,
        "TWILIO_API_KEY_SECRET": "test-api-key-secret-with-at-least-32-bytes",
        "TWILIO_TWIML_APP_SID": TWIML_APP_SID,
        "TWILIO_VOICE_FROM_NUMBER": STONEGATE_NUMBER,
        "TWILIO_WEBHOOK_BASE_URL": WEBHOOK_BASE_URL,
        "TWILIO_VALIDATE_WEBHOOK_SIGNATURES": "true",
        "TWILIO_SMS_ALLOWED_START_HOUR": "0",
        "TWILIO_SMS_ALLOWED_END_HOUR": "24",
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


def public_payload() -> dict[str, object]:
    return {
        "property_address": "55 Auburn Ave",
        "property_city": "Atlanta",
        "property_state": "GA",
        "property_postal_code": "30303",
        "name": "Sam Seller",
        "phone": "4045551212",
        "email": "sam@example.com",
        "preferred_contact_method": "phone",
        "reason_for_selling": "Inherited property",
        "desired_timeline": "30 days",
        "consent_to_contact": True,
    }


def seed_voice_lead(db: Session, client: TestClient) -> Conversation:
    bootstrap_foundation(
        db,
        organization_name="Stonegate Home Buyers",
        admin_email=OWNER_EMAIL,
        admin_name="Owner",
    )
    response = client.post("/api/v1/public/seller-leads", json=public_payload())
    assert response.status_code == 201
    conversation = db.scalar(select(Conversation))
    assert conversation is not None
    line = db.scalar(select(VoiceLine))
    assert line is not None
    owner = db.scalar(select(User).where(User.email == OWNER_EMAIL))
    assert owner is not None
    owner.voice_forwarding_number = "+14045550100"
    owner.voice_forwarding_enabled = True
    line.coverage_start_hour = 0
    line.coverage_end_hour = 24
    db.commit()
    return conversation


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


def create_intent(client: TestClient, conversation: Conversation) -> dict[str, object]:
    response = client.post(
        f"/api/v1/voice/conversations/{conversation.id}/call-intents",
        headers={"X-Dev-User-Email": OWNER_EMAIL},
        json={"idempotency_key": "voice-call-request-0001"},
    )
    assert response.status_code == 201
    return cast(dict[str, object], response.json())


def test_sms_and_voice_contact_hours_are_independent(monkeypatch: MonkeyPatch) -> None:
    monkeypatch.setenv("TWILIO_SMS_ALLOWED_START_HOUR", "0")
    monkeypatch.setenv("TWILIO_SMS_ALLOWED_END_HOUR", "24")
    monkeypatch.setenv("TWILIO_VOICE_ALLOWED_START_HOUR", "9")
    monkeypatch.setenv("TWILIO_VOICE_ALLOWED_END_HOUR", "20")
    get_settings.cache_clear()
    settings = get_settings()
    late_evening = datetime(2026, 7, 17, 21, 30, tzinfo=ZoneInfo("America/New_York"))

    assert is_within_sms_allowed_hours(settings, now=late_evening) is True
    assert is_within_voice_allowed_hours(settings, now=late_evening) is False
    get_settings.cache_clear()


def test_phone_line_ownership_records_department_primary_fallback_and_coverage(
    db_session: Session,
    api_db_override: None,
    voice_settings: None,
) -> None:
    client = TestClient(app)
    seed_voice_lead(db_session, client)
    headers = {"X-Dev-User-Email": OWNER_EMAIL}

    devon_response = client.post(
        "/api/v1/operations/users",
        headers=headers,
        json={
            "email": "devon@example.com",
            "display_name": "Devon",
            "role_key": "disposition_rep",
        },
    )
    assert devon_response.status_code == 201, devon_response.text
    devon = devon_response.json()

    lines_response = client.get("/api/v1/voice/lines", headers=headers)
    assert lines_response.status_code == 200, lines_response.text
    line_payload = lines_response.json()
    acquisitions_line = line_payload["items"][0]
    owner = next(user for user in line_payload["users"] if user["email"] == OWNER_EMAIL)
    assert any(user["id"] == devon["id"] for user in line_payload["users"])

    for user_id, cellphone in (
        (owner["id"], "+14045550100"),
        (devon["id"], "+14045550101"),
    ):
        forwarding_response = client.patch(
            f"/api/v1/voice/users/{user_id}/forwarding",
            headers=headers,
            json={
                "voice_forwarding_number": cellphone,
                "voice_forwarding_enabled": True,
            },
        )
        assert forwarding_response.status_code == 200, forwarding_response.text

    update_response = client.patch(
        f"/api/v1/voice/lines/{acquisitions_line['id']}",
        headers=headers,
        json={
            "label": "Stonegate Acquisitions",
            "department_key": "acquisitions",
            "purpose_key": "seller_conversations",
            "assigned_user_id": owner["id"],
            "fallback_user_id": devon["id"],
            "inbound_route": "conversation_owner",
            "coverage_timezone": "America/New_York",
            "coverage_start_hour": 0,
            "coverage_end_hour": 24,
            "missed_call_action": "fallback_then_voicemail",
            "is_default": True,
        },
    )
    assert update_response.status_code == 200, update_response.text
    updated = update_response.json()
    assert updated["department_key"] == "acquisitions"
    assert updated["purpose_key"] == "seller_conversations"
    assert updated["assigned_user_name"] == "Owner"
    assert updated["fallback_user_name"] == "Devon"
    assert updated["coverage_start_hour"] == 0
    assert updated["coverage_end_hour"] == 24
    assert updated["ownership_complete"] is True

    readiness_response = client.get("/api/v1/voice/readiness", headers=headers)
    assert readiness_response.status_code == 200, readiness_response.text
    readiness = readiness_response.json()
    assert readiness["configured"] is True
    assert readiness["line_phone_number"] == STONEGATE_NUMBER
    assert readiness["inbound_webhook_url"].endswith("/voice/incoming")
    assert readiness["outbound_twiml_app_url"].endswith("/voice/outbound")
    assert AUTH_TOKEN not in readiness_response.text

    duplicate_owner_response = client.patch(
        f"/api/v1/voice/lines/{acquisitions_line['id']}",
        headers=headers,
        json={
            "assigned_user_id": owner["id"],
            "fallback_user_id": owner["id"],
        },
    )
    assert duplicate_owner_response.status_code == 422
    assert "different people" in duplicate_owner_response.json()["detail"]

    dispositions_response = client.post(
        "/api/v1/voice/lines",
        headers=headers,
        json={
            "phone_number": "+14705550123",
            "label": "Stonegate Dispositions",
            "department_key": "dispositions",
            "purpose_key": "buyer_relations",
            "assigned_user_id": devon["id"],
            "fallback_user_id": owner["id"],
            "inbound_route": "assigned_user",
            "coverage_timezone": "America/New_York",
            "coverage_start_hour": 9,
            "coverage_end_hour": 20,
            "missed_call_action": "fallback_then_voicemail",
        },
    )
    assert dispositions_response.status_code == 201, dispositions_response.text
    dispositions = dispositions_response.json()
    assert dispositions["department_key"] == "dispositions"
    assert dispositions["purpose_key"] == "buyer_relations"
    assert dispositions["assigned_user_name"] == "Devon"
    assert dispositions["fallback_user_name"] == "Owner"
    assert dispositions["ownership_complete"] is True

    owner_record = db_session.get(User, UUID(owner["id"]))
    assert owner_record is not None
    owner_record.is_active = False
    db_session.commit()
    inbound_path = "/api/v1/webhooks/twilio/voice/incoming"
    inbound_payload = {
        "From": "+14045559876",
        "To": STONEGATE_NUMBER,
        "CallSid": "CA00000000000000000000000000000081",
    }
    inbound_response = post_signed(client, inbound_path, inbound_payload)
    assert inbound_response.status_code == 200, inbound_response.text
    assert "+14045550101" in inbound_response.text
    assert "<Client " not in inbound_response.text


def test_shared_line_rings_multiple_users_and_attributes_the_answer(
    db_session: Session,
    api_db_override: None,
    voice_settings: None,
) -> None:
    client = TestClient(app)
    seed_voice_lead(db_session, client)
    headers = {"X-Dev-User-Email": OWNER_EMAIL}
    devon_response = client.post(
        "/api/v1/operations/users",
        headers=headers,
        json={
            "email": "devon@example.com",
            "display_name": "Devon",
            "role_key": "disposition_rep",
        },
    )
    assert devon_response.status_code == 201, devon_response.text
    devon = devon_response.json()
    line_payload = client.get("/api/v1/voice/lines", headers=headers).json()
    line = line_payload["items"][0]
    owner = next(user for user in line_payload["users"] if user["email"] == OWNER_EMAIL)
    team_response = client.post(
        "/api/v1/operations/teams",
        headers=headers,
        json={
            "name": "Acquisitions",
            "team_type": "acquisitions",
            "manager_user_id": owner["id"],
        },
    )
    assert team_response.status_code == 201, team_response.text
    team = team_response.json()
    member_response = client.post(
        f"/api/v1/operations/teams/{team['id']}/members",
        headers=headers,
        json={"user_id": devon["id"], "membership_role": "member"},
    )
    assert member_response.status_code == 200, member_response.text
    line_payload = client.get("/api/v1/voice/lines", headers=headers).json()
    assert any(item["id"] == team["id"] for item in line_payload["teams"])
    updated = client.patch(
        f"/api/v1/voice/lines/{line['id']}",
        headers=headers,
        json={
            "assigned_user_id": owner["id"],
            "fallback_user_id": devon["id"],
            "assigned_team_id": team["id"],
            "ring_strategy": "simultaneous",
            "coverage_start_hour": 0,
            "coverage_end_hour": 24,
        },
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["assigned_team_name"] == "Acquisitions"
    for user_id, cellphone in (
        (owner["id"], "+14045550101"),
        (devon["id"], "+14045550102"),
    ):
        forwarding = client.patch(
            f"/api/v1/voice/users/{user_id}/forwarding",
            headers=headers,
            json={
                "voice_forwarding_number": cellphone,
                "voice_forwarding_enabled": True,
            },
        )
        assert forwarding.status_code == 200, forwarding.text
        assert forwarding.json()["voice_forwarding_number"] == cellphone
        assert forwarding.json()["voice_forwarding_enabled"] is True

    inbound_payload = {
        "From": SELLER_NUMBER,
        "To": STONEGATE_NUMBER,
        "CallSid": "CA00000000000000000000000000000082",
    }
    inbound = post_signed(
        client,
        "/api/v1/webhooks/twilio/voice/incoming",
        inbound_payload,
    )

    assert inbound.status_code == 200, inbound.text
    assert "<Client " not in inbound.text
    assert inbound.text.count("<Number ") == 2
    assert "/voice/screen" in inbound.text
    assert 'sequential="false"' in inbound.text
    call = db_session.scalar(select(CallRecord))
    assert call is not None
    assert call.call_metadata["ring_user_count"] == 2
    assert call.call_metadata["ring_target_count"] == 2

    mobile_screen_path = (
        f"/api/v1/webhooks/twilio/voice/screen?call_id={call.id}"
        f"&answered_user_id={devon['id']}&mobile=true"
    )
    mobile_screen = post_signed(
        client,
        mobile_screen_path,
        {"CallSid": "CA00000000000000000000000000000086"},
    )
    assert mobile_screen.status_code == 200, mobile_screen.text
    assert "Stonegate acquisitions call" in mobile_screen.text
    assert "Press 1 to accept" in mobile_screen.text
    assert "<Gather" in mobile_screen.text

    screen_result_path = (
        f"/api/v1/webhooks/twilio/voice/screen-result?call_id={call.id}"
        f"&answered_user_id={devon['id']}"
    )
    screen_result = post_signed(
        client,
        screen_result_path,
        {
            "CallSid": "CA00000000000000000000000000000086",
            "Digits": "1",
        },
    )
    assert screen_result.status_code == 200, screen_result.text
    assert "<Hangup" not in screen_result.text
    db_session.refresh(call)
    assert str(call.actor_user_id) == devon["id"]
    assert call.call_metadata["mobile_screen_accepted_by_user_id"] == devon["id"]

    answered_path = (
        f"/api/v1/webhooks/twilio/voice/status?call_id={call.id}"
        f"&answered_user_id={devon['id']}"
    )
    answered = post_signed(
        client,
        answered_path,
        {
            "CallSid": "CA00000000000000000000000000000083",
            "ParentCallSid": inbound_payload["CallSid"],
            "CallStatus": "in-progress",
        },
    )
    assert answered.status_code == 204, answered.text
    db_session.refresh(call)
    assert str(call.actor_user_id) == devon["id"]
    assert call.status == "in-progress"

    canceled_path = (
        f"/api/v1/webhooks/twilio/voice/status?call_id={call.id}"
        f"&answered_user_id={owner['id']}"
    )
    canceled = post_signed(
        client,
        canceled_path,
        {
            "CallSid": "CA00000000000000000000000000000084",
            "ParentCallSid": inbound_payload["CallSid"],
            "CallStatus": "canceled",
        },
    )
    assert canceled.status_code == 204, canceled.text
    db_session.refresh(call)
    assert call.status == "in-progress"
    assert str(call.actor_user_id) == devon["id"]


def test_after_hours_call_uses_voicemail_and_creates_follow_up(
    db_session: Session,
    api_db_override: None,
    voice_settings: None,
) -> None:
    client = TestClient(app)
    seed_voice_lead(db_session, client)
    line = db_session.scalar(select(VoiceLine))
    assert line is not None
    local_hour = datetime.now(ZoneInfo("America/New_York")).hour
    line.coverage_start_hour = (local_hour + 1) % 24
    line.coverage_end_hour = (local_hour + 2) % 24
    line.missed_call_action = "fallback_then_voicemail"
    db_session.commit()
    inbound_payload = {
        "From": SELLER_NUMBER,
        "To": STONEGATE_NUMBER,
        "CallSid": "CA00000000000000000000000000000085",
    }

    inbound = post_signed(
        client,
        "/api/v1/webhooks/twilio/voice/incoming",
        inbound_payload,
    )

    assert inbound.status_code == 200, inbound.text
    assert "<Record " in inbound.text
    assert "voicemail-complete" in inbound.text
    assert "<Client " not in inbound.text
    call = db_session.scalar(select(CallRecord))
    assert call is not None
    complete_path = f"/api/v1/webhooks/twilio/voice/voicemail-complete?call_id={call.id}"
    completed = post_signed(
        client,
        complete_path,
        {
            "CallSid": inbound_payload["CallSid"],
            "RecordingSid": "RE00000000000000000000000000000085",
            "RecordingDuration": "32",
        },
    )
    assert completed.status_code == 200, completed.text
    db_session.refresh(call)
    assert call.status == "completed"
    assert call.call_metadata["voicemail"] is True
    assert db_session.scalar(select(Task).where(Task.task_type == "missed_call")) is not None


def test_voice_session_and_outbound_call_are_scoped_and_idempotent(
    db_session: Session,
    api_db_override: None,
    voice_settings: None,
) -> None:
    client = TestClient(app)
    conversation = seed_voice_lead(db_session, client)
    headers = {"X-Dev-User-Email": OWNER_EMAIL}

    session_response = client.get("/api/v1/voice/session", headers=headers)
    assert session_response.status_code == 200
    session = session_response.json()
    assert session["can_initialize"] is True
    assert session["token"]
    assert session["line"]["phone_number"] == STONEGATE_NUMBER

    detail_response = client.get(
        f"/api/v1/inbox/conversations/{conversation.id}",
        headers=headers,
    )
    assert detail_response.status_code == 200
    assert detail_response.json()["voice_eligibility"]["can_call"] is True

    intent = create_intent(client, conversation)
    payload = {
        "From": f"client:{session['identity']}",
        "To": "",
        "CallSid": "CA00000000000000000000000000000001",
        "CallIntentId": str(intent["id"]),
    }
    path = "/api/v1/webhooks/twilio/voice/outbound"
    outbound = post_signed(client, path, payload)
    duplicate = post_signed(client, path, payload)

    assert outbound.status_code == 200
    assert duplicate.status_code == 200
    assert f'callerId="{STONEGATE_NUMBER}"' in outbound.text
    assert "<Number " in outbound.text
    assert SELLER_NUMBER in outbound.text
    assert int(db_session.scalar(select(func.count()).select_from(CallRecord)) or 0) == 1

    reused_payload = {**payload, "CallSid": "CA00000000000000000000000000000002"}
    reused = post_signed(client, path, reused_payload)
    assert reused.status_code == 422
    call_intent = db_session.get(VoiceCallIntent, UUID(str(intent["id"])))
    assert call_intent is not None
    assert call_intent.status == "started"


def test_forwarded_outbound_call_rings_staff_then_connects_seller(
    db_session: Session,
    api_db_override: None,
    voice_settings: None,
    monkeypatch: MonkeyPatch,
) -> None:
    class FakeVoiceProvider:
        def __init__(self) -> None:
            self.request: dict[str, str] = {}

        def start(self, **kwargs: str) -> TwilioVoiceCallResult:
            self.request = kwargs
            return TwilioVoiceCallResult(
                sid="CA00000000000000000000000000000090",
                status="queued",
            )

    fake_provider = FakeVoiceProvider()
    monkeypatch.setattr(
        "app.services.voice.get_twilio_voice_call_provider",
        lambda: fake_provider,
    )
    client = TestClient(app)
    conversation = seed_voice_lead(db_session, client)
    response = client.post(
        f"/api/v1/voice/conversations/{conversation.id}/forwarded-calls",
        headers={"X-Dev-User-Email": OWNER_EMAIL},
        json={"idempotency_key": "forwarded-call-request-0001"},
    )

    assert response.status_code == 201, response.text
    intent = response.json()
    assert intent["status"] == "started"
    assert fake_provider.request["to"] == "+14045550100"
    assert fake_provider.request["from_number"] == STONEGATE_NUMBER
    assert "Press 1 to connect" in fake_provider.request["twiml"]

    connect_path = (
        "/api/v1/webhooks/twilio/voice/forwarded-connect"
        f"?intent_id={intent['id']}"
    )
    connected = post_signed(
        client,
        connect_path,
        {"CallSid": "CA00000000000000000000000000000090", "Digits": "1"},
    )
    assert connected.status_code == 200, connected.text
    assert SELLER_NUMBER in connected.text
    assert f'callerId="{STONEGATE_NUMBER}"' in connected.text
    assert db_session.scalar(select(func.count()).select_from(CallRecord)) == 1


def test_forwarded_outbound_call_can_start_from_lead_page(
    db_session: Session,
    api_db_override: None,
    voice_settings: None,
    monkeypatch: MonkeyPatch,
) -> None:
    class FakeVoiceProvider:
        def start(self, **kwargs: str) -> TwilioVoiceCallResult:
            return TwilioVoiceCallResult(
                sid="CA00000000000000000000000000000091",
                status="queued",
            )

    monkeypatch.setattr(
        "app.services.voice.get_twilio_voice_call_provider",
        lambda: FakeVoiceProvider(),
    )
    client = TestClient(app)
    conversation = seed_voice_lead(db_session, client)

    response = client.post(
        f"/api/v1/voice/leads/{conversation.lead_id}/forwarded-calls",
        headers={"X-Dev-User-Email": OWNER_EMAIL},
        json={"idempotency_key": "lead-page-forwarded-call-0001"},
    )

    assert response.status_code == 201, response.text
    assert response.json()["conversation_id"] == str(conversation.id)
    call = db_session.scalar(select(CallRecord))
    assert call is not None
    assert call.from_number == STONEGATE_NUMBER
    assert call.to_number == SELLER_NUMBER


def test_voice_statuses_are_idempotent_and_create_missed_call_tasks(
    db_session: Session,
    api_db_override: None,
    voice_settings: None,
) -> None:
    client = TestClient(app)
    seed_voice_lead(db_session, client)
    inbound_payload = {
        "From": SELLER_NUMBER,
        "To": STONEGATE_NUMBER,
        "CallSid": "CA00000000000000000000000000000010",
    }
    inbound_path = "/api/v1/webhooks/twilio/voice/incoming"
    inbound = post_signed(client, inbound_path, inbound_payload)
    assert inbound.status_code == 200
    assert "<Client " not in inbound.text
    assert "<Number " in inbound.text

    call = db_session.scalar(select(CallRecord))
    assert call is not None
    status_path = f"/api/v1/webhooks/twilio/voice/status?call_id={call.id}"
    no_answer_payload = {
        "CallSid": "CA00000000000000000000000000000011",
        "ParentCallSid": inbound_payload["CallSid"],
        "CallStatus": "no-answer",
        "CallDuration": "0",
    }
    first = post_signed(client, status_path, no_answer_payload)
    duplicate = post_signed(client, status_path, no_answer_payload)

    assert first.status_code == 204
    assert duplicate.status_code == 204
    db_session.expire_all()
    updated_call = db_session.get(CallRecord, call.id)
    assert updated_call is not None
    assert updated_call.status == "no-answer"
    assert updated_call.child_provider_call_id == no_answer_payload["CallSid"]
    task = db_session.scalar(select(Task).where(Task.task_type == "missed_call"))
    assert task is not None
    assert task.priority == "high"
    assert (
        int(
            db_session.scalar(
                select(func.count())
                .select_from(Task)
                .where(Task.task_type == "missed_call")
            )
            or 0
        )
        == 1
    )


def test_unknown_inbound_caller_creates_one_lead_and_conversation(
    db_session: Session,
    api_db_override: None,
    voice_settings: None,
) -> None:
    client = TestClient(app)
    seed_voice_lead(db_session, client)
    initial_lead_count = int(db_session.scalar(select(func.count()).select_from(Lead)) or 0)
    payload = {
        "From": "+14705550199",
        "To": STONEGATE_NUMBER,
        "CallSid": "CA00000000000000000000000000000020",
    }
    path = "/api/v1/webhooks/twilio/voice/incoming"

    first = post_signed(client, path, payload)
    duplicate = post_signed(client, path, payload)

    assert first.status_code == 200
    assert duplicate.status_code == 200
    assert (
        int(db_session.scalar(select(func.count()).select_from(Lead)) or 0)
        == initial_lead_count + 1
    )
    contact = db_session.scalar(
        select(Contact).where(Contact.legal_name == "Inbound caller +14705550199")
    )
    assert contact is not None


def test_recording_callback_is_private_idempotent_and_visible_in_timeline(
    db_session: Session,
    api_db_override: None,
    voice_settings: None,
    monkeypatch: MonkeyPatch,
) -> None:
    monkeypatch.setenv("TWILIO_VOICE_RECORDING_ENABLED", "true")
    monkeypatch.setenv(
        "TWILIO_VOICE_RECORDING_DISCLOSURE",
        "This call may be recorded for quality and documentation.",
    )
    get_settings.cache_clear()
    client = TestClient(app)
    conversation = seed_voice_lead(db_session, client)
    intent = create_intent(client, conversation)
    session = client.get(
        "/api/v1/voice/session",
        headers={"X-Dev-User-Email": OWNER_EMAIL},
    ).json()
    outbound_payload = {
        "From": f"client:{session['identity']}",
        "CallSid": "CA00000000000000000000000000000030",
        "CallIntentId": str(intent["id"]),
    }
    outbound = post_signed(
        client,
        "/api/v1/webhooks/twilio/voice/outbound",
        outbound_payload,
    )
    assert outbound.status_code == 200
    assert 'record="record-from-answer-dual"' in outbound.text
    assert "/voice/disclosure" in outbound.text
    disclosure_path = f"/api/v1/webhooks/twilio/voice/disclosure?intent_id={intent['id']}"
    disclosure = post_signed(
        client,
        disclosure_path,
        {"CallSid": outbound_payload["CallSid"]},
    )
    assert disclosure.status_code == 200
    assert "This call may be recorded" in disclosure.text

    recording_path = (
        f"/api/v1/webhooks/twilio/voice/recording?intent_id={intent['id']}"
    )
    recording_payload = {
        "CallSid": outbound_payload["CallSid"],
        "RecordingSid": "RE00000000000000000000000000000001",
        "RecordingStatus": "completed",
        "RecordingDuration": "125",
        "RecordingChannels": "2",
        "RecordingSource": "DialVerb",
    }
    first = post_signed(client, recording_path, recording_payload)
    duplicate = post_signed(client, recording_path, recording_payload)
    assert first.status_code == 204
    assert duplicate.status_code == 204
    assert int(db_session.scalar(select(func.count()).select_from(CallRecording)) or 0) == 1
    assert int(db_session.scalar(select(func.count()).select_from(CallTranscript)) or 0) == 1
    recording = db_session.scalar(select(CallRecording))
    assert recording is not None
    assert recording.retention_expires_at is not None
    assert recording.recorded_at is not None
    assert (recording.retention_expires_at - recording.recorded_at).days == 180
    assert recording.consent_status == "disclosed"

    detail = client.get(
        f"/api/v1/inbox/conversations/{conversation.id}",
        headers={"X-Dev-User-Email": OWNER_EMAIL},
    )
    call_item = next(item for item in detail.json()["timeline"] if item["channel"] == "call")
    assert call_item["recording_id"]
    assert call_item["recording_status"] == "completed"
    assert call_item["recording_retention_expires_at"]
    assert call_item["transcript"]["status"] == "queued"


def test_recording_deletion_is_owner_only_audited_and_preserves_transcript(
    db_session: Session,
    api_db_override: None,
    voice_settings: None,
    monkeypatch: MonkeyPatch,
) -> None:
    monkeypatch.setenv("TWILIO_VOICE_RECORDING_ENABLED", "true")
    monkeypatch.setenv(
        "TWILIO_VOICE_RECORDING_DISCLOSURE",
        "This call may be recorded for quality and documentation.",
    )
    get_settings.cache_clear()
    client = TestClient(app)
    conversation = seed_voice_lead(db_session, client)
    intent = create_intent(client, conversation)
    session = client.get(
        "/api/v1/voice/session",
        headers={"X-Dev-User-Email": OWNER_EMAIL},
    ).json()
    call_sid = "CA00000000000000000000000000000031"
    outbound = post_signed(
        client,
        "/api/v1/webhooks/twilio/voice/outbound",
        {
            "From": f"client:{session['identity']}",
            "CallSid": call_sid,
            "CallIntentId": str(intent["id"]),
        },
    )
    assert outbound.status_code == 200
    recording_path = f"/api/v1/webhooks/twilio/voice/recording?intent_id={intent['id']}"
    recorded = post_signed(
        client,
        recording_path,
        {
            "CallSid": call_sid,
            "RecordingSid": "RE00000000000000000000000000000002",
            "RecordingStatus": "completed",
            "RecordingDuration": "95",
            "RecordingChannels": "2",
            "RecordingSource": "DialVerb",
        },
    )
    assert recorded.status_code == 204
    recording = db_session.scalar(select(CallRecording))
    transcript = db_session.scalar(select(CallTranscript))
    owner = db_session.scalar(select(User).where(User.email == OWNER_EMAIL))
    organization_id = conversation.organization_id
    acquisition_role = db_session.scalar(
        select(Role).where(
            Role.organization_id == organization_id,
            Role.key == "acquisition_rep",
        )
    )
    assert recording is not None
    assert transcript is not None
    assert owner is not None
    assert acquisition_role is not None
    transcript.status = "approved"
    acquisition_user = User(
        organization_id=organization_id,
        email="acquisition@example.com",
        display_name="Acquisition Rep",
        is_active=True,
    )
    db_session.add(acquisition_user)
    db_session.flush()
    db_session.add(
        RoleAssignment(
            organization_id=organization_id,
            user_id=acquisition_user.id,
            role_id=acquisition_role.id,
        )
    )
    db_session.commit()

    forbidden = client.request(
        "DELETE",
        f"/api/v1/voice/recordings/{recording.id}",
        headers={"X-Dev-User-Email": acquisition_user.email},
        json={"reason": "Seller requested early deletion."},
    )
    assert forbidden.status_code == 403

    deleted_provider_ids: list[str] = []
    monkeypatch.setattr(
        "app.services.voice.delete_twilio_recording",
        lambda _settings, provider_id: deleted_provider_ids.append(provider_id),
    )
    deleted = client.request(
        "DELETE",
        f"/api/v1/voice/recordings/{recording.id}",
        headers={"X-Dev-User-Email": OWNER_EMAIL},
        json={"reason": "Seller requested early deletion."},
    )
    assert deleted.status_code == 200
    assert deleted.json()["status"] == "deleted"
    assert deleted_provider_ids == ["RE00000000000000000000000000000002"]
    db_session.refresh(recording)
    db_session.refresh(transcript)
    assert recording.media_reference is None
    assert recording.deleted_by_user_id == owner.id
    assert recording.deletion_reason == "Seller requested early deletion."
    assert transcript.status == "approved"
    assert db_session.scalar(
        select(func.count())
        .select_from(AuditEvent)
        .where(AuditEvent.action == "communication.recording_delete")
    ) == 1

    detail = client.get(
        f"/api/v1/inbox/conversations/{conversation.id}",
        headers={"X-Dev-User-Email": OWNER_EMAIL},
    )
    call_item = next(item for item in detail.json()["timeline"] if item["channel"] == "call")
    assert call_item["recording_status"] == "deleted"
    assert call_item["recording_deleted_at"]
    assert call_item["transcript"]["status"] == "approved"


def test_expired_recording_is_deleted_by_retention_worker(
    db_session: Session,
    api_db_override: None,
    voice_settings: None,
    monkeypatch: MonkeyPatch,
) -> None:
    client = TestClient(app)
    conversation = seed_voice_lead(db_session, client)
    intent = create_intent(client, conversation)
    session = client.get(
        "/api/v1/voice/session",
        headers={"X-Dev-User-Email": OWNER_EMAIL},
    ).json()
    call_sid = "CA00000000000000000000000000000032"
    post_signed(
        client,
        "/api/v1/webhooks/twilio/voice/outbound",
        {
            "From": f"client:{session['identity']}",
            "CallSid": call_sid,
            "CallIntentId": str(intent["id"]),
        },
    )
    call = db_session.scalar(select(CallRecord))
    assert call is not None
    recording = CallRecording(
        organization_id=conversation.organization_id,
        call_record_id=call.id,
        provider="twilio",
        provider_recording_id="RE-expired-recording",
        status="completed",
        media_reference="twilio://recordings/RE-expired-recording",
        duration_seconds=60,
        channel_count=2,
        consent_status="disclosed",
        recorded_at=datetime(2026, 1, 1, tzinfo=ZoneInfo("UTC")),
        retention_expires_at=datetime(2026, 1, 2, tzinfo=ZoneInfo("UTC")),
        deleted_at=None,
        deleted_by_user_id=None,
        deletion_reason=None,
        recording_metadata=None,
    )
    db_session.add(recording)
    db_session.commit()
    deleted_provider_ids: list[str] = []
    monkeypatch.setattr(
        "app.services.voice.delete_twilio_recording",
        lambda _settings, provider_id: deleted_provider_ids.append(provider_id),
    )

    purged_id = purge_next_expired_recording(
        db_session,
        get_settings(),
        now=datetime(2026, 7, 18, tzinfo=ZoneInfo("UTC")),
    )

    assert purged_id == recording.id
    db_session.refresh(recording)
    assert recording.status == "deleted"
    assert recording.deleted_by_user_id is None
    assert recording.deletion_reason == "Stonegate recording retention period expired."
    assert deleted_provider_ids == ["RE-expired-recording"]


def test_voice_webhooks_reject_invalid_signatures(
    db_session: Session,
    api_db_override: None,
    voice_settings: None,
) -> None:
    client = TestClient(app)
    bootstrap_foundation(
        db_session,
        organization_name="Stonegate Home Buyers",
        admin_email=OWNER_EMAIL,
        admin_name="Owner",
    )
    response = client.post(
        "/api/v1/webhooks/twilio/voice/incoming",
        content=urlencode(
            {
                "From": SELLER_NUMBER,
                "To": STONEGATE_NUMBER,
                "CallSid": "CA00000000000000000000000000000040",
            }
        ),
        headers={
            "Content-Type": "application/x-www-form-urlencoded",
            "X-Twilio-Signature": "invalid",
        },
    )
    assert response.status_code == 403
    assert int(db_session.scalar(select(func.count()).select_from(CallRecord)) or 0) == 0
    assert (
        int(
            db_session.scalar(
                select(func.count()).select_from(CommunicationProviderEvent)
            )
            or 0
        )
        == 0
    )
    assert db_session.scalar(select(VoiceLine)) is not None


def test_buyer_call_intent_and_inbound_call_use_dispositions_line(
    db_session: Session,
    api_db_override: None,
    voice_settings: None,
) -> None:
    client = TestClient(app)
    bootstrap_foundation(
        db_session,
        organization_name="Stonegate Home Buyers",
        admin_email=OWNER_EMAIL,
        admin_name="Owner",
    )
    owner = db_session.scalar(select(User).where(User.email == OWNER_EMAIL))
    assert owner is not None
    dispositions_number = "+14708887952"
    line = VoiceLine(
        organization_id=owner.organization_id,
        assigned_user_id=owner.id,
        fallback_user_id=None,
        assigned_team_id=None,
        provider="twilio",
        provider_phone_number_id=None,
        phone_number=dispositions_number,
        label="Stonegate Dispositions",
        department_key="dispositions",
        purpose_key="buyer_relations",
        status="active",
        is_default=False,
        inbound_route="assigned_user",
        ring_strategy="sequential",
        coverage_timezone="America/New_York",
        coverage_start_hour=0,
        coverage_end_hour=24,
        missed_call_action="fallback_then_voicemail",
        line_metadata={"source": "test"},
    )
    db_session.add(line)
    db_session.commit()
    buyer_response = client.post(
        "/api/v1/buyers",
        headers={"X-Dev-User-Email": OWNER_EMAIL},
        json={
            "name": "Alex Investor",
            "phone": SELLER_NUMBER,
            "buyer_type": "cash_buyer",
            "phone_contact_permission": True,
        },
    )
    assert buyer_response.status_code == 201, buyer_response.text
    conversation = db_session.scalar(
        select(Conversation).where(Conversation.conversation_type == "buyer")
    )
    assert conversation is not None

    intent_response = client.post(
        f"/api/v1/voice/conversations/{conversation.id}/call-intents",
        headers={"X-Dev-User-Email": OWNER_EMAIL},
        json={"idempotency_key": "buyer-call-0001"},
    )
    assert intent_response.status_code == 201, intent_response.text
    assert intent_response.json()["from_number"] == dispositions_number
    intent = db_session.get(VoiceCallIntent, UUID(intent_response.json()["id"]))
    assert intent is not None
    assert intent.lead_id is None
    assert intent.voice_line_id == line.id

    inbound_payload = {
        "From": SELLER_NUMBER,
        "To": dispositions_number,
        "CallSid": "CA00000000000000000000000000000077",
    }
    inbound_response = post_signed(
        client,
        "/api/v1/webhooks/twilio/voice/incoming",
        inbound_payload,
    )
    assert inbound_response.status_code == 200, inbound_response.text
    call = db_session.scalar(
        select(CallRecord).where(CallRecord.provider_call_id == inbound_payload["CallSid"])
    )
    assert call is not None
    assert call.conversation_id == conversation.id
    assert call.lead_id is None
    assert call.voice_line_id == line.id
