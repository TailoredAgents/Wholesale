from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.auth import Principal, require_permission
from app.core.database import get_db
from app.domain.rbac import PermissionKeys
from app.schemas.leads import LeadCreate, LeadListResponse, LeadRead
from app.services.leads import create_lead, list_leads

router = APIRouter(prefix="/api/v1/leads", tags=["leads"])
view_leads_dependency = require_permission(PermissionKeys.VIEW_LEADS)
edit_leads_dependency = require_permission(PermissionKeys.EDIT_LEADS)


@router.get("")
def read_leads(
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(view_leads_dependency)],
) -> LeadListResponse:
    return LeadListResponse(items=list_leads(db, principal))


@router.post("", status_code=201)
def create_seller_lead(
    payload: LeadCreate,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(edit_leads_dependency)],
) -> LeadRead:
    return create_lead(db, principal, payload)
