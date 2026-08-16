from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class MarketingCampaignPerformance(BaseModel):
    source: str
    medium: str
    campaign: str
    page_views: int
    form_starts: int
    form_abandons: int
    form_submits: int
    call_clicks: int
    leads_created: int
    contracted_leads: int
    collected_revenue_cents: int
    marketing_spend_cents: int
    cost_per_lead_cents: int | None
    cost_per_contract_cents: int | None
    return_on_ad_spend_basis_points: int | None


class OfflineConversionExportRead(BaseModel):
    id: UUID
    platform: str
    conversion_event_id: UUID | None
    lead_id: UUID | None
    revenue_record_id: UUID | None
    event_key: str
    source_record_type: str
    source_record_id: UUID
    event_name: str
    occurred_at: datetime
    attribution_model: str
    consent_basis: str
    masked_click_id: str
    click_id_type: str
    value_cents: int | None
    currency: str
    delivery_mode: str
    status: str
    attempt_count: int
    last_attempt_at: datetime | None
    next_attempt_at: datetime | None
    exported_at: datetime | None
    provider_request_id: str | None
    provider_accepted_count: int | None
    provider_warnings: list[str]
    last_error: str | None
    created_at: datetime


class MarketingSummary(BaseModel):
    total_spend_cents: int
    collected_revenue_cents: int
    leads_created: int
    contracted_leads: int
    cost_per_lead_cents: int | None
    cost_per_contract_cents: int | None
    return_on_ad_spend_basis_points: int | None
    pending_offline_exports: int


class PublicFunnelSummary(BaseModel):
    page_views: int
    offer_starts: int
    form_starts: int
    step_completions: dict[str, int]
    validation_errors: int
    submit_attempts: int
    form_submits: int
    submit_errors: int
    form_abandons: int
    start_to_submit_rate_basis_points: int | None


class WebVitalSummary(BaseModel):
    metric: str
    sample_count: int
    p75_value: float
    good_rate_basis_points: int


class MarketingProviderReadiness(BaseModel):
    platform: str
    configured: bool
    blockers: list[str]
    delivery_mode: str | None = None
    test_mode_enabled: bool | None = None
    pixel_id_fingerprint: str | None = None
    access_token_present: bool | None = None


class MetaMatchCoverage(BaseModel):
    event_name: str
    total: int
    fbp_count: int
    fbc_count: int
    client_ip_count: int
    client_user_agent_count: int
    fbp_basis_points: int | None
    fbc_basis_points: int | None
    client_ip_basis_points: int | None
    client_user_agent_basis_points: int | None


class MarketingWorkerReadiness(BaseModel):
    status: str
    required: bool
    heartbeat_at: datetime | None
    consecutive_failures: int
    current_operation: str | None
    marketing_conversion_mode: str | None
    meta_pixel_id_fingerprint: str | None
    meta_test_mode_enabled: bool | None
    meta_configured: bool | None
    meta_configuration_blockers: list[str]
    meta_access_token_present: bool | None


class MarketingMeasurementSummary(BaseModel):
    mode: str
    attribution_model: str
    attribution_window_days: int
    policy_version: str
    providers: list[MarketingProviderReadiness]
    event_counts: dict[str, int]
    worker: MarketingWorkerReadiness
    meta_match_coverage: list[MetaMatchCoverage]
    meta_match_coverage_window_days: int
    oldest_meta_pending_at: datetime | None


class MarketingOverview(BaseModel):
    period_days: int | None
    period_start_at: datetime | None
    period_end_at: datetime
    previous_summary: MarketingSummary | None
    summary: MarketingSummary
    public_funnel: PublicFunnelSummary
    web_vitals: list[WebVitalSummary]
    measurement: MarketingMeasurementSummary
    campaigns: list[MarketingCampaignPerformance]
    offline_exports: list[OfflineConversionExportRead]


class OfflineConversionGenerateResponse(BaseModel):
    created: int


class OfflineConversionProcessResponse(BaseModel):
    processed_id: UUID | None
    status: str | None
