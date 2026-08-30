from collections.abc import Callable
from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from sqlalchemy.orm import Session

from app.core.auth import Principal, require_any_permission, require_permission
from app.core.database import get_db
from app.domain.rbac import PermissionKeys
from app.integrations.twilio_messaging import TwilioMessagingError
from app.integrations.twilio_voice_calls import TwilioVoiceCallError
from app.schemas.disposition_desk import (
    DispositionDeskCategory,
    DispositionDeskRead,
    DispositionDeskScope,
)
from app.schemas.disposition_execution import (
    DispositionExecutionCallCreate,
    DispositionExecutionOutcomeCreate,
    DispositionExecutionSmsCreate,
    DispositionExecutionWorkspaceRead,
    DispositionShowingCreate,
    DispositionShowingUpdate,
)
from app.schemas.disposition_intelligence import DispositionIntelligenceResponse
from app.schemas.disposition_offer_room import (
    BuyerOutcomeCreate,
    ClosingCheckpointCreate,
    ClosingCheckpointUpdate,
    DeadlineAlertAcknowledge,
    OfferNegotiationCreate,
    OfferPrimaryReplacementCreate,
    OfferRoomOfferCreate,
    OfferRoomOfferUpdate,
    OfferRoomRead,
    OfferSelectionCreate,
)
from app.schemas.disposition_outreach import (
    DispositionOutreachApprovalRequest,
    DispositionOutreachControlRequest,
    DispositionOutreachDraftCreate,
    DispositionOutreachRevisionRead,
    DispositionOutreachWorkspaceRead,
)
from app.schemas.disposition_provider import (
    ProviderDisconnectRequest,
    ProviderListingRevisionApproval,
    ProviderListingRevisionCreate,
    ProviderManualEventCreate,
    ProviderManualEventReview,
    ProviderManualLinkCreate,
    ProviderManualRefresh,
    ProviderWorkspaceRead,
)
from app.schemas.dispositions import (
    BuyerPoolConversionRequest,
    BuyerPoolDecisionUpdate,
    BuyerPoolRead,
    BuyerPoolRunRead,
    BuyerPoolSourceFilter,
    BuyerSelection,
    DispositionCaseCreate,
    DispositionCaseRead,
    DispositionCopilotAnalyzeRead,
    DispositionCopilotAnalyzeRequest,
    DispositionCopilotOverview,
    DispositionCopilotReviewRead,
    DispositionCopilotReviewRequest,
    DispositionOverview,
    DispositionPackageApprovalRequest,
    DispositionPackageShareLinkCreate,
    DispositionPackageShareLinkIssuedRead,
    DispositionPackageShareLinkRead,
    DispositionPackageShareLinkRevoke,
    DispositionPackageVersionCreate,
    DispositionPackageVersionRead,
    DispositionPackageWorkspaceRead,
    EngagementCreate,
    OfferCreate,
    ProofDocumentRead,
    ProofVerificationRequest,
    ReconciliationDecision,
)
from app.schemas.inbox import SmsSendRead
from app.schemas.voice import VoiceCallIntentRead
from app.services import (
    disposition_buyer_pool,
    disposition_desk,
    disposition_execution,
    disposition_intelligence,
    disposition_offer_room,
    disposition_outreach,
    disposition_packages,
    disposition_packet_links,
    disposition_provider,
    dispositions,
)
from app.services.disposition_copilot import (
    DispositionCopilotReviewConflict,
    analyze_disposition,
    get_disposition_copilot_overview,
    review_recommendation,
)
from app.services.messaging import (
    SmsComplianceError,
    SmsConfigurationError,
    SmsDispatchConflictError,
)
from app.services.voice import (
    VoiceComplianceError,
    VoiceConfigurationError,
    VoiceIntentConflictError,
)

router = APIRouter(prefix="/api/v1/dispositions", tags=["dispositions"])
view_dependency = require_permission(PermissionKeys.VIEW_DEALS)
edit_dependency = require_permission(PermissionKeys.EDIT_DEALS)
buyer_view_dependency = require_permission(PermissionKeys.VIEW_BUYERS)
buyer_edit_dependency = require_permission(PermissionKeys.EDIT_BUYERS)
buyer_proof_view_dependency = require_permission(PermissionKeys.VIEW_BUYER_PROOF)
buyer_proof_manage_dependency = require_permission(PermissionKeys.MANAGE_BUYER_PROOF)
package_approve_dependency = require_permission(PermissionKeys.APPROVE_DISPOSITION_PACKAGES)
outreach_manage_dependency = require_permission(PermissionKeys.MANAGE_DISPOSITION_OUTREACH)
outreach_approve_dependency = require_permission(PermissionKeys.APPROVE_DISPOSITION_OUTREACH)
buyer_selection_approve_dependency = require_permission(
    PermissionKeys.APPROVE_DISPOSITION_BUYER_SELECTION
)
outreach_view_dependency = require_any_permission(
    PermissionKeys.MANAGE_DISPOSITION_OUTREACH,
    PermissionKeys.APPROVE_DISPOSITION_OUTREACH,
)
bulk_send_dependency = require_permission(PermissionKeys.SEND_BULK_COMMUNICATIONS)
send_sms_dependency = require_any_permission(
    PermissionKeys.SEND_SMS,
    PermissionKeys.SEND_ASSIGNED_SMS,
)
call_dependency = require_any_permission(
    PermissionKeys.PLACE_CALLS,
    PermissionKeys.PLACE_ASSIGNED_CALLS,
)


