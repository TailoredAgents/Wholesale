from datetime import date, datetime
from typing import Annotated, Literal
from uuid import UUID

from pydantic import (
    BaseModel,
    ConfigDict,
    EmailStr,
    Field,
    field_validator,
    model_validator,
)

BuyerAssetClass = Literal["house", "land"]
BuyerVerificationStatus = Literal["unverified", "needs_review", "verified", "rejected"]
BuyerTier = Literal["unclassified", "a", "b", "c"]
BuyerTemperature = Literal["unknown", "cold", "warm", "hot"]
BuyerRelationshipStatus = Literal[
    "new", "active", "nurture", "paused", "do_not_contact", "inactive"
]


class BuyerBuyBoxGeographyEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    jurisdiction: Literal["state", "county", "city", "postal_code", "radius"]
    value: str = Field(min_length=1, max_length=255)
    state: str | None = Field(default=None, min_length=2, max_length=2)
    latitude: float | None = Field(default=None, ge=-90, le=90)
    longitude: float | None = Field(default=None, ge=-180, le=180)
    radius_miles: float | None = Field(default=None, gt=0, le=500)

    @field_validator("value")
    @classmethod
    def normalize_value(cls, value: str) -> str:
        normalized = " ".join(value.split())
        if not normalized:
            raise ValueError("Geography value is required.")
        return normalized

    @field_validator("state")
    @classmethod
    def normalize_state(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip().upper()
        if len(normalized) != 2 or not normalized.isalpha():
            raise ValueError("State must be a two-letter code.")
        return normalized

    @model_validator(mode="after")
    def validate_radius(self) -> "BuyerBuyBoxGeographyEntry":
        radius_values = (self.latitude, self.longitude, self.radius_miles)
        if self.jurisdiction in {"county", "city"} and self.state is None:
            raise ValueError("County and city geographies require a two-letter state code.")
        if self.jurisdiction == "state":
            normalized_state = self.value.strip().upper()
            if len(normalized_state) != 2 or not normalized_state.isalpha():
                raise ValueError("State geography must use a two-letter state code.")
            self.value = normalized_state
        if self.jurisdiction == "postal_code":
            postal_code = self.value.strip()
            if len(postal_code) == 10 and postal_code[5] == "-":
                postal_code = postal_code[:5]
            if len(postal_code) != 5 or not postal_code.isdigit():
                raise ValueError("Postal-code geography must use a five-digit ZIP code.")
            self.value = postal_code
        if self.jurisdiction == "radius" and any(value is None for value in radius_values):
            raise ValueError("Radius geography requires latitude, longitude, and radius_miles.")
        if self.jurisdiction != "radius" and any(value is not None for value in radius_values):
            raise ValueError("Coordinates and radius_miles are only valid for radius geography.")
        return self


class BuyerPurchaseCapacity(BaseModel):
    model_config = ConfigDict(extra="forbid")

    available_capital_cents: int | None = Field(default=None, ge=0)
    max_concurrent_purchases: int | None = Field(default=None, ge=0, le=10000)
    target_purchases_per_month: int | None = Field(default=None, ge=0, le=10000)


class BuyerBuyBoxCriteriaBase(BaseModel):
    model_config = ConfigDict(extra="forbid")

    geographies: list[BuyerBuyBoxGeographyEntry] = Field(default_factory=list, max_length=250)
    excluded_geographies: list[BuyerBuyBoxGeographyEntry] = Field(
        default_factory=list, max_length=250
    )
    strategies: list[
        Literal[
            "wholesale_assignment",
            "double_close",
            "fix_and_flip",
            "buy_and_hold",
            "wholetail",
            "novation",
            "new_construction",
            "development",
            "land_hold",
            "owner_finance",
        ]
    ] = Field(default_factory=list, max_length=20)
    min_price_cents: int | None = Field(default=None, ge=0)
    max_price_cents: int | None = Field(default=None, ge=0)
    funding_methods: list[
        Literal[
            "cash",
            "hard_money",
            "private_money",
            "conventional",
            "dscr",
            "seller_finance",
            "other",
        ]
    ] = Field(default_factory=list, max_length=20)
    capacity: BuyerPurchaseCapacity = Field(default_factory=BuyerPurchaseCapacity)
    exclusions: list[str] = Field(default_factory=list, max_length=100)

    @model_validator(mode="after")
    def validate_price_range(self) -> "BuyerBuyBoxCriteriaBase":
        if (
            self.min_price_cents is not None
            and self.max_price_cents is not None
            and self.min_price_cents > self.max_price_cents
        ):
            raise ValueError("Buy-box minimum price cannot exceed maximum price.")
        return self


class HouseBuyerBuyBoxCriteria(BuyerBuyBoxCriteriaBase):
    asset_class: Literal["house"] = "house"
    property_types: list[
        Literal[
            "single_family",
            "townhouse",
            "condo",
            "duplex",
            "triplex",
            "fourplex",
            "multifamily",
            "mobile_home",
            "other_residential",
        ]
    ] = Field(default_factory=list, max_length=20)
    rehab_tolerance: list[Literal["none", "light", "medium", "heavy", "full_gut"]] = Field(
        default_factory=list, max_length=5
    )
    occupancy_preferences: list[Literal["vacant", "owner_occupied", "tenant_occupied"]] = Field(
        default_factory=list, max_length=3
    )
    min_bedrooms: int | None = Field(default=None, ge=0, le=100)
    max_bedrooms: int | None = Field(default=None, ge=0, le=100)
    min_bathrooms: float | None = Field(default=None, ge=0, le=100)
    max_bathrooms: float | None = Field(default=None, ge=0, le=100)
    min_living_area_sqft: int | None = Field(default=None, ge=0)
    max_living_area_sqft: int | None = Field(default=None, ge=0)
    min_year_built: int | None = Field(default=None, ge=1700, le=2200)
    max_year_built: int | None = Field(default=None, ge=1700, le=2200)

    @model_validator(mode="after")
    def validate_house_ranges(self) -> "HouseBuyerBuyBoxCriteria":
        ranges = (
            (self.min_bedrooms, self.max_bedrooms, "bedroom"),
            (self.min_bathrooms, self.max_bathrooms, "bathroom"),
            (self.min_living_area_sqft, self.max_living_area_sqft, "living-area"),
            (self.min_year_built, self.max_year_built, "year-built"),
        )
        for minimum, maximum, label in ranges:
            if minimum is not None and maximum is not None and minimum > maximum:
                raise ValueError(f"Minimum {label} value cannot exceed its maximum.")
        return self


class LandBuyerBuyBoxCriteria(BuyerBuyBoxCriteriaBase):
    asset_class: Literal["land"] = "land"
    min_acres: float | None = Field(default=None, ge=0)
    max_acres: float | None = Field(default=None, ge=0)
    intended_uses: list[
        Literal[
            "residential",
            "agricultural",
            "recreational",
            "commercial",
            "industrial",
            "timber",
            "development",
            "hold",
        ]
    ] = Field(default_factory=list, max_length=20)
    zoning_codes: list[str] = Field(default_factory=list, max_length=100)
    access_preferences: list[
        Literal["paved_road", "gravel_road", "dirt_road", "legal_access", "landlocked_review"]
    ] = Field(default_factory=list, max_length=10)
    utility_preferences: list[
        Literal["electric", "public_water", "well", "public_sewer", "septic", "gas", "none"]
    ] = Field(default_factory=list, max_length=20)
    terrain_preferences: list[
        Literal["flat", "rolling", "sloped", "mountainous", "wooded", "cleared", "mixed"]
    ] = Field(default_factory=list, max_length=20)
    flood_zone_tolerance: Literal["avoid", "review", "accepted"] = "review"
    wetlands_tolerance: Literal["avoid", "review", "accepted"] = "review"

    @model_validator(mode="after")
    def validate_acreage_range(self) -> "LandBuyerBuyBoxCriteria":
        if (
            self.min_acres is not None
            and self.max_acres is not None
            and self.min_acres > self.max_acres
        ):
            raise ValueError("Minimum acreage cannot exceed maximum acreage.")
        return self


BuyerBuyBoxCriteria = Annotated[
    HouseBuyerBuyBoxCriteria | LandBuyerBuyBoxCriteria,
    Field(discriminator="asset_class"),
]


class BuyerBuyBoxPut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_version: int = Field(ge=0)
    source: str = Field(default="buyer_profile", min_length=1, max_length=80)
    change_reason: str = Field(min_length=2, max_length=500)
    verification_status: BuyerVerificationStatus = "unverified"
    criteria: BuyerBuyBoxCriteria

    @model_validator(mode="after")
    def require_matchable_verified_criteria(self) -> "BuyerBuyBoxPut":
        if self.verification_status != "verified":
            return self
        if not self.criteria.geographies:
            raise ValueError("A verified buy box requires at least one included geography.")
        if (
            self.criteria.min_price_cents is None
            and self.criteria.max_price_cents is None
        ):
            raise ValueError("A verified buy box requires a minimum or maximum price.")
        if isinstance(self.criteria, HouseBuyerBuyBoxCriteria) and not self.criteria.property_types:
            raise ValueError("A verified House buy box requires at least one property type.")
        return self


class BuyerBuyBoxVersionRead(BaseModel):
    id: UUID
    buy_box_id: UUID
    asset_class: BuyerAssetClass
    version_number: int
    is_current: bool
    criteria: BuyerBuyBoxCriteria
    source: str
    change_reason: str
    verification_status: BuyerVerificationStatus
    created_by_user_id: UUID
    verified_by_user_id: UUID | None
    verified_at: datetime | None
    effective_at: datetime
    superseded_at: datetime | None
    created_at: datetime


class BuyerBuyBoxSummaryRead(BaseModel):
    buy_box_id: UUID
    asset_class: BuyerAssetClass
    current_version: int
    verification_status: BuyerVerificationStatus
    verified_at: datetime | None
    updated_at: datetime
    criteria: BuyerBuyBoxCriteria


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
    tier: BuyerTier = "unclassified"
    temperature: BuyerTemperature = "unknown"
    tags: list[str] = Field(default_factory=list, max_length=100)
    relationship_status: BuyerRelationshipStatus = "new"
    next_follow_up_at: datetime | None = None
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
    tier: BuyerTier | None = None
    temperature: BuyerTemperature | None = None
    tags: list[str] | None = Field(default=None, max_length=100)
    relationship_status: BuyerRelationshipStatus | None = None
    next_follow_up_at: datetime | None = None
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
    tier: BuyerTier
    temperature: BuyerTemperature
    tags: list[str]
    relationship_status: BuyerRelationshipStatus
    next_follow_up_at: datetime | None
    verification_status: BuyerVerificationStatus
    verified_by_user_id: UUID | None
    verified_at: datetime | None
    last_contact_at: datetime | None
    asset_focus: Literal["house", "land", "both"] | None
    buy_boxes: list[BuyerBuyBoxSummaryRead]
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


class BuyerLegacyCriteriaRead(BaseModel):
    verification_status: Literal["unverified"] = "unverified"
    criteria: BuyerCriteriaRead


class BuyerTimelineItemRead(BaseModel):
    id: UUID
    category: Literal["relationship", "communication", "activity", "deal"]
    event_type: str
    occurred_at: datetime
    status: str | None = None
    summary: str
    body: str | None = None
    direction: str | None = None
    channel: str | None = None
    disposition_case_id: UUID | None = None


class BuyerTimelinePageRead(BaseModel):
    items: list[BuyerTimelineItemRead]
    total: int
    limit: int
    offset: int
    has_more: bool


class BuyerProfileRead(BaseModel):
    buyer: BuyerRead
    asset_focus: Literal["house", "land", "both"] | None
    legacy_criteria: BuyerLegacyCriteriaRead | None
    criteria_versions: list[BuyerBuyBoxVersionRead]
    timeline: BuyerTimelinePageRead


class BuyerRelationshipActivityCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    engagement_type: Literal["note", "follow_up"]
    scheduled_at: datetime | None = None
    notes: str = Field(min_length=1, max_length=1000)

    @model_validator(mode="after")
    def require_follow_up_schedule(self) -> "BuyerRelationshipActivityCreate":
        if self.engagement_type == "follow_up" and self.scheduled_at is None:
            raise ValueError("A relationship follow-up requires scheduled_at.")
        return self


class BuyerRelationshipActivityUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["open", "completed", "cancelled"]


class BuyerRelationshipActivityRead(BaseModel):
    id: UUID
    buyer_id: UUID
    engagement_type: Literal["note", "follow_up"]
    status: str
    scheduled_at: datetime | None
    occurred_at: datetime
    completed_at: datetime | None
    notes: str | None
    actor_user_id: UUID


class BuyerProfileVerificationCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    verification_status: Literal["verified", "needs_review", "rejected"]
    reason: str | None = Field(default=None, max_length=500)

    @model_validator(mode="after")
    def require_review_reason(self) -> "BuyerProfileVerificationCreate":
        normalized = " ".join((self.reason or "").split())
        if self.verification_status in {"needs_review", "rejected"} and len(normalized) < 2:
            raise ValueError("A reason is required when a buyer needs review or is rejected.")
        self.reason = normalized or None
        return self


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


BuyerDiscoverySearchTier = Literal["best_fit", "expanded", "regional"]


class BuyerDiscoveryEstimateCreate(BaseModel):
    disposition_case_id: UUID
    max_candidates: int = Field(default=10, ge=5, le=100)
    search_tier: BuyerDiscoverySearchTier | None = None


class BuyerDiscoveryCreate(BuyerDiscoveryEstimateCreate):
    confirmed_estimated_credits: int = Field(ge=0)
    confirmed_request_fingerprint: str = Field(
        min_length=64,
        max_length=64,
        pattern=r"^[0-9a-f]{64}$",
    )


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
    request_fingerprint: str
    search_tier: BuyerDiscoverySearchTier = "expanded"
    target_candidates: int = 20
    estimated_credit_cap: int = 60
    estimated_cost_usd: float = 0
    cumulative_case_credits: int = 0
    cumulative_case_credit_cap: int = 250
    monthly_credits: int = 0
    monthly_credit_cap: int = 2000
    reused: bool = False
    reused_run_id: UUID | None = None


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
    search_tier: BuyerDiscoverySearchTier = "expanded"
    target_candidates: int = 20
    estimated_credit_cap: int = 60
    estimated_credits: int = 0
    actual_credits: int | None = None
    estimated_cost_usd: float = 0
    actual_cost_usd: float | None = None
    cumulative_case_credits: int = 0
    cumulative_case_credit_cap: int = 250
    monthly_credits: int = 0
    monthly_credit_cap: int = 2000
    reused: bool = False
    reused_run_id: UUID | None = None


class BuyerDiscoveryTierStatusRead(BaseModel):
    search_tier: BuyerDiscoverySearchTier
    target_candidates: int
    estimated_credit_cap: int
    maximum_estimated_cost_usd: float
    completed: bool
    unlocked: bool
    latest_run: BuyerDiscoveryRunRead | None = None


class BuyerDiscoverySummaryRead(BaseModel):
    disposition_case_id: UUID
    provider: str
    completed_tiers: list[BuyerDiscoverySearchTier]
    unlocked_tiers: list[BuyerDiscoverySearchTier]
    next_tier: BuyerDiscoverySearchTier | None
    cumulative_case_credits: int
    cumulative_case_credit_cap: int = 250
    monthly_credits: int
    monthly_credit_cap: int = 2000
    approximate_cost_per_credit_usd: float = 0.0075
    tier_statuses: list[BuyerDiscoveryTierStatusRead]


class BuyerDiscoveryImport(BaseModel):
    candidate_ids: list[UUID] = Field(min_length=1, max_length=100)
