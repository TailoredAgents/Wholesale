from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.orm import Session

from app.core.auth import Principal, require_any_permission, require_permission
from app.core.config import get_settings
from app.core.database import get_db
from app.domain.rbac import PermissionKeys
from app.integrations.realestateapi_client import RealEstateAPIError
from app.schemas.approvals import (
    OfferConcessionCreate,
    OfferConcessionPresent,
    OfferConcessionRead,
    OfferNegotiationEventCreate,
    OfferNegotiationEventRead,
    OfferNegotiationLedgerRead,
    OfferNegotiationPlanCreate,
    OfferNegotiationPlanListResponse,
    OfferNegotiationPlanRead,
)
from app.schemas.leads import (
    LeadAppointmentCreate,
    LeadAppointmentUpdate,
    LeadBuyerOfferCreate,
    LeadCloseOutRead,
    LeadCloseOutRequest,
    LeadCommunicationCreate,
    LeadCreate,
    LeadDetail,
    LeadFollowUpTaskCreate,
    LeadListResponse,
    LeadMarketAnalysisCreate,
    LeadMarketAnalysisRead,
    LeadMarketValueEstimateRead,
    LeadNoteCreate,
    LeadRead,
    LeadReopenRead,
    LeadReopenRequest,
    LeadStaffUpdate,
    LeadStageUpdate,
    LeadTransactionCreate,
    LeadUnderwritingCreate,
    PropertyIntelligenceRead,
    PropertyValidationRead,
    RepairCatalogRead,
    RepairEstimateCreate,
    RepairEstimateRead,
    SmsPermissionUpdate,
    UnderwritingManualComparableCreate,
    UnderwritingManualComparableRead,
)
from app.schemas.underwriting_comp_copilot import (
    CompCopilotAnswerRead,
    CompCopilotAskRequest,
    CompCopilotThreadRead,
)
from app.services.acquisition_operations import update_appointment
from app.services.lead_lifecycle import LeadLifecycleConflictError
from app.services.leads import (
    AppointmentConflictError,
    add_lead_communication,
    add_lead_note,
    archive_lead,
    close_out_lead,
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
    reopen_lead,
    restore_lead,
    update_lead_sms_permission,
    update_lead_staff_details,
    update_lead_stage,
    validate_lead_property_address,
)
from app.services.offer_approvals import (
    create_offer_negotiation_plan,
    list_offer_negotiation_plans,
)
from app.services.offer_concessions import (
    create_concession,
    create_negotiation_event,
    get_negotiation_ledger,
    present_concession,
)
from app.services.property_intelligence import (
    get_property_image_content,
    request_property_research,
)
from app.services.repair_estimates import (
    create_repair_estimate,
    get_repair_catalog,
    list_repair_estimates,
)
from app.services.underwriting_comp_copilot import (
    ask_comp_copilot,
    get_comp_copilot_thread,
)
from app.services.underwriting_manual_comps import (
    create_manual_comparable,
    list_manual_comparables,
    void_manual_comparable,
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
sms_permission_dependency = require_any_permission(
    PermissionKeys.EDIT_LEADS,
    PermissionKeys.SEND_SMS,
    PermissionKeys.SEND_ASSIGNED_SMS,
)


@router.get("")
def read_leads(
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(view_leads_dependency)],
    archived: bool = Query(default=False),
    closed: bool = Query(default=False),
    asset_class: Literal["house", "land"] | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=101),
    offset: int = Query(default=0, ge=0),
    q: str | None = Query(default=None, max_length=200),
) -> LeadListResponse:
    return LeadListResponse(
        items=list_leads(
            db,
            principal,
            archived=archived,
            closed=closed,
            asset_class=asset_class,
            limit=limit,
            offset=offset,
            q=q,
        )
    )


@router.post("", status_code=201)
def create_seller_lead(
    payload: LeadCreate,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(edit_leads_dependency)],
) -> LeadRead:
    try:
        return create_lead(db, principal, payload)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(exc),
        ) from exc


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


@router.patch("/{lead_id}/sms-permission")
def record_lead_sms_permission(
    lead_id: UUID,
    payload: SmsPermissionUpdate,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(sms_permission_dependency)],
) -> LeadDetail:
    try:
        lead = update_lead_sms_permission(db, principal, lead_id, payload)
    except LeadLifecycleConflictError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc
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
    except AppointmentConflictError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc
    except PermissionError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(exc),
        ) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc
    if lead is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Lead not found.")
    return lead


