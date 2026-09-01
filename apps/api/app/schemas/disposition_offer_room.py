from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field, field_validator, model_validator

OfferStatus = Literal[
    "received",
    "countering",
    "selected",
    "backup",
    "passed",
    "withdrawn",
    "fell_out",
    "closed",
    "declined",
]
CheckpointType = Literal[
    "buyer_agreement",
    "buyer_signature",
    "buyer_deposit",
    "buyer_response",
    "access",
    "title",
    "closing",
]
CheckpointStatus = Literal[
    "pending",
    "in_progress",
    "completed",
    "waived",
    "missed",
    "cancelled",
]


class OfferRoomOfferCreate(BaseModel):
    buyer_id: UUID
    amount_cents: int = Field(ge=1)
    earnest_money_cents: int | None = Field(default=None, ge=0)
    deposit_due_at: datetime | None = None
    due_diligence_days: int | None = Field(default=None, ge=0, le=365)
    contingencies: list[str] = Field(default_factory=list, max_length=20)
    contingencies_confirmed: bool = False
    proposed_closing_at: datetime | None = None
    funding_method: str = Field(default="unknown", min_length=1, max_length=80)
    funding_confidence_basis_points: int = Field(default=0, ge=0, le=10000)
    proof_document_id: UUID | None = None
    special_terms: str | None = Field(default=None, max_length=4000)
    notes: str | None = Field(default=None, max_length=2000)
    change_reason: str = Field(
        default="Offer received and terms normalized.", min_length=3, max_length=1000
    )
    idempotency_key: str = Field(min_length=8, max_length=120)

    @field_validator("contingencies")
    @classmethod
    def normalize_contingencies(cls, values: list[str]) -> list[str]:
        normalized = [" ".join(value.split()) for value in values if value.strip()]
        if any(len(value) > 500 for value in normalized):
            raise ValueError("Each contingency must contain at most 500 characters.")
        return list(dict.fromkeys(normalized))


class OfferRoomOfferUpdate(BaseModel):
    expected_lock_version: int = Field(ge=1)
    amount_cents: int | None = Field(default=None, ge=1)
    earnest_money_cents: int | None = Field(default=None, ge=0)
    deposit_due_at: datetime | None = None
    due_diligence_days: int | None = Field(default=None, ge=0, le=365)
    contingencies: list[str] | None = Field(default=None, max_length=20)
    contingencies_confirmed: bool | None = None
    proposed_closing_at: datetime | None = None
    funding_method: str | None = Field(default=None, min_length=1, max_length=80)
    funding_confidence_basis_points: int | None = Field(default=None, ge=0, le=10000)
    proof_document_id: UUID | None = None
    special_terms: str | None = Field(default=None, max_length=4000)
    notes: str | None = Field(default=None, max_length=2000)
    change_reason: str = Field(min_length=3, max_length=1000)
    idempotency_key: str = Field(min_length=8, max_length=120)

    @field_validator("contingencies")
    @classmethod
    def normalize_contingencies(cls, values: list[str] | None) -> list[str] | None:
        if values is None:
            return None
        normalized = [" ".join(value.split()) for value in values if value.strip()]
        if any(len(value) > 500 for value in normalized):
            raise ValueError("Each contingency must contain at most 500 characters.")
        return list(dict.fromkeys(normalized))

    @model_validator(mode="after")
    def reject_explicit_null_for_required_terms(self) -> "OfferRoomOfferUpdate":
        for field_name in (
            "amount_cents",
            "contingencies",
            "contingencies_confirmed",
            "funding_method",
            "funding_confidence_basis_points",
        ):
            if field_name in self.model_fields_set and getattr(self, field_name) is None:
                raise ValueError(f"{field_name} cannot be null.")
        return self


class OfferNegotiationCreate(BaseModel):
    event_type: Literal["note", "counter", "request", "response", "retrade"]
    direction: Literal["inbound", "outbound", "internal"] = "internal"
    summary: str = Field(min_length=3, max_length=2000)
    metadata: dict[str, Any] = Field(default_factory=dict)
    occurred_at: datetime | None = None
    idempotency_key: str = Field(min_length=8, max_length=120)


