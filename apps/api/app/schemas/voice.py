from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class VoiceLineRead(BaseModel):
    id: UUID
    phone_number: str
    label: str
    status: str
    is_default: bool
    inbound_route: str
    assigned_user_id: UUID | None
    assigned_user_name: str | None


class VoiceLineCreate(BaseModel):
    phone_number: str = Field(min_length=8, max_length=80)
    label: str = Field(min_length=1, max_length=120)
    provider_phone_number_id: str | None = Field(default=None, max_length=255)
    assigned_user_id: UUID | None = None
    is_default: bool = False
    inbound_route: str = Field(default="conversation_owner", max_length=80)


class VoiceLineAssignmentUpdate(BaseModel):
    assigned_user_id: UUID | None = None
    label: str | None = Field(default=None, min_length=1, max_length=120)
    status: str | None = Field(default=None, max_length=40)
    is_default: bool | None = None
    inbound_route: str | None = Field(default=None, max_length=80)


class VoiceLineListResponse(BaseModel):
    items: list[VoiceLineRead]


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
    mortgage_or_title: str | None = Field(max_length=500)
    repairs: list[str] = Field(max_length=20)
    objections: list[str] = Field(max_length=20)
    commitments: list[str] = Field(max_length=20)
    next_action: str | None = Field(max_length=500)
    follow_up_at: str | None = Field(max_length=80)
    appointment_details: str | None = Field(max_length=500)
    confidence: int = Field(ge=0, le=100)
    evidence: list[CallNoteEvidence] = Field(max_length=40)


class CallTranscriptRead(BaseModel):
    id: UUID
    status: str
    model_name: str | None
    language: str | None
    transcript_text: str | None
    speaker_segments: list[dict[str, object]]
    confidence_score: int | None
    structured_notes: StructuredCallNotes | None
    approval_request_id: UUID | None
    approved_by_user_id: UUID | None
    approved_at: datetime | None
    error_message: str | None


class CallTranscriptReview(BaseModel):
    status: str = Field(pattern="^(approved|rejected)$")
    structured_notes: StructuredCallNotes
    decision_notes: str | None = Field(default=None, max_length=2000)
    apply_field_updates: list[str] = Field(default_factory=list, max_length=6)
    create_follow_up_task: bool = True
