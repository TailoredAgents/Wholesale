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
DispositionExecutionStep = Literal["sms", "call", "email", "outcome"]
DispositionExecutionSmsStatus = Literal["not_started", "drafted", "sent"]
DispositionExecutionCallStatus = Literal["not_started", "started", "completed"]
DispositionExecutionEmailStatus = Literal["not_started", "drafted", "sent"]
DispositionExecutionSessionState = Literal["active", "paused"]


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
    email_subject: str
    email_draft: str


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


class DispositionExecutionBuyerStateRead(BaseModel):
    sms_draft: str = ""
    email_subject: str = ""
    email_draft: str = ""
    email_sender_alias_id: UUID | None = None
    notes_draft: str = ""
    callback_at: datetime | None = None
    selected_outcome: DispositionCallOutcome | None = None
    current_step: DispositionExecutionStep = "sms"
    sms_status: DispositionExecutionSmsStatus = "not_started"
    call_status: DispositionExecutionCallStatus = "not_started"
    email_status: DispositionExecutionEmailStatus = "not_started"


class DispositionExecutionSessionRead(BaseModel):
    id: UUID | None
    persisted: bool
    state: DispositionExecutionSessionState
    current_buyer_id: UUID | None
    buyer_pool_run_id: UUID | None
    queue_buyer_ids: list[UUID]
    skipped_buyer_ids: list[UUID]
    buyer_states: dict[str, DispositionExecutionBuyerStateRead]
    last_outcome: DispositionCallOutcome | None
    last_outcome_buyer_id: UUID | None
    last_outcome_at: datetime | None
    follow_up_at: datetime | None
    started_at: datetime | None
    paused_at: datetime | None
    resumed_at: datetime | None
    updated_at: datetime | None
    lock_version: int | None


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
    session: DispositionExecutionSessionRead
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


class DispositionExecutionEmailCreate(_DispositionExecutionBuyerReference):
    email_sender_alias_id: UUID
    subject: str = Field(min_length=1, max_length=255)
    body: str = Field(min_length=1, max_length=4000)
    idempotency_key: str = Field(min_length=8, max_length=120)


class DispositionExecutionCallCreate(_DispositionExecutionBuyerReference):
    idempotency_key: str = Field(min_length=8, max_length=120)


class DispositionExecutionOutcomeCreate(_DispositionExecutionBuyerReference):
    outcome: DispositionCallOutcome
    notes: str | None = Field(default=None, max_length=1000)
    follow_up_at: datetime | None = None
    idempotency_key: str = Field(min_length=8, max_length=120)


class DispositionExecutionSessionUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    state: DispositionExecutionSessionState | None = None
    current_buyer_id: UUID | None = None
    advance_to_next: bool = False
    rerank_queue: bool = False
    skipped_buyer_ids: list[UUID] | None = None
    buyer_id: UUID | None = None
    sms_draft: str | None = Field(default=None, max_length=1600)
    email_subject: str | None = Field(default=None, max_length=255)
    email_draft: str | None = Field(default=None, max_length=4000)
    email_sender_alias_id: UUID | None = None
    notes_draft: str | None = Field(default=None, max_length=1000)
    callback_at: datetime | None = None
    selected_outcome: DispositionCallOutcome | None = None
    current_step: DispositionExecutionStep | None = None

    @model_validator(mode="after")
    def require_buyer_for_draft_state(self) -> "DispositionExecutionSessionUpdate":
        buyer_fields = {
            "sms_draft",
            "email_subject",
            "email_draft",
            "email_sender_alias_id",
            "notes_draft",
            "callback_at",
            "selected_outcome",
            "current_step",
        }
        if self.model_fields_set.intersection(buyer_fields) and self.buyer_id is None:
            raise ValueError("Provide a buyer when saving investor-specific session state.")
        if not self.model_fields_set.intersection(
            {
                "state",
                "current_buyer_id",
                "advance_to_next",
                "rerank_queue",
                "skipped_buyer_ids",
                *buyer_fields,
            }
        ):
            raise ValueError("Provide at least one session field to update.")
        if self.advance_to_next and "current_buyer_id" in self.model_fields_set:
            raise ValueError("Choose an exact investor or advance to the next one, not both.")
        if self.advance_to_next and self.rerank_queue:
            raise ValueError("Rerank the queue or advance to the next investor, not both.")
        return self


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