def _require_private_economics(principal: Principal) -> Principal:
    if PermissionKeys.VIEW_DISPOSITION_PRIVATE_ECONOMICS not in principal.permission_keys:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=(f"Missing permission: {PermissionKeys.VIEW_DISPOSITION_PRIVATE_ECONOMICS}"),
        )
    return principal


def private_economics_view_dependency(
    principal: Annotated[Principal, Depends(view_dependency)],
) -> Principal:
    return _require_private_economics(principal)


def private_economics_edit_dependency(
    principal: Annotated[Principal, Depends(edit_dependency)],
) -> Principal:
    return _require_private_economics(principal)


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


@router.get("/intelligence")
def read_disposition_intelligence(
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(view_dependency)],
    response: Response,
    deal_id: Annotated[UUID | None, Query()] = None,
    buyer_id: Annotated[UUID | None, Query()] = None,
    agent_user_id: Annotated[UUID | None, Query()] = None,
    source: Annotated[str | None, Query(max_length=120)] = None,
    market: Annotated[str | None, Query(max_length=120)] = None,
    asset_class: Annotated[str | None, Query(max_length=40)] = None,
    start_at: Annotated[datetime | None, Query()] = None,
    end_at: Annotated[datetime | None, Query()] = None,
) -> DispositionIntelligenceResponse:
    response.headers["Cache-Control"] = "private, no-store"
    try:
        return disposition_intelligence.read_disposition_intelligence(
            db,
            principal,
            deal_id=deal_id,
            buyer_id=buyer_id,
            agent_user_id=agent_user_id,
            source=source,
            market=market,
            asset_class=asset_class,
            start_at=start_at,
            end_at=end_at,
        )
    except ValueError as exc:
        raise invalid(exc) from exc


@router.get("/desk")
def read_disposition_desk(
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(view_dependency)],
    scope: Annotated[DispositionDeskScope, Query()] = "mine",
    section: Annotated[DispositionDeskCategory | None, Query()] = None,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> DispositionDeskRead:
    try:
        return disposition_desk.read_desk(
            db,
            principal,
            requested_scope=scope,
            selected_section=section,
            offset=offset,
        )
    except PermissionError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(exc),
        ) from exc
    except ValueError as exc:
        raise invalid(exc) from exc


@router.post("/cases", status_code=201)
def open_case(
    payload: DispositionCaseCreate,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(private_economics_edit_dependency)],
) -> DispositionCaseRead:
    try:
        return dispositions.create_case(db, principal, payload)
    except PermissionError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
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
    return dispositions.case_read(db, case, principal)


def _offer_room_result(
    action: Callable[..., OfferRoomRead],
    db: Session,
    principal: Principal,
    case_id: UUID,
    response: Response,
    *args: object,
    **kwargs: object,
) -> OfferRoomRead:
    try:
        result = action(db, principal, case_id, *args, **kwargs)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise invalid(exc) from exc
    response.headers["Cache-Control"] = "private, no-store"
    return result


@router.get(
    "/cases/{case_id}/offer-room",
    dependencies=[Depends(buyer_view_dependency)],
)
def read_offer_room(
    case_id: UUID,
    response: Response,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(private_economics_view_dependency)],
) -> OfferRoomRead:
    return _offer_room_result(
        disposition_offer_room.read_workspace,
        db,
        principal,
        case_id,
        response,
    )


@router.post(
    "/cases/{case_id}/offer-room/offers",
    status_code=201,
    dependencies=[Depends(buyer_view_dependency)],
)
def create_offer_room_offer(
    case_id: UUID,
    payload: OfferRoomOfferCreate,
    response: Response,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(private_economics_edit_dependency)],
) -> OfferRoomRead:
    return _offer_room_result(
        disposition_offer_room.create_offer,
        db,
        principal,
        case_id,
        response,
        payload,
    )


@router.patch(
    "/cases/{case_id}/offer-room/offers/{offer_id}",
    dependencies=[Depends(buyer_view_dependency)],
)
def revise_offer_room_offer(
    case_id: UUID,
    offer_id: UUID,
    payload: OfferRoomOfferUpdate,
    response: Response,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(private_economics_edit_dependency)],
) -> OfferRoomRead:
    return _offer_room_result(
        disposition_offer_room.revise_offer,
        db,
        principal,
        case_id,
        response,
        offer_id,
        payload,
    )


@router.post(
    "/cases/{case_id}/offer-room/offers/{offer_id}/negotiations",
    status_code=201,
    dependencies=[Depends(buyer_view_dependency)],
)
def record_offer_room_negotiation(
    case_id: UUID,
    offer_id: UUID,
    payload: OfferNegotiationCreate,
    response: Response,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(private_economics_edit_dependency)],
) -> OfferRoomRead:
    return _offer_room_result(
        disposition_offer_room.record_negotiation,
        db,
        principal,
        case_id,
        response,
        offer_id,
        payload,
    )


@router.post(
    "/cases/{case_id}/offer-room/selections",
    status_code=201,
    dependencies=[
        Depends(buyer_view_dependency),
        Depends(buyer_selection_approve_dependency),
    ],
)
def approve_offer_room_selection(
    case_id: UUID,
    payload: OfferSelectionCreate,
    response: Response,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(private_economics_edit_dependency)],
) -> OfferRoomRead:
    return _offer_room_result(
        disposition_offer_room.select_buyers,
        db,
        principal,
        case_id,
        response,
        payload,
    )


@router.post(
    "/cases/{case_id}/offer-room/selections/{selection_id}/replace-primary",
    dependencies=[
        Depends(buyer_view_dependency),
        Depends(buyer_selection_approve_dependency),
    ],
)
def replace_offer_room_primary(
    case_id: UUID,
    selection_id: UUID,
    payload: OfferPrimaryReplacementCreate,
    response: Response,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(private_economics_edit_dependency)],
) -> OfferRoomRead:
    return _offer_room_result(
        disposition_offer_room.replace_primary,
        db,
        principal,
        case_id,
        response,
        selection_id,
        payload,
    )


@router.post(
    "/cases/{case_id}/offer-room/checkpoints",
    status_code=201,
    dependencies=[Depends(buyer_view_dependency)],
)
def create_offer_room_checkpoint(
    case_id: UUID,
    payload: ClosingCheckpointCreate,
    response: Response,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(private_economics_edit_dependency)],
) -> OfferRoomRead:
    return _offer_room_result(
        disposition_offer_room.create_checkpoint,
        db,
        principal,
        case_id,
        response,
        payload,
    )


@router.patch(
    "/cases/{case_id}/offer-room/checkpoints/{checkpoint_id}",
    dependencies=[Depends(buyer_view_dependency)],
)
def update_offer_room_checkpoint(
    case_id: UUID,
    checkpoint_id: UUID,
    payload: ClosingCheckpointUpdate,
    response: Response,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(private_economics_edit_dependency)],
) -> OfferRoomRead:
    return _offer_room_result(
        disposition_offer_room.update_checkpoint,
        db,
        principal,
        case_id,
        response,
        checkpoint_id,
        payload,
    )


@router.post(
    "/cases/{case_id}/offer-room/deadlines/scan",
    dependencies=[Depends(buyer_view_dependency)],
)
def scan_offer_room_deadlines(
    case_id: UUID,
    response: Response,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(private_economics_edit_dependency)],
) -> OfferRoomRead:
    return _offer_room_result(
        disposition_offer_room.scan_case_deadlines,
        db,
        principal,
        case_id,
        response,
    )


@router.post(
    "/cases/{case_id}/offer-room/alerts/{alert_id}/acknowledge",
    dependencies=[Depends(buyer_view_dependency)],
)
def acknowledge_offer_room_alert(
    case_id: UUID,
    alert_id: UUID,
    payload: DeadlineAlertAcknowledge,
    response: Response,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(private_economics_edit_dependency)],
) -> OfferRoomRead:
    return _offer_room_result(
        disposition_offer_room.acknowledge_alert,
        db,
        principal,
        case_id,
        response,
        alert_id,
        reason=payload.reason,
    )


@router.post(
    "/cases/{case_id}/offer-room/outcomes",
    status_code=201,
    dependencies=[Depends(buyer_view_dependency)],
)
def record_offer_room_outcome(
    case_id: UUID,
    payload: BuyerOutcomeCreate,
    response: Response,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(private_economics_edit_dependency)],
) -> OfferRoomRead:
    return _offer_room_result(
        disposition_offer_room.record_outcome,
        db,
        principal,
        case_id,
        response,
        payload,
    )


@router.get("/cases/{case_id}/package")
def read_case_package(
    case_id: UUID,
    response: Response,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(view_dependency)],
) -> DispositionPackageWorkspaceRead:
    try:
        result = disposition_packages.read_workspace(db, principal, case_id)
    except ValueError as exc:
        raise invalid(exc) from exc
    if result is None:
        raise HTTPException(status_code=404, detail="Disposition case not found.")
    response.headers["Cache-Control"] = "private, no-store"
    return result


@router.get(
    "/cases/{case_id}/outreach",
    dependencies=[Depends(view_dependency), Depends(buyer_view_dependency)],
)
def read_case_outreach(
    case_id: UUID,
    response: Response,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(outreach_view_dependency)],
) -> DispositionOutreachWorkspaceRead:
    try:
        result = disposition_outreach.read_workspace(db, principal, case_id)
    except ValueError as exc:
        raise invalid(exc) from exc
    if result is None:
        raise HTTPException(status_code=404, detail="Disposition case not found.")
    response.headers["Cache-Control"] = "private, no-store"
    return result


@router.post(
    "/cases/{case_id}/outreach/drafts",
    status_code=201,
    dependencies=[Depends(buyer_view_dependency)],
)
def create_case_outreach_draft(
    case_id: UUID,
    payload: DispositionOutreachDraftCreate,
    response: Response,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(outreach_manage_dependency)],
) -> DispositionOutreachRevisionRead:
    try:
        result = disposition_outreach.create_draft(db, principal, case_id, payload)
    except ValueError as exc:
        raise invalid(exc) from exc
    if result is None:
        raise HTTPException(status_code=404, detail="Disposition case not found.")
    response.headers["Cache-Control"] = "private, no-store"
    return result


