from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, Field


class RevenueCreate(BaseModel):
    lead_id: UUID | None = None
    source: str = Field(default="assignment_fee", max_length=120)
    status: str = Field(default="collected", max_length=80)
    amount_cents: int = Field(ge=1)
    received_at: datetime | None = None
    notes: str | None = Field(default=None, max_length=2000)


class DealDeductionCreate(BaseModel):
    lead_id: UUID | None = None
    category: str = Field(default="other", max_length=120)
    amount_cents: int = Field(ge=1)
    incurred_at: datetime | None = None
    notes: str | None = Field(default=None, max_length=2000)


class CompensationRuleCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    role_key: str = Field(max_length=120)
    basis_points: int = Field(ge=0, le=10000)
    applies_to: str = Field(default="net_revenue", max_length=120)
    effective_start_at: datetime | None = None
    effective_end_at: datetime | None = None
    is_active: bool = True
    notes: str | None = Field(default=None, max_length=2000)


class MarketingSpendCreate(BaseModel):
    source: str = Field(min_length=1, max_length=120)
    campaign: str | None = Field(default=None, max_length=255)
    amount_cents: int = Field(ge=1)
    spend_month_at: datetime | None = None
    notes: str | None = Field(default=None, max_length=2000)


class RevenueRead(BaseModel):
    id: UUID
    lead_id: UUID | None
    deal_id: UUID | None
    transaction_id: UUID | None
    seller_name: str | None
    property_address: str | None
    source: str
    status: str
    amount_cents: int
    received_at: datetime
    notes: str | None
    created_at: datetime


class DealDeductionRead(BaseModel):
    id: UUID
    lead_id: UUID | None
    deal_id: UUID | None
    transaction_id: UUID | None
    category: str
    amount_cents: int
    incurred_at: datetime
    notes: str | None
    created_at: datetime


class CompensationRuleRead(BaseModel):
    id: UUID
    name: str
    role_key: str
    basis_points: int
    applies_to: str
    effective_start_at: datetime
    effective_end_at: datetime | None
    is_active: bool
    notes: str | None
    created_at: datetime


class CompensationCalculationRead(BaseModel):
    id: UUID
    revenue_record_id: UUID
    compensation_rule_id: UUID
    role_key: str
    basis_amount_cents: int
    basis_points: int
    calculated_amount_cents: int
    status: str
    notes: str | None
    created_at: datetime


class MarketingSpendRead(BaseModel):
    id: UUID
    source: str
    campaign: str | None
    amount_cents: int
    spend_month_at: datetime
    notes: str | None
    created_at: datetime


class FinanceSummary(BaseModel):
    collected_revenue_cents: int
    pending_revenue_cents: int
    deductions_cents: int
    net_revenue_cents: int
    compensation_cents: int
    marketing_spend_cents: int
    company_net_cents: int


class FinanceOverview(BaseModel):
    period_days: int | None
    period_start_at: datetime | None
    period_end_at: datetime
    previous_summary: FinanceSummary | None
    summary: FinanceSummary
    revenue_records: list[RevenueRead]
    deductions: list[DealDeductionRead]
    compensation_rules: list[CompensationRuleRead]
    compensation_calculations: list[CompensationCalculationRead]
    marketing_spend: list[MarketingSpendRead]


class AccountingProfileUpdate(BaseModel):
    legal_entity_name: str = Field(min_length=1, max_length=255)
    entity_type: str = Field(max_length=80)
    federal_tax_classification: str = Field(max_length=80)
    accounting_method: str = Field(max_length=40)
    tax_year_end_month: int = Field(default=12, ge=1, le=12)
    tax_year_end_day: int = Field(default=31, ge=1, le=31)
    books_start_date: date | None = None
    home_state: str = Field(default="GA", min_length=2, max_length=2)
    owner_compensation_treatment: str = Field(max_length=80)
    notes: str | None = Field(default=None, max_length=2000)


class AccountingProfileRead(BaseModel):
    id: UUID
    legal_entity_name: str
    entity_type: str
    federal_tax_classification: str
    accounting_method: str
    tax_year_end_month: int
    tax_year_end_day: int
    books_start_date: date | None
    home_state: str
    currency: str
    owner_compensation_treatment: str
    status: str
    policy_version: int
    tax_rule_year: int
    notes: str | None
    updated_at: datetime


class AccountingAccountRead(BaseModel):
    id: UUID
    policy_version: int
    code: str
    system_key: str
    name: str
    account_type: str
    subtype: str
    normal_balance: str
    tax_category: str
    deal_tracking: bool
    is_active: bool
    description: str


class TaxReadinessRead(BaseModel):
    capability_key: str
    mode: str
    status: str
    readiness_score: int
    readiness_gaps: list[str]
    review_scope: list[str]
    prohibited_actions: list[str]
    source_records: int
    records_missing_notes: int


class AccountingSetupRead(BaseModel):
    profile: AccountingProfileRead
    accounts: list[AccountingAccountRead]
    readiness_score: int
    readiness_gaps: list[str]
    policy_notes: list[str]
    tax_copilot: TaxReadinessRead


class AccountingPeriodCreate(BaseModel):
    period_key: str = Field(pattern=r"^\d{4}-(0[1-9]|1[0-2])$")


class AccountingPeriodStatusUpdate(BaseModel):
    status: str = Field(max_length=40)
    reason: str | None = Field(default=None, max_length=2000)


class JournalLineCreate(BaseModel):
    accounting_account_id: UUID
    debit_cents: int = Field(default=0, ge=0)
    credit_cents: int = Field(default=0, ge=0)
    memo: str | None = Field(default=None, max_length=1000)
    deal_id: UUID | None = None
    transaction_id: UUID | None = None


