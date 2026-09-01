from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, field_validator, model_validator

OutreachChannel = Literal["email", "sms"]
OutreachRevisionStatus = Literal[
    "draft",
    "review_required",
    "approved",
    "queued",
    "sending",
    "paused",
    "provider_degraded",
    "completed",
    "completed_with_failures",
    "cancelled",
    "invalidated",
]


class DispositionOutreachRecipientSelection(BaseModel):
    campaign_recipient_id: UUID
    channels: list[OutreachChannel] = Field(min_length=1, max_length=2)

    @field_validator("channels")
    @classmethod
    def unique_channels(cls, value: list[OutreachChannel]) -> list[OutreachChannel]:
        if len(set(value)) != len(value):
            raise ValueError("Each outreach channel may be selected only once per buyer.")
        return value


class DispositionOutreachDraftCreate(BaseModel):
    campaign_id: UUID
    recipients: list[DispositionOutreachRecipientSelection] = Field(
        min_length=1,
        max_length=25,
    )
    email_sender_alias_id: UUID | None = None
    sms_voice_line_id: UUID | None = None
    email_subject: str | None = Field(default=None, max_length=255)
    email_body: str | None = Field(default=None, max_length=4000)
    sms_body: str | None = Field(default=None, max_length=1000)

    @model_validator(mode="after")
    def require_channel_copy_and_sender(self) -> "DispositionOutreachDraftCreate":
        channels = {
            channel for selection in self.recipients for channel in selection.channels
        }
        if "email" in channels:
            if self.email_sender_alias_id is None:
                raise ValueError("Select an active Resend sender for email outreach.")
            if not (self.email_subject or "").strip():
                raise ValueError("Email outreach requires a subject.")
            if not (self.email_body or "").strip():
                raise ValueError("Email outreach requires message copy.")
        if "sms" in channels:
            if self.sms_voice_line_id is None:
                raise ValueError("Select an active Dispositions buyer-relations line for SMS.")
            if not (self.sms_body or "").strip():
                raise ValueError("SMS outreach requires message copy.")
        return self


class DispositionOutreachApprovalRequest(BaseModel):
    expected_lock_version: int = Field(ge=1)
    expected_approval_hash: str = Field(min_length=64, max_length=64)
    attestation: bool
    reason: str = Field(min_length=3, max_length=2000)

    @field_validator("expected_approval_hash")
    @classmethod
    def validate_hash(cls, value: str) -> str:
        normalized = value.strip().lower()
        if any(character not in "0123456789abcdef" for character in normalized):
            raise ValueError("Approval hash must be a SHA-256 hexadecimal value.")
        return normalized

    @field_validator("attestation")
    @classmethod
    def require_attestation(cls, value: bool) -> bool:
        if not value:
            raise ValueError("Outreach approval requires an affirmative human attestation.")
        return value

    @field_validator("reason")
    @classmethod
    def normalize_reason(cls, value: str) -> str:
        normalized = " ".join(value.split())
        if len(normalized) < 3:
            raise ValueError("Approval reason must contain at least 3 characters.")
        return normalized


class DispositionOutreachControlRequest(BaseModel):
    expected_lock_version: int = Field(ge=1)
    reason: str = Field(min_length=3, max_length=2000)

    @field_validator("reason")
    @classmethod
    def normalize_reason(cls, value: str) -> str:
        normalized = " ".join(value.split())
        if len(normalized) < 3:
            raise ValueError("A meaningful control reason is required.")
        return normalized


class DispositionOutreachSenderRead(BaseModel):
    id: UUID
    channel: OutreachChannel
    label: str
    address: str
    is_default: bool


class DispositionOutreachPreparedRecipientRead(BaseModel):
    id: UUID
    buyer_id: UUID
    buyer_name: str
    company_name: str | None
    available_channels: list[OutreachChannel]
    captured_email: str | None
    captured_phone: str | None


class DispositionOutreachDeliveryRead(BaseModel):
    id: UUID
    campaign_recipient_id: UUID
    buyer_id: UUID
    conversation_id: UUID | None
    buyer_name: str
    company_name: str | None
    channel: OutreachChannel
    destination: str
    subject: str | None
    body: str
    body_hash: str
    eligibility_status: Literal["eligible", "ineligible"]
    eligibility_snapshot: dict[str, object]
    exclusion_reason: str | None
    status: str
    attempt_count: int
    provider: str | None
    provider_message_id: str | None
    created_at: datetime


class DispositionOutreachRevisionRead(BaseModel):
    id: UUID
    campaign_id: UUID
    case_id: UUID
    package_version_id: UUID
    revision_number: int
    lock_version: int
    status: OutreachRevisionStatus
    mode: Literal["supervised"]
    recipient_cap: int
    recipient_manifest_hash: str
    approval_hash: str | None
    package_source_fingerprint: str
    artifact_sha256: str
    package_status: str
    package_was_current_at_prepare: bool
    package_is_current_now: bool
    package_is_preliminary: bool
    sender_snapshot: dict[str, object]
    created_by_user_id: UUID
    approved_by_user_id: UUID | None
    approval_reason: str | None
    approved_at: datetime | None
    queued_at: datetime | None
    paused_at: datetime | None
    cancelled_at: datetime | None
    completed_at: datetime | None
    delivery_counts: dict[str, int]
    deliveries: list[DispositionOutreachDeliveryRead]
    created_at: datetime


class DispositionOutreachWorkspaceRead(BaseModel):
    case_id: UUID
    campaign_id: UUID | None
    package_version_id: UUID | None
    package_source_fingerprint: str | None
    artifact_sha256: str | None
    package_status: str | None
    package_is_preliminary: bool
    hard_recipient_cap: int
    readiness_status: Literal["ready", "blocked"]
    blockers: list[str]
    prepared_recipients: list[DispositionOutreachPreparedRecipientRead]
    available_senders: list[DispositionOutreachSenderRead]
    latest_revision: DispositionOutreachRevisionRead | None
    revisions: list[DispositionOutreachRevisionRead]
