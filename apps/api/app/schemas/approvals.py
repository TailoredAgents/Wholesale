from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


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
