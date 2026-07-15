from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.auth import Principal, require_permission
from app.core.database import get_db
from app.domain.rbac import PermissionKeys
from app.schemas.tasks import (
    SpeedToLeadQueueResponse,
    TaskCompleteRequest,
    TaskQueueResponse,
    TaskRead,
)
from app.services.tasks import complete_task, list_open_task_queue, list_speed_to_lead_queue

router = APIRouter(prefix="/api/v1/tasks", tags=["tasks"])
view_leads_dependency = require_permission(PermissionKeys.VIEW_LEADS)
edit_leads_dependency = require_permission(PermissionKeys.EDIT_LEADS)


@router.get("/speed-to-lead")
def read_speed_to_lead_queue(
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(view_leads_dependency)],
) -> SpeedToLeadQueueResponse:
    return SpeedToLeadQueueResponse(items=list_speed_to_lead_queue(db, principal))


@router.get("/open")
def read_open_task_queue(
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(view_leads_dependency)],
) -> TaskQueueResponse:
    return TaskQueueResponse(items=list_open_task_queue(db, principal))


@router.patch("/{task_id}/complete")
def complete_acquisition_task(
    task_id: UUID,
    payload: TaskCompleteRequest,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(edit_leads_dependency)],
) -> TaskRead:
    task = complete_task(db, principal, task_id, reason=payload.reason)
    if task is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found.")
    return task
