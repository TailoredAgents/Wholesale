from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.orm import Session

from app.core.auth import Principal, require_any_permission, require_permission
from app.core.database import get_db
from app.domain.rbac import PermissionKeys
from app.schemas.leads import (
    LeadAppointmentCreate,
    LeadBuyerOfferCreate,
    LeadCommunicationCreate,
    LeadCreate,
    LeadDetail,
    LeadFollowUpTaskCreate,
    LeadListResponse,
    LeadMarketAnalysisRead,
    LeadMarketValueEstimateRead,
    LeadNoteCreate,
    LeadRead,
    LeadStaffUpdate,
    LeadStageUpdate,
    LeadTransactionCreate,
    LeadUnderwritingCreate,
)
from app.services.leads import (
    add_lead_communication,
    add_lead_note,
    archive_lead,
    create_lead,
    create_lead_appointment,
    create_lead_buyer_offer,
    create_lead_follow_up_task,
    create_lead_market_analysis,
    create_lead_transaction,
    create_lead_underwriting_version,
    get_latest_lead_market_analysis,
    get_lead_detail,
    list_leads,
    permanently_delete_lead,
    preview_lead_market_value,
    restore_lead,
    update_lead_staff_details,
    update_lead_stage,
)
from app.services.underwriting_reports import build_market_analysis_pdf

router = APIRouter(prefix="/api/v1/leads", tags=["leads"])
view_leads_dependency = require_any_permission(
    PermissionKeys.VIEW_LEADS,
    PermissionKeys.VIEW_ASSIGNED_LEADS,
)
view_full_leads_dependency = require_permission(PermissionKeys.VIEW_LEADS)
edit_leads_dependency = require_permission(PermissionKeys.EDIT_LEADS)
log_communications_dependency = require_any_permission(
    PermissionKeys.EDIT_LEADS,
    PermissionKeys.LOG_ASSIGNED_COMMUNICATIONS,
)
schedule_appointments_dependency = require_any_permission(
    PermissionKeys.EDIT_LEADS,
    PermissionKeys.SCHEDULE_ASSIGNED_APPOINTMENTS,
)
delete_leads_dependency = require_permission(PermissionKeys.DELETE_OR_ARCHIVE_RECORDS)


@router.get("")
def read_leads(
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(view_leads_dependency)],
    archived: bool = Query(default=False),
) -> LeadListResponse:
    return LeadListResponse(items=list_leads(db, principal, archived=archived))


@router.post("", status_code=201)
def create_seller_lead(
    payload: LeadCreate,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(edit_leads_dependency)],
) -> LeadRead:
    return create_lead(db, principal, payload)


@router.get("/{lead_id}")
def read_lead_detail(
    lead_id: UUID,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(view_leads_dependency)],
) -> LeadDetail:
    lead = get_lead_detail(db, principal, lead_id)
    if lead is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Lead not found.")
    return lead


@router.post("/{lead_id}/notes", status_code=201)
def create_lead_note(
    lead_id: UUID,
    payload: LeadNoteCreate,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(edit_leads_dependency)],
) -> LeadDetail:
    lead = add_lead_note(db, principal, lead_id, payload)
    if lead is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Lead not found.")
    return lead


@router.post("/{lead_id}/tasks", status_code=201)
def create_follow_up_task(
    lead_id: UUID,
    payload: LeadFollowUpTaskCreate,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(edit_leads_dependency)],
) -> LeadDetail:
    lead = create_lead_follow_up_task(db, principal, lead_id, payload)
    if lead is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Lead not found.")
    return lead


@router.post("/{lead_id}/communications", status_code=201)
def create_lead_communication(
    lead_id: UUID,
    payload: LeadCommunicationCreate,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(log_communications_dependency)],
) -> LeadDetail:
    try:
        lead = add_lead_communication(db, principal, lead_id, payload)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc
    if lead is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Lead not found.")
    return lead


@router.post("/{lead_id}/appointments", status_code=201)
def schedule_lead_appointment(
    lead_id: UUID,
    payload: LeadAppointmentCreate,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(schedule_appointments_dependency)],
) -> LeadDetail:
    try:
        lead = create_lead_appointment(db, principal, lead_id, payload)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc
    if lead is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Lead not found.")
    return lead


