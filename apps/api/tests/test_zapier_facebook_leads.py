from collections.abc import Iterator
from typing import Any, cast

import pytest
from fastapi.testclient import TestClient
from httpx import Response
from pytest import MonkeyPatch
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.integrations.rentcast_client import RentCastClientError
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
    process_next_meta_address_enrichment,
    process_next_meta_lead_event,
    process_next_staff_lead_alert,
)
from app.services.request_rate_limit import FixedWindowRateLimiter

PAGE_ID = "123456789"
PROVIDER_LEAD_ID = "987654321012345"
ENDPOINT = "/api/v1/webhooks/zapier/facebook-leads"


@pytest.fixture
def zapier_settings(monkeypatch: MonkeyPatch) -> Iterator[Settings]:
    values = {
        "ZAPIER_FACEBOOK_LEADS_ENABLED": "true",
        "ZAPIER_FACEBOOK_PAGE_ID": PAGE_ID,
        "RENTCAST_API_KEY": "test-rentcast-key",
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
        "provider_lead_id": lead_id,
        "page_id": PAGE_ID,
        "form_id": "form-123",
        "form_name": "Get a cash offer",
        "created_time": "2026-08-04T17:30:00+0000",
        "ad_id": "ad-123",
        "ad_name": "Atlanta inherited homes",
        "adset_id": "adset-123",
        "adset_name": "Metro Atlanta homeowners",
        "campaign_id": "campaign-123",
        "campaign_name": "Atlanta seller leads",
        "platform": "fb",
        "is_organic": False,
        "full_name": "Jane Facebook",
        "email": "jane@example.com",
        "phone_number": "404-555-0199",
        "property_address": "101 Zapier Lane",
        "property_city": "Atlanta",
        "property_state": "GA",
        "property_zip_code": "30303",
        "selling_reason": "Inherited property",
        "desired_timeline": "30 days",
    }


def post_lead(client: TestClient, payload: dict[str, object]) -> Response:
    return cast(Response, client.post(ENDPOINT, json=payload))


class FakePropertyRecordClient:
    def __init__(
        self,
        record: dict[str, Any] | None = None,
        error: RentCastClientError | None = None,
    ) -> None:
        self.record = record or {}
        self.error = error
        self.addresses: list[str] = []

    def get_property_record(
        self,
        *,
        address: str,
        property_id: str | None = None,
    ) -> dict[str, Any]:
        self.addresses.append(address)
        if self.error is not None:
            raise self.error
        return self.record


def test_zapier_form_allowlist_is_required_only_for_enabled_production_intake() -> None:
    common = {
        "ZAPIER_FACEBOOK_LEADS_ENABLED": True,
        "ZAPIER_FACEBOOK_PAGE_ID": PAGE_ID,
        "ZAPIER_FACEBOOK_ALLOWED_FORM_IDS": "",
    }

    local = Settings.model_validate({"APP_ENV": "local", **common})
    production = Settings.model_validate({"APP_ENV": "production", **common})
    production_disabled = Settings.model_validate(
        {
            "APP_ENV": "production",
            **common,
            "ZAPIER_FACEBOOK_LEADS_ENABLED": False,
        }
    )
    production_allowed = Settings.model_validate(
        {
            "APP_ENV": "production",
            **common,
            "ZAPIER_FACEBOOK_ALLOWED_FORM_IDS": " form-123, form-456 ",
        }
    )

    assert local.zapier_facebook_leads_configured is True
    assert "ZAPIER_FACEBOOK_ALLOWED_FORM_IDS" not in (
        local.zapier_facebook_leads_configuration_blockers
    )
    assert production.zapier_facebook_leads_configured is False
    assert production.production_zapier_facebook_leads_configuration_blockers == (
        "ZAPIER_FACEBOOK_ALLOWED_FORM_IDS",
    )
    assert production_disabled.production_zapier_facebook_leads_configuration_blockers == ()
    assert production_allowed.zapier_facebook_leads_configured is True
    assert production_allowed.zapier_facebook_allowed_form_ids == {
        "form-123",
        "form-456",
    }


