from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient
from pytest import MonkeyPatch
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.auth import principal_for_user
from app.core.config import Settings, get_settings
from app.main import app
from app.models.foundation import (
    Appointment,
    CalendarEvent,
    CallRecord,
    Lead,
    ProspectingInboundCallback,
    SuppressionRecord,
    Task,
    User,
    VoiceLine,
)
from app.routers import openai_webhooks
from app.services.bootstrap import bootstrap_foundation
from app.services.realtime_seller_agent import (
    NATURAL_TOOL_RESPONSE_DELAYS,
    RealtimeSellerAgentError,
    _tool_lookup_callback_context,
    _tool_record_call_outcome,
    _tool_save_seller_details,
    _tool_schedule_human_callback,
    mark_realtime_call_failed,
    realtime_agent_instructions,
    realtime_session_configuration,
    register_realtime_call,
    sip_phone_number,
)
from app.services.voice import get_realtime_seller_agent_readiness, select_voice_line

AI_NUMBER = "+14708887952"
HUMAN_NUMBER = "+16785417725"
CALLER_NUMBER = "+17065550199"
OWNER_EMAIL = "owner@example.com"


def configure_realtime(monkeypatch: MonkeyPatch, *, enabled: bool = True) -> Settings:
    values = {
        "TWILIO_VOICE_FROM_NUMBER": AI_NUMBER,
        "TWILIO_WEBHOOK_BASE_URL": "https://api.stonegate.test",
        "OPENAI_REALTIME_VOICE_ENABLED": "true" if enabled else "false",
        "OPENAI_API_KEY": "test-openai-key",
        "OPENAI_PROJECT_ID": "proj_stonegate",
        "OPENAI_WEBHOOK_SECRET": "whsec_stonegate-test-secret",
        "OPENAI_REALTIME_LINE_NUMBER": AI_NUMBER,
        "OPENAI_REALTIME_TRANSFER_NUMBER": HUMAN_NUMBER,
    }
    for key, value in values.items():
        monkeypatch.setenv(key, value)
    get_settings.cache_clear()
    return get_settings()


def seed_realtime_call(
    db: Session,
    monkeypatch: MonkeyPatch,
    *,
    call_id: str = "rtc_seller_1",
) -> tuple[ProspectingInboundCallback, Settings]:
    settings = configure_realtime(monkeypatch)
    bootstrap_foundation(
        db,
        organization_name="Stonegate Home Buyers",
        admin_email=OWNER_EMAIL,
        admin_name="Owner",
    )
    registered = register_realtime_call(
        db,
        event=incoming_event(call_id),
        webhook_id=f"wh_{call_id}",
        settings=settings,
    )
    callback = db.get(ProspectingInboundCallback, registered.callback_id)
    assert callback is not None
    return callback, settings


def incoming_event(call_id: str) -> dict[str, Any]:
    return {
        "type": "realtime.call.incoming",
        "data": {
            "call_id": call_id,
            "sip_headers": [
                {"name": "From", "value": f"<sip:{CALLER_NUMBER}@caller.example>"},
                {
                    "name": "To",
                    "value": "<sip:proj_stonegate@sip.api.openai.com>",
                },
                {"name": "Diversion", "value": f"<sip:{AI_NUMBER}@twilio.com>"},
                {"name": "Call-ID", "value": f"sip-{call_id}"},
            ],
        },
    }


def seller_details(**overrides: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "seller_name": "Sam Seller",
        "street_address": "55 Auburn Avenue",
        "city": "Atlanta",
        "state": "GA",
        "postal_code": "30303",
        "property_type": "house",
        "owner_confirmed": True,
        "seller_interested": True,
        "occupancy_status": "vacant",
        "property_condition": "needs cosmetic work",
        "desired_timeline": "within 30 days",
        "motivation": "inherited property",
        "asking_price": "$180,000",
        "notes": "Caller wants a straightforward sale.",
    }
    payload.update(overrides)
    return payload


