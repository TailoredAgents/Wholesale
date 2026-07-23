from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.main import app
from app.services.bootstrap import bootstrap_foundation

OWNER_EMAIL = "owner@example.com"
HEADERS = {"X-Dev-User-Email": OWNER_EMAIL}


def setup_transaction(db: Session, client: TestClient) -> tuple[str, str]:
    bootstrap_foundation(
        db, organization_name="Stonegate Home Buyers", admin_email=OWNER_EMAIL, admin_name="Owner"
    )
    lead = client.post(
        "/api/v1/leads",
        headers=HEADERS,
        json={
            "contact": {"legal_name": "Jane Seller", "contact_type": "seller"},
            "property": {
                "street_address": "123 Peachtree St",
                "city": "Atlanta",
                "state": "GA",
                "postal_code": "30303",
                "property_type": "single_family",
            },
            "source": "referral",
            "stage_key": "offer_ready",
        },
    )
    transaction_response = client.post(
        f"/api/v1/leads/{lead.json()['id']}/transactions",
        headers=HEADERS,
        json={
            "purchase_price_cents": 17000000,
            "earnest_money_cents": 100000,
            "closing_date": "2026-08-14T21:00:00Z",
            "inspection_period_days": 7,
        },
    )
    return lead.json()["id"], transaction_response.json()["transactions"][0]["id"]


def test_contract_approval_execution_and_funding_gates(
    db_session: Session, api_db_override: None
) -> None:
    client = TestClient(app)
    lead_id, transaction_id = setup_transaction(db_session, client)
    overview = client.get("/api/v1/transactions", headers=HEADERS)
    assert overview.status_code == 200
    assert overview.json()["metrics"]["active"] == 1

    package_response = client.post(
        f"/api/v1/transactions/{transaction_id}/contract-packages",
        headers=HEADERS,
        json={
            "seller_name": "Jane Seller",
            "buyer_entity_name": "Stonegate Acquisitions LLC",
            "purchase_price_cents": 17000000,
            "earnest_money_cents": 100000,
            "closing_date": "2026-08-14T21:00:00Z",
            "inspection_period_days": 7,
        },
    )
    assert package_response.status_code == 201
    package_id = package_response.json()["id"]
    pending = client.post(
        f"/api/v1/transactions/{transaction_id}/contract-packages/{package_id}/request-approval",
        headers=HEADERS,
    )
    approval_id = pending.json()["approval_request_id"]
    approved = client.patch(
        f"/api/v1/approvals/{approval_id}/decision",
        headers=HEADERS,
        json={"status": "approved", "decision_notes": "Terms verified."},
    )
    assert approved.status_code == 200
    assert (
        client.post(
            f"/api/v1/transactions/{transaction_id}/contract-packages/{package_id}/mark-sent",
            headers=HEADERS,
        ).status_code
        == 200
    )

    missing_document = client.post(
        f"/api/v1/transactions/{transaction_id}/contract-packages/{package_id}/mark-executed?document_id=00000000-0000-0000-0000-000000000001",
        headers=HEADERS,
    )
    assert missing_document.status_code == 422
    signed = client.post(
        f"/api/v1/transactions/{transaction_id}/documents?file_name=signed.pdf&document_type=signed_purchase_agreement&title=Signed%20purchase%20agreement&document_status=executed&package_id={package_id}",
        headers={**HEADERS, "Content-Type": "application/pdf"},
        content=b"%PDF signed purchase agreement",
    )
    assert signed.status_code == 201
    executed = client.post(
        f"/api/v1/transactions/{transaction_id}/contract-packages/{package_id}/mark-executed?document_id={signed.json()['id']}",
        headers=HEADERS,
    )
    assert executed.status_code == 200
    assert (
        client.get(f"/api/v1/leads/{lead_id}", headers=HEADERS).json()["stage_key"]
        == "under_contract"
    )

    blocked = client.post(
        f"/api/v1/transactions/{transaction_id}/close",
        headers=HEADERS,
        json={"outcome": "funded", "notes": "Closing confirmed."},
    )
    assert blocked.status_code == 422
    detail = client.get(f"/api/v1/transactions/{transaction_id}", headers=HEADERS).json()
    for item in detail["checklist"]:
        response = client.patch(
            f"/api/v1/transactions/{transaction_id}/checklist/{item['id']}",
            headers=HEADERS,
            json={"status": "complete"},
        )
        assert response.status_code == 200
    funding = client.post(
        f"/api/v1/transactions/{transaction_id}/documents?file_name=funding.pdf&document_type=funding_confirmation&title=Funding%20confirmation&document_status=evidence",
        headers={**HEADERS, "Content-Type": "application/pdf"},
        content=b"%PDF funding confirmation",
    )
    closed = client.post(
        f"/api/v1/transactions/{transaction_id}/close",
        headers=HEADERS,
        json={"outcome": "funded", "notes": "Funds received by closing attorney."},
    )
    assert funding.status_code == 201
    assert closed.status_code == 200
    assert closed.json()["status"] == "funded"


