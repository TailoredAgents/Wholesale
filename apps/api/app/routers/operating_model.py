from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.auth import Principal, get_current_principal, require_permission
from app.core.database import get_db
from app.domain.rbac import PermissionKeys
from app.schemas.operating_model import (
    BusinessCounterpartyCreate,
    BusinessCounterpartyDecision,
    BusinessCounterpartyRead,
    CompanySetupInstallRead,
    CompensationPlanActivation,
    CompensationPlanCreate,
    CompensationPlanRead,
    MarketLaunchChecklistApproval,
    MarketLaunchChecklistCreate,
    MarketLaunchChecklistItemRead,
    MarketLaunchChecklistItemUpdate,
    MarketLaunchChecklistRead,
    MyRoleSetupRead,
    OperatingModelOverview,
    OperatingSeatRead,
    OperatingSeatUpdate,
    RoleCreditCreate,
    RoleCreditDecision,
    RoleCreditRead,
    StaffRoleAcceptanceAssign,
    StaffRoleAcceptanceDecision,
    StaffRoleAcceptanceRead,
    StaffRoleAcceptanceSubmit,
)
from app.services.company_setup import (
    assign_role_acceptance,
    create_counterparty,
    decide_counterparty,
    decide_role_acceptance,
    get_my_role_setup,
    install_company_setup,
    submit_role_acceptance,
    update_operating_seat,
)
from app.services.operating_model import (
    activate_compensation_plan,
    approve_market_launch_checklist,
    create_compensation_plan,
    create_market_launch_checklist,
    create_role_credit,
    decide_role_credit,
    get_operating_model_overview,
    update_market_launch_item,
)

router = APIRouter(prefix="/api/v1/operating-model", tags=["operating-model"])
manage_operating_model_dependency = require_permission(PermissionKeys.MANAGE_OPERATING_MODEL)


@router.get("/my-setup")
def read_my_role_setup(
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(get_current_principal)],
) -> MyRoleSetupRead:
    try:
        return get_my_role_setup(db, principal)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/my-setup/role-acceptances/{acceptance_id}/submit")
def submit_my_role_acceptance(
    acceptance_id: UUID,
    payload: StaffRoleAcceptanceSubmit,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(get_current_principal)],
) -> StaffRoleAcceptanceRead:
    try:
        acceptance = submit_role_acceptance(db, principal, acceptance_id, payload)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(exc),
        ) from exc
    if acceptance is None:
        raise HTTPException(status_code=404, detail="Role acceptance not found.")
    return acceptance


@router.get("")
def read_operating_model(
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(manage_operating_model_dependency)],
) -> OperatingModelOverview:
    return get_operating_model_overview(db, principal)


@router.post("/setup/install")
def install_workspace_company_setup(
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(manage_operating_model_dependency)],
) -> CompanySetupInstallRead:
    return install_company_setup(db, principal)


@router.patch("/setup/seats/{seat_id}")
def update_workspace_operating_seat(
    seat_id: UUID,
    payload: OperatingSeatUpdate,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(manage_operating_model_dependency)],
) -> OperatingSeatRead:
    try:
        seat = update_operating_seat(db, principal, seat_id, payload)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(exc),
        ) from exc
    if seat is None:
        raise HTTPException(status_code=404, detail="Operating seat not found.")
    return seat


@router.post("/setup/counterparties", status_code=201)
def create_workspace_counterparty(
    payload: BusinessCounterpartyCreate,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(manage_operating_model_dependency)],
) -> BusinessCounterpartyRead:
    try:
        return create_counterparty(db, principal, payload)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(exc),
        ) from exc


@router.post("/setup/counterparties/{counterparty_id}/decision")
def decide_workspace_counterparty(
    counterparty_id: UUID,
    payload: BusinessCounterpartyDecision,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(manage_operating_model_dependency)],
) -> BusinessCounterpartyRead:
    counterparty = decide_counterparty(db, principal, counterparty_id, payload)
    if counterparty is None:
        raise HTTPException(status_code=404, detail="Counterparty not found.")
    return counterparty


