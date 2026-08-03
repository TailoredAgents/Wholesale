from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.auth import Principal, require_any_permission, require_permission
from app.core.database import get_db
from app.domain.rbac import PermissionKeys
from app.schemas.tasks import (
    AiOperationReviewRead,
    AiOperationReviewRequest,
    PrimaryNextActionCreate,
    SpeedToLeadQueueResponse,
    TaskCompleteRequest,
    TaskQueueResponse,
    TaskRead,
    TaskWorkspaceRead,
)
from app.services.ai_operations import review_ai_operation
from app.services.tasks import (
    complete_task,
    create_primary_next_action,
    list_open_task_queue,
    list_speed_to_lead_queue,
    list_task_workspace,
)

router = APIRouter(prefix="/api/v1/tasks", tags=["tasks"])
view_leads_dependency = require_permission(PermissionKeys.VIEW_LEADS)
view_tasks_dependency = require_any_permission(
    PermissionKeys.VIEW_LEADS,
    PermissionKeys.VIEW_ASSIGNED_LEADS,
    PermissionKeys.VIEW_DEALS,
    PermissionKeys.VIEW_FINANCIALS,
    PermissionKeys.VIEW_ACQUISITION_OPERATIONS,
    PermissionKeys.VIEW_AUDIT_LOGS,
    PermissionKeys.APPROVE_OFFERS,
    PermissionKeys.SEND_CONTRACTS,
)
edit_tasks_dependency = require_any_permission(
    PermissionKeys.EDIT_LEADS,
    PermissionKeys.EDIT_DEALS,
    PermissionKeys.MANAGE_ACQUISITION_OPERATIONS,
)


@router.get("/workspace")
def read_task_workspace(
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(view_tasks_dependency)],
) -> TaskWorkspaceRead:
    return list_task_workspace(db, principal)


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


@router.patch("/ai-work/{event_id}/review")
def review_ai_work_item(
    event_id: UUID,
    payload: AiOperationReviewRequest,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(view_tasks_dependency)],
) -> AiOperationReviewRead:
    try:
        result = review_ai_operation(db, principal, event_id, payload)
    except PermissionError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(exc),
        ) from exc
    if result is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="AI work not found.")
    return result


@router.patch("/{task_id}/complete")
def complete_acquisition_task(
    task_id: UUID,
    payload: TaskCompleteRequest,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(edit_tasks_dependency)],
) -> TaskRead:
    try:
        task = complete_task(db, principal, task_id, payload=payload)
    except PermissionError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(exc),
        ) from exc
    if task is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found.")
    return task


@router.post("/primary-next-actions", status_code=status.HTTP_201_CREATED)
def set_primary_next_action(
    payload: PrimaryNextActionCreate,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(edit_tasks_dependency)],
) -> TaskRead:
    try:
        return create_primary_next_action(db, principal, payload)
    except PermissionError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(exc),
        ) from exc