@router.post(
    "/campaigns/{campaign_id}/outreach/{revision_id}/approve",
    dependencies=[Depends(buyer_view_dependency)],
)
def approve_campaign_outreach(
    campaign_id: UUID,
    revision_id: UUID,
    payload: DispositionOutreachApprovalRequest,
    response: Response,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(outreach_approve_dependency)],
) -> DispositionOutreachRevisionRead:
    try:
        result = disposition_outreach.approve_revision(
            db,
            principal,
            campaign_id,
            revision_id,
            payload,
        )
    except ValueError as exc:
        raise invalid(exc) from exc
    if result is None:
        raise HTTPException(status_code=404, detail="Outreach revision not found.")
    response.headers["Cache-Control"] = "private, no-store"
    return result


@router.post(
    "/campaigns/{campaign_id}/outreach/{revision_id}/release",
    dependencies=[Depends(buyer_view_dependency), Depends(bulk_send_dependency)],
)
def release_campaign_outreach(
    campaign_id: UUID,
    revision_id: UUID,
    payload: DispositionOutreachControlRequest,
    response: Response,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(outreach_approve_dependency)],
) -> DispositionOutreachRevisionRead:
    return _outreach_control(
        disposition_outreach.release_revision,
        db,
        principal,
        campaign_id,
        revision_id,
        payload,
        response,
    )


@router.post(
    "/campaigns/{campaign_id}/outreach/{revision_id}/pause",
    dependencies=[Depends(buyer_view_dependency)],
)
def pause_campaign_outreach(
    campaign_id: UUID,
    revision_id: UUID,
    payload: DispositionOutreachControlRequest,
    response: Response,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(outreach_manage_dependency)],
) -> DispositionOutreachRevisionRead:
    return _outreach_control(
        disposition_outreach.pause_revision,
        db,
        principal,
        campaign_id,
        revision_id,
        payload,
        response,
    )


@router.post(
    "/campaigns/{campaign_id}/outreach/{revision_id}/resume",
    dependencies=[Depends(buyer_view_dependency), Depends(bulk_send_dependency)],
)
def resume_campaign_outreach(
    campaign_id: UUID,
    revision_id: UUID,
    payload: DispositionOutreachControlRequest,
    response: Response,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(outreach_approve_dependency)],
) -> DispositionOutreachRevisionRead:
    return _outreach_control(
        disposition_outreach.resume_revision,
        db,
        principal,
        campaign_id,
        revision_id,
        payload,
        response,
    )


@router.post(
    "/campaigns/{campaign_id}/outreach/{revision_id}/cancel-unsent",
    dependencies=[Depends(buyer_view_dependency)],
)
def cancel_campaign_unsent_outreach(
    campaign_id: UUID,
    revision_id: UUID,
    payload: DispositionOutreachControlRequest,
    response: Response,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(outreach_manage_dependency)],
) -> DispositionOutreachRevisionRead:
    return _outreach_control(
        disposition_outreach.cancel_unsent,
        db,
        principal,
        campaign_id,
        revision_id,
        payload,
        response,
    )


@router.post(
    "/campaigns/{campaign_id}/outreach/{revision_id}/retry-failed",
    dependencies=[Depends(buyer_view_dependency), Depends(bulk_send_dependency)],
)
def retry_campaign_failed_outreach(
    campaign_id: UUID,
    revision_id: UUID,
    payload: DispositionOutreachControlRequest,
    response: Response,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(outreach_approve_dependency)],
) -> DispositionOutreachRevisionRead:
    return _outreach_control(
        disposition_outreach.retry_failed,
        db,
        principal,
        campaign_id,
        revision_id,
        payload,
        response,
    )


@router.get("/cases/{case_id}/package/versions")
def read_case_package_versions(
    case_id: UUID,
    response: Response,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(view_dependency)],
) -> list[DispositionPackageVersionRead]:
    try:
        result = disposition_packages.read_versions(db, principal, case_id)
    except ValueError as exc:
        raise invalid(exc) from exc
    if result is None:
        raise HTTPException(status_code=404, detail="Disposition case not found.")
    response.headers["Cache-Control"] = "private, no-store"
    return result


@router.post("/cases/{case_id}/package/versions", status_code=201)
def create_case_package_version(
    case_id: UUID,
    payload: DispositionPackageVersionCreate,
    response: Response,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(edit_dependency)],
) -> DispositionPackageVersionRead:
    try:
        if any(
            value is not None
            for value in (
                payload.asking_price_cents,
                payload.minimum_acceptable_cents,
                payload.desired_assignment_fee_cents,
            )
        ):
            dispositions.require_private_economics_write(principal)
        result = disposition_packages.build_version(db, principal, case_id, payload)
    except PermissionError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    except ValueError as exc:
        raise invalid(exc) from exc
    if result is None:
        raise HTTPException(status_code=404, detail="Disposition case not found.")
    response.headers["Cache-Control"] = "private, no-store"
    return result


@router.post("/cases/{case_id}/package/versions/{version_id}/approval")
def approve_case_package_version(
    case_id: UUID,
    version_id: UUID,
    payload: DispositionPackageApprovalRequest,
    response: Response,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(package_approve_dependency)],
) -> DispositionPackageVersionRead:
    try:
        result = disposition_packages.approve_version(
            db,
            principal,
            case_id,
            version_id,
            payload,
        )
    except ValueError as exc:
        raise invalid(exc) from exc
    if result is None:
        raise HTTPException(status_code=404, detail="Package version not found.")
    response.headers["Cache-Control"] = "private, no-store"
    return result


