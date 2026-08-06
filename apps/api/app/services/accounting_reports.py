import csv
import io
import json
import zipfile
from collections import defaultdict
from datetime import UTC, date, datetime
from typing import TypedDict
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.auth import Principal
from app.models.foundation import (
    AccountingAccount,
    AccountingPeriod,
    AuditEvent,
    BankAccount,
    BankReconciliation,
    BankTransaction,
    DealPayout,
    FinancialObligation,
    JournalEntry,
    JournalLine,
    RevenueRecord,
)
from app.schemas.accounting_reports import (
    AccountingReportsWorkspaceRead,
    BalanceSheetRead,
    CashFlowRead,
    CloseChecklistItem,
    CloseReadinessRead,
    DealProfitabilityItem,
    GeneralLedgerLine,
    PayableScheduleItem,
    PaymentHistoryItem,
    ProfitAndLossRead,
    ReceivableScheduleItem,
    ReportAccountLine,
    ReportSection,
    TrialBalanceRead,
)
from app.services.finance import ensure_accounting_foundation


class AccountMovement(TypedDict):
    opening: int
    debits: int
    credits: int
    journals: set[UUID]


def get_accounting_reports(
    db: Session,
    principal: Principal,
    start_on: date,
    end_on: date,
) -> AccountingReportsWorkspaceRead:
    if end_on < start_on:
        raise ValueError("Report end date cannot be before its start date.")
    profile = ensure_accounting_foundation(db, principal)
    accounts = list(
        db.scalars(
            select(AccountingAccount)
            .where(
                AccountingAccount.organization_id == principal.organization_id,
                AccountingAccount.policy_version == profile.policy_version,
                AccountingAccount.is_active.is_(True),
            )
            .order_by(AccountingAccount.code)
        ).all()
    )
    entries = list(
        db.scalars(
            select(JournalEntry).where(
                JournalEntry.organization_id == principal.organization_id,
                JournalEntry.status == "posted",
                JournalEntry.entry_date <= end_on,
            )
        ).all()
    )
    entry_by_id = {item.id: item for item in entries}
    lines = list(
        db.scalars(
            select(JournalLine).where(
                JournalLine.organization_id == principal.organization_id,
                JournalLine.journal_entry_id.in_(set(entry_by_id)),
            )
        ).all()
    )
    account_by_id = {item.id: item for item in accounts}
    movements: dict[UUID, AccountMovement] = {
        account.id: {"opening": 0, "debits": 0, "credits": 0, "journals": set()}
        for account in accounts
    }
    period_lines: list[tuple[JournalLine, JournalEntry, AccountingAccount]] = []
    for line in lines:
        entry = entry_by_id[line.journal_entry_id]
        account = account_by_id.get(line.accounting_account_id)
        if account is None:
            continue
        movement = movements[account.id]
        signed = line.debit_cents - line.credit_cents
        if entry.entry_date < start_on:
            movement["opening"] += signed
        else:
            movement["debits"] += line.debit_cents
            movement["credits"] += line.credit_cents
            movement["journals"].add(entry.id)
            period_lines.append((line, entry, account))
    report_lines = {
        account.id: account_report_line(account, movements[account.id]) for account in accounts
    }
    pnl = profit_and_loss(accounts, report_lines)
    cumulative_earnings = sum(
        report_lines[account.id].ending_balance_cents
        * (1 if account.account_type == "revenue" else -1)
        for account in accounts
        if account.account_type in {"revenue", "cost_of_revenue", "expense"}
    )
    balance_sheet = build_balance_sheet(accounts, report_lines, cumulative_earnings)
    trial = trial_balance(accounts, report_lines)
    general_ledger = [
        GeneralLedgerLine(
            journal_entry_id=entry.id,
            entry_number=entry.entry_number,
            entry_date=entry.entry_date,
            memo=line.memo or entry.memo,
            source_type=entry.source_type,
            source_id=entry.source_id,
            evidence_references=entry.evidence_references,
            account_code=account.code,
            account_name=account.name,
            debit_cents=line.debit_cents,
            credit_cents=line.credit_cents,
            deal_id=line.deal_id,
            transaction_id=line.transaction_id,
        )
        for line, entry, account in sorted(
            period_lines,
            key=lambda item: (item[1].entry_date, item[1].entry_number, item[0].line_number),
        )
    ]
    payables = payable_schedule(db, principal, end_on)
    receivables = receivable_schedule(db, principal, end_on)
    payments = payment_history(db, principal, start_on, end_on)
    deal_profitability = deal_profitability_schedule(period_lines)
    close = close_readiness(
        db,
        principal,
        start_on,
        end_on,
        trial,
        entries,
    )
    return AccountingReportsWorkspaceRead(
        period_start_on=start_on,
        period_end_on=end_on,
        accounting_method=profile.accounting_method,
        profit_and_loss=pnl,
        balance_sheet=balance_sheet,
        cash_flow=cash_flow(period_lines),
        trial_balance=trial,
        general_ledger=general_ledger,
        receivables=receivables,
        payables=payables,
        payments=payments,
        deal_profitability=deal_profitability,
        close_readiness=close,
    )


