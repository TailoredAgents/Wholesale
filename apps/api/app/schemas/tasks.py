from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field


class TaskQueueItemRead(BaseModel):
    task_id: UUID
    lead_id: UUID | None
    deal_id: UUID | None
    task_type: str
    work_kind: str
    title: str
    seller_name: str | None
    property_address: str | None
    source: str | None
    stage_key: str | None
    priority: str
    status: str
    due_at: datetime | None
    created_at: datetime
    completed_at: datetime | None
    assigned_user_id: UUID | None
    assigned_user_email: str | None
    due_status: str


class SpeedToLeadQueueResponse(BaseModel):
    items: list[TaskQueueItemRead]


class TaskQueueResponse(BaseModel):
    items: list[TaskQueueItemRead]


class SuccessorTaskCreate(BaseModel):
    title: str = Field(min_length=3, max_length=255)
    task_type: str = Field(default="follow_up", min_length=1, max_length=120)
    due_at: datetime
    responsible_user_id: UUID | None = None
    priority: Literal["urgent", "high", "normal", "low"] = "normal"


class TaskCompleteRequest(BaseModel):
    reason: str | None = Field(default=None, max_length=500)
    outcome: str | None = Field(default=None, max_length=120)
    completion_notes: str | None = Field(default=None, max_length=2000)
    successor: SuccessorTaskCreate | None = None


class PrimaryNextActionCreate(BaseModel):
    source_record_type: Literal["lead", "deal"]
    source_record_id: UUID
    title: str = Field(min_length=3, max_length=255)
    action_type: str = Field(min_length=1, max_length=120)
    due_at: datetime
    responsible_user_id: UUID | None = None
    priority: Literal["urgent", "high", "normal", "low"] = "normal"
    reason: str = Field(min_length=3, max_length=500)


class TaskWorkspaceItemRead(BaseModel):
    id: str
    item_type: Literal["task", "approval"]
    work_kind: Literal[
        "primary_next_action",
        "supporting",
        "operational_exception",
        "approval",
    ]
    source_record_type: str
    source_record_id: UUID | None
    source_record_label: str
    source_record_detail: str | None
    source_url: str | None
    task_id: UUID | None = None
    approval_id: UUID | None = None
    task_type: str
    title: str
    summary: str | None
    status: str
    priority: str
    due_at: datetime | None
    due_status: Literal["overdue", "today", "upcoming", "unscheduled", "completed"]
    created_at: datetime
    completed_at: datetime | None
    assigned_user_id: UUID | None
    assigned_user_name: str | None
    assigned_user_email: str | None
    outcome: str | None
    completion_notes: str | None
    attention_flags: list[str] = Field(default_factory=list)
    can_complete: bool = False
    can_decide: bool = False
    review_url: str | None = None
    approval_metadata: dict[str, object] = Field(default_factory=dict)


class TaskWorkspaceRead(BaseModel):
    items: list[TaskWorkspaceItemRead]
    can_manage_team: bool
    can_decide_approvals: bool
    current_user_id: UUID
    current_user_email: str


class PrimaryNextActionRead(BaseModel):
    task_id: UUID
    title: str
    action_type: str
    due_at: datetime | None
    responsible_user_id: UUID | None
    responsible_user_email: str | None
    due_status: str


class TaskRead(BaseModel):
    id: UUID
    lead_id: UUID | None
    deal_id: UUID | None
    task_type: str
    work_kind: str
    title: str
    status: str
    priority: str
    due_at: datetime | None
    completed_at: datetime | None
    completed_by_user_id: UUID | None
    outcome: str | None
    completion_notes: str | None
    successor_task_id: UUID | None
