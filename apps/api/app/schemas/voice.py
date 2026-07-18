from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


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
