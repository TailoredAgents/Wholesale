from uuid import UUID

from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.main import app
from app.models.foundation import (
    AuditEvent,
    BusinessCounterparty,
    FinanceDocument,
    FinancialObligation,
    VendorBill,
    VendorBillLine,
    VendorProfile,
)
from app.services.bootstrap import bootstrap_foundation

OWNER_EMAIL = "owner@example.com"
HEADERS = {"X-Dev-User-Email": OWNER_EMAIL}


def seed_owner(db_session: Session) -> None:
    bootstrap_foundation(
        db_session,
        organization_name="Stonegate Home Buyers",
        admin_email=OWNER_EMAIL,
        admin_name="Owner",
    )


def approve_posting_rule(client: TestClient, rule_key: str) -> None:
    workspace = client.get(
        "/api/v1/finance/accounting/operations",
        headers=HEADERS,
    ).json()
    rule = next(item for item in workspace["rules"] if item["rule_key"] == rule_key)
    response = client.post(
        f"/api/v1/finance/accounting/posting-rules/{rule['id']}/approve",
        headers=HEADERS,
        json={},
    )
    assert response.status_code == 200


def upload_document(
    client: TestClient,
    *,
    document_type: str,
    title: str,
    vendor_profile_id: str,
    vendor_bill_id: str | None = None,
) -> dict[str, object]:
    params = {
        "file_name": f"{document_type}.pdf",
        "document_type": document_type,
        "title": title,
        "vendor_profile_id": vendor_profile_id,
    }
    if vendor_bill_id:
        params["vendor_bill_id"] = vendor_bill_id
    response = client.post(
        "/api/v1/finance/documents",
        headers={**HEADERS, "Content-Type": "application/pdf"},
        params=params,
        content=f"%PDF-1.4 {document_type} evidence".encode(),
    )
    assert response.status_code == 201
    return response.json()


