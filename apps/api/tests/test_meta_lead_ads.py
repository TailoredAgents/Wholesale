import hashlib
import hmac
import json
from collections.abc import Iterator

import httpx
import pytest
from fastapi.testclient import TestClient
from pytest import MonkeyPatch
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.integrations.meta_lead_ads import MetaLeadAdsClient, verify_meta_signature
from app.main import app
from app.models.foundation import (
    ConsentRecord,
    Contact,
    Lead,
    MetaLeadEvent,
    Notification,
    Property,
    StaffLeadAlert,
    User,
)
from app.services.bootstrap import bootstrap_foundation
from app.services.messaging import process_twilio_status
from app.services.meta_lead_ads import (
    process_next_meta_lead_event,
    process_next_staff_lead_alert,
)

APP_SECRET = "meta-app-secret-test"
VERIFY_TOKEN = "meta-verify-token-test"
PAGE_ID = "123456789"
PROVIDER_LEAD_ID = "987654321012345"


class FakeMetaLeadClient:
    def __init__(self, payload: dict[str, object]) -> None:
        self.payload = payload
        self.requested_ids: list[str] = []

    def fetch_lead(self, provider_lead_id: str) -> dict[str, object]:
        self.requested_ids.append(provider_lead_id)
        return self.payload


@pytest.fixture
def meta_settings(monkeypatch: MonkeyPatch) -> Iterator[Settings]:
    values = {
        "META_LEAD_ADS_ENABLED": "true",
        "META_LEAD_ADS_APP_SECRET": APP_SECRET,
        "META_LEAD_ADS_VERIFY_TOKEN": VERIFY_TOKEN,
        "META_LEAD_ADS_PAGE_ID": PAGE_ID,
        "META_LEAD_ADS_ACCESS_TOKEN": "meta-page-token-test",
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


def seed_owner(db_session: Session, *, enable_sms_alerts: bool = True) -> User:
    result = bootstrap_foundation(
        db_session,
        organization_name="Stonegate Home Buyers",
        admin_email="owner@example.com",
        admin_name="Owner",
    )
    assert result.admin_user is not None
    result.admin_user.voice_forwarding_number = "+14045550123"
    result.admin_user.lead_alert_sms_enabled = enable_sms_alerts
    db_session.commit()
    return result.admin_user


def webhook_payload(lead_id: str = PROVIDER_LEAD_ID) -> dict[str, object]:
    return {
        "object": "page",
        "entry": [
            {
                "id": PAGE_ID,
                "time": 1785875287,
                "changes": [
                    {
                        "field": "leadgen",
                        "value": {
                            "ad_id": "ad-123",
                            "form_id": "form-123",
                            "leadgen_id": lead_id,
                            "created_time": 1785875287,
                            "page_id": PAGE_ID,
                        },
                    }
                ],
            }
        ],
    }


def lead_payload(lead_id: str = PROVIDER_LEAD_ID) -> dict[str, object]:
    return {
        "id": lead_id,
        "created_time": "2026-08-04T17:30:00+0000",
        "ad_id": "ad-123",
        "ad_name": "Atlanta inherited homes",
        "campaign_id": "campaign-123",
        "campaign_name": "Atlanta seller leads",
        "form_id": "form-123",
        "platform": "fb",
        "is_organic": False,
        "field_data": [
            {"name": "full_name", "values": ["Jane Facebook"]},
            {"name": "email", "values": ["jane@example.com"]},
            {"name": "phone_number", "values": ["404-555-0199"]},
            {"name": "property_address", "values": ["101 Meta Lane"]},
            {"name": "property_city", "values": ["Atlanta"]},
            {"name": "property_state", "values": ["GA"]},
            {"name": "property_zip_code", "values": ["30303"]},
            {"name": "reason_for_selling", "values": ["Inherited property"]},
            {"name": "desired_timeline", "values": ["30 days"]},
        ],
    }


def signed_body(payload: dict[str, object]) -> tuple[bytes, str]:
    raw_body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    digest = hmac.new(APP_SECRET.encode("utf-8"), raw_body, hashlib.sha256).hexdigest()
    return raw_body, f"sha256={digest}"


def test_meta_webhook_verification_and_signature_rejection(
    db_session: Session,
    api_db_override: None,
    meta_settings: Settings,
) -> None:
    seed_owner(db_session)
    client = TestClient(app)

    verified = client.get(
        "/api/v1/webhooks/meta/lead-ads",
        params={
            "hub.mode": "subscribe",
            "hub.verify_token": VERIFY_TOKEN,
            "hub.challenge": "challenge-123",
        },
    )
    rejected = client.post(
        "/api/v1/webhooks/meta/lead-ads",
        json=webhook_payload(),
        headers={"X-Hub-Signature-256": "sha256=invalid"},
    )

    assert verified.status_code == 200
    assert verified.text == "challenge-123"
    assert rejected.status_code == 401
    assert verify_meta_signature(b"payload", None, APP_SECRET) is False


def test_meta_lead_webhook_creates_crm_lead_and_staff_alert(
    db_session: Session,
    api_db_override: None,
    meta_settings: Settings,
) -> None:
    seed_owner(db_session)
    client = TestClient(app)
    raw_body, signature = signed_body(webhook_payload())

    response = client.post(
        "/api/v1/webhooks/meta/lead-ads",
        content=raw_body,
        headers={
            "Content-Type": "application/json",
            "X-Hub-Signature-256": signature,
        },
    )
    duplicate = client.post(
        "/api/v1/webhooks/meta/lead-ads",
        content=raw_body,
        headers={
            "Content-Type": "application/json",
            "X-Hub-Signature-256": signature,
        },
    )
    fake_client = FakeMetaLeadClient(lead_payload())
    processed_id = process_next_meta_lead_event(db_session, meta_settings, fake_client)  # type: ignore[arg-type]

    assert response.status_code == 200
    assert response.json() == {"received": True, "accepted": 1}
    assert duplicate.json() == {"received": True, "accepted": 0}
    assert fake_client.requested_ids == [PROVIDER_LEAD_ID]
    event = db_session.get(MetaLeadEvent, processed_id)
    assert event is not None
    assert event.status == "processed"
    assert event.lead_id is not None
    lead = db_session.get(Lead, event.lead_id)
    assert lead is not None
    assert lead.source == "facebook_lead_ads"
    assert lead.motivation == "Inherited property"
    contact = db_session.get(Contact, lead.contact_id)
    property_record = db_session.get(Property, lead.property_id)
    assert contact is not None and contact.legal_name == "Jane Facebook"
    assert property_record is not None and property_record.street_address == "101 Meta Lane"
    consents = db_session.scalars(select(ConsentRecord)).all()
    assert {item.channel for item in consents} == {"email", "phone"}
    assert all(item.source == "facebook_lead_ads" for item in consents)
    assert all(item.channel != "sms" for item in consents)
    assert int(db_session.scalar(select(func.count()).select_from(Notification)) or 0) >= 1
    alert = db_session.scalar(select(StaffLeadAlert))
    assert alert is not None
    assert alert.status == "pending"
    assert "404-555-0199" not in alert.message_body
    assert "101 Meta Lane" not in alert.message_body

    alert_id = process_next_staff_lead_alert(db_session, meta_settings)
    assert alert_id == alert.id
    db_session.refresh(alert)
    assert alert.status == "simulated"
    assert alert.provider_message_id is not None

    callback_status = process_twilio_status(
        db_session,
        {
            "MessageSid": alert.provider_message_id,
            "MessageStatus": "delivered",
        },
    )
    assert callback_status == "processed"
    db_session.refresh(alert)
    assert alert.status == "delivered"
    assert alert.delivered_at is not None
    process_twilio_status(
        db_session,
        {
            "MessageSid": alert.provider_message_id,
            "MessageStatus": "sent",
        },
    )
    db_session.refresh(alert)
    assert alert.status == "delivered"


def test_meta_lead_without_contact_information_requires_review(
    db_session: Session,
    api_db_override: None,
    meta_settings: Settings,
) -> None:
    seed_owner(db_session)
    raw_body, signature = signed_body(webhook_payload())
    response = TestClient(app).post(
        "/api/v1/webhooks/meta/lead-ads",
        content=raw_body,
        headers={
            "Content-Type": "application/json",
            "X-Hub-Signature-256": signature,
        },
    )
    assert response.status_code == 200
    payload = lead_payload()
    payload["field_data"] = [{"name": "full_name", "values": ["No Contact"]}]

    event_id = process_next_meta_lead_event(
        db_session,
        meta_settings,
        FakeMetaLeadClient(payload),  # type: ignore[arg-type]
    )

    event = db_session.get(MetaLeadEvent, event_id)
    assert event is not None
    assert event.status == "needs_review"
    assert event.lead_payload is not None
    assert "neither an email address nor phone number" in (event.last_error or "")
    assert int(db_session.scalar(select(func.count()).select_from(Lead)) or 0) == 0


def test_meta_graph_client_uses_server_token_without_returning_it() -> None:
    observed_request: httpx.Request | None = None

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal observed_request
        observed_request = request
        return httpx.Response(200, json={"id": PROVIDER_LEAD_ID, "field_data": []})

    settings = Settings.model_validate(
        {
            "META_LEAD_ADS_ENABLED": True,
            "META_LEAD_ADS_ACCESS_TOKEN": "secret-page-token",
        }
    )
    client = MetaLeadAdsClient(settings, httpx.Client(transport=httpx.MockTransport(handler)))

    payload = client.fetch_lead(PROVIDER_LEAD_ID)

    assert payload["id"] == PROVIDER_LEAD_ID
    assert observed_request is not None
    assert observed_request.url.params["access_token"] == "secret-page-token"
    assert "secret-page-token" not in str(payload)
