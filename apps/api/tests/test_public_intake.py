import asyncio
import hashlib
import uuid

import pytest
from fastapi.testclient import TestClient
from pytest import MonkeyPatch
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from starlette.requests import Request
from starlette.types import Message, Scope

from app.core.config import Settings, get_settings
from app.integrations.communications import OutboundMessageRequest, OutboundMessageResult
from app.integrations.marketing_conversions import build_meta_payload
from app.integrations.twilio_messaging import TwilioMessagingError
from app.main import app
from app.models.foundation import (
    ActivityEvent,
    AiOrchestratorEvent,
    AttributionTouch,
    AuditEvent,
    ConsentRecord,
    Contact,
    ContactMethod,
    Conversation,
    ConversionEvent,
    Lead,
    LeadFormSubmission,
    LeadManagementCase,
    OfflineConversionExport,
    Property,
    PropertyResearchRun,
    StaffLeadAlert,
    Task,
    User,
)
from app.routers import public as public_router
from app.services.bootstrap import bootstrap_foundation
from app.services.meta_lead_ads import process_next_staff_lead_alert
from app.services.request_rate_limit import (
    FixedWindowRateLimiter,
    RequestBodyTooLargeError,
    read_bounded_request_body,
    trusted_client_address,
)


class FailingStaffAlertProvider:
    provider_name = "twilio"

    def send(
        self,
        request: OutboundMessageRequest,
        *,
        dry_run: bool = True,
    ) -> OutboundMessageResult:
        del request, dry_run
        raise TwilioMessagingError("Temporary Stage 1 delivery failure.")


def public_payload() -> dict[str, object]:
    return {
        "property_address": "55 Auburn Ave",
        "property_city": "Atlanta",
        "property_state": "GA",
        "property_postal_code": "30303",
        "property_type": "single_family",
        "name": "Sam Seller",
        "phone": "4045551212",
        "email": "sam@example.com",
        "preferred_contact_method": "phone",
        "reason_for_selling": "Inherited property",
        "desired_timeline": "30 days",
        "property_condition": "major_repairs",
        "occupancy_status": "vacant",
        "asking_price": "180000",
        "mortgage_balance": "90000",
        "comments": "Needs repairs",
        "consent_to_contact": True,
        "sms_consent": False,
        "conversion_session_id": "session-intake-123",
        "attribution": {
            "landing_page": "/get-a-cash-offer",
            "referrer": "https://www.google.com/",
            "utm_source": "google_ppc",
            "utm_medium": "cpc",
            "utm_campaign": "atlanta-seller-leads",
            "utm_term": "sell my house fast",
            "gclid": "test-gclid",
        },
    }


def seed_org(db_session: Session) -> None:
    bootstrap_foundation(
        db_session,
        organization_name="Stonegate Home Buyers",
        admin_email="owner@example.com",
        admin_name="Owner",
    )


def enable_owner_lead_alerts(db_session: Session) -> User:
    owner = db_session.scalar(select(User).where(User.email == "owner@example.com"))
    assert owner is not None
    owner.voice_forwarding_number = "+14045550123"
    owner.lead_alert_sms_enabled = True
    db_session.commit()
    return owner


def address_capture_payload(*, attempt_id: str | None = None) -> dict[str, object]:
    resolved_attempt_id = attempt_id or str(uuid.uuid4())
    return {
        "intake_attempt_id": resolved_attempt_id,
        "property_address": "55 Auburn Ave",
        "property_city": "Atlanta",
        "property_state": "ga",
        "property_postal_code": "30303",
        "conversion_session_id": "session-intake-123",
        "device_category": "mobile",
        "attribution": {
            "landing_page": "/get-a-cash-offer",
            "utm_source": "facebook_ads",
            "utm_medium": "paid_social",
            "utm_campaign": "georgia-seller-options",
            "fbclid": "test-fbclid",
        },
        "meta_browser_event": {
            "event_id": f"stonegate-lead-{resolved_attempt_id}",
            "event_source_url": "https://www.stonegatehb.com/get-a-cash-offer",
            "fbc": "fb.1.1785875287.test-fbclid",
            "fbp": "fb.1.1785875287.123456789",
        },
    }


def completed_website_payload(attempt_id: str) -> dict[str, object]:
    payload = public_payload()
    payload.pop("desired_timeline")
    payload["intake_attempt_id"] = attempt_id
    payload["meta_browser_event"] = {
        "event_id": f"stonegate-contact-{attempt_id}",
        "event_source_url": "https://www.stonegatehb.com/get-a-cash-offer",
        "fbc": "fb.1.1785875287.test-fbclid",
        "fbp": "fb.1.1785875287.123456789",
    }
    return payload


def test_address_capture_creates_cold_crm_lead_without_contact_automation(
    db_session: Session,
    api_db_override: None,
) -> None:
    seed_org(db_session)

    response = TestClient(app).post(
        "/api/v1/public/seller-leads/address-capture",
        json=address_capture_payload(),
        headers={"User-Agent": "pytest"},
    )

    assert response.status_code == 201, response.text
    assert response.json()["created"] is True
    assert response.json()["completion_status"] == "address_only"
    lead = db_session.scalar(select(Lead))
    contact = db_session.scalar(select(Contact))
    property_record = db_session.scalar(select(Property))
    submission = db_session.scalar(select(LeadFormSubmission))
    assert lead is not None
    assert contact is not None
    assert property_record is not None
    assert submission is not None
    assert str(lead.id) == response.json()["lead_id"]
    assert contact.legal_name == "Contact pending (website form)"
    assert lead.source == "facebook_ads"
    assert lead.stage_key == "new"
    assert lead.lead_temperature == "cold"
    assert lead.desired_timeline is None
    assert lead.qualification_context == {
        "website_intake_status": "address_only",
        "contact_details_status": "missing",
        "prospecting_status": "skip_trace_needed",
    }
    assert property_record.state == "GA"
    assert submission.completion_status == "address_only"
    assert submission.completed_at is None
    assert submission.enrichment_token_hash is None
    assert submission.raw_payload["_intake_status"] == "address_only"
    assert int(db_session.scalar(select(func.count()).select_from(ContactMethod)) or 0) == 0
    assert int(db_session.scalar(select(func.count()).select_from(ConsentRecord)) or 0) == 0
    assert int(db_session.scalar(select(func.count()).select_from(Conversation)) or 0) == 0
    assert int(db_session.scalar(select(func.count()).select_from(LeadManagementCase)) or 0) == 0
    assert int(db_session.scalar(select(func.count()).select_from(Task)) or 0) == 0
    assert int(db_session.scalar(select(func.count()).select_from(StaffLeadAlert)) or 0) == 0
    assert int(db_session.scalar(select(func.count()).select_from(PropertyResearchRun)) or 0) == 0
    assert int(db_session.scalar(select(func.count()).select_from(AiOrchestratorEvent)) or 0) == 0
    export = db_session.scalar(select(OfflineConversionExport))
    assert export is not None
    assert export.event_name == "Lead"
    assert export.event_key == f"stonegate-lead-{submission.intake_attempt_id}"
    assert export.payload_snapshot["email_hashes"] == []
    assert export.payload_snapshot["phone_hashes"] == []
    event = db_session.scalar(select(ConversionEvent))
    assert event is not None and event.event_type == "address_capture"
    assert int(db_session.scalar(select(func.count()).select_from(AttributionTouch)) or 0) == 2


def test_address_capture_is_idempotent_and_does_not_merge_separate_attempts(
    db_session: Session,
    api_db_override: None,
) -> None:
    seed_org(db_session)
    client = TestClient(app)
    attempt_id = str(uuid.uuid4())
    first = client.post(
        "/api/v1/public/seller-leads/address-capture",
        json=address_capture_payload(attempt_id=attempt_id),
    )
    retry = client.post(
        "/api/v1/public/seller-leads/address-capture",
        json=address_capture_payload(attempt_id=attempt_id),
    )
    separate = client.post(
        "/api/v1/public/seller-leads/address-capture",
        json=address_capture_payload(),
    )

    assert first.status_code == retry.status_code == separate.status_code == 201
    assert retry.json()["created"] is False
    assert retry.json()["lead_id"] == first.json()["lead_id"]
    assert separate.json()["lead_id"] != first.json()["lead_id"]
    assert int(db_session.scalar(select(func.count()).select_from(Lead)) or 0) == 2
    assert int(db_session.scalar(select(func.count()).select_from(Contact)) or 0) == 2
    assert int(db_session.scalar(select(func.count()).select_from(Property)) or 0) == 1
    assert int(db_session.scalar(select(func.count()).select_from(LeadFormSubmission)) or 0) == 2
    assert int(db_session.scalar(select(func.count()).select_from(ConversionEvent)) or 0) == 2
    assert (
        int(db_session.scalar(select(func.count()).select_from(OfflineConversionExport)) or 0) == 2
    )
    assert int(db_session.scalar(select(func.count()).select_from(AttributionTouch)) or 0) == 4
    first_lead = db_session.get(Lead, uuid.UUID(first.json()["lead_id"]))
    assert first_lead is not None and first_lead.desired_timeline is None


