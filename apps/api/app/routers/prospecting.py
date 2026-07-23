from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.auth import Principal, require_any_permission, require_permission
from app.core.database import get_db
from app.domain.rbac import PermissionKeys
from app.schemas.prospecting import (
    ProspectHandoffDecision,
    ProspectHandoffRead,
    ProspectingAttemptComplete,
    ProspectingCallQualityAnalyzeRead,
    ProspectingCallQualityRead,
    ProspectingCallQualityReviewRequest,
    ProspectingCopilotAnalyzeRead,
    ProspectingCopilotAnalyzeRequest,
    ProspectingCopilotReviewRead,
    ProspectingCopilotReviewRequest,
    ProspectingEntryRead,
    ProspectingScriptCreate,
    ProspectingScriptRead,
    ProspectingWorkbenchOverview,
)
from app.services.prospecting import (
    approve_script,
    complete_attempt,
    create_script,
    decide_handoff,
    get_prospecting_overview,
    start_attempt,
)
from app.services.prospecting_copilot import (
    analyze_call_quality,
    analyze_entry,
    review_call_quality,
    review_recommendation,
)

router = APIRouter(prefix="/api/v1/prospecting", tags=["prospecting"])
work_dependency = require_any_permission(
    PermissionKeys.WORK_ASSIGNED_CALLING_LISTS,
    PermissionKeys.MANAGE_ACQUISITION_OPERATIONS,
)
manage_dependency = require_permission(PermissionKeys.MANAGE_ACQUISITION_OPERATIONS)


@router.get("")
def read_prospecting_workbench(
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(work_dependency)],
) -> ProspectingWorkbenchOverview:
    return get_prospecting_overview(db, principal)


@router.post("/scripts", status_code=201)
def create_prospecting_script(
    payload: ProspectingScriptCreate,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(manage_dependency)],
) -> ProspectingScriptRead:
    try:
        return create_script(db, principal, payload)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(exc),
        ) from exc


@router.post("/scripts/{script_id}/approve")
def approve_prospecting_script(
    script_id: UUID,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(manage_dependency)],
) -> ProspectingScriptRead:
    try:
        script = approve_script(db, principal, script_id)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(exc),
        ) from exc
    if script is None:
        raise HTTPException(status_code=404, detail="Caller script not found.")
    return script


@router.post("/entries/{entry_id}/start")
def start_prospecting_attempt(
    entry_id: UUID,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(work_dependency)],
) -> ProspectingEntryRead:
    try:
        entry = start_attempt(db, principal, entry_id)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(exc),
        ) from exc
    if entry is None:
        raise HTTPException(status_code=404, detail="Assigned prospect not found.")
    return entry


@router.post("/attempts/{attempt_id}/complete")
def complete_prospecting_attempt(
    attempt_id: UUID,
    payload: ProspectingAttemptComplete,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(work_dependency)],
) -> ProspectingEntryRead:
    try:
        entry = complete_attempt(db, principal, attempt_id, payload)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(exc),
        ) from exc
    if entry is None:
        raise HTTPException(status_code=404, detail="Prospecting attempt not found.")
    return entry


@router.post("/handoffs/{handoff_id}/decision")
def review_prospect_handoff(
    handoff_id: UUID,
    payload: ProspectHandoffDecision,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(manage_dependency)],
) -> ProspectHandoffRead:
    try:
        handoff = decide_handoff(db, principal, handoff_id, payload)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(exc),
        ) from exc
    if handoff is None:
        raise HTTPException(status_code=404, detail="Warm handoff not found.")
    return handoff


@router.post("/entries/{entry_id}/copilot/analyze")
def analyze_prospecting_entry(
    entry_id: UUID,
    payload: ProspectingCopilotAnalyzeRequest,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(work_dependency)],
) -> ProspectingCopilotAnalyzeRead:
    try:
        result = analyze_entry(db, principal, entry_id, payload)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(exc),
        ) from exc
    if result is None:
        raise HTTPException(status_code=404, detail="Assigned prospect not found.")
    return result


@router.post("/copilot/recommendations/{recommendation_id}/review")
def review_prospecting_copilot_recommendation(
    recommendation_id: UUID,
    payload: ProspectingCopilotReviewRequest,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(work_dependency)],
) -> ProspectingCopilotReviewRead:
    try:
        review = review_recommendation(db, principal, recommendation_id, payload)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(exc),
        ) from exc
    if review is None:
        raise HTTPException(status_code=404, detail="Copilot recommendation not found.")
    return review


@router.post("/attempts/{attempt_id}/quality/analyze")
def analyze_prospecting_call_quality(
    attempt_id: UUID,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(work_dependency)],
) -> ProspectingCallQualityAnalyzeRead:
    try:
        result = analyze_call_quality(db, principal, attempt_id)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(exc),
        ) from exc
    if result is None:
        raise HTTPException(status_code=404, detail="Prospecting attempt not found.")
    return result


@router.post("/attempts/{attempt_id}/quality/review")
def review_prospecting_call_quality_result(
    attempt_id: UUID,
    payload: ProspectingCallQualityReviewRequest,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(manage_dependency)],
) -> ProspectingCallQualityRead:
    try:
        result = review_call_quality(db, principal, attempt_id, payload)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(exc),
        ) from exc
    if result is None:
        raise HTTPException(status_code=404, detail="Call-quality review not found.")
    return result
