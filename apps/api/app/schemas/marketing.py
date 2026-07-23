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
    event_name: str
    click_id: str
    click_id_type: str
    value_cents: int | None
    currency: str
    status: str
    attempt_count: int
    exported_at: datetime | None
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


class MarketingOverview(BaseModel):
    period_days: int | None
    period_start_at: datetime | None
    period_end_at: datetime
    previous_summary: MarketingSummary | None
    summary: MarketingSummary
    campaigns: list[MarketingCampaignPerformance]
    offline_exports: list[OfflineConversionExportRead]


class OfflineConversionGenerateResponse(BaseModel):
    created: int