def test_vendor_bill_evidence_and_itemized_posting_use_one_finance_trail(
    db_session: Session,
    api_db_override: None,
) -> None:
    seed_owner(db_session)
    client = TestClient(app)
    approve_posting_rule(client, "obligation_accrued")
    approve_posting_rule(client, "obligation_paid")

    vendor = client.post(
        "/api/v1/finance/vendors",
        headers=HEADERS,
        json={
            "name": "Atlanta Outreach LLC",
            "company_name": "Atlanta Outreach LLC",
            "email": "billing@example.com",
            "vendor_type": "contractor",
            "default_expense_account_key": "prospecting_labor",
            "payment_terms_days": 14,
            "tax_reportable": True,
            "w9_status": "requested",
            "notes": "Cold outreach contractor.",
        },
    )
    assert vendor.status_code == 201
    vendor_id = vendor.json()["id"]
    assert vendor.json()["w9_status"] == "requested"
    assert db_session.scalar(select(func.count()).select_from(BusinessCounterparty)) == 1
    assert db_session.scalar(select(func.count()).select_from(VendorProfile)) == 1

    w9 = upload_document(
        client,
        document_type="w9",
        title="2026 W-9",
        vendor_profile_id=vendor_id,
    )
    workspace_after_w9 = client.get(
        "/api/v1/finance/vendor-accounting",
        headers=HEADERS,
    ).json()
    assert workspace_after_w9["vendors"][0]["w9_status"] == "received"
    verified = client.post(
        f"/api/v1/finance/vendors/{vendor_id}/w9-status",
        headers=HEADERS,
        json={"status": "verified", "notes": "Name and signature reviewed."},
    )
    assert verified.status_code == 200
    assert verified.json()["w9_status"] == "verified"

    bill = client.post(
        "/api/v1/finance/vendor-bills",
        headers=HEADERS,
        json={
            "vendor_profile_id": vendor_id,
            "bill_number": "AO-2026-07",
            "description": "July outreach and calling software.",
            "lines": [
                {
                    "description": "Contract calling labor",
                    "amount_cents": 60000,
                    "expense_account_key": "prospecting_labor",
                },
                {
                    "description": "Calling platform reimbursement",
                    "amount_cents": 4000,
                    "expense_account_key": "communications",
                },
            ],
        },
    )
    assert bill.status_code == 201
    bill_id = bill.json()["id"]
    assert bill.json()["amount_cents"] == 64000
    assert len(bill.json()["lines"]) == 2
    duplicate_bill = client.post(
        "/api/v1/finance/vendor-bills",
        headers=HEADERS,
        json={
            "vendor_profile_id": vendor_id,
            "bill_number": "AO-2026-07",
            "description": "Duplicate invoice attempt.",
            "lines": [
                {
                    "description": "Duplicate labor",
                    "amount_cents": 60000,
                    "expense_account_key": "prospecting_labor",
                }
            ],
        },
    )
    assert duplicate_bill.status_code == 422
    assert duplicate_bill.json()["detail"] == "This vendor bill number is already recorded."

    invoice = upload_document(
        client,
        document_type="invoice",
        title="July contractor invoice",
        vendor_profile_id=vendor_id,
        vendor_bill_id=bill_id,
    )
    approved = client.post(
        f"/api/v1/finance/vendor-bills/{bill_id}/approve",
        headers=HEADERS,
        json={},
    )
    assert approved.status_code == 200
    assert approved.json()["status"] == "approved"
    obligation_id = approved.json()["financial_obligation_id"]
    assert obligation_id
    obligation = db_session.get(FinancialObligation, UUID(obligation_id))
    assert obligation is not None
    assert obligation.source_type == "vendor_bill"
    assert obligation.source_id == bill_id
    assert f"finance_document:{invoice['id']}" in obligation.evidence_references

    accounting = client.get(
        "/api/v1/finance/accounting/operations",
        headers=HEADERS,
    ).json()
    source = next(
        item
        for item in accounting["source_items"]
        if item["source_type"] == "financial_obligation"
        and item["source_id"] == obligation_id
        and item["posting_purpose"] == "accrued"
    )
    assert source["readiness"] == "ready"
    journal = client.post(
        "/api/v1/finance/accounting/operations/draft",
        headers=HEADERS,
        json={
            "source_type": source["source_type"],
            "source_id": source["source_id"],
            "posting_purpose": source["posting_purpose"],
        },
    )
    assert journal.status_code == 201
    assert journal.json()["total_debits_cents"] == 64000
    assert journal.json()["total_credits_cents"] == 64000
    assert {line["account_name"] for line in journal.json()["lines"]} == {
        "VA and Prospecting Labor",
        "Telephone and Communications",
        "Contractor Payable",
    }

    payable = client.post(
        f"/api/v1/finance/accounting/obligations/{obligation_id}/status",
        headers=HEADERS,
        json={"status": "payable"},
    )
    assert payable.status_code == 200
    payment = upload_document(
        client,
        document_type="payment_evidence",
        title="ACH payment confirmation",
        vendor_profile_id=vendor_id,
        vendor_bill_id=bill_id,
    )
    paid = client.post(
        f"/api/v1/finance/accounting/obligations/{obligation_id}/status",
        headers=HEADERS,
        json={
            "status": "paid",
            "payment_reference": "ACH-64000",
            "evidence_references": [f"finance_document:{payment['id']}"],
        },
    )
    assert paid.status_code == 200
    assert paid.json()["status"] == "paid"
    final_workspace = client.get(
        "/api/v1/finance/vendor-accounting",
        headers=HEADERS,
    ).json()
    assert final_workspace["bills"][0]["status"] == "paid"
    assert final_workspace["bills"][0]["payment_reference"] == "ACH-64000"
    assert final_workspace["summary"]["paid_year_to_date_cents"] == 64000
    assert db_session.scalar(select(func.count()).select_from(VendorBill)) == 1
    assert db_session.scalar(select(func.count()).select_from(VendorBillLine)) == 2
    assert db_session.scalar(select(func.count()).select_from(FinanceDocument)) == 3

    download = client.get(
        f"/api/v1/finance/documents/{w9['id']}/content",
        headers=HEADERS,
    )
    assert download.status_code == 200
    assert download.content.startswith(b"%PDF")
    assert (
        db_session.scalar(
            select(func.count()).select_from(AuditEvent).where(
                AuditEvent.action == "finance.document_access"
            )
        )
        == 1
    )
