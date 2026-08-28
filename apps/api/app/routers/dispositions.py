from collections.abc import Callable
from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from sqlalchemy.orm import Session

from app.core.auth import Principal, require_any_permission, require_permission
from app.core.database import get_db
from app.domain.rbac import PermissionKeys
from app.schemas.disposition_desk import (
    DispositionDeskCategory,
    DispositionDeskRead,
    DispositionDeskScope,
)
from app.schemas.disposition_outreach import (
    DispositionOutreachApprovalRequest,
    DispositionOutreachControlRequest,
    DispositionOutreachDraftCreate,
    DispositionOutreachRevisionRead,
    DispositionOutreachWorkspaceRead,
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
    DispositionPackageVersionCreate,
    DispositionPackageVersionRead,
    DispositionPackageWorkspaceRead,
    EngagementCreate,
    OfferCreate,
    ProofDocumentRead,
    ProofVerificationRequest,
    ReconciliationDecision,
)
from app.services import (
    disposition_buyer_pool,
    disposition_desk,
    disposition_outreach,
    disposition_packages,
    dispositions,
)
from app.services.disposition_copilot import (
    analyze_disposition,
    get_disposition_copilot_overview,
    review_recommendation,
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
outreach_view_dependency = require_any_permission(
    PermissionKeys.MANAGE_DISPOSITION_OUTREACH,
    PermissionKeys.APPROVE_DISPOSITION_OUTREACH,
)
bulk_send_dependency = require_permission(PermissionKeys.SEND_BULK_COMMUNICATIONS)


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
    principal: Annotated[Principal, Depends(private_economics_edit_dependency)],
) -> DispositionCaseRead:
    return _case_action(dispositions.select_buyer, db, principal, case_id, payload)


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
