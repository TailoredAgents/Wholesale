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
from app.main import app
from app.models.foundation import (
    CallRecord,
    CallRecording,
    CallTranscript,
    CommunicationProviderEvent,
    Contact,
    Conversation,
    Lead,
    Task,
    VoiceCallIntent,
    VoiceLine,
)
from app.services.bootstrap import bootstrap_foundation
from app.services.communication_compliance import (
    is_within_sms_allowed_hours,
    is_within_voice_allowed_hours,
)

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
    assert "<Client " in inbound.text

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

    detail = client.get(
        f"/api/v1/inbox/conversations/{conversation.id}",
        headers={"X-Dev-User-Email": OWNER_EMAIL},
    )
    call_item = next(item for item in detail.json()["timeline"] if item["channel"] == "call")
    assert call_item["recording_id"]
    assert call_item["recording_status"] == "completed"
    assert call_item["transcript"]["status"] == "queued"


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