@router.post("/{lead_id}/underwriting", status_code=201)
def create_underwriting_version(
    lead_id: UUID,
    payload: LeadUnderwritingCreate,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(edit_leads_dependency)],
) -> LeadDetail:
    try:
        lead = create_lead_underwriting_version(db, principal, lead_id, payload)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc
    if lead is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Lead not found.")
    return lead


@router.get("/{lead_id}/underwriting/market-value")
def preview_underwriting_market_value(
    lead_id: UUID,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(edit_leads_dependency)],
) -> LeadMarketValueEstimateRead:
    try:
        estimate = preview_lead_market_value(db, principal, lead_id)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc
    except RuntimeError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(exc),
        ) from exc
    if estimate is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Lead not found.")
    return estimate


@router.get("/{lead_id}/underwriting/market-analysis")
def read_latest_underwriting_market_analysis(
    lead_id: UUID,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(view_full_leads_dependency)],
) -> LeadMarketAnalysisRead:
    analysis = get_latest_lead_market_analysis(db, principal, lead_id)
    if analysis is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Market analysis not found.",
        )
    return analysis


@router.post("/{lead_id}/underwriting/market-analysis", status_code=201)
def create_underwriting_market_analysis(
    lead_id: UUID,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(edit_leads_dependency)],
) -> LeadMarketAnalysisRead:
    try:
        analysis = create_lead_market_analysis(db, principal, lead_id)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc
    except RuntimeError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(exc),
        ) from exc
    if analysis is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Lead not found.")
    return analysis


@router.get("/{lead_id}/underwriting/market-analysis/{analysis_id}/report.pdf")
def download_underwriting_market_analysis_report(
    lead_id: UUID,
    analysis_id: UUID,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(edit_leads_dependency)],
    audience: Literal["investor", "client"] = Query(default="investor"),
) -> Response:
    report = build_market_analysis_pdf(
        db,
        principal,
        lead_id,
        analysis_id,
        audience=audience,
    )
    if report is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Report not found.")
    content, filename = report
    return Response(
        content=content,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("/{lead_id}/transactions", status_code=201)
def open_lead_transaction(
    lead_id: UUID,
    payload: LeadTransactionCreate,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(edit_leads_dependency)],
) -> LeadDetail:
    try:
        lead = create_lead_transaction(db, principal, lead_id, payload)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc
    if lead is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Lead not found.")
    return lead


@router.post("/{lead_id}/buyer-offers", status_code=201)
def record_lead_buyer_offer(
    lead_id: UUID,
    payload: LeadBuyerOfferCreate,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(edit_leads_dependency)],
) -> LeadDetail:
    try:
        lead = create_lead_buyer_offer(db, principal, lead_id, payload)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc
    if lead is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Lead not found.")
    return lead


@router.patch("/{lead_id}")
def update_seller_lead_details(
    lead_id: UUID,
    payload: LeadStaffUpdate,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(edit_leads_dependency)],
) -> LeadDetail:
    lead = update_lead_staff_details(db, principal, lead_id, payload)
    if lead is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Lead not found.")
    return lead


@router.patch("/{lead_id}/stage")
def update_seller_lead_stage(
    lead_id: UUID,
    payload: LeadStageUpdate,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(edit_leads_dependency)],
) -> LeadDetail:
    try:
        lead = update_lead_stage(db, principal, lead_id, payload)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc
    if lead is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Lead not found.")
    return lead


@router.delete("/{lead_id}")
def archive_seller_lead(
    lead_id: UUID,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(delete_leads_dependency)],
) -> LeadRead:
    lead = archive_lead(db, principal, lead_id)
    if lead is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Lead not found.")
    return lead


@router.post("/{lead_id}/restore")
def restore_seller_lead(
    lead_id: UUID,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(delete_leads_dependency)],
) -> LeadRead:
    lead = restore_lead(db, principal, lead_id)
    if lead is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Lead not found.")
    return lead


@router.delete("/{lead_id}/permanent", status_code=status.HTTP_204_NO_CONTENT)
def permanently_delete_seller_lead(
    lead_id: UUID,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(delete_leads_dependency)],
    confirmation: str = Query(default=""),
) -> Response:
    if confirmation != "DELETE":
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail='Type "DELETE" to confirm permanent deletion.',
        )
    try:
        deleted = permanently_delete_lead(db, principal, lead_id)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Lead not found.")
    return Response(status_code=status.HTTP_204_NO_CONTENT)
