from __future__ import annotations

import hashlib
import hmac
import json
from datetime import UTC, datetime

from fastapi.testclient import TestClient
from pytest import MonkeyPatch
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.main import app
from app.models.foundation import CallRecord, Lead, ProspectingInboundCallback, VoiceLine
from app.services.bootstrap import bootstrap_foundation

AI_NUMBER = "+14708887952"
HUMAN_NUMBER = "+16785417725"
CALLER_NUMBER = "+17065550199"
AGENT_ID = "agent_0101m2b1nejvfdz8ev4pznm59pwz"
TOOL_SECRET = "stonegate-elevenlabs-tool-secret"
WEBHOOK_SECRET = "stonegate-elevenlabs-webhook-secret"
OWNER_EMAIL = "owner@example.com"


def configure_elevenlabs(monkeypatch: MonkeyPatch) -> Settings:
    values = {
        "TWILIO_VOICE_FROM_NUMBER": AI_NUMBER,
        "TWILIO_WEBHOOK_BASE_URL": "https://api.stonegate.test",
        "SELLER_CALLBACK_AGENT_PROVIDER": "elevenlabs",
        "ELEVENLABS_AGENT_ENABLED": "true",
        "ELEVENLABS_AGENT_ID": AGENT_ID,
        "ELEVENLABS_WEBHOOK_SECRET": WEBHOOK_SECRET,
        "ELEVENLABS_TOOL_SECRET": TOOL_SECRET,
        "ELEVENLABS_LINE_NUMBER": AI_NUMBER,
        "ELEVENLABS_TRANSFER_NUMBER": HUMAN_NUMBER,
    }
    for key, value in values.items():
        monkeypatch.setenv(key, value)
    get_settings.cache_clear()
    return get_settings()


def seed_foundation(db: Session, monkeypatch: MonkeyPatch) -> Settings:
    settings = configure_elevenlabs(monkeypatch)
    bootstrap_foundation(
        db,
        organization_name="Stonegate Home Buyers",
        admin_email=OWNER_EMAIL,
        admin_name="Owner",
    )
    return settings


def initiation_payload(conversation_id: str = "conv_stonegate_1") -> dict[str, str]:
    return {
        "caller_id": CALLER_NUMBER,
        "called_number": AI_NUMBER,
        "agent_id": AGENT_ID,
        "call_sid": "CAelevenlabs1",
        "conversation_id": conversation_id,
    }


def signed_headers(payload: dict[str, object], *, timestamp: int) -> dict[str, str]:
    raw = json.dumps(payload, separators=(",", ":"))
    digest = hmac.new(
        WEBHOOK_SECRET.encode(),
        f"{timestamp}.{raw}".encode(),
        hashlib.sha256,
    ).hexdigest()
    return {
        "Content-Type": "application/json",
        "ElevenLabs-Signature": f"t={timestamp},v0={digest}",
        "X-Raw-Body": raw,
    }


def test_elevenlabs_settings_are_safe_by_default_and_validate_fixed_numbers() -> None:
    settings = Settings()

    assert settings.seller_callback_agent_provider == "openai_realtime"
    assert settings.elevenlabs_agent_enabled is False
    assert "ELEVENLABS_AGENT_ENABLED=true" in settings.elevenlabs_agent_configuration_blockers
    assert settings.elevenlabs_line_number == AI_NUMBER
    assert settings.elevenlabs_transfer_number == HUMAN_NUMBER