def test_bootstrap_reserves_ai_line_and_keeps_human_line_default(
    db_session: Session,
    monkeypatch: MonkeyPatch,
) -> None:
    settings = configure_realtime(monkeypatch)
    foundation = bootstrap_foundation(
        db_session,
        organization_name="Stonegate Home Buyers",
        admin_email=OWNER_EMAIL,
        admin_name="Owner",
    )
    lines = {
        line.phone_number: line
        for line in db_session.scalars(
            select(VoiceLine).where(VoiceLine.organization_id == foundation.organization.id)
        )
    }

    assert lines[HUMAN_NUMBER].is_default is True
    assert lines[HUMAN_NUMBER].purpose_key == "seller_conversations"
    assert lines[AI_NUMBER].is_default is False
    assert lines[AI_NUMBER].purpose_key == "seller_callback_ai"
    assert lines[AI_NUMBER].inbound_route == "openai_realtime"
    assert "+14047772631" not in lines
    assert foundation.admin_user is not None
    selected = select_voice_line(
        db_session,
        foundation.organization.id,
        foundation.admin_user.id,
    )
    assert selected is not None
    assert selected.phone_number == settings.openai_realtime_transfer_number


def test_realtime_session_is_natural_constrained_and_private() -> None:
    settings = Settings()
    session = realtime_session_configuration(settings)
    instructions = realtime_agent_instructions()

    assert session["model"] == "gpt-realtime-2.1"
    assert session["audio"]["output"]["voice"] == "marin"
    assert "voice" not in session
    assert session["audio"]["input"]["turn_detection"]["type"] == "semantic_vad"
    assert session["reasoning"] == {"effort": "minimal"}
    assert session["audio"]["input"]["turn_detection"]["eagerness"] == "auto"
    assert session["audio"]["input"]["noise_reduction"] == {"type": "near_field"}
    assert session["audio"]["input"]["transcription"]["model"] == "gpt-4o-transcribe"
    assert session["parallel_tool_calls"] is False
    assert session["max_output_tokens"] == 500
    assert "Open warmly in two or three very short sentences." in instructions
    assert "around 25 to 30 spoken words" in instructions
    assert "We may have called to see if you'd consider an offer on a property." in instructions
    assert "The example is not a script." in instructions
    assert "Vary the wording naturally" in instructions
    assert "Never imply that you know the caller" in instructions
    assert "Do not ask the caller to remember which property" in instructions
    assert "before asking their name" in instructions
    assert "do not guess" in instructions
    assert 'say "gracias por llamar" rather than "gracias por contestar."' in instructions
    assert "ask multiple questions in the opening" in instructions
    assert "only need two or three quick details" in instructions
    assert "collect only these essentials" in instructions
    assert "Once the essentials are known, immediately offer the human handoff" in instructions
    assert "never ask for them as a requirement" in instructions
    assert "A phone-number match alone is not identity verification." in instructions
    assert "first offer to connect them with an Acquisitions Manager now" in instructions
    assert "books the Acquisitions callback on Stonegate's internal calendar" in instructions
    assert "without inventing an appointment or follow-up task" in instructions
    assert 'Do not say "let me check,"' in instructions
    assert NATURAL_TOOL_RESPONSE_DELAYS == {
        "lookup_callback_context": 0.25,
        "schedule_human_callback": 0.75,
    }
    assert {tool["name"] for tool in session["tools"]} == {
        "lookup_callback_context",
        "save_seller_details",
        "schedule_human_callback",
        "transfer_to_acquisitions",
        "record_call_outcome",
        "wait_for_user",
        "finish_call",
    }


def test_call_registration_is_idempotent(
    db_session: Session,
    monkeypatch: MonkeyPatch,
) -> None:
    callback, settings = seed_realtime_call(db_session, monkeypatch)
    duplicate = register_realtime_call(
        db_session,
        event=incoming_event(callback.provider_call_id),
        webhook_id="wh_retry",
        settings=settings,
    )

    assert duplicate.created is False
    assert duplicate.callback_id == callback.id
    assert db_session.scalar(select(func.count()).select_from(ProspectingInboundCallback)) == 1
    assert db_session.scalar(select(func.count()).select_from(CallRecord)) == 1