@router.get("/cases/{case_id}/provider")
def read_case_provider_workspace(
    case_id: UUID,
    response: Response,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(view_dependency)],
) -> ProviderWorkspaceRead:
    try:
        result = disposition_provider.read_workspace(db, principal, case_id)
    except ValueError as exc:
        raise invalid(exc) from exc
    if result is None:
        raise HTTPException(status_code=404, detail="Disposition case not found.")
    response.headers["Cache-Control"] = "private, no-store"
    return result


@router.post(
    "/cases/{case_id}/provider/listing-revisions",
    status_code=201,
    dependencies=[Depends(edit_dependency)],
)
def create_case_provider_listing_revision(
    case_id: UUID,
    payload: ProviderListingRevisionCreate,
    response: Response,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(outreach_manage_dependency)],
) -> ProviderWorkspaceRead:
    try:
        result = disposition_provider.create_listing_revision(db, principal, case_id, payload)
    except ValueError as exc:
        raise invalid(exc) from exc
    if result is None:
        raise HTTPException(status_code=404, detail="Disposition case not found.")
    response.headers["Cache-Control"] = "private, no-store"
    return result


@router.post("/cases/{case_id}/provider/listing-revisions/{revision_id}/approve")
def approve_case_provider_listing_revision(
    case_id: UUID,
    revision_id: UUID,
    payload: ProviderListingRevisionApproval,
    response: Response,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(outreach_approve_dependency)],
) -> ProviderWorkspaceRead:
    try:
        result = disposition_provider.approve_listing_revision(
            db,
            principal,
            case_id,
            revision_id,
            payload,
        )
    except ValueError as exc:
        raise invalid(exc) from exc
    if result is None:
        raise HTTPException(status_code=404, detail="Provider listing revision not found.")
    response.headers["Cache-Control"] = "private, no-store"
    return result


@router.get("/cases/{case_id}/provider/listing-revisions/{revision_id}/bundle")
def download_case_provider_listing_bundle(
    case_id: UUID,
    revision_id: UUID,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(view_dependency)],
) -> Response:
    try:
        result = disposition_provider.listing_bundle(db, principal, case_id, revision_id)
    except ValueError as exc:
        raise invalid(exc) from exc
    if result is None:
        raise HTTPException(status_code=404, detail="Provider listing revision not found.")
    content, file_name = result
    return Response(
        content=content,
        media_type="application/json",
        headers={
            "Cache-Control": "private, no-store",
            "Content-Disposition": f'attachment; filename="{file_name}"',
        },
    )


@router.post(
    "/cases/{case_id}/provider/manual-link",
    status_code=201,
    dependencies=[Depends(edit_dependency)],
)
def record_case_provider_manual_link(
    case_id: UUID,
    payload: ProviderManualLinkCreate,
    response: Response,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(outreach_manage_dependency)],
) -> ProviderWorkspaceRead:
    try:
        result = disposition_provider.record_manual_link(db, principal, case_id, payload)
    except ValueError as exc:
        raise invalid(exc) from exc
    if result is None:
        raise HTTPException(status_code=404, detail="Disposition case not found.")
    response.headers["Cache-Control"] = "private, no-store"
    return result


@router.post(
    "/cases/{case_id}/provider/manual-events",
    status_code=201,
    dependencies=[Depends(edit_dependency)],
)
def record_case_provider_manual_event(
    case_id: UUID,
    payload: ProviderManualEventCreate,
    response: Response,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(outreach_manage_dependency)],
) -> ProviderWorkspaceRead:
    try:
        result = disposition_provider.record_manual_event(db, principal, case_id, payload)
    except ValueError as exc:
        raise invalid(exc) from exc
    if result is None:
        raise HTTPException(status_code=404, detail="Disposition case not found.")
    response.headers["Cache-Control"] = "private, no-store"
    return result


@router.patch(
    "/cases/{case_id}/provider/manual-events/{event_id}",
    dependencies=[Depends(edit_dependency)],
)
def review_case_provider_manual_event(
    case_id: UUID,
    event_id: UUID,
    payload: ProviderManualEventReview,
    response: Response,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(outreach_manage_dependency)],
) -> ProviderWorkspaceRead:
    try:
        result = disposition_provider.review_manual_event(
            db,
            principal,
            case_id,
            event_id,
            payload,
        )
    except ValueError as exc:
        raise invalid(exc) from exc
    if result is None:
        raise HTTPException(status_code=404, detail="Provider evidence not found.")
    response.headers["Cache-Control"] = "private, no-store"
    return result


@router.post(
    "/cases/{case_id}/provider/manual-refresh",
    dependencies=[Depends(edit_dependency)],
)
def refresh_case_provider_manual_status(
    case_id: UUID,
    payload: ProviderManualRefresh,
    response: Response,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(outreach_manage_dependency)],
) -> ProviderWorkspaceRead:
    try:
        result = disposition_provider.manual_refresh(db, principal, case_id, payload)
    except ValueError as exc:
        raise invalid(exc) from exc
    if result is None:
        raise HTTPException(status_code=404, detail="Disposition case not found.")
    response.headers["Cache-Control"] = "private, no-store"
    return result


@router.post(
    "/cases/{case_id}/provider/disconnect",
    dependencies=[Depends(edit_dependency)],
)
def disconnect_case_provider_listing(
    case_id: UUID,
    payload: ProviderDisconnectRequest,
    response: Response,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(outreach_manage_dependency)],
) -> ProviderWorkspaceRead:
    try:
        result = disposition_provider.disconnect(db, principal, case_id, payload)
    except ValueError as exc:
        raise invalid(exc) from exc
    if result is None:
        raise HTTPException(status_code=404, detail="Disposition case not found.")
    response.headers["Cache-Control"] = "private, no-store"
    return result


