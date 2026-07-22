from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from sqlalchemy.orm import Session

from app.core.auth import Principal, require_permission
from app.core.database import get_db
from app.domain.rbac import PermissionKeys
from app.schemas.dispositions import (
    BuyerSelection,
    DispositionCaseCreate,
    DispositionCaseRead,
    DispositionOverview,
    EngagementCreate,
    OfferCreate,
    ProofDocumentRead,
    ReconciliationDecision,
)
from app.services import dispositions

router = APIRouter(prefix="/api/v1/dispositions", tags=["dispositions"])
view_dependency = require_permission(PermissionKeys.VIEW_DEALS)
edit_dependency = require_permission(PermissionKeys.EDIT_DEALS)
buyer_edit_dependency = require_permission(PermissionKeys.EDIT_BUYERS)


def invalid(exc: ValueError) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        detail=str(exc),
    )


@router.get("")
def read_overview(
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(view_dependency)],
) -> DispositionOverview:
    return dispositions.overview(db, principal)


@router.post("/cases", status_code=201)
def open_case(
    payload: DispositionCaseCreate,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(edit_dependency)],
) -> DispositionCaseRead:
    try:
        return dispositions.create_case(db, principal, payload)
    except ValueError as exc:
        raise invalid(exc) from exc


@router.get("/cases/{case_id}")
def read_case(
    case_id: UUID,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(view_dependency)],
) -> DispositionCaseRead:
    case = dispositions.scoped_case(db, principal, case_id)
    if case is None:
        raise HTTPException(status_code=404, detail="Disposition case not found.")
    return dispositions.case_read(db, case)


@router.post("/cases/{case_id}/package/approve")
def approve_case_package(
    case_id: UUID,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(edit_dependency)],
) -> DispositionCaseRead:
    return _case_action(dispositions.approve_package, db, principal, case_id)


@router.post("/cases/{case_id}/matches")
def match_case_buyers(
    case_id: UUID,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(edit_dependency)],
) -> DispositionCaseRead:
    return _case_action(dispositions.generate_matches, db, principal, case_id)


@router.post("/cases/{case_id}/campaigns/release")
def release_case_campaign(
    case_id: UUID,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(edit_dependency)],
) -> DispositionCaseRead:
    return _case_action(dispositions.release_campaign, db, principal, case_id)


@router.post("/cases/{case_id}/offers")
def record_offer(
    case_id: UUID,
    payload: OfferCreate,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(edit_dependency)],
) -> DispositionCaseRead:
    return _case_action(dispositions.create_offer, db, principal, case_id, payload)


@router.post("/cases/{case_id}/engagements")
def record_engagement(
    case_id: UUID,
    payload: EngagementCreate,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(edit_dependency)],
) -> DispositionCaseRead:
    return _case_action(dispositions.add_engagement, db, principal, case_id, payload)


@router.post("/cases/{case_id}/buyer-selection")
def approve_buyer_selection(
    case_id: UUID,
    payload: BuyerSelection,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(edit_dependency)],
) -> DispositionCaseRead:
    return _case_action(dispositions.select_buyer, db, principal, case_id, payload)


@router.post("/cases/{case_id}/reconciliation")
def calculate_reconciliation(
    case_id: UUID,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(edit_dependency)],
) -> DispositionCaseRead:
    return _case_action(dispositions.build_reconciliation, db, principal, case_id)


@router.post("/cases/{case_id}/reconciliation/decision")
def decide_case_reconciliation(
    case_id: UUID,
    payload: ReconciliationDecision,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(edit_dependency)],
) -> DispositionCaseRead:
    return _case_action(dispositions.decide_reconciliation, db, principal, case_id, payload)


@router.get("/cases/{case_id}/package.pdf")
def download_package(
    case_id: UUID,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(view_dependency)],
) -> Response:
    result = dispositions.package_pdf(db, principal, case_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Approved deal package not found.")
    content, file_name = result
    return Response(
        content=content,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{file_name}"'},
    )


@router.get("/cases/{case_id}/accounting.csv")
def download_accounting_export(
    case_id: UUID,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(view_dependency)],
) -> Response:
    content = dispositions.accounting_csv(db, principal, case_id)
    if content is None:
        raise HTTPException(status_code=404, detail="Approved reconciliation not found.")
    return Response(
        content=content,
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="deal-{case_id}-accounting.csv"'},
    )


@router.post("/buyers/{buyer_id}/proof", status_code=201)
async def upload_buyer_proof(
    buyer_id: UUID,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(buyer_edit_dependency)],
    file_name: Annotated[str, Query(min_length=1, max_length=255)],
    content_type: Annotated[str, Query(min_length=1, max_length=120)],
    institution_name: Annotated[str | None, Query(max_length=255)] = None,
    verified_amount_cents: Annotated[int | None, Query(ge=0)] = None,
    expires_at: datetime | None = None,
) -> ProofDocumentRead:
    try:
        return dispositions.upload_proof(
            db,
            principal,
            buyer_id,
            content=await request.body(),
            file_name=file_name,
            content_type=content_type,
            institution_name=institution_name,
            verified_amount_cents=verified_amount_cents,
            expires_at=expires_at,
        )
    except ValueError as exc:
        raise invalid(exc) from exc


def _case_action(function, db: Session, principal: Principal, case_id: UUID, *args):
    try:
        result = function(db, principal, case_id, *args)
    except ValueError as exc:
        raise invalid(exc) from exc
    if result is None:
        raise HTTPException(status_code=404, detail="Disposition case not found.")
    return result