class OfferSelectionCreate(BaseModel):
    primary_offer_id: UUID
    backup_offer_ids: list[UUID] = Field(default_factory=list, max_length=5)
    expected_offer_lock_versions: dict[UUID, int] = Field(min_length=1, max_length=6)
    expected_selection_lock_version: int | None = Field(default=None, ge=1)
    reason: str = Field(min_length=10, max_length=1000)
    eligibility_override_reason: str | None = Field(default=None, min_length=10, max_length=1000)
    idempotency_key: str = Field(min_length=8, max_length=120)

    @model_validator(mode="after")
    def distinct_offer_ids(self) -> "OfferSelectionCreate":
        all_ids = [self.primary_offer_id, *self.backup_offer_ids]
        if len(set(all_ids)) != len(all_ids):
            raise ValueError("Primary and backup offer IDs must be distinct.")
        if set(self.expected_offer_lock_versions) != set(all_ids):
            raise ValueError(
                "Expected lock versions must be provided for the primary and every backup offer."
            )
        if any(version < 1 for version in self.expected_offer_lock_versions.values()):
            raise ValueError("Expected offer lock versions must be positive.")
        return self


class OfferPrimaryReplacementCreate(BaseModel):
    expected_lock_version: int = Field(ge=1)
    replacement_offer_id: UUID | None = None
    expected_replacement_offer_lock_version: int | None = Field(default=None, ge=1)
    outcome_type: Literal["withdrawal", "fallout", "retrade", "missed_deadline"]
    cause_category: Literal["buyer", "seller", "title", "property", "stonegate", "external"]
    reason: str = Field(min_length=10, max_length=1000)
    details: str | None = Field(default=None, max_length=2000)
    evidence: dict[str, Any] = Field(default_factory=dict)
    idempotency_key: str = Field(min_length=8, max_length=120)


class ClosingCheckpointCreate(BaseModel):
    selection_id: UUID | None = None
    offer_id: UUID | None = None
    checkpoint_type: CheckpointType
    label: str = Field(min_length=2, max_length=255)
    due_at: datetime
    responsible_user_id: UUID | None = None
    notes: str | None = Field(default=None, max_length=2000)
    evidence: dict[str, Any] = Field(default_factory=dict)
    idempotency_key: str = Field(min_length=8, max_length=120)


class ClosingCheckpointUpdate(BaseModel):
    expected_lock_version: int = Field(ge=1)
    status: CheckpointStatus | None = None
    due_at: datetime | None = None
    responsible_user_id: UUID | None = None
    notes: str | None = Field(default=None, max_length=2000)
    evidence: dict[str, Any] | None = None
    reason: str = Field(min_length=3, max_length=1000)


class DeadlineAlertAcknowledge(BaseModel):
    reason: str = Field(min_length=3, max_length=1000)


class BuyerOutcomeCreate(BaseModel):
    offer_id: UUID
    selection_id: UUID | None = None
    outcome_type: Literal["pass", "withdrawal", "fallout", "retrade"]
    cause_category: Literal["buyer", "seller", "title", "property", "stonegate", "external"]
    reason: str = Field(min_length=10, max_length=1000)
    details: str | None = Field(default=None, max_length=2000)
    evidence: dict[str, Any] = Field(default_factory=dict)
    occurred_at: datetime | None = None
    idempotency_key: str = Field(min_length=8, max_length=120)


class OfferRiskFlagRead(BaseModel):
    code: str
    severity: Literal["info", "warning", "danger"]
    message: str
    evidence: dict[str, Any]


class OfferRevisionRead(BaseModel):
    id: UUID
    offer_id: UUID
    buyer_id: UUID
    actor_user_id: UUID
    revision_number: int
    terms_snapshot: dict[str, Any]
    risk_snapshot: dict[str, Any]
    change_reason: str
    created_at: datetime


