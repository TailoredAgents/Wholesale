from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.core.auth import Principal, require_permission
from app.core.database import get_db
from app.domain.rbac import PermissionKeys
from app.schemas.finance import (
    AccountingProfileUpdate,
    AccountingSetupRead,
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
from app.schemas.management_copilots import (
    ManagementCopilotAnalyzeRead,
    ManagementCopilotAnalyzeRequest,
    ManagementCopilotOverview,
    ManagementCopilotReviewRead,
    ManagementCopilotReviewRequest,
)
from app.services.finance import (
    create_compensation_rule,
    create_deal_deduction,
    create_marketing_spend,
    create_revenue_record,
    get_accounting_setup,
    get_finance_overview,
    update_accounting_profile,
)
from app.services.management_copilots import (
    analyze_management,
    get_management_copilot_overview,
    review_management_recommendation,
)

router = APIRouter(prefix="/api/v1/finance", tags=["finance"])
view_financials_dependency = require_permission(PermissionKeys.VIEW_FINANCIALS)
change_compensation_dependency = require_permission(PermissionKeys.CHANGE_COMPENSATION_RULES)
manage_accounting_dependency = require_permission(PermissionKeys.MANAGE_ACCOUNTING_POLICY)


def invalid(exc: ValueError) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        detail=str(exc),
    )


@router.get("")
def read_finance_overview(
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(view_financials_dependency)],
    period_days: Annotated[int | None, Query(ge=7, le=3650)] = None,
) -> FinanceOverview:
    return get_finance_overview(db, principal, period_days=period_days)


@router.get("/accounting/setup")
def read_accounting_setup(
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(view_financials_dependency)],
) -> AccountingSetupRead:
    return get_accounting_setup(db, principal)


@router.put("/accounting/profile")
def change_accounting_profile(
    payload: AccountingProfileUpdate,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(manage_accounting_dependency)],
) -> AccountingSetupRead:
    try:
        return update_accounting_profile(db, principal, payload)
    except ValueError as exc:
        raise invalid(exc) from exc


@router.get("/copilot")
def read_finance_copilot(
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(view_financials_dependency)],
    period_days: Annotated[int, Query(ge=7, le=365)] = 30,
) -> ManagementCopilotOverview:
    return get_management_copilot_overview(
        db,
        principal,
        "finance.reconcile",
        period_days,
    )


@router.get("/tax-copilot")
def read_tax_copilot(
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(view_financials_dependency)],
    period_days: Annotated[int, Query(ge=7, le=365)] = 30,
) -> ManagementCopilotOverview:
    return get_management_copilot_overview(
        db,
        principal,
        "finance.tax_review",
        period_days,
    )


@router.post("/tax-copilot/analyze")
def create_tax_copilot_draft(
    payload: ManagementCopilotAnalyzeRequest,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(view_financials_dependency)],
) -> ManagementCopilotAnalyzeRead:
    try:
        return analyze_management(
            db,
            principal,
            "finance.tax_review",
            payload,
        )
    except ValueError as exc:
        raise invalid(exc) from exc


@router.post("/tax-copilot/recommendations/{recommendation_id}/review")
def review_tax_copilot_draft(
    recommendation_id: UUID,
    payload: ManagementCopilotReviewRequest,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(view_financials_dependency)],
) -> ManagementCopilotReviewRead:
    try:
        result = review_management_recommendation(
            db,
            principal,
            "finance.tax_review",
            recommendation_id,
            payload,
        )
    except ValueError as exc:
        raise invalid(exc) from exc
    if result is None:
        raise HTTPException(status_code=404, detail="Recommendation not found.")
    return result


@router.post("/copilot/analyze")
def create_finance_copilot_draft(
    payload: ManagementCopilotAnalyzeRequest,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(view_financials_dependency)],
) -> ManagementCopilotAnalyzeRead:
    try:
        return analyze_management(
            db,
            principal,
            "finance.reconcile",
            payload,
        )
    except ValueError as exc:
        raise invalid(exc) from exc


@router.post("/copilot/recommendations/{recommendation_id}/review")
def review_finance_copilot_draft(
    recommendation_id: UUID,
    payload: ManagementCopilotReviewRequest,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(view_financials_dependency)],
) -> ManagementCopilotReviewRead:
    try:
        result = review_management_recommendation(
            db,
            principal,
            "finance.reconcile",
            recommendation_id,
            payload,
        )
    except ValueError as exc:
        raise invalid(exc) from exc
    if result is None:
        raise HTTPException(status_code=404, detail="Recommendation not found.")
    return result


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
