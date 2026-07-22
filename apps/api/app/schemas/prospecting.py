from datetime import date, datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field, model_validator

from app.schemas.operations import OperationsUserRead

ProspectingOutcome = Literal[
    "no_answer",
    "left_voicemail",
    "callback_requested",
    "follow_up",
    "interested",
    "appointment_set",
    "not_interested",
    "wrong_number",
    "do_not_call",
]


class ScriptQuestion(BaseModel):
    key: str = Field(pattern=r"^[a-z][a-z0-9_]{1,79}$")
    label: str = Field(min_length=1, max_length=160)
    prompt: str = Field(min_length=1, max_length=500)
    answer_type: Literal["text", "choice"] = "text"
    choices: list[str] = Field(default_factory=list, max_length=20)
    required_for_handoff: bool = False

    @model_validator(mode="after")
    def choices_match_answer_type(self) -> "ScriptQuestion":
        if self.answer_type == "choice" and len(self.choices) < 2:
            raise ValueError("Choice questions require at least two options.")
        if self.answer_type == "text" and self.choices:
            raise ValueError("Text questions cannot include choices.")
        return self


class ProspectingScriptCreate(BaseModel):
    title: str = Field(min_length=1, max_length=160)
    opening_script: str = Field(min_length=20, max_length=5000)
    qualification_questions: list[ScriptQuestion] = Field(min_length=1, max_length=30)

    @model_validator(mode="after")
    def question_keys_are_unique(self) -> "ProspectingScriptCreate":
        keys = [question.key for question in self.qualification_questions]
        if len(keys) != len(set(keys)):
            raise ValueError("Caller-script question keys must be unique.")
        return self


class ProspectingScriptRead(BaseModel):
    id: UUID
    version_number: int
    title: str
    status: str
    opening_script: str
    qualification_questions: list[ScriptQuestion]
    created_by_name: str
    approved_by_name: str | None
    approved_at: datetime | None
    created_at: datetime


class ProspectingAttemptRead(BaseModel):
    id: UUID
    script_version_id: UUID
    script_version_number: int
    status: str
    outcome: str | None
    contact_made: bool | None
    qualification_answers: dict[str, Any]
    notes: str | None
    callback_at: datetime | None
    started_at: datetime
    completed_at: datetime | None
    quality_score_basis_points: int | None


class ProspectingEntryRead(BaseModel):
    id: UUID
    batch_id: UUID
    batch_name: str
    campaign_name: str
    prospect_id: UUID
    legal_name: str
    phone: str | None
    email: str | None
    property_address: str | None
    sequence_number: int
    status: str
    attempt_count: int
    disposition: str | None
    next_attempt_at: datetime | None
    active_attempt: ProspectingAttemptRead | None
    attempts: list[ProspectingAttemptRead]


class ProspectingAttemptComplete(BaseModel):
    outcome: ProspectingOutcome
    qualification_answers: dict[str, str] = Field(default_factory=dict, max_length=50)
    notes: str | None = Field(default=None, max_length=2000)
    callback_at: datetime | None = None
    handoff_user_id: UUID | None = None
    appointment_start_at: datetime | None = None
    appointment_location_type: Literal["phone", "video", "seller_property", "office"] | None = None
    appointment_location: str | None = Field(default=None, max_length=500)

    @model_validator(mode="after")
    def outcome_fields_are_coherent(self) -> "ProspectingAttemptComplete":
        if self.outcome in {"callback_requested", "follow_up"} and self.callback_at is None:
            raise ValueError("Callback and follow-up outcomes require a callback date and time.")
        if self.outcome in {"interested", "appointment_set"} and self.handoff_user_id is None:
            raise ValueError("Warm outcomes require an acquisitions handoff owner.")
        if self.outcome == "appointment_set" and self.appointment_start_at is None:
            raise ValueError("Appointment set requires an appointment date and time.")
        if self.outcome != "appointment_set" and self.appointment_start_at is not None:
            raise ValueError("Appointment details apply only to an appointment-set outcome.")
        return self


class ProspectHandoffRead(BaseModel):
    id: UUID
    prospect_id: UUID
    attempt_id: UUID
    lead_id: UUID
    seller_name: str
    property_address: str | None
    caller_name: str
    assigned_user_id: UUID
    assigned_user_name: str
    status: str
    outcome: str
    qualification_answers: dict[str, Any]
    notes: str | None
    submitted_at: datetime
    reviewed_by_name: str | None
    reviewed_at: datetime | None
    review_reason: str | None


class ProspectHandoffDecision(BaseModel):
    decision: Literal["accepted", "needs_correction"]
    reason: str | None = Field(default=None, max_length=1000)

    @model_validator(mode="after")
    def correction_requires_reason(self) -> "ProspectHandoffDecision":
        if self.decision == "needs_correction" and not (self.reason or "").strip():
            raise ValueError("Returning a handoff requires a clear correction reason.")
        return self


class ProspectingQueueSummary(BaseModel):
    ready: int
    callbacks_due: int
    in_progress: int
    handoff_pending: int
    completed: int


class ProspectingScorecardRead(BaseModel):
    caller_user_id: UUID
    caller_name: str
    score_date: date
    attempts: int
    contacts: int
    callbacks: int
    handoffs: int
    accepted_handoffs: int
    wrong_numbers: int
    dnc_requests: int
    contact_rate_basis_points: int
    handoff_rate_basis_points: int
    accepted_handoff_rate_basis_points: int
    script_completion_rate_basis_points: int
    data_quality_issue_rate_basis_points: int


class ProspectingWorkbenchOverview(BaseModel):
    current_user_id: UUID
    current_user_name: str
    can_manage: bool
    active_script: ProspectingScriptRead | None
    scripts: list[ProspectingScriptRead]
    current_entry: ProspectingEntryRead | None
    queue: ProspectingQueueSummary
    acquisition_users: list[OperationsUserRead]
    pending_handoffs: list[ProspectHandoffRead]
    returned_handoffs: list[ProspectHandoffRead]
    scorecards: list[ProspectingScorecardRead]