class OfferRoomOfferRead(BaseModel):
    id: UUID
    buyer_id: UUID
    buyer_name: str
    amount_cents: int
    earnest_money_cents: int | None
    deposit_due_at: datetime | None
    due_diligence_days: int | None
    contingencies: list[str]
    contingencies_confirmed: bool
    proposed_closing_at: datetime | None
    funding_method: str
    funding_confidence_basis_points: int
    reliability_score_basis_points: int
    reliability_evidence: list[str]
    proof_document_id: UUID | None
    proof_status: str
    proof_verified_amount_cents: int | None
    proof_expires_at: datetime | None
    special_terms: str | None
    notes: str | None
    status: str
    lock_version: int
    received_at: datetime
    updated_at: datetime
    risk_score_basis_points: int
    risk_flags: list[OfferRiskFlagRead]
    strengths: list[str]
    execution_score_basis_points: int
    comparison_rank: int
    is_recommended: bool


class SelectionSlotRead(BaseModel):
    offer_id: UUID
    buyer_id: UUID
    buyer_name: str
    amount_cents: int
    role: Literal["primary", "backup"]
    rank: int
    offer_snapshot: dict[str, Any]
    readiness_status: Literal["ready", "provisional"]
    readiness_blockers: list[str]


class BuyerSelectionRead(BaseModel):
    id: UUID
    status: str
    lock_version: int
    primary: SelectionSlotRead
    backups: list[SelectionSlotRead]
    reason: str
    evidence_hash: str
    approved_by_user_id: UUID
    approved_at: datetime
    replaced_at: datetime | None
    backup_coverage_state: Literal["covered", "missing"]
    advisory_snapshot: dict[str, Any]


class NegotiationEventRead(BaseModel):
    id: UUID
    offer_id: UUID
    buyer_id: UUID
    buyer_name: str
    actor_user_id: UUID
    event_type: str
    direction: str
    summary: str
    metadata: dict[str, Any]
    occurred_at: datetime


class DeadlineAlertRead(BaseModel):
    id: UUID
    checkpoint_id: UUID
    status: str
    severity: str
    title: str
    message: str
    due_at: datetime
    deadline_version: int
    acknowledged_by_user_id: UUID | None
    acknowledged_at: datetime | None
    resolved_at: datetime | None


class ClosingCheckpointRead(BaseModel):
    id: UUID
    selection_id: UUID | None
    offer_id: UUID | None
    buyer_id: UUID | None
    buyer_name: str | None
    checkpoint_type: str
    label: str
    canonical_source: str
    source_record_id: UUID | None
    due_at: datetime
    status: str
    lock_version: int
    deadline_version: int
    responsible_user_id: UUID | None
    completed_at: datetime | None
    notes: str | None
    evidence: dict[str, Any]
    is_overdue: bool
    active_alert: DeadlineAlertRead | None


class ReplacementOptionRead(BaseModel):
    offer_id: UUID
    offer_lock_version: int
    buyer_id: UUID
    buyer_name: str
    backup_rank: int | None
    comparison_rank: int
    amount_cents: int
    execution_score_basis_points: int
    risk_score_basis_points: int
    eligible: bool
    blockers: list[str]


class BuyerOutcomeRead(BaseModel):
    id: UUID
    selection_id: UUID | None
    offer_id: UUID
    buyer_id: UUID
    buyer_name: str
    outcome_type: str
    cause_category: str
    reason: str
    details: str | None
    evidence: dict[str, Any]
    occurred_at: datetime
    completed_delta: int
    failed_delta: int
    reliability_delta_basis_points: int


class StrategyAgreementReadinessRead(BaseModel):
    strategy: Literal["assignment", "double_close", "novation"]
    label: str
    ready: bool
    blockers: list[str]


class OfferRoomRead(BaseModel):
    case_id: UUID
    case_status: str
    disposition_strategy: str
    assignment_execution_verified: bool
    strategy_agreement: StrategyAgreementReadinessRead
    currency: Literal["USD"] = "USD"
    generated_at: datetime
    offers: list[OfferRoomOfferRead]
    revision_history: list[OfferRevisionRead]
    current_selection: BuyerSelectionRead | None
    selection_history: list[BuyerSelectionRead]
    negotiation_history: list[NegotiationEventRead]
    checkpoints: list[ClosingCheckpointRead]
    alerts: list[DeadlineAlertRead]
    replacement_options: list[ReplacementOptionRead]
    outcomes: list[BuyerOutcomeRead]
