from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class TaskQueueItemRead(BaseModel):
    task_id: UUID
    lead_id: UUID
    task_type: str
    title: str
    seller_name: str
    property_address: str
    source: str
    stage_key: str
    priority: str
    status: str
    due_at: datetime | None
    created_at: datetime
    assigned_user_email: str | None
    due_status: str


class SpeedToLeadQueueResponse(BaseModel):
    items: list[TaskQueueItemRead]


class TaskQueueResponse(BaseModel):
    items: list[TaskQueueItemRead]


class TaskCompleteRequest(BaseModel):
    reason: str | None = Field(default=None, max_length=500)


class TaskRead(BaseModel):
    id: UUID
    lead_id: UUID | None
    task_type: str
    title: str
    status: str
    priority: str
    due_at: datetime | None
    completed_at: datetime | None