def account_report_line(
    account: AccountingAccount,
    movement: AccountMovement,
) -> ReportAccountLine:
    opening_signed = movement["opening"]
    debits = movement["debits"]
    credits = movement["credits"]
    raw_ending = opening_signed + debits - credits
    normal_multiplier = 1 if account.normal_balance == "debit" else -1
    return ReportAccountLine(
        account_id=account.id,
        code=account.code,
        name=account.name,
        account_type=account.account_type,
        opening_balance_cents=opening_signed * normal_multiplier,
        debit_cents=debits,
        credit_cents=credits,
        ending_balance_cents=raw_ending * normal_multiplier,
        journal_count=len(movement["journals"]),
    )


def section(
    key: str,
    label: str,
    account_types: set[str],
    accounts: list[AccountingAccount],
    lines: dict[UUID, ReportAccountLine],
    *,
    movement_only: bool = False,
    presentation_normal: str | None = None,
) -> ReportSection:
    selected = []
    for account in accounts:
        if account.account_type not in account_types:
            continue
        item = lines[account.id]
        if movement_only:
            multiplier = 1 if account.normal_balance == "debit" else -1
            amount = (item.debit_cents - item.credit_cents) * multiplier
            item = item.model_copy(
                update={"opening_balance_cents": 0, "ending_balance_cents": amount}
            )
        elif presentation_normal is not None:
            account_multiplier = 1 if account.normal_balance == "debit" else -1
            presentation_multiplier = 1 if presentation_normal == "debit" else -1
            item = item.model_copy(
                update={
                    "opening_balance_cents": (
                        item.opening_balance_cents * account_multiplier * presentation_multiplier
                    ),
                    "ending_balance_cents": (
                        item.ending_balance_cents * account_multiplier * presentation_multiplier
                    ),
                }
            )
        if item.ending_balance_cents or item.debit_cents or item.credit_cents:
            selected.append(item)
    return ReportSection(
        key=key,
        label=label,
        total_cents=sum(item.ending_balance_cents for item in selected),
        lines=selected,
    )


def profit_and_loss(
    accounts: list[AccountingAccount],
    lines: dict[UUID, ReportAccountLine],
) -> ProfitAndLossRead:
    revenue = section("revenue", "Revenue", {"revenue"}, accounts, lines, movement_only=True)
    costs = section(
        "cost_of_revenue",
        "Cost of revenue",
        {"cost_of_revenue"},
        accounts,
        lines,
        movement_only=True,
    )
    expenses = section(
        "operating_expenses",
        "Operating expenses",
        {"expense"},
        accounts,
        lines,
        movement_only=True,
    )
    gross = revenue.total_cents - costs.total_cents
    return ProfitAndLossRead(
        revenue=revenue,
        cost_of_revenue=costs,
        operating_expenses=expenses,
        gross_profit_cents=gross,
        net_income_cents=gross - expenses.total_cents,
    )


