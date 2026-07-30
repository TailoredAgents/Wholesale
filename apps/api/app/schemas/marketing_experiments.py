from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, model_validator

ExperimentMetric = Literal[
    "form_submit",
    "qualified_lead",
    "appointment_scheduled",
    "contract_signed",
    "funded_deal",
]
ExperimentDecision = Literal["start", "pause", "resume", "complete", "return_to_draft"]


class MarketingExperimentVariant(BaseModel):
    key: str = Field(pattern=r"^[a-z][a-z0-9_]{0,39}$")
    label: str = Field(min_length=2, max_length=80)
    weight_basis_points: int = Field(ge=1, le=9999)
    cta_label: str = Field(min_length=2, max_length=40)


class MarketingExperimentCreate(BaseModel):
    experiment_key: str = Field(pattern=r"^[a-z][a-z0-9_]{2,79}$")
    name: str = Field(min_length=3, max_length=180)
    hypothesis: str = Field(min_length=10, max_length=1000)
    surface_key: Literal["homepage_offer_cta"] = "homepage_offer_cta"
    primary_metric: ExperimentMetric = "qualified_lead"
    variants: list[MarketingExperimentVariant] = Field(min_length=2, max_length=2)
    minimum_sessions_per_variant: int = Field(default=50, ge=20, le=100000)
    minimum_runtime_days: int = Field(default=14, ge=7, le=365)
    decision_rule: str = Field(min_length=10, max_length=1000)

    @model_validator(mode="after")
    def validate_variants(self) -> "MarketingExperimentCreate":
        keys = [variant.key for variant in self.variants]
        if len(set(keys)) != len(keys):
            raise ValueError("Experiment variant keys must be unique.")
        if sum(variant.weight_basis_points for variant in self.variants) != 10000:
            raise ValueError("Experiment variant weights must total 10,000 basis points.")
        if "control" not in keys:
            raise ValueError("One experiment variant must use the key 'control'.")
        return self


class MarketingExperimentUpdate(MarketingExperimentCreate):
    pass


class MarketingExperimentDecisionRequest(BaseModel):
    decision: ExperimentDecision
    reason: str = Field(min_length=3, max_length=2000)


class PublicExperimentRead(BaseModel):
    experiment_key: str
    surface_key: str
    variants: list[MarketingExperimentVariant]


class PublicExperimentResponse(BaseModel):
    experiments: list[PublicExperimentRead]


class ExperimentSourcePerformance(BaseModel):
    source: str
    medium: str
    campaign: str
    assigned_sessions: int
    leads_created: int
    qualified_leads: int
    contracts_signed: int
    funded_deals: int
    collected_revenue_cents: int


class ExperimentVariantPerformance(BaseModel):
    key: str
    label: str
    cta_label: str
    assigned_sessions: int
    desktop_sessions: int
    tablet_sessions: int
    mobile_sessions: int
    form_starts: int
    form_submits: int
    leads_created: int
    qualified_leads: int
    appointments_scheduled: int
    contracts_signed: int
    funded_deals: int
    collected_revenue_cents: int
    primary_outcomes: int
    primary_rate_basis_points: int | None
    source_breakdown: list[ExperimentSourcePerformance]


class MarketingExperimentRead(BaseModel):
    id: UUID
    experiment_key: str
    name: str
    hypothesis: str
    surface_key: str
    primary_metric: str
    variants: list[MarketingExperimentVariant]
    minimum_sessions_per_variant: int
    minimum_runtime_days: int
    decision_rule: str
    status: str
    started_at: datetime | None
    paused_at: datetime | None
    completed_at: datetime | None
    decision_notes: str | None
    runtime_days: int
    decision_status: str
    decision_blockers: list[str]
    performance: list[ExperimentVariantPerformance]
    created_at: datetime
    updated_at: datetime


class MarketingExperimentOverview(BaseModel):
    can_manage: bool
    experiments: list[MarketingExperimentRead]