def test_website_funnel_queues_one_labeled_sms_per_stage_and_recipient(
    db_session: Session,
    api_db_override: None,
) -> None:
    seed_org(db_session)
    enable_owner_lead_alerts(db_session)
    client = TestClient(app)
    attempt_id = str(uuid.uuid4())
    address_payload = address_capture_payload(attempt_id=attempt_id)

    capture = client.post(
        "/api/v1/public/seller-leads/address-capture",
        json=address_payload,
    )

    assert capture.status_code == 201, capture.text
    submission = db_session.scalar(select(LeadFormSubmission))
    assert submission is not None
    stage_1 = db_session.scalar(
        select(StaffLeadAlert).where(
            StaffLeadAlert.source_type == "website_form_stage_1"
        )
    )
    assert stage_1 is not None
    assert stage_1.source_event_id == submission.id
    assert stage_1.message_body.startswith(
        "Stonegate Stage 1 filled: 55 Auburn Ave, Atlanta, GA 30303."
    )
    assert "Address only; no contact details or permission yet." in stage_1.message_body
    assert "?view=address_only" in stage_1.message_body
    assert "Sam Seller" not in stage_1.message_body
    assert "4045551212" not in stage_1.message_body

    capture_retry = client.post(
        "/api/v1/public/seller-leads/address-capture",
        json=address_payload,
    )
    assert capture_retry.status_code == 201, capture_retry.text
    assert int(db_session.scalar(select(func.count()).select_from(StaffLeadAlert)) or 0) == 1

    completed = client.post(
        "/api/v1/public/seller-leads",
        json=completed_website_payload(attempt_id),
    )

    assert completed.status_code == 201, completed.text
    alerts = db_session.scalars(select(StaffLeadAlert).order_by(StaffLeadAlert.source_type)).all()
    assert len(alerts) == 2
    assert {alert.source_event_id for alert in alerts} == {submission.id}
    assert {alert.source_type for alert in alerts} == {
        "website_form_stage_1",
        "website_form",
    }
    stage_2 = next(alert for alert in alerts if alert.source_type == "website_form")
    assert stage_2.message_body.startswith("Stonegate Stage 2 filled: Sam Seller, +14045551212")
    assert "Contact details received." in stage_2.message_body
    assert f"/os/leads/{completed.json()['lead_id']}" in stage_2.message_body

    completed_retry = client.post(
        "/api/v1/public/seller-leads",
        json=completed_website_payload(attempt_id),
    )
    late_capture = client.post(
        "/api/v1/public/seller-leads/address-capture",
        json=address_payload,
    )
    assert completed_retry.status_code == 201, completed_retry.text
    assert late_capture.status_code == 201, late_capture.text
    assert int(db_session.scalar(select(func.count()).select_from(StaffLeadAlert)) or 0) == 2

    settings = Settings.model_validate({"STAFF_LEAD_ALERT_SMS_MODE": "simulate"})
    assert process_next_staff_lead_alert(db_session, settings) == stage_1.id
    assert process_next_staff_lead_alert(db_session, settings) == stage_2.id
    db_session.refresh(stage_1)
    db_session.refresh(stage_2)
    assert stage_1.status == stage_2.status == "simulated"


def test_stage_2_waits_while_stage_1_delivery_is_retrying(
    db_session: Session,
    api_db_override: None,
) -> None:
    seed_org(db_session)
    enable_owner_lead_alerts(db_session)
    client = TestClient(app)
    attempt_id = str(uuid.uuid4())
    capture = client.post(
        "/api/v1/public/seller-leads/address-capture",
        json=address_capture_payload(attempt_id=attempt_id),
    )
    completed = client.post(
        "/api/v1/public/seller-leads",
        json=completed_website_payload(attempt_id),
    )
    assert capture.status_code == 201, capture.text
    assert completed.status_code == 201, completed.text
    settings = Settings.model_validate({"STAFF_LEAD_ALERT_SMS_MODE": "simulate"})
    stage_1 = db_session.scalar(
        select(StaffLeadAlert).where(
            StaffLeadAlert.source_type == "website_form_stage_1"
        )
    )
    stage_2 = db_session.scalar(
        select(StaffLeadAlert).where(StaffLeadAlert.source_type == "website_form")
    )
    assert stage_1 is not None and stage_2 is not None

    failed_id = process_next_staff_lead_alert(
        db_session,
        settings,
        FailingStaffAlertProvider(),
    )

    assert failed_id == stage_1.id
    db_session.refresh(stage_1)
    db_session.refresh(stage_2)
    assert stage_1.status == "retry"
    assert stage_1.next_attempt_at is not None
    assert stage_2.status == "pending"
    assert process_next_staff_lead_alert(db_session, settings) is None

    stage_1.next_attempt_at = None
    db_session.commit()
    assert process_next_staff_lead_alert(db_session, settings) == stage_1.id
    assert process_next_staff_lead_alert(db_session, settings) == stage_2.id
    db_session.refresh(stage_1)
    db_session.refresh(stage_2)
    assert stage_1.status == stage_2.status == "simulated"


def test_each_eligible_employee_receives_each_stage_exactly_once(
    db_session: Session,
    api_db_override: None,
) -> None:
    seed_org(db_session)
    owner = enable_owner_lead_alerts(db_session)
    second_recipient = User(
        organization_id=owner.organization_id,
        email="second-recipient@example.com",
        display_name="Second Recipient",
        is_active=True,
        voice_forwarding_number="+14045550124",
        lead_alert_sms_enabled=False,
    )
    db_session.add(second_recipient)
    db_session.commit()
    client = TestClient(app)
    attempt_id = str(uuid.uuid4())
    capture = client.post(
        "/api/v1/public/seller-leads/address-capture",
        json=address_capture_payload(attempt_id=attempt_id),
    )
    assert capture.status_code == 201, capture.text
    assert int(db_session.scalar(select(func.count()).select_from(StaffLeadAlert)) or 0) == 1

    second_recipient.lead_alert_sms_enabled = True
    db_session.commit()
    completed = client.post(
        "/api/v1/public/seller-leads",
        json=completed_website_payload(attempt_id),
    )
    retry = client.post(
        "/api/v1/public/seller-leads",
        json=completed_website_payload(attempt_id),
    )

    assert completed.status_code == 201, completed.text
    assert retry.status_code == 201, retry.text
    alerts = db_session.scalars(select(StaffLeadAlert)).all()
    assert len(alerts) == 4
    assert {
        (alert.recipient_user_id, alert.source_type)
        for alert in alerts
    } == {
        (owner.id, "website_form_stage_1"),
        (owner.id, "website_form"),
        (second_recipient.id, "website_form_stage_1"),
        (second_recipient.id, "website_form"),
    }


def test_address_capture_accepts_legacy_timeline_during_rolling_deploy(
    db_session: Session,
    api_db_override: None,
) -> None:
    seed_org(db_session)
    payload = address_capture_payload()
    payload["desired_timeline"] = "within_30_days"

    response = TestClient(app).post(
        "/api/v1/public/seller-leads/address-capture",
        json=payload,
    )

    assert response.status_code == 201, response.text
    lead = db_session.scalar(select(Lead))
    assert lead is not None
    assert lead.desired_timeline == "within_30_days"


def test_new_address_retry_preserves_legacy_timeline_for_duplicate_cleanup(
    db_session: Session,
    api_db_override: None,
) -> None:
    seed_org(db_session)
    client = TestClient(app)
    existing = client.post("/api/v1/public/seller-leads", json=public_payload())
    assert existing.status_code == 201, existing.text

    attempt_id = str(uuid.uuid4())
    legacy_capture_payload = address_capture_payload(attempt_id=attempt_id)
    legacy_capture_payload["desired_timeline"] = "within_30_days"
    capture = client.post(
        "/api/v1/public/seller-leads/address-capture",
        json=legacy_capture_payload,
    )
    assert capture.status_code == 201, capture.text
    placeholder_lead_id = uuid.UUID(capture.json()["lead_id"])
    placeholder_contact_id = uuid.UUID(capture.json()["contact_id"])

    new_client_retry = client.post(
        "/api/v1/public/seller-leads/address-capture",
        json=address_capture_payload(attempt_id=attempt_id),
    )
    assert new_client_retry.status_code == 201, new_client_retry.text
    submission = db_session.scalar(
        select(LeadFormSubmission).where(
            LeadFormSubmission.intake_attempt_id == uuid.UUID(attempt_id)
        )
    )
    placeholder_lead = db_session.get(Lead, placeholder_lead_id)
    assert submission is not None
    assert placeholder_lead is not None
    assert placeholder_lead.desired_timeline == "within_30_days"
    assert submission.raw_payload["desired_timeline"] == "within_30_days"

    completed = client.post(
        "/api/v1/public/seller-leads",
        json=completed_website_payload(attempt_id),
    )

    assert completed.status_code == 201, completed.text
    assert completed.json()["lead_id"] == existing.json()["lead_id"]
    assert completed.json()["matched_existing_lead"] is True
    assert db_session.get(Lead, placeholder_lead_id) is None
    assert db_session.get(Contact, placeholder_contact_id) is None
    assert int(db_session.scalar(select(func.count()).select_from(Lead)) or 0) == 1


def test_new_address_retry_does_not_hide_staff_timeline_change_from_cleanup_guard(
    db_session: Session,
    api_db_override: None,
) -> None:
    seed_org(db_session)
    client = TestClient(app)
    existing = client.post("/api/v1/public/seller-leads", json=public_payload())
    assert existing.status_code == 201, existing.text

    attempt_id = str(uuid.uuid4())
    capture = client.post(
        "/api/v1/public/seller-leads/address-capture",
        json=address_capture_payload(attempt_id=attempt_id),
    )
    assert capture.status_code == 201, capture.text
    placeholder_lead_id = uuid.UUID(capture.json()["lead_id"])
    placeholder_contact_id = uuid.UUID(capture.json()["contact_id"])
    placeholder_lead = db_session.get(Lead, placeholder_lead_id)
    assert placeholder_lead is not None
    placeholder_lead.desired_timeline = "asap"
    db_session.commit()

    retry = client.post(
        "/api/v1/public/seller-leads/address-capture",
        json=address_capture_payload(attempt_id=attempt_id),
    )
    assert retry.status_code == 201, retry.text
    submission = db_session.scalar(
        select(LeadFormSubmission).where(
            LeadFormSubmission.intake_attempt_id == uuid.UUID(attempt_id)
        )
    )
    assert submission is not None
    assert submission.raw_payload["desired_timeline"] is None

    completed = client.post(
        "/api/v1/public/seller-leads",
        json=completed_website_payload(attempt_id),
    )

    assert completed.status_code == 201, completed.text
    assert completed.json()["lead_id"] == existing.json()["lead_id"]
    assert completed.json()["matched_existing_lead"] is True
    preserved_lead = db_session.get(Lead, placeholder_lead_id)
    assert preserved_lead is not None
    assert preserved_lead.desired_timeline == "asap"
    assert db_session.get(Contact, placeholder_contact_id) is not None
    assert int(db_session.scalar(select(func.count()).select_from(Lead)) or 0) == 2


@pytest.mark.parametrize("invalid_event", ["missing", "wrong"])
def test_address_capture_requires_its_deterministic_meta_lead_event(
    db_session: Session,
    api_db_override: None,
    invalid_event: str,
) -> None:
    seed_org(db_session)
    payload = address_capture_payload()
    if invalid_event == "missing":
        payload.pop("meta_browser_event")
    else:
        payload["meta_browser_event"]["event_id"] = "stonegate-lead-wrong-attempt"

    response = TestClient(app).post(
        "/api/v1/public/seller-leads/address-capture",
        json=payload,
    )

    assert response.status_code == 422
    assert int(db_session.scalar(select(func.count()).select_from(Lead)) or 0) == 0


