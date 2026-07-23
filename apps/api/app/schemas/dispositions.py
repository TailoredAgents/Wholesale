from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field


class DispositionCaseCreate(BaseModel):
    transaction_id: UUID
    strategy: Literal["assignment", "double_close", "novation"] = "assignment"
    asking_price_cents: int = Field(ge=1)
    minimum_acceptable_cents: int = Field(ge=1)
    operating_mode_key: str = Field(default="human_led", max_length=80)
    notes: str | None = Field(default=None, max_length=2000)


class ProofDocumentRead(BaseModel):
    id: UUID
    buyer_id: UUID
    status: str
    institution_name: str | None
    verified_amount_cents: int | None
    expires_at: datetime | None
    file_name: str
    created_at: datetime


class MatchRead(BaseModel):
    id: UUID
    buyer_id: UUID
    buyer_name: str
    score_basis_points: int
    score_components: dict[str, int]
    qualification_status: str
    recipient_status: str
    rank: int
    proof_status: str
    proof_expires_at: datetime | None
    latest_proof_document_id: UUID | None


class OfferCreate(BaseModel):
    buyer_id: UUID
    amount_cents: int = Field(ge=1)
    earnest_money_cents: int | None = Field(default=None, ge=0)
    financing_type: str = Field(default="cash", max_length=80)
    proof_document_id: UUID | None = None
    deposit_due_at: datetime | None = None
    notes: str | None = Field(default=None, max_length=2000)


class OfferRead(BaseModel):
    id: UUID
    buyer_id: UUID
    buyer_name: str
    amount_cents: int
    earnest_money_cents: int | None
    financing_type: str
    status: str
    proof_document_id: UUID | None
    deposit_due_at: datetime | None
    deposit_received_at: datetime | None
    selected_at: datetime | None
    notes: str | None
    received_at: datetime


class EngagementCreate(BaseModel):
    buyer_id: UUID
    engagement_type: Literal["inquiry", "showing", "follow_up", "deposit"]
    status: str = Field(default="logged", max_length=40)
    scheduled_at: datetime | None = None
    notes: str | None = Field(default=None, max_length=1000)


class EngagementRead(BaseModel):
    id: UUID
    buyer_id: UUID
    buyer_name: str
    engagement_type: str
    status: str
    scheduled_at: datetime | None
    occurred_at: datetime
    notes: str | None


class BuyerSelection(BaseModel):
    primary_offer_id: UUID
    backup_offer_id: UUID | None = None
    reason: str = Field(min_length=3, max_length=1000)


class PayoutRead(BaseModel):
    id: UUID
    role_key: str
    user_id: UUID | None
    user_name: str | None
    credit_basis_points: int
    amount_cents: int
    status: str


class ReconciliationRead(BaseModel):
    id: UUID
    status: str
    gross_revenue_cents: int
    acquisition_reserve_cents: int
    deal_deductions_cents: int
    adjusted_deal_margin_cents: int
    total_compensation_cents: int
    company_profit_cents: int
    company_margin_basis_points: int
    target_margin_basis_points: int
    notes: str | None
    payouts: list[PayoutRead]
    created_at: datetime


class ReconciliationDecision(BaseModel):
    decision: Literal["approved", "rejected"]
    notes: str = Field(min_length=3, max_length=2000)
    approve_below_target: bool = False


class DispositionCaseRead(BaseModel):
    id: UUID
    transaction_id: UUID
    lead_id: UUID
    seller_name: str
    property_address: str
    property_type: str | None
    status: str
    strategy: str
    asking_price_cents: int
    minimum_acceptable_cents: int
    package_status: str
    package_snapshot: dict[str, object]
    compensation_plan_label: str
    operating_mode_label: str
    selected_buyer_id: UUID | None
    backup_buyer_id: UUID | None
    matches: list[MatchRead]
    offers: list[OfferRead]
    engagements: list[EngagementRead]
    reconciliation: ReconciliationRead | None
    created_at: datetime


