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


class TransactionDocumentFactCreate(BaseModel):
    field_key: str = Field(min_length=1, max_length=120)
    value_text: str = Field(min_length=1, max_length=2000)
    source_page: int | None = Field(default=None, ge=1, le=10_000)
    source_excerpt: str | None = Field(default=None, max_length=1000)


class TransactionDocumentFactRead(BaseModel):
    id: UUID
    document_id: UUID
    field_key: str
    value_text: str
    source_page: int | None
    source_excerpt: str | None
    extraction_method: str
    status: str
    confidence_score: int | None
    reviewed_by_name: str | None
    reviewed_at: datetime | None
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
    facts: list[TransactionDocumentFactRead] = Field(default_factory=list)


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


class TransactionDeadlineRisk(BaseModel):
    item: str
    due_at: datetime
    severity: Literal["info", "warning", "critical"]
    reason: str
    evidence: list[str]


class TransactionDocumentFinding(BaseModel):
    finding: str
    document_id: UUID | None = None
    source_page: int | None = Field(default=None, ge=1)
    evidence: str


class TransactionCoordinationOutput(BaseModel):
    status_summary: str
    missing_items: list[str]
    deadline_risks: list[TransactionDeadlineRisk]
    document_findings: list[TransactionDocumentFinding]
    party_gaps: list[str]
    recommended_internal_actions: list[str]
    closing_attorney_email_draft: str
    seller_email_draft: str
    legal_escalations: list[str]
    evidence: list[str]
    confidence: int = Field(ge=0, le=100)


class TransactionCopilotAnalyzeRequest(BaseModel):
    idempotency_key: str | None = Field(default=None, min_length=1, max_length=255)


class TransactionCopilotRecommendationRead(BaseModel):
    id: UUID
    transaction_id: UUID
    lead_id: UUID
    ai_run_log_id: UUID | None
    status: str
    output_payload: dict[str, object]
    confidence_score: int | None
    generated_at: datetime
    reviewed_at: datetime | None


class TransactionCopilotAnalyzeRead(BaseModel):
    run_id: UUID
    run_status: str
    message: str
    recommendation: TransactionCopilotRecommendationRead | None


class TransactionCopilotReviewRequest(BaseModel):
    decision: Literal["accepted", "edited", "rejected"]
    final_output: dict[str, object] | None = None
    notes: str | None = Field(default=None, max_length=2000)
    estimated_time_saved_seconds: int = Field(default=0, ge=0, le=86_400)

    def model_post_init(self, __context: object) -> None:
        if self.decision == "edited" and self.final_output is None:
            raise ValueError("Edited guidance requires the corrected output.")
        if self.decision != "edited" and self.final_output is not None:
            raise ValueError("Corrected output is only accepted with an edited decision.")


class TransactionCopilotReviewRead(BaseModel):
    id: UUID
    recommendation_id: UUID
    decision: str
    final_output: dict[str, object] | None
    notes: str | None
    estimated_time_saved_seconds: int
    reviewed_at: datetime


class TransactionCopilotMetrics(BaseModel):
    generated: int
    reviewed: int
    accepted_or_corrected_rate_basis_points: int
    correction_rate_basis_points: int
    estimated_time_saved_minutes: int


class TransactionCopilotOverview(BaseModel):
    pilot_mode: Literal["draft_only"]
    runtime_status: str
    capability_status: str
    external_actions_blocked: bool
    readiness_score: int = Field(ge=0, le=100)
    readiness_band: Literal["ready", "needs_review", "blocked"]
    readiness_gaps: list[str]
    deadline_risks: list[TransactionDeadlineRisk]
    evidence_available: list[str]
    confirmed_document_fact_count: int
    recommendations: list[TransactionCopilotRecommendationRead]
    metrics: TransactionCopilotMetrics


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
