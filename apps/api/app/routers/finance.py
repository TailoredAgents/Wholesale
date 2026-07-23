from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.core.auth import Principal, require_permission
from app.core.database import get_db
from app.domain.rbac import PermissionKeys
from app.schemas.finance import (
    CompensationRuleCreate,
    CompensationRuleRead,
    DealDeductionCreate,
    DealDeductionRead,
    FinanceOverview,
    MarketingSpendCreate,
    MarketingSpendRead,
    RevenueCreate,
    RevenueRead,
)
from app.services.finance import (
    create_compensation_rule,
    create_deal_deduction,
    create_marketing_spend,
    create_revenue_record,
    get_finance_overview,
)

router = APIRouter(prefix="/api/v1/finance", tags=["finance"])
view_financials_dependency = require_permission(PermissionKeys.VIEW_FINANCIALS)
change_compensation_dependency = require_permission(PermissionKeys.CHANGE_COMPENSATION_RULES)


@router.get("")
def read_finance_overview(
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(view_financials_dependency)],
    period_days: Annotated[int | None, Query(ge=7, le=3650)] = None,
) -> FinanceOverview:
    return get_finance_overview(db, principal, period_days=period_days)


@router.post("/revenue", status_code=201)
def record_revenue(
    payload: RevenueCreate,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(view_financials_dependency)],
) -> RevenueRead:
    try:
        return create_revenue_record(db, principal, payload)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc


@router.post("/deductions", status_code=201)
def record_deduction(
    payload: DealDeductionCreate,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(view_financials_dependency)],
) -> DealDeductionRead:
    try:
        return create_deal_deduction(db, principal, payload)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc


@router.post("/compensation-rules", status_code=201)
def record_compensation_rule(
    payload: CompensationRuleCreate,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(change_compensation_dependency)],
) -> CompensationRuleRead:
    try:
        return create_compensation_rule(db, principal, payload)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc


@router.post("/marketing-spend", status_code=201)
def record_marketing_spend(
    payload: MarketingSpendCreate,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(view_financials_dependency)],
) -> MarketingSpendRead:
    return create_marketing_spend(db, principal, payload)