@router.get("/cases/{case_id}/provider/export")
def download_case_provider_export(
    case_id: UUID,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(view_dependency)],
    export_format: Annotated[Literal["json", "csv"], Query(alias="format")] = "json",
) -> Response:
    result = disposition_provider.export_case(
        db,
        principal,
        case_id,
        export_format=export_format,
    )
    if result is None:
        raise HTTPException(status_code=404, detail="Disposition case not found.")
    content, file_name, media_type = result
    return Response(
        content=content,
        media_type=media_type,
        headers={
            "Cache-Control": "private, no-store",
            "Content-Disposition": f'attachment; filename="{file_name}"',
        },
    )


@router.get("/cases/{case_id}/copilot")
def read_disposition_copilot(
    case_id: UUID,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(view_dependency)],
) -> DispositionCopilotOverview:
    result = get_disposition_copilot_overview(db, principal, case_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Disposition case not found.")
    return result


@router.post("/cases/{case_id}/copilot/analyze")
def create_disposition_copilot_draft(
    case_id: UUID,
    payload: DispositionCopilotAnalyzeRequest,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(private_economics_edit_dependency)],
) -> DispositionCopilotAnalyzeRead:
    try:
        result = analyze_disposition(db, principal, case_id, payload)
    except ValueError as exc:
        raise invalid(exc) from exc
    if result is None:
        raise HTTPException(status_code=404, detail="Disposition case not found.")
    return result


@router.post("/copilot/recommendations/{recommendation_id}/review")
def review_disposition_copilot_draft(
    recommendation_id: UUID,
    payload: DispositionCopilotReviewRequest,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(private_economics_edit_dependency)],
) -> DispositionCopilotReviewRead:
    try:
        result = review_recommendation(
            db,
            principal,
            recommendation_id,
            payload,
        )
    except DispositionCopilotReviewConflict as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc
    except ValueError as exc:
        raise invalid(exc) from exc
    if result is None:
        raise HTTPException(status_code=404, detail="Recommendation not found.")
    return result


@router.post("/cases/{case_id}/package/approve")
def approve_case_package(
    case_id: UUID,
    payload: DispositionPackageApprovalRequest,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(package_approve_dependency)],
) -> DispositionCaseRead:
    return _case_action(dispositions.approve_package, db, principal, case_id, payload)


@router.post("/cases/{case_id}/matches")
def match_case_buyers(
    case_id: UUID,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(edit_dependency)],
) -> DispositionCaseRead:
    return _case_action(dispositions.generate_matches, db, principal, case_id)


@router.get(
    "/cases/{case_id}/buyer-pool",
    dependencies=[Depends(buyer_view_dependency)],
)
def read_case_buyer_pool(
    case_id: UUID,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(view_dependency)],
    source: BuyerPoolSourceFilter = "all",
    stage: Annotated[str, Query(max_length=40)] = "all",
    search: Annotated[str, Query(max_length=255)] = "",
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 50,
) -> BuyerPoolRead:
    result = disposition_buyer_pool.read_buyer_pool(
        db,
        principal,
        case_id,
        source=source,
        stage=stage,
        search=search,
        page=page,
        page_size=page_size,
    )
    if result is None:
        raise HTTPException(status_code=404, detail="Disposition case not found.")
    return result


@router.get("/cases/{case_id}/package/share-links")
def read_case_package_share_links(
    case_id: UUID,
    response: Response,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(view_dependency)],
) -> list[DispositionPackageShareLinkRead]:
    result = disposition_packet_links.list_share_links(db, principal, case_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Disposition case not found.")
    response.headers["Cache-Control"] = "private, no-store"
    return result


@router.post("/cases/{case_id}/package/share-links", status_code=201)
def create_case_package_share_link(
    case_id: UUID,
    payload: DispositionPackageShareLinkCreate,
    request: Request,
    response: Response,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(edit_dependency)],
) -> DispositionPackageShareLinkIssuedRead:
    try:
        result = disposition_packet_links.issue_share_link(
            db,
            principal,
            case_id,
            payload,
            share_url_builder=lambda token: str(
                request.url_for("download_shared_investor_package", token=token)
            ),
        )
    except ValueError as exc:
        raise invalid(exc) from exc
    if result is None:
        raise HTTPException(status_code=404, detail="Disposition case not found.")
    response.headers["Cache-Control"] = "private, no-store"
    return result


@router.post("/cases/{case_id}/package/share-links/{link_id}/revoke")
def revoke_case_package_share_link(
    case_id: UUID,
    link_id: UUID,
    payload: DispositionPackageShareLinkRevoke,
    response: Response,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(edit_dependency)],
) -> DispositionPackageShareLinkRead:
    try:
        result = disposition_packet_links.revoke_share_link(
            db,
            principal,
            case_id,
            link_id,
            payload,
        )
    except ValueError as exc:
        raise invalid(exc) from exc
    if result is None:
        raise HTTPException(status_code=404, detail="Package share link not found.")
    response.headers["Cache-Control"] = "private, no-store"
    return result


@router.get(
    "/cases/{case_id}/execution",
    dependencies=[Depends(buyer_view_dependency)],
)
def read_case_execution_workspace(
    case_id: UUID,
    response: Response,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(view_dependency)],
) -> DispositionExecutionWorkspaceRead:
    try:
        result = disposition_execution.read_workspace(db, principal, case_id)
    except ValueError as exc:
        raise invalid(exc) from exc
    if result is None:
        raise HTTPException(status_code=404, detail="Disposition case not found.")
    response.headers["Cache-Control"] = "private, no-store"
    return result


@router.post(
    "/cases/{case_id}/execution/sms",
    status_code=201,
    dependencies=[Depends(buyer_edit_dependency), Depends(send_sms_dependency)],
)
def send_case_execution_sms(
    case_id: UUID,
    payload: DispositionExecutionSmsCreate,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(edit_dependency)],
) -> SmsSendRead:
    try:
        return disposition_execution.send_pre_call_sms(db, principal, case_id, payload)
    except PermissionError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    except SmsComplianceError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(exc),
        ) from exc
    except SmsDispatchConflictError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except SmsConfigurationError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc
    except TwilioMessagingError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc
    except ValueError as exc:
        raise invalid(exc) from exc


@router.post(
    "/cases/{case_id}/execution/calls",
    status_code=201,
    dependencies=[Depends(buyer_edit_dependency), Depends(call_dependency)],
)
def start_case_execution_call(
    case_id: UUID,
    payload: DispositionExecutionCallCreate,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(edit_dependency)],
) -> VoiceCallIntentRead:
    try:
        return disposition_execution.start_candidate_call(db, principal, case_id, payload)
    except PermissionError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    except VoiceComplianceError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(exc),
        ) from exc
    except VoiceIntentConflictError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except VoiceConfigurationError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc
    except TwilioVoiceCallError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc
    except ValueError as exc:
        raise invalid(exc) from exc


@router.post(
    "/cases/{case_id}/execution/outcomes",
    dependencies=[Depends(buyer_edit_dependency)],
)
def record_case_execution_outcome(
    case_id: UUID,
    payload: DispositionExecutionOutcomeCreate,
    response: Response,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(edit_dependency)],
) -> DispositionExecutionWorkspaceRead:
    try:
        result = disposition_execution.record_call_outcome(db, principal, case_id, payload)
    except ValueError as exc:
        raise invalid(exc) from exc
    response.headers["Cache-Control"] = "private, no-store"
    return result


@router.post(
    "/cases/{case_id}/execution/showings",
    status_code=201,
    dependencies=[Depends(buyer_edit_dependency)],
)
def create_case_execution_showing(
    case_id: UUID,
    payload: DispositionShowingCreate,
    response: Response,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(edit_dependency)],
) -> DispositionExecutionWorkspaceRead:
    try:
        result = disposition_execution.create_showing(db, principal, case_id, payload)
    except ValueError as exc:
        raise invalid(exc) from exc
    response.headers["Cache-Control"] = "private, no-store"
    return result


@router.patch(
    "/cases/{case_id}/execution/showings/{showing_id}",
    dependencies=[Depends(buyer_edit_dependency)],
)
def update_case_execution_showing(
    case_id: UUID,
    showing_id: UUID,
    payload: DispositionShowingUpdate,
    response: Response,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(edit_dependency)],
) -> DispositionExecutionWorkspaceRead:
    try:
        result = disposition_execution.update_showing(
            db,
            principal,
            case_id,
            showing_id,
            payload,
        )
    except ValueError as exc:
        raise invalid(exc) from exc
    if result is None:
        raise HTTPException(status_code=404, detail="Buyer showing not found.")
    response.headers["Cache-Control"] = "private, no-store"
    return result


@router.post(
    "/cases/{case_id}/buyer-pool/runs",
    dependencies=[Depends(buyer_view_dependency)],
)
def refresh_case_buyer_pool(
    case_id: UUID,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(edit_dependency)],
) -> BuyerPoolRead:
    try:
        result = dispositions.generate_matches(db, principal, case_id)
    except ValueError as exc:
        raise invalid(exc) from exc
    if result is None:
        raise HTTPException(status_code=404, detail="Disposition case not found.")
    pool = disposition_buyer_pool.read_buyer_pool(db, principal, case_id)
    if pool is None:
        raise HTTPException(status_code=404, detail="Disposition case not found.")
    return pool


