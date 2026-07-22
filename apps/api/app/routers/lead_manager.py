from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.auth import Principal, require_any_permission, require_permission
from app.core.database import get_db
from app.domain.rbac import PermissionKeys
from app.schemas.lead_manager import (
    LeadManagerAcceptRequest,
    LeadManagerCaseRead,
    LeadManagerOverview,
    QualificationCompleteRequest,
    QualificationScriptCreate,
    QualificationScriptRead,
    QualificationSessionRead,
)
from app.services.lead_manager import (
    accept_case,
    approve_script,
    complete_qualification,
    create_script,
    get_overview,
)

router = APIRouter(prefix="/api/v1/lead-manager", tags=["lead-manager"])
work_dependency = require_any_permission(
    PermissionKeys.VIEW_ACQUISITION_OPERATIONS,
    PermissionKeys.MANAGE_ACQUISITION_OPERATIONS,
)
manage_dependency = require_permission(PermissionKeys.MANAGE_ACQUISITION_OPERATIONS)


@router.get("")
def read_lead_manager_overview(
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(work_dependency)],
) -> LeadManagerOverview:
    return get_overview(db, principal)


@router.post("/scripts", status_code=201)
def create_qualification_script(
    payload: QualificationScriptCreate,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(manage_dependency)],
) -> QualificationScriptRead:
    return create_script(db, principal, payload)


@router.post("/scripts/{script_id}/approve")
def approve_qualification_script(
    script_id: UUID,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(manage_dependency)],
) -> QualificationScriptRead:
    try:
        script = approve_script(db, principal, script_id)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)
        ) from exc
    if script is None:
        raise HTTPException(status_code=404, detail="Qualification script not found.")
    return script


@router.post("/cases/{case_id}/accept")
def accept_warm_lead(
    case_id: UUID,
    payload: LeadManagerAcceptRequest,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(work_dependency)],
) -> LeadManagerCaseRead:
    try:
        case = accept_case(db, principal, case_id, payload.reason)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)
        ) from exc
    if case is None:
        raise HTTPException(status_code=404, detail="Lead Manager case not found.")
    return case


@router.post("/cases/{case_id}/qualification")
def complete_guided_qualification(
    case_id: UUID,
    payload: QualificationCompleteRequest,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(work_dependency)],
) -> QualificationSessionRead:
    try:
        session = complete_qualification(db, principal, case_id, payload)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)
        ) from exc
    if session is None:
        raise HTTPException(status_code=404, detail="Lead Manager case not found.")
    return session
