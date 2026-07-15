from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.auth import Principal, require_permission
from app.core.database import get_db
from app.domain.rbac import PermissionKeys
from app.schemas.marketing import MarketingOverview, OfflineConversionGenerateResponse
from app.services.marketing import generate_offline_conversion_exports, get_marketing_overview

router = APIRouter(prefix="/api/v1/marketing", tags=["marketing"])
view_financials_dependency = require_permission(PermissionKeys.VIEW_FINANCIALS)


@router.get("")
def read_marketing_overview(
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(view_financials_dependency)],
) -> MarketingOverview:
    return get_marketing_overview(db, principal)


@router.post("/offline-conversions/generate", status_code=201)
def create_offline_conversion_exports(
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(view_financials_dependency)],
) -> OfflineConversionGenerateResponse:
    return OfflineConversionGenerateResponse(
        created=generate_offline_conversion_exports(db, principal)
    )
