from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, Field


class BuyerCriteriaCreate(BaseModel):
    markets: str | None = Field(default=None, max_length=500)
    property_types: str | None = Field(default=None, max_length=500)
    min_price_cents: int | None = Field(default=None, ge=0)
    max_price_cents: int | None = Field(default=None, ge=0)
    rehab_levels: str | None = Field(default=None, max_length=500)
    notes: str | None = Field(default=None, max_length=1000)


class BuyerCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    company_name: str | None = Field(default=None, max_length=255)
    email: str | None = Field(default=None, max_length=320)
    phone: str | None = Field(default=None, max_length=80)
    buyer_type: str = Field(default="cash_buyer", max_length=80)
    status: str = Field(default="active", max_length=80)
    proof_of_funds_status: str = Field(default="unknown", max_length=80)
    max_purchase_price_cents: int | None = Field(default=None, ge=0)
    notes: str | None = Field(default=None, max_length=2000)
    phone_contact_permission: bool = False
    sms_consent: bool = False
    criteria: BuyerCriteriaCreate | None = None


class BuyerCriteriaRead(BaseModel):
    markets: str | None
    property_types: str | None
    min_price_cents: int | None
    max_price_cents: int | None
    rehab_levels: str | None
    notes: str | None


class BuyerRead(BaseModel):
    id: UUID
    name: str
    company_name: str | None
    email: str | None
    phone: str | None
    buyer_type: str
    status: str
    proof_of_funds_status: str
    max_purchase_price_cents: int | None
    reliability_score_basis_points: int
    completed_deals: int
    failed_deals: int
    proof_of_funds_expires_at: datetime | None
    notes: str | None
    criteria: BuyerCriteriaRead | None
    created_at: datetime


class BuyerListResponse(BaseModel):
    items: list[BuyerRead]


class BuyerConversationRead(BaseModel):
    conversation_id: UUID


class BuyerDataProviderRead(BaseModel):
    provider: str
    configured: bool
    live_search_enabled: bool
    message: str
    connected: bool | None = None
    plan_name: str | None = None
    is_paid: bool | None = None
    billing_cycle_end: datetime | None = None
    credits_remaining: int | None = None
    credits_used: int | None = None
    credits_total: int | None = None


class BuyerDiscoveryEstimateCreate(BaseModel):
    disposition_case_id: UUID
    max_candidates: int = Field(default=25, ge=5, le=100)


class BuyerDiscoveryCreate(BuyerDiscoveryEstimateCreate):
    confirmed_estimated_credits: int = Field(ge=0)


class BuyerDiscoveryEstimateRead(BaseModel):
    disposition_case_id: UUID
    requested_candidates: int
    provider_result_limit: int
    total_matching_properties: int
    estimated_credits: int
    estimated_property_credits: int
    estimated_people_credits: int
    credits_remaining: int
    enough_credits: bool
    message: str


class BuyerDiscoveryCandidateRead(BaseModel):
    id: UUID
    buyer_id: UUID | None
    provider: str
    name: str
    company_name: str | None
    email: str | None
    phone: str | None
    market: str
    state: str
    property_types: list[str]
    observed_purchase_count: int
    no_mortgage_count: int
    last_purchase_date: date | None
    min_purchase_price_cents: int | None
    max_purchase_price_cents: int | None
    score_basis_points: int
    score_components: dict[str, int]
    evidence_snapshot: dict[str, object]
    status: str


class BuyerDiscoveryRunRead(BaseModel):
    id: UUID
    disposition_case_id: UUID
    provider: str
    status: str
    search_snapshot: dict[str, object]
    result_count: int
    imported_count: int
    credit_summary: dict[str, object] | None
    error_message: str | None
    completed_at: datetime | None
    candidates: list[BuyerDiscoveryCandidateRead]
    created_at: datetime


class BuyerDiscoveryImport(BaseModel):
    candidate_ids: list[UUID] = Field(min_length=1, max_length=100)