@router.get(
    "/cases/{case_id}/buyer-pool/runs",
    dependencies=[Depends(buyer_view_dependency)],
)
def read_case_buyer_pool_runs(
    case_id: UUID,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(view_dependency)],
) -> list[BuyerPoolRunRead]:
    result = disposition_buyer_pool.read_run_history(db, principal, case_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Disposition case not found.")
    return result


@router.patch(
    "/cases/{case_id}/buyer-pool/candidates/{candidate_id}",
    dependencies=[Depends(buyer_edit_dependency)],
)
def decide_case_buyer_pool_candidate(
    case_id: UUID,
    candidate_id: UUID,
    payload: BuyerPoolDecisionUpdate,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(edit_dependency)],
) -> BuyerPoolRead:
    try:
        disposition_buyer_pool.update_candidate_decision(
            db,
            principal,
            case_id,
            candidate_id,
            payload,
        )
    except ValueError as exc:
        raise invalid(exc) from exc
    result = disposition_buyer_pool.read_buyer_pool(db, principal, case_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Disposition case not found.")
    return result


@router.post("/cases/{case_id}/buyer-pool/candidates/{candidate_id}/conversion")
def convert_case_buyer_pool_candidate(
    case_id: UUID,
    candidate_id: UUID,
    payload: BuyerPoolConversionRequest,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(edit_dependency)],
) -> BuyerPoolRead:
    if PermissionKeys.EDIT_BUYERS not in principal.permission_keys:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Missing permission: {PermissionKeys.EDIT_BUYERS}",
        )
    try:
        disposition_buyer_pool.convert_external_candidate(
            db,
            principal,
            case_id,
            candidate_id,
            payload,
        )
    except ValueError as exc:
        raise invalid(exc) from exc
    result = disposition_buyer_pool.read_buyer_pool(db, principal, case_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Disposition case not found.")
    return result


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
    raise HTTPException(
        status_code=410,
        detail=("Legacy offer entry is retired. Record normalized terms through the Offer Room."),
    )


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
    principal: Annotated[Principal, Depends(private_economics_edit_dependency)],
) -> DispositionCaseRead:
    raise HTTPException(
        status_code=410,
        detail=(
            "Legacy buyer selection is retired. A disposition manager must approve primary "
            "and backup coverage through the Offer Room."
        ),
    )


@router.post("/cases/{case_id}/reconciliation")
def calculate_reconciliation(
    case_id: UUID,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(private_economics_edit_dependency)],
) -> DispositionCaseRead:
    return _case_action(dispositions.build_reconciliation, db, principal, case_id)


@router.post("/cases/{case_id}/reconciliation/decision")
def decide_case_reconciliation(
    case_id: UUID,
    payload: ReconciliationDecision,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(private_economics_edit_dependency)],
) -> DispositionCaseRead:
    return _case_action(dispositions.decide_reconciliation, db, principal, case_id, payload)


@router.get("/cases/{case_id}/package.pdf")
def download_package(
    case_id: UUID,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(view_dependency)],
) -> Response:
    try:
        result = dispositions.package_pdf(db, principal, case_id)
    except ValueError as exc:
        raise invalid(exc) from exc
    if result is None:
        raise HTTPException(status_code=404, detail="Approved deal package not found.")
    content, file_name = result
    return Response(
        content=content,
        media_type="application/pdf",
        headers={
            "Cache-Control": "private, no-store",
            "Content-Disposition": f'attachment; filename="{file_name}"',
        },
    )


@router.get("/cases/{case_id}/package/versions/{version_id}/package.pdf")
def download_exact_package_version(
    case_id: UUID,
    version_id: UUID,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(view_dependency)],
) -> Response:
    result = disposition_packages.exact_version_pdf(db, principal, case_id, version_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Stored package artifact not found.")
    content, file_name = result
    return Response(
        content=content,
        media_type="application/pdf",
        headers={
            "Cache-Control": "private, no-store",
            "Content-Disposition": f'attachment; filename="{file_name}"',
        },
    )


@router.get("/cases/{case_id}/accounting.csv")
def download_accounting_export(
    case_id: UUID,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(private_economics_view_dependency)],
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
    principal: Annotated[Principal, Depends(buyer_proof_manage_dependency)],
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


@router.get("/buyers/{buyer_id}/proof")
def list_buyer_proof(
    buyer_id: UUID,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(buyer_proof_view_dependency)],
) -> list[ProofDocumentRead]:
    result = dispositions.list_proof(db, principal, buyer_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Buyer not found.")
    return result


@router.post("/proof-documents/{document_id}/verification")
def review_buyer_proof(
    document_id: UUID,
    payload: ProofVerificationRequest,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(buyer_proof_manage_dependency)],
) -> ProofDocumentRead:
    try:
        result = dispositions.review_proof(db, principal, document_id, payload)
    except ValueError as exc:
        raise invalid(exc) from exc
    if result is None:
        raise HTTPException(status_code=404, detail="Proof-of-funds document not found.")
    return result


@router.get("/proof-documents/{document_id}/content")
def download_buyer_proof(
    document_id: UUID,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(buyer_proof_view_dependency)],
) -> Response:
    result = dispositions.get_proof_content(db, principal, document_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Proof-of-funds document not found.")
    document, content = result
    return Response(
        content=content,
        media_type=document.content_type,
        headers={
            "Cache-Control": "private, no-store",
            "Content-Disposition": f'attachment; filename="{document.file_name}"',
        },
    )


def _case_action(
    function: Callable[..., DispositionCaseRead | None],
    db: Session,
    principal: Principal,
    case_id: UUID,
    *args: object,
) -> DispositionCaseRead:
    try:
        result = function(db, principal, case_id, *args)
    except PermissionError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    except ValueError as exc:
        raise invalid(exc) from exc
    if result is None:
        raise HTTPException(status_code=404, detail="Disposition case not found.")
    return result


def _outreach_control(
    function: Callable[..., DispositionOutreachRevisionRead | None],
    db: Session,
    principal: Principal,
    campaign_id: UUID,
    revision_id: UUID,
    payload: DispositionOutreachControlRequest,
    response: Response,
) -> DispositionOutreachRevisionRead:
    try:
        result = function(
            db,
            principal,
            campaign_id,
            revision_id,
            payload,
        )
    except PermissionError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    except ValueError as exc:
        raise invalid(exc) from exc
    if result is None:
        raise HTTPException(status_code=404, detail="Outreach revision not found.")
    response.headers["Cache-Control"] = "private, no-store"
    return result
