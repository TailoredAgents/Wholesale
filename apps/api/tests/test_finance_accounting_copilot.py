from datetime import date

from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.auth import principal_for_user
from app.main import app
from app.models.foundation import (
    BankTransactionMatch,
    JournalEntry,
    User,
)
from app.services.bootstrap import bootstrap_foundation
from app.services.management_intelligence import build_management_facts

OWNER_EMAIL = "owner@example.com"
HEADERS = {"X-Dev-User-Email": OWNER_EMAIL}


def seed_owner(db: Session) -> User:
    bootstrap_foundation(
        db,
        organization_name="Stonegate Home Buyers",
        admin_email=OWNER_EMAIL,
        admin_name="Owner",
    )
    owner = db.scalar(select(User).where(User.email == OWNER_EMAIL))
    assert owner is not None
    return owner


def post_cash_journal(
    client: TestClient,
    accounts: dict[str, str],
    amount_cents: int,
) -> str:
    response = client.post(
        "/api/v1/finance/accounting/journals",
        headers=HEADERS,
        json={
            "entry_date": date.today().isoformat(),
            "memo": "Collected assignment fee for F6F review.",
            "source_type": "f6f_test",
            "source_id": "f6f-closing-001",
            "posting_rule_version": 1,
            "evidence_references": ["closing_statement:f6f-001"],
            "idempotency_key": "f6f-journal-001",
            "currency": "USD",
            "lines": [
                {
                    "accounting_account_id": accounts["operating_cash"],
                    "debit_cents": amount_cents,
                    "credit_cents": 0,
                },
                {
                    "accounting_account_id": accounts["assignment_fee_revenue"],
                    "debit_cents": 0,
                    "credit_cents": amount_cents,
                },
            ],
        },
    )
    assert response.status_code == 201
    entry_id = response.json()["id"]
    assert client.post(
        f"/api/v1/finance/accounting/journals/{entry_id}/approve",
        headers=HEADERS,
        json={"notes": "Evidence reviewed for Copilot test."},
    ).status_code == 200
    assert client.post(
        f"/api/v1/finance/accounting/journals/{entry_id}/post",
        headers=HEADERS,
        json={"notes": "Posted for Copilot evidence test."},
    ).status_code == 200
    return str(entry_id)


def test_f6f_finance_copilot_uses_exact_read_only_accounting_evidence(
    db_session: Session,
    api_db_override: None,
) -> None:
    owner = seed_owner(db_session)
    principal = principal_for_user(db_session, owner)
    client = TestClient(app)
    setup = client.get(
        "/api/v1/finance/accounting/setup",
        headers=HEADERS,
    ).json()
    accounts = {item["system_key"]: item["id"] for item in setup["accounts"]}
    journal_id = post_cash_journal(client, accounts, 2_500_000)

    assert client.post(
        "/api/v1/finance/marketing-spend",
        headers=HEADERS,
        json={
            "source": "software",
            "campaign": "F6F accounting classification",
            "amount_cents": 25_000,
            "notes": "Monthly CRM subscription.",
        },
    ).status_code == 201
    bank_account = client.post(
        "/api/v1/finance/banking/accounts",
        headers=HEADERS,
        json={
            "name": "F6F operating account",
            "institution_name": "Test Bank",
            "account_type": "checking",
            "last_four": "1001",
        },
    )
    assert bank_account.status_code == 201
    imported = client.post(
        "/api/v1/finance/banking/imports",
        headers=HEADERS,
        json={
            "bank_account_id": bank_account.json()["id"],
            "file_name": "f6f-statement.csv",
            "csv_content": (
                "Date,Description,Amount,Transaction ID\n"
                f"{date.today().isoformat()},Settlement deposit,25000.00,f6f-bank-001\n"
            ),
            "field_mapping": {
                "date": "Date",
                "description": "Description",
                "amount": "Amount",
                "external_id": "Transaction ID",
            },
        },
    )
    assert imported.status_code == 201

    journal_count_before = db_session.scalar(
        select(func.count(JournalEntry.id))
    )
    match_count_before = db_session.scalar(
        select(func.count(BankTransactionMatch.id))
    )
    finance = build_management_facts(
        db_session,
        principal,
        "finance.reconcile",
        30,
    )
    tax = build_management_facts(
        db_session,
        principal,
        "finance.tax_review",
        30,
    )

    accounting = finance["context"]["accounting_review"]
    assert accounting["statement_summary"]["trial_balance_balanced"] is True
    assert accounting["statement_summary"]["balance_sheet_balanced"] is True
    assert accounting["close_readiness"]["blocking_count"] >= 1
    assert len(accounting["prior_period_variances"]) == 5
    assert accounting["bank_match_candidates"] == [
        {
            "bank_transaction_citation": accounting["bank_match_candidates"][0][
                "bank_transaction_citation"
            ],
            "journal_citation": f"journal_entry:{journal_id}",
            "occurred_on": date.today().isoformat(),
            "description": "Settlement deposit",
            "amount_cents": 2_500_000,
            "journal_entry_number": accounting["bank_match_candidates"][0][
                "journal_entry_number"
            ],
            "journal_memo": "Collected assignment fee for F6F review.",
            "match_basis": (
                "one unused posted journal has the exact cash movement"
            ),
            "confidence": "candidate_only",
            "requires_human_match_decision": True,
        }
    ]
    assert any(
        item["citation"].startswith("accounting_source:marketing_spend:")
        for item in accounting["posting_candidates"]
    )
    assert any(
        item["citation"].startswith("journal_line:")
        for item in accounting["general_ledger_evidence"]
    )
    assert any(
        item["proposed_tax_category"]
        for item in tax["context"]["classification_candidates"]
    )
    assert db_session.scalar(select(func.count(JournalEntry.id))) == journal_count_before
    assert (
        db_session.scalar(select(func.count(BankTransactionMatch.id)))
        == match_count_before
    )


def test_f6f_bank_candidates_preserve_same_amount_ambiguity(
    db_session: Session,
    api_db_override: None,
) -> None:
    owner = seed_owner(db_session)
    principal = principal_for_user(db_session, owner)
    client = TestClient(app)
    setup = client.get(
        "/api/v1/finance/accounting/setup",
        headers=HEADERS,
    ).json()
    accounts = {item["system_key"]: item["id"] for item in setup["accounts"]}
    post_cash_journal(client, accounts, 2_500_000)
    bank_account = client.post(
        "/api/v1/finance/banking/accounts",
        headers=HEADERS,
        json={
            "name": "Ambiguous operating account",
            "institution_name": "Test Bank",
            "account_type": "checking",
            "last_four": "1002",
        },
    )
    assert bank_account.status_code == 201
    imported = client.post(
        "/api/v1/finance/banking/imports",
        headers=HEADERS,
        json={
            "bank_account_id": bank_account.json()["id"],
            "file_name": "ambiguous-f6f-statement.csv",
            "csv_content": (
                "Date,Description,Amount,Transaction ID\n"
                f"{date.today().isoformat()},Deposit one,25000.00,f6f-bank-002\n"
                f"{date.today().isoformat()},Deposit two,25000.00,f6f-bank-003\n"
            ),
            "field_mapping": {
                "date": "Date",
                "description": "Description",
                "amount": "Amount",
                "external_id": "Transaction ID",
            },
        },
    )
    assert imported.status_code == 201

    finance = build_management_facts(
        db_session,
        principal,
        "finance.reconcile",
        30,
    )
    accounting = finance["context"]["accounting_review"]

    assert accounting["bank_match_candidates"] == []
    assert accounting["ambiguous_bank_line_count"] == 2