@pytest.mark.parametrize("invalid_event", ["missing", "wrong"])
def test_attempt_aware_contact_step_requires_its_deterministic_meta_contact_event(
    db_session: Session,
    api_db_override: None,
    invalid_event: str,
) -> None:
    seed_org(db_session)
    attempt_id = str(uuid.uuid4())
    payload = completed_website_payload(attempt_id)
    if invalid_event == "missing":
        payload.pop("meta_browser_event")
    else:
        payload["meta_browser_event"]["event_id"] = "stonegate-contact-wrong-attempt"

    response = TestClient(app).post("/api/v1/public/seller-leads", json=payload)

    assert response.status_code == 422
    assert int(db_session.scalar(select(func.count()).select_from(Lead)) or 0) == 0


def test_completed_contact_step_promotes_same_address_capture_exactly_once(
    db_session: Session,
    api_db_override: None,
) -> None:
    seed_org(db_session)
    client = TestClient(app)
    attempt_id = str(uuid.uuid4())
    capture = client.post(
        "/api/v1/public/seller-leads/address-capture",
        json=address_capture_payload(attempt_id=attempt_id),
    )
    assert capture.status_code == 201, capture.text
    payload = completed_website_payload(attempt_id)

    completed = client.post("/api/v1/public/seller-leads", json=payload)

    assert completed.status_code == 201, completed.text
    result = completed.json()
    assert result["lead_id"] == capture.json()["lead_id"]
    assert result["contact_id"] == capture.json()["contact_id"]
    assert result["property_id"] == capture.json()["property_id"]
    assert result["matched_existing_lead"] is False
    assert result["meta_pixel_event_name"] == "Contact"
    lead = db_session.get(Lead, uuid.UUID(result["lead_id"]))
    contact = db_session.get(Contact, uuid.UUID(result["contact_id"]))
    submission = db_session.scalar(select(LeadFormSubmission))
    assert lead is not None and contact is not None and submission is not None
    assert contact.legal_name == "Sam Seller"
    assert lead.source == "google_ppc"
    assert lead.lead_temperature is None
    assert lead.desired_timeline is None
    assert lead.qualification_context["website_intake_status"] == "completed"
    assert lead.qualification_context["contact_details_status"] == "provided"
    assert "prospecting_status" not in lead.qualification_context
    assert submission.completion_status == "completed"
    assert submission.completed_at is not None
    assert submission.raw_payload["_promoted_address_capture"] is True
    assert int(db_session.scalar(select(func.count()).select_from(Lead)) or 0) == 1
    assert int(db_session.scalar(select(func.count()).select_from(LeadFormSubmission)) or 0) == 1
    assert int(db_session.scalar(select(func.count()).select_from(ContactMethod)) or 0) == 2
    assert int(db_session.scalar(select(func.count()).select_from(ConsentRecord)) or 0) == 2
    assert int(db_session.scalar(select(func.count()).select_from(LeadManagementCase)) or 0) == 1
    assert int(db_session.scalar(select(func.count()).select_from(Task)) or 0) == 1
    assert int(db_session.scalar(select(func.count()).select_from(Conversation)) or 0) == 1
    assert int(db_session.scalar(select(func.count()).select_from(PropertyResearchRun)) or 0) == 1
    assert int(db_session.scalar(select(func.count()).select_from(AttributionTouch)) or 0) == 2
    assert int(db_session.scalar(select(func.count()).select_from(ConversionEvent)) or 0) == 2
    assert {event.event_type for event in db_session.scalars(select(ConversionEvent)).all()} == {
        "address_capture",
        "contact_complete",
    }
    exports = db_session.scalars(
        select(OfflineConversionExport).order_by(OfflineConversionExport.event_name)
    ).all()
    assert {(export.event_name, export.event_key) for export in exports} == {
        ("Lead", f"stonegate-lead-{attempt_id}"),
        ("Contact", f"stonegate-contact-{attempt_id}"),
    }

    counts_before_retry = {
        model.__tablename__: int(db_session.scalar(select(func.count()).select_from(model)) or 0)
        for model in (
            Lead,
            LeadFormSubmission,
            ContactMethod,
            ConsentRecord,
            LeadManagementCase,
            Task,
            Conversation,
            PropertyResearchRun,
            AttributionTouch,
            ConversionEvent,
            OfflineConversionExport,
        )
    }
    retry = client.post("/api/v1/public/seller-leads", json=payload)
    counts_after_retry = {
        model.__tablename__: int(db_session.scalar(select(func.count()).select_from(model)) or 0)
        for model in (
            Lead,
            LeadFormSubmission,
            ContactMethod,
            ConsentRecord,
            LeadManagementCase,
            Task,
            Conversation,
            PropertyResearchRun,
            AttributionTouch,
            ConversionEvent,
            OfflineConversionExport,
        )
    }
    assert retry.status_code == 201, retry.text
    assert retry.json()["lead_id"] == result["lead_id"]
    assert retry.json()["duplicate_status"] == "already_completed"
    assert counts_after_retry == counts_before_retry

    late_capture = client.post(
        "/api/v1/public/seller-leads/address-capture",
        json=address_capture_payload(attempt_id=attempt_id),
    )
    assert late_capture.status_code == 201
    assert late_capture.json()["completion_status"] == "completed"
    assert late_capture.json()["lead_id"] == result["lead_id"]
    counts_after_late_capture = {
        model.__tablename__: int(db_session.scalar(select(func.count()).select_from(model)) or 0)
        for model in (
            Lead,
            LeadFormSubmission,
            ContactMethod,
            ConsentRecord,
            LeadManagementCase,
            Task,
            Conversation,
            PropertyResearchRun,
            AttributionTouch,
            ConversionEvent,
            OfflineConversionExport,
        )
    }
    assert counts_after_late_capture == counts_before_retry


def test_optional_enrichment_adds_timeline_after_contact_completion(
    db_session: Session,
    api_db_override: None,
) -> None:
    seed_org(db_session)
    client = TestClient(app)
    attempt_id = str(uuid.uuid4())
    capture = client.post(
        "/api/v1/public/seller-leads/address-capture",
        json=address_capture_payload(attempt_id=attempt_id),
    )
    assert capture.status_code == 201, capture.text

    completed = client.post(
        "/api/v1/public/seller-leads",
        json=completed_website_payload(attempt_id),
    )
    assert completed.status_code == 201, completed.text
    lead = db_session.get(Lead, uuid.UUID(completed.json()["lead_id"]))
    assert lead is not None
    assert lead.desired_timeline is None

    enriched = client.post(
        "/api/v1/public/seller-leads/enrichment",
        json={
            "enrichment_token": completed.json()["enrichment_token"],
            "desired_timeline": "within_30_days",
        },
    )

    assert enriched.status_code == 200, enriched.text
    assert enriched.json()["lead_id"] == completed.json()["lead_id"]
    db_session.refresh(lead)
    assert lead.desired_timeline == "within_30_days"
    submission = db_session.scalar(select(LeadFormSubmission))
    assert submission is not None
    assert submission.raw_payload["desired_timeline"] == "within_30_days"
    enrichment_event = db_session.scalar(
        select(ConversionEvent).where(ConversionEvent.event_type == "form_enrichment_submit")
    )
    assert enrichment_event is not None
    assert enrichment_event.event_metadata == {"fields_added": ["desired_timeline"]}


def test_contact_step_arriving_first_creates_both_meta_events_and_late_capture_is_noop(
    db_session: Session,
    api_db_override: None,
) -> None:
    seed_org(db_session)
    enable_owner_lead_alerts(db_session)
    client = TestClient(app)
    attempt_id = str(uuid.uuid4())
    payload = completed_website_payload(attempt_id)

    completed = client.post("/api/v1/public/seller-leads", json=payload)

    assert completed.status_code == 201, completed.text
    result = completed.json()
    assert result["meta_pixel_event_name"] == "Contact"
    assert int(db_session.scalar(select(func.count()).select_from(Lead)) or 0) == 1
    assert int(db_session.scalar(select(func.count()).select_from(LeadFormSubmission)) or 0) == 1
    assert int(db_session.scalar(select(func.count()).select_from(ConversionEvent)) or 0) == 2
    alerts = db_session.scalars(select(StaffLeadAlert)).all()
    assert len(alerts) == 2
    assert {alert.source_type for alert in alerts} == {
        "website_form_stage_1",
        "website_form",
    }
    assert any("Stage 1 filled" in alert.message_body for alert in alerts)
    assert any("Stage 2 filled" in alert.message_body for alert in alerts)
    exports = db_session.scalars(select(OfflineConversionExport)).all()
    assert {(export.event_name, export.event_key) for export in exports} == {
        ("Lead", f"stonegate-lead-{attempt_id}"),
        ("Contact", f"stonegate-contact-{attempt_id}"),
    }
    counts_before_late_capture = {
        model.__tablename__: int(db_session.scalar(select(func.count()).select_from(model)) or 0)
        for model in (
            Lead,
            LeadFormSubmission,
            AttributionTouch,
            ConversionEvent,
            OfflineConversionExport,
            ActivityEvent,
            AuditEvent,
            Task,
            StaffLeadAlert,
        )
    }

    late_capture = client.post(
        "/api/v1/public/seller-leads/address-capture",
        json=address_capture_payload(attempt_id=attempt_id),
    )

    assert late_capture.status_code == 201, late_capture.text
    assert late_capture.json()["lead_id"] == result["lead_id"]
    assert late_capture.json()["completion_status"] == "completed"
    counts_after_late_capture = {
        model.__tablename__: int(db_session.scalar(select(func.count()).select_from(model)) or 0)
        for model in (
            Lead,
            LeadFormSubmission,
            AttributionTouch,
            ConversionEvent,
            OfflineConversionExport,
            ActivityEvent,
            AuditEvent,
            Task,
            StaffLeadAlert,
        )
    }
    assert counts_after_late_capture == counts_before_late_capture


