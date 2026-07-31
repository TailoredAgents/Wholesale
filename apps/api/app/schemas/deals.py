from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class DealNextActionRead(BaseModel):
    task_id: UUID
    title: str
    action_type: str
    due_at: datetime | None
    responsible_user_id: UUID | None
    responsible_user_email: str | None
    due_status: str


class DealBlockerRead(BaseModel):
    key: str
    domain: str
    label: str
    severity: str


class DealQueueItemRead(BaseModel):
    id: UUID
    lead_id: UUID
    transaction_id: UUID
    disposition_case_id: UUID | None
    seller_name: str
    property_address: str
    property_type: str | None
    stage_key: str
    contract_status: str
    closing_status: str
    disposition_status: str
    finance_status: str
    owner_name: str | None
    coordinator_name: str | None
    disposition_owner_name: str | None
    closing_date: datetime | None
    next_deadline: datetime | None
    checklist_complete: int
    checklist_total: int
    document_count: int
    buyer_match_count: int
    buyer_offer_count: int
    selected_buyer_name: str | None
    contract_price_cents: int
    assignment_fee_cents: int | None
    company_profit_cents: int | None
    company_margin_basis_points: int | None
    primary_next_action: DealNextActionRead | None
    blockers: list[DealBlockerRead] = Field(default_factory=list)
    created_at: datetime


class DealMetricsRead(BaseModel):
    active: int
    closing_exceptions: int
    ready_for_disposition: int
    buyer_needed: int
    finance_review: int
    completed: int


class DealOverviewRead(BaseModel):
    can_view_economics: bool
    metrics: DealMetricsRead
    items: list[DealQueueItemRead]


class DealDetailRead(DealQueueItemRead):
    can_view_economics: bool
