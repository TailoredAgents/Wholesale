from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field

MetricState = Literal["known", "partial", "unavailable"]


class DispositionIntelligenceFilters(BaseModel):
    deal_id: UUID | None = None
    buyer_id: UUID | None = None
    agent_user_id: UUID | None = None
    source: str | None = None
    market: str | None = None
    asset_class: str | None = None
    start_at: datetime | None = None
    end_at: datetime | None = None


class DispositionIntelligenceScope(BaseModel):
    start_at: datetime | None
    end_at: datetime | None
    filters_applied: DispositionIntelligenceFilters


class DispositionIntelligenceAccess(BaseModel):
    private_economics_visible: bool


class IntelligenceDataQuality(BaseModel):
    key: str
    label: str
    state: MetricState
    detail: str
    record_count: int = 0


class DispositionActivityMetrics(BaseModel):
    cases: int = 0
    packages_approved: int = 0
    outreach_sent: int = 0
    replies: int = 0
    inquiries: int = 0
    showings: int = 0
    offers: int = 0
    selected_buyers: int = 0
    deposits: int = 0


class DispositionEconomicsMetrics(BaseModel):
    state: MetricState
    completed_assignments: int = 0
    reconciled_completed_assignments: int = 0
    contracted_assignment_spread_cents: int | None = None
    collected_revenue_cents: int | None = None
    approved_company_profit_cents: int | None = None
    campaign_cost_cents: int | None = None
    cost_per_offer_cents: int | None = None
    cost_per_selected_buyer_cents: int | None = None
    cost_per_completed_assignment_cents: int | None = None
    detail: str


class DispositionMilestoneMetric(BaseModel):
    key: str
    label: str
    state: MetricState
    count: int = 0
    median_hours: float | None = None
    p90_hours: float | None = None


class DispositionRateMetric(BaseModel):
    key: str
    label: str
    state: MetricState
    numerator: int = 0
    denominator: int = 0
    rate_percent: float | None = None


class DispositionSourceMetric(BaseModel):
    key: str
    label: str
    category: str
    state: MetricState
    activity_count: int = 0
    offers: int = 0
    selected_buyers: int = 0
    completed_assignments: int = 0
    collected_revenue_cents: int | None = None


class DispositionBuyerMetric(BaseModel):
    buyer_id: UUID
    name: str
    state: MetricState
    replies: int = 0
    showings: int = 0
    offers: int = 0
    selections: int = 0
    completed_assignments: int = 0
    fallouts: int = 0
    retrades: int = 0
    reliability_score_basis_points: int | None
    provenance: str


class DispositionAgentMetric(BaseModel):
    user_id: UUID
    name: str
    state: MetricState
    role: str
    packages_approved: int = 0
    outreach_sent: int = 0
    replies_reviewed: int = 0
    selections_approved: int = 0
    outcomes_recorded: int = 0
    completed_assignments: int = 0


class DispositionCorrectionMetrics(BaseModel):
    package_revisions: int = 0
    match_overrides: int = 0
    ai_corrections: int = 0
    backup_buyer_saves: int = 0


class DispositionLearningMetrics(BaseModel):
    state: MetricState
    human_led_count: int = 0
    ai_assisted_count: int = 0
    minimum_comparison_sample: int = 10
    comparison_allowed: bool = False
    notice: str
    corrections: DispositionCorrectionMetrics


class DispositionMetricProvenance(BaseModel):
    metric_key: str
    state: MetricState
    canonical_sources: list[str]
    definition: str


class DispositionFilterOption(BaseModel):
    value: str
    label: str
    count: int = Field(default=0, ge=0)


class DispositionFilterOptions(BaseModel):
    deals: list[DispositionFilterOption]
    buyers: list[DispositionFilterOption]
    agents: list[DispositionFilterOption]
    sources: list[DispositionFilterOption]
    markets: list[DispositionFilterOption]
    asset_classes: list[DispositionFilterOption]


class DispositionIntelligenceResponse(BaseModel):
    generated_at: datetime
    scope: DispositionIntelligenceScope
    access: DispositionIntelligenceAccess
    data_state: MetricState
    data_quality: list[IntelligenceDataQuality]
    activity: DispositionActivityMetrics
    economics: DispositionEconomicsMetrics
    milestones: list[DispositionMilestoneMetric]
    rates: list[DispositionRateMetric]
    sources: list[DispositionSourceMetric]
    buyers: list[DispositionBuyerMetric]
    agents: list[DispositionAgentMetric]
    learning: DispositionLearningMetrics
    provenance: list[DispositionMetricProvenance]
    filter_options: DispositionFilterOptions
