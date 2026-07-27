from fastapi.testclient import TestClient

from app.main import app
from app.services.bootstrap import bootstrap_foundation

OWNER_EMAIL = "owner@example.com"
HEADERS = {"X-Dev-User-Email": OWNER_EMAIL}
CSV_CONTENT = "Date,Description,Amount,Balance,Transaction ID\n2026-07-01,Vendor ACH,-20.00,80.00,txn-1\n2026-07-02,Card fee,-10.00,70.00,txn-2\n"


def seed_owner(db_session) -> None:
    bootstrap_foundation(
        db_session,
        organization_name="Stonegate Home Buyers",
        admin_email=OWNER_EMAIL,
        admin_name="Owner",
    )


def import_payload(account_id: str) -> dict[str, object]:
    return {
        "bank_account_id": account_id,
        "file_name": "july-operating.csv",
        "csv_content": CSV_CONTENT,
        "field_mapping": {
            "date": "Date",
            "description": "Description",
            "amount": "Amount",
            "balance": "Balance",
            "external_id": "Transaction ID",
        },
        "opening_balance_cents": 10000,
        "closing_balance_cents": 7000,
    }


def test_private_bank_import_and_reconciliation_flow(db_session, api_db_override) -> None:
    seed_owner(db_session)
    client = TestClient(app)
    account = client.post(
        "/api/v1/finance/banking/accounts",
        headers=HEADERS,
        json={
            "name": "Operating checking",
            "institution_name": "Local Bank",
            "account_type": "checking",
            "last_four": "1234",
        },
    )
    assert account.status_code == 201
    account_id = account.json()["id"]
    preview = client.post(
        "/api/v1/finance/banking/imports/preview",
        headers=HEADERS,
        json=import_payload(account_id),
    )
    assert preview.status_code == 200
    assert preview.json()["valid_rows"] == 2
    imported = client.post(
        "/api/v1/finance/banking/imports",
        headers=HEADERS,
        json=import_payload(account_id),
    )
    assert imported.status_code == 201
    assert imported.json()["imported_rows"] == 2
    duplicate = client.post(
        "/api/v1/finance/banking/imports",
        headers=HEADERS,
        json=import_payload(account_id),
    )
    assert duplicate.status_code == 422

    workspace = client.get("/api/v1/finance/banking", headers=HEADERS)
    assert workspace.status_code == 200
    transactions = workspace.json()["transactions"]
    assert len(transactions) == 2
    for transaction in transactions:
        ignored = client.post(
            f"/api/v1/finance/banking/transactions/{transaction['id']}/status",
            headers=HEADERS,
            json={"status": "ignored", "notes": "Test non-operating item."},
        )
        assert ignored.status_code == 200

    reconciliation = client.post(
        "/api/v1/finance/banking/reconciliations",
        headers=HEADERS,
        json={
            "bank_account_id": account_id,
            "statement_import_id": imported.json()["id"],
            "statement_start_on": "2026-07-01",
            "statement_end_on": "2026-07-02",
            "opening_balance_cents": 10000,
            "closing_balance_cents": 7000,
        },
    )
    assert reconciliation.status_code == 201
    assert reconciliation.json()["difference_cents"] == 0
    assert reconciliation.json()["status"] == "review"
    approved = client.post(
        f"/api/v1/finance/banking/reconciliations/{reconciliation.json()['id']}/approve",
        headers=HEADERS,
        json={},
    )
    assert approved.status_code == 200
    assert approved.json()["status"] == "approved"