def test_completed_retry_repairs_missing_contact_export_without_replaying_operations(
    db_session: Session,
    api_db_override: None,
) -> None:
    seed_org(db_session)
    client = TestClient(app)
    attempt_id = str(uuid.uuid4())
    payload = completed_website_payload(attempt_id)
    completed = client.post("/api/v1/public/seller-leads", json=payload)
    assert completed.status_code == 201, completed.text
    contact_export = db_session.scalar(
        select(OfflineConversionExport).where(OfflineConversionExport.event_name == "Contact")
    )
    assert contact_export is not None
    db_session.delete(contact_export)
    db_session.commit()
    operational_models = (
        Lead,
        LeadFormSubmission,
        ContactMethod,
        ConsentRecord,
        LeadManagementCase,
        Task,
        Conversation,
        PropertyResearchRun,
        AttributionTouch,
        ConversionEvent,
        ActivityEvent,
        AuditEvent,
        StaffLeadAlert,
    )
    counts_before_retry = {
        model.__tablename__: int(db_session.scalar(select(func.count()).select_from(model)) or 0)
        for model in operational_models
    }

    retry = client.post("/api/v1/public/seller-leads", json=payload)

    assert retry.status_code == 201, retry.text
    assert retry.json()["duplicate_status"] == "already_completed"
    assert retry.json()["meta_pixel_event_name"] == "Contact"
    assert (
        int(db_session.scalar(select(func.count()).select_from(OfflineConversionExport)) or 0) == 2
    )
    counts_after_retry = {
        model.__tablename__: int(db_session.scalar(select(func.count()).select_from(model)) or 0)
        for model in operational_models
    }
    assert counts_after_retry == counts_before_retry


def test_address_capture_rejects_a_meta_event_identity_collision(
    db_session: Session,
    api_db_override: None,
) -> None:
    seed_org(db_session)
    client = TestClient(app)
    attempt_id = str(uuid.uuid4())
    payload = address_capture_payload(attempt_id=attempt_id)
    created = client.post("/api/v1/public/seller-leads/address-capture", json=payload)
    assert created.status_code == 201, created.text
    export = db_session.scalar(select(OfflineConversionExport))
    assert export is not None
    export.event_name = "Contact"
    db_session.commit()

    with pytest.raises(RuntimeError, match="Address-lead conversion identity is already in use"):
        client.post("/api/v1/public/seller-leads/address-capture", json=payload)


def test_address_capture_promotion_reuses_known_contact_without_orphaning_placeholder(
    db_session: Session,
    api_db_override: None,
) -> None:
    seed_org(db_session)
    client = TestClient(app)
    attempt_id = str(uuid.uuid4())
    capture = client.post(
        "/api/v1/public/seller-leads/address-capture",
        json=address_capture_payload(attempt_id=attempt_id),
    )
    assert capture.status_code == 201, capture.text
    partial_lead = db_session.get(Lead, uuid.UUID(capture.json()["lead_id"]))
    assert partial_lead is not None
    known_contact = Contact(
        organization_id=partial_lead.organization_id,
        legal_name="Known Seller",
        preferred_name=None,
        contact_type="seller",
        assigned_user_id=None,
    )
    db_session.add(known_contact)
    db_session.flush()
    db_session.add(
        ContactMethod(
            organization_id=partial_lead.organization_id,
            contact_id=known_contact.id,
            method_type="email",
            value="sam@example.com",
            normalized_value="sam@example.com",
            is_primary=True,
        )
    )
    db_session.commit()

    payload = completed_website_payload(attempt_id)
    completed = client.post("/api/v1/public/seller-leads", json=payload)

    assert completed.status_code == 201, completed.text
    assert completed.json()["lead_id"] == capture.json()["lead_id"]
    assert completed.json()["contact_id"] == str(known_contact.id)
    assert db_session.get(Contact, uuid.UUID(capture.json()["contact_id"])) is None
    assert int(db_session.scalar(select(func.count()).select_from(Contact)) or 0) == 1


def test_address_capture_promotion_merges_into_existing_active_person_property_lead(
    db_session: Session,
    api_db_override: None,
) -> None:
    seed_org(db_session)
    client = TestClient(app)
    existing_response = client.post("/api/v1/public/seller-leads", json=public_payload())
    assert existing_response.status_code == 201, existing_response.text
    existing = existing_response.json()
    attempt_id = str(uuid.uuid4())
    capture = client.post(
        "/api/v1/public/seller-leads/address-capture",
        json=address_capture_payload(attempt_id=attempt_id),
    )
    assert capture.status_code == 201, capture.text
    placeholder_lead_id = uuid.UUID(capture.json()["lead_id"])
    placeholder_contact_id = uuid.UUID(capture.json()["contact_id"])
    assert placeholder_lead_id != uuid.UUID(existing["lead_id"])
    automation_models = (
        Task,
        AiOrchestratorEvent,
        StaffLeadAlert,
        Conversation,
        LeadManagementCase,
        PropertyResearchRun,
    )
    automation_before_completion = {
        model.__tablename__: int(db_session.scalar(select(func.count()).select_from(model)) or 0)
        for model in automation_models
    }

    completed = client.post(
        "/api/v1/public/seller-leads",
        json=completed_website_payload(attempt_id),
    )

    assert completed.status_code == 201, completed.text
    result = completed.json()
    assert result["lead_id"] == existing["lead_id"]
    assert result["contact_id"] == existing["contact_id"]
    assert result["property_id"] == existing["property_id"]
    assert result["duplicate_status"] == "matched_existing_lead"
    assert result["matched_existing_lead"] is True
    assert result["meta_pixel_event_name"] == "Contact"
    assert db_session.get(Lead, placeholder_lead_id) is None
    assert db_session.get(Contact, placeholder_contact_id) is None
    assert int(db_session.scalar(select(func.count()).select_from(Lead)) or 0) == 1
    assert int(db_session.scalar(select(func.count()).select_from(Contact)) or 0) == 1
    assert int(db_session.scalar(select(func.count()).select_from(Property)) or 0) == 1
    automation_after_completion = {
        model.__tablename__: int(db_session.scalar(select(func.count()).select_from(model)) or 0)
        for model in automation_models
    }
    assert automation_after_completion == automation_before_completion

    submission = db_session.scalar(
        select(LeadFormSubmission).where(
            LeadFormSubmission.intake_attempt_id == uuid.UUID(attempt_id)
        )
    )
    assert submission is not None
    assert str(submission.lead_id) == existing["lead_id"]
    assert submission.completion_status == "completed"
    assert submission.raw_payload["_matched_existing_lead"] is True
    assert submission.raw_payload["_promoted_address_capture"] is True
    address_event = db_session.scalar(
        select(ConversionEvent).where(ConversionEvent.event_type == "address_capture")
    )
    assert address_event is not None
    assert str(address_event.lead_id) == existing["lead_id"]
    address_export = db_session.scalar(
        select(OfflineConversionExport).where(
            OfflineConversionExport.event_key == f"stonegate-lead-{attempt_id}"
        )
    )
    assert address_export is not None
    assert str(address_export.lead_id) == existing["lead_id"]
    expected_external_id = hashlib.sha256(
        f"{address_export.organization_id}:{existing['lead_id']}".encode()
    ).hexdigest()
    assert address_export.payload_snapshot["external_id_hash"] == expected_external_id
    contact_export = db_session.scalar(
        select(OfflineConversionExport).where(
            OfflineConversionExport.event_key == f"stonegate-contact-{attempt_id}"
        )
    )
    assert contact_export is not None
    assert str(contact_export.lead_id) == existing["lead_id"]
    assert {touch.lead_id for touch in db_session.scalars(select(AttributionTouch)).all()} == {
        uuid.UUID(existing["lead_id"])
    }

    counts_before_retry = {
        model.__tablename__: int(db_session.scalar(select(func.count()).select_from(model)) or 0)
        for model in (
            Lead,
            Contact,
            LeadFormSubmission,
            AttributionTouch,
            ConversionEvent,
            OfflineConversionExport,
            ActivityEvent,
            AuditEvent,
            *automation_models,
        )
    }
    retry = client.post(
        "/api/v1/public/seller-leads",
        json=completed_website_payload(attempt_id),
    )
    assert retry.status_code == 201, retry.text
    assert retry.json()["duplicate_status"] == "already_completed"
    assert retry.json()["matched_existing_lead"] is True
    assert retry.json()["lead_id"] == existing["lead_id"]
    counts_after_retry = {
        model.__tablename__: int(db_session.scalar(select(func.count()).select_from(model)) or 0)
        for model in (
            Lead,
            Contact,
            LeadFormSubmission,
            AttributionTouch,
            ConversionEvent,
            OfflineConversionExport,
            ActivityEvent,
            AuditEvent,
            *automation_models,
        )
    }
    assert counts_after_retry == counts_before_retry


def test_stage_alerts_survive_address_placeholder_merge_without_a_dead_link(
    db_session: Session,
    api_db_override: None,
) -> None:
    seed_org(db_session)
    client = TestClient(app)
    existing = client.post("/api/v1/public/seller-leads", json=public_payload())
    assert existing.status_code == 201, existing.text
    enable_owner_lead_alerts(db_session)
    attempt_id = str(uuid.uuid4())

    capture = client.post(
        "/api/v1/public/seller-leads/address-capture",
        json=address_capture_payload(attempt_id=attempt_id),
    )
    assert capture.status_code == 201, capture.text
    placeholder_lead_id = uuid.UUID(capture.json()["lead_id"])
    stage_1 = db_session.scalar(
        select(StaffLeadAlert).where(
            StaffLeadAlert.source_type == "website_form_stage_1"
        )
    )
    assert stage_1 is not None
    assert stage_1.lead_id == placeholder_lead_id
    assert str(placeholder_lead_id) not in stage_1.message_body

    completed = client.post(
        "/api/v1/public/seller-leads",
        json=completed_website_payload(attempt_id),
    )

    assert completed.status_code == 201, completed.text
    surviving_lead_id = uuid.UUID(existing.json()["lead_id"])
    assert completed.json()["lead_id"] == existing.json()["lead_id"]
    assert completed.json()["matched_existing_lead"] is True
    assert db_session.get(Lead, placeholder_lead_id) is None
    alerts = db_session.scalars(select(StaffLeadAlert)).all()
    assert len(alerts) == 2
    assert {alert.lead_id for alert in alerts} == {surviving_lead_id}
    assert {alert.source_type for alert in alerts} == {
        "website_form_stage_1",
        "website_form",
    }
    stage_2 = next(alert for alert in alerts if alert.source_type == "website_form")
    assert f"/os/leads/{surviving_lead_id}" in stage_2.message_body


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("property_state", "Georgia"),
        ("property_state", "G1"),
        ("property_postal_code", "3030"),
        ("property_postal_code", "abcde"),
    ],
)
def test_address_capture_rejects_invalid_address_components(
    db_session: Session,
    api_db_override: None,
    field: str,
    value: str,
) -> None:
    seed_org(db_session)
    payload = address_capture_payload()
    payload[field] = value

    response = TestClient(app).post(
        "/api/v1/public/seller-leads/address-capture",
        json=payload,
    )

    assert response.status_code == 422
    assert int(db_session.scalar(select(func.count()).select_from(Lead)) or 0) == 0