def test_conversation_initiation_is_authenticated_and_idempotent(
    db_session: Session,
    api_db_override: None,
    monkeypatch: MonkeyPatch,
) -> None:
    del api_db_override
    seed_foundation(db_session, monkeypatch)
    client = TestClient(app)
    payload = initiation_payload()

    unauthorized = client.post(
        "/api/v1/webhooks/elevenlabs/conversation-initiation",
        json=payload,
    )
    assert unauthorized.status_code == 401

    headers = {"X-Stonegate-Agent-Secret": TOOL_SECRET}
    created = client.post(
        "/api/v1/webhooks/elevenlabs/conversation-initiation",
        headers=headers,
        json=payload,
    )
    repeated = client.post(
        "/api/v1/webhooks/elevenlabs/conversation-initiation",
        headers=headers,
        json=payload,
    )

    assert created.status_code == 200, created.text
    assert repeated.status_code == 200, repeated.text
    assert created.json()["user_id"] == repeated.json()["user_id"]
    assert created.json()["dynamic_variables"] == {}
    assert (
        db_session.scalar(select(func.count()).select_from(ProspectingInboundCallback)) == 1
    )
    callback = db_session.scalar(select(ProspectingInboundCallback))
    assert callback is not None
    assert callback.provider == "elevenlabs"
    assert callback.status == "routing"
    line = db_session.get(VoiceLine, callback.voice_line_id)
    assert line is not None
    assert line.label == "Caroline seller callback"
    assert line.inbound_route == "elevenlabs"


def test_tool_capture_creates_one_lead_and_is_idempotent(
    db_session: Session,
    api_db_override: None,
    monkeypatch: MonkeyPatch,
) -> None:
    del api_db_override
    seed_foundation(db_session, monkeypatch)
    client = TestClient(app)
    headers = {"X-Stonegate-Agent-Secret": TOOL_SECRET}
    assert client.post(
        "/api/v1/webhooks/elevenlabs/conversation-initiation",
        headers=headers,
        json=initiation_payload(),
    ).status_code == 200
    tool_payload = {
        **initiation_payload(),
        "interest_level": "depends_on_numbers",
        "interest_basis": "Caller said they would consider an offer if the price makes sense.",
        "seller_name": "Sam Seller",
        "property_type": "land",
        "city": "Ringgold",
        "state": "GA",
        "owner_confirmed": True,
    }

    first = client.post(
        "/api/v1/webhooks/elevenlabs/tools/capture_seller_interest",
        headers=headers,
        json=tool_payload,
    )
    repeated = client.post(
        "/api/v1/webhooks/elevenlabs/tools/capture_seller_interest",
        headers=headers,
        json=tool_payload,
    )

    assert first.status_code == 200, first.text
    assert repeated.status_code == 200, repeated.text
    assert first.json()["ok"] is True
    assert db_session.scalar(select(func.count()).select_from(Lead)) == 1
    callback = db_session.scalar(select(ProspectingInboundCallback))
    assert callback is not None
    assert callback.routing_metadata["lead_capture_status"] == "provisional"
    assert len(callback.routing_metadata["tool_call_ids"]) == 1


def test_signed_post_call_saves_transcript_and_appears_in_call_review(
    db_session: Session,
    api_db_override: None,
    monkeypatch: MonkeyPatch,
) -> None:
    del api_db_override
    seed_foundation(db_session, monkeypatch)
    client = TestClient(app)
    tool_headers = {"X-Stonegate-Agent-Secret": TOOL_SECRET}
    assert client.post(
        "/api/v1/webhooks/elevenlabs/conversation-initiation",
        headers=tool_headers,
        json=initiation_payload(),
    ).status_code == 200
    timestamp = round(datetime.now(UTC).timestamp())
    event: dict[str, object] = {
        "type": "post_call_transcription",
        "event_timestamp": timestamp,
        "data": {
            "agent_id": AGENT_ID,
            "agent_name": "Caroline | Stonegate Seller Callback",
            "conversation_id": "conv_stonegate_1",
            "status": "done",
            "version_id": "agtvrsn_stonegate_1",
            "environment": "production",
            "transcript": [
                {
                    "role": "agent",
                    "message": "Hi, you've reached Stonegate Home Buyers. This is Caroline.",
                    "time_in_call_secs": 0,
                },
                {
                    "role": "user",
                    "message": "I was returning a call about an offer.",
                    "time_in_call_secs": 4,
                },
            ],
            "metadata": {
                "start_time_unix_secs": timestamp - 18,
                "call_duration_secs": 18,
                "termination_reason": "user_hangup",
                "phone_call": {
                    "type": "twilio",
                    "agent_number": AI_NUMBER,
                    "external_number": CALLER_NUMBER,
                    "direction": "inbound",
                    "call_sid": "CAelevenlabs1",
                },
            },
            "analysis": {
                "call_successful": "success",
                "transcript_summary": "Caller returned Stonegate's call about a possible offer.",
                "data_collection_results": {},
            },
            "has_audio": True,
            "has_user_audio": True,
            "has_response_audio": True,
        },
    }
    headers = signed_headers(event, timestamp=timestamp)
    raw_body = headers.pop("X-Raw-Body")

    response = client.post(
        "/api/v1/webhooks/elevenlabs/post-call",
        headers=headers,
        content=raw_body,
    )
    duplicate = client.post(
        "/api/v1/webhooks/elevenlabs/post-call",
        headers=headers,
        content=raw_body,
    )

    assert response.status_code == 200, response.text
    assert duplicate.status_code == 200, duplicate.text
    callback = db_session.scalar(select(ProspectingInboundCallback))
    assert callback is not None
    assert callback.status == "completed"
    assert callback.routing_metadata["agent_name"].startswith("Caroline")
    assert callback.routing_metadata["transcript"][1] == {
        "speaker": "caller",
        "text": "I was returning a call about an offer.",
    }
    record = db_session.scalar(select(CallRecord))
    assert record is not None
    assert record.duration_seconds == 18
    dashboard = client.get(
        "/api/v1/voice/marin-calls",
        headers={"X-Dev-User-Email": OWNER_EMAIL},
    )
    assert dashboard.status_code == 200, dashboard.text
    assert dashboard.json()["stats"]["total_calls"] == 1
    assert dashboard.json()["items"][0]["agent_name"].startswith("Caroline")
    assert dashboard.json()["items"][0]["transcript_turn_count"] == 2


