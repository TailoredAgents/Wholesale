from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.auth import Principal, require_permission
from app.core.database import get_db
from app.domain.rbac import PermissionKeys
from app.schemas.leads import (
    LeadCommunicationCreate,
    LeadCreate,
    LeadDetail,
    LeadFollowUpTaskCreate,
    LeadListResponse,
    LeadNoteCreate,
    LeadRead,
    LeadStaffUpdate,
    LeadStageUpdate,
)
from app.services.leads import (
    add_lead_communication,
    add_lead_note,
    create_lead,
    create_lead_follow_up_task,
    get_lead_detail,
    list_leads,
    update_lead_staff_details,
    update_lead_stage,
)

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
    principal: Annotated[Principal, Depends(edit_leads_dependency)],
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
