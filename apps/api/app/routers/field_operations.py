from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.orm import Session

from app.core.auth import Principal, require_any_permission, require_permission
from app.core.database import get_db
from app.domain.rbac import PermissionKeys
from app.schemas.field_operations import (
    AppointmentDispatchCreate,
    AppointmentDispatchRead,
    CloserAvailabilityBlockCreate,
    CloserAvailabilityBlockRead,
    CloserProfileRead,
    CloserProfileUpsert,
    DispatchSlotEvaluation,
    DispatchSlotRequest,
    FieldOperationsOverview,
)
from app.services.field_operations import (
    add_availability_block,
    delete_availability_block,
    dispatch_appointment,
    evaluate_slot,
    get_overview,
    upsert_profile,
)

router = APIRouter(prefix="/api/v1/field-operations", tags=["field-operations"])
work_dependency = require_any_permission(
    PermissionKeys.VIEW_ACQUISITION_OPERATIONS,
    PermissionKeys.MANAGE_ACQUISITION_OPERATIONS,
)
manage_dependency = require_permission(PermissionKeys.MANAGE_ACQUISITION_OPERATIONS)


@router.get("")
def read_field_operations(
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(work_dependency)],
) -> FieldOperationsOverview:
    return get_overview(db, principal)


@router.put("/profiles/{user_id}")
def configure_closer(
    user_id: UUID,
    payload: CloserProfileUpsert,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(manage_dependency)],
) -> CloserProfileRead:
    try:
        profile = upsert_profile(db, principal, user_id, payload)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)
        ) from exc
    if profile is None:
        raise HTTPException(status_code=404, detail="Closer user not found.")
    return profile


@router.post("/profiles/{profile_id}/blocks", status_code=201)
def block_closer_time(
    profile_id: UUID,
    payload: CloserAvailabilityBlockCreate,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(manage_dependency)],
) -> CloserAvailabilityBlockRead:
    block = add_availability_block(db, principal, profile_id, payload)
    if block is None:
        raise HTTPException(status_code=404, detail="Closer profile not found.")
    return block


@router.delete("/blocks/{block_id}", status_code=204)
def remove_closer_block(
    block_id: UUID,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(manage_dependency)],
) -> Response:
    if not delete_availability_block(db, principal, block_id):
        raise HTTPException(status_code=404, detail="Availability block not found.")
    return Response(status_code=204)


@router.post("/evaluate")
def evaluate_dispatch_slot(
    payload: DispatchSlotRequest,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(work_dependency)],
) -> DispatchSlotEvaluation:
    try:
        result = evaluate_slot(db, principal, payload)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)
        ) from exc
    if result is None:
        raise HTTPException(status_code=404, detail="Lead not found.")
    return result


@router.post("/dispatch", status_code=201)
def schedule_dispatched_appointment(
    payload: AppointmentDispatchCreate,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(work_dependency)],
) -> AppointmentDispatchRead:
    try:
        result = dispatch_appointment(db, principal, payload)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)
        ) from exc
    if result is None:
        raise HTTPException(status_code=404, detail="Lead not found.")
    return result
