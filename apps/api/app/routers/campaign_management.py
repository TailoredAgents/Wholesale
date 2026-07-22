from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.auth import Principal, require_permission
from app.core.database import get_db
from app.domain.rbac import PermissionKeys
from app.schemas.campaign_management import (
    CampaignCostCreate,
    CampaignCostRead,
    CampaignManagementOverview,
    ProspectCallingBatchCreate,
    ProspectCallingBatchRead,
    ProspectImportBatchRead,
    ProspectImportMappingCreate,
    ProspectImportMappingRead,
    ProspectImportPreview,
    ProspectImportRequest,
    ProspectScreeningDecision,
    ProspectScreeningReviewRead,
)
from app.services.campaign_management import (
    create_calling_batch,
    create_campaign_cost,
    create_import_mapping,
    create_prospect_import,
    get_campaign_management_overview,
    record_screening_decision,
    validate_prospect_import,
)

router = APIRouter(prefix="/api/v1/campaign-management", tags=["campaign-management"])
manage_campaigns_dependency = require_permission(PermissionKeys.MANAGE_ACQUISITION_OPERATIONS)


@router.get("")
def read_campaign_management(
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(manage_campaigns_dependency)],
) -> CampaignManagementOverview:
    return get_campaign_management_overview(db, principal)


@router.post("/import-mappings", status_code=201)
def create_workspace_import_mapping(
    payload: ProspectImportMappingCreate,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(manage_campaigns_dependency)],
) -> ProspectImportMappingRead:
    try:
        return create_import_mapping(db, principal, payload)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)
        ) from exc


@router.post("/imports/validate")
def validate_workspace_prospect_import(
    payload: ProspectImportRequest,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(manage_campaigns_dependency)],
) -> ProspectImportPreview:
    try:
        return validate_prospect_import(db, principal, payload)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)
        ) from exc


@router.post("/imports", status_code=201)
def create_workspace_prospect_import(
    payload: ProspectImportRequest,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(manage_campaigns_dependency)],
) -> ProspectImportBatchRead:
    try:
        return create_prospect_import(db, principal, payload)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)
        ) from exc


@router.post("/costs", status_code=201)
def create_workspace_campaign_cost(
    payload: CampaignCostCreate,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(manage_campaigns_dependency)],
) -> CampaignCostRead:
    try:
        return create_campaign_cost(db, principal, payload)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)
        ) from exc


@router.post("/calling-batches", status_code=201)
def create_workspace_calling_batch(
    payload: ProspectCallingBatchCreate,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(manage_campaigns_dependency)],
) -> ProspectCallingBatchRead:
    try:
        return create_calling_batch(db, principal, payload)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)
        ) from exc


@router.post("/prospects/{prospect_id}/screening")
def decide_workspace_prospect_screening(
    prospect_id: UUID,
    payload: ProspectScreeningDecision,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(manage_campaigns_dependency)],
) -> ProspectScreeningReviewRead:
    try:
        prospect = record_screening_decision(db, principal, prospect_id, payload)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)
        ) from exc
    if prospect is None:
        raise HTTPException(status_code=404, detail="Prospect not found.")
    return prospect
