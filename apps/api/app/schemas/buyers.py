from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field, field_validator, model_validator


class BuyerCriteriaCreate(BaseModel):
    markets: str | None = Field(default=None, max_length=500)
    property_types: str | None = Field(default=None, max_length=500)
    min_price_cents: int | None = Field(default=None, ge=0)
    max_price_cents: int | None = Field(default=None, ge=0)
    rehab_levels: str | None = Field(default=None, max_length=500)
    notes: str | None = Field(default=None, max_length=1000)


class BuyerCriteriaUpdate(BaseModel):
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
    status: str = Field(default="needs_review", max_length=80)
    source_key: str = Field(default="manual", min_length=1, max_length=80)
    source_detail: str | None = Field(default=None, max_length=255)
    source_external_key: str | None = Field(default=None, max_length=255)
    relationship_owner_user_id: UUID | None = None
    last_verified_at: datetime | None = None
    proof_of_funds_status: str = Field(default="unknown", max_length=80)
    max_purchase_price_cents: int | None = Field(default=None, ge=0)
    notes: str | None = Field(default=None, max_length=2000)
    phone_contact_permission: bool = False
    sms_consent: bool = False
    permission_evidence_source: str = Field(
        default="buyer_crm_manual", min_length=1, max_length=120
    )
    allow_separate_record: bool = False
    separate_record_reason: str | None = Field(default=None, max_length=500)
    criteria: BuyerCriteriaCreate | None = None

    @model_validator(mode="after")
    def require_contact_identity(self) -> "BuyerCreate":
        if self.email is None and not (self.phone or "").strip():
            raise ValueError("A buyer requires at least one valid phone number or email address.")
        return self


class BuyerUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    company_name: str | None = Field(default=None, max_length=255)
    email: str | None = Field(default=None, max_length=320)
    phone: str | None = Field(default=None, max_length=80)
    buyer_type: str | None = Field(default=None, max_length=80)
    status: str | None = Field(default=None, max_length=80)
    source_key: str | None = Field(default=None, min_length=1, max_length=80)
    source_detail: str | None = Field(default=None, max_length=255)
    source_external_key: str | None = Field(default=None, max_length=255)
    relationship_owner_user_id: UUID | None = None
    last_verified_at: datetime | None = None
    proof_of_funds_status: str | None = Field(default=None, max_length=80)
    max_purchase_price_cents: int | None = Field(default=None, ge=0)
    notes: str | None = Field(default=None, max_length=2000)
    phone_contact_permission: bool | None = None
    sms_consent: bool | None = None
    permission_evidence_source: str = Field(
        default="buyer_crm_manual", min_length=1, max_length=120
    )
    allow_separate_record: bool = False
    separate_record_reason: str | None = Field(default=None, max_length=500)
    criteria: BuyerCriteriaUpdate | None = None


class BuyerArchiveRequest(BaseModel):
    reason: str = Field(min_length=2, max_length=500)

    @field_validator("reason")
    @classmethod
    def require_meaningful_reason(cls, value: str) -> str:
        normalized = value.strip()
        if len(normalized) < 2:
            raise ValueError("Archive reason must contain at least 2 characters.")
        return normalized


class BuyerDuplicatePreflightRequest(BaseModel):
    email: EmailStr | None = None
    phone: str | None = Field(default=None, max_length=80)
    company_name: str | None = Field(default=None, max_length=255)
    exclude_buyer_id: UUID | None = None

    @model_validator(mode="after")
    def require_identity(self) -> "BuyerDuplicatePreflightRequest":
        if (
            self.email is None
            and not (self.phone or "").strip()
            and not (self.company_name or "").strip()
        ):
            raise ValueError("Email, phone, or company name is required for duplicate checking.")
        return self


class BuyerCriteriaRead(BaseModel):
    version_number: int
    markets: str | None
    property_types: str | None
    min_price_cents: int | None
    max_price_cents: int | None
    rehab_levels: str | None
    notes: str | None


class BuyerPermissionEvidenceRead(BaseModel):
    status: str
    source: str | None
    recorded_at: datetime | None
    normalized_address: str | None
    wording_version: str | None


class BuyerPermissionHistoryRead(BuyerPermissionEvidenceRead):
    channel: str


class BuyerOwnerOptionRead(BaseModel):
    user_id: UUID
    display_name: str
    email: str


class BuyerDuplicateMatchRead(BaseModel):
    buyer_id: UUID
    name: str
    company_name: str | None
    email: str | None
    phone: str | None
    status: str
    matched_fields: list[str]
    reasons: list[str]


class BuyerDuplicatePreflightRead(BaseModel):
    has_matches: bool
    normalized_email: str | None
    normalized_phone: str | None
    normalized_company_name: str | None
    matches: list[BuyerDuplicateMatchRead]


class BuyerRead(BaseModel):
    id: UUID
    name: str
    company_name: str | None
    email: str | None
    phone: str | None
    normalized_email: str | None
    normalized_phone: str | None
    buyer_type: str
    status: str
    source_key: str
    source_detail: str | None
    source_external_key: str | None
    created_by_user_id: UUID | None
    created_by_name: str | None
    created_by_email: str | None
    relationship_owner_user_id: UUID | None
    relationship_owner_name: str | None
    last_verified_at: datetime | None
    archived_at: datetime | None
    archived_by_user_id: UUID | None
    archive_reason: str | None
    proof_of_funds_status: str
    max_purchase_price_cents: int | None
    reliability_score_basis_points: int
    completed_deals: int
    failed_deals: int
    proof_of_funds_expires_at: datetime | None
    notes: str | None
    phone_permission: BuyerPermissionEvidenceRead
    sms_permission: BuyerPermissionEvidenceRead
    permission_history: list[BuyerPermissionHistoryRead]
    criteria: BuyerCriteriaRead | None
    created_at: datetime
    updated_at: datetime


class BuyerListResponse(BaseModel):
    items: list[BuyerRead]
    total: int
    limit: int
    offset: int
    has_more: bool
    owner_options: list[BuyerOwnerOptionRead]
    source_options: list[str]


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
