from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.auth import Principal, require_permission
from app.core.database import get_db
from app.domain.rbac import PermissionKeys
from app.schemas.underwriting import (
    CalibrationCaseRead,
    CalibrationCaseUpsert,
    CalibrationDecisionAction,
    CalibrationDecisionCreate,
    CalibrationDecisionRead,
    CalibrationOverview,
)
from app.services.underwriting_calibration import (
    create_calibration_decision,
    decide_calibration_decision,
    get_calibration_case,
    get_calibration_overview,
    upsert_calibration_case,
)

router = APIRouter(prefix="/api/v1/underwriting", tags=["underwriting"])
view_underwriting_dependency = require_permission(PermissionKeys.EDIT_UNDERWRITING)
calibrate_underwriting_dependency = require_permission(PermissionKeys.APPROVE_ARV)


@router.get("/calibration")
def read_calibration_overview(
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(view_underwriting_dependency)],
) -> CalibrationOverview:
    return get_calibration_overview(db, principal)


@router.get("/calibration-cases/{analysis_id}")
def read_calibration_case(
    analysis_id: UUID,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(view_underwriting_dependency)],
) -> CalibrationCaseRead | None:
    return get_calibration_case(db, principal, analysis_id)


@router.put("/calibration-cases/{analysis_id}")
def record_calibration_case(
    analysis_id: UUID,
    payload: CalibrationCaseUpsert,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(calibrate_underwriting_dependency)],
) -> CalibrationCaseRead:
    try:
        return upsert_calibration_case(db, principal, analysis_id, payload)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc


@router.post("/calibration-decisions", status_code=status.HTTP_201_CREATED)
def create_methodology_decision(
    payload: CalibrationDecisionCreate,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(calibrate_underwriting_dependency)],
) -> CalibrationDecisionRead:
    try:
        return create_calibration_decision(db, principal, payload)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc


@router.patch("/calibration-decisions/{decision_id}")
def decide_methodology_decision(
    decision_id: UUID,
    payload: CalibrationDecisionAction,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(calibrate_underwriting_dependency)],
) -> CalibrationDecisionRead:
    try:
        return decide_calibration_decision(db, principal, decision_id, payload)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc
