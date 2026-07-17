from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


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
    subject: str | None
    body: str
    actor_user_id: UUID | None
    actor_display_name: str | None
    occurred_at: datetime


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


class ConversationRead(BaseModel):
    id: UUID
    lead_id: UUID
    contact_id: UUID
    seller_name: str
    property_address: str
    assigned_user_id: UUID | None
    assigned_user_email: str | None
    assigned_user_display_name: str | None
    status: str
    queue_key: str
    priority: str
    unread_count: int
    last_activity_at: datetime | None
    last_inbound_at: datetime | None
    last_outbound_at: datetime | None
    closed_at: datetime | None
    watchers: list[ConversationWatcherRead]
    assignment_history: list[ConversationAssignmentEventRead]
    created_at: datetime
    updated_at: datetime


class ConversationDetailRead(ConversationRead):
    preferred_name: str | None
    contact_methods: list[ConversationContactMethodRead]
    source: str
    stage_key: str
    lead_temperature: str | None
    motivation: str | None
    desired_timeline: str | None
    property_condition: str | None
    occupancy_status: str | None
    appointment_status: str | None
    next_follow_up_at: datetime | None
    property_type: str | None
    property_county: str | None
    timeline: list[ConversationTimelineItemRead]
    open_tasks: list[ConversationTaskRead]
    appointments: list[ConversationAppointmentRead]


class ConversationListResponse(BaseModel):
    items: list[ConversationRead]


class ConversationHandoffRequest(BaseModel):
    assigned_user_id: UUID
    queue_key: str = Field(min_length=1, max_length=120)
    reason: str = Field(min_length=1, max_length=500)


class ConversationWatcherCreate(BaseModel):
    user_id: UUID
    notification_level: str = Field(default="all", max_length=80)


class InboxAssigneeRead(BaseModel):
    user_id: UUID
    email: str
    display_name: str
    role_keys: list[str]


class InboxAssigneeListResponse(BaseModel):
    items: list[InboxAssigneeRead]
