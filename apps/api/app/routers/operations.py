from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.auth import Principal, require_any_permission, require_permission
from app.core.database import get_db
from app.domain.rbac import PermissionKeys
from app.schemas.operations import (
    AcquisitionOperationsOverview,
    CallingListCreate,
    CallingListEntryRead,
    CallingListEntryUpdate,
    CallingListLeadAdd,
    CallingListRead,
    DuplicateCandidateRead,
    DuplicateResolution,
    FollowUpEnrollmentCreate,
    FollowUpPlanCreate,
    FollowUpPlanRead,
    NotificationRead,
    OperationsUserCreate,
    OperationsUserRead,
    OperationsUserUpdate,
    SavedViewCreate,
    SavedViewRead,
    TeamCreate,
    TeamMemberCreate,
    TeamRead,
)
from app.services.acquisition_operations import (
    add_calling_list_leads,
    add_team_member,
    create_calling_list,
    create_follow_up_plan,
    create_operations_user,
    create_saved_view,
    create_team,
    enroll_follow_up_plan,
    get_operations_overview,
    mark_notification_read,
    resolve_duplicate_candidate,
    scan_duplicate_candidates,
    update_calling_list_entry,
    update_operations_user,
)

router = APIRouter(prefix="/api/v1/operations", tags=["operations"])
view_operations_dependency = require_any_permission(
    PermissionKeys.VIEW_ACQUISITION_OPERATIONS,
    PermissionKeys.WORK_ASSIGNED_CALLING_LISTS,
)
manage_operations_dependency = require_permission(PermissionKeys.MANAGE_ACQUISITION_OPERATIONS)


@router.get("")
def read_operations_overview(
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(view_operations_dependency)],
) -> AcquisitionOperationsOverview:
    return get_operations_overview(db, principal)


@router.post("/users", status_code=201)
def create_workspace_user(
    payload: OperationsUserCreate,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(manage_operations_dependency)],
) -> OperationsUserRead:
    try:
        return create_operations_user(db, principal, payload)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)
        ) from exc


@router.patch("/users/{user_id}")
def update_workspace_user(
    user_id: UUID,
    payload: OperationsUserUpdate,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(manage_operations_dependency)],
) -> OperationsUserRead:
    try:
        user = update_operations_user(db, principal, user_id, payload)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)
        ) from exc
    if user is None:
        raise HTTPException(status_code=404, detail="Workspace user not found.")
    return user


@router.post("/teams", status_code=201)
def create_workspace_team(
    payload: TeamCreate,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(manage_operations_dependency)],
) -> TeamRead:
    try:
        return create_team(db, principal, payload)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/teams/{team_id}/members")
def upsert_workspace_team_member(
    team_id: UUID,
    payload: TeamMemberCreate,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(manage_operations_dependency)],
) -> TeamRead:
    try:
        team = add_team_member(db, principal, team_id, payload)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if team is None:
        raise HTTPException(status_code=404, detail="Team not found.")
    return team


@router.post("/calling-lists", status_code=201)
def create_workspace_calling_list(
    payload: CallingListCreate,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(manage_operations_dependency)],
) -> CallingListRead:
    try:
        return create_calling_list(db, principal, payload)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/calling-lists/{calling_list_id}/leads")
def add_workspace_calling_list_leads(
    calling_list_id: UUID,
    payload: CallingListLeadAdd,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(manage_operations_dependency)],
) -> CallingListRead:
    try:
        calling_list = add_calling_list_leads(db, principal, calling_list_id, payload)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if calling_list is None:
        raise HTTPException(status_code=404, detail="Calling list not found.")
    return calling_list


@router.patch("/calling-list-entries/{entry_id}")
def record_calling_list_attempt(
    entry_id: UUID,
    payload: CallingListEntryUpdate,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(view_operations_dependency)],
) -> CallingListEntryRead:
    try:
        entry = update_calling_list_entry(db, principal, entry_id, payload)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if entry is None:
        raise HTTPException(status_code=404, detail="Calling-list record not found.")
    return entry


@router.post("/saved-views", status_code=201)
def create_workspace_saved_view(
    payload: SavedViewCreate,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(view_operations_dependency)],
) -> SavedViewRead:
    try:
        return create_saved_view(db, principal, payload)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.patch("/notifications/{notification_id}/read")
def read_workspace_notification(
    notification_id: UUID,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(view_operations_dependency)],
) -> NotificationRead:
    notification = mark_notification_read(db, principal, notification_id)
    if notification is None:
        raise HTTPException(status_code=404, detail="Notification not found.")
    return notification


@router.post("/duplicates/scan")
def scan_workspace_duplicates(
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(manage_operations_dependency)],
) -> dict[str, int]:
    return {"created": scan_duplicate_candidates(db, principal)}


@router.post("/duplicates/{candidate_id}/resolve")
def resolve_workspace_duplicate(
    candidate_id: UUID,
    payload: DuplicateResolution,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(manage_operations_dependency)],
) -> DuplicateCandidateRead:
    try:
        candidate = resolve_duplicate_candidate(db, principal, candidate_id, payload)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if candidate is None:
        raise HTTPException(status_code=404, detail="Duplicate candidate not found.")
    return candidate


@router.post("/follow-up-plans", status_code=201)
def create_workspace_follow_up_plan(
    payload: FollowUpPlanCreate,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(manage_operations_dependency)],
) -> FollowUpPlanRead:
    try:
        return create_follow_up_plan(db, principal, payload)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/follow-up-plans/{plan_id}/enroll")
def enroll_workspace_follow_up_plan(
    plan_id: UUID,
    payload: FollowUpEnrollmentCreate,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(manage_operations_dependency)],
) -> FollowUpPlanRead:
    try:
        plan = enroll_follow_up_plan(db, principal, plan_id, payload)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if plan is None:
        raise HTTPException(status_code=404, detail="Follow-up plan not found.")
    return plan
