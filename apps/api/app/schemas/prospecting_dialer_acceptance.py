from datetime import date, datetime
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, Field, StringConstraints, field_validator, model_validator

NonBlank120 = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=120),
]
NonBlank255 = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=255),
]
NonBlank500 = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=500),
]
NonBlank1000 = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=1000),
]
NonBlank2000 = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=2000),
]

ProspectingDialerPilotStatus = Literal[
    "draft",
    "smoke_testing",
    "running",
    "ready_for_owner_review",
    "accepted",
    "rejected",
    "rolled_back",
    "revoked",
    "cancelled",
]
ProspectingDialerPilotReviewStatus = Literal["pending", "passed", "failed"]
ProspectingDialerPilotGateStatus = Literal["pass", "block", "pending", "warning"]


class ProspectingDialerPilotMutation(BaseModel):
    expected_revision: int = Field(ge=0)
    idempotency_key: NonBlank255


class ProspectingDialerPilotCreate(ProspectingDialerPilotMutation):
    caller_user_id: UUID
    campaign_id: UUID
    cohort_id: UUID
    prospect_calling_batch_id: UUID
    voice_line_id: UUID

    @model_validator(mode="after")
    def require_create_revision(self) -> "ProspectingDialerPilotCreate":
        if self.expected_revision != 0:
            raise ValueError("A new pilot must use expected_revision 0.")
        return self


class ProspectingDialerPilotStart(ProspectingDialerPilotMutation):
    controlled_numbers_only: Literal[True]
    controlled_phone_numbers: list[NonBlank120] = Field(min_length=1, max_length=10)
    controlled_number_evidence: NonBlank1000
    batchdialer_cohort_is_separate: Literal[True]
    batchdialer_non_overlap_evidence: NonBlank1000
    reason: NonBlank1000


class ProspectingDialerPilotProviderCostItem(BaseModel):
    provider_call_id: NonBlank255
    actual_cost_cents: int = Field(ge=0, le=100_000)
    currency: Literal["USD"] = "USD"
    provider_reference: NonBlank500


class ProspectingDialerPilotSmokeTestEvidence(BaseModel):
    controlled_numbers_only: Literal[True]
    completed_at: datetime
    call_record_ids: list[UUID] = Field(min_length=1, max_length=50)
    provider_cost_items: list[ProspectingDialerPilotProviderCostItem] = Field(
        min_length=1,
        max_length=100,
    )
    summary: NonBlank2000


class ProspectingDialerPilotKillSwitchEvidence(BaseModel):
    company_switch_tested: Literal[True]
    campaign_switch_tested: Literal[True]
    idle_sessions_stopped: Literal[True]
    low_dial_cap_block_tested: Literal[True]
    tested_at: datetime
    summary: NonBlank2000


class ProspectingDialerPilotBatchComparisonEvidence(BaseModel):
    separate_cohort: Literal[True]
    overlapping_record_count: Literal[0]
    batchdialer_cohort_reference: NonBlank500
    comparison_summary: NonBlank2000


class ProspectingDialerPilotRollbackEvidence(BaseModel):
    campaign_pause_tested: Literal[True]
    sessions_end_tested: Literal[True]
    unworked_records_returnable: Literal[True]
    native_evidence_remains_read_only: Literal[True]
    tested_at: datetime
    summary: NonBlank2000


class ProspectingDialerPilotEvidenceUpdate(ProspectingDialerPilotMutation):
    smoke_test: ProspectingDialerPilotSmokeTestEvidence | None = None
    kill_switch: ProspectingDialerPilotKillSwitchEvidence | None = None
    batchdialer_comparison: ProspectingDialerPilotBatchComparisonEvidence | None = None
    rollback: ProspectingDialerPilotRollbackEvidence | None = None

    @model_validator(mode="after")
    def require_evidence(self) -> "ProspectingDialerPilotEvidenceUpdate":
        if not any(
            (
                self.smoke_test,
                self.kill_switch,
                self.batchdialer_comparison,
                self.rollback,
            )
        ):
            raise ValueError("Provide at least one pilot evidence section.")
        return self


class ProspectingDialerPilotAttemptReviewCreate(ProspectingDialerPilotMutation):
    recording_reviewed: bool
    provider_cost_verified: bool
    compliance_clear: bool
    reason: NonBlank2000


class ProspectingDialerPilotShiftReviewCreate(ProspectingDialerPilotMutation):
    shift_date: date
    no_duplicate_calls: bool
    no_lost_answers: bool
    no_stuck_sessions: bool
    provider_billing_verified: bool
    kill_switches_verified: bool
    compliance_clear: bool
    billing_evidence_reference: NonBlank1000
    provider_cost_items: list[ProspectingDialerPilotProviderCostItem] = Field(
        min_length=1,
        max_length=250,
    )
    reason: NonBlank2000


class ProspectingDialerPilotSubmit(ProspectingDialerPilotMutation):
    reason: NonBlank2000


