from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.main import app
from app.models.foundation import AuditEvent, OfflineConversionExport
from app.services.bootstrap import bootstrap_foundation

OWNER_EMAIL = "owner@example.com"


def seed_owner(db_session: Session) -> None:
    bootstrap_foundation(
        db_session,
        organization_name="Oakwell Home Buyers",
        admin_email=OWNER_EMAIL,
        admin_name="Owner",
    )


def test_marketing_overview_and_offline_export_generation(
    db_session: Session,
    api_db_override: None,
) -> None:
    seed_owner(db_session)
    client = TestClient(app)
    intake_response = client.post(
        "/api/v1/public/seller-leads",
        json={
            "property_address": "123 Peachtree St",
            "property_city": "Atlanta",
            "property_state": "GA",
            "property_postal_code": "30303",
            "name": "Jane Seller",
            "phone": "4045551212",
            "preferred_contact_method": "phone",
            "consent_to_contact": True,
            "attribution": {
                "landing_page": "/get-a-cash-offer",
                "utm_source": "google_ppc",
                "utm_medium": "cpc",
                "utm_campaign": "atlanta-cash-offer",
                "gclid": "test-gclid-123",
            },
        },
    )
    lead_id = intake_response.json()["lead_id"]
    spend_response = client.post(
        "/api/v1/finance/marketing-spend",
        headers={"X-Dev-User-Email": OWNER_EMAIL},
        json={
            "source": "google_ppc",
            "campaign": "atlanta-cash-offer",
            "amount_cents": 500000,
        },
    )
    revenue_response = client.post(
        "/api/v1/finance/revenue",
        headers={"X-Dev-User-Email": OWNER_EMAIL},
        json={
            "lead_id": lead_id,
            "source": "assignment_fee",
            "status": "collected",
            "amount_cents": 2500000,
        },
    )

    overview_response = client.get(
        "/api/v1/marketing",
        headers={"X-Dev-User-Email": OWNER_EMAIL},
    )
    generate_response = client.post(
        "/api/v1/marketing/offline-conversions/generate",
        headers={"X-Dev-User-Email": OWNER_EMAIL},
    )
    duplicate_generate_response = client.post(
        "/api/v1/marketing/offline-conversions/generate",
        headers={"X-Dev-User-Email": OWNER_EMAIL},
    )
    updated_overview_response = client.get(
        "/api/v1/marketing",
        headers={"X-Dev-User-Email": OWNER_EMAIL},
    )

    assert intake_response.status_code == 201
    assert spend_response.status_code == 201
    assert revenue_response.status_code == 201
    assert overview_response.status_code == 200
    overview = overview_response.json()
    google_row = next(row for row in overview["campaigns"] if row["source"] == "google_ppc")
    assert google_row["leads_created"] == 1
    assert google_row["form_submits"] == 1
    assert google_row["collected_revenue_cents"] == 2500000
    assert generate_response.status_code == 201
    assert generate_response.json() == {"created": 1}
    assert duplicate_generate_response.status_code == 201
    assert duplicate_generate_response.json() == {"created": 0}
    assert updated_overview_response.json()["summary"]["pending_offline_exports"] == 1
    assert int(
        db_session.scalar(select(func.count()).select_from(OfflineConversionExport)) or 0
    ) == 1
    export = db_session.scalar(select(OfflineConversionExport))
    assert export is not None
    assert export.platform == "google_ads"
    assert export.click_id == "test-gclid-123"
    assert export.value_cents == 2500000
    assert int(
        db_session.scalar(
            select(func.count()).select_from(AuditEvent).where(
                AuditEvent.action == "marketing.offline_exports_generate"
            )
        )
        or 0
    ) == 1