def build_balance_sheet(
    accounts: list[AccountingAccount],
    lines: dict[UUID, ReportAccountLine],
    current_earnings: int,
) -> BalanceSheetRead:
    assets = section(
        "assets",
        "Assets",
        {"asset"},
        accounts,
        lines,
        presentation_normal="debit",
    )
    liabilities = section(
        "liabilities",
        "Liabilities",
        {"liability"},
        accounts,
        lines,
        presentation_normal="credit",
    )
    equity = section(
        "equity",
        "Equity",
        {"equity"},
        accounts,
        lines,
        presentation_normal="credit",
    )
    liabilities_and_equity = liabilities.total_cents + equity.total_cents + current_earnings
    return BalanceSheetRead(
        assets=assets,
        liabilities=liabilities,
        equity=equity,
        current_earnings_cents=current_earnings,
        total_assets_cents=assets.total_cents,
        total_liabilities_and_equity_cents=liabilities_and_equity,
        balanced=assets.total_cents == liabilities_and_equity,
    )


def trial_balance(
    accounts: list[AccountingAccount],
    lines: dict[UUID, ReportAccountLine],
) -> TrialBalanceRead:
    result = []
    total_debits = 0
    total_credits = 0
    for account in accounts:
        item = lines[account.id]
        signed = (
            item.ending_balance_cents
            if account.normal_balance == "debit"
            else -item.ending_balance_cents
        )
        debit = max(signed, 0)
        credit = max(-signed, 0)
        total_debits += debit
        total_credits += credit
        if debit or credit:
            result.append(
                item.model_copy(
                    update={
                        "debit_cents": debit,
                        "credit_cents": credit,
                    }
                )
            )
    return TrialBalanceRead(
        total_debits_cents=total_debits,
        total_credits_cents=total_credits,
        balanced=total_debits == total_credits,
        lines=result,
    )


def cash_flow(
    period_lines: list[tuple[JournalLine, JournalEntry, AccountingAccount]],
) -> CashFlowRead:
    by_entry: dict[
        UUID,
        list[tuple[JournalLine, JournalEntry, AccountingAccount]],
    ] = defaultdict(list)
    for item in period_lines:
        by_entry[item[1].id].append(item)
    totals = {"operating": 0, "investing": 0, "financing": 0}
    for grouped in by_entry.values():
        cash_lines = [item for item in grouped if item[2].subtype == "cash"]
        if not cash_lines:
            continue
        delta = sum(line.debit_cents - line.credit_cents for line, _, _ in cash_lines)
        other_accounts = [account for _, _, account in grouped if account.subtype != "cash"]
        entry = grouped[0][1]
        category = "operating"
        if entry.source_type == "owner_distribution" or any(
            account.account_type in {"equity", "liability"} for account in other_accounts
        ):
            category = "financing"
        elif any(account.account_type == "asset" for account in other_accounts):
            category = "investing"
        totals[category] += delta
    return CashFlowRead(
        operating_cents=totals["operating"],
        investing_cents=totals["investing"],
        financing_cents=totals["financing"],
        net_change_cents=sum(totals.values()),
    )


def payable_schedule(
    db: Session,
    principal: Principal,
    end_on: date,
) -> list[PayableScheduleItem]:
    items = [
        PayableScheduleItem(
            id=item.id,
            category=item.obligation_type,
            counterparty=item.counterparty_name,
            amount_cents=item.amount_cents,
            status=item.status,
            due_on=item.due_at.date() if item.due_at else None,
            source_id=item.source_id,
        )
        for item in db.scalars(
            select(FinancialObligation).where(
                FinancialObligation.organization_id == principal.organization_id,
                FinancialObligation.status.in_({"approved", "payable", "disputed"}),
            )
        ).all()
        if not item.due_at or item.due_at.date() <= end_on
    ]
    items.extend(
        PayableScheduleItem(
            id=item.id,
            category="commission",
            counterparty=item.role_key,
            amount_cents=item.amount_cents,
            status=item.status,
            due_on=None,
            source_id=str(item.deal_reconciliation_id),
        )
        for item in db.scalars(
            select(DealPayout).where(
                DealPayout.organization_id == principal.organization_id,
                DealPayout.status.in_({"approved", "payable", "disputed"}),
            )
        ).all()
    )
    return sorted(items, key=lambda item: (item.due_on or date.max, item.counterparty))