@router.patch("/{lead_id}/appointments/{appointment_id}")
def update_lead_appointment(
    lead_id: UUID,
    appointment_id: UUID,
    payload: LeadAppointmentUpdate,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(schedule_appointments_dependency)],
) -> LeadDetail:
    try:
        lead = update_appointment(db, principal, lead_id, appointment_id, payload)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if lead is None:
        raise HTTPException(status_code=404, detail="Appointment not found.")
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


@router.get("/{lead_id}/repair-estimates")
def read_repair_estimates(
    lead_id: UUID,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(view_full_leads_dependency)],
) -> list[RepairEstimateRead]:
    estimates = list_repair_estimates(db, principal, lead_id)
    if estimates is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Lead not found.")
    return estimates


@router.get("/{lead_id}/repair-catalog")
def read_repair_catalog(
    lead_id: UUID,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(view_full_leads_dependency)],
) -> RepairCatalogRead:
    catalog = get_repair_catalog(db, principal, lead_id)
    if catalog is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Lead not found.")
    return catalog


@router.post("/{lead_id}/repair-estimates", status_code=201)
def record_repair_estimate(
    lead_id: UUID,
    payload: RepairEstimateCreate,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(edit_leads_dependency)],
) -> RepairEstimateRead:
    try:
        estimate = create_repair_estimate(db, principal, lead_id, payload)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if estimate is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Lead not found.")
    return estimate


@router.get("/{lead_id}/underwriting/manual-comps")
def read_underwriting_manual_comparables(
    lead_id: UUID,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(view_full_leads_dependency)],
) -> list[UnderwritingManualComparableRead]:
    comparables = list_manual_comparables(db, principal, lead_id)
    if comparables is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Lead not found.")
    return comparables


@router.post("/{lead_id}/underwriting/manual-comps", status_code=201)
def record_underwriting_manual_comparable(
    lead_id: UUID,
    payload: UnderwritingManualComparableCreate,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(edit_leads_dependency)],
) -> UnderwritingManualComparableRead:
    try:
        comparable = create_manual_comparable(db, principal, lead_id, payload)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if comparable is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Lead not found.")
    return comparable


@router.delete(
    "/{lead_id}/underwriting/manual-comps/{comparable_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def remove_underwriting_manual_comparable(
    lead_id: UUID,
    comparable_id: UUID,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(edit_leads_dependency)],
) -> Response:
    removed = void_manual_comparable(db, principal, lead_id, comparable_id)
    if removed is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Lead not found.")
    if removed is False:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Manual comparable not found.",
        )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/{lead_id}/underwriting/offer-plans")
def read_offer_negotiation_plans(
    lead_id: UUID,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(view_full_leads_dependency)],
) -> OfferNegotiationPlanListResponse:
    plans = list_offer_negotiation_plans(db, principal, lead_id)
    if plans is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Lead not found.")
    return plans


@router.post("/{lead_id}/underwriting/offer-plans", status_code=201)
def request_offer_ceiling_approval(
    lead_id: UUID,
    payload: OfferNegotiationPlanCreate,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(edit_leads_dependency)],
) -> OfferNegotiationPlanRead:
    try:
        plan = create_offer_negotiation_plan(db, principal, lead_id, payload)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if plan is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Lead not found.")
    return plan


@router.get("/{lead_id}/underwriting/negotiation-ledger")
def read_offer_negotiation_ledger(
    lead_id: UUID,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(view_full_leads_dependency)],
) -> OfferNegotiationLedgerRead:
    ledger = get_negotiation_ledger(db, principal, lead_id)
    if ledger is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Lead not found.")
    return ledger


@router.post("/{lead_id}/underwriting/concessions", status_code=201)
def request_offer_concession(
    lead_id: UUID,
    payload: OfferConcessionCreate,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(edit_leads_dependency)],
) -> OfferConcessionRead:
    try:
        concession = create_concession(db, principal, lead_id, payload)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if concession is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Lead not found.")
    return concession


@router.post("/{lead_id}/underwriting/concessions/{concession_id}/present")
def record_offer_concession_presented(
    lead_id: UUID,
    concession_id: UUID,
    payload: OfferConcessionPresent,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(edit_leads_dependency)],
) -> OfferConcessionRead:
    try:
        concession = present_concession(db, principal, lead_id, concession_id, payload)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if concession is None:
        raise HTTPException(status_code=404, detail="Concession not found.")
    return concession


