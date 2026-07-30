from datetime import date, datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field

ProofType = Literal["review", "seller_story", "completed_purchase", "statistic"]
PermissionStatus = Literal["pending", "granted", "not_required", "revoked"]
ProofDecision = Literal["submit_review", "publish", "return_to_draft", "retire"]


class TrustProofCreate(BaseModel):
    proof_type: ProofType
    title: str = Field(min_length=2, max_length=180)
    content: str | None = Field(default=None, max_length=6000)
    attribution_name: str | None = Field(default=None, max_length=120)
    attribution_detail: str | None = Field(default=None, max_length=180)
    location_label: str | None = Field(default=None, max_length=120)
    rating: int | None = Field(default=None, ge=1, le=5)
    metric_label: str | None = Field(default=None, max_length=120)
    metric_value: str | None = Field(default=None, max_length=80)
    methodology: str | None = Field(default=None, max_length=2000)
    as_of_date: date | None = None
    source_type: str = Field(min_length=2, max_length=60)
    source_url: str | None = Field(default=None, max_length=1000)
    source_reference: str | None = Field(default=None, max_length=500)
    show_source_link: bool = False
    permission_status: PermissionStatus = "pending"
    permission_evidence_notes: str | None = Field(default=None, max_length=2000)
    material_connection: str | None = Field(default=None, max_length=500)
    disclosure: str | None = Field(default=None, max_length=500)
    featured: bool = False
    sort_order: int = Field(default=0, ge=-1000, le=1000)


class TrustProofUpdate(BaseModel):
    proof_type: ProofType | None = None
    title: str | None = Field(default=None, min_length=2, max_length=180)
    content: str | None = Field(default=None, max_length=6000)
    attribution_name: str | None = Field(default=None, max_length=120)
    attribution_detail: str | None = Field(default=None, max_length=180)
    location_label: str | None = Field(default=None, max_length=120)
    rating: int | None = Field(default=None, ge=1, le=5)
    metric_label: str | None = Field(default=None, max_length=120)
    metric_value: str | None = Field(default=None, max_length=80)
    methodology: str | None = Field(default=None, max_length=2000)
    as_of_date: date | None = None
    source_type: str | None = Field(default=None, min_length=2, max_length=60)
    source_url: str | None = Field(default=None, max_length=1000)
    source_reference: str | None = Field(default=None, max_length=500)
    show_source_link: bool | None = None
    permission_status: PermissionStatus | None = None
    permission_evidence_notes: str | None = Field(default=None, max_length=2000)
    material_connection: str | None = Field(default=None, max_length=500)
    disclosure: str | None = Field(default=None, max_length=500)
    featured: bool | None = None
    sort_order: int | None = Field(default=None, ge=-1000, le=1000)


class TrustProofDecisionRequest(BaseModel):
    decision: ProofDecision
    reason: str = Field(min_length=3, max_length=500)


class TrustProofAdminRead(BaseModel):
    id: UUID
    proof_type: str
    title: str
    content: str | None
    attribution_name: str | None
    attribution_detail: str | None
    location_label: str | None
    rating: int | None
    metric_label: str | None
    metric_value: str | None
    methodology: str | None
    as_of_date: date | None
    source_type: str
    source_url: str | None
    source_reference: str | None
    show_source_link: bool
    permission_status: str
    permission_evidence_notes: str | None
    material_connection: str | None
    disclosure: str | None
    publication_status: str
    featured: bool
    sort_order: int
    created_by_name: str
    updated_by_name: str
    approved_by_name: str | None
    approved_at: datetime | None
    published_at: datetime | None
    retired_at: datetime | None
    created_at: datetime
    updated_at: datetime


class TrustProofAdminOverview(BaseModel):
    can_manage: bool
    records: list[TrustProofAdminRead]


class PublicTrustProofRead(BaseModel):
    id: UUID
    proof_type: str
    title: str
    content: str | None
    attribution_name: str | None
    attribution_detail: str | None
    location_label: str | None
    rating: int | None
    metric_label: str | None
    metric_value: str | None
    methodology: str | None
    as_of_date: date | None
    source_type: str
    source_url: str | None
    disclosure: str | None
    featured: bool
    published_at: datetime


class PublicTrustProofResponse(BaseModel):
    records: list[PublicTrustProofRead]