def test_signed_call_initiation_failure_is_saved_for_review(
    db_session: Session,
    api_db_override: None,
    monkeypatch: MonkeyPatch,
) -> None:
    del api_db_override
    seed_foundation(db_session, monkeypatch)
    client = TestClient(app)
    assert client.post(
        "/api/v1/webhooks/elevenlabs/conversation-initiation",
        headers={"X-Stonegate-Agent-Secret": TOOL_SECRET},
        json=initiation_payload("conv_failed_1"),
    ).status_code == 200
    timestamp = round(datetime.now(UTC).timestamp())
    event: dict[str, object] = {
        "type": "call_initiation_failure",
        "event_timestamp": timestamp,
        "data": {
            "agent_id": AGENT_ID,
            "conversation_id": "conv_failed_1",
            "failure_reason": "Twilio rejected the call connection",
        },
    }
    headers = signed_headers(event, timestamp=timestamp)
    raw_body = headers.pop("X-Raw-Body")

    response = client.post(
        "/api/v1/webhooks/elevenlabs/post-call",
        headers=headers,
        content=raw_body,
    )
    duplicate = client.post(
        "/api/v1/webhooks/elevenlabs/post-call",
        headers=headers,
        content=raw_body,
    )

    assert response.status_code == 200, response.text
    assert duplicate.status_code == 200, duplicate.text
    callback = db_session.scalar(select(ProspectingInboundCallback))
    assert callback is not None
    assert callback.status == "failed"
    assert callback.routing_metadata["outcome"] == "agent_failed"
    assert callback.routing_metadata["failure_reason"] == "Twilio rejected the call connection"
    record = db_session.scalar(select(CallRecord))
    assert record is not None
    assert record.status == "failed"
    assert record.disposition == "agent_failed"
    dashboard = client.get(
        "/api/v1/voice/marin-calls",
        headers={"X-Dev-User-Email": OWNER_EMAIL},
    )
    assert dashboard.status_code == 200, dashboard.text
    assert dashboard.json()["stats"]["needs_review"] == 1


def test_post_call_rejects_invalid_signature(
    db_session: Session,
    api_db_override: None,
    monkeypatch: MonkeyPatch,
) -> None:
    del db_session, api_db_override
    configure_elevenlabs(monkeypatch)

    response = TestClient(app).post(
        "/api/v1/webhooks/elevenlabs/post-call",
        headers={"ElevenLabs-Signature": "t=1,v0=bad"},
        json={"type": "post_call_transcription", "data": {}},
    )

    assert response.status_code == 401
