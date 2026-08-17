import hashlib
import hmac
import json
from collections.abc import Iterator
from typing import cast
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from httpx import Response
from pytest import MonkeyPatch
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.main import app
from app.models.foundation import (
    ActivityEvent,
    AiOrchestratorEvent,
    Appointment,
    AttributionTouch,
    ConsentRecord,
    Lead,
    LeadFormSubmission,
    LeadManagementCase,
    PropertyResearchRun,
    ProspectingProviderEvent,
    StaffLeadAlert,
    SuppressionRecord,
    User,
)
from app.services.batchdialer_zapier import process_next_batchdialer_event
from app.services.bootstrap import bootstrap_foundation

ENDPOINT = "/api/v1/webhooks/zapier/batchdialer"
SECRET = "batchdialer-test-secret-0123456789abcdef"
CAMPAIGN_ID = "batch-campaign-atlanta-01"


@pytest.fixture
def batchdialer_settings(monkeypatch: MonkeyPatch) -> Iterator[Settings]:
    values = {
        "ZAPIER_BATCHDIALER_ENABLED": "true",
        "ZAPIER_BATCHDIALER_WEBHOOK_SECRET": SECRET,
        "ZAPIER_BATCHDIALER_ALLOWED_CAMPAIGN_IDS": CAMPAIGN_ID,
        "ZAPIER_BATCHDIALER_RETRY_BASE_SECONDS": "5",
        "STAFF_LEAD_ALERT_SMS_MODE": "simulate",
    }
    for key, value in values.items():
        monkeypatch.setenv(key, value)
    get_settings.cache_clear()
    settings = get_settings()
    try:
        yield settings
    finally:
        get_settings.cache_clear()


def seed_owner(db_session: Session) -> User:
    result = bootstrap_foundation(
        db_session,
        organization_name="Stonegate Home Buyers",
        admin_email="owner@example.com",
        admin_name="Owner",
    )
    assert result.admin_user is not None
    result.admin_user.voice_forwarding_number = "+14045550123"
    result.admin_user.lead_alert_sms_enabled = True
    db_session.commit()
    return result.admin_user


def lead_payload(
    *,
    event_id: str = "batch-event-lead-001",
    provider_contact_id: str = "batch-contact-001",
    permission: str = "phone",
) -> dict[str, object]:
    return {
        "event_id": event_id,
        "event_type": "lead.created",
        "occurred_at": "2026-08-17T14:30:00-04:00",
        "campaign_id": CAMPAIGN_ID,
        "campaign_name": "Atlanta absentee owners",
        "provider_contact_id": provider_contact_id,
        "provider_call_id": "batch-call-001",
        "provider_agent_id": "batch-agent-ava",
        "va_name": "Ava Caller",
        "va_email": "ava@example.com",
        "full_name": "Jane Seller",
        "phone": "+14045550199",
        "email": "jane.seller@example.com",
        "property_address": "101 Batch Lane",
        "property_city": "Atlanta",
        "property_state": "GA",
        "property_zip_code": "30303",
        "reason_for_selling": "Inherited property",
        "desired_timeline": "Within 30 days",
        "property_condition": "Needs updates",
        "occupancy_status": "Vacant",
        "notes": "Seller asked for a call tomorrow morning.",
        "disposition": "interested",
        "follow_up_permission": permission,
    }


def signed_post(
    client: TestClient,
    payload: dict[str, object],
    *,
    secret: str = SECRET,
    signature: str | None = None,
) -> Response:
    raw = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    digest = signature or hmac.new(secret.encode(), raw, hashlib.sha256).hexdigest()
    return cast(
        Response,
        client.post(
            ENDPOINT,
            content=raw,
            headers={
                "Content-Type": "application/json",
                "X-Stonegate-BatchDialer-Signature": f"sha256={digest}",
            },
        ),
    )


