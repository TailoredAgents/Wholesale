from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.auth import Principal, require_permission
from app.core.database import get_db
from app.domain.rbac import PermissionKeys
from app.schemas.leads import DashboardSummary
from app.services.leads import get_dashboard_summary

router = APIRouter(prefix="/api/v1/dashboard", tags=["dashboard"])
view_leads_dependency = require_permission(PermissionKeys.VIEW_LEADS)


@router.get("/summary")
def read_dashboard_summary(
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(view_leads_dependency)],
) -> DashboardSummary:
    return get_dashboard_summary(db, principal)
