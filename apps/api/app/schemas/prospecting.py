from datetime import date, datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.domain.assets import HOUSE_ASSET_CLASS, AssetClass
from app.schemas.operations import OperationsUserRead
from app.schemas.voice import CallNoteEvidence, CallTranscriptRead, VoiceRecordingRead

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
HandoffDecisionCode = Literal[
    "accepted_interested",
    "accepted_appointment_set",
    "correction_decision_maker",
    "correction_property_details",
    "correction_interest_evidence",
    "correction_follow_up_permission",
    "correction_qualification",
    "correction_other",
    "rejected_not_interested",
    "rejected_wrong_party",
    "rejected_duplicate",
    "rejected_already_sold",
    "rejected_invalid_property",
    "rejected_no_follow_up_permission",
    "rejected_other",
]
DialerProfileStatus = Literal["inactive", "active", "suspended"]
DialerSessionState = Literal[
    "ready",
    "dialing",
    "ringing",
    "connected",
    "wrap_up",
    "paused",
    "reconnecting",
    "ended",
    "stopped",
    "failed",
    "expired",
]
DialerLegStatus = Literal[
    "queued",
    "dialing",
    "ringing",
    "answered",
    "connected",
    "cancelling",
    "cancelled",
    "no_answer",
    "busy",
    "failed",
    "completed",
]
QualificationResponseState = Literal[
    "not_covered",
    "answered",
    "needs_follow_up",
    "conflict",
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
    asset_class: AssetClass = HOUSE_ASSET_CLASS
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
    asset_class: AssetClass
    title: str
    status: str
    opening_script: str
    qualification_questions: list[ScriptQuestion]
    created_by_name: str
    approved_by_name: str | None
    approved_at: datetime | None
    created_at: datetime


class ProspectingQualificationChecklistItemRead(BaseModel):
    question_key: str
    label: str
    prompt: str
    answer_type: Literal["text", "choice"]
    choices: list[str]
    is_required: bool
    state: QualificationResponseState
    answer_value: str | None
    source: str
    revision: int = Field(ge=0)
    captured_at: datetime | None
    updated_at: datetime | None


class ProspectingQualificationChecklistRead(BaseModel):
    attempt_id: UUID
    script_version_id: UUID
    items: list[ProspectingQualificationChecklistItemRead]
    answered_count: int = Field(ge=0)
    total_count: int = Field(ge=0)
    required_answered_count: int = Field(ge=0)
    required_count: int = Field(ge=0)
    missing_required_keys: list[str]
    complete: bool


class ProspectingQualificationSuggestionRead(BaseModel):
    question_key: str
    state: Literal["suggested", "corroborated", "conflict"]
    current_value: Any | None = None
    suggested_value: Any
    evidence: list[CallNoteEvidence]


class ProspectingCallEvidenceCapabilities(BaseModel):
    can_play: bool
    can_download_audio: bool
    can_download_transcript: bool
    can_retry: bool
    can_delete: bool


class ProspectingCallEvidenceRead(BaseModel):
    attempt_id: UUID
    call_record_id: UUID | None
    dial_leg_id: UUID | None
    recording: VoiceRecordingRead | None
    transcript: CallTranscriptRead | None
    suggestions: list[ProspectingQualificationSuggestionRead]
    capabilities: ProspectingCallEvidenceCapabilities
    evidence_status: Literal[
        "unavailable",
        "recording_ready",
        "processing",
        "ready",
        "failed",
        "exhausted",
    ]


class ProspectingQualificationAutosaveRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    state: QualificationResponseState
    answer_value: str | None = Field(default=None, max_length=2000)
    expected_revision: int = Field(ge=0)
    mutation_id: UUID
    browser_session_id: str | None = Field(default=None, min_length=8, max_length=255)
    lease_token: str | None = Field(default=None, min_length=32, max_length=255)

    @model_validator(mode="after")
    def dialer_lease_fields_are_coherent(self) -> "ProspectingQualificationAutosaveRequest":
        if (self.browser_session_id is None) != (self.lease_token is None):
            raise ValueError("Browser session ID and dialer lease token must be supplied together.")
        return self


class ProspectingAttemptRead(BaseModel):
    id: UUID
    script_version_id: UUID
    script_version_number: int
    cohort_id: UUID | None
    dialer_mode: str
    status: str
    outcome: str | None
    contact_made: bool | None
    answer_classification: str
    party_classification: str
    interest_classification: str
    follow_up_permission: str
    classification_source: str
    dial_started_at: datetime | None
    answered_at: datetime | None
    right_party_confirmed_at: datetime | None
    interest_confirmed_at: datetime | None
    measurement_metadata: dict[str, Any]
    qualification_answers: dict[str, Any]
    notes: str | None
    callback_at: datetime | None
    started_at: datetime
    completed_at: datetime | None
    quality_score_basis_points: int | None
    qualification_checklist: ProspectingQualificationChecklistRead


class ProspectingDialerProfileUpsert(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: DialerProfileStatus = "inactive"
    voice_line_id: UUID | None = None
    default_line_count: int = Field(default=1, ge=1, le=3)
    max_line_count: int = Field(default=1, ge=1, le=3)
    recording_policy: str = Field(default="company_policy", min_length=1, max_length=80)
    daily_dial_limit: int | None = Field(default=None, gt=0)
    daily_spend_limit_cents: int | None = Field(default=None, ge=0)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def default_lines_do_not_exceed_maximum(self) -> "ProspectingDialerProfileUpsert":
        if self.default_line_count > self.max_line_count:
            raise ValueError("Default line count cannot exceed the profile maximum.")
        return self


class ProspectingDialerProfileRead(BaseModel):
    id: UUID
    organization_id: UUID
    user_id: UUID
    user_name: str
    user_email: str
    user_is_active: bool
    user_calling_enabled: bool
    voice_line_id: UUID | None
    voice_line_label: str | None
    voice_line_number: str | None
    status: DialerProfileStatus
    default_line_count: int = Field(ge=1, le=3)
    max_line_count: int = Field(ge=1, le=3)
    effective_line_count: int = Field(ge=1, le=3)
    recording_policy: str
    daily_dial_limit: int | None
    daily_spend_limit_cents: int | None
    metadata: dict[str, Any]
    created_by_user_id: UUID
    updated_by_user_id: UUID | None
    created_at: datetime
    updated_at: datetime


class ProspectingDialSessionRead(BaseModel):
    id: UUID
    organization_id: UUID
    dialer_profile_id: UUID
    caller_user_id: UUID
    campaign_id: UUID
    cohort_id: UUID | None
    prospect_calling_batch_id: UUID | None
    voice_line_id: UUID | None
    current_prospect_id: UUID | None
    current_batch_entry_id: UUID | None
    current_attempt_id: UUID | None
    state: DialerSessionState
    requested_line_count: int = Field(ge=1, le=3)
    effective_line_count: int = Field(ge=1, le=3)
    organization_line_limit: int = Field(ge=1, le=3)
    va_line_limit: int = Field(ge=1, le=3)
    campaign_line_limit: int = Field(ge=1, le=3)
    voice_line_limit: int = Field(ge=1, le=3)
    feature_line_limit: int = Field(ge=1, le=3)
    lease_expires_at: datetime | None
    started_at: datetime
    paused_at: datetime | None
    resumed_at: datetime | None
    heartbeat_at: datetime
    ended_at: datetime | None
    stop_reason: str | None
    pause_after_current: bool
    stop_after_current: bool
    created_at: datetime
    updated_at: datetime


class ProspectingDialSessionStart(BaseModel):
    model_config = ConfigDict(extra="forbid")

    campaign_id: UUID
    cohort_id: UUID
    calling_batch_id: UUID
    browser_session_id: str = Field(min_length=8, max_length=255)
    idempotency_key: str = Field(min_length=8, max_length=255)
    requested_line_count: int = Field(ge=1, le=3)


class ProspectingDialSessionLeaseCommand(BaseModel):
    model_config = ConfigDict(extra="forbid")

    browser_session_id: str = Field(min_length=8, max_length=255)
    lease_token: str = Field(min_length=32, max_length=255)


class ProspectingTechnicalFailureComplete(ProspectingDialSessionLeaseCommand):
    idempotency_key: str = Field(min_length=8, max_length=255)


class ProspectingDialSessionEndCommand(ProspectingDialSessionLeaseCommand):
    reason: str = Field(min_length=3, max_length=255)


class ProspectingDialSessionRecoveryCommand(BaseModel):
    model_config = ConfigDict(extra="forbid")

    previous_browser_session_id: str = Field(min_length=8, max_length=255)
    new_browser_session_id: str = Field(min_length=8, max_length=255)
    lease_token: str = Field(min_length=32, max_length=255)


class ProspectingDialLegRead(BaseModel):
    id: UUID
    organization_id: UUID
    dial_session_id: UUID
    prospect_id: UUID
    batch_entry_id: UUID
    attempt_id: UUID | None
    contact_point_id: UUID | None
    voice_line_id: UUID | None
    call_record_id: UUID | None
    line_slot: int = Field(ge=1, le=3)
    recipient: str
    provider: str
    provider_call_id: str | None
    status: DialerLegStatus
    queued_at: datetime
    dialing_at: datetime | None
    ringing_at: datetime | None
    answered_at: datetime | None
    connected_at: datetime | None
    cancelled_at: datetime | None
    failed_at: datetime | None
    completed_at: datetime | None
    answer_classification: str
    party_classification: str
    terminal_result: str | None
    provider_error_code: str | None
    provider_error_message: str | None
    cancellation_reason: str | None
    created_at: datetime
    updated_at: datetime


class ProspectingDialSessionSnapshotRead(BaseModel):
    session: ProspectingDialSessionRead
    current_leg: ProspectingDialLegRead | None = None


class ProspectingDialSessionControlRead(BaseModel):
    snapshot: ProspectingDialSessionSnapshotRead
    lease_token: str | None = None
    queue_status: Literal["reserved", "unchanged", "empty", "none"]
    replayed: bool


class ProspectingDialerSwitchUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool
    reason: str = Field(min_length=3, max_length=255)


class ProspectingDialerSwitchRead(BaseModel):
    scope: Literal["company", "campaign"]
    scope_id: UUID
    enabled: bool
    reason: str
    updated_at: datetime


class ProspectingVoiceCallCreate(ProspectingDialSessionLeaseCommand):
    """Authorize one controlled provider call for an already-reserved dial leg."""

    model_config = ConfigDict(extra="forbid")

    idempotency_key: str = Field(min_length=8, max_length=120)


class ProspectingVoiceCallControl(ProspectingDialSessionLeaseCommand):
    """Audited operator reason for ending a provider call."""

    model_config = ConfigDict(extra="forbid")

    reason: str = Field(min_length=3, max_length=255)


class ProspectingBrowserVoiceLineRead(BaseModel):
    id: UUID
    phone_number: str
    label: str
    provider: str
    status: str
    department_key: str
    purpose_key: str


class ProspectingBrowserVoiceSessionRead(BaseModel):
    can_initialize: bool
    dial_session_id: UUID
    identity: str
    token: str | None
    expires_at: datetime | None
    line: ProspectingBrowserVoiceLineRead
    recording_enabled: bool
    effective_line_count: Literal[1]
    blockers: list[str]


class ProspectingVoiceCallRead(BaseModel):
    """Cold-call state without requiring a CRM conversation or contact."""

    context_type: Literal["prospecting"] = "prospecting"
    call_intent_id: UUID
    call_record_id: UUID
    prospect_id: UUID
    attempt_id: UUID
    dial_session_id: UUID
    dial_leg_id: UUID
    provider: str
    provider_call_id: str | None
    provider_status: str
    recipient: str
    from_number: str
    recording_enabled: bool
    control_action: Literal[
        "prepared",
        "started",
        "fetched",
        "cancelled",
        "hung_up",
        "replayed",
    ]
    leg: ProspectingDialLegRead


class DialerContextRead(BaseModel):
    feature_enabled: bool
    configured_line_cap: int = Field(ge=1, le=3)
    implemented_line_cap: int = Field(ge=1, le=3)
    effective_line_cap: int = Field(ge=1, le=3)
    can_manage: bool
    profile: ProspectingDialerProfileRead | None
    active_session: ProspectingDialSessionRead | None
    active_legs: list[ProspectingDialLegRead]
    blockers: list[str]


ProspectingCallbackMatchStatus = Literal["pending", "matched", "unknown", "ambiguous"]
ProspectingCallbackStatus = Literal[
    "received",
    "routing",
    "ringing",
    "answered",
    "voicemail",
    "missed",
    "completed",
    "failed",
    "canceled",
]


class ProspectingInboundCallbackRead(BaseModel):
    id: UUID
    voice_line_id: UUID
    voice_line_label: str
    caller_number: str
    match_status: ProspectingCallbackMatchStatus
    match_strategy: str
    match_confidence_basis_points: int = Field(ge=0, le=10000)
    candidate_count: int = Field(ge=0)
    matched_prospect_id: UUID | None
    matched_attempt_id: UUID | None
    batch_entry_id: UUID | None
    can_open: bool
    prospect_name: str | None
    property_address: str | None
    assigned_user_id: UUID | None
    assigned_user_name: str | None
    fallback_user_id: UUID | None
    status: ProspectingCallbackStatus
    call_record_id: UUID | None
    missed_task_id: UUID | None
    received_at: datetime
    answered_at: datetime | None
    completed_at: datetime | None
    created_at: datetime
    updated_at: datetime


class ProspectingInboundCallbackListRead(BaseModel):
    items: list[ProspectingInboundCallbackRead]
    total: int = Field(ge=0)


class ProspectingEligibleVoiceLineRead(BaseModel):
    id: UUID
    label: str
    phone_number: str
    status: str
    assigned_user_id: UUID | None
    fallback_user_id: UUID | None
    assigned_team_id: UUID | None
    ring_strategy: str
    missed_call_action: str
    max_concurrent_legs: int = Field(ge=1, le=3)


class ProspectingDialerCallerRead(BaseModel):
    id: UUID
    display_name: str
    email: str
    is_active: bool
    calling_enabled: bool


class ProspectingCampaignDialerControlRead(BaseModel):
    id: UUID
    name: str
    code: str
    status: str
    enabled: bool
    max_concurrent_legs: int = Field(ge=1, le=3)


class ProspectingDialSessionOperationRead(BaseModel):
    session: ProspectingDialSessionRead
    caller_name: str
    caller_email: str
    campaign_name: str
    voice_line_label: str | None
    current_leg_status: str | None
    health_status: Literal["healthy", "stale", "reconnecting", "attention"]


class ProspectingDialerHealthSummaryRead(BaseModel):
    active_session_count: int = Field(ge=0)
    stale_session_count: int = Field(ge=0)
    reconnecting_session_count: int = Field(ge=0)
    active_leg_count: int = Field(ge=0)
    callback_waiting_count: int = Field(ge=0)
    missed_callback_task_count: int = Field(ge=0)
    open_recovery_failure_count: int = Field(ge=0)
    oldest_heartbeat_at: datetime | None
    worker_status: str
    worker_heartbeat_at: datetime | None


class ProspectingDialerOperationalErrorRead(BaseModel):
    occurred_at: datetime
    code: str
    message: str
    session_id: UUID | None
    caller_user_id: UUID | None
    campaign_id: UUID | None
    recoverable: bool


class ProspectingDialerOperationsRead(BaseModel):
    feature_enabled: bool
    company_enabled: bool
    configured_line_cap: int = Field(ge=1, le=3)
    implemented_line_cap: int = Field(ge=1, le=3)
    effective_line_cap: int = Field(ge=1, le=3)
    callers: list[ProspectingDialerCallerRead]
    profiles: list[ProspectingDialerProfileRead]
    eligible_lines: list[ProspectingEligibleVoiceLineRead]
    campaigns: list[ProspectingCampaignDialerControlRead]
    sessions: list[ProspectingDialSessionOperationRead]
    health: ProspectingDialerHealthSummaryRead
    recent_errors: list[ProspectingDialerOperationalErrorRead]


class ProspectingManagerSessionStopCommand(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mode: Literal["safe_drain", "cancel_unanswered"] = "safe_drain"
    reason: str = Field(min_length=3, max_length=255)
    idempotency_key: str = Field(min_length=8, max_length=255)


class ProspectingManagerSessionRecoveryCommand(BaseModel):
    model_config = ConfigDict(extra="forbid")

    action: Literal["reconcile", "release_orphan", "mark_failed"]
    reason: str = Field(min_length=3, max_length=255)
    idempotency_key: str = Field(min_length=8, max_length=255)


class ProspectingContactPointRead(BaseModel):
    contact_type: str
    value: str
    rank: int
    is_primary: bool
    validation_status: str


class ProspectingEntryRead(BaseModel):
    id: UUID
    batch_id: UUID
    batch_name: str
    campaign_id: UUID
    cohort_id: UUID | None
    cohort_name: str | None
    campaign_name: str
    assigned_user_id: UUID
    assigned_user_name: str
    prospect_id: UUID
    asset_class: AssetClass
    script: ProspectingScriptRead | None
    source_name: str
    warnings: list[str]
    legal_name: str
    phone: str | None
    email: str | None
    contact_points: list[ProspectingContactPointRead]
    property_address: str | None
    sequence_number: int
    status: str
    queue_kind: str
    is_actionable: bool
    dialer_mode: str
    provider_sync_status: str
    attempt_count: int
    disposition: str | None
    next_attempt_at: datetime | None
    active_attempt: ProspectingAttemptRead | None
    attempts: list[ProspectingAttemptRead]


class ProspectingAttemptComplete(BaseModel):
    model_config = ConfigDict(extra="forbid")

    outcome: ProspectingOutcome
    idempotency_key: str | None = Field(default=None, min_length=8, max_length=255)
    browser_session_id: str | None = Field(default=None, min_length=8, max_length=255)
    lease_token: str | None = Field(default=None, min_length=32, max_length=255)
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
        if (self.browser_session_id is None) != (self.lease_token is None):
            raise ValueError("Browser session ID and dialer lease token must be supplied together.")
        if self.outcome in {"callback_requested", "follow_up"} and self.callback_at is None:
            raise ValueError("Callback and follow-up outcomes require a callback date and time.")
        if self.outcome in {"interested", "appointment_set"} and self.handoff_user_id is None:
            raise ValueError("Warm outcomes require an acquisitions handoff owner.")
        if self.outcome == "appointment_set" and self.appointment_start_at is None:
            raise ValueError("Appointment set requires an appointment date and time.")
        if self.outcome == "appointment_set" and self.appointment_location_type is None:
            raise ValueError("Appointment set requires an appointment location type.")
        if (
            self.outcome == "appointment_set"
            and self.appointment_location_type in {"phone", "video", "office"}
            and not (self.appointment_location or "").strip()
        ):
            raise ValueError("Phone, video, and office appointments require an explicit location.")
        if self.outcome != "appointment_set" and self.appointment_start_at is not None:
            raise ValueError("Appointment details apply only to an appointment-set outcome.")
        if self.outcome != "appointment_set" and (
            self.appointment_location_type is not None or self.appointment_location is not None
        ):
            raise ValueError("Appointment details apply only to an appointment-set outcome.")
        return self


class ProspectHandoffRead(BaseModel):
    id: UUID
    prospect_id: UUID
    attempt_id: UUID
    lead_id: UUID
    asset_class: AssetClass
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
    decision_code: str | None
    review_reason: str | None


class ProspectHandoffDecision(BaseModel):
    decision: Literal["accepted", "needs_correction", "rejected"]
    reason_code: HandoffDecisionCode | None = None
    reason: str | None = Field(default=None, max_length=1000)

    @model_validator(mode="after")
    def decision_reason_is_coherent(self) -> "ProspectHandoffDecision":
        if self.decision in {"needs_correction", "rejected"} and not (self.reason or "").strip():
            raise ValueError("Returning or rejecting a handoff requires a clear reason.")
        if self.reason_code and not self.reason_code.startswith(
            {
                "accepted": "accepted_",
                "needs_correction": "correction_",
                "rejected": "rejected_",
            }[self.decision]
        ):
            raise ValueError("Handoff reason code must match the selected decision.")
        return self


class ProspectingQueueSummary(BaseModel):
    ready: int
    callbacks_due: int
    callbacks_scheduled: int
    retries_due: int
    retries_scheduled: int
    corrections: int
    in_progress: int
    handoff_pending: int
    completed: int


class ProspectingBatchQueueRead(BaseModel):
    batch_id: UUID
    batch_name: str
    campaign_name: str
    cohort_name: str | None
    dialer_mode: str
    provider_sync_status: str
    ready: int
    callbacks_due: int
    callbacks_scheduled: int
    retries_due: int
    retries_scheduled: int
    corrections: int
    in_progress: int
    handoff_pending: int


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
    queue_entries: list[ProspectingEntryRead]
    queue: ProspectingQueueSummary
    batch_queues: list[ProspectingBatchQueueRead]
    acquisition_users: list[OperationsUserRead]
    pending_handoffs: list[ProspectHandoffRead]
    returned_handoffs: list[ProspectHandoffRead]
    scorecards: list[ProspectingScorecardRead]
    copilot: ProspectingCopilotOverview


class BatchDialerVaMetricsRead(BaseModel):
    """Provider-call facts and downstream outcomes for one scorecard slice.

    ``inferred_calling_minutes`` is deliberately not represented as paid or logged
    hours. It is only the span of observed calling activity after long idle gaps are
    removed.
    """

    calls: int = 0
    unique_contacts: int = 0
    identified_contact_calls: int = 0
    identified_contact_coverage_basis_points: int | None = None
    human_contacts: int = 0
    recorded_duration_calls: int = 0
    recorded_duration_coverage_basis_points: int | None = None
    recorded_call_seconds: int | None = None
    average_recorded_call_seconds: int | None = None
    qualified_candidates: int = 0
    evidence_accepted_candidates: int = 0
    verified_handoffs: int = 0
    qualification_false_positives: int = 0
    appointments_set: int = 0
    appointments_entered: int = 0
    handoffs_with_appointment_entered: int = 0
    appointments_held: int = 0
    signed_contracts: int = 0
    closed_transactions: int = 0
    dnc: int = 0
    not_interested: int = 0
    voicemails: int = 0
    no_answers: int = 0
    first_call_at: datetime | None = None
    last_call_at: datetime | None = None
    inferred_calling_minutes: int | None = None
    human_contact_rate_basis_points: int | None = None
    evidence_acceptance_rate_basis_points: int | None = None
    false_positive_rate_basis_points: int | None = None
    appointments_entered_rate_basis_points: int | None = None


class BatchDialerVaScorecardRead(BaseModel):
    mapping_id: UUID | None
    provider_agent_id: str
    provider_agent_name: str
    user_id: UUID | None
    user_name: str | None
    metrics: BatchDialerVaMetricsRead


class BatchDialerCampaignScorecardRead(BaseModel):
    provider_campaign_id: str
    campaign_name: str
    metrics: BatchDialerVaMetricsRead


class BatchDialerVaDailyActivityRead(BaseModel):
    date: date
    provider_agent_id: str
    provider_agent_name: str
    metrics: BatchDialerVaMetricsRead


class BatchDialerVaHourlyActivityRead(BaseModel):
    hour_start_at: datetime
    provider_agent_id: str
    provider_agent_name: str
    calls: int
    human_contacts: int
    verified_handoffs: int
    recorded_call_seconds: int | None


class BatchDialerVaPerformanceRead(BaseModel):
    timezone: str
    date_from: date
    date_to: date
    as_of: datetime
    earliest_archived_call_at: datetime | None
    archive_history_status: Literal[
        "no_archived_calls",
        "selected_range_may_be_incomplete",
        "archived_calls_available",
    ]
    provider_scan_window_days: int
    provider_sync_status: Literal[
        "missing",
        "idle",
        "polling",
        "healthy",
        "failed",
        "unknown",
    ]
    provider_sync_freshness: Literal["current", "stale", "incomplete"]
    provider_sync_last_success_at: datetime | None
    provider_sync_error_present: bool
    provider_sync_poll_interval_seconds: int
    summary: BatchDialerVaMetricsRead
    agents: list[BatchDialerVaScorecardRead]
    campaigns: list[BatchDialerCampaignScorecardRead]
    daily_activity: list[BatchDialerVaDailyActivityRead]
    hourly_activity: list[BatchDialerVaHourlyActivityRead]
    coverage_warnings: list[str]


class BatchDialerAgentMappingRead(BaseModel):
    id: UUID
    provider_agent_id: str
    provider_agent_name: str
    user_id: UUID | None
    user_name: str | None
    last_seen_at: datetime


class BatchDialerAgentMappingUserRead(BaseModel):
    id: UUID
    name: str
    email: str
    is_active: bool


class BatchDialerAgentMappingListRead(BaseModel):
    items: list[BatchDialerAgentMappingRead]
    users: list[BatchDialerAgentMappingUserRead]


class BatchDialerAgentMappingUpdate(BaseModel):
    user_id: UUID | None


class BatchDialerCampaignMappingRead(BaseModel):
    id: UUID
    provider_campaign_id: str
    provider_campaign_name: str
    provider_status: str
    is_active: bool
    asset_class: AssetClass | None
    asset_class_mapped_at: datetime | None
    asset_class_mapped_by_user_id: UUID | None
    last_seen_at: datetime
    historical_lead_count: int
    historical_asset_mismatch_count: int
    historical_asset_mismatch_sample_lead_ids: list[UUID]


class BatchDialerCampaignMappingListRead(BaseModel):
    items: list[BatchDialerCampaignMappingRead]


class BatchDialerCampaignMappingUpdate(BaseModel):
    asset_class: AssetClass | None


class BatchDialerCampaignMappingUpdateRead(BaseModel):
    item: BatchDialerCampaignMappingRead
    requeued_event_count: int


class BatchDialerVaCoachAnalyzeRequest(BaseModel):
    provider_agent_id: str = Field(min_length=1, max_length=255)
    date_from: date | None = None
    date_to: date | None = None


class BatchDialerVaCoachObservationRead(BaseModel):
    observation: str
    evidence_refs: list[str]


class BatchDialerVaCoachActionRead(BaseModel):
    action: str
    rationale: str
    evidence_refs: list[str]


class BatchDialerVaCoachCallReviewRead(BaseModel):
    provider_event_id: str
    reason: str
    evidence_refs: list[str]


class BatchDialerVaCoachCaveatRead(BaseModel):
    caveat: str
    evidence_refs: list[str]


class BatchDialerVaCoachSummaryRead(BaseModel):
    text: str
    evidence_refs: list[str]


class BatchDialerVaCoachConfidenceRead(BaseModel):
    level: Literal["high", "medium", "low"]
    rationale: str
    evidence_refs: list[str]


class BatchDialerVaCoachOutputRead(BaseModel):
    draft_only: Literal[True]
    summary: BatchDialerVaCoachSummaryRead
    strengths: list[BatchDialerVaCoachObservationRead]
    concerns: list[BatchDialerVaCoachObservationRead]
    next_shift_actions: list[BatchDialerVaCoachActionRead]
    calls_to_review: list[BatchDialerVaCoachCallReviewRead]
    comparison_caveats: list[BatchDialerVaCoachCaveatRead]
    confidence: BatchDialerVaCoachConfidenceRead


class BatchDialerVaCoachReportRead(BaseModel):
    run_id: UUID
    provider_agent_id: str
    range_start: datetime
    range_end: datetime
    status: str
    output: BatchDialerVaCoachOutputRead | None
    generated_at: datetime
    reused: bool
    is_stale: bool
    refresh_required: bool
    stale_reasons: list[Literal["evidence_changed", "generation_contract_changed"]]
    current_evidence_as_of: datetime


class ProspectingAnalyticsPeriodRead(BaseModel):
    date_from: date
    date_to: date
    timezone: Literal["UTC"] = "UTC"
    start_at: datetime
    end_at_exclusive: datetime
    report_mode: Literal["activity_window"] = "activity_window"
    as_of: datetime


class ProspectingAnalyticsFiltersRead(BaseModel):
    cohort_id: UUID | None
    source: str | None
    campaign_id: UUID | None
    caller_user_id: UUID | None
    dial_mode: str | None


class ProspectingAnalyticsFilterOptionRead(BaseModel):
    id: UUID
    name: str


class ProspectingAnalyticsFilterOptionsRead(BaseModel):
    sources: list[str]
    campaigns: list[ProspectingAnalyticsFilterOptionRead]
    cohorts: list[ProspectingAnalyticsFilterOptionRead]
    callers: list[ProspectingAnalyticsFilterOptionRead]
    dial_modes: list[str]


class ProspectingMetricCoverageRead(BaseModel):
    raw_attempts_basis_points: int | None
    paid_hours_basis_points: int | None
    provider_cost_basis_points: int | None
    appointment_outcomes_basis_points: int | None
    profit_basis_points: int | None
    reputation_basis_points: int | None
    warnings: list[str]


class ProspectingDialerScorecardMetricsRead(BaseModel):
    entered_leads: int
    attempts: int | None
    answered_calls: int | None
    human_conversations: int | None
    conversations_over_60_seconds: int | None
    right_party_contacts: int | None
    qualified_sellers: int | None
    appointments_set: int
    appointments_held: int | None
    submitted_handoffs: int | None
    accepted_handoffs: int | None
    signed_contracts: int
    closed_assignments: int
    paid_minutes: int | None
    productive_calling_minutes: int | None
    labor_cost_cents: int | None
    provider_cost_cents: int | None
    list_cost_cents: int | None
    other_cost_cents: int | None
    total_cost_cents: int | None
    gross_revenue_cents: int | None
    contribution_profit_cents: int | None
    attempts_per_paid_hour_x100: int | None
    human_conversations_per_paid_hour_x100: int | None
    profit_per_paid_hour_cents: int | None
    cost_per_qualified_seller_cents: int | None
    cost_per_contract_cents: int | None
    human_contact_rate_basis_points: int | None
    right_party_contact_rate_basis_points: int | None
    qualified_seller_rate_basis_points: int | None
    accepted_handoff_rate_basis_points: int | None
    appointment_held_rate_basis_points: int | None
    contract_rate_basis_points: int | None
    close_rate_basis_points: int | None
    short_calls: int | None
    silent_or_dead_air_calls: int | None
    blocked_or_failed_calls: int | None
    no_answer_calls: int | None
    voicemail_calls: int | None
    duplicate_call_incidents: int | None
    seller_complaints: int | None
    dnc_requests: int | None
    abandoned_calls: int | None
    average_connection_time_seconds: int | None
    number_reputation_score: int | None
    answer_rate_trend_basis_points: int | None
    status_by_key: dict[
        str,
        Literal["known", "partial", "unknown", "not_applicable"],
    ]
    coverage: ProspectingMetricCoverageRead


class ProspectingDialerDimensionScorecardRead(BaseModel):
    dimension_type: Literal["va", "campaign", "cohort", "list", "dial_mode", "source"]
    dimension_id: UUID | None
    dimension_name: str
    external_key: str
    entry_stage: str
    source: str | None
    dial_mode: str | None
    metrics: ProspectingDialerScorecardMetricsRead


class ProspectingDialerDailyPointRead(BaseModel):
    date: date
    attempts: int | None
    human_conversations: int | None
    right_party_contacts: int | None
    accepted_handoffs: int | None
    answer_rate_basis_points: int | None
    blocked_or_failed_calls: int | None


class ProspectingDialerReadinessCheckRead(BaseModel):
    key: str
    label: str
    status: Literal["pass", "warning", "block"]
    detail: str


class ProspectingDialerLaunchReadinessRead(BaseModel):
    status: Literal["blocked", "needs_review", "ready_for_controlled_pilot"]
    controlled_pilot_ready: bool
    d10_acceptance_required: Literal[True] = True
    observed_at: datetime
    checks: list[ProspectingDialerReadinessCheckRead]
    blockers: list[str]
    warnings: list[str]


class ProspectingMetricDefinitionRead(BaseModel):
    key: str
    label: str
    definition: str
    source_records: list[str]
    attribution_timestamp: str
    unavailable_when: str | None


class ProspectingDialerAnalyticsRead(BaseModel):
    attribution_model_version: str
    profit_formula_version: str
    financials_visible: bool
    period: ProspectingAnalyticsPeriodRead
    filters: ProspectingAnalyticsFiltersRead
    filter_options: ProspectingAnalyticsFilterOptionsRead
    summary: ProspectingDialerScorecardMetricsRead
    by_va: list[ProspectingDialerDimensionScorecardRead]
    by_campaign: list[ProspectingDialerDimensionScorecardRead]
    by_cohort: list[ProspectingDialerDimensionScorecardRead]
    by_list: list[ProspectingDialerDimensionScorecardRead]
    by_dial_mode: list[ProspectingDialerDimensionScorecardRead]
    by_source: list[ProspectingDialerDimensionScorecardRead]
    daily_trend: list[ProspectingDialerDailyPointRead]
    readiness: ProspectingDialerLaunchReadinessRead
    metric_definitions: list[ProspectingMetricDefinitionRead]