def test_batchdialer_configuration_requires_secret_and_campaign_allowlist() -> None:
    disabled = Settings.model_validate(
        {
            "ZAPIER_BATCHDIALER_ENABLED": False,
            "ZAPIER_BATCHDIALER_WEBHOOK_SECRET": "",
            "ZAPIER_BATCHDIALER_ALLOWED_CAMPAIGN_IDS": "",
        }
    )
    incomplete = Settings.model_validate(
        {
            "ZAPIER_BATCHDIALER_ENABLED": True,
            "ZAPIER_BATCHDIALER_WEBHOOK_SECRET": "short",
            "ZAPIER_BATCHDIALER_ALLOWED_CAMPAIGN_IDS": "",
        }
    )
    configured = Settings.model_validate(
        {
            "ZAPIER_BATCHDIALER_ENABLED": True,
            "ZAPIER_BATCHDIALER_WEBHOOK_SECRET": SECRET,
            "ZAPIER_BATCHDIALER_ALLOWED_CAMPAIGN_IDS": f" {CAMPAIGN_ID}, second-campaign ",
        }
    )

    assert disabled.zapier_batchdialer_configured is False
    assert "ZAPIER_BATCHDIALER_WEBHOOK_SECRET (at least 32 characters)" in (
        incomplete.zapier_batchdialer_configuration_blockers
    )
    assert "ZAPIER_BATCHDIALER_ALLOWED_CAMPAIGN_IDS" in (
        incomplete.zapier_batchdialer_configuration_blockers
    )
    assert configured.zapier_batchdialer_configured is True
    assert configured.zapier_batchdialer_allowed_campaign_ids == {
        CAMPAIGN_ID,
        "second-campaign",
    }


def test_batchdialer_webhook_is_disabled_by_default_and_requires_valid_hmac(
    db_session: Session,
    api_db_override: None,
    batchdialer_settings: Settings,
    monkeypatch: MonkeyPatch,
) -> None:
    seed_owner(db_session)
    client = TestClient(app)
    invalid_signature = signed_post(client, lead_payload(), signature="0" * 64)

    monkeypatch.setenv("ZAPIER_BATCHDIALER_ENABLED", "false")
    get_settings.cache_clear()
    disabled = signed_post(client, lead_payload())

    assert invalid_signature.status_code == 401
    assert disabled.status_code == 503
    assert (
        int(db_session.scalar(select(func.count()).select_from(ProspectingProviderEvent)) or 0) == 0
    )


def test_batchdialer_webhook_validates_payload_allowlist_size_and_replay(
    db_session: Session,
    api_db_override: None,
    batchdialer_settings: Settings,
) -> None:
    seed_owner(db_session)
    client = TestClient(app)
    invalid = lead_payload()
    invalid.pop("follow_up_permission")
    wrong_campaign = lead_payload(event_id="batch-event-wrong-campaign")
    wrong_campaign["campaign_id"] = "not-allowed"
    oversized = lead_payload(event_id="batch-event-oversized")
    oversized["notes"] = "x" * (batchdialer_settings.zapier_batchdialer_max_payload_bytes + 1)

    assert signed_post(client, invalid).status_code == 422
    assert signed_post(client, wrong_campaign).status_code == 400
    assert signed_post(client, oversized).status_code == 413
    accepted = signed_post(client, lead_payload())
    duplicate = signed_post(client, lead_payload())

    assert accepted.status_code == 202
    assert accepted.json() == {"received": True, "accepted": 1}
    assert duplicate.status_code == 202
    assert duplicate.json() == {"received": True, "accepted": 0}
    assert (
        int(db_session.scalar(select(func.count()).select_from(ProspectingProviderEvent)) or 0) == 1
    )


def test_batchdialer_lead_creates_full_intake_once_and_only_mapped_consent(
    db_session: Session,
    api_db_override: None,
    batchdialer_settings: Settings,
) -> None:
    seed_owner(db_session)
    assert signed_post(TestClient(app), lead_payload()).status_code == 202

    event_id = process_next_batchdialer_event(db_session, batchdialer_settings)
    event = db_session.get(ProspectingProviderEvent, event_id)

    assert event is not None
    assert event.processing_status == "processed"
    result = event.payload["_stonegate"]
    lead = db_session.get(Lead, UUID(result["lead_id"]))
    assert lead is not None
    assert lead.source == "batchdialer"
    assert lead.motivation == "Inherited property"
    assert lead.qualification_context["batchdialer"]["campaign_id"] == CAMPAIGN_ID
    assert lead.qualification_context["batchdialer"]["va_name"] == "Ava Caller"
    assert int(db_session.scalar(select(func.count()).select_from(LeadFormSubmission)) or 0) == 1
    assert int(db_session.scalar(select(func.count()).select_from(LeadManagementCase)) or 0) == 1
    assert int(db_session.scalar(select(func.count()).select_from(PropertyResearchRun)) or 0) == 1
    assert int(db_session.scalar(select(func.count()).select_from(AiOrchestratorEvent)) or 0) == 1
    alert = db_session.scalar(select(StaffLeadAlert))
    assert alert is not None
    assert alert.source_type == "batchdialer_warm_handoff"
    consents = db_session.scalars(select(ConsentRecord)).all()
    assert {record.channel for record in consents} == {"phone"}
    assert consents[0].source == "batchdialer"
    assert process_next_batchdialer_event(db_session, batchdialer_settings) is None


