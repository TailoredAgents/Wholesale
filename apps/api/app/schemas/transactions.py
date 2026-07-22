from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field


class TransactionQueueItem(BaseModel):
    id: UUID
    lead_id: UUID
    seller_name: str
    property_address: str
    status: str
    purchase_price_cents: int
    closing_date: datetime | None
    next_deadline: datetime | None
    coordinator_name: str | None
    checklist_complete: int
    checklist_total: int
    risk_flags: list[str]


class TransactionMetrics(BaseModel):
    active: int
    pending_approval: int
    due_next_seven_days: int
    overdue: int
    ready_to_close: int


class TransactionOverview(BaseModel):
    metrics: TransactionMetrics
    items: list[TransactionQueueItem]


class ContractPackageCreate(BaseModel):
    template_id: UUID | None = None
    seller_name: str = Field(min_length=1, max_length=255)
    buyer_entity_name: str = Field(min_length=1, max_length=255)
    purchase_price_cents: int = Field(ge=1)
    earnest_money_cents: int | None = Field(default=None, ge=0)
    closing_date: datetime | None = None
    inspection_period_days: int | None = Field(default=None, ge=0, le=120)
    special_terms: str | None = Field(default=None, max_length=4000)
    notes: str | None = Field(default=None, max_length=2000)


class ContractPackageRead(BaseModel):
    id: UUID
    version_number: int
    template_id: UUID | None
    status: str
    seller_name: str
    buyer_entity_name: str
    purchase_price_cents: int
    earnest_money_cents: int | None
    closing_date: datetime | None
    inspection_period_days: int | None
    approval_request_id: UUID | None
    notes: str | None
    approved_at: datetime | None
    sent_at: datetime | None
    executed_at: datetime | None
    created_at: datetime


class TransactionDocumentRead(BaseModel):
    id: UUID
    contract_package_id: UUID | None
    document_type: str
    title: str
    status: str
    file_name: str
    content_type: str
    file_size: int
    occurred_at: datetime
    notes: str | None
    download_url: str


class TransactionPartyCreate(BaseModel):
    party_type: Literal["seller", "buyer", "closing_attorney", "title_company", "lender", "other"]
    name: str = Field(min_length=1, max_length=255)
    company_name: str | None = Field(default=None, max_length=255)
    email: str | None = Field(default=None, max_length=320)
    phone: str | None = Field(default=None, max_length=80)
    address: str | None = Field(default=None, max_length=500)
    is_primary: bool = False
    notes: str | None = Field(default=None, max_length=1000)


class TransactionPartyRead(BaseModel):
    id: UUID
    party_type: str
    name: str
    company_name: str | None
    email: str | None
    phone: str | None
    address: str | None
    is_primary: bool
    notes: str | None
    created_at: datetime


class ChecklistItemUpdate(BaseModel):
    status: Literal["open", "in_progress", "blocked", "complete", "not_applicable"] | None = None
    responsible_user_id: UUID | None = None
    due_at: datetime | None = None
    evidence_document_id: UUID | None = None
    evidence_notes: str | None = Field(default=None, max_length=1000)


class TransactionChecklistRead(BaseModel):
    id: UUID
    item_key: str | None
    category: str
    title: str
    description: str | None
    status: str
    is_required: bool
    responsible_user_id: UUID | None
    responsible_name: str | None
    due_at: datetime | None
    completed_at: datetime | None
    dependency_item_id: UUID | None
    evidence_document_id: UUID | None
    evidence_notes: str | None
    escalated_at: datetime | None
    sort_order: int


class TransactionEventCreate(BaseModel):
    summary: str = Field(min_length=1, max_length=500)
    event_type: str = Field(default="note", min_length=1, max_length=80)


class TransactionEventRead(BaseModel):
    id: UUID
    event_type: str
    summary: str
    actor_name: str | None
    occurred_at: datetime


class TransactionUpdate(BaseModel):
    coordinator_user_id: UUID | None = None
    title_company: str | None = Field(default=None, max_length=255)
    closing_date: datetime | None = None
    earnest_money_due_at: datetime | None = None
    earnest_money_paid_at: datetime | None = None
    due_diligence_deadline: datetime | None = None
    title_opened_at: datetime | None = None
    title_cleared_at: datetime | None = None
    assignment_deadline: datetime | None = None
    notes: str | None = Field(default=None, max_length=2000)


class TransactionClose(BaseModel):
    outcome: Literal["funded", "cancelled"]
    notes: str = Field(min_length=3, max_length=2000)


class ContractTemplateRead(BaseModel):
    id: UUID
    document_type: str
    state_code: str
    name: str
    version_number: int
    status: str
    file_name: str
    approved_at: datetime | None
    created_at: datetime


class TransactionDetail(BaseModel):
    id: UUID
    lead_id: UUID
    deal_id: UUID
    seller_name: str
    property_address: str
    status: str
    contract_type: str
    purchase_price_cents: int
    assignment_fee_cents: int | None
    earnest_money_cents: int | None
    title_company: str | None
    closing_date: datetime | None
    inspection_period_days: int | None
    coordinator_user_id: UUID | None
    coordinator_name: str | None
    earnest_money_due_at: datetime | None
    earnest_money_paid_at: datetime | None
    due_diligence_deadline: datetime | None
    title_opened_at: datetime | None
    title_cleared_at: datetime | None
    assignment_deadline: datetime | None
    funded_at: datetime | None
    closed_at: datetime | None
    cancelled_at: datetime | None
    notes: str | None
    contract_packages: list[ContractPackageRead]
    documents: list[TransactionDocumentRead]
    parties: list[TransactionPartyRead]
    checklist: list[TransactionChecklistRead]
    events: list[TransactionEventRead]
