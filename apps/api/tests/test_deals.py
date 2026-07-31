from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.main import app
from app.models.foundation import Role, RoleAssignment, User
from app.services.bootstrap import bootstrap_foundation

OWNER_EMAIL = "owner@example.com"
HEADERS = {"X-Dev-User-Email": OWNER_EMAIL}


def create_transaction(client: TestClient) -> tuple[str, str]:
    lead = client.post(
        "/api/v1/leads",
        headers=HEADERS,
        json={
            "contact": {"legal_name": "Unified Deal Seller", "contact_type": "seller"},
            "property": {
                "street_address": "18 Deal Center Way",
                "city": "Atlanta",
                "state": "GA",
                "postal_code": "30303",
                "property_type": "single_family",
            },
            "source": "referral",
            "stage_key": "offer_ready",
        },
    )
    transaction = client.post(
        f"/api/v1/leads/{lead.json()['id']}/transactions",
        headers=HEADERS,
        json={
            "purchase_price_cents": 17500000,
            "assignment_fee_cents": 2500000,
            "closing_date": "2026-08-28T21:00:00Z",
        },
    )
    detail = transaction.json()["transactions"][0]
    return detail["deal_id"], detail["id"]


def test_unified_deal_overview_and_detail(
    db_session: Session,
    api_db_override: None,
) -> None:
    bootstrap_foundation(
        db_session,
        organization_name="Stonegate Home Buyers",
        admin_email=OWNER_EMAIL,
        admin_name="Owner",
    )
    client = TestClient(app)
    deal_id, transaction_id = create_transaction(client)

    overview = client.get("/api/v1/deals", headers=HEADERS)
    assert overview.status_code == 200
    payload = overview.json()
    assert payload["can_view_economics"] is True
    assert payload["metrics"]["active"] == 1
    assert len(payload["items"]) == 1
    item = payload["items"][0]
    assert item["id"] == deal_id
    assert item["transaction_id"] == transaction_id
    assert item["seller_name"] == "Unified Deal Seller"
    assert item["contract_status"] == "preparing"
    assert item["closing_status"] == "waiting_for_contract"
    assert item["disposition_status"] == "waiting_for_contract"
    assert item["finance_status"] == "waiting_for_outcome"
    assert item["contract_price_cents"] == 17500000
    assert item["assignment_fee_cents"] == 2500000
    assert {blocker["domain"] for blocker in item["blockers"]} == {"contract"}

    detail = client.get(f"/api/v1/deals/{deal_id}", headers=HEADERS)
    assert detail.status_code == 200
    assert detail.json()["id"] == deal_id
    assert detail.json()["can_view_economics"] is True


def test_unified_deal_is_organization_scoped(
    db_session: Session,
    api_db_override: None,
) -> None:
    bootstrap_foundation(
        db_session,
        organization_name="Stonegate Home Buyers",
        admin_email=OWNER_EMAIL,
        admin_name="Owner",
    )
    client = TestClient(app)
    response = client.get(
        "/api/v1/deals/00000000-0000-0000-0000-000000000001",
        headers=HEADERS,
    )
    assert response.status_code == 404


def test_unified_deal_redacts_restricted_economics(
    db_session: Session,
    api_db_override: None,
) -> None:
    bootstrap_foundation(
        db_session,
        organization_name="Stonegate Home Buyers",
        admin_email=OWNER_EMAIL,
        admin_name="Owner",
    )
    client = TestClient(app)
    create_transaction(client)
    owner = db_session.scalar(select(User).where(User.email == OWNER_EMAIL))
    assert owner is not None
    role = db_session.scalar(
        select(Role).where(
            Role.organization_id == owner.organization_id,
            Role.key == "read_only_partner",
        )
    )
    assert role is not None
    viewer = User(
        organization_id=owner.organization_id,
        email="viewer@example.com",
        display_name="Read Only Viewer",
        external_auth_id=None,
        is_active=True,
        calling_enabled=False,
    )
    db_session.add(viewer)
    db_session.flush()
    db_session.add(
        RoleAssignment(
            organization_id=owner.organization_id,
            user_id=viewer.id,
            role_id=role.id,
        )
    )
    db_session.commit()

    response = client.get(
        "/api/v1/deals",
        headers={"X-Dev-User-Email": viewer.email},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["can_view_economics"] is False
    assert payload["items"][0]["contract_price_cents"] == 17500000
    assert payload["items"][0]["assignment_fee_cents"] is None
    assert payload["items"][0]["company_profit_cents"] is None
    assert payload["items"][0]["company_margin_basis_points"] is None