def provider_property_record(
    *,
    street_address: str = "101 Zapier Lane",
) -> dict[str, Any]:
    return {
        "id": "rentcast-property-101",
        "formattedAddress": f"{street_address}, Atlanta, GA 30303",
        "addressLine1": street_address,
        "city": "Atlanta",
        "state": "GA",
        "zipCode": "30303",
        "county": "Fulton",
        "countyFips": "121",
        "latitude": 33.75,
        "longitude": -84.39,
    }


def test_zapier_webhook_requires_enabled_mode(
    db_session: Session,
    api_db_override: None,
    monkeypatch: MonkeyPatch,
) -> None:
    seed_owner(db_session)
    monkeypatch.setenv("ZAPIER_FACEBOOK_LEADS_ENABLED", "false")
    get_settings.cache_clear()
    client = TestClient(app)
    disabled = client.post(ENDPOINT, json=webhook_payload())

    monkeypatch.setenv("ZAPIER_FACEBOOK_LEADS_ENABLED", "true")
    monkeypatch.setenv("ZAPIER_FACEBOOK_PAGE_ID", PAGE_ID)
    get_settings.cache_clear()
    accepted = client.post(ENDPOINT, json=webhook_payload())
    retired = client.post("/api/v1/webhooks/meta/lead-ads", json={})

    assert disabled.status_code == 503
    assert accepted.status_code == 200
    assert accepted.json() == {"received": True, "accepted": 1}
    assert retired.status_code == 404
    get_settings.cache_clear()


def test_zapier_webhook_rejects_wrong_page_invalid_and_oversized_payloads(
    db_session: Session,
    api_db_override: None,
    zapier_settings: Settings,
) -> None:
    seed_owner(db_session)
    client = TestClient(app)
    wrong_page = webhook_payload()
    wrong_page["page_id"] = "999999999"
    invalid = webhook_payload()
    invalid["nested_answer"] = {"not": "allowed"}
    oversized = webhook_payload()
    oversized["padding"] = "x" * (zapier_settings.zapier_facebook_leads_max_payload_bytes + 1)

    wrong_page_response = post_lead(client, wrong_page)
    invalid_response = post_lead(client, invalid)
    oversized_response = post_lead(client, oversized)

    assert wrong_page_response.status_code == 400
    assert invalid_response.status_code == 422
    assert oversized_response.status_code == 413
    assert int(db_session.scalar(select(func.count()).select_from(MetaLeadEvent)) or 0) == 0


def test_zapier_webhook_enforces_optional_form_allowlist(
    db_session: Session,
    api_db_override: None,
    monkeypatch: MonkeyPatch,
) -> None:
    seed_owner(db_session)
    monkeypatch.setenv("ZAPIER_FACEBOOK_LEADS_ENABLED", "true")
    monkeypatch.setenv("ZAPIER_FACEBOOK_PAGE_ID", PAGE_ID)
    monkeypatch.setenv("ZAPIER_FACEBOOK_ALLOWED_FORM_IDS", "allowed-form")
    get_settings.cache_clear()
    client = TestClient(app)

    rejected = post_lead(client, webhook_payload())
    allowed_payload = webhook_payload("987654321012346")
    allowed_payload["form_id"] = "allowed-form"
    accepted = post_lead(client, allowed_payload)

    assert rejected.status_code == 400
    assert accepted.status_code == 200
    assert accepted.json()["accepted"] == 1
    assert int(db_session.scalar(select(func.count()).select_from(MetaLeadEvent)) or 0) == 1
    get_settings.cache_clear()