def test_public_seller_intake_creates_lead_consent_and_attribution(
    db_session: Session,
    api_db_override: None,
) -> None:
    seed_org(db_session)
    client = TestClient(app)

    response = client.post(
        "/api/v1/public/seller-leads",
        json=public_payload(),
        headers={"User-Agent": "pytest", "X-Forwarded-For": "203.0.113.10"},
    )

    assert response.status_code == 201
    payload = response.json()
    assert payload["message"] == "Thanks. Your property inquiry was received."
    assert payload["duplicate_status"] == "created"
    assert payload["matched_existing_lead"] is False
    assert len(payload["enrichment_token"]) >= 32
    assert payload["enrichment_expires_at"]
    assert int(db_session.scalar(select(func.count()).select_from(Lead)) or 0) == 1
    assert int(db_session.scalar(select(func.count()).select_from(LeadManagementCase)) or 0) == 1
    assert int(db_session.scalar(select(func.count()).select_from(Task)) or 0) == 1
    assert int(db_session.scalar(select(func.count()).select_from(ContactMethod)) or 0) == 2
    assert int(db_session.scalar(select(func.count()).select_from(ConsentRecord)) or 0) == 2
    assert int(db_session.scalar(select(func.count()).select_from(LeadFormSubmission)) or 0) == 1
    assert int(db_session.scalar(select(func.count()).select_from(AttributionTouch)) or 0) == 2
    assert int(db_session.scalar(select(func.count()).select_from(ConversionEvent)) or 0) == 1

    consents = db_session.scalars(select(ConsentRecord).order_by(ConsentRecord.channel)).all()
    assert {consent.channel for consent in consents} == {"email", "phone"}
    assert all(consent.status == "granted" for consent in consents)
    assert all(consent.captured_ip == "testclient" for consent in consents)
    assert all(consent.wording_version == "seller-contact-web-v3" for consent in consents)
    assert all(
        consent.wording
        == (
            "By submitting this form, you authorize Stonegate Home Buyers to contact you by "
            "phone call or email about your property inquiry and possible selling options. "
            "This permission does not include text messages."
        )
        for consent in consents
    )
    property_record = db_session.scalar(select(Property))
    assert property_record is not None
    assert property_record.normalized_address_key == "55 auburn ave|atlanta|GA|30303"
    lead = db_session.scalar(select(Lead))
    assert lead is not None
    assert lead.motivation == "Inherited property"
    assert lead.desired_timeline == "30 days"
    assert lead.asking_price == "180000"
    assert lead.property_condition == "major_repairs"
    assert lead.occupancy_status == "vacant"
    assert lead.mortgage_balance == "90000"
    assert property_record.property_type == "single_family"
    assert lead.assigned_user_id is not None
    task = db_session.scalar(select(Task))
    assert task is not None
    assert task.task_type == "speed_to_lead"
    assert task.status == "open"
    assert task.priority == "urgent"
    assert task.responsible_user_id == lead.assigned_user_id
    assert str(task.lead_id) == payload["lead_id"]
    lead_manager_case = db_session.scalar(select(LeadManagementCase))
    assert lead_manager_case is not None
    assert lead_manager_case.status == "awaiting_acceptance"
    assert lead_manager_case.assigned_user_id == lead.assigned_user_id
    conversation = db_session.scalar(select(Conversation))
    assert conversation is not None
    assert conversation.assigned_user_id == lead.assigned_user_id
    accepted = client.post(
        f"/api/v1/lead-manager/cases/{lead_manager_case.id}/accept",
        headers={"X-Dev-User-Email": "owner@example.com"},
        json={"reason": "Website inquiry assigned for immediate qualification."},
    )
    assert accepted.status_code == 200, accepted.text
    assert accepted.json()["status"] == "active"
    conversion_event = db_session.scalar(select(ConversionEvent))
    assert conversion_event is not None
    assert conversion_event.event_type == "form_submit"
    assert str(conversion_event.lead_id) == payload["lead_id"]
    assert conversion_event.source == "google_ppc"
    assert conversion_event.medium == "cpc"
    assert conversion_event.event_metadata == {"matched_existing_lead": False}
    assert conversion_event.session_id == "session-intake-123"
    submission = db_session.scalar(select(LeadFormSubmission))
    assert submission is not None
    assert submission.enrichment_token_hash
    assert submission.raw_payload["consent_to_contact"] is True
    assert submission.raw_payload["sms_consent"] is False
    assert payload["enrichment_token"] not in str(submission.raw_payload)
    audit_event = db_session.scalar(
        select(AuditEvent).where(AuditEvent.action == "lead.public_create")
    )
    assert audit_event is not None
    assert audit_event.new_value is not None
    assert audit_event.new_value["consent_wording_version"] == "seller-contact-web-v3"
    assert audit_event.new_value["sms_consent"] is False
    assert audit_event.new_value["sms_consent_wording_version"] is None


def test_public_intake_preserves_supported_older_consent_wording(
    db_session: Session,
    api_db_override: None,
) -> None:
    seed_org(db_session)
    payload = public_payload()
    payload["consent_wording_version"] = "seller-contact-web-v2"
    payload["sms_consent"] = True
    payload["sms_consent_wording_version"] = "seller-sms-web-v2"

    response = TestClient(app).post("/api/v1/public/seller-leads", json=payload)

    assert response.status_code == 201, response.text
    assert response.json()["consent_wording_version"] == "seller-contact-web-v2"
    consents = db_session.scalars(select(ConsentRecord).order_by(ConsentRecord.channel)).all()
    non_sms_consents = [consent for consent in consents if consent.channel != "sms"]
    assert all(consent.wording_version == "seller-contact-web-v2" for consent in non_sms_consents)
    assert all("cash offer request" in consent.wording for consent in non_sms_consents)
    sms_consent = next(consent for consent in consents if consent.channel == "sms")
    assert sms_consent.wording_version == "seller-sms-web-v2"
    assert "cash offer updates" in sms_consent.wording


@pytest.mark.parametrize(
    ("field", "version"),
    [
        ("consent_wording_version", "seller-contact-web-unknown"),
        ("sms_consent_wording_version", "seller-sms-web-unknown"),
    ],
)
def test_public_intake_rejects_unknown_consent_wording_version(
    db_session: Session,
    api_db_override: None,
    field: str,
    version: str,
) -> None:
    seed_org(db_session)
    payload = public_payload()
    payload[field] = version

    response = TestClient(app).post("/api/v1/public/seller-leads", json=payload)

    assert response.status_code == 422
    assert "wording version" in response.text
    assert int(db_session.scalar(select(func.count()).select_from(Lead)) or 0) == 0


def test_public_seller_intake_queues_source_independent_staff_alert(
    db_session: Session,
    api_db_override: None,
) -> None:
    seed_org(db_session)
    owner = db_session.scalar(select(User).where(User.email == "owner@example.com"))
    assert owner is not None
    owner.voice_forwarding_number = "+14045550123"
    owner.lead_alert_sms_enabled = True
    db_session.commit()

    response = TestClient(app).post("/api/v1/public/seller-leads", json=public_payload())

    assert response.status_code == 201, response.text
    submission = db_session.scalar(select(LeadFormSubmission))
    alert = db_session.scalar(select(StaffLeadAlert))
    assert submission is not None
    assert alert is not None
    assert alert.meta_lead_event_id is None
    assert alert.source_type == "website_form"
    assert alert.source_event_id == submission.id
    assert alert.message_body.startswith("New Website House lead:")
    assert (
        process_next_staff_lead_alert(
            db_session,
            Settings.model_validate({"STAFF_LEAD_ALERT_SMS_MODE": "simulate"}),
        )
        == alert.id
    )
    db_session.refresh(alert)
    assert alert.status == "simulated"


def test_staff_alert_worker_recovers_recent_unalerted_website_lead(
    db_session: Session,
    api_db_override: None,
) -> None:
    seed_org(db_session)
    owner = db_session.scalar(select(User).where(User.email == "owner@example.com"))
    assert owner is not None
    owner.voice_forwarding_number = "+14045550123"
    owner.lead_alert_sms_enabled = False
    db_session.commit()
    response = TestClient(app).post("/api/v1/public/seller-leads", json=public_payload())
    assert response.status_code == 201, response.text
    assert db_session.scalar(select(StaffLeadAlert)) is None

    owner.lead_alert_sms_enabled = True
    db_session.commit()
    alert_id = process_next_staff_lead_alert(
        db_session,
        Settings.model_validate({"STAFF_LEAD_ALERT_SMS_MODE": "simulate"}),
    )

    alert = db_session.get(StaffLeadAlert, alert_id)
    assert alert is not None
    assert alert.source_type == "website_form"
    assert alert.meta_lead_event_id is None
    assert alert.status == "simulated"


def test_staff_alert_worker_recovers_stage_1_while_address_is_still_incomplete(
    db_session: Session,
    api_db_override: None,
) -> None:
    seed_org(db_session)
    owner = db_session.scalar(select(User).where(User.email == "owner@example.com"))
    assert owner is not None
    owner.voice_forwarding_number = "+14045550123"
    owner.lead_alert_sms_enabled = False
    db_session.commit()
    capture = TestClient(app).post(
        "/api/v1/public/seller-leads/address-capture",
        json=address_capture_payload(),
    )
    assert capture.status_code == 201, capture.text
    assert db_session.scalar(select(StaffLeadAlert)) is None

    owner.lead_alert_sms_enabled = True
    db_session.commit()
    alert_id = process_next_staff_lead_alert(
        db_session,
        Settings.model_validate({"STAFF_LEAD_ALERT_SMS_MODE": "simulate"}),
    )

    alert = db_session.get(StaffLeadAlert, alert_id)
    assert alert is not None
    assert alert.source_type == "website_form_stage_1"
    assert "Stage 1 filled" in alert.message_body
    assert alert.status == "simulated"