def test_failed_call_preserves_partial_transcript_for_review(
    db_session: Session,
    monkeypatch: MonkeyPatch,
) -> None:
    callback, settings = seed_realtime_call(db_session, monkeypatch)
    registered = register_realtime_call(
        db_session,
        event=incoming_event(callback.provider_call_id),
        webhook_id="wh_failure_retry",
        settings=settings,
    )

    mark_realtime_call_failed(
        db_session,
        registered,
        error="Realtime connection closed unexpectedly.",
        transcript=[
            {"speaker": "caller", "text": "I am calling back about my property."},
            {"speaker": "marin", "text": "I can help with that."},
        ],
    )

    db_session.refresh(callback)
    call = db_session.scalar(
        select(CallRecord).where(CallRecord.prospecting_inbound_callback_id == callback.id)
    )
    assert call is not None
    assert callback.status == "failed"
    assert callback.routing_metadata["outcome"] == "agent_failed"
    assert callback.routing_metadata["transcript"][0]["speaker"] == "caller"
    assert callback.routing_metadata["transcript_complete"] is False
    assert call.call_metadata is not None
    assert call.call_metadata["transcript"][1]["speaker"] == "marin"
    assert call.duration_seconds is not None


def test_marin_call_review_is_company_visible_and_keeps_human_findings(
    db_session: Session,
    api_db_override: None,
    monkeypatch: MonkeyPatch,
) -> None:
    del api_db_override
    callback, _ = seed_realtime_call(db_session, monkeypatch)
    call = db_session.scalar(
        select(CallRecord).where(CallRecord.prospecting_inbound_callback_id == callback.id)
    )
    assert call is not None
    now = datetime.now(UTC)
    callback.status = "completed"
    callback.completed_at = now
    callback.routing_metadata = {
        **callback.routing_metadata,
        "outcome": "interested",
        "summary": "Interested owner asked for an acquisitions follow-up.",
        "seller_details": {
            "seller_name": "Sam Seller",
            "street_address": "55 Auburn Avenue",
            "city": "Atlanta",
            "state": "GA",
            "postal_code": "30303",
        },
        "transcript": [
            {"speaker": "caller", "text": "I may sell if the offer makes sense."},
            {"speaker": "marin", "text": "I can connect you with our acquisitions team."},
        ],
        "tool_events": [
            {
                "name": "save_seller_details",
                "succeeded": True,
                "occurred_at": now.isoformat(),
            }
        ],
    }
    call.status = "completed"
    call.ended_at = now
    call.duration_seconds = 74
    call.disposition = "interested"
    call.call_metadata = {
        **(call.call_metadata or {}),
        "transcript": callback.routing_metadata["transcript"],
    }
    db_session.commit()

    client = TestClient(app)
    owner_headers = {"X-Dev-User-Email": OWNER_EMAIL}
    va_email = "marin-review-va@example.com"
    created = client.post(
        "/api/v1/operations/users",
        headers=owner_headers,
        json={
            "email": va_email,
            "display_name": "Marin Review VA",
            "role_key": "prospecting_caller",
        },
    )
    assert created.status_code == 201, created.text
    va_headers = {"X-Dev-User-Email": va_email}

    dashboard = client.get("/api/v1/voice/marin-calls", headers=va_headers)
    assert dashboard.status_code == 200, dashboard.text
    payload = dashboard.json()
    assert payload["stats"]["total_calls"] == 1
    assert payload["stats"]["total_unique_callers"] == 1
    assert payload["stats"]["calls_today"] == 1
    assert payload["items"][0]["seller_name"] == "Sam Seller"
    assert payload["items"][0]["transcript_turn_count"] == 2

    detail = client.get(f"/api/v1/voice/marin-calls/{callback.id}", headers=va_headers)
    assert detail.status_code == 200, detail.text
    assert detail.json()["transcript"][0] == {
        "speaker": "caller",
        "text": "I may sell if the offer makes sense.",
    }
    assert detail.json()["tool_events"][0]["name"] == "save_seller_details"

    reviewed = client.patch(
        f"/api/v1/voice/marin-calls/{callback.id}/review",
        headers=va_headers,
        json={
            "status": "flagged",
            "flags": ["awkward_wording", "missed_intent"],
            "notes": "Marin should have asked one shorter follow-up question.",
        },
    )
    assert reviewed.status_code == 200, reviewed.text
    assert reviewed.json()["review"]["status"] == "flagged"
    assert reviewed.json()["review"]["reviewer_name"] == "Marin Review VA"
    assert reviewed.json()["needs_review"] is True

    resolved = client.patch(
        f"/api/v1/voice/marin-calls/{callback.id}/review",
        headers=owner_headers,
        json={
            "status": "resolved",
            "flags": ["awkward_wording", "missed_intent"],
            "notes": "Prompt adjusted and verified.",
        },
    )
    assert resolved.status_code == 200, resolved.text
    assert resolved.json()["review"]["status"] == "resolved"
    assert resolved.json()["needs_review"] is False