def test_batchdialer_sms_consent_is_created_only_when_explicitly_mapped(
    db_session: Session,
    api_db_override: None,
    batchdialer_settings: Settings,
) -> None:
    seed_owner(db_session)
    payload = lead_payload(
        event_id="batch-event-lead-sms",
        provider_contact_id="batch-contact-sms",
        permission="phone_and_sms",
    )
    assert signed_post(TestClient(app), payload).status_code == 202

    process_next_batchdialer_event(db_session, batchdialer_settings)
    consents = db_session.scalars(select(ConsentRecord).order_by(ConsentRecord.channel)).all()

    assert {record.channel for record in consents} == {"phone", "sms"}
    sms = next(record for record in consents if record.channel == "sms")
    assert sms.source == "batchdialer"
    assert sms.wording_version == "batchdialer-va-sms-follow-up-v1"


def test_distinct_lead_event_for_same_provider_contact_does_not_alert_twice(
    db_session: Session,
    api_db_override: None,
    batchdialer_settings: Settings,
) -> None:
    seed_owner(db_session)
    client = TestClient(app)
    assert signed_post(client, lead_payload()).status_code == 202
    process_next_batchdialer_event(db_session, batchdialer_settings)
    duplicate = lead_payload(event_id="batch-event-lead-provider-replay")
    assert signed_post(client, duplicate).status_code == 202

    duplicate_event_id = process_next_batchdialer_event(db_session, batchdialer_settings)
    duplicate_event = db_session.get(ProspectingProviderEvent, duplicate_event_id)

    assert duplicate_event is not None and duplicate_event.processing_status == "processed"
    assert duplicate_event.payload["_stonegate"]["duplicate_provider_handoff"] is True
    assert int(db_session.scalar(select(func.count()).select_from(Lead)) or 0) == 1
    assert int(db_session.scalar(select(func.count()).select_from(StaffLeadAlert)) or 0) == 1
    assert (
        int(
            db_session.scalar(
                select(func.count())
                .select_from(ActivityEvent)
                .where(ActivityEvent.event_type == "lead.batchdialer_warm_handoff_received")
            )
            or 0
        )
        == 1
    )


def test_batchdialer_calendar_creates_one_initial_appointment_and_stores_result(
    db_session: Session,
    api_db_override: None,
    batchdialer_settings: Settings,
) -> None:
    owner = seed_owner(db_session)
    client = TestClient(app)
    assert signed_post(client, lead_payload()).status_code == 202
    process_next_batchdialer_event(db_session, batchdialer_settings)
    calendar_payload = {
        "event_id": "batch-event-calendar-001",
        "event_type": "calendar.created",
        "occurred_at": "2026-08-17T14:35:00-04:00",
        "campaign_id": CAMPAIGN_ID,
        "campaign_name": "Atlanta absentee owners",
        "provider_contact_id": "batch-contact-001",
        "related_lead_event_id": "batch-event-lead-001",
        "provider_appointment_id": "batch-appointment-001",
        "appointment_start_at": "2026-08-19T10:00:00-04:00",
        "appointment_end_at": "2026-08-19T11:00:00-04:00",
        "appointment_location_type": "seller_property",
        "appointment_owner_email": owner.email,
    }
    assert signed_post(client, calendar_payload).status_code == 202

    calendar_event_id = process_next_batchdialer_event(db_session, batchdialer_settings)
    calendar_event = db_session.get(ProspectingProviderEvent, calendar_event_id)
    appointment = db_session.scalar(select(Appointment))

    assert calendar_event is not None and calendar_event.processing_status == "processed"
    assert appointment is not None
    assert calendar_event.payload["_stonegate"]["appointment_id"] == str(appointment.id)
    assert appointment.owner_user_id == owner.id
    assert appointment.appointment_metadata["provider_appointment_id"] == "batch-appointment-001"

    # Simulate a safe worker replay after the event result checkpoint was lost.
    raw = dict(calendar_event.payload)
    raw.pop("_stonegate")
    calendar_event.payload = raw
    calendar_event.processing_status = "pending"
    calendar_event.processed_at = None
    db_session.commit()
    process_next_batchdialer_event(db_session, batchdialer_settings)

    assert int(db_session.scalar(select(func.count()).select_from(Appointment)) or 0) == 1