class EligibleTransactionRead(BaseModel):
    id: UUID
    seller_name: str
    property_address: str
    purchase_price_cents: int
    assignment_fee_cents: int | None


class DispositionMetrics(BaseModel):
    active_cases: int
    packages_pending: int
    buyer_selected: int
    reconciliation_pending: int
    below_margin_target: int


class DispositionOverview(BaseModel):
    metrics: DispositionMetrics
    eligible_transactions: list[EligibleTransactionRead]
    cases: list[DispositionCaseRead]


class DispositionBuyerRecommendation(BaseModel):
    buyer_id: UUID
    buyer_name: str
    recommendation: Literal["priority", "backup", "hold", "exclude"]
    rationale: list[str]
    risks: list[str]
    evidence: list[str]


class DispositionOfferComparison(BaseModel):
    offer_id: UUID
    buyer_name: str
    strength: Literal["strong", "acceptable", "weak", "ineligible"]
    rationale: list[str]
    risks: list[str]


class DispositionCoordinationOutput(BaseModel):
    status_summary: str
    package_gaps: list[str]
    package_highlights: list[str]
    recommended_buyers: list[DispositionBuyerRecommendation]
    offer_comparison: list[DispositionOfferComparison]
    buyer_outreach_subject: str
    buyer_outreach_body: str
    recommended_internal_actions: list[str]
    relationship_update_proposals: list[str]
    risk_alerts: list[str]
    uncertainties: list[str]
    evidence: list[str]
    confidence: int = Field(ge=0, le=100)


class DispositionCopilotAnalyzeRequest(BaseModel):
    idempotency_key: str | None = Field(default=None, min_length=1, max_length=255)


class DispositionCopilotRecommendationRead(BaseModel):
    id: UUID
    disposition_case_id: UUID
    transaction_id: UUID
    lead_id: UUID
    ai_run_log_id: UUID | None
    status: str
    output_payload: DispositionCoordinationOutput
    confidence_score: int | None
    generated_at: datetime
    reviewed_at: datetime | None


class DispositionCopilotAnalyzeRead(BaseModel):
    run_id: UUID
    run_status: str
    message: str
    recommendation: DispositionCopilotRecommendationRead | None


class DispositionCopilotReviewRequest(BaseModel):
    decision: Literal["accepted", "edited", "rejected"]
    final_output: dict[str, object] | None = None
    notes: str | None = Field(default=None, max_length=2000)
    estimated_time_saved_seconds: int = Field(default=0, ge=0, le=86_400)

    def model_post_init(self, __context: object) -> None:
        if self.decision == "edited" and self.final_output is None:
            raise ValueError("Edited guidance requires the corrected output.")
        if self.decision != "edited" and self.final_output is not None:
            raise ValueError("Corrected output is only accepted with an edited decision.")


class DispositionCopilotReviewRead(BaseModel):
    id: UUID
    recommendation_id: UUID
    decision: str
    final_output: DispositionCoordinationOutput | None
    notes: str | None
    estimated_time_saved_seconds: int
    reviewed_at: datetime


class DispositionCopilotMetrics(BaseModel):
    generated: int
    reviewed: int
    accepted_or_corrected_rate_basis_points: int
    correction_rate_basis_points: int
    estimated_time_saved_minutes: int


class DispositionRiskAlert(BaseModel):
    severity: Literal["info", "warning", "critical"]
    item: str
    reason: str
    evidence: list[str]


class DispositionCopilotOverview(BaseModel):
    pilot_mode: Literal["draft_only"]
    runtime_status: str
    capability_status: str
    external_actions_blocked: bool
    readiness_score: int = Field(ge=0, le=100)
    readiness_band: Literal["ready", "needs_review", "blocked"]
    readiness_gaps: list[str]
    risk_alerts: list[DispositionRiskAlert]
    qualified_buyer_count: int
    verified_buyer_count: int
    offer_count: int
    backup_coverage: bool
    recommendations: list[DispositionCopilotRecommendationRead]
    metrics: DispositionCopilotMetrics