def test_staff_alert_recovery_backfills_both_stages_in_order_after_completion(
    db_session: Session,
    api_db_override: None,
) -> None:
    seed_org(db_session)
    owner = db_session.scalar(select(User).where(User.email == "owner@example.com"))
    assert owner is not None
    owner.voice_forwarding_number = "+14045550123"
    owner.lead_alert_sms_enabled = False
    db_session.commit()
    client = TestClient(app)
    attempt_id = str(uuid.uuid4())
    capture = client.post(
        "/api/v1/public/seller-leads/address-capture",
        json=address_capture_payload(attempt_id=attempt_id),
    )
    completed = client.post(
        "/api/v1/public/seller-leads",
        json=completed_website_payload(attempt_id),
    )
    assert capture.status_code == 201, capture.text
    assert completed.status_code == 201, completed.text
    assert db_session.scalar(select(StaffLeadAlert)) is None

    owner.lead_alert_sms_enabled = True
    db_session.commit()
    stage_1_id = process_next_staff_lead_alert(
        db_session,
        Settings.model_validate({"STAFF_LEAD_ALERT_SMS_MODE": "simulate"}),
    )
    stage_2_id = process_next_staff_lead_alert(
        db_session,
        Settings.model_validate({"STAFF_LEAD_ALERT_SMS_MODE": "simulate"}),
    )

    stage_1 = db_session.get(StaffLeadAlert, stage_1_id)
    stage_2 = db_session.get(StaffLeadAlert, stage_2_id)
    assert stage_1 is not None and stage_2 is not None
    assert stage_1.source_type == "website_form_stage_1"
    assert stage_2.source_type == "website_form"
    assert "Stage 1 filled" in stage_1.message_body
    assert "Stage 2 filled" in stage_2.message_body
    assert stage_1.status == stage_2.status == "simulated"
    assert int(db_session.scalar(select(func.count()).select_from(StaffLeadAlert)) or 0) == 2


def test_public_land_intake_preserves_asset_and_parcel_identity(
    db_session: Session,
    api_db_override: None,
) -> None:
    seed_org(db_session)
    payload = public_payload()
    payload.update(
        {
            "property_address": "",
            "property_city": "",
            "property_postal_code": "",
            "property_county": "Gilmer County",
            "property_type": "vacant_land",
            "asset_class": "Land",
            "parcel_id": "3050-007-007",
        }
    )

    response = TestClient(app).post("/api/v1/public/seller-leads", json=payload)

    assert response.status_code == 201, response.text
    lead = db_session.scalar(select(Lead))
    property_record = db_session.scalar(select(Property))
    assert lead is not None and lead.asset_class == "land"
    assert property_record is not None
    assert property_record.property_type == "vacant_land"
    assert property_record.parcel_id == "3050-007-007"
    assert property_record.normalized_address_key is None
    assert property_record.normalized_parcel_key == "GA|gilmer|3050007007"

    payload["parcel_id"] = "3050007007"
    payload["property_county"] = "Gilmer"
    duplicate = TestClient(app).post("/api/v1/public/seller-leads", json=payload)
    assert duplicate.status_code == 201, duplicate.text
    assert duplicate.json()["matched_existing_lead"] is True
    assert int(db_session.scalar(select(func.count()).select_from(Property)) or 0) == 1


def test_public_duplicate_matching_does_not_merge_house_and_land_lanes(
    db_session: Session,
    api_db_override: None,
) -> None:
    seed_org(db_session)
    client = TestClient(app)
    house_payload = public_payload()
    land_payload = public_payload()
    land_payload.update({"asset_class": "land", "property_type": "vacant_land"})

    house = client.post("/api/v1/public/seller-leads", json=house_payload)
    land = client.post("/api/v1/public/seller-leads", json=land_payload)

    assert house.status_code == 201, house.text
    assert land.status_code == 201, land.text
    assert house.json()["matched_existing_lead"] is False
    assert land.json()["matched_existing_lead"] is False
    leads = db_session.scalars(select(Lead).order_by(Lead.created_at)).all()
    assert {lead.asset_class for lead in leads} == {"house", "land"}
    assert len({lead.property_id for lead in leads}) == 1


def test_public_intake_enrichment_updates_same_lead_without_overwriting_staff_values(
    db_session: Session,
    api_db_override: None,
) -> None:
    seed_org(db_session)
    client = TestClient(app)
    initial = public_payload()
    for field in (
        "property_type",
        "reason_for_selling",
        "desired_timeline",
        "property_condition",
        "occupancy_status",
        "asking_price",
        "mortgage_balance",
        "comments",
    ):
        initial[field] = None

    intake_response = client.post("/api/v1/public/seller-leads", json=initial)
    assert intake_response.status_code == 201
    token = intake_response.json()["enrichment_token"]

    lead = db_session.scalar(select(Lead))
    assert lead is not None
    lead.motivation = "staff_reviewed_motivation"
    db_session.commit()

    enrichment_response = client.post(
        "/api/v1/public/seller-leads/enrichment",
        json={
            "enrichment_token": token,
            "property_type": "single_family",
            "reason_for_selling": "repairs_or_condition",
            "desired_timeline": "within_30_days",
            "property_condition": "major_repairs",
            "occupancy_status": "vacant",
            "asking_price": "200,000",
            "mortgage_balance": "90,000",
            "comments": "Older roof and kitchen updates are likely.",
            "conversion_session_id": "session-intake-123",
        },
        headers={"User-Agent": "pytest-enrichment", "X-Forwarded-For": "203.0.113.12"},
    )

    assert enrichment_response.status_code == 200
    assert enrichment_response.json()["lead_id"] == intake_response.json()["lead_id"]
    assert int(db_session.scalar(select(func.count()).select_from(Lead)) or 0) == 1
    assert int(db_session.scalar(select(func.count()).select_from(LeadFormSubmission)) or 0) == 1
    db_session.refresh(lead)
    property_record = db_session.scalar(select(Property))
    submission = db_session.scalar(select(LeadFormSubmission))
    assert property_record is not None
    assert submission is not None
    assert lead.motivation == "staff_reviewed_motivation"
    assert lead.desired_timeline == "within_30_days"
    assert lead.property_condition == "major_repairs"
    assert lead.occupancy_status == "vacant"
    assert lead.asking_price == "200,000"
    assert lead.mortgage_balance == "90,000"
    assert property_record.property_type == "single_family"
    assert submission.raw_payload["comments"] == "Older roof and kitchen updates are likely."
    assert submission.enriched_at is not None
    enrichment_event = db_session.scalar(
        select(ConversionEvent).where(ConversionEvent.event_type == "form_enrichment_submit")
    )
    assert enrichment_event is not None
    assert enrichment_event.event_metadata == {
        "fields_added": [
            "asking_price",
            "comments",
            "desired_timeline",
            "mortgage_balance",
            "occupancy_status",
            "property_condition",
            "property_type",
            "reason_for_selling",
        ]
    }
    audit_event = db_session.scalar(
        select(AuditEvent).where(AuditEvent.action == "lead.public_enrich")
    )
    assert audit_event is not None


def test_public_intake_enrichment_rejects_unknown_token(
    db_session: Session,
    api_db_override: None,
) -> None:
    seed_org(db_session)
    client = TestClient(app)

    response = client.post(
        "/api/v1/public/seller-leads/enrichment",
        json={
            "enrichment_token": "not-a-real-token-but-long-enough-to-validate",
            "property_condition": "major_repairs",
        },
    )

    assert response.status_code == 404
    assert int(db_session.scalar(select(func.count()).select_from(Lead)) or 0) == 0


def test_public_seller_intake_bootstraps_default_organization_when_missing(
    db_session: Session,
    api_db_override: None,
) -> None:
    client = TestClient(app)

    response = client.post("/api/v1/public/seller-leads", json=public_payload())

    assert response.status_code == 201
    assert int(db_session.scalar(select(func.count()).select_from(Lead)) or 0) == 1


def test_public_conversion_event_endpoint_records_attribution(
    db_session: Session,
    api_db_override: None,
) -> None:
    seed_org(db_session)
    client = TestClient(app)

    response = client.post(
        "/api/v1/public/conversion-events",
        json={
            "event_type": "form_start",
            "session_id": "session-123",
            "metadata": {"field": "property_address"},
            "attribution": {
                "landing_page": "/get-a-cash-offer",
                "referrer": "https://example.com",
                "utm_source": "meta_ads",
                "utm_medium": "paid_social",
                "utm_campaign": "seller-leads",
                "fbclid": "fbclid-test",
            },
        },
        headers={"User-Agent": "pytest", "X-Forwarded-For": "203.0.113.11"},
    )

    assert response.status_code == 201
    event = db_session.scalar(select(ConversionEvent))
    assert event is not None
    assert response.json()["id"] == str(event.id)
    assert event.event_type == "form_start"
    assert event.session_id == "session-123"
    assert event.ip_address == "testclient"
    assert event.source == "meta_ads"
    assert event.medium == "paid_social"
    assert event.event_metadata == {"field": "property_address"}


def test_public_write_rate_limits_are_route_specific_and_conversion_friendly(
    monkeypatch: MonkeyPatch,
    db_session: Session,
    api_db_override: None,
) -> None:
    seed_org(db_session)
    monkeypatch.setenv("PUBLIC_INTAKE_RATE_LIMIT_ENABLED", "true")
    monkeypatch.setenv("PUBLIC_INTAKE_RATE_LIMIT_REQUESTS", "1")
    monkeypatch.setenv("PUBLIC_INTAKE_RATE_LIMIT_WINDOW_SECONDS", "600")
    monkeypatch.setenv("PUBLIC_CONVERSION_EVENT_RATE_LIMIT_REQUESTS", "2")
    monkeypatch.setenv("PUBLIC_CONVERSION_EVENT_RATE_LIMIT_WINDOW_SECONDS", "600")
    monkeypatch.setattr(
        public_router,
        "public_intake_rate_limiter",
        FixedWindowRateLimiter(),
    )
    get_settings.cache_clear()
    client = TestClient(app)
    headers = {"X-Forwarded-For": "198.51.100.200", "User-Agent": "rate-limit-test"}

    try:
        intake = client.post(
            "/api/v1/public/seller-leads",
            json=public_payload(),
            headers=headers,
        )
        blocked_intake = client.post(
            "/api/v1/public/seller-leads",
            json=public_payload(),
            headers=headers,
        )
        enrichment_payload = {
            "enrichment_token": intake.json()["enrichment_token"],
            "property_condition": "major_repairs",
        }
        enrichment = client.post(
            "/api/v1/public/seller-leads/enrichment",
            json=enrichment_payload,
            headers=headers,
        )
        blocked_enrichment = client.post(
            "/api/v1/public/seller-leads/enrichment",
            json=enrichment_payload,
            headers=headers,
        )
        conversion_payload = {
            "event_type": "form_start",
            "session_id": "rate-limit-session",
            "attribution": {"landing_page": "/get-a-cash-offer"},
        }
        conversions = [
            client.post(
                "/api/v1/public/conversion-events",
                json=conversion_payload,
                headers=headers,
            )
            for _ in range(2)
        ]
        blocked_conversion = client.post(
            "/api/v1/public/conversion-events",
            json=conversion_payload,
            headers=headers,
        )
    finally:
        get_settings.cache_clear()

    assert intake.status_code == 201
    assert blocked_intake.status_code == 429
    assert enrichment.status_code == 200
    assert blocked_enrichment.status_code == 429
    assert [response.status_code for response in conversions] == [201, 201]
    assert blocked_conversion.status_code == 429
    assert blocked_conversion.json()["detail"] == (
        "Too many conversion events. Please wait before trying again."
    )
    assert int(blocked_conversion.headers["Retry-After"]) >= 1