def test_zapier_webhook_has_burst_and_daily_cost_circuits(
    db_session: Session,
    api_db_override: None,
    monkeypatch: MonkeyPatch,
) -> None:
    seed_owner(db_session)
    monkeypatch.setenv("ZAPIER_FACEBOOK_LEADS_ENABLED", "true")
    monkeypatch.setenv("ZAPIER_FACEBOOK_PAGE_ID", PAGE_ID)
    monkeypatch.setenv("ZAPIER_FACEBOOK_LEADS_BURST_LIMIT", "1")
    monkeypatch.setenv("ZAPIER_FACEBOOK_LEADS_DAILY_ACCEPT_LIMIT", "1")
    get_settings.cache_clear()
    monkeypatch.setattr(
        "app.routers.zapier_webhooks.zapier_lead_rate_limiter",
        FixedWindowRateLimiter(),
    )
    client = TestClient(app)

    wrong_page = webhook_payload("987654321012340")
    wrong_page["page_id"] = "999999999"
    rejected_without_consuming_burst = post_lead(client, wrong_page)
    first = post_lead(client, webhook_payload())
    burst_limited = post_lead(client, webhook_payload("987654321012346"))

    assert rejected_without_consuming_burst.status_code == 400
    assert first.status_code == 200
    assert burst_limited.status_code == 429
    assert burst_limited.headers["retry-after"]

    monkeypatch.setattr(
        "app.routers.zapier_webhooks.zapier_lead_rate_limiter",
        FixedWindowRateLimiter(),
    )
    daily_limited = post_lead(client, webhook_payload("987654321012347"))
    monkeypatch.setattr(
        "app.routers.zapier_webhooks.zapier_lead_rate_limiter",
        FixedWindowRateLimiter(),
    )
    duplicate = post_lead(client, webhook_payload())

    assert daily_limited.status_code == 429
    assert daily_limited.headers["retry-after"] == "3600"
    assert duplicate.status_code == 200
    assert duplicate.json()["accepted"] == 0
    assert int(db_session.scalar(select(func.count()).select_from(MetaLeadEvent)) or 0) == 1
    get_settings.cache_clear()


def test_zapier_lead_creates_crm_lead_once_and_queues_staff_alert(
    db_session: Session,
    api_db_override: None,
    zapier_settings: Settings,
) -> None:
    seed_owner(db_session)
    client = TestClient(app)

    response = post_lead(client, webhook_payload())
    duplicate = post_lead(client, webhook_payload())
    processed_id = process_next_meta_lead_event(db_session, zapier_settings)

    assert response.status_code == 200
    assert response.json() == {"received": True, "accepted": 1}
    assert duplicate.json() == {"received": True, "accepted": 0}
    event = db_session.get(MetaLeadEvent, processed_id)
    assert event is not None
    assert event.ingestion_method == "zapier"
    assert event.status == "processed"
    assert event.lead_id is not None
    assert event.webhook_payload["selling_reason"] == "Inherited property"
    lead = db_session.get(Lead, event.lead_id)
    assert lead is not None
    assert lead.source == "facebook_lead_ads"
    assert lead.motivation == "Inherited property"
    contact = db_session.get(Contact, lead.contact_id)
    property_record = db_session.get(Property, lead.property_id)
    assert contact is not None and contact.legal_name == "Jane Facebook"
    assert property_record is not None and property_record.street_address == "101 Zapier Lane"
    consents = db_session.scalars(select(ConsentRecord)).all()
    assert {item.channel for item in consents} == {"email", "phone"}
    assert all(item.source == "facebook_lead_ads" for item in consents)
    assert all(item.channel != "sms" for item in consents)
    assert int(db_session.scalar(select(func.count()).select_from(Notification)) or 0) >= 1
    alert = db_session.scalar(select(StaffLeadAlert))
    assert alert is not None
    assert alert.status == "pending"
    assert "404-555-0199" not in alert.message_body
    assert "101 Zapier Lane" not in alert.message_body

    alert_id = process_next_staff_lead_alert(db_session, zapier_settings)
    assert alert_id == alert.id
    db_session.refresh(alert)
    assert alert.status == "simulated"
    assert alert.provider_message_id is not None

    callback_status = process_twilio_status(
        db_session,
        {"MessageSid": alert.provider_message_id, "MessageStatus": "delivered"},
    )
    assert callback_status == "processed"
    db_session.refresh(alert)
    assert alert.status == "delivered"
    assert alert.delivered_at is not None

    process_twilio_status(
        db_session,
        {"MessageSid": alert.provider_message_id, "MessageStatus": "sent"},
    )
    db_session.refresh(alert)
    assert alert.status == "delivered"


