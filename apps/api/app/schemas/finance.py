from datetime import datetime
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
    summary: FinanceSummary
    revenue_records: list[RevenueRead]
    deductions: list[DealDeductionRead]
    compensation_rules: list[CompensationRuleRead]
    compensation_calculations: list[CompensationCalculationRead]
    marketing_spend: list[MarketingSpendRead]