def test_in_process_rate_limiter_has_a_hard_key_bound() -> None:
    limiter = FixedWindowRateLimiter(max_keys=2)

    assert limiter.check("client-a", limit=5, window_seconds=60, now=1) is None
    assert limiter.check("client-b", limit=5, window_seconds=60, now=1) is None
    assert limiter.check("client-c", limit=5, window_seconds=60, now=1) is None

    assert limiter.tracked_key_count == 2


def test_client_address_uses_only_platform_resolved_production_peer() -> None:
    scope: Scope = {
        "type": "http",
        "asgi": {"version": "3.0", "spec_version": "2.3"},
        "http_version": "1.1",
        "method": "POST",
        "scheme": "https",
        "path": "/",
        "raw_path": b"/",
        "query_string": b"",
        "root_path": "",
        "headers": [
            (b"cf-connecting-ip", b"203.0.113.25"),
            (b"cf-ray", b"test-ray-ATL"),
            (b"x-forwarded-for", b"198.51.100.99"),
        ],
        "client": ("10.0.0.5", 12345),
        "server": ("api.stonegate.test", 443),
    }
    request = Request(scope)
    missing_edge_header = Request({**scope, "headers": [(b"x-forwarded-for", b"198.51.100.99")]})
    public_peer = Request(
        {
            **scope,
            "headers": [(b"x-forwarded-for", b"198.51.100.99")],
            "client": ("8.8.8.8", 12345),
        }
    )

    assert trusted_client_address(request, production=True) == "edge-unknown"
    assert trusted_client_address(missing_edge_header, production=True) == "edge-unknown"
    assert trusted_client_address(public_peer, production=True) == "8.8.8.8"
    assert trusted_client_address(request, production=False) == "10.0.0.5"


def test_bounded_request_reader_stops_before_buffering_an_oversized_stream() -> None:
    messages: list[Message] = [
        {"type": "http.request", "body": b"1234", "more_body": True},
        {"type": "http.request", "body": b"5678", "more_body": True},
        {"type": "http.request", "body": b"never-read", "more_body": False},
    ]
    receive_count = 0

    async def receive() -> Message:
        nonlocal receive_count
        message = messages[receive_count]
        receive_count += 1
        return message

    scope: Scope = {
        "type": "http",
        "asgi": {"version": "3.0", "spec_version": "2.3"},
        "http_version": "1.1",
        "method": "POST",
        "scheme": "https",
        "path": "/",
        "raw_path": b"/",
        "query_string": b"",
        "root_path": "",
        "headers": [],
        "client": ("10.0.0.5", 12345),
        "server": ("api.stonegate.test", 443),
    }
    request = Request(scope, receive)

    with pytest.raises(RequestBodyTooLargeError):
        asyncio.run(read_bounded_request_body(request, max_bytes=6))

    assert receive_count == 2


def test_public_page_view_queues_deduplicated_meta_view_content(
    db_session: Session,
    api_db_override: None,
) -> None:
    seed_org(db_session)
    client = TestClient(app)

    response = client.post(
        "/api/v1/public/conversion-events",
        json={
            "event_type": "page_view",
            "session_id": "session-meta-view",
            "attribution": {
                "landing_page": "/contact",
                "fbclid": "click-123",
                "fbclid_captured_at": "2026-08-04T21:48:07Z",
            },
            "meta_browser_event": {
                "event_id": "meta-view-event-123",
                "event_source_url": "https://www.stonegatehb.com/contact",
                "fbc": "fb.1.1785875287.click-123",
                "fbp": "fb.1.1785875287.987654321",
            },
        },
        headers={"User-Agent": "pytest-browser", "X-Forwarded-For": "203.0.113.12"},
    )

    assert response.status_code == 201
    export = db_session.scalar(select(OfflineConversionExport))
    assert export is not None
    assert export.event_name == "ViewContent"
    assert export.event_key == "meta-view-event-123"
    assert export.payload_snapshot["client_ip_address"] == "testclient"
    assert export.payload_snapshot["client_user_agent"] == "pytest-browser"
    assert export.payload_snapshot["fbp"] == "fb.1.1785875287.987654321"
    assert export.payload_snapshot["fbclid"] == "click-123"
    assert export.payload_snapshot["click_captured_at"] == "2026-08-04T21:48:07+00:00"
    conversion_event = db_session.scalar(select(ConversionEvent))
    assert conversion_event is not None
    assert conversion_event.source == "meta_ads"
    assert conversion_event.fbclid_captured_at is not None


def test_public_seller_intake_queues_hashed_meta_lead(
    db_session: Session,
    api_db_override: None,
) -> None:
    seed_org(db_session)
    client = TestClient(app)
    payload = public_payload()
    payload["attribution"] = {
        "landing_page": "/get-a-cash-offer",
        "utm_source": "meta_ads",
        "fbclid": "lead-click",
        "fbclid_captured_at": "2026-08-04T21:48:07Z",
    }
    payload["meta_browser_event"] = {
        "event_id": "meta-lead-event-123",
        "event_source_url": "https://stonegatehb.com/get-a-cash-offer",
        "fbc": "fb.1.1785875287.lead-click",
        "fbp": "fb.1.1785875287.123456789",
    }

    response = client.post(
        "/api/v1/public/seller-leads",
        json=payload,
        headers={"User-Agent": "pytest-browser", "X-Forwarded-For": "203.0.113.13"},
    )

    assert response.status_code == 201
    assert response.json()["meta_pixel_event_name"] == "Lead"
    export = db_session.scalar(select(OfflineConversionExport))
    assert export is not None
    assert export.event_name == "Lead"
    assert export.event_key == "meta-lead-event-123"
    assert export.lead_id is not None
    assert export.payload_snapshot["email_hashes"]
    assert export.payload_snapshot["phone_hashes"] == []
    assert export.payload_snapshot["external_id_hash"]
    assert "sam@example.com" not in str(export.payload_snapshot)
    assert "4045551212" not in str(export.payload_snapshot)
    meta_payload = build_meta_payload(export, Settings())
    meta_event = meta_payload["data"][0]
    assert meta_event["event_name"] == "Lead"
    assert meta_event["event_id"] == "meta-lead-event-123"
    assert meta_event["action_source"] == "website"
    assert meta_event["event_source_url"].endswith("/get-a-cash-offer")
    assert meta_event["user_data"]["em"]
    assert meta_event["user_data"]["external_id"]
    assert meta_event["user_data"]["client_ip_address"] == "testclient"
    assert meta_event["user_data"]["client_user_agent"] == "pytest-browser"
    assert meta_event["user_data"]["fbc"] == "fb.1.1785875287.lead-click"
    assert meta_event["user_data"]["fbp"] == "fb.1.1785875287.123456789"
    assert "ph" not in meta_event["user_data"]
    conversion_event = db_session.scalar(select(ConversionEvent))
    submission = db_session.scalar(select(LeadFormSubmission))
    touches = db_session.scalars(select(AttributionTouch)).all()
    assert conversion_event is not None and conversion_event.fbclid_captured_at is not None
    assert submission is not None and submission.fbclid_captured_at is not None
    assert touches and all(touch.fbclid_captured_at is not None for touch in touches)


def test_public_attribution_discards_unbound_click_time_without_rejecting_lead(
    db_session: Session,
    api_db_override: None,
) -> None:
    seed_org(db_session)
    payload = public_payload()
    payload["attribution"] = {
        "landing_page": "/get-a-cash-offer",
        "fbclid_captured_at": "2026-08-04T21:48:07Z",
    }

    response = TestClient(app).post("/api/v1/public/seller-leads", json=payload)

    assert response.status_code == 201
    assert int(db_session.scalar(select(func.count()).select_from(Lead)) or 0) == 1
    conversion_event = db_session.scalar(select(ConversionEvent))
    submission = db_session.scalar(select(LeadFormSubmission))
    touches = db_session.scalars(select(AttributionTouch)).all()
    assert conversion_event is not None and conversion_event.fbclid_captured_at is None
    assert submission is not None and submission.fbclid_captured_at is None
    assert touches and all(touch.fbclid_captured_at is None for touch in touches)


def test_public_attribution_discards_future_click_time_without_rejecting_lead(
    db_session: Session,
    api_db_override: None,
) -> None:
    seed_org(db_session)
    payload = public_payload()
    payload["attribution"] = {
        "landing_page": "/get-a-cash-offer",
        "fbclid": "clock-skew-click",
        "fbclid_captured_at": "2099-01-01T00:00:00Z",
    }

    response = TestClient(app).post("/api/v1/public/seller-leads", json=payload)

    assert response.status_code == 201
    conversion_event = db_session.scalar(select(ConversionEvent))
    assert conversion_event is not None
    assert conversion_event.fbclid == "clock-skew-click"
    assert conversion_event.fbclid_captured_at is None


def test_public_attribution_discards_malformed_click_time_without_rejecting_lead(
    db_session: Session,
    api_db_override: None,
) -> None:
    seed_org(db_session)
    payload = public_payload()
    payload["attribution"] = {
        "landing_page": "/get-a-cash-offer",
        "fbclid": "valid-click-with-bad-clock",
        "fbclid_captured_at": "not-a-date",
    }

    response = TestClient(app).post("/api/v1/public/seller-leads", json=payload)

    assert response.status_code == 201
    conversion_event = db_session.scalar(select(ConversionEvent))
    assert conversion_event is not None
    assert conversion_event.fbclid == "valid-click-with-bad-clock"
    assert conversion_event.fbclid_captured_at is None


def test_public_conversion_event_endpoint_records_form_abandonment(
    db_session: Session,
    api_db_override: None,
) -> None:
    seed_org(db_session)
    client = TestClient(app)

    response = client.post(
        "/api/v1/public/conversion-events",
        json={
            "event_type": "form_abandon",
            "session_id": "session-abandoned",
            "metadata": {"form": "cash_offer"},
            "attribution": {
                "landing_page": "/get-a-cash-offer",
                "utm_source": "google_ppc",
                "utm_medium": "cpc",
            },
        },
    )

    assert response.status_code == 201
    event = db_session.scalar(select(ConversionEvent))
    assert event is not None
    assert event.event_type == "form_abandon"
    assert event.session_id == "session-abandoned"
    assert event.source == "google_ppc"