def test_batchdialer_lead_revives_calendar_that_arrived_and_exhausted_first(
    db_session: Session,
    api_db_override: None,
    batchdialer_settings: Settings,
) -> None:
    owner = seed_owner(db_session)
    client = TestClient(app)
    calendar_payload = {
        "event_id": "batch-event-calendar-early",
        "event_type": "calendar.created",
        "occurred_at": "2026-08-17T14:20:00-04:00",
        "campaign_id": CAMPAIGN_ID,
        "provider_contact_id": "batch-contact-001",
        "related_lead_event_id": "batch-event-lead-001",
        "provider_appointment_id": "batch-appointment-early",
        "appointment_start_at": "2026-08-19T10:00:00-04:00",
        "appointment_owner_email": owner.email,
    }
    assert signed_post(client, calendar_payload).status_code == 202
    calendar_event_id = process_next_batchdialer_event(db_session, batchdialer_settings)
    calendar_event = db_session.get(ProspectingProviderEvent, calendar_event_id)
    assert calendar_event is not None
    assert "explicitly linked" in (calendar_event.error_message or "")
    calendar_event.processing_status = "exhausted"
    db_session.commit()

    assert signed_post(client, lead_payload()).status_code == 202
    lead_event_id = process_next_batchdialer_event(db_session, batchdialer_settings)
    lead_event = db_session.get(ProspectingProviderEvent, lead_event_id)
    db_session.refresh(calendar_event)

    assert lead_event is not None and lead_event.processing_status == "processed"
    assert lead_event.payload["_stonegate"]["revived_dependency_count"] == 1
    assert calendar_event.processing_status == "pending"
    assert calendar_event.retry_count == 0
    assert calendar_event.error_message is None

    process_next_batchdialer_event(db_session, batchdialer_settings)
    assert int(db_session.scalar(select(func.count()).select_from(Appointment)) or 0) == 1


def test_batchdialer_calendar_does_not_fallback_when_explicit_lead_link_is_wrong(
    db_session: Session,
    api_db_override: None,
    batchdialer_settings: Settings,
) -> None:
    seed_owner(db_session)
    client = TestClient(app)
    assert signed_post(client, lead_payload()).status_code == 202
    process_next_batchdialer_event(db_session, batchdialer_settings)
    calendar_payload = {
        "event_id": "batch-event-calendar-bad-link",
        "event_type": "calendar.created",
        "occurred_at": "2026-08-17T14:35:00-04:00",
        "campaign_id": CAMPAIGN_ID,
        "provider_contact_id": "batch-contact-001",
        "related_lead_event_id": "mistyped-lead-event-id",
        "provider_appointment_id": "batch-appointment-bad-link",
        "appointment_start_at": "2026-08-19T10:00:00-04:00",
    }
    assert signed_post(client, calendar_payload).status_code == 202

    event_id = process_next_batchdialer_event(db_session, batchdialer_settings)
    event = db_session.get(ProspectingProviderEvent, event_id)

    assert event is not None and event.processing_status == "retry"
    assert "explicitly linked" in (event.error_message or "")
    assert db_session.scalar(select(Appointment)) is None


def test_batchdialer_dnc_suppresses_phone_and_revokes_phone_and_sms_consent(
    db_session: Session,
    api_db_override: None,
    batchdialer_settings: Settings,
) -> None:
    seed_owner(db_session)
    client = TestClient(app)
    initial = lead_payload(permission="phone_and_sms")
    assert signed_post(client, initial).status_code == 202
    process_next_batchdialer_event(db_session, batchdialer_settings)
    dnc_payload = {
        "event_id": "batch-event-dnc-001",
        "event_type": "dnc.added",
        "occurred_at": "2026-08-17T15:00:00-04:00",
        "campaign_id": CAMPAIGN_ID,
        "provider_contact_id": "batch-contact-001",
        "related_lead_event_id": "batch-event-lead-001",
        "phone": "+14045550199",
        "dnc_reason": "Seller requested no more calls",
    }
    assert signed_post(client, dnc_payload).status_code == 202

    dnc_event_id = process_next_batchdialer_event(db_session, batchdialer_settings)
    dnc_event = db_session.get(ProspectingProviderEvent, dnc_event_id)
    suppression = db_session.scalar(select(SuppressionRecord))
    revoked = db_session.scalars(
        select(ConsentRecord).where(ConsentRecord.status == "revoked")
    ).all()

    assert dnc_event is not None and dnc_event.processing_status == "processed"
    assert suppression is not None
    assert suppression.channel == "phone"
    assert suppression.normalized_address == "+14045550199"
    assert suppression.status == "active"
    assert {record.channel for record in revoked} == {"phone", "sms"}
    assert dnc_event.payload["_stonegate"]["suppression_id"] == str(suppression.id)


