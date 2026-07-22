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
    evidence_reference: str | None
    notes: str | None
    recorded_by_user_id: UUID | None
    created_at: datetime
    updated_at: datetime


class CalibrationMetricSummary(BaseModel):
    market_key: str
    sample_count: int
    median_error_percentage: float | None
    median_absolute_error_percentage: float | None
    range_coverage_percentage: float | None
    overestimate_count: int
    underestimate_count: int
    balanced_count: int
    repair_sample_count: int
    repair_median_absolute_error_percentage: float | None
    disposition_sample_count: int
    disposition_median_absolute_error_percentage: float | None
    readiness: str


class CalibrationOverview(BaseModel):
    overall: CalibrationMetricSummary
    markets: list[CalibrationMetricSummary]
    cases: list[CalibrationCaseRead]
    uncalibrated_analysis_count: int
    minimum_sample_for_formula_review: int = 50
    automatic_formula_changes_enabled: bool = False