def receivable_schedule(
    db: Session,
    principal: Principal,
    end_on: date,
) -> list[ReceivableScheduleItem]:
    return [
        ReceivableScheduleItem(
            id=item.id,
            source=item.source,
            amount_cents=item.amount_cents,
            status=item.status,
            expected_on=item.received_at.date(),
            lead_id=item.lead_id,
            deal_id=item.deal_id,
            transaction_id=item.transaction_id,
        )
        for item in db.scalars(
            select(RevenueRecord)
            .where(
                RevenueRecord.organization_id == principal.organization_id,
                RevenueRecord.status == "pending",
                RevenueRecord.received_at
                <= datetime.combine(
                    end_on,
                    datetime.max.time(),
                    tzinfo=UTC,
                ),
            )
            .order_by(RevenueRecord.received_at)
        ).all()
    ]


def payment_history(
    db: Session,
    principal: Principal,
    start_on: date,
    end_on: date,
) -> list[PaymentHistoryItem]:
    obligation_items = [
        PaymentHistoryItem(
            id=item.id,
            category=item.obligation_type,
            counterparty=item.counterparty_name,
            amount_cents=item.amount_cents,
            paid_on=item.paid_at.date(),
            payment_reference=item.payment_reference,
            source_id=item.source_id,
        )
        for item in db.scalars(
            select(FinancialObligation).where(
                FinancialObligation.organization_id == principal.organization_id,
                FinancialObligation.status == "paid",
                FinancialObligation.paid_at.is_not(None),
            )
        ).all()
        if item.paid_at and start_on <= item.paid_at.date() <= end_on
    ]
    payout_items = [
        PaymentHistoryItem(
            id=item.id,
            category="commission",
            counterparty=item.role_key,
            amount_cents=item.amount_cents,
            paid_on=item.paid_at.date(),
            payment_reference=item.payment_reference,
            source_id=str(item.deal_reconciliation_id),
        )
        for item in db.scalars(
            select(DealPayout).where(
                DealPayout.organization_id == principal.organization_id,
                DealPayout.status == "paid",
                DealPayout.paid_at.is_not(None),
            )
        ).all()
        if item.paid_at and start_on <= item.paid_at.date() <= end_on
    ]
    return sorted(
        obligation_items + payout_items,
        key=lambda item: (item.paid_on, item.counterparty),
    )


def deal_profitability_schedule(
    period_lines: list[tuple[JournalLine, JournalEntry, AccountingAccount]],
) -> list[DealProfitabilityItem]:
    totals: dict[UUID, dict[str, int]] = defaultdict(lambda: {"revenue": 0, "cost": 0})
    for line, _, account in period_lines:
        if line.deal_id is None:
            continue
        if account.account_type == "revenue":
            totals[line.deal_id]["revenue"] += line.credit_cents - line.debit_cents
        elif account.account_type in {"cost_of_revenue", "expense"}:
            totals[line.deal_id]["cost"] += line.debit_cents - line.credit_cents
    return [
        DealProfitabilityItem(
            deal_id=deal_id,
            revenue_cents=values["revenue"],
            cost_cents=values["cost"],
            profit_cents=values["revenue"] - values["cost"],
        )
        for deal_id, values in totals.items()
    ]