def test_batchdialer_dnc_suppresses_valid_cold_number_without_a_crm_contact(
    db_session: Session,
    api_db_override: None,
    batchdialer_settings: Settings,
) -> None:
    seed_owner(db_session)
    payload = {
        "event_id": "batch-event-dnc-cold-001",
        "event_type": "dnc.added",
        "occurred_at": "2026-08-17T15:05:00-04:00",
        "campaign_id": CAMPAIGN_ID,
        "provider_contact_id": "batch-contact-cold-dnc",
        "phone": "+14045550888",
        "dnc_reason": "Cold prospect requested no further calls",
    }
    assert signed_post(TestClient(app), payload).status_code == 202

    event_id = process_next_batchdialer_event(db_session, batchdialer_settings)
    event = db_session.get(ProspectingProviderEvent, event_id)
    suppression = db_session.scalar(select(SuppressionRecord))

    assert event is not None and event.processing_status == "processed"
    assert suppression is not None
    assert suppression.contact_id is None
    assert suppression.normalized_address == "+14045550888"
    assert db_session.scalar(select(ConsentRecord)) is None


def test_batchdialer_dnc_requires_the_exact_phone_being_suppressed(
    db_session: Session,
    api_db_override: None,
    batchdialer_settings: Settings,
) -> None:
    seed_owner(db_session)
    payload = {
        "event_id": "batch-event-dnc-missing-phone",
        "event_type": "dnc.added",
        "occurred_at": "2026-08-17T15:05:00-04:00",
        "campaign_id": CAMPAIGN_ID,
        "provider_contact_id": "batch-contact-dnc-missing-phone",
    }

    response = signed_post(TestClient(app), payload)

    assert response.status_code == 422
    assert db_session.scalar(select(SuppressionRecord)) is None


def test_batchdialer_conflicting_phone_and_email_contacts_are_quarantined(
    db_session: Session,
    api_db_override: None,
    batchdialer_settings: Settings,
) -> None:
    seed_owner(db_session)
    client = TestClient(app)
    first = lead_payload()
    assert signed_post(client, first).status_code == 202
    process_next_batchdialer_event(db_session, batchdialer_settings)
    second = lead_payload(
        event_id="batch-event-lead-second",
        provider_contact_id="batch-contact-second",
    )
    second["email"] = "other@example.com"
    second["phone"] = "+14045550200"
    second["property_address"] = "202 Batch Lane"
    assert signed_post(client, second).status_code == 202
    process_next_batchdialer_event(db_session, batchdialer_settings)
    conflicting = lead_payload(
        event_id="batch-event-lead-conflict",
        provider_contact_id="batch-contact-conflict",
    )
    conflicting["phone"] = first["phone"]
    conflicting["email"] = second["email"]
    conflicting["property_address"] = "303 Batch Lane"
    assert signed_post(client, conflicting).status_code == 202
    process_next_batchdialer_event(db_session, batchdialer_settings)

    conflicting_event = db_session.scalar(
        select(ProspectingProviderEvent).where(
            ProspectingProviderEvent.external_event_id == "batch-event-lead-conflict"
        )
    )
    assert conflicting_event is not None
    assert conflicting_event.processing_status == "needs_review"
    assert "different CRM contacts" in (conflicting_event.error_message or "")
    assert int(db_session.scalar(select(func.count()).select_from(Lead)) or 0) == 2
    assert (
        int(
            db_session.scalar(
                select(func.count())
                .select_from(AttributionTouch)
                .where(AttributionTouch.source == "batchdialer")
            )
            or 0
        )
        >= 2
    )