@router.post("/setup/role-acceptances", status_code=201)
def assign_workspace_role_acceptance(
    payload: StaffRoleAcceptanceAssign,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(manage_operating_model_dependency)],
) -> StaffRoleAcceptanceRead:
    try:
        return assign_role_acceptance(db, principal, payload)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(exc),
        ) from exc


@router.post("/setup/role-acceptances/{acceptance_id}/decision")
def decide_workspace_role_acceptance(
    acceptance_id: UUID,
    payload: StaffRoleAcceptanceDecision,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(manage_operating_model_dependency)],
) -> StaffRoleAcceptanceRead:
    try:
        acceptance = decide_role_acceptance(db, principal, acceptance_id, payload)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(exc),
        ) from exc
    if acceptance is None:
        raise HTTPException(status_code=404, detail="Role acceptance not found.")
    return acceptance


@router.post("/compensation-plans", status_code=201)
def create_workspace_compensation_plan(
    payload: CompensationPlanCreate,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(manage_operating_model_dependency)],
) -> CompensationPlanRead:
    try:
        return create_compensation_plan(db, principal, payload)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(exc),
        ) from exc


@router.post("/compensation-plans/{plan_id}/activate")
def activate_workspace_compensation_plan(
    plan_id: UUID,
    payload: CompensationPlanActivation,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(manage_operating_model_dependency)],
) -> CompensationPlanRead:
    try:
        plan = activate_compensation_plan(db, principal, plan_id, payload)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(exc),
        ) from exc
    if plan is None:
        raise HTTPException(status_code=404, detail="Compensation plan not found.")
    return plan


@router.post("/role-credits", status_code=201)
def create_workspace_role_credit(
    payload: RoleCreditCreate,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(manage_operating_model_dependency)],
) -> RoleCreditRead:
    try:
        return create_role_credit(db, principal, payload)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(exc),
        ) from exc


@router.post("/role-credits/{credit_id}/decision")
def decide_workspace_role_credit(
    credit_id: UUID,
    payload: RoleCreditDecision,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(manage_operating_model_dependency)],
) -> RoleCreditRead:
    try:
        credit = decide_role_credit(db, principal, credit_id, payload)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(exc),
        ) from exc
    if credit is None:
        raise HTTPException(status_code=404, detail="Role credit not found.")
    return credit


@router.post("/markets/{market_id}/launch-checklists", status_code=201)
def create_workspace_market_launch_checklist(
    market_id: UUID,
    payload: MarketLaunchChecklistCreate,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(manage_operating_model_dependency)],
) -> MarketLaunchChecklistRead:
    try:
        checklist = create_market_launch_checklist(db, principal, market_id, payload)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(exc),
        ) from exc
    if checklist is None:
        raise HTTPException(status_code=404, detail="Market not found.")
    return checklist


@router.patch("/launch-checklist-items/{item_id}")
def update_workspace_market_launch_item(
    item_id: UUID,
    payload: MarketLaunchChecklistItemUpdate,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(manage_operating_model_dependency)],
) -> MarketLaunchChecklistItemRead:
    try:
        item = update_market_launch_item(db, principal, item_id, payload)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(exc),
        ) from exc
    if item is None:
        raise HTTPException(status_code=404, detail="Market launch item not found.")
    return item


@router.post("/launch-checklists/{checklist_id}/approve")
def approve_workspace_market_launch_checklist(
    checklist_id: UUID,
    payload: MarketLaunchChecklistApproval,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(manage_operating_model_dependency)],
) -> MarketLaunchChecklistRead:
    try:
        checklist = approve_market_launch_checklist(db, principal, checklist_id, payload)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(exc),
        ) from exc
    if checklist is None:
        raise HTTPException(status_code=404, detail="Market launch checklist not found.")
    return checklist
