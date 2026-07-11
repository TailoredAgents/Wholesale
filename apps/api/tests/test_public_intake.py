from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.main import app
from app.models.foundation import (
    AttributionTouch,
    ConsentRecord,
    Lead,
    LeadFormSubmission,
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
        organization_name="Georgia Wholesale Operating Company",
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
    assert int(db_session.scalar(select(func.count()).select_from(Lead)) or 0) == 1
    assert int(db_session.scalar(select(func.count()).select_from(ConsentRecord)) or 0) == 1
    assert int(db_session.scalar(select(func.count()).select_from(LeadFormSubmission)) or 0) == 1
    assert int(db_session.scalar(select(func.count()).select_from(AttributionTouch)) or 0) == 2

    consent = db_session.scalar(select(ConsentRecord))
    assert consent is not None
    assert consent.status == "granted"
    assert consent.captured_ip == "203.0.113.10"


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