class ProspectingDialerPilotRollback(ProspectingDialerPilotMutation):
    confirmation_phrase: str = Field(max_length=120)
    return_unworked_cohort_to_batchdialer: Literal[True]
    preserve_native_evidence_read_only: Literal[True]
    reason: NonBlank2000

    @field_validator("confirmation_phrase", mode="before")
    @classmethod
    def normalize_confirmation_phrase(cls, value: object) -> object:
        return value.strip() if isinstance(value, str) else value


class ProspectingDialerPilotRevoke(ProspectingDialerPilotMutation):
    confirmation_phrase: str = Field(max_length=120)
    reason: NonBlank2000

    @field_validator("confirmation_phrase", mode="before")
    @classmethod
    def normalize_confirmation_phrase(cls, value: object) -> object:
        return value.strip() if isinstance(value, str) else value


class ProspectingDialerPilotDecision(ProspectingDialerPilotMutation):
    decision: Literal["accept", "reject"]
    confirmation_phrase: str | None = Field(default=None, max_length=120)
    reason: NonBlank2000

    @field_validator("confirmation_phrase", mode="before")
    @classmethod
    def normalize_confirmation_phrase(cls, value: object) -> object:
        return value.strip() if isinstance(value, str) else value


class ProspectingDialerPilotGateRead(BaseModel):
    key: str
    label: str
    status: ProspectingDialerPilotGateStatus
    detail: str


class ProspectingDialerPilotRead(BaseModel):
    id: UUID
    status: ProspectingDialerPilotStatus
    revision: int
    caller_user_id: UUID
    caller_name: str
    campaign_id: UUID
    campaign_name: str
    cohort_id: UUID
    cohort_name: str
    prospect_calling_batch_id: UUID
    calling_batch_name: str
    voice_line_id: UUID
    voice_line_number: str
    effective_line_count: int
    timezone: str
    required_clean_shift_count: int
    minimum_attempts_per_shift: int
    minimum_productive_minutes_per_shift: int
    minimum_total_attempts: int
    minimum_batch_size: int
    maximum_batch_size: int
    daily_dial_limit: int
    daily_spend_limit_cents: int
    configuration_fingerprint: str
    started_at: datetime | None
    start_attestation: dict[str, object]
    smoke_test_evidence: dict[str, object]
    kill_switch_evidence: dict[str, object]
    batchdialer_comparison_evidence: dict[str, object]
    rollback_evidence: dict[str, object]
    evidence_hash: str | None
    submitted_at: datetime | None
    accepted_at: datetime | None
    rejected_at: datetime | None
    rolled_back_at: datetime | None
    revoked_at: datetime | None
    revocation_reason: str | None
    cancelled_at: datetime | None
    cancellation_reason: str | None
    created_at: datetime
    updated_at: datetime


class ProspectingDialerPilotAttemptReviewRead(BaseModel):
    id: UUID
    attempt_id: UUID
    dial_session_id: UUID
    status: ProspectingDialerPilotReviewStatus
    server_dial_leg_count: int
    server_terminal_leg_count: int
    disposition_complete: bool
    recording_review_required: bool
    recording_reviewed: bool
    callback_required: bool
    callback_reconciled: bool
    handoff_required: bool
    handoff_reconciled: bool
    provider_cost_verified: bool
    compliance_clear: bool
    reviewed_at: datetime
    reason: str


class ProspectingDialerPilotAttemptQueueRead(BaseModel):
    attempt_id: UUID
    dial_session_id: UUID
    acceptance_stage: Literal["smoke_testing", "running", "accepted"] | None
    counts_toward_production_shift: bool
    call_record_ids: list[UUID]
    provider_call_ids: list[str]
    placed_call: bool
    smoke_test_eligible: bool
    started_at: datetime
    completed_at: datetime | None
    outcome: str | None
    review_status: ProspectingDialerPilotReviewStatus
    blocker: str | None


class ProspectingDialerPilotShiftReviewRead(BaseModel):
    id: UUID
    dial_session_id: UUID
    shift_date: date
    timezone: str
    status: ProspectingDialerPilotReviewStatus
    server_attempt_count: int
    server_reviewed_attempt_count: int
    server_passed_attempt_count: int
    reserved_attempt_count: int
    provider_started_attempt_count: int
    placed_call_count: int
    productive_minutes: int
    all_attempts_reviewed: bool
    all_legs_terminal: bool
    no_duplicate_calls: bool
    no_lost_answers: bool
    no_stuck_sessions: bool
    callbacks_reconciled: bool
    handoffs_reconciled: bool
    provider_billing_verified: bool
    daily_caps_respected: bool
    kill_switches_verified: bool
    recordings_reviewed: bool
    compliance_clear: bool
    reviewed_at: datetime
    reason: str


class ProspectingDialerPilotOverviewRead(BaseModel):
    pilot: ProspectingDialerPilotRead | None
    gates: list[ProspectingDialerPilotGateRead]
    attempt_review_queue: list[ProspectingDialerPilotAttemptQueueRead]
    attempt_reviews: list[ProspectingDialerPilotAttemptReviewRead]
    shift_reviews: list[ProspectingDialerPilotShiftReviewRead]
    current_configuration_fingerprint: str | None
    configuration_matches: bool
    batch_entry_count: int
    total_reviewed_attempts: int
    total_passed_attempts: int
    passed_shift_count: int
    allowed_actions: list[str]
