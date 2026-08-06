from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.auth import Principal, require_any_permission
from app.core.config import get_settings
from app.core.database import get_db
from app.domain.rbac import PermissionKeys
from app.models.foundation import OfflineConversionExport
from app.schemas.management_copilots import (
    ManagementCopilotAnalyzeRead,
    ManagementCopilotAnalyzeRequest,
    ManagementCopilotOverview,
    ManagementCopilotReviewRead,
    ManagementCopilotReviewRequest,
)
from app.schemas.marketing import (
    MarketingOverview,
    OfflineConversionGenerateResponse,
    OfflineConversionProcessResponse,
)
from app.schemas.marketing_experiments import (
    MarketingExperimentCreate,
    MarketingExperimentDecisionRequest,
    MarketingExperimentOverview,
    MarketingExperimentRead,
    MarketingExperimentUpdate,
)
from app.schemas.trust_proof import (
    TrustProofAdminOverview,
    TrustProofAdminRead,
    TrustProofCreate,
    TrustProofDecisionRequest,
    TrustProofUpdate,
)
from app.services.management_copilots import (
    analyze_management,
    get_management_copilot_overview,
    review_management_recommendation,
)
from app.services.marketing import (
    generate_offline_conversion_exports,
    get_marketing_overview,
    process_next_marketing_conversion,
)
from app.services.marketing_experiments import (
    create_marketing_experiment,
    decide_marketing_experiment,
    list_marketing_experiments,
    update_marketing_experiment,
)
from app.services.trust_proof import (
    create_trust_proof,
    decide_trust_proof,
    list_trust_proofs,
    update_trust_proof,
)

router = APIRouter(prefix="/api/v1/marketing", tags=["marketing"])
view_marketing_dependency = require_any_permission(
    PermissionKeys.VIEW_FINANCIALS,
    PermissionKeys.SEND_BULK_COMMUNICATIONS,
)
manage_public_proof_dependency = require_any_permission(PermissionKeys.MANAGE_PUBLIC_PROOF)
manage_experiments_dependency = require_any_permission(PermissionKeys.MANAGE_MARKETING_EXPERIMENTS)


def invalid(exc: ValueError) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        detail=str(exc),
    )


@router.get("/experiments")
def read_marketing_experiments(
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(view_marketing_dependency)],
) -> MarketingExperimentOverview:
    return list_marketing_experiments(db, principal)


@router.post("/experiments", status_code=201)
def create_conversion_experiment(
    payload: MarketingExperimentCreate,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(manage_experiments_dependency)],
) -> MarketingExperimentRead:
    try:
        return create_marketing_experiment(db, principal, payload)
    except (PermissionError, ValueError) as exc:
        raise invalid(ValueError(str(exc))) from exc


@router.put("/experiments/{experiment_id}")
def update_conversion_experiment(
    experiment_id: UUID,
    payload: MarketingExperimentUpdate,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(manage_experiments_dependency)],
) -> MarketingExperimentRead:
    try:
        result = update_marketing_experiment(db, principal, experiment_id, payload)
    except (PermissionError, ValueError) as exc:
        raise invalid(ValueError(str(exc))) from exc
    if result is None:
        raise HTTPException(status_code=404, detail="Marketing experiment not found.")
    return result


@router.post("/experiments/{experiment_id}/decision")
def decide_conversion_experiment(
    experiment_id: UUID,
    payload: MarketingExperimentDecisionRequest,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(manage_experiments_dependency)],
) -> MarketingExperimentRead:
    try:
        result = decide_marketing_experiment(db, principal, experiment_id, payload)
    except (PermissionError, ValueError) as exc:
        raise invalid(ValueError(str(exc))) from exc
    if result is None:
        raise HTTPException(status_code=404, detail="Marketing experiment not found.")
    return result


@router.get("/trust-proofs")
def read_trust_proofs(
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(view_marketing_dependency)],
) -> TrustProofAdminOverview:
    return list_trust_proofs(db, principal)


@router.post("/trust-proofs", status_code=201)
def create_public_proof(
    payload: TrustProofCreate,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(manage_public_proof_dependency)],
) -> TrustProofAdminRead:
    try:
        return create_trust_proof(db, principal, payload)
    except (PermissionError, ValueError) as exc:
        raise invalid(ValueError(str(exc))) from exc


@router.patch("/trust-proofs/{record_id}")
def update_public_proof(
    record_id: UUID,
    payload: TrustProofUpdate,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(manage_public_proof_dependency)],
) -> TrustProofAdminRead:
    try:
        result = update_trust_proof(db, principal, record_id, payload)
    except (PermissionError, ValueError) as exc:
        raise invalid(ValueError(str(exc))) from exc
    if result is None:
        raise HTTPException(status_code=404, detail="Public proof not found.")
    return result


@router.post("/trust-proofs/{record_id}/decision")
def decide_public_proof(
    record_id: UUID,
    payload: TrustProofDecisionRequest,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(manage_public_proof_dependency)],
) -> TrustProofAdminRead:
    try:
        result = decide_trust_proof(db, principal, record_id, payload)
    except (PermissionError, ValueError) as exc:
        raise invalid(ValueError(str(exc))) from exc
    if result is None:
        raise HTTPException(status_code=404, detail="Public proof not found.")
    return result


@router.get("")
def read_marketing_overview(
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(view_marketing_dependency)],
    period_days: Annotated[int | None, Query(ge=7, le=3650)] = None,
) -> MarketingOverview:
    return get_marketing_overview(db, principal, period_days=period_days)


@router.get("/copilot")
def read_marketing_copilot(
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(view_marketing_dependency)],
    period_days: Annotated[int, Query(ge=7, le=365)] = 30,
) -> ManagementCopilotOverview:
    return get_management_copilot_overview(
        db,
        principal,
        "marketing.analyze",
        period_days,
    )


@router.post("/copilot/analyze")
def create_marketing_copilot_draft(
    payload: ManagementCopilotAnalyzeRequest,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(view_marketing_dependency)],
) -> ManagementCopilotAnalyzeRead:
    try:
        return analyze_management(
            db,
            principal,
            "marketing.analyze",
            payload,
        )
    except ValueError as exc:
        raise invalid(exc) from exc


@router.post("/copilot/recommendations/{recommendation_id}/review")
def review_marketing_copilot_draft(
    recommendation_id: UUID,
    payload: ManagementCopilotReviewRequest,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(view_marketing_dependency)],
) -> ManagementCopilotReviewRead:
    try:
        result = review_management_recommendation(
            db,
            principal,
            "marketing.analyze",
            recommendation_id,
            payload,
        )
    except ValueError as exc:
        raise invalid(exc) from exc
    if result is None:
        raise HTTPException(status_code=404, detail="Recommendation not found.")
    return result


@router.post("/offline-conversions/generate", status_code=201)
def create_offline_conversion_exports(
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(view_marketing_dependency)],
) -> OfflineConversionGenerateResponse:
    return OfflineConversionGenerateResponse(
        created=generate_offline_conversion_exports(db, principal)
    )


@router.post("/offline-conversions/process-next")
def process_offline_conversion(
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(view_marketing_dependency)],
) -> OfflineConversionProcessResponse:
    settings = get_settings()
    processed_id = process_next_marketing_conversion(
        db,
        settings,
        organization_id=principal.organization_id,
    )
    export_status = None
    if processed_id is not None:
        export_status = db.scalar(
            select(OfflineConversionExport.status).where(
                OfflineConversionExport.organization_id == principal.organization_id,
                OfflineConversionExport.id == processed_id,
            )
        )
    return OfflineConversionProcessResponse(
        processed_id=processed_id,
        status=export_status,
    )
