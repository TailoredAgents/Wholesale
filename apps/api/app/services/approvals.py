from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.auth import Principal
from app.domain.rbac import PermissionKeys
from app.models.foundation import (
    ActivityEvent,
    ApprovalRequest,
    AuditEvent,
    Lead,
    OfferNegotiationPlan,
    UnderwritingVersion,
)
from app.schemas.approvals import ApprovalDecision, ApprovalRequestRead
from app.services.offer_concessions import (
    apply_concession_decision,
    supersede_prior_offer_authority,
    validate_concession_decision,
)

APPROVAL_STATUSES = {"pending", "approved", "rejected", "cancelled"}
DECISION_STATUSES = {"approved", "rejected", "cancelled"}


def list_approval_requests(db: Session, principal: Principal) -> list[ApprovalRequestRead]:
    requests = db.scalars(
        select(ApprovalRequest)
        .where(ApprovalRequest.organization_id == principal.organization_id)
        .order_by(ApprovalRequest.created_at.desc())
        .limit(100)
    ).all()
    return [approval_to_read(request) for request in requests]


def decide_approval_request(
    db: Session,
    principal: Principal,
    approval_id: UUID,
    payload: ApprovalDecision,
) -> ApprovalRequestRead | None:
    if payload.status not in DECISION_STATUSES:
        raise ValueError(f"Unsupported approval decision: {payload.status}")
    request = db.scalar(
        select(ApprovalRequest).where(
            ApprovalRequest.organization_id == principal.organization_id,
            ApprovalRequest.id == approval_id,
        )
    )
    if request is None:
        return None
    if request.status != "pending":
        raise ValueError("This approval request has already been decided.")
    if request.request_type == "call_notes_review":
        raise ValueError("Call notes must be reviewed with the recording in the shared inbox.")
    offer_context = None
    concession_context = None
    contract_context = None
    if request.request_type == "offer_ceiling":
        offer_context = validate_offer_decision(db, principal, request, payload)
    elif request.request_type == "offer_concession":
        concession_context = validate_concession_decision(db, principal, request, payload)
    elif request.request_type == "contract_send":
        if PermissionKeys.SEND_CONTRACTS not in principal.permission_keys:
            raise ValueError("Your role cannot approve contract packages for sending.")
        from app.services.transactions import apply_contract_decision

        contract_context = apply_contract_decision(db, principal, request, payload)
    previous_status = request.status
    request.status = payload.status
    request.decision_notes = payload.decision_notes
    request.decided_by_user_id = principal.user_id
    request.decided_at = datetime.now(UTC)
    if offer_context is not None:
        plan, version, lead = offer_context
        plan.status = payload.status
        if payload.status == "approved":
            version.status = "approved"
            lead.stage_key = "offer_ready"
            supersede_prior_offer_authority(db, principal, plan)
        else:
            version.status = "needs_review"
            lead.stage_key = "underwriting"
        db.add(
            ActivityEvent(
                organization_id=principal.organization_id,
                actor_user_id=principal.user_id,
                entity_type="lead",
                entity_id=lead.id,
                event_type=f"underwriting.offer_approval_{payload.status}",
                summary=(
                    f"Offer ceiling ${plan.seller_ceiling_cents / 100:,.0f} "
                    f"{payload.status} for underwriting version {version.version_number}."
                ),
            )
        )
        db.add(
            AuditEvent(
                organization_id=principal.organization_id,
                actor_user_id=principal.user_id,
                actor_type="user",
                action="underwriting.offer_approval.decide",
                entity_type="offer_negotiation_plan",
                entity_id=plan.id,
                previous_value={"status": previous_status},
                new_value={
                    "status": payload.status,
                    "decision_notes": payload.decision_notes,
                    "underwriting_version_id": str(version.id),
                    "lead_stage": lead.stage_key,
                },
                reason="Human seller-offer ceiling decision",
            )
        )
    if concession_context is not None:
        concession, plan, lead = concession_context
        apply_concession_decision(concession, principal, payload)
        db.add(
            ActivityEvent(
                organization_id=principal.organization_id,
                actor_user_id=principal.user_id,
                entity_type="lead",
                entity_id=lead.id,
                event_type=f"underwriting.concession_{payload.status}",
                summary=(
                    f"Concession to ${concession.proposed_offer_cents / 100:,.0f} "
                    f"was {payload.status}."
                ),
            )
        )
        db.add(
            AuditEvent(
                organization_id=principal.organization_id,
                actor_user_id=principal.user_id,
                actor_type="user",
                action="underwriting.concession.decide",
                entity_type="offer_concession",
                entity_id=concession.id,
                previous_value={"status": previous_status},
                new_value={
                    "status": concession.status,
                    "decision_notes": concession.decision_notes,
                    "offer_negotiation_plan_id": str(plan.id),
                    "proposed_offer_cents": concession.proposed_offer_cents,
                    "seller_ceiling_cents": plan.seller_ceiling_cents,
                },
                reason="Human seller-concession decision",
            )
        )
    if contract_context is not None:
        package, transaction = contract_context
        db.add(
            AuditEvent(
                organization_id=principal.organization_id,
                actor_user_id=principal.user_id,
                actor_type="user",
                action="contract.approval.decide",
                entity_type="contract_package",
                entity_id=package.id,
                previous_value={"status": "pending_approval"},
                new_value={"status": package.status, "transaction_id": str(transaction.id)},
                reason="Human contract package decision",
            )
        )
    db.add(
        ActivityEvent(
            organization_id=principal.organization_id,
            actor_user_id=principal.user_id,
            entity_type="approval_request",
            entity_id=request.id,
            event_type="approval.decided",
            summary=f"Approval request {payload.status}: {request.title}.",
        )
    )
    db.add(
        AuditEvent(
            organization_id=principal.organization_id,
            actor_user_id=principal.user_id,
            actor_type="user",
            action="approval.decide",
            entity_type="approval_request",
            entity_id=request.id,
            previous_value={"status": previous_status},
            new_value={"status": request.status, "decision_notes": request.decision_notes},
            reason="Manual approval decision",
        )
    )
    db.commit()
    db.refresh(request)
    return approval_to_read(request)


def approval_to_read(request: ApprovalRequest) -> ApprovalRequestRead:
    metadata = request.approval_metadata or {}
    if request.request_type == "call_notes_review":
        review_url = "/os/inbox"
    elif request.request_type == "offer_ceiling" and metadata.get("lead_id"):
        review_url = f"/os/leads/{metadata['lead_id']}?tab=underwriting#offer-approval"
    elif request.request_type == "offer_concession" and metadata.get("lead_id"):
        review_url = f"/os/leads/{metadata['lead_id']}?tab=underwriting#negotiation-governance"
    elif request.request_type == "contract_send" and metadata.get("transaction_id"):
        review_url = f"/os/transactions?transaction={metadata['transaction_id']}"
    else:
        review_url = None
    return ApprovalRequestRead(
        id=request.id,
        request_type=request.request_type,
        entity_type=request.entity_type,
        entity_id=request.entity_id,
        status=request.status,
        title=request.title,
        summary=request.summary,
        decision_notes=request.decision_notes,
        decided_by_user_id=request.decided_by_user_id,
        due_at=request.due_at,
        decided_at=request.decided_at,
        created_at=request.created_at,
        review_url=review_url,
        approval_metadata=metadata,
    )


def validate_offer_decision(
    db: Session,
    principal: Principal,
    request: ApprovalRequest,
    payload: ApprovalDecision,
) -> tuple[OfferNegotiationPlan, UnderwritingVersion, Lead]:
    if PermissionKeys.APPROVE_OFFERS not in principal.permission_keys:
        raise ValueError("Your role cannot approve seller offer ceilings.")
    if payload.status in {"rejected", "cancelled"} and not (
        payload.decision_notes and payload.decision_notes.strip()
    ):
        raise ValueError("Decision notes are required when rejecting or cancelling an offer plan.")
    plan = db.scalar(
        select(OfferNegotiationPlan).where(
            OfferNegotiationPlan.organization_id == principal.organization_id,
            OfferNegotiationPlan.id == request.entity_id,
        )
    )
    if plan is None or plan.status != "pending":
        raise ValueError("The negotiation plan is no longer pending.")
    version = db.get(UnderwritingVersion, plan.underwriting_version_id)
    lead = db.get(Lead, plan.lead_id)
    if version is None or lead is None:
        raise ValueError("The source underwriting record is no longer available.")
    latest_version = db.scalar(
        select(func.max(UnderwritingVersion.version_number)).where(
            UnderwritingVersion.organization_id == principal.organization_id,
            UnderwritingVersion.lead_id == lead.id,
        )
    )
    if version.version_number != latest_version:
        raise ValueError(
            "A newer underwriting version exists. Submit a new offer plan before approval."
        )
    return plan, version, lead
