from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.auth import Principal, require_permission
from app.core.database import get_db
from app.domain.rbac import PermissionKeys
from app.schemas.deals import DealDetailRead, DealOverviewRead
from app.services import deals

router = APIRouter(prefix="/api/v1/deals", tags=["deals"])
view_dependency = require_permission(PermissionKeys.VIEW_DEALS)


@router.get("")
def read_deals(
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(view_dependency)],
) -> DealOverviewRead:
    return deals.overview(db, principal)


@router.get("/{deal_id}")
def read_deal(
    deal_id: UUID,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(view_dependency)],
) -> DealDetailRead:
    result = deals.detail(db, principal, deal_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Deal not found.")
    return result
