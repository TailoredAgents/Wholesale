from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class VoiceLineRead(BaseModel):
    id: UUID
    phone_number: str
    label: str
    status: str
    is_default: bool
    inbound_route: str
    department_key: str
    purpose_key: str
    assigned_user_id: UUID | None
    assigned_user_name: str | None
    fallback_user_id: UUID | None
    fallback_user_name: str | None
    assigned_team_id: UUID | None
    assigned_team_name: str | None
    ring_strategy: str
    coverage_timezone: str
    coverage_start_hour: int
    coverage_end_hour: int
    missed_call_action: str
    ownership_complete: bool


class VoiceLineUserRead(BaseModel):
    id: UUID
    display_name: str
    email: str
    voice_forwarding_number: str | None
    voice_forwarding_enabled: bool
    lead_alert_sms_enabled: bool
    inbound_message_alert_sms_enabled: bool


class VoiceForwardingUpdate(BaseModel):
    voice_forwarding_number: str | None = Field(default=None, max_length=80)
    voice_forwarding_enabled: bool = False
    lead_alert_sms_enabled: bool = False
    # Optional during the rollout so a briefly cached older Settings client cannot erase the
    # migration-backfilled preference by omitting this newly introduced field.
    inbound_message_alert_sms_enabled: bool | None = None


class VoiceLineTeamRead(BaseModel):
    id: UUID
    name: str
    team_type: str


class VoiceLineCreate(BaseModel):
    phone_number: str = Field(min_length=8, max_length=80)
    label: str = Field(min_length=1, max_length=120)
    provider_phone_number_id: str | None = Field(default=None, max_length=255)
    assigned_user_id: UUID | None = None
    fallback_user_id: UUID | None = None
    assigned_team_id: UUID | None = None
    department_key: Literal["acquisitions", "dispositions", "general"] = "acquisitions"
    purpose_key: Literal["seller_conversations", "buyer_relations", "company_general"] = (
        "seller_conversations"
    )
    is_default: bool = False
    inbound_route: str = Field(default="conversation_owner", max_length=80)
    ring_strategy: Literal["sequential", "simultaneous"] = "simultaneous"
    coverage_timezone: str = Field(default="America/New_York", min_length=3, max_length=80)
    coverage_start_hour: int = Field(default=9, ge=0, le=23)
    coverage_end_hour: int = Field(default=20, ge=1, le=24)
    missed_call_action: Literal["fallback_then_voicemail", "voicemail", "task_only"] = (
        "fallback_then_voicemail"
    )


class VoiceLineAssignmentUpdate(BaseModel):
    assigned_user_id: UUID | None = None
    fallback_user_id: UUID | None = None
    assigned_team_id: UUID | None = None
    label: str | None = Field(default=None, min_length=1, max_length=120)
    department_key: Literal["acquisitions", "dispositions", "general"] | None = None
    purpose_key: Literal["seller_conversations", "buyer_relations", "company_general"] | None = None
    status: str | None = Field(default=None, max_length=40)
    is_default: bool | None = None
    inbound_route: str | None = Field(default=None, max_length=80)
    ring_strategy: Literal["sequential", "simultaneous"] | None = None
    coverage_timezone: str | None = Field(default=None, min_length=3, max_length=80)
    coverage_start_hour: int | None = Field(default=None, ge=0, le=23)
    coverage_end_hour: int | None = Field(default=None, ge=1, le=24)
    missed_call_action: Literal["fallback_then_voicemail", "voicemail", "task_only"] | None = None


class VoiceLineListResponse(BaseModel):
    items: list[VoiceLineRead]
    users: list[VoiceLineUserRead]
    teams: list[VoiceLineTeamRead]


class VoiceReadinessCheckRead(BaseModel):
    key: str
    label: str
    required: bool
    ready: bool
    detail: str


class VoiceProviderReadinessRead(BaseModel):
    configured: bool
    line_id: UUID | None
    line_phone_number: str | None
    inbound_webhook_url: str
    outbound_twiml_app_url: str
    status_callback_url: str
    recording_callback_url: str
    checks: list[VoiceReadinessCheckRead]


class VoiceSessionRead(BaseModel):
    can_initialize: bool
    identity: str
    token: str | None
    expires_at: datetime | None
    line: VoiceLineRead | None
    recording_enabled: bool
    blockers: list[str]


class VoiceCallIntentCreate(BaseModel):
    idempotency_key: str = Field(min_length=8, max_length=120)


class VoiceCallIntentRead(BaseModel):
    id: UUID
    conversation_id: UUID
    recipient: str
    from_number: str
    status: str
    expires_at: datetime
    recording_enabled: bool


class VoiceRecordingRead(BaseModel):
    id: UUID
    call_record_id: UUID
    status: str
    duration_seconds: int | None
    channel_count: int | None
    consent_status: str
    recorded_at: datetime | None
    retention_expires_at: datetime | None
    deleted_at: datetime | None
    deletion_reason: str | None


class VoiceRecordingDelete(BaseModel):
    reason: str = Field(min_length=10, max_length=1000)


class CallNoteEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid")

    field: str = Field(max_length=80)
    segment_index: int = Field(ge=0)
    start_seconds: float = Field(ge=0)
    supporting_text: str = Field(max_length=500)


class StructuredCallNotes(BaseModel):
    model_config = ConfigDict(extra="forbid")

    summary: str = Field(max_length=2000)
    motivation: str | None = Field(max_length=500)
    timeline: str | None = Field(max_length=120)
    property_condition: str | None = Field(max_length=120)
    occupancy_status: str | None = Field(max_length=120)
    asking_price: str | None = Field(max_length=120)
    mortgage_balance: str | None = Field(max_length=120)
    mortgage_or_title: str | None = Field(max_length=500)
    repairs: list[str] = Field(max_length=20)
    objections: list[str] = Field(max_length=20)
    commitments: list[str] = Field(max_length=20)
    next_action: str | None = Field(max_length=500)
    follow_up_at: str | None = Field(max_length=80)
    appointment_details: str | None = Field(max_length=500)
    confidence: int = Field(ge=0, le=100)
    evidence: list[CallNoteEvidence] = Field(max_length=40)


class LandStructuredCallNotes(StructuredCallNotes):
    """Transcript-grounded seller facts that are specific to vacant land."""

    parcel_id: str | None = Field(max_length=255)
    acreage: str | None = Field(max_length=120)
    legal_description: str | None = Field(max_length=1000)
    access_or_frontage: str | None = Field(max_length=500)
    utilities: str | None = Field(max_length=500)
    zoning_or_use: str | None = Field(max_length=500)
    septic_or_perc: str | None = Field(max_length=500)
    taxes_or_hoa: str | None = Field(max_length=500)
    terrain_or_environmental_concerns: str | None = Field(max_length=1000)


CallNotes = LandStructuredCallNotes | StructuredCallNotes


class CallTranscriptRead(BaseModel):
    id: UUID
    status: str
    model_name: str | None
    language: str | None
    transcript_text: str | None
    speaker_segments: list[dict[str, object]]
    confidence_score: int | None
    structured_notes: CallNotes | None
    quick_read_summary: str | None = Field(max_length=800)
    approval_request_id: UUID | None
    approved_by_user_id: UUID | None
    approved_at: datetime | None
    error_message: str | None


class CallTranscriptReview(BaseModel):
    status: str = Field(pattern="^(approved|rejected)$")
    structured_notes: CallNotes
    decision_notes: str | None = Field(default=None, max_length=2000)
    apply_field_updates: list[str] = Field(default_factory=list, max_length=6)
    create_follow_up_task: bool = True
