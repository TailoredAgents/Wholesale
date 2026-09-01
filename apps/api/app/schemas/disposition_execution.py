from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

DispositionCallOutcome = Literal[
    "interested",
    "showing_scheduled",
    "offer_expected",
    "callback",
    "no_answer",
    "voicemail",
    "not_interested",
    "wrong_number",
    "do_not_contact",
]
ShowingStatus = Literal["scheduled", "confirmed", "completed", "cancelled", "no_show"]
ShowingAccessStatus = Literal[
    "not_requested",
    "pending",
    "confirmed",
    "shared_privately",
    "not_required",
]


class DispositionExecutionPermissionRead(BaseModel):
    status: str
    allowed: bool
    blockers: list[str]


class DispositionExecutionCandidateRead(BaseModel):
    candidate_id: UUID | None
    buyer_id: UUID
    conversation_id: UUID | None
    name: str
    company_name: str | None
    phone: str | None
    email: str | None
    ranking_status: Literal["ranked", "unranked"]
    rank: int | None
    score_basis_points: int | None
    relationship_status: str | None
    tier: str | None
    temperature: str | None
    decision_status: str
    lifecycle_stage: str
    decision_reason: str | None
    lock_version: int | None
    actionable: bool
    action_blockers: list[str]
    score_explanation: list[str]
    recent_purchase_reference: str | None
    sms: DispositionExecutionPermissionRead
    voice: DispositionExecutionPermissionRead
    sms_draft: str


class DispositionShowingRead(BaseModel):
    id: UUID
    candidate_id: UUID
    buyer_id: UUID
    buyer_name: str
    status: ShowingStatus
    access_status: ShowingAccessStatus
    scheduled_at: datetime | None
    completed_at: datetime | None
    follow_up_task_id: UUID | None
    notes: str | None


class DispositionExecutionWorkspaceRead(BaseModel):
    case_id: UUID
    deal_id: UUID
    asset_class: str
    property_address: str
    package_status: str
    package_is_preliminary: bool
    package_pdf_path: str | None
    ready: bool
    blockers: list[str]
    remaining_candidate_count: int
    current_candidate: DispositionExecutionCandidateRead | None
    candidates: list[DispositionExecutionCandidateRead]
    showings: list[DispositionShowingRead]


class _DispositionExecutionBuyerReference(BaseModel):
    model_config = ConfigDict(extra="forbid")

    candidate_id: UUID | None = None
    buyer_id: UUID | None = None

    @model_validator(mode="after")
    def require_buyer_reference(self) -> "_DispositionExecutionBuyerReference":
        if self.candidate_id is None and self.buyer_id is None:
            raise ValueError("Provide a ranked candidate or canonical buyer reference.")
        return self


class DispositionExecutionSmsCreate(_DispositionExecutionBuyerReference):
    body: str = Field(min_length=1, max_length=1600)
    idempotency_key: str = Field(min_length=8, max_length=120)


class DispositionExecutionCallCreate(_DispositionExecutionBuyerReference):
    idempotency_key: str = Field(min_length=8, max_length=120)


class DispositionExecutionOutcomeCreate(_DispositionExecutionBuyerReference):
    outcome: DispositionCallOutcome
    notes: str | None = Field(default=None, max_length=1000)
    follow_up_at: datetime | None = None
    idempotency_key: str = Field(min_length=8, max_length=120)


class DispositionShowingCreate(_DispositionExecutionBuyerReference):
    scheduled_at: datetime
    access_status: ShowingAccessStatus = "pending"
    notes: str | None = Field(default=None, max_length=1000)
    idempotency_key: str = Field(min_length=8, max_length=120)


class DispositionShowingUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: ShowingStatus
    access_status: ShowingAccessStatus
    scheduled_at: datetime | None = None
    notes: str | None = Field(default=None, max_length=1000)
