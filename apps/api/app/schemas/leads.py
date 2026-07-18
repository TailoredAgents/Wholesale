from datetime import datetime
from typing import Any, Literal
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
    motivation: str | None = Field(default=None, max_length=500)
    desired_timeline: str | None = Field(default=None, max_length=120)
    property_condition: str | None = Field(default=None, max_length=120)
    occupancy_status: str | None = Field(default=None, max_length=120)
    asking_price: str | None = Field(default=None, max_length=120)
    mortgage_balance: str | None = Field(default=None, max_length=120)
    appointment_status: str | None = Field(default=None, max_length=120)
    next_follow_up_at: datetime | None = None


class LeadRead(BaseModel):
    id: UUID
    contact_id: UUID
    property_id: UUID
    source: str
    stage_key: str
    lead_temperature: str | None
    seller_name: str
    preferred_name: str | None
    property_address: str
    property_street_address: str
    property_city: str
    property_state: str
    property_postal_code: str
    property_county: str | None
    property_type: str | None
    assigned_user_email: str | None
    motivation: str | None
    desired_timeline: str | None
    property_condition: str | None
    occupancy_status: str | None
    asking_price: str | None
    mortgage_balance: str | None
    appointment_status: str | None
    next_follow_up_at: datetime | None
    archived_at: datetime | None
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


class LeadTaskRead(BaseModel):
    id: UUID
    task_type: str
    title: str
    status: str
    priority: str
    due_at: datetime | None
    completed_at: datetime | None


class CommunicationRecordRead(BaseModel):
    id: UUID
    direction: str
    channel: str
    status: str
    provider: str
    provider_message_id: str | None
    subject: str | None
    body: str
    occurred_at: datetime
    created_at: datetime


class AppointmentRead(BaseModel):
    id: UUID
    appointment_type: str
    status: str
    scheduled_start_at: datetime
    scheduled_end_at: datetime | None
    location_type: str
    location: str | None
    notes: str | None
    outcome: str | None
    created_at: datetime


class UnderwritingVersionRead(BaseModel):
    id: UUID
    version_number: int
    status: str
    arv_low_cents: int | None
    arv_high_cents: int | None
    repair_low_cents: int | None
    repair_high_cents: int | None
    max_offer_cents: int | None
    recommended_offer_cents: int | None
    offer_strategy: str | None
    notes: str | None
    source: str
    created_at: datetime


class MarketComparableRead(BaseModel):
    provider_id: str | None
    formatted_address: str | None
    status: str | None
    listing_type: str | None
    property_type: str | None
    price_cents: int | None
    bedrooms: float | None
    bathrooms: float | None
    square_footage: int | None
    year_built: int | None
    distance_miles: float | None
    days_old: int | None
    correlation: float | None
    listed_date: str | None
    removed_date: str | None
    last_seen_date: str | None
    sale_date: str | None = None
    price_source: str | None = None
    verification_status: str | None = None
    condition_classification: str | None = None
    condition_evidence: str | None = None
    lot_size: int | None = None
    adjusted_value_cents: int | None = None
    price_per_square_foot_cents: int | None = None
    weight: float | None = None


class LeadMarketValueEstimateRead(BaseModel):
    lead_id: UUID
    property_id: UUID
    provider: str
    requested_address: str
    estimated_value_cents: int | None
    estimated_value_low_cents: int | None
    estimated_value_high_cents: int | None
    subject_property: dict[str, Any]
    comparables: list[MarketComparableRead]
    human_review_required: bool = True
    source_note: str


class MarketAnalysisCompRead(MarketComparableRead):
    selection_status: str
    selection_reason: str
    score: int


RepairCategory = Literal[
    "roof",
    "hvac",
    "plumbing",
    "electrical",
    "foundation",
    "kitchen",
    "bathrooms",
    "flooring",
    "paint_drywall",
    "windows_doors",
    "exterior",
    "landscaping",
    "permits",
    "cleanup",
    "other",
]


class UnderwritingRepairItemInput(BaseModel):
    category: RepairCategory
    estimated_cost_cents: int = Field(ge=1, le=100_000_000)
    details: str | None = Field(default=None, max_length=500)


class UnderwritingPreMeetingInputsRead(BaseModel):
    verification_status: str
    report_stage: str
    current_condition: str | None
    target_condition: str
    repair_level: str
    repair_estimate_source: str
    base_rehab_override_cents: int | None
    repair_items: list[UnderwritingRepairItemInput]
    contingency_override_percentage: int | None
    holding_period_months: int
    repair_notes: str | None
    custom_inputs_applied: bool