def test_call_registration_accepts_destination_from_to_header(
    db_session: Session,
    monkeypatch: MonkeyPatch,
) -> None:
    settings = configure_realtime(monkeypatch)
    bootstrap_foundation(
        db_session,
        organization_name="Stonegate Home Buyers",
        admin_email=OWNER_EMAIL,
        admin_name="Owner",
    )
    event = incoming_event("rtc_openai_example")
    event["data"]["sip_headers"] = [
        {"name": "From", "value": f"<sip:{CALLER_NUMBER}@caller.example>"},
        {"name": "To", "value": f"<sip:{AI_NUMBER}@sip.api.openai.com>"},
        {"name": "Call-ID", "value": "sip-rtc_openai_example"},
    ]

    registered = register_realtime_call(
        db_session,
        event=event,
        webhook_id="wh_openai_example",
        settings=settings,
    )

    assert registered.called_number == AI_NUMBER


def test_sip_parser_does_not_mistake_project_id_for_phone_number() -> None:
    assert sip_phone_number("<sip:proj_123456789012@sip.api.openai.com>") is None


def test_call_registration_rejects_non_marin_diversion_number(
    db_session: Session,
    monkeypatch: MonkeyPatch,
) -> None:
    settings = configure_realtime(monkeypatch)
    bootstrap_foundation(
        db_session,
        organization_name="Stonegate Home Buyers",
        admin_email=OWNER_EMAIL,
        admin_name="Owner",
    )
    event = incoming_event("rtc_wrong_destination")
    event["data"]["sip_headers"] = [
        {"name": "From", "value": f"<sip:{CALLER_NUMBER}@caller.example>"},
        {"name": "To", "value": f"<sip:{AI_NUMBER}@sip.api.openai.com>"},
        {"name": "Diversion", "value": f"<sip:{HUMAN_NUMBER}@twilio.com>"},
        {"name": "Call-ID", "value": "sip-rtc_wrong_destination"},
    ]

    with pytest.raises(
        RealtimeSellerAgentError,
        match="Incoming SIP call was not addressed to the Marin line",
    ):
        register_realtime_call(
            db_session,
            event=event,
            webhook_id="wh_wrong_destination",
            settings=settings,
        )