@router.post("/{lead_id}/underwriting/negotiation-events", status_code=201)
def record_offer_negotiation_event(
    lead_id: UUID,
    payload: OfferNegotiationEventCreate,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(edit_leads_dependency)],
) -> OfferNegotiationEventRead:
    try:
        event = create_negotiation_event(db, principal, lead_id, payload)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if event is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Lead not found.")
    return event


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


@router.post("/{lead_id}/property-validation")
def validate_property_address(
    lead_id: UUID,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(edit_leads_dependency)],
) -> PropertyValidationRead:
    try:
        validation = validate_lead_property_address(db, principal, lead_id)
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
    if validation is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Lead not found.")
    return validation


@router.post("/{lead_id}/property-intelligence/refresh", status_code=202)
def refresh_property_intelligence(
    lead_id: UUID,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(edit_leads_dependency)],
) -> PropertyIntelligenceRead:
    try:
        intelligence = request_property_research(db, principal, lead_id)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc
    if intelligence is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Lead not found.")
    return intelligence


@router.get("/{lead_id}/property-image")
def read_property_image(
    lead_id: UUID,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(view_leads_dependency)],
    view: Literal["listing"] = Query(default="listing"),
) -> Response:
    try:
        image = get_property_image_content(
            db,
            principal,
            lead_id,
            get_settings(),
            view=view,
        )
    except RealEstateAPIError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc
    if image is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Property image not found."
        )
    return Response(
        content=image.content,
        media_type=image.content_type,
        headers={
            "Cache-Control": "private, max-age=300",
            "X-Property-Image-Source": image.source,
        },
    )


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
    payload: LeadMarketAnalysisCreate | None = None,
) -> LeadMarketAnalysisRead:
    try:
        analysis = create_lead_market_analysis(db, principal, lead_id, payload)
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


@router.post("/{lead_id}/underwriting/market-analysis/review", status_code=201)
def apply_underwriting_comp_review(
    lead_id: UUID,
    payload: LeadMarketAnalysisCreate,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(edit_leads_dependency)],
) -> LeadMarketAnalysisRead:
    if payload.source_analysis_id is None or not payload.comp_review_decisions:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="A source analysis and comparable review decisions are required.",
        )
    try:
        analysis = create_lead_market_analysis(db, principal, lead_id, payload)
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


@router.get(
    "/{lead_id}/underwriting/market-analysis/{analysis_id}/copilot",
)
def read_underwriting_comp_copilot(
    lead_id: UUID,
    analysis_id: UUID,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(view_full_leads_dependency)],
) -> CompCopilotThreadRead:
    thread = get_comp_copilot_thread(
        db,
        principal,
        lead_id,
        analysis_id,
        get_settings(),
    )
    if thread is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Analysis not found.")
    return thread


@router.post(
    "/{lead_id}/underwriting/market-analysis/{analysis_id}/copilot/messages",
    status_code=201,
)
def create_underwriting_comp_copilot_message(
    lead_id: UUID,
    analysis_id: UUID,
    payload: CompCopilotAskRequest,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(edit_leads_dependency)],
) -> CompCopilotAnswerRead:
    try:
        answer = ask_comp_copilot(
            db,
            principal,
            lead_id,
            analysis_id,
            get_settings(),
            question=payload.question,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc
    if answer is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Analysis not found.")
    return answer


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
    try:
        lead = update_lead_staff_details(db, principal, lead_id, payload)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc
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


@router.post("/{lead_id}/close-out")
def close_out_seller_lead(
    lead_id: UUID,
    payload: LeadCloseOutRequest,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(edit_leads_dependency)],
) -> LeadCloseOutRead:
    try:
        result = close_out_lead(db, principal, lead_id, payload)
    except LeadLifecycleConflictError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc
    if result is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Lead not found.")
    return result


@router.post("/{lead_id}/reopen")
def reopen_seller_lead(
    lead_id: UUID,
    payload: LeadReopenRequest,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(edit_leads_dependency)],
) -> LeadReopenRead:
    try:
        result = reopen_lead(db, principal, lead_id, payload)
    except LeadLifecycleConflictError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc
    if result is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Lead not found.")
    return result


@router.delete("/{lead_id}")
def archive_seller_lead(
    lead_id: UUID,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(delete_leads_dependency)],
) -> LeadRead:
    try:
        lead = archive_lead(db, principal, lead_id)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc
    if lead is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Lead not found.")
    return lead


@router.post("/{lead_id}/restore")
def restore_seller_lead(
    lead_id: UUID,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(delete_leads_dependency)],
) -> LeadRead:
    try:
        lead = restore_lead(db, principal, lead_id)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc
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
