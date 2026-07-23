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
    compliance_flags: list[
        Literal[
            "seller_complaint",
            "identity_unclear",
            "policy_uncertainty",
            "recording_disclosure_issue",
        ]
    ] = Field(default_factory=list, max_length=4)

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


class ProspectingCopilotWorkItemRead(BaseModel):
    entry_id: UUID
    prospect_id: UUID
    seller_name: str
    property_address: str | None
    campaign_name: str
    priority_score: int
    priority_band: str
    recommended_action: str
    reasons: list[str]
    data_quality_warnings: list[str]
    eligibility_evidence: list[str]
    callback_due: bool
    correction_required: bool


class ProspectingCopilotModelOutput(BaseModel):
    pre_call_summary: str = Field(max_length=4000)
    priority_explanation: str = Field(max_length=2000)
    property_context: list[str] = Field(max_length=20)
    prior_attempt_context: list[str] = Field(max_length=20)
    opening_guidance: str = Field(max_length=2000)
    required_questions: list[str] = Field(max_length=30)
    disposition_guidance: list[str] = Field(max_length=20)
    data_quality_warnings: list[str] = Field(max_length=20)
    compliance_reminders: list[str] = Field(max_length=20)
    evidence: list[str] = Field(max_length=40)
    confidence: int = Field(ge=0, le=100)


class ProspectingCopilotRecommendationRead(BaseModel):
    id: UUID
    entry_id: UUID
    prospect_id: UUID
    ai_run_log_id: UUID | None
    status: str
    priority_score: int
    priority_band: str
    output_payload: ProspectingCopilotModelOutput
    confidence_score: int | None
    generated_at: datetime
    reviewed_at: datetime | None


class ProspectingCopilotAnalyzeRequest(BaseModel):
    idempotency_key: str | None = Field(default=None, min_length=1, max_length=255)


class ProspectingCopilotAnalyzeRead(BaseModel):
    run_id: UUID
    run_status: str
    message: str
    recommendation: ProspectingCopilotRecommendationRead | None


class ProspectingCopilotReviewRequest(BaseModel):
    decision: Literal["accepted", "edited", "rejected"]
    final_output: dict[str, Any] | None = None
    notes: str | None = Field(default=None, max_length=2000)
    estimated_time_saved_seconds: int = Field(default=0, ge=0, le=7200)

    @model_validator(mode="after")
    def edited_output_is_required(self) -> "ProspectingCopilotReviewRequest":
        if self.decision == "edited" and self.final_output is None:
            raise ValueError("Edited recommendations require corrected output.")
        return self


class ProspectingCopilotReviewRead(BaseModel):
    id: UUID
    recommendation_id: UUID
    decision: str
    final_output: dict[str, Any] | None
    notes: str | None
    estimated_time_saved_seconds: int
    reviewed_at: datetime


class ProspectingCallQualityModelOutput(BaseModel):
    call_summary: str = Field(max_length=4000)
    suggested_disposition: ProspectingOutcome
    disposition_reason: str = Field(max_length=2000)
    callback_recommendation: str = Field(max_length=1000)
    handoff_draft: str = Field(max_length=3000)
    script_adherence_score: int = Field(ge=0, le=100)
    qualification_completeness_score: int = Field(ge=0, le=100)
    objection_handling_score: int = Field(ge=0, le=100)
    data_quality_score: int = Field(ge=0, le=100)
    handoff_quality_score: int = Field(ge=0, le=100)
    coaching_points: list[str] = Field(max_length=20)
    compliance_flags: list[str] = Field(max_length=20)
    evidence_timestamps: list[str] = Field(max_length=40)
    confidence: int = Field(ge=0, le=100)


class ProspectingCallQualityRead(BaseModel):
    id: UUID
    attempt_id: UUID
    caller_user_id: UUID
    caller_name: str
    seller_name: str
    outcome: str | None
    status: str
    deterministic_scores: dict[str, int | None]
    ai_output: ProspectingCallQualityModelOutput | None
    final_output: ProspectingCallQualityModelOutput | None
    compliance_flags: list[str]
    escalation_required: bool
    transcript_available: bool
    reviewed_at: datetime | None
    review_notes: str | None
    completed_at: datetime | None


class ProspectingCallQualityAnalyzeRead(BaseModel):
    run_id: UUID
    run_status: str
    message: str
    quality_review: ProspectingCallQualityRead


class ProspectingCallQualityReviewRequest(BaseModel):
    decision: Literal["approved", "corrected", "rejected"]
    final_output: dict[str, Any] | None = None
    notes: str | None = Field(default=None, max_length=2000)

    @model_validator(mode="after")
    def correction_requires_output(self) -> "ProspectingCallQualityReviewRequest":
        if self.decision == "corrected" and self.final_output is None:
            raise ValueError("Corrected coaching requires corrected output.")
        return self


class ProspectingCopilotMetrics(BaseModel):
    generated_briefs: int
    reviewed_briefs: int
    accepted_or_corrected_rate_basis_points: int
    correction_rate_basis_points: int
    estimated_time_saved_minutes: int
    quality_reviews: int
    transcript_ready: int
    escalations: int
    coaching_approved: int
    coaching_corrected: int


class ProspectingCopilotOverview(BaseModel):
    pilot_mode: str
    runtime_status: str
    priority_capability_status: str
    quality_capability_status: str
    external_actions_blocked: bool
    work_items: list[ProspectingCopilotWorkItemRead]
    recommendations: list[ProspectingCopilotRecommendationRead]
    quality_queue: list[ProspectingCallQualityRead]
    metrics: ProspectingCopilotMetrics


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
    copilot: ProspectingCopilotOverview
