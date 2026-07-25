from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.auth import Principal, get_current_principal, require_permission
from app.core.database import get_db
from app.domain.rbac import PermissionKeys
from app.schemas.compliance import (
    ComplianceControlRunRead,
    ComplianceIncidentCreate,
    ComplianceIncidentRead,
    ComplianceIncidentResolution,
    ComplianceInstallRead,
    ComplianceOverviewRead,
    CompliancePolicyDecision,
    CompliancePolicyLegalReviewUpdate,
    CompliancePolicyRead,
    ComplianceTrainingAssign,
    ComplianceTrainingDecision,
    ComplianceTrainingRead,
    ComplianceTrainingSubmit,
    DncScreeningRefreshCreate,
    DncScreeningSourceCreate,
    DncScreeningSourceDecision,
    DncScreeningSourceRead,
)
from app.services.compliance import (
    assign_training,
    create_dnc_source,
    create_incident,
    decide_dnc_source,
    decide_policy,
    decide_training,
    get_compliance_overview,
    get_my_training,
    install_standard_policies,
    record_dnc_refresh,
    resolve_incident,
    run_compliance_controls,
    submit_training,
    update_policy_legal_review,
)

router = APIRouter(prefix="/api/v1/compliance", tags=["compliance"])
manager_dependency = require_permission(PermissionKeys.MANAGE_OPERATING_MODEL)


@router.get("")
def read_compliance_overview(
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(manager_dependency)],
) -> ComplianceOverviewRead:
    return get_compliance_overview(db, principal)


@router.post("/install")
def install_compliance_policy_set(
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(manager_dependency)],
) -> ComplianceInstallRead:
    return install_standard_policies(db, principal)


@router.patch("/policies/{policy_id}/legal-review")
def patch_policy_legal_review(
    policy_id: UUID,
    payload: CompliancePolicyLegalReviewUpdate,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(manager_dependency)],
) -> CompliancePolicyRead:
    try:
        policy = update_policy_legal_review(db, principal, policy_id, payload)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if policy is None:
        raise HTTPException(status_code=404, detail="Compliance policy not found.")
    return policy


@router.post("/policies/{policy_id}/decision")
def post_policy_decision(
    policy_id: UUID,
    payload: CompliancePolicyDecision,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(manager_dependency)],
) -> CompliancePolicyRead:
    try:
        policy = decide_policy(db, principal, policy_id, payload)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if policy is None:
        raise HTTPException(status_code=404, detail="Compliance policy not found.")
    return policy


@router.post("/dnc-sources", status_code=201)
def post_dnc_source(
    payload: DncScreeningSourceCreate,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(manager_dependency)],
) -> DncScreeningSourceRead:
    try:
        return create_dnc_source(db, principal, payload)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/dnc-sources/{source_id}/decision")
def post_dnc_source_decision(
    source_id: UUID,
    payload: DncScreeningSourceDecision,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(manager_dependency)],
) -> DncScreeningSourceRead:
    source = decide_dnc_source(db, principal, source_id, payload)
    if source is None:
        raise HTTPException(status_code=404, detail="DNC source not found.")
    return source


@router.post("/dnc-sources/{source_id}/refresh")
def post_dnc_source_refresh(
    source_id: UUID,
    payload: DncScreeningRefreshCreate,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(manager_dependency)],
) -> DncScreeningSourceRead:
    try:
        source = record_dnc_refresh(db, principal, source_id, payload)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if source is None:
        raise HTTPException(status_code=404, detail="DNC source not found.")
    return source


@router.post("/training", status_code=201)
def post_training_assignment(
    payload: ComplianceTrainingAssign,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(manager_dependency)],
) -> ComplianceTrainingRead:
    try:
        return assign_training(db, principal, payload)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/training/{record_id}/decision")
def post_training_decision(
    record_id: UUID,
    payload: ComplianceTrainingDecision,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(manager_dependency)],
) -> ComplianceTrainingRead:
    try:
        record = decide_training(db, principal, record_id, payload)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if record is None:
        raise HTTPException(status_code=404, detail="Training assignment not found.")
    return record


@router.get("/my-training")
def read_my_compliance_training(
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(get_current_principal)],
) -> list[ComplianceTrainingRead]:
    return get_my_training(db, principal)


@router.post("/my-training/{record_id}/submit")
def post_my_training_submission(
    record_id: UUID,
    payload: ComplianceTrainingSubmit,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(get_current_principal)],
) -> ComplianceTrainingRead:
    try:
        record = submit_training(db, principal, record_id, payload)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if record is None:
        raise HTTPException(status_code=404, detail="Training assignment not found.")
    return record


@router.post("/incidents", status_code=201)
def post_compliance_incident(
    payload: ComplianceIncidentCreate,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(manager_dependency)],
) -> ComplianceIncidentRead:
    return create_incident(db, principal, payload)


@router.post("/incidents/{incident_id}/resolve")
def post_incident_resolution(
    incident_id: UUID,
    payload: ComplianceIncidentResolution,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(manager_dependency)],
) -> ComplianceIncidentRead:
    incident = resolve_incident(db, principal, incident_id, payload)
    if incident is None:
        raise HTTPException(status_code=404, detail="Compliance incident not found.")
    return incident


@router.post("/control-runs", status_code=status.HTTP_201_CREATED)
def post_compliance_control_run(
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(manager_dependency)],
) -> ComplianceControlRunRead:
    return run_compliance_controls(db, principal)
