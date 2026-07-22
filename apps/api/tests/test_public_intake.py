from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.main import app
from app.models.foundation import (
    ActivityEvent,
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
    Property,
    Task,
)
from app.services.bootstrap import bootstrap_foundation


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
        "asking_price": "180000",
        "comments": "Needs repairs",
        "consent_to_contact": True,
        "sms_consent": True,
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
    assert payload["message"] == "Thanks. Your information was received."
    assert payload["duplicate_status"] == "created"
    assert payload["matched_existing_lead"] is False
    assert int(db_session.scalar(select(func.count()).select_from(Lead)) or 0) == 1
    assert int(db_session.scalar(select(func.count()).select_from(LeadManagementCase)) or 0) == 1
    assert int(db_session.scalar(select(func.count()).select_from(Task)) or 0) == 1
    assert int(db_session.scalar(select(func.count()).select_from(ContactMethod)) or 0) == 2
    assert int(db_session.scalar(select(func.count()).select_from(ConsentRecord)) or 0) == 3
    assert int(db_session.scalar(select(func.count()).select_from(LeadFormSubmission)) or 0) == 1
    assert int(db_session.scalar(select(func.count()).select_from(AttributionTouch)) or 0) == 2
    assert int(db_session.scalar(select(func.count()).select_from(ConversionEvent)) or 0) == 1

    consents = db_session.scalars(select(ConsentRecord).order_by(ConsentRecord.channel)).all()
    assert {consent.channel for consent in consents} == {"email", "phone", "sms"}
    assert all(consent.status == "granted" for consent in consents)
    assert all(consent.captured_ip == "203.0.113.10" for consent in consents)
    sms_consent = next(consent for consent in consents if consent.channel == "sms")
    assert sms_consent.wording_version == "seller-sms-web-v2"
    assert "Reply STOP to opt out or HELP for help." in sms_consent.wording
    property_record = db_session.scalar(select(Property))
    assert property_record is not None
    assert property_record.normalized_address_key == "55 auburn ave|atlanta|GA|30303"
    lead = db_session.scalar(select(Lead))
    assert lead is not None
    assert lead.motivation == "Inherited property"
    assert lead.desired_timeline == "30 days"
    assert lead.asking_price == "180000"
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
    assert event.ip_address == "203.0.113.11"
    assert event.source == "meta_ads"
    assert event.medium == "paid_social"
    assert event.event_metadata == {"field": "property_address"}


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


def test_public_seller_intake_allows_autofilled_honeypot_field(
    db_session: Session,
    api_db_override: None,
) -> None:
    seed_org(db_session)
    client = TestClient(app)
    payload = public_payload()
    payload["company_website"] = "https://spam.example"

    response = client.post("/api/v1/public/seller-leads", json=payload)

    assert response.status_code == 201
    assert int(db_session.scalar(select(func.count()).select_from(Lead)) or 0) == 1


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
    assert second["lead_id"] == first["lead_id"]
    assert second["contact_id"] == first["contact_id"]
    assert second["property_id"] == first["property_id"]
    assert int(db_session.scalar(select(func.count()).select_from(Contact)) or 0) == 1
    assert int(db_session.scalar(select(func.count()).select_from(Property)) or 0) == 1
    assert int(db_session.scalar(select(func.count()).select_from(Lead)) or 0) == 1
    assert int(db_session.scalar(select(func.count()).select_from(Task)) or 0) == 1
    assert int(db_session.scalar(select(func.count()).select_from(ConsentRecord)) or 0) == 6
    assert int(db_session.scalar(select(func.count()).select_from(LeadFormSubmission)) or 0) == 2
    assert int(db_session.scalar(select(func.count()).select_from(AttributionTouch)) or 0) == 4
    assert int(db_session.scalar(select(func.count()).select_from(ConversionEvent)) or 0) == 2


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
        json={"reason": "Seller contacted by phone."},
    )

    assert complete_response.status_code == 200
    assert complete_response.json()["status"] == "completed"
    assert int(
        db_session.scalar(
            select(func.count()).select_from(AuditEvent).where(AuditEvent.action == "task.complete")
        )
        or 0
    ) == 1
    assert int(
        db_session.scalar(
            select(func.count()).select_from(ActivityEvent).where(
                ActivityEvent.event_type == "task.completed"
            )
        )
        or 0
    ) == 1

    completed_queue_response = client.get(
        "/api/v1/tasks/speed-to-lead",
        headers={"X-Dev-User-Email": "owner@example.com"},
    )
    assert completed_queue_response.status_code == 200
    assert completed_queue_response.json()["items"] == []