def test_zapier_land_lead_preserves_asset_and_parcel_identity(
    db_session: Session,
    api_db_override: None,
    zapier_settings: Settings,
) -> None:
    seed_owner(db_session)
    payload = webhook_payload("987654321012399")
    payload.update(
        {
            "property_address": "Lot 12 Talking Rock Road",
            "property_city": "Talking Rock",
            "property_zip_code": "30175",
            "property_type": "vacant_land",
            "asset_class": "Land",
            "parcel_id": "1234-012-099",
        }
    )

    response = post_lead(TestClient(app), payload)
    event_id = process_next_meta_lead_event(db_session, zapier_settings)

    assert response.status_code == 200, response.text
    event = db_session.get(MetaLeadEvent, event_id)
    assert event is not None and event.lead_id is not None
    lead = db_session.get(Lead, event.lead_id)
    assert lead is not None and lead.asset_class == "land"
    property_record = db_session.get(Property, lead.property_id)
    assert property_record is not None
    assert property_record.property_type == "vacant_land"
    assert property_record.parcel_id == "1234-012-099"
    alert = db_session.scalar(select(StaffLeadAlert))
    assert alert is not None
    assert alert.message_body.startswith("New Facebook Land lead:")


def test_facebook_address_enrichment_fills_zip_and_county_after_staff_alert(
    db_session: Session,
    api_db_override: None,
    zapier_settings: Settings,
) -> None:
    seed_owner(db_session)
    payload = webhook_payload("987654321012346")
    payload.pop("property_zip_code")
    client = TestClient(app)
    assert post_lead(client, payload).status_code == 200
    assert post_lead(client, payload).json() == {"received": True, "accepted": 0}

    event_id = process_next_meta_lead_event(db_session, zapier_settings)
    event = db_session.get(MetaLeadEvent, event_id)
    assert event is not None and event.lead_id is not None
    alert = db_session.scalar(select(StaffLeadAlert))
    assert alert is not None
    assert process_next_staff_lead_alert(db_session, zapier_settings) == alert.id

    provider = FakePropertyRecordClient(provider_property_record())
    assert process_next_meta_address_enrichment(db_session, zapier_settings, provider) == event.id

    db_session.refresh(event)
    lead = db_session.get(Lead, event.lead_id)
    assert lead is not None
    property_record = db_session.get(Property, lead.property_id)
    assert property_record is not None
    assert event.address_enrichment_status == "enriched"
    assert event.address_enrichment_attempt_count == 1
    assert event.address_enriched_at is not None
    assert event.address_enrichment_last_error is None
    assert property_record.postal_code == "30303"
    assert property_record.county == "Fulton"
    assert property_record.address_validation_status == "provider_confirmed"
    assert property_record.normalized_address_key == "101 zapier ln|atlanta|GA|30303"
    assert provider.addresses == ["101 Zapier Lane, Atlanta, GA"]
    assert process_next_meta_address_enrichment(db_session, zapier_settings, provider) is None
    assert len(provider.addresses) == 1


