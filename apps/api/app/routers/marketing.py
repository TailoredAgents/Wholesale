from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.auth import Principal, require_any_permission
from app.core.database import get_db
from app.domain.rbac import PermissionKeys
from app.schemas.marketing import MarketingOverview, OfflineConversionGenerateResponse
from app.services.marketing import generate_offline_conversion_exports, get_marketing_overview

router = APIRouter(prefix="/api/v1/marketing", tags=["marketing"])
view_marketing_dependency = require_any_permission(
    PermissionKeys.VIEW_FINANCIALS,
    PermissionKeys.SEND_BULK_COMMUNICATIONS,
)


@router.get("")
def read_marketing_overview(
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(view_marketing_dependency)],
    period_days: Annotated[int | None, Query(ge=7, le=3650)] = None,
) -> MarketingOverview:
    return get_marketing_overview(db, principal, period_days=period_days)


@router.post("/offline-conversions/generate", status_code=201)
def create_offline_conversion_exports(
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(view_marketing_dependency)],
) -> OfflineConversionGenerateResponse:
    return OfflineConversionGenerateResponse(
        created=generate_offline_conversion_exports(db, principal)
    )
