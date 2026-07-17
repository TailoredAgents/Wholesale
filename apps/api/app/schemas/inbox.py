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


class ConversationRead(BaseModel):
    id: UUID
    lead_id: UUID
    contact_id: UUID
    seller_name: str
    property_address: str
    assigned_user_id: UUID | None
    assigned_user_email: str | None
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