def test_agent_creates_no_lead_or_task_until_caller_is_qualified_and_agrees(
    db_session: Session,
    monkeypatch: MonkeyPatch,
) -> None:
    callback, _ = seed_realtime_call(db_session, monkeypatch)

    declined = _tool_save_seller_details(
        db_session,
        callback,
        seller_details(seller_interested=False),
    )
    db_session.flush()
    assert declined["lead_created"] is False
    assert db_session.scalar(select(func.count()).select_from(Lead)) == 0
    assert db_session.scalar(select(func.count()).select_from(Task)) == 0

    qualified = _tool_save_seller_details(db_session, callback, seller_details())
    db_session.flush()
    assert qualified["lead_created"] is True
    assert db_session.scalar(select(func.count()).select_from(Lead)) == 1
    assert db_session.scalar(select(func.count()).select_from(Task)) == 0
    lead = db_session.scalar(select(Lead))
    assert lead is not None
    assert lead.source == "batchdialer_callback"
    assert lead.stage_key == "qualification_in_progress"

    first_time = datetime.now(UTC) + timedelta(days=2)
    second_time = first_time + timedelta(hours=1)
    _tool_schedule_human_callback(
        db_session,
        callback,
        {
            "callback_at": first_time.isoformat(),
            "reason": "Seller asked for Austin after work.",
            "caller_confirmed": True,
        },
    )
    _tool_schedule_human_callback(
        db_session,
        callback,
        {
            "callback_at": second_time.isoformat(),
            "reason": "Seller corrected the agreed time.",
            "caller_confirmed": True,
        },
    )
    tasks = list(db_session.scalars(select(Task)))
    appointments = list(db_session.scalars(select(Appointment)))
    calendar_events = list(db_session.scalars(select(CalendarEvent)))
    assert len(tasks) == 1
    assert len(appointments) == 1
    assert len(calendar_events) == 1
    assert tasks[0].due_at is not None
    assert tasks[0].due_at.replace(tzinfo=UTC) == second_time
    assert tasks[0].completion_notes == "Seller corrected the agreed time."
    assert appointments[0].appointment_type == "acquisition_callback"
    assert appointments[0].location_type == "phone"
    assert appointments[0].location == CALLER_NUMBER
    assert appointments[0].status == "rescheduled"
    assert appointments[0].scheduled_start_at.replace(tzinfo=UTC) == second_time
    assert appointments[0].scheduled_end_at is not None
    assert appointments[0].scheduled_end_at.replace(tzinfo=UTC) == second_time + timedelta(
        minutes=30
    )
    assert calendar_events[0].appointment_id == appointments[0].id
    assert calendar_events[0].provider == "internal"
    assert calendar_events[0].status == "rescheduled"
    assert lead.stage_key == "appointment_scheduled"
    assert lead.appointment_status == "rescheduled"


def test_lookup_never_reveals_stored_property_before_identity_match(
    db_session: Session,
    monkeypatch: MonkeyPatch,
) -> None:
    first_callback, settings = seed_realtime_call(db_session, monkeypatch)
    _tool_save_seller_details(db_session, first_callback, seller_details())
    db_session.commit()
    second_registered = register_realtime_call(
        db_session,
        event=incoming_event("rtc_seller_2"),
        webhook_id="wh_rtc_seller_2",
        settings=settings,
    )
    callback = db_session.get(ProspectingInboundCallback, second_registered.callback_id)
    assert callback is not None

    unverified = _tool_lookup_callback_context(
        db_session,
        callback,
        {"caller_name": "Someone Else"},
    )
    assert unverified["verified"] is False
    assert "seller_name" not in unverified
    assert "property_address" not in unverified

    verified = _tool_lookup_callback_context(
        db_session,
        callback,
        {"caller_name": "Sam Seller"},
    )
    assert verified["verified"] is True
    assert verified["property_address"] == "55 Auburn Avenue, Atlanta, GA, 30303"


def test_explicit_do_not_contact_suppresses_voice_and_sms(
    db_session: Session,
    monkeypatch: MonkeyPatch,
) -> None:
    callback, _ = seed_realtime_call(db_session, monkeypatch)
    result = _tool_record_call_outcome(
        db_session,
        callback,
        {
            "outcome": "do_not_contact",
            "notes": "Caller explicitly asked not to be contacted again.",
            "do_not_contact_confirmed": True,
        },
    )
    db_session.flush()

    assert result["saved"] is True
    suppressions = list(
        db_session.scalars(
            select(SuppressionRecord).where(
                SuppressionRecord.normalized_address == CALLER_NUMBER,
            )
        )
    )
    assert {item.channel for item in suppressions} == {"phone", "sms"}


