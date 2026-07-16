from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.main import app
from app.models.foundation import (
    AuditEvent,
    CompensationCalculation,
    CompensationRule,
    DealDeduction,
    MarketingSpend,
    RevenueRecord,
)
from app.services.bootstrap import bootstrap_foundation

OWNER_EMAIL = "owner@example.com"


def seed_owner(db_session: Session) -> None:
    bootstrap_foundation(
        db_session,
        organization_name="Stonegate Home Buyers",
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
    }


def create_contract_lead(client: TestClient) -> str:
    created_response = client.post(
        "/api/v1/leads",
        headers={"X-Dev-User-Email": OWNER_EMAIL},
        json=lead_payload(),
    )
    lead_id = created_response.json()["id"]
    transaction_response = client.post(
        f"/api/v1/leads/{lead_id}/transactions",
        headers={"X-Dev-User-Email": OWNER_EMAIL},
        json={
            "contract_type": "purchase_agreement",
            "purchase_price_cents": 17000000,
            "assignment_fee_cents": 2500000,
        },
    )

    assert created_response.status_code == 201
    assert transaction_response.status_code == 201
    return str(lead_id)


def test_finance_records_revenue_deductions_compensation_and_spend(
    db_session: Session,
    api_db_override: None,
) -> None:
    seed_owner(db_session)
    client = TestClient(app)
    lead_id = create_contract_lead(client)

    deduction_response = client.post(
        "/api/v1/finance/deductions",
        headers={"X-Dev-User-Email": OWNER_EMAIL},
        json={
            "lead_id": lead_id,
            "category": "title",
            "amount_cents": 300000,
            "notes": "Closing attorney fee.",
        },
    )
    rule_response = client.post(
        "/api/v1/finance/compensation-rules",
        headers={"X-Dev-User-Email": OWNER_EMAIL},
        json={
            "name": "Disposition rep split",
            "role_key": "disposition_rep",
            "basis_points": 1000,
            "applies_to": "net_revenue",
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
            "notes": "Assignment fee collected at closing.",
        },
    )
    spend_response = client.post(
        "/api/v1/finance/marketing-spend",
        headers={"X-Dev-User-Email": OWNER_EMAIL},
        json={
            "source": "google_ppc",
            "campaign": "atlanta-cash-offer",
            "amount_cents": 500000,
        },
    )

    assert deduction_response.status_code == 201
    assert rule_response.status_code == 201
    assert revenue_response.status_code == 201
    assert spend_response.status_code == 201
    assert revenue_response.json()["seller_name"] == "Jane Seller"
    assert int(db_session.scalar(select(func.count()).select_from(RevenueRecord)) or 0) == 1
    assert int(db_session.scalar(select(func.count()).select_from(DealDeduction)) or 0) == 1
    assert int(db_session.scalar(select(func.count()).select_from(CompensationRule)) or 0) == 1
    assert int(
        db_session.scalar(select(func.count()).select_from(CompensationCalculation)) or 0
    ) == 1
    assert int(db_session.scalar(select(func.count()).select_from(MarketingSpend)) or 0) == 1

    overview_response = client.get(
        "/api/v1/finance",
        headers={"X-Dev-User-Email": OWNER_EMAIL},
    )

    assert overview_response.status_code == 200
    overview = overview_response.json()
    assert overview["summary"] == {
        "collected_revenue_cents": 2500000,
        "pending_revenue_cents": 0,
        "deductions_cents": 300000,
        "net_revenue_cents": 2200000,
        "compensation_cents": 220000,
        "marketing_spend_cents": 500000,
        "company_net_cents": 1480000,
    }
    assert overview["compensation_calculations"][0]["basis_amount_cents"] == 2200000
    assert overview["compensation_calculations"][0]["calculated_amount_cents"] == 220000
    assert int(
        db_session.scalar(
            select(func.count()).select_from(AuditEvent).where(
                AuditEvent.action.in_(
                    [
                        "finance.deduction_create",
                        "finance.compensation_rule_create",
                        "finance.revenue_create",
                        "finance.marketing_spend_create",
                    ]
                )
            )
        )
        or 0
    ) == 4


def test_finance_rejects_invalid_revenue_status(
    db_session: Session,
    api_db_override: None,
) -> None:
    seed_owner(db_session)
    client = TestClient(app)

    response = client.post(
        "/api/v1/finance/revenue",
        headers={"X-Dev-User-Email": OWNER_EMAIL},
        json={
            "source": "assignment_fee",
            "status": "not_real",
            "amount_cents": 2500000,
        },
    )

    assert response.status_code == 422
