import io
import zipfile
from datetime import date

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.main import app
from app.services.bootstrap import bootstrap_foundation

OWNER_EMAIL = "owner@example.com"


def seed_owner(db: Session) -> None:
    bootstrap_foundation(
        db,
        organization_name="Stonegate Home Buyers",
        admin_email=OWNER_EMAIL,
        admin_name="Owner",
    )


def post_journal(
    client: TestClient,
    headers: dict[str, str],
    accounts: dict[str, str],
    *,
    key: str,
    memo: str,
    debit_account: str,
    credit_account: str,
    amount_cents: int,
) -> None:
    response = client.post(
        "/api/v1/finance/accounting/journals",
        headers=headers,
        json={
            "entry_date": date.today().isoformat(),
            "memo": memo,
            "source_type": "report_test",
            "source_id": key,
            "posting_rule_version": 1,
            "evidence_references": [f"evidence:{key}"],
            "idempotency_key": key,
            "currency": "USD",
            "lines": [
                {
                    "accounting_account_id": accounts[debit_account],
                    "debit_cents": amount_cents,
                    "credit_cents": 0,
                    "memo": memo,
                },
                {
                    "accounting_account_id": accounts[credit_account],
                    "debit_cents": 0,
                    "credit_cents": amount_cents,
                    "memo": memo,
                },
            ],
        },
    )
    assert response.status_code == 201
    entry_id = response.json()["id"]
    approved = client.post(
        f"/api/v1/finance/accounting/journals/{entry_id}/approve",
        headers=headers,
        json={"notes": "Source evidence reviewed."},
    )
    posted = client.post(
        f"/api/v1/finance/accounting/journals/{entry_id}/post",
        headers=headers,
        json={"notes": "Included in financial reporting test."},
    )
    assert approved.status_code == 200
    assert posted.status_code == 200


def test_posted_ledger_reports_and_cpa_export(
    db_session: Session,
    api_db_override: None,
) -> None:
    seed_owner(db_session)
    client = TestClient(app)
    headers = {"X-Dev-User-Email": OWNER_EMAIL}
    setup = client.get("/api/v1/finance/accounting/setup", headers=headers).json()
    accounts = {item["system_key"]: item["id"] for item in setup["accounts"]}

    post_journal(
        client,
        headers,
        accounts,
        key="report-revenue-001",
        memo="Collected assignment fee.",
        debit_account="operating_cash",
        credit_account="assignment_fee_revenue",
        amount_cents=2_500_000,
    )
    post_journal(
        client,
        headers,
        accounts,
        key="report-expense-001",
        memo="Paid prospecting contractor.",
        debit_account="prospecting_labor",
        credit_account="operating_cash",
        amount_cents=500_000,
    )
    post_journal(
        client,
        headers,
        accounts,
        key="report-owner-distribution-001",
        memo="Recorded owner distribution.",
        debit_account="owner_distributions",
        credit_account="operating_cash",
        amount_cents=100_000,
    )

    today = date.today()
    start_on = today.replace(day=1).isoformat()
    end_on = today.isoformat()
    response = client.get(
        f"/api/v1/finance/accounting/reports?start_on={start_on}&end_on={end_on}",
        headers=headers,
    )

    assert response.status_code == 200
    reports = response.json()
    assert reports["profit_and_loss"]["revenue"]["total_cents"] == 2_500_000
    assert (
        reports["profit_and_loss"]["operating_expenses"]["total_cents"] == 500_000
    )
    assert reports["profit_and_loss"]["net_income_cents"] == 2_000_000
    assert reports["cash_flow"]["operating_cents"] == 2_000_000
    assert reports["cash_flow"]["financing_cents"] == -100_000
    assert reports["cash_flow"]["net_change_cents"] == 1_900_000
    assert reports["balance_sheet"]["total_assets_cents"] == 1_900_000
    assert reports["balance_sheet"]["equity"]["total_cents"] == -100_000
    assert (
        reports["balance_sheet"]["total_liabilities_and_equity_cents"]
        == 1_900_000
    )
    assert reports["balance_sheet"]["balanced"] is True
    assert reports["trial_balance"]["total_debits_cents"] == 2_500_000
    assert reports["trial_balance"]["total_credits_cents"] == 2_500_000
    assert reports["trial_balance"]["balanced"] is True
    assert len(reports["general_ledger"]) == 6
    assert reports["close_readiness"]["ready_to_close"] is False
    assert reports["close_readiness"]["blocking_count"] == 1

    archive_response = client.get(
        (
            "/api/v1/finance/accounting/reports/cpa-export"
            f"?start_on={start_on}&end_on={end_on}"
        ),
        headers=headers,
    )
    assert archive_response.status_code == 200
    assert archive_response.headers["content-type"] == "application/zip"
    assert "stonegate-cpa-" in archive_response.headers["content-disposition"]
    with zipfile.ZipFile(io.BytesIO(archive_response.content)) as archive:
        assert set(archive.namelist()) == {
            "balance-sheet.csv",
            "deal-profitability.csv",
            "general-ledger.csv",
            "manifest.json",
            "payables.csv",
            "payments.csv",
            "profit-and-loss.csv",
            "receivables.csv",
            "trial-balance.csv",
        }
        assert "Collected assignment fee." in archive.read(
            "general-ledger.csv"
        ).decode()


def test_accounting_reports_reject_reversed_date_range(
    db_session: Session,
    api_db_override: None,
) -> None:
    seed_owner(db_session)
    client = TestClient(app)
    response = client.get(
        "/api/v1/finance/accounting/reports?start_on=2026-07-31&end_on=2026-07-01",
        headers={"X-Dev-User-Email": OWNER_EMAIL},
    )
    assert response.status_code == 422
    assert response.json()["detail"] == (
        "Report end date cannot be before its start date."
    )
