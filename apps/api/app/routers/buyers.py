from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.auth import Principal, require_permission
from app.core.database import get_db
from app.domain.rbac import PermissionKeys
from app.schemas.buyers import BuyerCreate, BuyerListResponse, BuyerRead
from app.services.buyers import create_buyer, list_buyers

router = APIRouter(prefix="/api/v1/buyers", tags=["buyers"])
view_leads_dependency = require_permission(PermissionKeys.VIEW_LEADS)
edit_leads_dependency = require_permission(PermissionKeys.EDIT_LEADS)


@router.get("")
def read_buyers(
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(view_leads_dependency)],
) -> BuyerListResponse:
    return BuyerListResponse(items=list_buyers(db, principal))


@router.post("", status_code=201)
def create_buyer_record(
    payload: BuyerCreate,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(edit_leads_dependency)],
) -> BuyerRead:
    try:
        return create_buyer(db, principal, payload)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc
