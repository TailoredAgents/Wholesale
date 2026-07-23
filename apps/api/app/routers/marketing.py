from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.core.auth import Principal, require_any_permission
from app.core.database import get_db
from app.domain.rbac import PermissionKeys
from app.schemas.management_copilots import (
    ManagementCopilotAnalyzeRead,
    ManagementCopilotAnalyzeRequest,
    ManagementCopilotOverview,
    ManagementCopilotReviewRead,
    ManagementCopilotReviewRequest,
)
from app.schemas.marketing import MarketingOverview, OfflineConversionGenerateResponse
from app.services.management_copilots import (
    analyze_management,
    get_management_copilot_overview,
    review_management_recommendation,
)
from app.services.marketing import generate_offline_conversion_exports, get_marketing_overview

router = APIRouter(prefix="/api/v1/marketing", tags=["marketing"])
view_marketing_dependency = require_any_permission(
    PermissionKeys.VIEW_FINANCIALS,
    PermissionKeys.SEND_BULK_COMMUNICATIONS,
)


def invalid(exc: ValueError) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        detail=str(exc),
    )


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