class JournalEntryCreate(BaseModel):
    entry_date: date
    memo: str = Field(min_length=1, max_length=1000)
    source_type: str = Field(default="manual", min_length=1, max_length=120)
    source_id: str | None = Field(default=None, max_length=255)
    posting_rule_version: int = Field(default=1, ge=1)
    evidence_references: list[str] = Field(default_factory=list, max_length=50)
    idempotency_key: str = Field(min_length=8, max_length=255)
    currency: str = Field(default="USD", min_length=3, max_length=3)
    lines: list[JournalLineCreate] = Field(min_length=2, max_length=100)


class JournalDecision(BaseModel):
    notes: str | None = Field(default=None, max_length=2000)


class JournalReverseCreate(BaseModel):
    reversal_date: date
    reason: str = Field(min_length=1, max_length=2000)
    idempotency_key: str = Field(min_length=8, max_length=255)


class AccountingPeriodRead(BaseModel):
    id: UUID
    period_key: str
    period_start_at: date
    period_end_at: date
    status: str
    review_started_at: datetime | None
    closed_at: datetime | None
    locked_at: datetime | None
    reopened_at: datetime | None
    reopen_reason: str | None
    draft_entries: int
    approved_entries: int
    posted_entries: int


class JournalLineRead(BaseModel):
    id: UUID
    accounting_account_id: UUID
    account_code: str
    account_name: str
    line_number: int
    debit_cents: int
    credit_cents: int
    memo: str | None
    deal_id: UUID | None
    transaction_id: UUID | None


class JournalEntryRead(BaseModel):
    id: UUID
    accounting_period_id: UUID
    entry_number: str
    entry_date: date
    status: str
    memo: str
    source_type: str
    source_id: str | None
    posting_rule_version: int
    evidence_references: list[str]
    idempotency_key: str
    currency: str
    total_debits_cents: int
    total_credits_cents: int
    prepared_by_user_id: UUID
    approved_by_user_id: UUID | None
    posted_by_user_id: UUID | None
    reversed_by_user_id: UUID | None
    reverses_entry_id: UUID | None
    reversal_entry_id: UUID | None
    approved_at: datetime | None
    posted_at: datetime | None
    reversed_at: datetime | None
    review_notes: str | None
    created_at: datetime
    lines: list[JournalLineRead]


class AccountingLedgerSummary(BaseModel):
    draft_entries: int
    approved_entries: int
    posted_entries: int
    reversed_entries: int
    posted_amount_cents: int
    out_of_balance_entries: int


class AccountingLedgerOverview(BaseModel):
    summary: AccountingLedgerSummary
    periods: list[AccountingPeriodRead]
    entries: list[JournalEntryRead]


class AccountingPostingRuleRead(BaseModel):
    id: UUID
    rule_key: str
    version_number: int
    name: str
    source_type: str
    trigger_status: str
    strategy_key: str
    debit_account_key: str
    credit_account_key: str
    evidence_required: bool
    status: str
    description: str
    approved_by_user_id: UUID | None
    approved_at: datetime | None
    effective_at: datetime | None


class AccountingSourceItemRead(BaseModel):
    source_type: str
    source_id: str
    posting_purpose: str
    label: str
    amount_cents: int
    occurred_at: datetime
    status: str
    readiness: str
    readiness_detail: str
    rule_id: UUID | None
    rule_key: str
    journal_entry_id: UUID | None
    journal_status: str | None
    evidence_references: list[str]
    lead_id: UUID | None = None
    deal_id: UUID | None = None
    transaction_id: UUID | None = None


class FinancialObligationCreate(BaseModel):
    obligation_type: str = Field(max_length=80)
    counterparty_name: str = Field(min_length=1, max_length=255)
    user_id: UUID | None = None
    expense_account_key: str | None = Field(default=None, max_length=120)
    amount_cents: int = Field(ge=1)
    status: str = Field(default="draft", max_length=40)
    source_type: str | None = Field(default=None, max_length=120)
    source_id: str | None = Field(default=None, max_length=255)
    due_at: datetime | None = None
    payment_reference: str | None = Field(default=None, max_length=255)
    evidence_references: list[str] = Field(default_factory=list, max_length=50)
    notes: str | None = Field(default=None, max_length=2000)


class FinancialObligationStatusUpdate(BaseModel):
    status: str = Field(max_length=40)
    payment_reference: str | None = Field(default=None, max_length=255)
    evidence_references: list[str] | None = Field(default=None, max_length=50)
    notes: str | None = Field(default=None, max_length=2000)


class FinancialObligationRead(BaseModel):
    id: UUID
    obligation_type: str
    direction: str
    counterparty_name: str
    user_id: UUID | None
    expense_account_key: str | None
    amount_cents: int
    status: str
    source_type: str | None
    source_id: str | None
    due_at: datetime | None
    approved_by_user_id: UUID | None
    approved_at: datetime | None
    paid_at: datetime | None
    payment_reference: str | None
    evidence_references: list[str]
    notes: str | None
    created_at: datetime


class AccountingPostingWorkspaceRead(BaseModel):
    rules: list[AccountingPostingRuleRead]
    source_items: list[AccountingSourceItemRead]
    obligations: list[FinancialObligationRead]
    draft_rule_count: int
    ready_item_count: int
    exception_count: int


class AccountingSourceDraftRequest(BaseModel):
    source_type: str = Field(max_length=120)
    source_id: str = Field(max_length=255)
    posting_purpose: str = Field(max_length=120)


class DealPayoutStatusUpdate(BaseModel):
    status: str = Field(max_length=40)
    due_at: datetime | None = None
    payment_reference: str | None = Field(default=None, max_length=255)
    evidence_references: list[str] | None = Field(default=None, max_length=50)
