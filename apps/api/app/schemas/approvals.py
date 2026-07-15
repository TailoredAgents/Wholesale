from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class ApprovalDecision(BaseModel):
    status: str = Field(max_length=80)
    decision_notes: str | None = Field(default=None, max_length=2000)


class ApprovalRequestRead(BaseModel):
    id: UUID
    request_type: str
    entity_type: str
    entity_id: UUID | None
    status: str
    title: str
    summary: str
    decision_notes: str | None
    due_at: datetime | None
    decided_at: datetime | None
    created_at: datetime


class ApprovalListResponse(BaseModel):
    items: list[ApprovalRequestRead]