class LeadMarketAnalysisCreate(BaseModel):
    target_condition: str = Field(default="standard_flip", max_length=80)
    current_condition: str | None = Field(default=None, max_length=80)
    repair_level: str | None = Field(default=None, max_length=80)
    input_verification_status: Literal[
        "preliminary",
        "pre_meeting_reviewed",
        "walkthrough_verified",
    ] = "preliminary"
    base_rehab_override_cents: int | None = Field(
        default=None,
        ge=0,
        le=100_000_000,
    )
    repair_items: list[UnderwritingRepairItemInput] = Field(default_factory=list, max_length=25)
    contingency_override_percentage: int | None = Field(default=None, ge=0, le=50)
    holding_period_months: int = Field(default=6, ge=1, le=24)
    repair_notes: str | None = Field(default=None, max_length=2000)
    comp_condition_overrides: dict[str, str] = Field(default_factory=dict)
    refresh_market_data: bool = False


class LeadMarketAnalysisRead(BaseModel):
    id: UUID
    lead_id: UUID
    property_id: UUID
    underwriting_version_id: UUID | None
    provider: str
    requested_address: str
    estimated_value_cents: int | None
    estimated_value_low_cents: int | None
    estimated_value_high_cents: int | None
    arv_low_cents: int | None
    arv_high_cents: int | None
    repair_low_cents: int | None
    repair_high_cents: int | None
    mao_low_cents: int | None
    mao_high_cents: int | None
    recommended_offer_cents: int | None
    assignment_fee_cents: int | None
    offer_low_percentage: int
    offer_high_percentage: int
    confidence_score: int
    selected_comps: list[MarketAnalysisCompRead]
    rejected_comps: list[MarketAnalysisCompRead]
    source_note: str
    created_at: datetime
    methodology_version: str = "v1"
    as_is_value_low_cents: int | None = None
    as_is_value_cents: int | None = None
    as_is_value_high_cents: int | None = None
    arv_point_cents: int | None = None
    conservative_arv_cents: int | None = None
    base_rehab_cents: int | None = None
    rehab_contingency_percentage: int | None = None
    total_rehab_cents: int | None = None
    flip_buyer_max_cents: int | None = None
    rental_buyer_max_cents: int | None = None
    recommended_disposition_cents: int | None = None
    seller_contract_ceiling_cents: int | None = None
    transaction_reserve_cents: int | None = None
    monthly_rent_cents: int | None = None
    manual_review_required: bool = True
    review_reasons: list[str] = Field(default_factory=list)
    data_disagreements: list[str] = Field(default_factory=list)
    assumptions: dict[str, Any] = Field(default_factory=dict)
    report_stage: str = "preliminary"
    pre_meeting_inputs: UnderwritingPreMeetingInputsRead | None = None


class TransactionChecklistItemRead(BaseModel):
    id: UUID
    title: str
    status: str
    due_at: datetime | None
    completed_at: datetime | None
    sort_order: int


class TransactionRead(BaseModel):
    id: UUID
    deal_id: UUID
    status: str
    contract_type: str
    purchase_price_cents: int
    assignment_fee_cents: int | None
    earnest_money_cents: int | None
    title_company: str | None
    closing_date: datetime | None
    inspection_period_days: int | None
    contract_sent_at: datetime | None
    contract_executed_at: datetime | None
    notes: str | None
    checklist_items: list[TransactionChecklistItemRead]
    created_at: datetime


class BuyerOfferRead(BaseModel):
    id: UUID
    buyer_id: UUID
    buyer_name: str
    amount_cents: int
    earnest_money_cents: int | None
    financing_type: str
    status: str
    proof_of_funds_received: bool
    notes: str | None
    received_at: datetime
    created_at: datetime


class LeadMissingField(BaseModel):
    field_key: str
    label: str
    question: str
    severity: str


class LeadNextBestAction(BaseModel):
    action_type: str
    label: str
    description: str
    priority: str


class LeadAiReadySummary(BaseModel):
    situation: str
    urgency: str
    known_facts: list[str]
    missing_questions: list[str]
    recommended_next_action: str


class LeadIntelligence(BaseModel):
    quality_score: int
    urgency_score: int
    priority_label: str
    missing_fields: list[LeadMissingField]
    next_best_action: LeadNextBestAction
    ai_ready_summary: LeadAiReadySummary


class LeadDetail(LeadRead):
    contact_methods: list[ContactMethodRead]
    consent_records: list[ConsentRecordRead]
    attribution_touches: list[AttributionTouchRead]
    open_tasks: list[LeadTaskRead]
    communications: list[CommunicationRecordRead]
    appointments: list[AppointmentRead]
    underwriting_versions: list[UnderwritingVersionRead]
    transactions: list[TransactionRead]
    buyer_offers: list[BuyerOfferRead]
    recent_activity: list[ActivityEventRead]
    intelligence: LeadIntelligence