def test_facebook_address_enrichment_routes_ambiguous_and_missing_addresses_to_review(
    db_session: Session,
    api_db_override: None,
    zapier_settings: Settings,
) -> None:
    seed_owner(db_session, enable_sms_alerts=False)
    ambiguous = webhook_payload("987654321012347")
    ambiguous.pop("property_zip_code")
    missing = webhook_payload("987654321012348")
    missing.pop("property_address")
    missing.pop("property_city")
    client = TestClient(app)
    post_lead(client, ambiguous)
    post_lead(client, missing)

    first_id = process_next_meta_lead_event(db_session, zapier_settings)
    second_id = process_next_meta_lead_event(db_session, zapier_settings)
    provider = FakePropertyRecordClient(
        provider_property_record(street_address="999 Different Road")
    )
    assert process_next_meta_address_enrichment(db_session, zapier_settings, provider) == first_id
    assert process_next_meta_address_enrichment(db_session, zapier_settings, provider) == second_id

    first = db_session.get(MetaLeadEvent, first_id)
    second = db_session.get(MetaLeadEvent, second_id)
    assert first is not None and first.lead_id is not None
    assert second is not None
    ambiguous_lead = db_session.get(Lead, first.lead_id)
    assert ambiguous_lead is not None
    ambiguous_property = db_session.get(Property, ambiguous_lead.property_id)
    assert ambiguous_property is not None
    assert first.address_enrichment_status == "needs_review"
    assert ambiguous_property.postal_code == "Unknown"
    assert ambiguous_property.county is None
    assert ambiguous_property.address_validation_status == "needs_review"
    assert second.address_enrichment_status == "skipped"
    assert "did not provide" in (second.address_enrichment_last_error or "")
    assert len(provider.addresses) == 1


def test_facebook_address_enrichment_retries_provider_outage_without_losing_lead(
    db_session: Session,
    api_db_override: None,
    zapier_settings: Settings,
) -> None:
    seed_owner(db_session, enable_sms_alerts=False)
    payload = webhook_payload("987654321012349")
    payload.pop("property_zip_code")
    post_lead(TestClient(app), payload)
    event_id = process_next_meta_lead_event(db_session, zapier_settings)
    provider = FakePropertyRecordClient(
        error=RentCastClientError(
            "temporary RentCast outage",
            operation="property record",
            status_code=503,
        )
    )

    assert process_next_meta_address_enrichment(db_session, zapier_settings, provider) == event_id

    event = db_session.get(MetaLeadEvent, event_id)
    assert event is not None and event.lead_id is not None
    assert event.address_enrichment_status == "retry"
    assert event.address_enrichment_attempt_count == 1
    assert event.address_enrichment_next_attempt_at is not None
    assert event.address_enrichment_last_attempt_at is not None
    assert event.address_enrichment_next_attempt_at > event.address_enrichment_last_attempt_at
    assert event.address_enrichment_last_error == "temporary RentCast outage"
    assert db_session.get(Lead, event.lead_id) is not None


def test_zapier_lead_without_contact_information_requires_review(
    db_session: Session,
    api_db_override: None,
    zapier_settings: Settings,
) -> None:
    seed_owner(db_session)
    payload = webhook_payload()
    payload.pop("email")
    payload.pop("phone_number")
    response = post_lead(TestClient(app), payload)
    assert response.status_code == 200

    event_id = process_next_meta_lead_event(db_session, zapier_settings)

    event = db_session.get(MetaLeadEvent, event_id)
    assert event is not None
    assert event.status == "needs_review"
    assert event.lead_payload is not None
    assert "neither an email address nor phone number" in (event.last_error or "")
    assert int(db_session.scalar(select(func.count()).select_from(Lead)) or 0) == 0


def test_zapier_intake_failure_retries_without_losing_event(
    db_session: Session,
    api_db_override: None,
    zapier_settings: Settings,
    monkeypatch: MonkeyPatch,
) -> None:
    seed_owner(db_session)
    response = post_lead(TestClient(app), webhook_payload())
    assert response.status_code == 200

    def fail_intake(*_args: object, **_kwargs: object) -> object:
        raise RuntimeError("temporary CRM failure")

    monkeypatch.setattr("app.services.meta_lead_ads.create_public_seller_lead", fail_intake)
    event_id = process_next_meta_lead_event(db_session, zapier_settings)

    event = db_session.get(MetaLeadEvent, event_id)
    assert event is not None
    assert event.status == "retry"
    assert event.attempt_count == 1
    assert event.next_attempt_at is not None
    assert event.last_attempt_at is not None
    assert event.next_attempt_at > event.last_attempt_at
    assert event.last_error == "temporary CRM failure"
