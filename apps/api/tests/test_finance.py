from datetime import UTC, date, datetime, timedelta

from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.main import app
from app.models.foundation import (
    AccountingAccount,
    AccountingPostingRule,
    AccountingProfile,
    AccountingPeriod,
    AccountingSourceLink,
    AiCapabilityRuntimePolicy,
    AuditEvent,
    CompensationCalculation,
    CompensationRule,
    DealDeduction,
    FinancialObligation,
    JournalEntry,
    JournalLine,
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

    prior_period_at = datetime.now(UTC) - timedelta(days=45)
    for record in db_session.scalars(select(RevenueRecord)).all():
        record.received_at = prior_period_at
    for deduction in db_session.scalars(select(DealDeduction)).all():
        deduction.incurred_at = prior_period_at
    for spend in db_session.scalars(select(MarketingSpend)).all():
        spend.spend_month_at = prior_period_at
    db_session.commit()

    period_response = client.get(
        "/api/v1/finance?period_days=30",
        headers={"X-Dev-User-Email": OWNER_EMAIL},
    )
    assert period_response.status_code == 200
    period = period_response.json()
    assert period["period_days"] == 30
    assert period["period_start_at"] is not None
    assert period["summary"]["collected_revenue_cents"] == 0
    assert period["summary"]["company_net_cents"] == 0
    assert period["previous_summary"]["collected_revenue_cents"] == 2500000
    assert period["previous_summary"]["company_net_cents"] == 1480000
    assert period["revenue_records"] == []
    assert period["compensation_calculations"] == []
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


def test_accounting_foundation_is_wholesale_specific_and_idempotent(
    db_session: Session,
    api_db_override: None,
) -> None:
    seed_owner(db_session)
    client = TestClient(app)
    headers = {"X-Dev-User-Email": OWNER_EMAIL}

    first = client.get("/api/v1/finance/accounting/setup", headers=headers)
    second = client.get("/api/v1/finance/accounting/setup", headers=headers)

    assert first.status_code == 200
    assert second.status_code == 200
    setup = first.json()
    assert setup["profile"]["status"] == "needs_setup"
    assert setup["profile"]["accounting_method"] == "cash"
    assert setup["tax_copilot"]["mode"] == "draft_only"
    account_keys = {item["system_key"] for item in setup["accounts"]}
    assert {
        "assignment_fee_revenue",
        "wholesale_property_sale_revenue",
        "real_estate_inventory",
        "earnest_money_deposits",
        "owner_distributions",
    }.issubset(account_keys)
    assert "acquisition_reserve" not in account_keys
    assert (
        db_session.scalar(select(func.count()).select_from(AccountingProfile)) == 1
    )
    assert (
        db_session.scalar(select(func.count()).select_from(AccountingAccount))
        == len(setup["accounts"])
    )


def test_accounting_profile_and_tax_copilot_require_human_review(
    db_session: Session,
    api_db_override: None,
) -> None:
    seed_owner(db_session)
    client = TestClient(app)
    headers = {"X-Dev-User-Email": OWNER_EMAIL}

    updated = client.put(
        "/api/v1/finance/accounting/profile",
        headers=headers,
        json={
            "legal_entity_name": "Stonegate Home Buyers LLC",
            "entity_type": "single_member_llc",
            "federal_tax_classification": "disregarded_entity",
            "accounting_method": "cash",
            "tax_year_end_month": 12,
            "tax_year_end_day": 31,
            "books_start_date": "2026-01-01",
            "home_state": "GA",
            "owner_compensation_treatment": "owner_draw",
            "notes": "Classification to be confirmed by Stonegate's tax professional.",
        },
    )
    copilot = client.get(
        "/api/v1/finance/tax-copilot?period_days=30",
        headers=headers,
    )

    assert updated.status_code == 200
    assert updated.json()["profile"]["status"] == "ready"
    assert updated.json()["readiness_gaps"] == []
    assert copilot.status_code == 200
    assert copilot.json()["capability_key"] == "finance.tax_review"
    assert copilot.json()["pilot_mode"] == "draft_only"
    assert copilot.json()["external_actions_blocked"] is True
    policy = db_session.scalar(
        select(AiCapabilityRuntimePolicy).where(
            AiCapabilityRuntimePolicy.capability_key == "finance.tax_review"
        )
    )
    assert policy is not None
    assert policy.status == "enabled"
    assert policy.requires_human_review is True


def journal_payload(
    setup: dict[str, object],
    *,
    idempotency_key: str,
    amount_cents: int = 2500000,
) -> dict[str, object]:
    accounts = {
        item["system_key"]: item["id"]
        for item in setup["accounts"]  # type: ignore[index,union-attr]
    }
    return {
        "entry_date": date.today().isoformat(),
        "memo": "Assignment fee deposited after closing.",
        "source_type": "manual_test",
        "source_id": "closing-001",
        "posting_rule_version": 1,
        "evidence_references": ["closing-statement:test-001"],
        "idempotency_key": idempotency_key,
        "currency": "USD",
        "lines": [
            {
                "accounting_account_id": accounts["operating_cash"],
                "debit_cents": amount_cents,
                "credit_cents": 0,
                "memo": "Cash received.",
            },
            {
                "accounting_account_id": accounts["assignment_fee_revenue"],
                "debit_cents": 0,
                "credit_cents": amount_cents,
                "memo": "Assignment revenue.",
            },
        ],
    }


def test_double_entry_journal_lifecycle_and_linked_reversal(
    db_session: Session,
    api_db_override: None,
) -> None:
    seed_owner(db_session)
    client = TestClient(app)
    headers = {"X-Dev-User-Email": OWNER_EMAIL}
    setup = client.get(
        "/api/v1/finance/accounting/setup",
        headers=headers,
    ).json()

    created = client.post(
        "/api/v1/finance/accounting/journals",
        headers=headers,
        json=journal_payload(setup, idempotency_key="assignment-closing-001"),
    )
    duplicate = client.post(
        "/api/v1/finance/accounting/journals",
        headers=headers,
        json=journal_payload(setup, idempotency_key="assignment-closing-001"),
    )
    entry_id = created.json()["id"]
    approved = client.post(
        f"/api/v1/finance/accounting/journals/{entry_id}/approve",
        headers=headers,
        json={"notes": "Closing statement and cleared proceeds reviewed."},
    )
    posted = client.post(
        f"/api/v1/finance/accounting/journals/{entry_id}/post",
        headers=headers,
        json={"notes": "Posted to the open monthly period."},
    )
    reversal = client.post(
        f"/api/v1/finance/accounting/journals/{entry_id}/reverse",
        headers=headers,
        json={
            "reversal_date": date.today().isoformat(),
            "reason": "Test correction through a linked reversal.",
            "idempotency_key": "reverse-assignment-closing-001",
        },
    )
    reversal_id = reversal.json()["id"]
    reversal_approved = client.post(
        f"/api/v1/finance/accounting/journals/{reversal_id}/approve",
        headers=headers,
        json={"notes": "Reversal reviewed."},
    )
    reversal_posted = client.post(
        f"/api/v1/finance/accounting/journals/{reversal_id}/post",
        headers=headers,
        json={"notes": "Reversal posted."},
    )
    ledger = client.get(
        "/api/v1/finance/accounting/ledger",
        headers=headers,
    )

    assert created.status_code == 201
    assert duplicate.status_code == 201
    assert duplicate.json()["id"] == entry_id
    assert approved.status_code == 200
    assert approved.json()["status"] == "approved"
    assert posted.status_code == 200
    assert posted.json()["status"] == "posted"
    assert reversal.status_code == 201
    assert reversal.json()["status"] == "draft"
    assert reversal.json()["reverses_entry_id"] == entry_id
    assert reversal.json()["lines"][0]["debit_cents"] == 0
    assert reversal.json()["lines"][0]["credit_cents"] == 2500000
    assert reversal_approved.status_code == 200
    assert reversal_posted.status_code == 200
    assert reversal_posted.json()["status"] == "posted"
    assert ledger.status_code == 200
    ledger_entries = {item["id"]: item for item in ledger.json()["entries"]}
    assert ledger_entries[entry_id]["status"] == "reversed"
    assert ledger_entries[entry_id]["reversal_entry_id"] == reversal_id
    assert ledger.json()["summary"]["out_of_balance_entries"] == 0
    assert int(db_session.scalar(select(func.count()).select_from(JournalEntry)) or 0) == 2
    assert int(db_session.scalar(select(func.count()).select_from(JournalLine)) or 0) == 4


def test_journals_reject_imbalance_and_periods_control_posting(
    db_session: Session,
    api_db_override: None,
) -> None:
    seed_owner(db_session)
    client = TestClient(app)
    headers = {"X-Dev-User-Email": OWNER_EMAIL}
    setup = client.get(
        "/api/v1/finance/accounting/setup",
        headers=headers,
    ).json()
    invalid_payload = journal_payload(
        setup,
        idempotency_key="unbalanced-closing-001",
    )
    invalid_payload["lines"][1]["credit_cents"] = 2400000  # type: ignore[index]
    unbalanced = client.post(
        "/api/v1/finance/accounting/journals",
        headers=headers,
        json=invalid_payload,
    )

    created = client.post(
        "/api/v1/finance/accounting/journals",
        headers=headers,
        json=journal_payload(setup, idempotency_key="period-closing-001"),
    )
    entry_id = created.json()["id"]
    approved = client.post(
        f"/api/v1/finance/accounting/journals/{entry_id}/approve",
        headers=headers,
        json={"notes": "Ready for posting."},
    )
    ledger = client.get(
        "/api/v1/finance/accounting/ledger",
        headers=headers,
    ).json()
    period_id = ledger["periods"][0]["id"]
    review = client.post(
        f"/api/v1/finance/accounting/periods/{period_id}/status",
        headers=headers,
        json={"status": "review"},
    )
    blocked_post = client.post(
        f"/api/v1/finance/accounting/journals/{entry_id}/post",
        headers=headers,
        json={"notes": "Should be blocked while period is under review."},
    )
    blocked_close = client.post(
        f"/api/v1/finance/accounting/periods/{period_id}/status",
        headers=headers,
        json={"status": "closed"},
    )
    reopen = client.post(
        f"/api/v1/finance/accounting/periods/{period_id}/status",
        headers=headers,
        json={"status": "open"},
    )
    posted = client.post(
        f"/api/v1/finance/accounting/journals/{entry_id}/post",
        headers=headers,
        json={"notes": "Posted after review returned to open."},
    )
    review_again = client.post(
        f"/api/v1/finance/accounting/periods/{period_id}/status",
        headers=headers,
        json={"status": "review"},
    )
    closed = client.post(
        f"/api/v1/finance/accounting/periods/{period_id}/status",
        headers=headers,
        json={"status": "closed"},
    )
    reopened_without_reason = client.post(
        f"/api/v1/finance/accounting/periods/{period_id}/status",
        headers=headers,
        json={"status": "open"},
    )
    reopened = client.post(
        f"/api/v1/finance/accounting/periods/{period_id}/status",
        headers=headers,
        json={"status": "open", "reason": "Owner-approved correcting entry required."},
    )

    assert unbalanced.status_code == 422
    assert "equal" in unbalanced.json()["detail"]
    assert created.status_code == 201
    assert approved.status_code == 200
    assert review.status_code == 200
    assert blocked_post.status_code == 422
    assert blocked_close.status_code == 422
    assert "unposted" in blocked_close.json()["detail"]
    assert reopen.status_code == 200
    assert posted.status_code == 200
    assert review_again.status_code == 200
    assert closed.status_code == 200
    assert reopened_without_reason.status_code == 422
    assert reopened.status_code == 200
    assert reopened.json()["status"] == "open"
    assert db_session.scalar(select(func.count()).select_from(AccountingPeriod)) == 1


def approve_posting_rule(
    client: TestClient,
    headers: dict[str, str],
    rule_key: str,
) -> dict[str, object]:
    workspace = client.get(
        "/api/v1/finance/accounting/operations",
        headers=headers,
    ).json()
    rule = next(item for item in workspace["rules"] if item["rule_key"] == rule_key)
    response = client.post(
        f"/api/v1/finance/accounting/posting-rules/{rule['id']}/approve",
        headers=headers,
        json={},
    )
    assert response.status_code == 200
    return response.json()


def test_operational_posting_rules_require_approval_and_link_once(
    db_session: Session,
    api_db_override: None,
) -> None:
    seed_owner(db_session)
    client = TestClient(app)
    headers = {"X-Dev-User-Email": OWNER_EMAIL}

    initial = client.get(
        "/api/v1/finance/accounting/operations",
        headers=headers,
    )
    assert initial.status_code == 200
    assert initial.json()["draft_rule_count"] == 10
    assert all(rule["status"] == "draft" for rule in initial.json()["rules"])

    approve_posting_rule(client, headers, "marketing_spend_paid")
    spend = client.post(
        "/api/v1/finance/marketing-spend",
        headers=headers,
        json={
            "source": "lead_lists_data",
            "campaign": "Georgia absentee owners",
            "amount_cents": 12500,
            "notes": "Prospecting data subscription.",
        },
    )
    assert spend.status_code == 201
    workspace = client.get(
        "/api/v1/finance/accounting/operations",
        headers=headers,
    ).json()
    item = next(
        source
        for source in workspace["source_items"]
        if source["source_type"] == "marketing_spend"
    )
    assert item["readiness"] == "ready"

    payload = {
        "source_type": item["source_type"],
        "source_id": item["source_id"],
        "posting_purpose": item["posting_purpose"],
    }
    drafted = client.post(
        "/api/v1/finance/accounting/operations/draft",
        headers=headers,
        json=payload,
    )
    duplicate = client.post(
        "/api/v1/finance/accounting/operations/draft",
        headers=headers,
        json=payload,
    )

    assert drafted.status_code == 201
    assert duplicate.status_code == 201
    assert duplicate.json()["id"] == drafted.json()["id"]
    assert drafted.json()["status"] == "draft"
    assert drafted.json()["total_debits_cents"] == 12500
    assert drafted.json()["total_credits_cents"] == 12500
    account_names = {line["account_name"] for line in drafted.json()["lines"]}
    assert account_names == {"Lead Lists and Data", "Operating Cash"}
    assert (
        db_session.scalar(select(func.count()).select_from(AccountingSourceLink)) == 1
    )
    assert (
        db_session.scalar(select(func.count()).select_from(AccountingPostingRule)) == 10
    )


def test_obligation_payment_states_create_separate_accrual_and_settlement_drafts(
    db_session: Session,
    api_db_override: None,
) -> None:
    seed_owner(db_session)
    client = TestClient(app)
    headers = {"X-Dev-User-Email": OWNER_EMAIL}
    approve_posting_rule(client, headers, "obligation_accrued")
    approve_posting_rule(client, headers, "obligation_paid")

    obligation = client.post(
        "/api/v1/finance/accounting/obligations",
        headers=headers,
        json={
            "obligation_type": "vendor_payable",
            "counterparty_name": "Stonegate Hosting",
            "expense_account_key": "software_subscriptions",
            "amount_cents": 4900,
            "status": "approved",
            "evidence_references": ["invoice:host-2026-07"],
            "notes": "Monthly application hosting.",
        },
    )
    assert obligation.status_code == 201
    obligation_id = obligation.json()["id"]
    payable = client.post(
        f"/api/v1/finance/accounting/obligations/{obligation_id}/status",
        headers=headers,
        json={"status": "payable"},
    )
    paid = client.post(
        f"/api/v1/finance/accounting/obligations/{obligation_id}/status",
        headers=headers,
        json={
            "status": "paid",
            "payment_reference": "ACH-1007",
            "evidence_references": ["bank:ACH-1007"],
        },
    )
    assert payable.status_code == 200
    assert paid.status_code == 200
    assert paid.json()["status"] == "paid"

    workspace = client.get(
        "/api/v1/finance/accounting/operations",
        headers=headers,
    ).json()
    items = [
        item
        for item in workspace["source_items"]
        if item["source_type"] == "financial_obligation"
    ]
    assert {item["posting_purpose"] for item in items} == {"accrued", "paid"}
    assert all(item["readiness"] == "ready" for item in items)
    drafts = []
    for item in items:
        response = client.post(
            "/api/v1/finance/accounting/operations/draft",
            headers=headers,
            json={
                "source_type": item["source_type"],
                "source_id": item["source_id"],
                "posting_purpose": item["posting_purpose"],
            },
        )
        assert response.status_code == 201
        drafts.append(response.json())

    accrued = next(
        entry for entry in drafts if entry["idempotency_key"].endswith(":accrued:v1")
    )
    settled = next(
        entry for entry in drafts if entry["idempotency_key"].endswith(":paid:v1")
    )
    assert {line["account_name"] for line in accrued["lines"]} == {
        "Software and Subscriptions",
        "Accounts Payable",
    }
    assert {line["account_name"] for line in settled["lines"]} == {
        "Accounts Payable",
        "Operating Cash",
    }
    assert db_session.scalar(select(func.count()).select_from(FinancialObligation)) == 1