def close_readiness(
    db: Session,
    principal: Principal,
    start_on: date,
    end_on: date,
    trial: TrialBalanceRead,
    posted_entries: list[JournalEntry],
) -> CloseReadinessRead:
    period_key = start_on.strftime("%Y-%m")
    period = db.scalar(
        select(AccountingPeriod).where(
            AccountingPeriod.organization_id == principal.organization_id,
            AccountingPeriod.period_key == period_key,
        )
    )
    unposted = list(
        db.scalars(
            select(JournalEntry).where(
                JournalEntry.organization_id == principal.organization_id,
                JournalEntry.entry_date >= start_on,
                JournalEntry.entry_date <= end_on,
                JournalEntry.status.in_({"draft", "approved"}),
            )
        ).all()
    )
    active_banks = list(
        db.scalars(
            select(BankAccount).where(
                BankAccount.organization_id == principal.organization_id,
                BankAccount.status == "active",
            )
        ).all()
    )
    reconciled_accounts = set(
        db.scalars(
            select(BankReconciliation.bank_account_id).where(
                BankReconciliation.organization_id == principal.organization_id,
                BankReconciliation.statement_end_on >= start_on,
                BankReconciliation.statement_end_on <= end_on,
                BankReconciliation.status == "approved",
            )
        ).all()
    )
    unmatched = len(
        list(
            db.scalars(
                select(BankTransaction.id).where(
                    BankTransaction.organization_id == principal.organization_id,
                    BankTransaction.occurred_on >= start_on,
                    BankTransaction.occurred_on <= end_on,
                    BankTransaction.status == "unmatched",
                )
            ).all()
        )
    )
    missing_evidence = sum(
        not entry.evidence_references
        for entry in posted_entries
        if start_on <= entry.entry_date <= end_on
    )
    items = [
        checklist(
            "trial_balance",
            "Trial balance",
            not trial.balanced,
            (
                "Trial balance is balanced."
                if trial.balanced
                else "Debits and credits do not balance."
            ),
            "/os/finance",
        ),
        checklist(
            "unfinished_journals",
            "Unfinished journals",
            bool(unposted),
            (
                f"{len(unposted)} draft or approved journals remain."
                if unposted
                else "No unfinished journals remain."
            ),
            "/os/finance",
        ),
        checklist(
            "bank_reconciliation",
            "Bank reconciliations",
            bool(active_banks and len(reconciled_accounts) < len(active_banks)),
            (
                f"{len(reconciled_accounts)} of {len(active_banks)} active accounts reconciled."
                if active_banks
                else "No active bank accounts require reconciliation."
            ),
            "/os/finance",
        ),
        checklist(
            "unmatched_bank",
            "Unmatched bank transactions",
            bool(unmatched),
            (
                f"{unmatched} statement transactions remain unmatched."
                if unmatched
                else "No unmatched statement transactions remain."
            ),
            "/os/finance",
        ),
        CloseChecklistItem(
            key="source_evidence",
            label="Posted-entry evidence",
            status="warning" if missing_evidence else "pass",
            detail=(
                f"{missing_evidence} posted entries have no evidence reference."
                if missing_evidence
                else "Posted entries include evidence references."
            ),
            action_href="/os/finance",
        ),
        checklist(
            "period_review",
            "Accounting period review",
            period is None or period.status == "open",
            (
                "Start period review before closing."
                if period is None or period.status == "open"
                else f"Period is {period.status}."
            ),
            "/os/finance",
        ),
    ]
    blocking = sum(item.status == "block" for item in items)
    return CloseReadinessRead(
        period_key=period_key,
        period_status=period.status if period else "not_created",
        ready_to_close=blocking == 0,
        blocking_count=blocking,
        warning_count=sum(item.status == "warning" for item in items),
        items=items,
    )


def checklist(
    key: str,
    label: str,
    blocked: bool,
    detail: str,
    href: str,
) -> CloseChecklistItem:
    return CloseChecklistItem(
        key=key,
        label=label,
        status="block" if blocked else "pass",
        detail=detail,
        action_href=href,
    )