def test_contract_template_requires_explicit_approval(
    db_session: Session, api_db_override: None
) -> None:
    client = TestClient(app)
    bootstrap_foundation(
        db_session,
        organization_name="Stonegate Home Buyers",
        admin_email=OWNER_EMAIL,
        admin_name="Owner",
    )
    created = client.post(
        "/api/v1/transactions/templates?file_name=ga-purchase.pdf&document_type=purchase_agreement&state_code=GA&name=Georgia%20Purchase%20Agreement",
        headers={**HEADERS, "Content-Type": "application/pdf"},
        content=b"%PDF attorney reviewed template",
    )
    assert created.status_code == 201
    assert created.json()["status"] == "draft"
    approved = client.post(
        f"/api/v1/transactions/templates/{created.json()['id']}/approve", headers=HEADERS
    )
    assert approved.status_code == 200
    assert approved.json()["status"] == "approved"


def test_transaction_document_facts_preserve_page_evidence_and_reject_duplicates(
    db_session: Session,
    api_db_override: None,
) -> None:
    client = TestClient(app)
    _, transaction_id = setup_transaction(db_session, client)
    path = (
        f"/api/v1/transactions/{transaction_id}/documents"
        "?file_name=contract.pdf"
        "&document_type=signed_purchase_agreement"
        "&title=Executed%20agreement"
        "&document_status=executed"
    )
    content = b"%PDF unique executed agreement"
    uploaded = client.post(
        path,
        headers={**HEADERS, "Content-Type": "application/pdf"},
        content=content,
    )
    assert uploaded.status_code == 201, uploaded.text
    duplicate = client.post(
        path,
        headers={**HEADERS, "Content-Type": "application/pdf"},
        content=content,
    )
    assert duplicate.status_code == 422
    assert "already stored" in duplicate.json()["detail"]

    fact = client.post(
        (
            f"/api/v1/transactions/{transaction_id}/documents/"
            f"{uploaded.json()['id']}/facts"
        ),
        headers=HEADERS,
        json={
            "field_key": "Closing Date",
            "value_text": "August 14, 2026",
            "source_page": 4,
            "source_excerpt": "Closing shall occur on August 14, 2026.",
        },
    )
    assert fact.status_code == 201, fact.text
    assert fact.json()["field_key"] == "closing_date"
    assert fact.json()["status"] == "confirmed"
    assert fact.json()["source_page"] == 4

    detail = client.get(
        f"/api/v1/transactions/{transaction_id}",
        headers=HEADERS,
    )
    stored_document = next(
        item
        for item in detail.json()["documents"]
        if item["id"] == uploaded.json()["id"]
    )
    assert stored_document["facts"][0]["value_text"] == "August 14, 2026"
    assert stored_document["facts"][0]["reviewed_by_name"] == "Owner"
