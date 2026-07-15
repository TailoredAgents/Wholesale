from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.main import app
from app.models.foundation import AuditEvent, Buyer, BuyerCriteria
from app.services.bootstrap import bootstrap_foundation

OWNER_EMAIL = "owner@example.com"


def seed_owner(db_session: Session) -> None:
    bootstrap_foundation(
        db_session,
        organization_name="Oakwell Home Buyers",
        admin_email=OWNER_EMAIL,
        admin_name="Owner",
    )


def test_create_and_list_buyer_with_criteria(
    db_session: Session,
    api_db_override: None,
) -> None:
    seed_owner(db_session)
    client = TestClient(app)

    create_response = client.post(
        "/api/v1/buyers",
        headers={"X-Dev-User-Email": OWNER_EMAIL},
        json={
            "name": "Acme Cash Buyer",
            "company_name": "Acme Homes",
            "email": "buyer@example.com",
            "phone": "(404) 555-0199",
            "buyer_type": "cash_buyer",
            "status": "active",
            "proof_of_funds_status": "received",
            "max_purchase_price_cents": 35000000,
            "notes": "Prefers light rehab in Atlanta.",
            "criteria": {
                "markets": "Atlanta, Decatur",
                "property_types": "single_family, duplex",
                "min_price_cents": 10000000,
                "max_price_cents": 35000000,
                "rehab_levels": "light, medium",
                "notes": "Avoid foundation issues.",
            },
        },
    )

    assert create_response.status_code == 201
    created = create_response.json()
    assert created["name"] == "Acme Cash Buyer"
    assert created["criteria"]["markets"] == "Atlanta, Decatur"
    assert created["proof_of_funds_status"] == "received"
    assert int(db_session.scalar(select(func.count()).select_from(Buyer)) or 0) == 1
    assert int(db_session.scalar(select(func.count()).select_from(BuyerCriteria)) or 0) == 1
    assert int(
        db_session.scalar(
            select(func.count()).select_from(AuditEvent).where(AuditEvent.action == "buyer.create")
        )
        or 0
    ) == 1

    list_response = client.get("/api/v1/buyers", headers={"X-Dev-User-Email": OWNER_EMAIL})

    assert list_response.status_code == 200
    items = list_response.json()["items"]
    assert len(items) == 1
    assert items[0]["id"] == created["id"]


def test_create_buyer_rejects_invalid_type(
    db_session: Session,
    api_db_override: None,
) -> None:
    seed_owner(db_session)
    client = TestClient(app)

    response = client.post(
        "/api/v1/buyers",
        headers={"X-Dev-User-Email": OWNER_EMAIL},
        json={"name": "Unsupported Buyer", "buyer_type": "not_real"},
    )

    assert response.status_code == 422
