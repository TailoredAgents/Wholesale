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
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session
from twilio.request_validator import RequestValidator  # type: ignore[import-untyped]

from app.core.config import get_settings
from app.integrations.twilio_recordings import TwilioRecordingMedia
from app.integrations.twilio_voice_calls import TwilioVoiceCallResult
from app.main import app
from app.models.foundation import (
    ActivityEvent,
    AiOrchestratorEvent,
    AuditEvent,
    CallRecord,
    CallRecording,
    CallTranscript,
    CommunicationProviderEvent,
    ConsentRecord,
    Contact,
    ContactMethod,
    Conversation,
    ConversationAssignmentEvent,
    ConversationContextLink,
    Lead,
    Organization,
    Role,
    RoleAssignment,
    SuppressionRecord,
    Task,
    User,
    VoiceCallIntent,
    VoiceLine,
)
from app.services.bootstrap import bootstrap_foundation
from app.services.communication_compliance import (
    evaluate_voice_eligibility,
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


def test_cellphone_voice_uses_active_line_without_legacy_from_number(
    voice_settings: None,
    monkeypatch: MonkeyPatch,
) -> None:
    monkeypatch.delenv("TWILIO_VOICE_FROM_NUMBER")
    get_settings.cache_clear()

    settings = get_settings()

    assert settings.twilio_voice_configured is True
    assert "TWILIO_VOICE_FROM_NUMBER" not in settings.twilio_voice_configuration_blockers


def test_call_intelligence_allows_georgia_one_party_recording_and_requires_ai(
    voice_settings: None,
    monkeypatch: MonkeyPatch,
) -> None:
    settings = get_settings()

    assert "TWILIO_VOICE_RECORDING_ENABLED=true" in (
        settings.call_intelligence_configuration_blockers
    )
    monkeypatch.setenv("TWILIO_VOICE_RECORDING_ENABLED", "true")
    monkeypatch.delenv("TWILIO_VOICE_RECORDING_DISCLOSURE", raising=False)
    monkeypatch.setenv("CALL_TRANSCRIPTION_ENABLED", "true")
    monkeypatch.setenv("AI_ENABLED", "true")
    monkeypatch.setenv("OPENAI_API_KEY", "test-openai-api-key")
    get_settings.cache_clear()

    assert get_settings().call_intelligence_configuration_blockers == ()


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


def create_call_assets(
    db: Session,
    conversation: Conversation,
    *,
    provider_suffix: str,
    recording_status: str = "completed",
    transcript_status: str = "completed",
    transcript_text: str | None = "Agent greeted the seller. Seller wants to move in 30 days.",
    speaker_segments: list[dict[str, object]] | None = None,
) -> tuple[CallRecording, CallTranscript]:
    call = CallRecord(
        organization_id=conversation.organization_id,
        conversation_id=conversation.id,
        lead_id=conversation.lead_id,
        contact_id=conversation.contact_id,
        actor_user_id=conversation.assigned_user_id,
        communication_record_id=None,
        voice_line_id=None,
        call_intent_id=None,
        provider="twilio",
        provider_call_id=f"CA-{provider_suffix}",
        child_provider_call_id=None,
        direction="outbound",
        status="completed",
        from_number=STONEGATE_NUMBER,
        to_number=SELLER_NUMBER,
        started_at=datetime.now(ZoneInfo("UTC")),
        answered_at=datetime.now(ZoneInfo("UTC")),
        ended_at=datetime.now(ZoneInfo("UTC")),
        duration_seconds=90,
        disposition=None,
        recording_consent_status="one_party_consent",
        call_metadata=None,
    )
    db.add(call)
    db.flush()
    recording = CallRecording(
        organization_id=conversation.organization_id,
        call_record_id=call.id,
        provider="twilio",
        provider_recording_id=f"RE-{provider_suffix}",
        status=recording_status,
        media_reference=f"twilio://recordings/RE-{provider_suffix}",
        duration_seconds=90,
        channel_count=2,
        consent_status="one_party_consent",
        recorded_at=datetime.now(ZoneInfo("UTC")),
        retention_expires_at=None,
        deleted_at=None,
        deleted_by_user_id=None,
        deletion_reason=None,
        recording_metadata=None,
    )
    db.add(recording)
    db.flush()
    transcript = CallTranscript(
        organization_id=conversation.organization_id,
        recording_id=recording.id,
        provider="openai",
        model_name="gpt-4o-transcribe-diarize",
        status=transcript_status,
        language="en",
        transcript_text=transcript_text,
        speaker_segments=(
            speaker_segments
            if speaker_segments is not None
            else [
                {
                    "index": 0,
                    "speaker": "Seller",
                    "start": 12.4,
                    "end": 17.8,
                    "text": "I want to move in 30 days.",
                }
            ]
        ),
        confidence_score=95,
        approved_by_user_id=None,
        approved_at=None,
        error_message=None,
        transcript_metadata=None,
    )
    db.add(transcript)
    db.commit()
    return recording, transcript


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


def test_manual_staff_call_remains_available_outside_contact_hours(
    db_session: Session,
    api_db_override: None,
    voice_settings: None,
    monkeypatch: MonkeyPatch,
) -> None:
    client = TestClient(app)
    seed_voice_lead(db_session, client)
    contact = db_session.scalar(select(Contact))
    assert contact is not None
    monkeypatch.setenv("TWILIO_VOICE_ALLOWED_START_HOUR", "9")
    monkeypatch.setenv("TWILIO_VOICE_ALLOWED_END_HOUR", "20")
    get_settings.cache_clear()
    late_evening = datetime(2026, 7, 17, 21, 30, tzinfo=ZoneInfo("America/New_York"))

    eligibility = evaluate_voice_eligibility(
        db_session,
        contact,
        settings=get_settings(),
        now=late_evening,
    )

    assert eligibility.within_allowed_hours is False
    assert eligibility.can_call is True
    assert not any("outside" in blocker.lower() for blocker in eligibility.blockers)


def test_bootstrap_normalizes_existing_active_voice_line_to_always_on(
    db_session: Session,
    voice_settings: None,
) -> None:
    bootstrap_foundation(
        db_session,
        organization_name="Stonegate Home Buyers",
        admin_email=OWNER_EMAIL,
        admin_name="Owner",
    )
    line = db_session.scalar(select(VoiceLine))
    assert line is not None
    line.coverage_start_hour = 9
    line.coverage_end_hour = 20
    line.missed_call_action = "task_only"
    db_session.commit()

    bootstrap_foundation(
        db_session,
        organization_name="Stonegate Home Buyers",
        admin_email=OWNER_EMAIL,
        admin_name="Owner",
    )

    db_session.refresh(line)
    assert line.coverage_start_hour == 0
    assert line.coverage_end_hour == 24
    assert line.missed_call_action == "task_only"


def test_staff_text_alert_preferences_are_independent_and_audited(
    db_session: Session,
    api_db_override: None,
    voice_settings: None,
) -> None:
    client = TestClient(app)
    seed_voice_lead(db_session, client)
    headers = {"X-Dev-User-Email": OWNER_EMAIL}
    line_payload = client.get("/api/v1/voice/lines", headers=headers).json()
    owner = next(user for user in line_payload["users"] if user["email"] == OWNER_EMAIL)
    assert owner["inbound_message_alert_sms_enabled"] is False

    response = client.patch(
        f"/api/v1/voice/users/{owner['id']}/forwarding",
        headers=headers,
        json={
            "voice_forwarding_number": "+14045550100",
            "voice_forwarding_enabled": True,
            "lead_alert_sms_enabled": False,
            "inbound_message_alert_sms_enabled": True,
        },
    )

    assert response.status_code == 200, response.text
    assert response.json()["lead_alert_sms_enabled"] is False
    assert response.json()["inbound_message_alert_sms_enabled"] is True
    audit = db_session.scalar(
        select(AuditEvent)
        .where(AuditEvent.action == "communication.voice_forwarding_update")
        .order_by(AuditEvent.created_at.desc())
    )
    assert audit is not None
    assert audit.new_value is not None
    assert audit.previous_value is not None
    assert audit.previous_value["inbound_message_alert_sms_enabled"] is False
    assert audit.new_value["lead_alert_sms_enabled"] is False
    assert audit.new_value["inbound_message_alert_sms_enabled"] is True

    legacy_client_update = client.patch(
        f"/api/v1/voice/users/{owner['id']}/forwarding",
        headers=headers,
        json={
            "voice_forwarding_number": "+14045550100",
            "voice_forwarding_enabled": True,
            "lead_alert_sms_enabled": False,
        },
    )
    assert legacy_client_update.status_code == 200, legacy_client_update.text
    assert legacy_client_update.json()["inbound_message_alert_sms_enabled"] is True

    missing_cellphone = client.patch(
        f"/api/v1/voice/users/{owner['id']}/forwarding",
        headers=headers,
        json={
            "voice_forwarding_number": None,
            "voice_forwarding_enabled": False,
            "lead_alert_sms_enabled": False,
            "inbound_message_alert_sms_enabled": True,
        },
    )
    assert missing_cellphone.status_code == 422
    assert "cellphone" in missing_cellphone.json()["detail"].lower()


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
            "missed_call_action": "voicemail",
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
    assert updated["missed_call_action"] == "voicemail"
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
            "missed_call_action": "task_only",
        },
    )
    assert dispositions_response.status_code == 201, dispositions_response.text
    dispositions = dispositions_response.json()
    assert dispositions["department_key"] == "dispositions"
    assert dispositions["purpose_key"] == "buyer_relations"
    assert dispositions["assigned_user_name"] == "Devon"
    assert dispositions["fallback_user_name"] == "Owner"
    assert dispositions["coverage_start_hour"] == 0
    assert dispositions["coverage_end_hour"] == 24
    assert dispositions["missed_call_action"] == "task_only"
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
    assert "<Client " in inbound_response.text
    assert f"stonegate_{devon['id'].replace('-', '')}" in inbound_response.text
    assert "CallerNumber" in inbound_response.text


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
    assert inbound.text.count("<Client ") == 2
    assert inbound.text.count("<Number ") == 2
    assert "/voice/screen" in inbound.text
    assert inbound.text.count("answered_user_id=") == 6
    assert 'sequential="false"' in inbound.text
    call = db_session.scalar(select(CallRecord))
    assert call is not None
    assert call.call_metadata is not None
    assert call.call_metadata["ring_user_count"] == 2
    assert call.call_metadata["ring_target_count"] == 4
    assert call.call_metadata["ring_browser_target_count"] == 2
    assert call.call_metadata["ring_mobile_target_count"] == 2

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
    assert call.call_metadata is not None
    assert call.call_metadata["mobile_screen_accepted_by_user_id"] == devon["id"]

    answered_path = (
        f"/api/v1/webhooks/twilio/voice/status?call_id={call.id}&answered_user_id={devon['id']}"
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
        f"/api/v1/webhooks/twilio/voice/status?call_id={call.id}&answered_user_id={owner['id']}"
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


def test_inbound_call_still_rings_cellphone_without_browser_credentials(
    db_session: Session,
    api_db_override: None,
    voice_settings: None,
    monkeypatch: MonkeyPatch,
) -> None:
    client = TestClient(app)
    seed_voice_lead(db_session, client)
    for key in ("TWILIO_API_KEY_SID", "TWILIO_API_KEY_SECRET", "TWILIO_TWIML_APP_SID"):
        monkeypatch.delenv(key)
    get_settings.cache_clear()

    inbound = post_signed(
        client,
        "/api/v1/webhooks/twilio/voice/incoming",
        {
            "From": SELLER_NUMBER,
            "To": STONEGATE_NUMBER,
            "CallSid": "CA00000000000000000000000000000087",
        },
    )

    assert inbound.status_code == 200, inbound.text
    assert "<Client " not in inbound.text
    assert "<Number " in inbound.text
    assert "+14045550100" in inbound.text


def test_inbound_call_rings_after_hours_then_uses_voicemail_on_no_answer(
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
    assert "+14045550100" in inbound.text
    assert "<Number " in inbound.text
    assert "<Record " not in inbound.text
    call = db_session.scalar(select(CallRecord))
    assert call is not None

    dial_result_path = f"/api/v1/webhooks/twilio/voice/dial-result?call_id={call.id}"
    dial_result = post_signed(
        client,
        dial_result_path,
        {
            "CallSid": inbound_payload["CallSid"],
            "DialCallSid": "CA00000000000000000000000000000086",
            "DialCallStatus": "no-answer",
        },
    )
    assert dial_result.status_code == 200, dial_result.text
    assert "<Record " in dial_result.text
    assert "voicemail-complete" in dial_result.text

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
    assert call.call_metadata is not None
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

    initial_status = client.get(
        f"/api/v1/voice/call-intents/{intent['id']}/status",
        headers=headers,
    )
    assert initial_status.status_code == 200, initial_status.text
    assert initial_status.json()["status"] == "initiated"
    assert initial_status.json()["terminal"] is False

    completed_status = post_signed(
        client,
        f"/api/v1/webhooks/twilio/voice/status?intent_id={intent['id']}",
        {
            "CallSid": payload["CallSid"],
            "CallStatus": "completed",
            "CallDuration": "14",
        },
    )
    assert completed_status.status_code == 204, completed_status.text
    final_status = client.get(
        f"/api/v1/voice/call-intents/{intent['id']}/status",
        headers=headers,
    )
    assert final_status.status_code == 200, final_status.text
    assert final_status.json()["status"] == "completed"
    assert final_status.json()["duration_seconds"] == 14
    assert final_status.json()["terminal"] is True

    reused_payload = {**payload, "CallSid": "CA00000000000000000000000000000002"}
    reused = post_signed(client, path, reused_payload)
    assert reused.status_code == 422
    call_intent = db_session.get(VoiceCallIntent, UUID(str(intent["id"])))
    assert call_intent is not None
    assert call_intent.status == "started"


def test_quick_dial_creates_business_thread_and_reuses_it_idempotently(
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
    headers = {"X-Dev-User-Email": OWNER_EMAIL}
    payload = {
        "phone_number": "+14045550199",
        "company_name": "Peachtree Title",
        "purpose": "title_company",
        "call_reason": "Confirm closing availability.",
        "idempotency_key": "quick-dial-title-0001",
    }

    created = client.post("/api/v1/voice/quick-dial", headers=headers, json=payload)
    duplicate = client.post("/api/v1/voice/quick-dial", headers=headers, json=payload)
    second_intent = client.post(
        "/api/v1/voice/quick-dial",
        headers=headers,
        json={**payload, "idempotency_key": "quick-dial-title-0002"},
    )

    assert created.status_code == 201, created.text
    assert duplicate.status_code == 201, duplicate.text
    assert second_intent.status_code == 201, second_intent.text
    body = created.json()
    assert body["conversation_type"] == "general"
    assert body["contact_name"] == "Peachtree Title"
    assert body["reused_contact"] is False
    assert body["reused_conversation"] is False
    assert body["intent"]["recipient"] == "+14045550199"
    assert body["intent"]["status"] == "pending"
    assert duplicate.json()["intent"]["id"] == body["intent"]["id"]
    assert second_intent.json()["conversation_id"] == body["conversation_id"]
    assert second_intent.json()["contact_id"] == body["contact_id"]
    assert second_intent.json()["intent"]["id"] != body["intent"]["id"]
    contact = db_session.get(Contact, UUID(body["contact_id"]))
    assert contact is not None
    assert contact.contact_type == "business_contact"
    assert int(db_session.scalar(select(func.count()).select_from(Contact)) or 0) == 1
    assert int(db_session.scalar(select(func.count()).select_from(Conversation)) or 0) == 1
    assert int(db_session.scalar(select(func.count()).select_from(VoiceCallIntent)) or 0) == 2
    assert int(db_session.scalar(select(func.count()).select_from(Lead)) or 0) == 0


def test_quick_dial_replay_is_bound_to_request_and_actor(
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
    owner_role = db_session.scalar(select(Role).where(Role.key == "owner"))
    assert owner is not None
    assert owner_role is not None
    second_owner = User(
        organization_id=owner.organization_id,
        email="second-owner@example.com",
        display_name="Second Owner",
        is_active=True,
    )
    db_session.add(second_owner)
    db_session.flush()
    db_session.add(
        RoleAssignment(
            organization_id=owner.organization_id,
            user_id=second_owner.id,
            role_id=owner_role.id,
        )
    )
    db_session.commit()
    payload = {
        "phone_number": "+14045550198",
        "company_name": "Peachtree Inspections",
        "purpose": "vendor",
        "call_reason": "Confirm inspection availability.",
        "idempotency_key": "quick-dial-replay-0001",
    }

    created = client.post(
        "/api/v1/voice/quick-dial",
        headers={"X-Dev-User-Email": OWNER_EMAIL},
        json=payload,
    )
    changed_request = client.post(
        "/api/v1/voice/quick-dial",
        headers={"X-Dev-User-Email": OWNER_EMAIL},
        json={**payload, "call_reason": "A different call."},
    )
    changed_actor = client.post(
        "/api/v1/voice/quick-dial",
        headers={"X-Dev-User-Email": second_owner.email},
        json=payload,
    )

    assert created.status_code == 201, created.text
    assert changed_request.status_code == 409, changed_request.text
    assert changed_actor.status_code == 409, changed_actor.text
    assert int(db_session.scalar(select(func.count()).select_from(VoiceCallIntent)) or 0) == 1
    assert (
        int(
            db_session.scalar(
                select(func.count())
                .select_from(AuditEvent)
                .where(AuditEvent.action == "communication.quick_dial_prepare")
            )
            or 0
        )
        == 1
    )


def test_quick_dial_treats_recorded_phone_permission_as_advisory(
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
    headers = {"X-Dev-User-Email": OWNER_EMAIL}
    payload = {
        "phone_number": "+14045550197",
        "company_name": "North Metro Vendor",
        "purpose": "vendor",
        "idempotency_key": "quick-dial-revocation-0001",
    }
    created = client.post("/api/v1/voice/quick-dial", headers=headers, json=payload)
    assert created.status_code == 201, created.text
    contact = db_session.get(Contact, UUID(created.json()["contact_id"]))
    assert contact is not None
    db_session.add(
        ConsentRecord(
            organization_id=contact.organization_id,
            contact_id=contact.id,
            channel="phone",
            status="revoked",
            source="phone_call",
            wording_version="manual-v1",
            wording="The contact revoked phone permission.",
            normalized_address="+14045550197",
            captured_ip=None,
            user_agent=None,
        )
    )
    db_session.commit()

    advisory = client.post(
        "/api/v1/voice/quick-dial",
        headers=headers,
        json={**payload, "idempotency_key": "quick-dial-revocation-0002"},
    )

    assert advisory.status_code == 201, advisory.text
    detail = client.get(
        f"/api/v1/inbox/conversations/{advisory.json()['conversation_id']}",
        headers=headers,
    )
    assert detail.status_code == 200, detail.text
    assert detail.json()["voice_eligibility"]["can_call"] is True
    assert detail.json()["voice_eligibility"]["consent_status"] == "revoked"
    session = client.get("/api/v1/voice/session", headers=headers).json()
    outbound = post_signed(
        client,
        "/api/v1/webhooks/twilio/voice/outbound",
        {
            "From": f"client:{session['identity']}",
            "CallSid": "CA00000000000000000000000000000096",
            "CallIntentId": advisory.json()["intent"]["id"],
        },
    )
    assert outbound.status_code == 200, outbound.text
    assert "+14045550197" in outbound.text
    assert int(db_session.scalar(select(func.count()).select_from(VoiceCallIntent)) or 0) == 2


def test_quick_dial_reuses_existing_outside_contact_without_hidden_permission_block(
    db_session: Session,
    api_db_override: None,
    voice_settings: None,
) -> None:
    client = TestClient(app)
    conversation = seed_voice_lead(db_session, client)
    phone_consent = db_session.scalar(
        select(ConsentRecord).where(
            ConsentRecord.contact_id == conversation.contact_id,
            ConsentRecord.channel == "phone",
        )
    )
    assert phone_consent is not None
    db_session.delete(phone_consent)
    db_session.commit()
    headers = {"X-Dev-User-Email": OWNER_EMAIL}

    response = client.post(
        "/api/v1/voice/quick-dial",
        headers=headers,
        json={
            "phone_number": SELLER_NUMBER,
            "purpose": "other",
            "idempotency_key": "quick-dial-existing-contact-0001",
        },
    )

    assert response.status_code == 201, response.text
    assert response.json()["conversation_id"] == str(conversation.id)
    intent = db_session.get(VoiceCallIntent, UUID(response.json()["intent"]["id"]))
    assert intent is not None
    assert intent.intent_metadata["recorded_permission_required"] is False

    session = client.get("/api/v1/voice/session", headers=headers).json()
    outbound = post_signed(
        client,
        "/api/v1/webhooks/twilio/voice/outbound",
        {
            "From": f"client:{session['identity']}",
            "CallSid": "CA00000000000000000000000000000094",
            "CallIntentId": response.json()["intent"]["id"],
        },
    )
    assert outbound.status_code == 200, outbound.text
    assert SELLER_NUMBER in outbound.text


def test_quick_dial_reuses_existing_business_contact_without_creating_a_lead(
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
    contact = Contact(
        organization_id=owner.organization_id,
        legal_name="Cobb Closing Counsel",
        preferred_name=None,
        contact_type="business_contact",
        assigned_user_id=owner.id,
    )
    db_session.add(contact)
    db_session.flush()
    db_session.add(
        ContactMethod(
            organization_id=owner.organization_id,
            contact_id=contact.id,
            method_type="phone",
            value="(470) 555-0117",
            normalized_value="4705550117",
            is_primary=True,
        )
    )
    db_session.commit()

    response = client.post(
        "/api/v1/voice/quick-dial",
        headers={"X-Dev-User-Email": OWNER_EMAIL},
        json={
            "phone_number": "+14705550117",
            "purpose": "attorney",
            "idempotency_key": "quick-dial-attorney-0001",
        },
    )

    assert response.status_code == 201, response.text
    assert response.json()["contact_id"] == str(contact.id)
    assert response.json()["reused_contact"] is True
    assert response.json()["reused_conversation"] is False
    assert int(db_session.scalar(select(func.count()).select_from(Contact)) or 0) == 1
    assert int(db_session.scalar(select(func.count()).select_from(Lead)) or 0) == 0


def test_quick_dial_binds_an_existing_contact_to_the_exact_entered_number(
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
    contact = Contact(
        organization_id=owner.organization_id,
        legal_name="Multi-line Closing Company",
        preferred_name=None,
        contact_type="business_contact",
        assigned_user_id=owner.id,
    )
    db_session.add(contact)
    db_session.flush()
    db_session.add_all(
        [
            ContactMethod(
                organization_id=owner.organization_id,
                contact_id=contact.id,
                method_type="phone",
                value="(470) 555-0120",
                normalized_value="4705550120",
                is_primary=True,
            ),
            ContactMethod(
                organization_id=owner.organization_id,
                contact_id=contact.id,
                method_type="phone",
                value="(470) 555-0121",
                normalized_value="4705550121",
                is_primary=False,
            ),
        ]
    )
    db_session.commit()

    response = client.post(
        "/api/v1/voice/quick-dial",
        headers={"X-Dev-User-Email": OWNER_EMAIL},
        json={
            "phone_number": "+14705550121",
            "company_name": "Multi-line Closing Company",
            "purpose": "title_company",
            "idempotency_key": "quick-dial-secondary-number-0001",
        },
    )

    assert response.status_code == 201, response.text
    body = response.json()
    assert body["contact_id"] == str(contact.id)
    assert body["intent"]["recipient"] == "+14705550121"
    conversation = db_session.get(Conversation, UUID(body["conversation_id"]))
    assert conversation is not None
    assert conversation.conversation_metadata["quick_dial"]["phone_number"] == "+14705550121"
    detail = client.get(
        f"/api/v1/inbox/conversations/{conversation.id}",
        headers={"X-Dev-User-Email": OWNER_EMAIL},
    )
    assert detail.status_code == 200, detail.text
    assert detail.json()["voice_eligibility"]["recipient"] == "+14705550121"


def test_quick_dial_uses_only_the_selected_authorized_company_line(
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
    company_number = "+14705550191"
    company_line = VoiceLine(
        organization_id=owner.organization_id,
        assigned_user_id=owner.id,
        fallback_user_id=None,
        assigned_team_id=None,
        provider="twilio",
        provider_phone_number_id=None,
        phone_number=company_number,
        label="Company calls",
        department_key="general",
        purpose_key="company_general",
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
    db_session.add(company_line)
    db_session.commit()

    response = client.post(
        "/api/v1/voice/quick-dial",
        headers={"X-Dev-User-Email": OWNER_EMAIL},
        json={
            "phone_number": "+14045550155",
            "company_name": "Georgia Closing Services",
            "purpose": "title_company",
            "voice_line_id": str(company_line.id),
            "idempotency_key": "quick-dial-company-line-0001",
        },
    )

    assert response.status_code == 201, response.text
    assert response.json()["intent"]["from_number"] == company_number
    intent = db_session.get(VoiceCallIntent, UUID(response.json()["intent"]["id"]))
    assert intent is not None
    assert intent.voice_line_id == company_line.id


def test_quick_dial_requires_full_call_permission_and_rejects_internal_numbers(
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
    caller_role = db_session.scalar(select(Role).where(Role.key == "prospecting_caller"))
    assert owner is not None
    assert caller_role is not None
    assigned_only_user = User(
        organization_id=owner.organization_id,
        email="assigned-caller@example.com",
        display_name="Assigned Caller",
        is_active=True,
    )
    db_session.add(assigned_only_user)
    db_session.flush()
    db_session.add(
        RoleAssignment(
            organization_id=owner.organization_id,
            user_id=assigned_only_user.id,
            role_id=caller_role.id,
        )
    )
    db_session.commit()
    payload = {
        "phone_number": "+14045550188",
        "purpose": "vendor",
        "idempotency_key": "quick-dial-permission-0001",
    }

    forbidden = client.post(
        "/api/v1/voice/quick-dial",
        headers={"X-Dev-User-Email": assigned_only_user.email},
        json=payload,
    )
    own_line = client.post(
        "/api/v1/voice/quick-dial",
        headers={"X-Dev-User-Email": OWNER_EMAIL},
        json={**payload, "phone_number": STONEGATE_NUMBER},
    )

    assert forbidden.status_code == 403
    assert own_line.status_code == 422
    assert "cannot call a Stonegate company line" in own_line.text


def test_general_quick_dial_browser_call_creates_twiml_and_call_history(
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
    headers = {"X-Dev-User-Email": OWNER_EMAIL}
    quick_dial = client.post(
        "/api/v1/voice/quick-dial",
        headers=headers,
        json={
            "phone_number": "+14045550177",
            "company_name": "North Georgia Surveying",
            "purpose": "vendor",
            "idempotency_key": "quick-dial-browser-0001",
        },
    )
    assert quick_dial.status_code == 201, quick_dial.text
    result = quick_dial.json()
    detail = client.get(
        f"/api/v1/inbox/conversations/{result['conversation_id']}",
        headers=headers,
    )
    assert detail.status_code == 200, detail.text
    assert detail.json()["voice_eligibility"]["can_call"] is True
    session = client.get("/api/v1/voice/session", headers=headers).json()
    payload = {
        "From": f"client:{session['identity']}",
        "CallSid": "CA00000000000000000000000000000066",
        "CallIntentId": result["intent"]["id"],
    }

    outbound = post_signed(client, "/api/v1/webhooks/twilio/voice/outbound", payload)
    duplicate = post_signed(client, "/api/v1/webhooks/twilio/voice/outbound", payload)

    assert outbound.status_code == 200, outbound.text
    assert duplicate.status_code == 200, duplicate.text
    assert "+14045550177" in outbound.text
    assert f'callerId="{STONEGATE_NUMBER}"' in outbound.text
    call = db_session.scalar(select(CallRecord))
    assert call is not None
    assert call.conversation_id == UUID(result["conversation_id"])
    assert call.contact_id == UUID(result["contact_id"])
    assert call.lead_id is None
    assert int(db_session.scalar(select(func.count()).select_from(CallRecord)) or 0) == 1
    activity = db_session.scalar(
        select(ActivityEvent).where(ActivityEvent.event_type == "conversation.call_started")
    )
    assert activity is not None
    assert activity.summary == "Outbound company call initiated from Quick Dial."


def test_browser_calling_requires_browser_credentials_but_cellphone_forwarding_does_not(
    db_session: Session,
    api_db_override: None,
    voice_settings: None,
    monkeypatch: MonkeyPatch,
) -> None:
    class FakeVoiceProvider:
        def start(self, **kwargs: str) -> TwilioVoiceCallResult:
            return TwilioVoiceCallResult(
                sid="CA00000000000000000000000000000096",
                status="queued",
            )

    for key in ("TWILIO_API_KEY_SID", "TWILIO_API_KEY_SECRET", "TWILIO_TWIML_APP_SID"):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setattr(
        "app.services.voice.get_twilio_voice_call_provider",
        lambda: FakeVoiceProvider(),
    )
    get_settings.cache_clear()
    client = TestClient(app)
    conversation = seed_voice_lead(db_session, client)
    headers = {"X-Dev-User-Email": OWNER_EMAIL}

    browser = client.post(
        f"/api/v1/voice/leads/{conversation.lead_id}/call-intents",
        headers=headers,
        json={"idempotency_key": "missing-browser-credentials-0001"},
    )
    quick_dial = client.post(
        "/api/v1/voice/quick-dial",
        headers=headers,
        json={
            "phone_number": "+14045550196",
            "company_name": "Browser Credential Test",
            "purpose": "vendor",
            "idempotency_key": "missing-browser-credentials-0002",
        },
    )

    assert browser.status_code == 503, browser.text
    assert quick_dial.status_code == 503, quick_dial.text
    assert "TWILIO_API_KEY_SID" in browser.text
    assert int(db_session.scalar(select(func.count()).select_from(VoiceCallIntent)) or 0) == 0
    assert (
        db_session.scalar(
            select(Contact).where(Contact.legal_name == "Browser Credential Test")
        )
        is None
    )

    forwarded = client.post(
        f"/api/v1/voice/leads/{conversation.lead_id}/forwarded-calls",
        headers=headers,
        json={"idempotency_key": "cellphone-fallback-0001"},
    )

    assert forwarded.status_code == 201, forwarded.text
    assert forwarded.json()["status"] == "started"


def test_unassigned_lead_browser_call_does_not_persist_a_conversation(
    db_session: Session,
    api_db_override: None,
    voice_settings: None,
) -> None:
    client = TestClient(app)
    conversation = seed_voice_lead(db_session, client)
    assert conversation.lead_id is not None
    lead_id = conversation.lead_id
    owner = db_session.scalar(select(User).where(User.email == OWNER_EMAIL))
    caller_role = db_session.scalar(select(Role).where(Role.key == "prospecting_caller"))
    assert owner is not None
    assert caller_role is not None
    assigned_only_user = User(
        organization_id=owner.organization_id,
        email="unassigned-browser-caller@example.com",
        display_name="Unassigned Browser Caller",
        is_active=True,
    )
    db_session.add(assigned_only_user)
    db_session.flush()
    db_session.add(
        RoleAssignment(
            organization_id=owner.organization_id,
            user_id=assigned_only_user.id,
            role_id=caller_role.id,
        )
    )
    db_session.execute(
        delete(ConversationAssignmentEvent).where(
            ConversationAssignmentEvent.conversation_id == conversation.id
        )
    )
    db_session.execute(
        delete(ConversationContextLink).where(
            ConversationContextLink.conversation_id == conversation.id
        )
    )
    db_session.execute(delete(Conversation).where(Conversation.id == conversation.id))
    db_session.commit()
    assert db_session.get(Lead, lead_id) is not None

    response = client.post(
        f"/api/v1/voice/leads/{lead_id}/call-intents",
        headers={"X-Dev-User-Email": assigned_only_user.email},
        json={"idempotency_key": "unassigned-lead-browser-0001"},
    )

    assert response.status_code in {403, 404}, response.text
    db_session.rollback()
    assert int(db_session.scalar(select(func.count()).select_from(Conversation)) or 0) == 0
    assert int(db_session.scalar(select(func.count()).select_from(VoiceCallIntent)) or 0) == 0


def test_outbound_execution_rechecks_suppression_after_intent_creation(
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
    headers = {"X-Dev-User-Email": OWNER_EMAIL}
    quick_dial = client.post(
        "/api/v1/voice/quick-dial",
        headers=headers,
        json={
            "phone_number": "+14045550195",
            "company_name": "Suppression Test Vendor",
            "purpose": "vendor",
            "idempotency_key": "quick-dial-suppression-0001",
        },
    )
    assert quick_dial.status_code == 201, quick_dial.text
    result = quick_dial.json()
    contact = db_session.get(Contact, UUID(result["contact_id"]))
    assert contact is not None
    db_session.add(
        SuppressionRecord(
            organization_id=contact.organization_id,
            contact_id=contact.id,
            channel="phone",
            normalized_address="+14045550195",
            status="active",
            reason="Contact requested no calls.",
            source="manual",
            provider=None,
            external_event_id=None,
            suppressed_at=datetime.now(ZoneInfo("UTC")),
            lifted_at=None,
            suppression_metadata=None,
        )
    )
    db_session.commit()
    session = client.get("/api/v1/voice/session", headers=headers).json()

    outbound = post_signed(
        client,
        "/api/v1/webhooks/twilio/voice/outbound",
        {
            "From": f"client:{session['identity']}",
            "CallSid": "CA00000000000000000000000000000095",
            "CallIntentId": result["intent"]["id"],
        },
    )

    assert outbound.status_code == 422, outbound.text
    assert "suppressed from phone calls" in outbound.text
    assert int(db_session.scalar(select(func.count()).select_from(CallRecord)) or 0) == 0
    intent = db_session.get(VoiceCallIntent, UUID(result["intent"]["id"]))
    assert intent is not None
    assert intent.status == "pending"


def test_manual_call_treats_missing_permission_as_advisory_through_outbound_flow(
    db_session: Session,
    api_db_override: None,
    voice_settings: None,
) -> None:
    client = TestClient(app)
    conversation = seed_voice_lead(db_session, client)
    phone_consent = db_session.scalar(
        select(ConsentRecord).where(
            ConsentRecord.contact_id == conversation.contact_id,
            ConsentRecord.channel == "phone",
        )
    )
    assert phone_consent is not None
    db_session.delete(phone_consent)
    db_session.commit()
    headers = {"X-Dev-User-Email": OWNER_EMAIL}

    ready = client.post(
        f"/api/v1/voice/conversations/{conversation.id}/call-intents",
        headers=headers,
        json={"idempotency_key": "manual-permission-advisory-0001"},
    )

    assert ready.status_code == 201, ready.text
    assert ready.json()["recipient"] == SELLER_NUMBER
    detail = client.get(
        f"/api/v1/inbox/conversations/{conversation.id}",
        headers=headers,
    )
    assert detail.status_code == 200, detail.text
    assert detail.json()["voice_eligibility"]["can_call"] is True
    assert detail.json()["voice_eligibility"]["consent_status"] == "missing"
    session = client.get("/api/v1/voice/session", headers=headers).json()
    outbound = post_signed(
        client,
        "/api/v1/webhooks/twilio/voice/outbound",
        {
            "From": f"client:{session['identity']}",
            "CallSid": "CA00000000000000000000000000000097",
            "CallIntentId": ready.json()["id"],
        },
    )
    assert outbound.status_code == 200, outbound.text
    assert SELLER_NUMBER in outbound.text


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

    connect_path = f"/api/v1/webhooks/twilio/voice/forwarded-connect?intent_id={intent['id']}"
    connected = post_signed(
        client,
        connect_path,
        {"CallSid": "CA00000000000000000000000000000090", "Digits": "1"},
    )
    assert connected.status_code == 200, connected.text
    assert SELLER_NUMBER in connected.text
    assert f'callerId="{STONEGATE_NUMBER}"' in connected.text
    assert db_session.scalar(select(func.count()).select_from(CallRecord)) == 1


def test_forwarded_outbound_call_rechecks_suppression_before_connecting_seller(
    db_session: Session,
    api_db_override: None,
    voice_settings: None,
    monkeypatch: MonkeyPatch,
) -> None:
    class FakeVoiceProvider:
        def start(self, **kwargs: str) -> TwilioVoiceCallResult:
            return TwilioVoiceCallResult(
                sid="CA00000000000000000000000000000098",
                status="queued",
            )

    monkeypatch.setattr(
        "app.services.voice.get_twilio_voice_call_provider",
        lambda: FakeVoiceProvider(),
    )
    client = TestClient(app)
    conversation = seed_voice_lead(db_session, client)
    response = client.post(
        f"/api/v1/voice/conversations/{conversation.id}/forwarded-calls",
        headers={"X-Dev-User-Email": OWNER_EMAIL},
        json={"idempotency_key": "forwarded-call-suppression-0001"},
    )
    assert response.status_code == 201, response.text
    contact = db_session.get(Contact, conversation.contact_id)
    assert contact is not None
    db_session.add(
        SuppressionRecord(
            organization_id=contact.organization_id,
            contact_id=contact.id,
            channel="all",
            normalized_address=SELLER_NUMBER,
            status="active",
            reason="Contact requested no calls or texts.",
            source="manual",
            provider=None,
            external_event_id=None,
            suppressed_at=datetime.now(ZoneInfo("UTC")),
            lifted_at=None,
            suppression_metadata=None,
        )
    )
    db_session.commit()

    connect_path = (
        "/api/v1/webhooks/twilio/voice/forwarded-connect"
        f"?intent_id={response.json()['id']}"
    )
    connected = post_signed(
        client,
        connect_path,
        {"CallSid": "CA00000000000000000000000000000098", "Digits": "1"},
    )

    assert connected.status_code == 422, connected.text
    assert "suppressed from phone calls" in connected.text


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


def test_browser_call_intent_can_start_from_lead_page(
    db_session: Session,
    api_db_override: None,
    voice_settings: None,
) -> None:
    client = TestClient(app)
    conversation = seed_voice_lead(db_session, client)

    response = client.post(
        f"/api/v1/voice/leads/{conversation.lead_id}/call-intents",
        headers={"X-Dev-User-Email": OWNER_EMAIL},
        json={"idempotency_key": "lead-page-browser-call-0001"},
    )

    assert response.status_code == 201, response.text
    assert response.json()["conversation_id"] == str(conversation.id)
    assert response.json()["status"] == "pending"
    assert response.json()["recipient"] == SELLER_NUMBER
    assert db_session.scalar(select(func.count()).select_from(CallRecord)) == 0


def test_general_line_inbound_call_reuses_known_seller_conversation(
    db_session: Session,
    api_db_override: None,
    voice_settings: None,
) -> None:
    client = TestClient(app)
    conversation = seed_voice_lead(db_session, client)
    line = db_session.scalar(select(VoiceLine))
    assert line is not None
    line.department_key = "general"
    line.purpose_key = "company_general"
    db_session.commit()

    response = post_signed(
        client,
        "/api/v1/webhooks/twilio/voice/incoming",
        {
            "From": SELLER_NUMBER,
            "To": STONEGATE_NUMBER,
            "CallSid": "CA00000000000000000000000000000093",
        },
    )

    assert response.status_code == 200, response.text
    call = db_session.scalar(
        select(CallRecord).where(
            CallRecord.provider_call_id == "CA00000000000000000000000000000093"
        )
    )
    assert call is not None
    assert call.conversation_id == conversation.id
    assert call.lead_id == conversation.lead_id
    assert int(db_session.scalar(select(func.count()).select_from(Contact)) or 0) == 1
    assert int(db_session.scalar(select(func.count()).select_from(Lead)) or 0) == 1


def test_unknown_general_inbound_call_records_phone_permission(
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
    line = db_session.scalar(select(VoiceLine))
    assert line is not None
    line.department_key = "general"
    line.purpose_key = "company_general"
    db_session.commit()
    caller = "+14045550194"

    response = post_signed(
        client,
        "/api/v1/webhooks/twilio/voice/incoming",
        {
            "From": caller,
            "To": STONEGATE_NUMBER,
            "CallSid": "CA00000000000000000000000000000094",
        },
    )

    assert response.status_code == 200, response.text
    contact = db_session.scalar(
        select(Contact)
        .join(ContactMethod, ContactMethod.contact_id == Contact.id)
        .where(ContactMethod.normalized_value == "14045550194")
    )
    assert contact is not None
    assert contact.contact_type == "business_contact"
    consent = db_session.scalar(
        select(ConsentRecord).where(
            ConsentRecord.contact_id == contact.id,
            ConsentRecord.channel == "phone",
        )
    )
    assert consent is not None
    assert consent.status == "granted"
    assert consent.source == "inbound_call"
    assert evaluate_voice_eligibility(db_session, contact).can_call is True


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
    assert updated_call.status == "ringing"
    dial_result = post_signed(
        client,
        f"/api/v1/webhooks/twilio/voice/dial-result?call_id={call.id}",
        {
            "CallSid": inbound_payload["CallSid"],
            "DialCallStatus": "no-answer",
            "DialCallDuration": "0",
        },
    )
    assert dial_result.status_code == 200
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
                select(func.count()).select_from(Task).where(Task.task_type == "missed_call")
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
    inbound_lead = db_session.scalar(select(Lead).where(Lead.contact_id == contact.id))
    assert inbound_lead is not None
    ai_event = db_session.scalar(
        select(AiOrchestratorEvent).where(
            AiOrchestratorEvent.event_key == f"lead.created:{inbound_lead.id}"
        )
    )
    assert ai_event is not None
    assert ai_event.status == "queued"
    assert (ai_event.payload or {}).get("trigger_source") == "inbound_call"
    assert (
        int(
            db_session.scalar(
                select(func.count())
                .select_from(AiOrchestratorEvent)
                .where(AiOrchestratorEvent.event_key == ai_event.event_key)
            )
            or 0
        )
        == 1
    )


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

    recording_path = f"/api/v1/webhooks/twilio/voice/recording?intent_id={intent['id']}"
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


def test_recording_media_and_transcript_download_are_private_and_playable(
    db_session: Session,
    api_db_override: None,
    voice_settings: None,
    monkeypatch: MonkeyPatch,
) -> None:
    client = TestClient(app)
    conversation = seed_voice_lead(db_session, client)
    recording, transcript = create_call_assets(
        db_session,
        conversation,
        provider_suffix="private-media",
    )
    monkeypatch.setattr(
        "app.routers.voice.download_twilio_recording",
        lambda *_args: TwilioRecordingMedia(b"ID3-test-audio", "audio/mpeg"),
    )
    headers = {"X-Dev-User-Email": OWNER_EMAIL}

    media = client.get(
        f"/api/v1/voice/recordings/{recording.id}/media",
        headers=headers,
    )
    assert media.status_code == 200
    assert media.content == b"ID3-test-audio"
    assert media.headers["content-type"] == "audio/mpeg"
    assert media.headers["content-length"] == str(len(media.content))
    assert media.headers["cache-control"] == "private, no-store"
    assert media.headers["x-content-type-options"] == "nosniff"
    assert media.headers["content-disposition"].startswith("inline;")

    transcript_response = client.get(
        f"/api/v1/voice/transcripts/{transcript.id}",
        headers=headers,
    )
    assert transcript_response.status_code == 200
    assert transcript_response.json()["transcript_text"].startswith("Agent greeted")

    transcript_download = client.get(
        f"/api/v1/voice/transcripts/{transcript.id}/download",
        headers=headers,
    )
    assert transcript_download.status_code == 200
    assert transcript_download.headers["content-type"] == "text/plain; charset=utf-8"
    assert transcript_download.headers["cache-control"] == "private, no-store"
    assert transcript_download.headers["x-content-type-options"] == "nosniff"
    assert transcript_download.headers["content-disposition"].endswith('.txt"')
    assert transcript_download.text == "[00:12] Seller: I want to move in 30 days.\n"

    recording.status = "deleted"
    recording.deleted_at = datetime.now(ZoneInfo("UTC"))
    recording.media_reference = None
    db_session.commit()

    preserved_download = client.get(
        f"/api/v1/voice/transcripts/{transcript.id}/download",
        headers=headers,
    )
    assert preserved_download.status_code == 200
    assert "Seller: I want to move in 30 days." in preserved_download.text


def test_recording_and_transcript_routes_require_recording_access(
    db_session: Session,
    api_db_override: None,
    voice_settings: None,
) -> None:
    client = TestClient(app)
    conversation = seed_voice_lead(db_session, client)
    recording, transcript = create_call_assets(
        db_session,
        conversation,
        provider_suffix="permission-test",
    )
    administrator_role = db_session.scalar(select(Role).where(Role.key == "administrator"))
    assert administrator_role is not None
    user = User(
        organization_id=conversation.organization_id,
        email="administrator@example.com",
        display_name="Administrator",
        is_active=True,
    )
    db_session.add(user)
    db_session.flush()
    db_session.add(
        RoleAssignment(
            organization_id=conversation.organization_id,
            user_id=user.id,
            role_id=administrator_role.id,
        )
    )
    db_session.commit()
    headers = {"X-Dev-User-Email": user.email}

    assert (
        client.get(
            f"/api/v1/voice/recordings/{recording.id}/media",
            headers=headers,
        ).status_code
        == 403
    )
    assert (
        client.get(
            f"/api/v1/voice/transcripts/{transcript.id}",
            headers=headers,
        ).status_code
        == 403
    )
    assert (
        client.get(
            f"/api/v1/voice/transcripts/{transcript.id}/download",
            headers=headers,
        ).status_code
        == 403
    )


def test_recording_and_transcript_routes_enforce_scope_and_readiness(
    db_session: Session,
    api_db_override: None,
    voice_settings: None,
) -> None:
    client = TestClient(app)
    conversation = seed_voice_lead(db_session, client)
    recording, transcript = create_call_assets(
        db_session,
        conversation,
        provider_suffix="not-ready",
        recording_status="processing",
        transcript_status="queued",
        transcript_text=None,
        speaker_segments=[],
    )
    headers = {"X-Dev-User-Email": OWNER_EMAIL}

    media = client.get(
        f"/api/v1/voice/recordings/{recording.id}/media",
        headers=headers,
    )
    assert media.status_code == 409
    assert media.json()["detail"] == "Recording is not ready."
    transcript_status = client.get(
        f"/api/v1/voice/transcripts/{transcript.id}",
        headers=headers,
    )
    assert transcript_status.status_code == 200
    assert transcript_status.json()["status"] == "queued"
    transcript_download = client.get(
        f"/api/v1/voice/transcripts/{transcript.id}/download",
        headers=headers,
    )
    assert transcript_download.status_code == 409
    assert transcript_download.json()["detail"] == "Transcript text is not ready."

    other_organization = Organization(
        name="Other Company",
        slug="other-company",
        is_active=True,
    )
    db_session.add(other_organization)
    db_session.flush()
    other_contact = Contact(
        organization_id=other_organization.id,
        legal_name="Other Seller",
        preferred_name=None,
        contact_type="seller",
        assigned_user_id=None,
    )
    db_session.add(other_contact)
    db_session.flush()
    other_conversation = Conversation(
        organization_id=other_organization.id,
        conversation_type="general",
        lead_id=None,
        contact_id=other_contact.id,
        assigned_user_id=None,
        assigned_team_id=None,
        source_alias_id=None,
        visibility_scope="standard",
        status="open",
        queue_key="unassigned",
        priority="normal",
        unread_count=0,
        last_activity_at=datetime.now(ZoneInfo("UTC")),
        last_inbound_at=None,
        last_outbound_at=None,
        closed_at=None,
        conversation_metadata=None,
    )
    db_session.add(other_conversation)
    db_session.flush()
    other_recording, other_transcript = create_call_assets(
        db_session,
        other_conversation,
        provider_suffix="other-company",
    )

    assert (
        client.get(
            f"/api/v1/voice/recordings/{other_recording.id}/media",
            headers=headers,
        ).status_code
        == 404
    )
    assert (
        client.get(
            f"/api/v1/voice/transcripts/{other_transcript.id}",
            headers=headers,
        ).status_code
        == 404
    )
    assert (
        client.get(
            f"/api/v1/voice/transcripts/{other_transcript.id}/download",
            headers=headers,
        ).status_code
        == 404
    )


def test_recording_can_use_georgia_one_party_policy_without_announcement(
    db_session: Session,
    api_db_override: None,
    voice_settings: None,
    monkeypatch: MonkeyPatch,
) -> None:
    monkeypatch.setenv("TWILIO_VOICE_RECORDING_ENABLED", "true")
    monkeypatch.delenv("TWILIO_VOICE_RECORDING_DISCLOSURE", raising=False)
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
        "CallSid": "CA00000000000000000000000000000092",
        "CallIntentId": str(intent["id"]),
    }
    outbound = post_signed(
        client,
        "/api/v1/webhooks/twilio/voice/outbound",
        outbound_payload,
    )

    assert outbound.status_code == 200, outbound.text
    assert 'record="record-from-answer-dual"' in outbound.text
    assert "/voice/disclosure" not in outbound.text
    call = db_session.scalar(select(CallRecord))
    assert call is not None
    assert call.recording_consent_status == "one_party_consent"

    recording_path = f"/api/v1/webhooks/twilio/voice/recording?intent_id={intent['id']}"
    recording = post_signed(
        client,
        recording_path,
        {
            "CallSid": outbound_payload["CallSid"],
            "RecordingSid": "RE00000000000000000000000000000092",
            "RecordingStatus": "completed",
            "RecordingDuration": "60",
            "RecordingChannels": "2",
            "RecordingSource": "DialVerb",
        },
    )

    assert recording.status_code == 204, recording.text
    stored_recording = db_session.scalar(select(CallRecording))
    assert stored_recording is not None
    assert stored_recording.consent_status == "one_party_consent"
    assert db_session.scalar(select(func.count()).select_from(CallTranscript)) == 1


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
    assert (
        db_session.scalar(
            select(func.count())
            .select_from(AuditEvent)
            .where(AuditEvent.action == "communication.recording_delete")
        )
        == 1
    )

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
        int(db_session.scalar(select(func.count()).select_from(CommunicationProviderEvent)) or 0)
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
