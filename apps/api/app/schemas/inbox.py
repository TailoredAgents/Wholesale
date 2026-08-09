from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, model_validator

from app.domain.assets import LAND_ASSET_CLASS, asset_class_for_property_type
from app.schemas.email import EmailAttachmentRead
from app.schemas.leads import PropertyCreate
from app.schemas.voice import CallTranscriptRead


class ConversationWatcherRead(BaseModel):
    user_id: UUID
    email: str
    display_name: str
    source: str
    notification_level: str
    is_muted: bool


class ConversationAssignmentEventRead(BaseModel):
    id: UUID
    actor_user_id: UUID | None
    previous_assigned_user_id: UUID | None
    assigned_user_id: UUID | None
    previous_queue_key: str
    queue_key: str
    reason: str
    created_at: datetime


class ConversationContactMethodRead(BaseModel):
    method_type: str
    value: str
    is_primary: bool


class ConversationTimelineItemRead(BaseModel):
    id: UUID
    item_type: str
    direction: str | None
    channel: str
    status: str
    provider: str | None
    status_detail: str | None = None
    subject: str | None
    body: str
    actor_user_id: UUID | None
    actor_display_name: str | None
    occurred_at: datetime
    call_id: UUID | None = None
    duration_seconds: int | None = None
    recording_id: UUID | None = None
    recording_status: str | None = None
    recording_retention_expires_at: datetime | None = None
    recording_deleted_at: datetime | None = None
    transcript: CallTranscriptRead | None = None
    attachments: list[EmailAttachmentRead] = Field(default_factory=list)


class ConversationTaskRead(BaseModel):
    id: UUID
    title: str
    task_type: str
    status: str
    priority: str
    due_at: datetime | None


class ConversationAppointmentRead(BaseModel):
    id: UUID
    appointment_type: str
    status: str
    scheduled_start_at: datetime
    scheduled_end_at: datetime | None
    location_type: str
    location: str | None
    notes: str | None


class SmsEligibilityRead(BaseModel):
    can_send: bool
    recipient: str | None
    consent_status: str
    is_suppressed: bool
    provider_configured: bool
    within_allowed_hours: bool
    blockers: list[str]


class VoiceEligibilityRead(BaseModel):
    can_call: bool
    recipient: str | None
    consent_status: str
    is_suppressed: bool
    provider_configured: bool
    within_allowed_hours: bool
    blockers: list[str]


class ConversationRead(BaseModel):
    id: UUID
    conversation_type: str
    lead_id: UUID | None
    buyer_id: UUID | None
    contact_id: UUID
    seller_name: str
    property_address: str
    assigned_user_id: UUID | None
    assigned_user_email: str | None
    assigned_user_display_name: str | None
    assigned_team_id: UUID | None
    source_alias_id: UUID | None
    visibility_scope: str
    status: str
    queue_key: str
    priority: str
    mail_category: str | None
    merged_into_conversation_id: UUID | None
    unread_count: int
    last_activity_at: datetime | None
    last_inbound_at: datetime | None
    last_outbound_at: datetime | None
    response_state: str
    response_kind: str | None
    response_age_minutes: int | None
    response_target_minutes: int | None
    response_due_at: datetime | None
    closed_at: datetime | None
    watchers: list[ConversationWatcherRead]
    assignment_history: list[ConversationAssignmentEventRead]
    created_at: datetime
    updated_at: datetime


class ConversationDetailRead(ConversationRead):
    preferred_name: str | None
    contact_methods: list[ConversationContactMethodRead]
    source: str | None
    stage_key: str | None
    lead_temperature: str | None
    motivation: str | None
    desired_timeline: str | None
    property_condition: str | None
    occupancy_status: str | None
    appointment_status: str | None
    next_follow_up_at: datetime | None
    property_type: str | None
    asset_class: Literal["house", "land"] | None
    property_parcel_id: str | None
    property_county: str | None
    timeline: list[ConversationTimelineItemRead]
    open_tasks: list[ConversationTaskRead]
    appointments: list[ConversationAppointmentRead]
    sms_eligibility: SmsEligibilityRead
    voice_eligibility: VoiceEligibilityRead


class ConversationListResponse(BaseModel):
    items: list[ConversationRead]


class MailboxResponseBucketRead(BaseModel):
    scope_id: UUID | None
    scope_label: str
    conversation_count: int
    needs_reply_count: int
    overdue_count: int
    oldest_wait_minutes: int | None


class MailboxResponseOverviewRead(BaseModel):
    conversation_count: int
    needs_reply_count: int
    overdue_count: int
    oldest_wait_minutes: int | None
    by_alias: list[MailboxResponseBucketRead]
    by_team: list[MailboxResponseBucketRead]
    by_assignee: list[MailboxResponseBucketRead]


class ConversationHandoffRequest(BaseModel):
    assigned_user_id: UUID
    queue_key: str = Field(min_length=1, max_length=120)
    reason: str = Field(min_length=1, max_length=500)


class SmsSendRequest(BaseModel):
    body: str = Field(min_length=1, max_length=1600)
    idempotency_key: str = Field(min_length=8, max_length=120)


class SmsSendRead(BaseModel):
    communication_id: UUID
    provider_message_id: str
    status: str
    recipient: str


class ConversationWatcherCreate(BaseModel):
    user_id: UUID
    notification_level: str = Field(default="all", max_length=80)


class GeneralConversationLeadCreate(BaseModel):
    property: PropertyCreate
    assigned_user_id: UUID | None = None
    source: str = Field(default="inbound_email", min_length=1, max_length=120)
    asset_class: Literal["house", "land"] | None = None

    @model_validator(mode="after")
    def require_asset_specific_property_identity(self) -> "GeneralConversationLeadCreate":
        asset_class = asset_class_for_property_type(
            self.property.property_type,
            explicit_asset_class=self.asset_class,
        )
        has_address = all(
            value.strip()
            for value in (
                self.property.street_address,
                self.property.city,
                self.property.state,
                self.property.postal_code,
            )
        )
        has_parcel = bool(
            self.property.parcel_id
            and self.property.county
            and self.property.state.strip()
        )
        if asset_class == LAND_ASSET_CLASS and (has_address or has_parcel):
            return self
        if asset_class == LAND_ASSET_CLASS:
            raise ValueError(
                "Land leads require either a complete address or APN with county and state."
            )
        if not has_address:
            raise ValueError("House leads require a complete property address.")
        return self


class GeneralConversationLeadLink(BaseModel):
    lead_id: UUID


class GeneralConversationClassification(BaseModel):
    category: Literal["general", "vendor", "administrative", "spam", "archived"]
    close: bool = True
    reason: str | None = Field(default=None, max_length=500)


class ConversationResolutionRead(BaseModel):
    action: str
    source_conversation_id: UUID
    conversation_id: UUID
    lead_id: UUID | None
    status: str
    message: str


class InboxAssigneeRead(BaseModel):
    user_id: UUID
    email: str
    display_name: str
    role_keys: list[str]


class InboxAssigneeListResponse(BaseModel):
    items: list[InboxAssigneeRead]