def test_readiness_exposes_only_admin_setup_values(
    db_session: Session,
    monkeypatch: MonkeyPatch,
) -> None:
    configure_realtime(monkeypatch)
    foundation = bootstrap_foundation(
        db_session,
        organization_name="Stonegate Home Buyers",
        admin_email=OWNER_EMAIL,
        admin_name="Owner",
    )
    assert foundation.admin_user is not None
    readiness = get_realtime_seller_agent_readiness(
        db_session,
        principal_for_user(db_session, foundation.admin_user),
    )

    assert readiness.configured is True
    assert readiness.ai_line_number == AI_NUMBER
    assert readiness.human_transfer_number == HUMAN_NUMBER
    assert readiness.webhook_url == "https://api.stonegate.test/api/v1/webhooks/openai/realtime"
    assert readiness.sip_uri == "sip:proj_stonegate@sip.api.openai.com;transport=tls"


def test_readiness_rejects_crossed_or_placeholder_line_configuration(
    db_session: Session,
    monkeypatch: MonkeyPatch,
) -> None:
    configure_realtime(monkeypatch)
    monkeypatch.setenv("OPENAI_PROJECT_ID", "stonegate")
    monkeypatch.setenv("OPENAI_REALTIME_LINE_NUMBER", HUMAN_NUMBER)
    monkeypatch.setenv("OPENAI_REALTIME_TRANSFER_NUMBER", AI_NUMBER)
    get_settings.cache_clear()
    settings = get_settings()

    assert settings.openai_realtime_voice_configured is False
    assert "OPENAI_PROJECT_ID must start with proj_" in (
        settings.openai_realtime_voice_configuration_blockers
    )
    assert "OPENAI_REALTIME_LINE_NUMBER must be +14708887952" in (
        settings.openai_realtime_voice_configuration_blockers
    )
    assert "OPENAI_REALTIME_TRANSFER_NUMBER must be +16785417725" in (
        settings.openai_realtime_voice_configuration_blockers
    )
    foundation = bootstrap_foundation(
        db_session,
        organization_name="Stonegate Home Buyers",
        admin_email=OWNER_EMAIL,
        admin_name="Owner",
    )
    assert foundation.admin_user is not None
    readiness = get_realtime_seller_agent_readiness(
        db_session,
        principal_for_user(db_session, foundation.admin_user),
    )
    assert readiness.configured is False


def test_incoming_webhook_accepts_once_and_starts_monitor(
    db_session: Session,
    api_db_override: None,
    monkeypatch: MonkeyPatch,
) -> None:
    del api_db_override
    configure_realtime(monkeypatch)
    bootstrap_foundation(
        db_session,
        organization_name="Stonegate Home Buyers",
        admin_email=OWNER_EMAIL,
        admin_name="Owner",
    )
    accepted: list[tuple[str, dict[str, Any]]] = []
    monitored: list[str] = []

    class FakeRealtimeClient:
        def __init__(self, settings: Settings) -> None:
            del settings

        async def accept(self, call_id: str, session: dict[str, Any]) -> None:
            accepted.append((call_id, session))

        async def reject(self, call_id: str, *, status_code: int = 480) -> None:
            raise AssertionError((call_id, status_code))

    monkeypatch.setattr(
        openai_webhooks,
        "unwrap_openai_webhook",
        lambda body, headers, settings: incoming_event("rtc_webhook"),
    )
    monkeypatch.setattr(openai_webhooks, "OpenAIRealtimeCallClient", FakeRealtimeClient)
    monkeypatch.setattr(
        openai_webhooks,
        "start_realtime_call_monitor",
        lambda call: monitored.append(call.call_id),
    )

    with TestClient(app) as client:
        response = client.post(
            "/api/v1/webhooks/openai/realtime",
            content=b"{}",
            headers={"webhook-id": "wh_webhook"},
        )

    assert response.status_code == 204
    assert [item[0] for item in accepted] == ["rtc_webhook"]
    assert monitored == ["rtc_webhook"]
    callback = db_session.scalar(
        select(ProspectingInboundCallback).where(
            ProspectingInboundCallback.provider_call_id == "rtc_webhook"
        )
    )
    assert callback is not None
    assert callback.status == "answered"
    user = db_session.scalar(select(User).where(User.email == OWNER_EMAIL))
    assert user is not None
