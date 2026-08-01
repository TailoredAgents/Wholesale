from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field


ValidationScenario = Literal[
    "dense_market",
    "suburban",
    "rural",
    "unique_property",
    "low_comp",
    "wrong_address",
    "provider_failure",
    "high_risk_repairs",
]


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
    validation_scenarios: list[ValidationScenario] = Field(
        default_factory=list,
        max_length=8,
    )


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
    validation_scenarios: list[str]
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


class CalibrationSegmentSummary(BaseModel):
    dimension: str
    segment_key: str
    sample_count: int
    median_absolute_error_percentage: float | None
    range_coverage_percentage: float | None
    repair_sample_count: int
    repair_median_absolute_error_percentage: float | None
    comp_review_override_percentage: float | None


class UnderwritingBaselineSummary(BaseModel):
    analysis_count: int
    instrumented_analysis_count: int
    methodology_versions: list[str]
    median_duration_ms: float | None
    median_provider_returned_comp_count: float | None
    median_candidate_comp_count: float | None
    median_selected_comp_count: float | None
    median_comp_yield_percentage: float | None
    market_data_reuse_count: int
    market_data_reuse_percentage: float | None
    manual_review_required_count: int
    manual_review_required_percentage: float | None
    comp_review_case_count: int
    comp_review_decision_count: int
    comp_review_override_count: int
    comp_review_override_percentage: float | None
    ai_scope_review_count: int
    ai_scope_correction_count: int
    ai_scope_correction_percentage: float | None
    repair_catalog_case_count: int
    repair_catalog_median_absolute_error_percentage: float | None


class ShadowReplayCaseRead(BaseModel):
    analysis_id: UUID
    lead_id: UUID
    property_address: str
    market_key: str
    benchmark_arv_cents: int
    baseline_arv_cents: int
    shadow_arv_cents: int
    baseline_absolute_error_percentage: float
    shadow_absolute_error_percentage: float
    improvement_percentage_points: float
    winner: Literal["v2.2", "v3_shadow", "tie"]
    shadow_status: str
    shadow_confidence_score: int | None
    validation_scenarios: list[str]
    risk_flags: list[str]


class ShadowReplayMetric(BaseModel):
    scope_key: str
    paired_case_count: int
    baseline_median_absolute_error_percentage: float | None
    shadow_median_absolute_error_percentage: float | None
    median_improvement_percentage_points: float | None
    shadow_win_count: int
    tie_count: int
    baseline_win_count: int
    shadow_supported_count: int
    shadow_partial_count: int
    shadow_unsupported_count: int
    unsafe_certainty_count: int


class UnderwritingRolloutGate(BaseModel):
    key: str
    label: str
    status: Literal["passed", "blocked", "pending"]
    current_value: str
    required_value: str
    detail: str


class UnderwritingShadowValidation(BaseModel):
    active_methodology_version: str = "v2.2"
    shadow_methodology_version: str = "v3.0-adjustment-shadow"
    rollout_status: str
    activation_allowed: bool
    rollback_available: bool = True
    human_authority_required: bool = True
    overall: ShadowReplayMetric
    markets: list[ShadowReplayMetric]
    cases: list[ShadowReplayCaseRead]
    gates: list[UnderwritingRolloutGate]
    scenario_coverage: dict[str, int]
    approved_rollout_decision_id: UUID | None


class CalibrationDecisionCreate(BaseModel):
    scope_key: str = Field(min_length=1, max_length=255)
    decision_type: Literal[
        "continue_current_method",
        "methodology_change",
        "provider_change",
        "v3_rollout",
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
    baseline: UnderwritingBaselineSummary
    overall: CalibrationMetricSummary
    markets: list[CalibrationMetricSummary]
    provider_scorecards: list[CalibrationMetricSummary]
    segments: list[CalibrationSegmentSummary]
    shadow_validation: UnderwritingShadowValidation
    cases: list[CalibrationCaseRead]
    decisions: list[CalibrationDecisionRead]
    uncalibrated_analysis_count: int
    minimum_sample_for_formula_review: int = 50
    automatic_formula_changes_enabled: bool = False
