from datetime import datetime
from decimal import Decimal
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field, model_validator

LandSearchTier = Literal["preferred", "expanded", "extended"]
LandValuationBasis = Literal["per_acre", "per_lot"]
LandAccessEvidenceStatus = Literal["unknown", "reported", "verified"]
LandUseGroup = Literal[
    "residential",
    "agricultural",
    "commercial",
    "industrial",
    "recreational",
]


class LandValuationCreate(BaseModel):
    refresh_comps: bool = False
    idempotency_key: str | None = Field(default=None, min_length=8, max_length=160)
    source_analysis_id: UUID | None = None
    search_tier: LandSearchTier = "preferred"
    valuation_basis: LandValuationBasis = "per_acre"
    subject_acres_override: Decimal | None = Field(
        default=None,
        gt=Decimal("0"),
        le=Decimal("100000"),
        decimal_places=4,
    )
    subject_acres_evidence_reference: str | None = Field(default=None, max_length=1000)
    subject_lot_count: int | None = Field(default=None, ge=1, le=10000)
    subject_lot_count_evidence_reference: str | None = Field(default=None, max_length=1000)
    access_evidence_status: LandAccessEvidenceStatus = "unknown"
    access_evidence_reference: str | None = Field(default=None, max_length=1000)
    subject_use_override: LandUseGroup | None = None
    subject_use_evidence_reference: str | None = Field(default=None, max_length=1000)
    selected_comp_keys: list[str] | None = Field(default=None, max_length=12)
    review_note: str | None = Field(default=None, max_length=2000)

    @model_validator(mode="after")
    def inputs_are_coherent(self) -> "LandValuationCreate":
        if self.refresh_comps and self.source_analysis_id is not None:
            raise ValueError("A saved Land analysis cannot be combined with a provider refresh.")
        if self.selected_comp_keys is not None and self.source_analysis_id is None:
            raise ValueError("Comparable review requires a saved source analysis.")
        if self.valuation_basis == "per_lot" and self.subject_lot_count is None:
            raise ValueError("Per-lot valuation requires a verified subject lot count.")
        if self.subject_acres_override is not None and not (
            self.subject_acres_evidence_reference
            and self.subject_acres_evidence_reference.strip()
        ):
            raise ValueError("An acreage override requires an evidence reference.")
        if self.valuation_basis == "per_lot" and not (
            self.subject_lot_count_evidence_reference
            and self.subject_lot_count_evidence_reference.strip()
        ):
            raise ValueError("A per-lot valuation requires lot-count evidence.")
        if self.access_evidence_status == "verified" and not (
            self.access_evidence_reference and self.access_evidence_reference.strip()
        ):
            raise ValueError("Verified legal access requires an evidence reference.")
        if self.subject_use_override is not None and not (
            self.subject_use_evidence_reference
            and self.subject_use_evidence_reference.strip()
        ):
            raise ValueError("A human-selected Land use group requires an evidence reference.")
        return self


class LandComparableRead(BaseModel):
    key: str
    provider_id: str | None = None
    formatted_address: str | None = None
    parcel_id: str | None = None
    county: str | None = None
    state: str | None = None
    property_type: str | None = None
    property_use: str | None = None
    zoning: str | None = None
    sale_date: str | None = None
    sale_price_cents: int | None = None
    lot_square_feet: int | None = None
    acres: float | None = None
    lot_count: int | None = None
    price_per_acre_cents: int | None = None
    price_per_lot_cents: int | None = None
    adjustment_factor: float = 1.0
    adjusted_unit_price_cents: int | None = None
    subject_indication_cents: int | None = None
    distance_miles: float | None = None
    days_old: int | None = None
    acreage_ratio: float | None = None
    evidence_tier: LandSearchTier | None = None
    score: int = 0
    weight: float = 0
    selection_status: Literal["selected", "rejected"]
    selection_reason: str
    source: str = "realestateapi"
    arms_length_evidence: str | None = None


class LandOfferPolicyCreate(BaseModel):
    title: str = Field(min_length=3, max_length=160)
    quick_sale_discount_low_basis_points: int = Field(default=1500, ge=0, le=5000)
    quick_sale_discount_high_basis_points: int = Field(default=2500, ge=0, le=6000)
    opening_reserve_basis_points: int = Field(default=1000, ge=0, le=5000)
    assignment_fee_cents: int = Field(default=1_500_000, ge=0, le=100_000_000)
    closing_title_reserve_cents: int = Field(default=300_000, ge=0, le=100_000_000)
    curative_reserve_cents: int = Field(default=500_000, ge=0, le=100_000_000)
    uncertainty_reserve_cents: int = Field(default=500_000, ge=0, le=100_000_000)
    maximum_dispersion_basis_points: int = Field(default=5000, ge=500, le=20000)
    minimum_comparable_count: int = Field(default=3, ge=3, le=8)
    notes: str | None = Field(default=None, max_length=2000)

    @model_validator(mode="after")
    def discount_range_is_ordered(self) -> "LandOfferPolicyCreate":
        if (
            self.quick_sale_discount_low_basis_points
            > self.quick_sale_discount_high_basis_points
        ):
            raise ValueError("The low quick-sale discount cannot exceed the high discount.")
        return self


class LandOfferPolicyActivate(BaseModel):
    reason: str = Field(min_length=5, max_length=500)


class LandOfferPolicyRead(BaseModel):
    id: UUID
    version_number: int
    status: Literal["draft", "active", "retired"]
    title: str
    quick_sale_discount_low_basis_points: int
    quick_sale_discount_high_basis_points: int
    opening_reserve_basis_points: int
    assignment_fee_cents: int
    closing_title_reserve_cents: int
    curative_reserve_cents: int
    uncertainty_reserve_cents: int
    maximum_dispersion_basis_points: int
    minimum_comparable_count: int
    notes: str | None
    approved_by_user_id: UUID | None
    approved_at: datetime | None
    created_at: datetime


class LandValuationRead(BaseModel):
    id: UUID
    lead_id: UUID
    property_id: UUID
    property_snapshot_id: UUID
    source_analysis_id: UUID | None
    policy_version_id: UUID | None
    version_number: int
    valuation_profile: Literal["land_v1"] = "land_v1"
    methodology_version: str
    status: Literal["ready", "needs_review", "insufficient_evidence"]
    guidance_status: Literal["available", "withheld"]
    is_current: bool = True
    valuation_basis: LandValuationBasis
    access_evidence_status: LandAccessEvidenceStatus
    subject_acres: float
    subject_lot_count: int | None
    supported_value_low_cents: int | None
    supported_value_cents: int | None
    supported_value_high_cents: int | None
    quick_sale_low_cents: int | None
    quick_sale_high_cents: int | None
    opening_offer_cents: int | None
    seller_contract_ceiling_cents: int | None
    assignment_fee_cents: int
    closing_title_reserve_cents: int
    curative_reserve_cents: int
    uncertainty_reserve_cents: int
    confidence_score: int
    selected_comps: list[LandComparableRead]
    rejected_comps: list[LandComparableRead]
    subject_snapshot: dict[str, Any]
    search_snapshot: dict[str, Any]
    assumptions: dict[str, Any]
    review_reasons: list[str]
    guidance_blockers: list[str]
    policy_snapshot: dict[str, Any]
    created_at: datetime