def test_public_seller_intake_requires_consent(
    db_session: Session,
    api_db_override: None,
) -> None:
    seed_org(db_session)
    client = TestClient(app)
    payload = public_payload()
    payload["consent_to_contact"] = False

    response = client.post("/api/v1/public/seller-leads", json=payload)

    assert response.status_code == 422
    assert int(db_session.scalar(select(func.count()).select_from(Lead)) or 0) == 0


@pytest.mark.parametrize("phone_value", [None, "", "   "])
def test_public_seller_intake_requires_phone_even_with_email(
    db_session: Session,
    api_db_override: None,
    phone_value: str | None,
) -> None:
    seed_org(db_session)
    client = TestClient(app)
    payload = public_payload()
    payload["phone"] = phone_value
    payload["preferred_contact_method"] = "email"

    response = client.post("/api/v1/public/seller-leads", json=payload)

    assert response.status_code == 422
    assert "phone number is required" in str(response.json())
    assert int(db_session.scalar(select(func.count()).select_from(Lead)) or 0) == 0


@pytest.mark.parametrize("phone_value", ["not-a-number", "404555121", "1" * 16])
def test_public_seller_intake_rejects_incomplete_phone_numbers(
    db_session: Session,
    api_db_override: None,
    phone_value: str,
) -> None:
    seed_org(db_session)
    client = TestClient(app)
    payload = public_payload()
    payload["phone"] = phone_value

    response = client.post("/api/v1/public/seller-leads", json=payload)

    assert response.status_code == 422
    assert "Enter a complete phone number" in str(response.json())
    assert int(db_session.scalar(select(func.count()).select_from(Lead)) or 0) == 0


def test_public_seller_intake_does_not_grant_sms_without_separate_opt_in(
    db_session: Session,
    api_db_override: None,
) -> None:
    seed_org(db_session)
    client = TestClient(app)
    payload = public_payload()
    payload["sms_consent"] = False

    response = client.post("/api/v1/public/seller-leads", json=payload)

    assert response.status_code == 201
    consents = db_session.scalars(select(ConsentRecord)).all()
    assert {consent.channel for consent in consents} == {"email", "phone"}


def test_public_seller_intake_preserves_explicit_api_sms_opt_in(
    db_session: Session,
    api_db_override: None,
) -> None:
    seed_org(db_session)
    client = TestClient(app)
    payload = public_payload()
    payload["preferred_contact_method"] = "sms"
    payload["sms_consent"] = True

    response = client.post("/api/v1/public/seller-leads", json=payload)

    assert response.status_code == 201
    consents = db_session.scalars(select(ConsentRecord).order_by(ConsentRecord.channel)).all()
    assert {consent.channel for consent in consents} == {"email", "phone", "sms"}
    sms_consent = next(consent for consent in consents if consent.channel == "sms")
    assert sms_consent.wording_version == "seller-sms-web-v3"
    assert sms_consent.normalized_address == "+14045551212"
    assert sms_consent.wording == (
        "By checking this optional box, I agree to receive recurring automated text messages "
        "from Stonegate Home Buyers about my property inquiry, appointments, and possible "
        "selling options at the number provided. Message frequency varies. Message and data "
        "rates may apply. Reply STOP to opt out or HELP for help. Consent is not a condition of "
        "purchase. See our Terms & Conditions and Privacy Policy."
    )


def test_public_seller_intake_rejects_sms_opt_in_for_an_invalid_phone(
    db_session: Session,
    api_db_override: None,
) -> None:
    seed_org(db_session)
    payload = public_payload()
    payload["phone"] = "not-a-phone"
    payload["sms_consent"] = True

    response = TestClient(app).post("/api/v1/public/seller-leads", json=payload)

    assert response.status_code == 422
    assert "valid phone number" in response.text
    assert db_session.scalar(select(func.count()).select_from(ConsentRecord)) == 0


def test_public_seller_intake_requires_sms_opt_in_when_text_is_preferred(
    db_session: Session,
    api_db_override: None,
) -> None:
    seed_org(db_session)
    client = TestClient(app)
    payload = public_payload()
    payload["preferred_contact_method"] = "sms"
    payload["sms_consent"] = False

    response = client.post("/api/v1/public/seller-leads", json=payload)

    assert response.status_code == 422
    assert "Text message consent is required" in str(response.json())
    assert int(db_session.scalar(select(func.count()).select_from(Lead)) or 0) == 0


def test_public_seller_intake_requires_selected_contact_channel(
    db_session: Session,
    api_db_override: None,
) -> None:
    seed_org(db_session)
    client = TestClient(app)
    payload = public_payload()
    payload["preferred_contact_method"] = "email"
    payload["email"] = None

    response = client.post("/api/v1/public/seller-leads", json=payload)

    assert response.status_code == 422
    assert "email address is required" in str(response.json())
    assert int(db_session.scalar(select(func.count()).select_from(Lead)) or 0) == 0


def test_public_seller_intake_rejects_populated_honeypot_field(
    db_session: Session,
    api_db_override: None,
) -> None:
    seed_org(db_session)
    client = TestClient(app)
    payload = public_payload()
    payload["company_website"] = "https://spam.example"

    response = client.post("/api/v1/public/seller-leads", json=payload)

    assert response.status_code == 422
    assert int(db_session.scalar(select(func.count()).select_from(Lead)) or 0) == 0


def test_public_seller_intake_matches_duplicate_active_lead(
    db_session: Session,
    api_db_override: None,
) -> None:
    seed_org(db_session)
    client = TestClient(app)

    first_response = client.post("/api/v1/public/seller-leads", json=public_payload())
    second_payload = public_payload()
    second_payload["name"] = "Sam Seller Updated"
    second_payload["phone"] = "(404) 555-1212"
    second_response = client.post("/api/v1/public/seller-leads", json=second_payload)

    assert first_response.status_code == 201
    assert second_response.status_code == 201
    first = first_response.json()
    second = second_response.json()
    assert second["duplicate_status"] == "matched_existing_lead"
    assert second["matched_existing_lead"] is True
    assert second["message"] == "Thanks. We received your updated property information."
    assert second["lead_id"] == first["lead_id"]
    assert second["contact_id"] == first["contact_id"]
    assert second["property_id"] == first["property_id"]
    assert int(db_session.scalar(select(func.count()).select_from(Contact)) or 0) == 1
    assert int(db_session.scalar(select(func.count()).select_from(Property)) or 0) == 1
    assert int(db_session.scalar(select(func.count()).select_from(Lead)) or 0) == 1
    assert int(db_session.scalar(select(func.count()).select_from(Task)) or 0) == 1
    assert int(db_session.scalar(select(func.count()).select_from(ConsentRecord)) or 0) == 4
    assert int(db_session.scalar(select(func.count()).select_from(LeadFormSubmission)) or 0) == 2
    assert int(db_session.scalar(select(func.count()).select_from(AttributionTouch)) or 0) == 2
    assert int(db_session.scalar(select(func.count()).select_from(ConversionEvent)) or 0) == 2


def test_duplicate_public_intake_fills_missing_context_without_overwriting_reviewed_values(
    db_session: Session,
    api_db_override: None,
) -> None:
    seed_org(db_session)
    client = TestClient(app)
    initial = public_payload()
    initial["property_type"] = None
    initial["property_condition"] = None
    initial["occupancy_status"] = None
    initial["mortgage_balance"] = None
    first_response = client.post("/api/v1/public/seller-leads", json=initial)
    assert first_response.status_code == 201

    lead = db_session.scalar(select(Lead))
    property_record = db_session.scalar(select(Property))
    assert lead is not None
    assert property_record is not None
    lead.motivation = "staff_reviewed_motivation"
    db_session.commit()

    updated = public_payload()
    updated["reason_for_selling"] = "seller_updated_motivation"
    second_response = client.post("/api/v1/public/seller-leads", json=updated)

    assert second_response.status_code == 201
    assert second_response.json()["matched_existing_lead"] is True
    db_session.refresh(lead)
    db_session.refresh(property_record)
    assert lead.motivation == "staff_reviewed_motivation"
    assert lead.property_condition == "major_repairs"
    assert lead.occupancy_status == "vacant"
    assert lead.mortgage_balance == "90000"
    assert property_record.property_type == "single_family"


def test_speed_to_lead_queue_and_completion(
    db_session: Session,
    api_db_override: None,
) -> None:
    seed_org(db_session)
    client = TestClient(app)
    intake_response = client.post("/api/v1/public/seller-leads", json=public_payload())
    assert intake_response.status_code == 201

    queue_response = client.get(
        "/api/v1/tasks/speed-to-lead",
        headers={"X-Dev-User-Email": "owner@example.com"},
    )

    assert queue_response.status_code == 200
    queue = queue_response.json()["items"]
    assert len(queue) == 1
    assert queue[0]["seller_name"] == "Sam Seller"
    assert queue[0]["source"] == "google_ppc"
    assert queue[0]["due_status"] in {"due", "overdue"}

    complete_response = client.patch(
        f"/api/v1/tasks/{queue[0]['task_id']}/complete",
        headers={"X-Dev-User-Email": "owner@example.com"},
        json={
            "outcome": "seller_contacted",
            "completion_notes": "Seller contacted by phone.",
            "successor": {
                "title": "Complete seller qualification",
                "task_type": "qualification",
                "due_at": "2026-07-17T14:00:00Z",
                "priority": "high",
            },
        },
    )

    assert complete_response.status_code == 200
    assert complete_response.json()["status"] == "completed"
    assert complete_response.json()["successor_task_id"] is not None
    assert (
        int(
            db_session.scalar(
                select(func.count())
                .select_from(AuditEvent)
                .where(AuditEvent.action == "task.complete")
            )
            or 0
        )
        == 1
    )
    assert (
        int(
            db_session.scalar(
                select(func.count())
                .select_from(ActivityEvent)
                .where(ActivityEvent.event_type == "task.completed")
            )
            or 0
        )
        == 1
    )

    completed_queue_response = client.get(
        "/api/v1/tasks/speed-to-lead",
        headers={"X-Dev-User-Email": "owner@example.com"},
    )
    assert completed_queue_response.status_code == 200
    assert completed_queue_response.json()["items"] == []
