from datetime import date
from uuid import UUID

from pydantic import BaseModel


class ReportAccountLine(BaseModel):
    account_id: UUID
    code: str
    name: str
    account_type: str
    opening_balance_cents: int
    debit_cents: int
    credit_cents: int
    ending_balance_cents: int
    journal_count: int


class ReportSection(BaseModel):
    key: str
    label: str
    total_cents: int
    lines: list[ReportAccountLine]


class GeneralLedgerLine(BaseModel):
    journal_entry_id: UUID
    entry_number: str
    entry_date: date
    memo: str
    source_type: str
    source_id: str | None
    evidence_references: list[str]
    account_code: str
    account_name: str
    debit_cents: int
    credit_cents: int
    deal_id: UUID | None
    transaction_id: UUID | None


class TrialBalanceRead(BaseModel):
    total_debits_cents: int
    total_credits_cents: int
    balanced: bool
    lines: list[ReportAccountLine]


class ProfitAndLossRead(BaseModel):
    revenue: ReportSection
    cost_of_revenue: ReportSection
    operating_expenses: ReportSection
    gross_profit_cents: int
    net_income_cents: int


class BalanceSheetRead(BaseModel):
    assets: ReportSection
    liabilities: ReportSection
    equity: ReportSection
    current_earnings_cents: int
    total_assets_cents: int
    total_liabilities_and_equity_cents: int
    balanced: bool


class CashFlowRead(BaseModel):
    operating_cents: int
    investing_cents: int
    financing_cents: int
    net_change_cents: int


class CloseChecklistItem(BaseModel):
    key: str
    label: str
    status: str
    detail: str
    action_href: str


class CloseReadinessRead(BaseModel):
    period_key: str
    period_status: str
    ready_to_close: bool
    blocking_count: int
    warning_count: int
    items: list[CloseChecklistItem]


class PayableScheduleItem(BaseModel):
    id: UUID
    category: str
    counterparty: str
    amount_cents: int
    status: str
    due_on: date | None
    source_id: str | None


class ReceivableScheduleItem(BaseModel):
    id: UUID
    source: str
    amount_cents: int
    status: str
    expected_on: date
    lead_id: UUID | None
    deal_id: UUID | None
    transaction_id: UUID | None


class PaymentHistoryItem(BaseModel):
    id: UUID
    category: str
    counterparty: str
    amount_cents: int
    paid_on: date
    payment_reference: str | None
    source_id: str | None


class DealProfitabilityItem(BaseModel):
    deal_id: UUID
    revenue_cents: int
    cost_cents: int
    profit_cents: int


class AccountingReportsWorkspaceRead(BaseModel):
    period_start_on: date
    period_end_on: date
    accounting_method: str
    profit_and_loss: ProfitAndLossRead
    balance_sheet: BalanceSheetRead
    cash_flow: CashFlowRead
    trial_balance: TrialBalanceRead
    general_ledger: list[GeneralLedgerLine]
    receivables: list[ReceivableScheduleItem]
    payables: list[PayableScheduleItem]
    payments: list[PaymentHistoryItem]
    deal_profitability: list[DealProfitabilityItem]
    close_readiness: CloseReadinessRead