class LeadStageUpdate(BaseModel):
    stage_key: str = Field(min_length=1, max_length=120)
    reason: str | None = Field(default=None, max_length=500)


class LeadStaffUpdate(BaseModel):
    seller_name: str | None = Field(default=None, min_length=1, max_length=255)
    preferred_name: str | None = Field(default=None, max_length=255)
    phone: str | None = Field(default=None, max_length=80)
    email: str | None = Field(default=None, max_length=320)
    property_street_address: str | None = Field(default=None, min_length=1, max_length=255)
    property_city: str | None = Field(default=None, min_length=1, max_length=120)
    property_state: str | None = Field(default=None, min_length=2, max_length=2)
    property_postal_code: str | None = Field(default=None, min_length=1, max_length=20)
    property_county: str | None = Field(default=None, max_length=120)
    property_type: str | None = Field(default=None, max_length=80)
    source: str | None = Field(default=None, min_length=1, max_length=120)
    lead_temperature: str | None = Field(default=None, max_length=80)
    motivation: str | None = Field(default=None, max_length=500)
    desired_timeline: str | None = Field(default=None, max_length=120)
    property_condition: str | None = Field(default=None, max_length=120)
    occupancy_status: str | None = Field(default=None, max_length=120)
    asking_price: str | None = Field(default=None, max_length=120)
    mortgage_balance: str | None = Field(default=None, max_length=120)
    appointment_status: str | None = Field(default=None, max_length=120)
    next_follow_up_at: datetime | None = None
    reason: str | None = Field(default=None, max_length=500)


class LeadNoteCreate(BaseModel):
    note: str = Field(min_length=1, max_length=500)


class LeadFollowUpTaskCreate(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    due_at: datetime | None = None
    priority: str = Field(default="normal", max_length=80)


class LeadCommunicationCreate(BaseModel):
    direction: str = Field(default="outbound", max_length=40)
    channel: str = Field(default="call", max_length=40)
    status: str = Field(default="logged", max_length=80)
    subject: str | None = Field(default=None, max_length=255)
    body: str = Field(min_length=1, max_length=4000)
    occurred_at: datetime | None = None


class LeadAppointmentCreate(BaseModel):
    appointment_type: str = Field(default="seller_call", max_length=80)
    status: str = Field(default="scheduled", max_length=80)
    scheduled_start_at: datetime
    scheduled_end_at: datetime | None = None
    location_type: str = Field(default="phone", max_length=80)
    location: str | None = Field(default=None, max_length=500)
    notes: str | None = Field(default=None, max_length=1000)


class LeadUnderwritingCreate(BaseModel):
    status: str = Field(default="draft", max_length=80)
    arv_low_cents: int | None = Field(default=None, ge=0)
    arv_high_cents: int | None = Field(default=None, ge=0)
    repair_low_cents: int | None = Field(default=None, ge=0)
    repair_high_cents: int | None = Field(default=None, ge=0)
    max_offer_cents: int | None = Field(default=None, ge=0)
    recommended_offer_cents: int | None = Field(default=None, ge=0)
    offer_strategy: str | None = Field(default=None, max_length=120)
    notes: str | None = Field(default=None, max_length=2000)


class LeadTransactionCreate(BaseModel):
    contract_type: str = Field(default="purchase_agreement", max_length=120)
    purchase_price_cents: int = Field(ge=1)
    assignment_fee_cents: int | None = Field(default=None, ge=0)
    earnest_money_cents: int | None = Field(default=None, ge=0)
    title_company: str | None = Field(default=None, max_length=255)
    closing_date: datetime | None = None
    inspection_period_days: int | None = Field(default=None, ge=0, le=120)
    notes: str | None = Field(default=None, max_length=2000)


class LeadBuyerOfferCreate(BaseModel):
    buyer_id: UUID
    amount_cents: int = Field(ge=1)
    earnest_money_cents: int | None = Field(default=None, ge=0)
    financing_type: str = Field(default="cash", max_length=80)
    status: str = Field(default="received", max_length=80)
    proof_of_funds_received: bool = False
    notes: str | None = Field(default=None, max_length=2000)
    received_at: datetime | None = None


class PipelineStageCount(BaseModel):
    stage_key: str
    count: int


class SourcePerformance(BaseModel):
    source: str
    medium: str
    campaign: str
    page_views: int
    form_starts: int
    form_abandons: int
    form_submits: int
    call_clicks: int
    leads_created: int


class DashboardSummary(BaseModel):
    total_leads: int
    new_paid_leads: int
    active_contracts: int
    offers_pending: int
    collected_revenue_cents: int
    pipeline: list[PipelineStageCount]
    source_performance: list[SourcePerformance]