def build_cpa_export(
    db: Session,
    principal: Principal,
    start_on: date,
    end_on: date,
) -> bytes:
    reports = get_accounting_reports(db, principal, start_on, end_on)
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(
            "manifest.json",
            json.dumps(
                {
                    "organization_id": str(principal.organization_id),
                    "period_start": start_on.isoformat(),
                    "period_end": end_on.isoformat(),
                    "generated_at": datetime.now(UTC).isoformat(),
                    "accounting_method": reports.accounting_method,
                    "trial_balance_balanced": reports.trial_balance.balanced,
                    "close_ready": reports.close_readiness.ready_to_close,
                },
                indent=2,
            ),
        )
        archive.writestr(
            "trial-balance.csv",
            csv_bytes(
                ["code", "account", "debit_cents", "credit_cents"],
                [
                    [item.code, item.name, item.debit_cents, item.credit_cents]
                    for item in reports.trial_balance.lines
                ],
            ),
        )
        archive.writestr(
            "general-ledger.csv",
            csv_bytes(
                [
                    "date",
                    "entry_number",
                    "memo",
                    "account_code",
                    "account",
                    "debit_cents",
                    "credit_cents",
                    "source_type",
                    "source_id",
                    "evidence",
                ],
                [
                    [
                        item.entry_date,
                        item.entry_number,
                        item.memo,
                        item.account_code,
                        item.account_name,
                        item.debit_cents,
                        item.credit_cents,
                        item.source_type,
                        item.source_id or "",
                        "|".join(item.evidence_references),
                    ]
                    for item in reports.general_ledger
                ],
            ),
        )
        archive.writestr(
            "profit-and-loss.csv",
            csv_bytes(
                ["section", "code", "account", "amount_cents"],
                [
                    [section.label, item.code, item.name, item.ending_balance_cents]
                    for section in [
                        reports.profit_and_loss.revenue,
                        reports.profit_and_loss.cost_of_revenue,
                        reports.profit_and_loss.operating_expenses,
                    ]
                    for item in section.lines
                ],
            ),
        )
        archive.writestr(
            "balance-sheet.csv",
            csv_bytes(
                ["section", "code", "account", "amount_cents"],
                [
                    [section.label, item.code, item.name, item.ending_balance_cents]
                    for section in [
                        reports.balance_sheet.assets,
                        reports.balance_sheet.liabilities,
                        reports.balance_sheet.equity,
                    ]
                    for item in section.lines
                ],
            ),
        )
        archive.writestr(
            "receivables.csv",
            csv_bytes(
                [
                    "source",
                    "amount_cents",
                    "status",
                    "expected_on",
                    "lead_id",
                    "deal_id",
                    "transaction_id",
                ],
                [
                    [
                        item.source,
                        item.amount_cents,
                        item.status,
                        item.expected_on,
                        item.lead_id or "",
                        item.deal_id or "",
                        item.transaction_id or "",
                    ]
                    for item in reports.receivables
                ],
            ),
        )
        archive.writestr(
            "payables.csv",
            csv_bytes(
                ["category", "counterparty", "amount_cents", "status", "due_on", "source_id"],
                [
                    [
                        item.category,
                        item.counterparty,
                        item.amount_cents,
                        item.status,
                        item.due_on or "",
                        item.source_id or "",
                    ]
                    for item in reports.payables
                ],
            ),
        )
        archive.writestr(
            "payments.csv",
            csv_bytes(
                [
                    "category",
                    "counterparty",
                    "amount_cents",
                    "paid_on",
                    "payment_reference",
                    "source_id",
                ],
                [
                    [
                        item.category,
                        item.counterparty,
                        item.amount_cents,
                        item.paid_on,
                        item.payment_reference or "",
                        item.source_id or "",
                    ]
                    for item in reports.payments
                ],
            ),
        )
        archive.writestr(
            "deal-profitability.csv",
            csv_bytes(
                ["deal_id", "revenue_cents", "cost_cents", "profit_cents"],
                [
                    [
                        item.deal_id,
                        item.revenue_cents,
                        item.cost_cents,
                        item.profit_cents,
                    ]
                    for item in reports.deal_profitability
                ],
            ),
        )
    db.add(
        AuditEvent(
            organization_id=principal.organization_id,
            actor_user_id=principal.user_id,
            actor_type="user",
            action="finance.cpa_export",
            entity_type="accounting_period",
            entity_id=principal.organization_id,
            previous_value=None,
            new_value={"period_start": start_on.isoformat(), "period_end": end_on.isoformat()},
            reason="CPA handoff package generated from posted ledger records.",
        )
    )
    db.commit()
    return output.getvalue()


def csv_bytes(headers: list[str], rows: list[list[object]]) -> str:
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(headers)
    writer.writerows(rows)
    return output.getvalue()
