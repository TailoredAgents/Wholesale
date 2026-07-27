from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field


class CalibrationCaseUpsert(BaseModel):
    benchmark_type: Literal[
        "expert_review",
        "appraisal",
        "completed_resale",
        "verified_market_sale",
    ]
    evidence_date: datetime
    benchmark_arv_cents: int = Field(ge=1, le=1_000_000_000)
    actual_rehab_cents: int | None = Field(default=None, ge=0, le=1_000_000_000)
    actual_seller_contract_cents: int | None = Field(
        default=None, ge=0, le=1_000_000_000
    )
    actual_disposition_cents: int | None = Field(default=None, ge=0, le=1_000_000_000)
    evidence_reference: str | None = Field(default=None, max_length=500)
    notes: str | None = Field(default=None, max_length=2000)


class CalibrationCaseRead(BaseModel):
    id: UUID
    lead_id: UUID
    analysis_id: UUID
    seller_name: str
    property_address: str
    market_key: str
    benchmark_type: str
    evidence_date: datetime
    benchmark_arv_cents: int
    actual_rehab_cents: int | None
    actual_seller_contract_cents: int | None
    actual_disposition_cents: int | None
    predicted_arv_low_cents: int | None
    predicted_arv_point_cents: int | None
    predicted_arv_high_cents: int | None
    predicted_rehab_cents: int | None
    predicted_seller_ceiling_cents: int | None
    predicted_disposition_cents: int | None
    arv_error_cents: int | None
    arv_error_percentage: float | None
    arv_absolute_error_percentage: float | None
    arv_range_hit: bool | None
    provider: str
    methodology_version: str | None
    confidence_score: int
    comp_review_applied: bool
    evidence_reference: str | None
    notes: str | None
    recorded_by_user_id: UUID | None
    created_at: datetime
    updated_at: datetime


class CalibrationMetricSummary(BaseModel):
    market_key: str
    providers: list[str]
    methodology_versions: list[str]
    sample_count: int
    median_error_percentage: float | None
    median_absolute_error_percentage: float | None
    range_coverage_percentage: float | None
    overestimate_count: int
    underestimate_count: int
    balanced_count: int
    repair_sample_count: int
    repair_median_absolute_error_percentage: float | None
    seller_contract_sample_count: int
    seller_contract_median_absolute_variance_percentage: float | None
    disposition_sample_count: int
    disposition_median_absolute_error_percentage: float | None
    comp_review_case_count: int
    comp_review_decision_count: int
    comp_review_override_count: int
    comp_review_override_percentage: float | None
    provider_adequacy: str
    failure_patterns: list[str]
    readiness: str


class CalibrationDecisionCreate(BaseModel):
    scope_key: str = Field(min_length=1, max_length=255)
    decision_type: Literal[
        "continue_current_method",
        "methodology_change",
        "provider_change",
    ]
    title: str = Field(min_length=3, max_length=255)
    rationale: str = Field(min_length=10, max_length=3000)
    proposed_methodology_version: str | None = Field(default=None, max_length=80)
    proposed_changes: dict[str, str | int | float | bool | None] = Field(
        default_factory=dict
    )


class CalibrationDecisionAction(BaseModel):
    status: Literal["approved", "rejected"]
    decision_notes: str = Field(min_length=3, max_length=2000)


class CalibrationDecisionRead(BaseModel):
    id: UUID
    scope_key: str
    decision_type: str
    status: str
    title: str
    rationale: str
    current_methodology_version: str | None
    proposed_methodology_version: str | None
    proposed_changes: dict[str, object]
    evidence_snapshot: dict[str, object]
    sample_count: int
    minimum_sample_required: int
    approval_blocked: bool
    proposed_by_user_id: UUID | None
    decided_by_user_id: UUID | None
    decision_notes: str | None
    decided_at: datetime | None
    created_at: datetime
    updated_at: datetime


class CalibrationOverview(BaseModel):
    overall: CalibrationMetricSummary
    markets: list[CalibrationMetricSummary]
    provider_scorecards: list[CalibrationMetricSummary]
    cases: list[CalibrationCaseRead]
    decisions: list[CalibrationDecisionRead]
    uncalibrated_analysis_count: int
    minimum_sample_for_formula_review: int = 50
    automatic_formula_changes_enabled: bool = False
