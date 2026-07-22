from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, model_validator


class ApprovalDecision(BaseModel):
    status: str = Field(max_length=80)
    decision_notes: str | None = Field(default=None, max_length=2000)


class ApprovalRequestRead(BaseModel):
    id: UUID
    request_type: str
    entity_type: str
    entity_id: UUID | None
    status: str
    title: str
    summary: str
    decision_notes: str | None
    decided_by_user_id: UUID | None
    due_at: datetime | None
    decided_at: datetime | None
    created_at: datetime
    review_url: str | None
    approval_metadata: dict[str, object]


class ApprovalListResponse(BaseModel):
    items: list[ApprovalRequestRead]


class OfferNegotiationPlanCreate(BaseModel):
    underwriting_version_id: UUID
    seller_asking_price_cents: int | None = Field(default=None, ge=0, le=1_000_000_000)
    opening_offer_cents: int | None = Field(default=None, ge=0, le=1_000_000_000)
    target_contract_cents: int | None = Field(default=None, ge=0, le=1_000_000_000)
    stretch_contract_cents: int | None = Field(default=None, ge=0, le=1_000_000_000)
    seller_context: str | None = Field(default=None, max_length=2000)
    rationale: str = Field(min_length=10, max_length=2000)


class OfferNegotiationPlanRead(BaseModel):
    id: UUID
    lead_id: UUID
    property_id: UUID
    underwriting_version_id: UUID
    underwriting_version_number: int
    market_analysis_id: UUID | None
    approval_request_id: UUID | None
    status: str
    seller_asking_price_cents: int | None
    arv_low_cents: int | None
    arv_point_cents: int | None
    arv_high_cents: int | None
    total_rehab_cents: int | None
    disposition_cents: int | None
    opening_offer_cents: int
    target_contract_cents: int
    stretch_contract_cents: int
    seller_ceiling_cents: int
    seller_context: str | None
    rationale: str
    source_snapshot: dict[str, object]
    approval_status: str | None
    decision_notes: str | None
    decided_by_user_id: UUID | None
    decided_at: datetime | None
    created_at: datetime


class OfferNegotiationPlanListResponse(BaseModel):
    items: list[OfferNegotiationPlanRead]
    can_approve: bool


class OfferConcessionCreate(BaseModel):
    offer_negotiation_plan_id: UUID
    appointment_id: UUID | None = None
    previous_offer_cents: int = Field(ge=0, le=1_000_000_000)
    proposed_offer_cents: int = Field(ge=0, le=1_000_000_000)
    seller_counter_cents: int | None = Field(default=None, ge=0, le=1_000_000_000)
    reason: str = Field(min_length=10, max_length=2000)
    seller_exchange: str = Field(min_length=3, max_length=2000)

    @model_validator(mode="after")
    def validate_increase(self) -> "OfferConcessionCreate":
        if self.proposed_offer_cents <= self.previous_offer_cents:
            raise ValueError("A concession must increase the last Stonegate offer.")
        return self


class OfferNegotiationEventCreate(BaseModel):
    offer_negotiation_plan_id: UUID
    appointment_id: UUID | None = None
    event_type: Literal[
        "price_discussion",
        "seller_counter",
        "objection",
        "follow_up",
        "agreement",
    ]
    channel: Literal["in_person", "phone", "sms", "email", "internal"]
    previous_offer_cents: int | None = Field(default=None, ge=0, le=1_000_000_000)
    amount_cents: int | None = Field(default=None, ge=0, le=1_000_000_000)
    seller_counter_cents: int | None = Field(default=None, ge=0, le=1_000_000_000)
    notes: str = Field(min_length=3, max_length=2000)
    seller_response: str | None = Field(default=None, max_length=2000)
    objections: list[str] = Field(default_factory=list, max_length=20)
    occurred_at: datetime | None = None

    @model_validator(mode="after")
    def validate_event(self) -> "OfferNegotiationEventCreate":
        if self.event_type == "seller_counter" and self.seller_counter_cents is None:
            raise ValueError("A seller-counter event requires the counter amount.")
        if self.event_type == "agreement" and self.amount_cents is None:
            raise ValueError("An agreement event requires the agreed amount.")
        return self


class OfferNegotiationEventRead(BaseModel):
    id: UUID
    offer_negotiation_plan_id: UUID
    concession_id: UUID | None
    appointment_id: UUID | None
    actor_user_id: UUID
    actor_name: str
    event_type: str
    channel: str
    previous_offer_cents: int | None
    amount_cents: int | None
    seller_counter_cents: int | None
    notes: str
    seller_response: str | None
    objections: list[str]
    occurred_at: datetime
    created_at: datetime


class OfferConcessionRead(BaseModel):
    id: UUID
    lead_id: UUID
    offer_negotiation_plan_id: UUID
    underwriting_version_id: UUID
    appointment_id: UUID | None
    approval_request_id: UUID | None
    sequence_number: int
    status: str
    authority_basis: str
    previous_offer_cents: int
    proposed_offer_cents: int
    concession_delta_cents: int
    seller_counter_cents: int | None
    reason: str
    seller_exchange: str
    decision_notes: str | None
    requested_by_user_id: UUID
    requested_by_name: str
    decided_by_user_id: UUID | None
    presented_by_user_id: UUID | None
    decided_at: datetime | None
    presented_at: datetime | None
    source_snapshot: dict[str, object]
    created_at: datetime


class OfferConcessionPresent(BaseModel):
    channel: Literal["in_person", "phone", "sms", "email"]
    notes: str = Field(min_length=3, max_length=2000)
    seller_response: str | None = Field(default=None, max_length=2000)
    occurred_at: datetime | None = None


class OfferNegotiationLedgerRead(BaseModel):
    active_plan: OfferNegotiationPlanRead | None
    concessions: list[OfferConcessionRead]
    events: list[OfferNegotiationEventRead]
    can_approve: bool
