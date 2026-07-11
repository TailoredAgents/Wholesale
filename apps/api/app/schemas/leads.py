from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class ContactCreate(BaseModel):
    legal_name: str = Field(min_length=1, max_length=255)
    preferred_name: str | None = Field(default=None, max_length=255)
    contact_type: str = Field(default="seller", max_length=80)


class PropertyCreate(BaseModel):
    street_address: str = Field(min_length=1, max_length=255)
    city: str = Field(min_length=1, max_length=120)
    state: str = Field(min_length=2, max_length=2)
    postal_code: str = Field(min_length=1, max_length=20)
    county: str | None = Field(default=None, max_length=120)
    property_type: str | None = Field(default=None, max_length=80)


class LeadCreate(BaseModel):
    contact: ContactCreate
    property: PropertyCreate
    source: str = Field(default="manual", max_length=120)
    stage_key: str = Field(default="new", max_length=120)
    lead_temperature: str | None = Field(default=None, max_length=80)


class LeadRead(BaseModel):
    id: UUID
    contact_id: UUID
    property_id: UUID
    source: str
    stage_key: str
    lead_temperature: str | None
    seller_name: str
    property_address: str
    assigned_user_email: str | None
    created_at: datetime


class LeadListResponse(BaseModel):
    items: list[LeadRead]


class ContactMethodRead(BaseModel):
    method_type: str
    value: str
    is_primary: bool


class ConsentRecordRead(BaseModel):
    channel: str
    status: str
    source: str
    wording_version: str
    captured_ip: str | None
    created_at: datetime


class AttributionTouchRead(BaseModel):
    touch_type: str
    source: str | None
    medium: str | None
    campaign: str | None
    term: str | None
    content: str | None
    gclid: str | None
    fbclid: str | None
    landing_page: str | None
    referrer: str | None
    created_at: datetime


class ActivityEventRead(BaseModel):
    event_type: str
    summary: str
    created_at: datetime


class LeadDetail(LeadRead):
    contact_methods: list[ContactMethodRead]
    consent_records: list[ConsentRecordRead]
    attribution_touches: list[AttributionTouchRead]
    recent_activity: list[ActivityEventRead]


class LeadStageUpdate(BaseModel):
    stage_key: str = Field(min_length=1, max_length=120)
    reason: str | None = Field(default=None, max_length=500)


class PipelineStageCount(BaseModel):
    stage_key: str
    count: int


class DashboardSummary(BaseModel):
    total_leads: int
    new_paid_leads: int
    active_contracts: int
    offers_pending: int
    collected_revenue_cents: int
    pipeline: list[PipelineStageCount]
