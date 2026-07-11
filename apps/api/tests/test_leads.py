from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.main import app
from app.models.foundation import ActivityEvent, AuditEvent
from app.services.bootstrap import bootstrap_foundation

OWNER_EMAIL = "owner@example.com"


def seed_owner(db_session: Session) -> None:
    bootstrap_foundation(
        db_session,
        organization_name="Georgia Wholesale Operating Company",
        admin_email=OWNER_EMAIL,
        admin_name="Owner",
    )


def lead_payload() -> dict[str, object]:
    return {
        "contact": {
            "legal_name": "Jane Seller",
            "preferred_name": "Jane",
            "contact_type": "seller",
        },
        "property": {
            "street_address": "123 Peachtree St",
            "city": "Atlanta",
            "state": "ga",
            "postal_code": "30303",
            "county": "Fulton",
            "property_type": "single_family",
        },
        "source": "google_ppc",
        "stage_key": "new",
        "lead_temperature": "hot",
    }


def test_create_and_list_lead(
    db_session: Session,
    api_db_override: None,
) -> None:
    seed_owner(db_session)
    client = TestClient(app)

    create_response = client.post(
        "/api/v1/leads",
        headers={"X-Dev-User-Email": OWNER_EMAIL},
        json=lead_payload(),
    )

    assert create_response.status_code == 201
    created = create_response.json()
    assert created["seller_name"] == "Jane Seller"
    assert created["property_address"] == "123 Peachtree St, Atlanta, GA 30303"
    assert created["source"] == "google_ppc"

    list_response = client.get("/api/v1/leads", headers={"X-Dev-User-Email": OWNER_EMAIL})

    assert list_response.status_code == 200
    items = list_response.json()["items"]
    assert len(items) == 1
    assert items[0]["id"] == created["id"]
    assert int(db_session.scalar(select(func.count()).select_from(ActivityEvent)) or 0) == 1
    assert int(
        db_session.scalar(
            select(func.count()).select_from(AuditEvent).where(AuditEvent.action == "lead.create")
        )
        or 0
    ) == 1


def test_dashboard_summary_counts_leads(
    db_session: Session,
    api_db_override: None,
) -> None:
    seed_owner(db_session)
    client = TestClient(app)
    client.post("/api/v1/leads", headers={"X-Dev-User-Email": OWNER_EMAIL}, json=lead_payload())

    response = client.get(
        "/api/v1/dashboard/summary",
        headers={"X-Dev-User-Email": OWNER_EMAIL},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["total_leads"] == 1
    assert payload["new_paid_leads"] == 1
    assert payload["offers_pending"] == 0
    assert payload["active_contracts"] == 0
    assert payload["pipeline"] == [{"stage_key": "new", "count": 1}]


def test_create_lead_requires_permission(api_db_override: None) -> None:
    client = TestClient(app)

    response = client.post("/api/v1/leads", json=lead_payload())

    assert response.status_code == 401
