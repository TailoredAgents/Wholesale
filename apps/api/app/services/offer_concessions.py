from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.auth import Principal
from app.domain.rbac import PermissionKeys
from app.models.foundation import (
    ActivityEvent,
    Appointment,
    ApprovalRequest,
    AuditEvent,
    Contact,
    Lead,
    OfferConcession,
    OfferNegotiationEvent,
    OfferNegotiationPlan,
    UnderwritingVersion,
    User,
)
from app.schemas.approvals import (
    ApprovalDecision,
    OfferConcessionCreate,
    OfferConcessionPresent,
    OfferConcessionRead,
    OfferNegotiationEventCreate,
    OfferNegotiationEventRead,
    OfferNegotiationLedgerRead,
)
from app.services.offer_approvals import find_offer_approver_id, offer_plan_to_read


def get_negotiation_ledger(
    db: Session, principal: Principal, lead_id: UUID
) -> OfferNegotiationLedgerRead | None:
    lead = scoped_lead(db, principal, lead_id)
    if lead is None:
        return None
    plan = latest_approved_plan(db, principal.organization_id, lead.id)
    concessions = list(
        db.scalars(
            select(OfferConcession)
            .where(
                OfferConcession.organization_id == principal.organization_id,
                OfferConcession.lead_id == lead.id,
            )
            .order_by(OfferConcession.created_at.desc(), OfferConcession.id.desc())
        )
    )
    events = list(
        db.scalars(
            select(OfferNegotiationEvent)
            .where(
                OfferNegotiationEvent.organization_id == principal.organization_id,
                OfferNegotiationEvent.lead_id == lead.id,
            )
            .order_by(
                OfferNegotiationEvent.occurred_at.desc(),
                OfferNegotiationEvent.created_at.desc(),
            )
            .limit(200)
        )
    )
    return OfferNegotiationLedgerRead(
        active_plan=offer_plan_to_read(db, plan) if plan else None,
        concessions=[concession_read(db, item) for item in concessions],
        events=[event_read(db, item) for item in events],
        can_approve=PermissionKeys.APPROVE_OFFERS in principal.permission_keys,
    )


def create_concession(
    db: Session,
    principal: Principal,
    lead_id: UUID,
    payload: OfferConcessionCreate,
) -> OfferConcessionRead | None:
    lead = scoped_lead(db, principal, lead_id)
    if lead is None:
        return None
    plan = approved_current_plan(
        db, principal.organization_id, lead, payload.offer_negotiation_plan_id
    )
    db.execute(
        select(OfferNegotiationPlan.id)
        .where(OfferNegotiationPlan.id == plan.id)
        .with_for_update()
    )
    validate_appointment(db, principal, lead, payload.appointment_id)
    expected_previous = latest_presented_amount(db, plan) or plan.opening_offer_cents
    if payload.previous_offer_cents != expected_previous:
        raise ValueError(
            f"The last governed Stonegate offer is ${expected_previous / 100:,.0f}. "
            "Refresh the negotiation ledger before requesting another concession."
        )
    if payload.proposed_offer_cents > plan.seller_ceiling_cents:
        raise ValueError(
            "The proposed concession exceeds the approved seller ceiling. "
            "Create new underwriting and request a new offer plan."
        )
    duplicate = db.scalar(
        select(OfferConcession.id).where(
            OfferConcession.offer_negotiation_plan_id == plan.id,
            OfferConcession.proposed_offer_cents == payload.proposed_offer_cents,
            OfferConcession.status.in_(("pending", "authorized", "approved")),
        )
    )
    if duplicate is not None:
        raise ValueError("This concession amount is already pending or authorized.")

    authority_basis, concession_status = authority_for(plan, payload.proposed_offer_cents)
    sequence = (
        int(
            db.scalar(
                select(func.max(OfferConcession.sequence_number)).where(
                    OfferConcession.offer_negotiation_plan_id == plan.id
                )
            )
            or 0
        )
        + 1
    )
    source_snapshot = {
        "offer_negotiation_plan_id": str(plan.id),
        "underwriting_version_id": str(plan.underwriting_version_id),
        "opening_offer_cents": plan.opening_offer_cents,
        "target_contract_cents": plan.target_contract_cents,
        "stretch_contract_cents": plan.stretch_contract_cents,
        "seller_ceiling_cents": plan.seller_ceiling_cents,
        "plan_status": plan.status,
        "previous_offer_cents": payload.previous_offer_cents,
        "seller_counter_cents": payload.seller_counter_cents,
    }
    concession = OfferConcession(
        organization_id=principal.organization_id,
        lead_id=lead.id,
        property_id=lead.property_id,
        offer_negotiation_plan_id=plan.id,
        underwriting_version_id=plan.underwriting_version_id,
        appointment_id=payload.appointment_id,
        requested_by_user_id=principal.user_id,
        approval_request_id=None,
        decided_by_user_id=None,
        presented_by_user_id=None,
        sequence_number=sequence,
        status=concession_status,
        authority_basis=authority_basis,
        previous_offer_cents=payload.previous_offer_cents,
        proposed_offer_cents=payload.proposed_offer_cents,
        concession_delta_cents=payload.proposed_offer_cents - payload.previous_offer_cents,
        seller_counter_cents=payload.seller_counter_cents,
        reason=payload.reason.strip(),
        seller_exchange=payload.seller_exchange.strip(),
        decision_notes=(
            "Authorized within the approved negotiation ladder."
            if concession_status == "authorized"
            else None
        ),
        decided_at=datetime.now(UTC) if concession_status == "authorized" else None,
        presented_at=None,
        source_snapshot=source_snapshot,
    )
    if concession_status == "authorized":
        concession.decided_by_user_id = principal.user_id
    db.add(concession)
    db.flush()

    if concession_status == "pending":
        contact = db.get(Contact, lead.contact_id)
        seller_name = contact.preferred_name or contact.legal_name if contact else "Seller"
        approval = ApprovalRequest(
            organization_id=principal.organization_id,
            requested_by_user_id=principal.user_id,
            assigned_to_user_id=find_offer_approver_id(db, principal),
            decided_by_user_id=None,
            request_type="offer_concession",
            entity_type="offer_concession",
            entity_id=concession.id,
            status="pending",
            title=f"Approve seller concession for {seller_name}",
            summary=(
                f"Increase Stonegate's offer from "
                f"${payload.previous_offer_cents / 100:,.0f} to "
                f"${payload.proposed_offer_cents / 100:,.0f}; approved ceiling "
                f"${plan.seller_ceiling_cents / 100:,.0f}."
            ),
            decision_notes=None,
            due_at=None,
            decided_at=None,
            approval_metadata={
                "lead_id": str(lead.id),
                "offer_negotiation_plan_id": str(plan.id),
                "offer_concession_id": str(concession.id),
                "previous_offer_cents": payload.previous_offer_cents,
                "proposed_offer_cents": payload.proposed_offer_cents,
                "concession_delta_cents": concession.concession_delta_cents,
                "stretch_contract_cents": plan.stretch_contract_cents,
                "seller_ceiling_cents": plan.seller_ceiling_cents,
                "seller_exchange": concession.seller_exchange,
            },
        )
        db.add(approval)
        db.flush()
        concession.approval_request_id = approval.id

    add_event(
        db,
        principal,
        lead,
        plan,
        event_type="concession_requested",
        channel="internal",
        notes=concession.reason,
        previous_offer_cents=concession.previous_offer_cents,
        amount_cents=concession.proposed_offer_cents,
        seller_counter_cents=concession.seller_counter_cents,
        seller_response=concession.seller_exchange,
        objections=[],
        appointment_id=concession.appointment_id,
        concession_id=concession.id,
        metadata={
            "status": concession.status,
            "authority_basis": concession.authority_basis,
            "sequence_number": concession.sequence_number,
        },
    )
    add_activity(
        db,
        principal,
        lead.id,
        "underwriting.concession_requested",
        (
            f"Concession #{sequence} to ${concession.proposed_offer_cents / 100:,.0f} "
            f"was {concession.status}."
        ),
    )
    add_audit(
        db,
        principal,
        "underwriting.concession.request",
        "offer_concession",
        concession.id,
        {
            **source_snapshot,
            "status": concession.status,
            "authority_basis": concession.authority_basis,
            "proposed_offer_cents": concession.proposed_offer_cents,
            "reason": concession.reason,
            "seller_exchange": concession.seller_exchange,
        },
        "Seller concession recorded against approved offer authority",
    )
    db.commit()
    return concession_read(db, concession)


def present_concession(
    db: Session,
    principal: Principal,
    lead_id: UUID,
    concession_id: UUID,
    payload: OfferConcessionPresent,
) -> OfferConcessionRead | None:
    lead = scoped_lead(db, principal, lead_id)
    if lead is None:
        return None
    concession = db.scalar(
        select(OfferConcession).where(
            OfferConcession.id == concession_id,
            OfferConcession.organization_id == principal.organization_id,
            OfferConcession.lead_id == lead.id,
        )
    )
    if concession is None:
        return None
    plan = approved_current_plan(
        db, principal.organization_id, lead, concession.offer_negotiation_plan_id
    )
    if concession.status not in {"authorized", "approved"}:
        raise ValueError("Only an authorized or approved concession can be presented.")
    if concession.presented_at is not None:
        raise ValueError("This concession has already been recorded as presented.")
    concession.status = "presented"
    concession.presented_by_user_id = principal.user_id
    concession.presented_at = as_utc(payload.occurred_at or datetime.now(UTC))
    add_event(
        db,
        principal,
        lead,
        plan,
        event_type="concession_presented",
        channel=payload.channel,
        notes=payload.notes.strip(),
        previous_offer_cents=concession.previous_offer_cents,
        amount_cents=concession.proposed_offer_cents,
        seller_counter_cents=concession.seller_counter_cents,
        seller_response=clean_optional(payload.seller_response),
        objections=[],
        appointment_id=concession.appointment_id,
        concession_id=concession.id,
        metadata={"authority_basis": concession.authority_basis},
        occurred_at=concession.presented_at,
    )
    add_activity(
        db,
        principal,
        lead.id,
        "underwriting.concession_presented",
        f"Authorized concession presented at ${concession.proposed_offer_cents / 100:,.0f}.",
    )
    add_audit(
        db,
        principal,
        "underwriting.concession.present",
        "offer_concession",
        concession.id,
        {
            "status": concession.status,
            "presented_at": concession.presented_at.isoformat(),
            "presented_by_user_id": str(principal.user_id),
            "channel": payload.channel,
        },
        "Authorized concession presented to seller",
    )
    db.commit()
    return concession_read(db, concession)


def create_negotiation_event(
    db: Session,
    principal: Principal,
    lead_id: UUID,
    payload: OfferNegotiationEventCreate,
) -> OfferNegotiationEventRead | None:
    lead = scoped_lead(db, principal, lead_id)
    if lead is None:
        return None
    plan = approved_current_plan(
        db, principal.organization_id, lead, payload.offer_negotiation_plan_id
    )
    validate_appointment(db, principal, lead, payload.appointment_id)
    concession: OfferConcession | None = None
    governed_amount = payload.amount_cents
    if governed_amount is not None:
        concession = authority_for_amount(db, plan, governed_amount)
    if payload.event_type == "agreement":
        presented_amount = latest_presented_amount(db, plan)
        if governed_amount != presented_amount:
            raise ValueError(
                "The agreed amount must match the most recently presented governed offer."
            )
    event = add_event(
        db,
        principal,
        lead,
        plan,
        event_type=payload.event_type,
        channel=payload.channel,
        notes=payload.notes.strip(),
        previous_offer_cents=payload.previous_offer_cents,
        amount_cents=payload.amount_cents,
        seller_counter_cents=payload.seller_counter_cents,
        seller_response=clean_optional(payload.seller_response),
        objections=[{"details": item} for item in payload.objections],
        appointment_id=payload.appointment_id,
        concession_id=concession.id if concession else None,
        metadata={"source": "manual_negotiation_ledger"},
        occurred_at=as_utc(payload.occurred_at or datetime.now(UTC)),
    )
    add_activity(
        db,
        principal,
        lead.id,
        f"underwriting.negotiation_{payload.event_type}",
        f"Negotiation event recorded: {payload.event_type.replace('_', ' ')}.",
    )
    add_audit(
        db,
        principal,
        "underwriting.negotiation_event.create",
        "offer_negotiation_event",
        event.id,
        {
            "event_type": event.event_type,
            "channel": event.channel,
            "amount_cents": event.amount_cents,
            "seller_counter_cents": event.seller_counter_cents,
            "concession_id": str(event.concession_id) if event.concession_id else None,
        },
        "Append-only seller negotiation event recorded",
    )
    db.commit()
    return event_read(db, event)


def validate_concession_decision(
    db: Session,
    principal: Principal,
    request: ApprovalRequest,
    payload: ApprovalDecision,
) -> tuple[OfferConcession, OfferNegotiationPlan, Lead]:
    if PermissionKeys.APPROVE_OFFERS not in principal.permission_keys:
        raise ValueError("Your role cannot approve seller concessions.")
    if payload.status in {"rejected", "cancelled"} and not clean_optional(payload.decision_notes):
        raise ValueError("Decision notes are required when rejecting a concession.")
    concession = db.scalar(
        select(OfferConcession).where(
            OfferConcession.organization_id == principal.organization_id,
            OfferConcession.id == request.entity_id,
        )
    )
    if concession is None or concession.status != "pending":
        raise ValueError("The concession is no longer pending.")
    lead = db.get(Lead, concession.lead_id)
    if lead is None:
        raise ValueError("The concession lead is no longer available.")
    plan = approved_current_plan(
        db, principal.organization_id, lead, concession.offer_negotiation_plan_id
    )
    if concession.proposed_offer_cents > plan.seller_ceiling_cents:
        raise ValueError("The concession exceeds the approved seller ceiling.")
    return concession, plan, lead


def apply_concession_decision(
    concession: OfferConcession, principal: Principal, payload: ApprovalDecision
) -> None:
    concession.status = payload.status
    concession.decided_by_user_id = principal.user_id
    concession.decision_notes = clean_optional(payload.decision_notes)
    concession.decided_at = datetime.now(UTC)


def supersede_prior_offer_authority(
    db: Session,
    principal: Principal,
    approved_plan: OfferNegotiationPlan,
) -> None:
    prior_plans = list(
        db.scalars(
            select(OfferNegotiationPlan).where(
                OfferNegotiationPlan.organization_id == principal.organization_id,
                OfferNegotiationPlan.lead_id == approved_plan.lead_id,
                OfferNegotiationPlan.id != approved_plan.id,
                OfferNegotiationPlan.status == "approved",
            )
        )
    )
    if not prior_plans:
        return
    prior_plan_ids = [plan.id for plan in prior_plans]
    for plan in prior_plans:
        plan.status = "superseded"
    concessions = list(
        db.scalars(
            select(OfferConcession).where(
                OfferConcession.offer_negotiation_plan_id.in_(prior_plan_ids),
                OfferConcession.status.in_(("pending", "authorized", "approved")),
            )
        )
    )
    approval_ids: list[UUID] = []
    for concession in concessions:
        concession.status = "cancelled"
        concession.decision_notes = "Cancelled when a newer offer plan became active."
        concession.decided_at = datetime.now(UTC)
        concession.decided_by_user_id = principal.user_id
        if concession.approval_request_id:
            approval_ids.append(concession.approval_request_id)
    if approval_ids:
        pending_approvals = list(
            db.scalars(
                select(ApprovalRequest).where(
                    ApprovalRequest.id.in_(approval_ids),
                    ApprovalRequest.status == "pending",
                )
            )
        )
        for request in pending_approvals:
            request.status = "cancelled"
            request.decision_notes = "Superseded by a newly approved offer plan."
            request.decided_by_user_id = principal.user_id
            request.decided_at = datetime.now(UTC)
    add_audit(
        db,
        principal,
        "underwriting.offer_authority.supersede",
        "offer_negotiation_plan",
        approved_plan.id,
        {
            "superseded_plan_ids": [str(plan_id) for plan_id in prior_plan_ids],
            "cancelled_concession_ids": [str(item.id) for item in concessions],
        },
        "New offer plan replaced prior unused negotiation authority",
    )


def authority_for_amount(
    db: Session, plan: OfferNegotiationPlan, amount_cents: int
) -> OfferConcession | None:
    if amount_cents > plan.seller_ceiling_cents:
        raise ValueError("The amount exceeds the approved seller ceiling.")
    if amount_cents <= plan.opening_offer_cents:
        return None
    concession = db.scalar(
        select(OfferConcession)
        .where(
            OfferConcession.offer_negotiation_plan_id == plan.id,
            OfferConcession.proposed_offer_cents == amount_cents,
            OfferConcession.status == "presented",
        )
        .order_by(OfferConcession.presented_at.desc())
    )
    if concession is None:
        raise ValueError(
            "This amount is above the approved opening offer and has not been recorded as an "
            "authorized concession."
        )
    return concession


def record_field_offer(
    db: Session,
    principal: Principal,
    lead_id: UUID,
    appointment_id: UUID,
    amount_cents: int,
    *,
    seller_counter_cents: int | None,
    notes: str,
) -> tuple[OfferNegotiationPlan, OfferConcession | None]:
    lead = scoped_lead(db, principal, lead_id)
    if lead is None:
        raise ValueError("The lead is no longer available.")
    plan = latest_approved_plan(db, principal.organization_id, lead.id)
    if plan is None:
        raise ValueError("An approved offer plan is required before presenting a price.")
    concession = authority_for_field_offer(db, plan, amount_cents)
    duplicate = db.scalar(
        select(OfferNegotiationEvent.id).where(
            OfferNegotiationEvent.offer_negotiation_plan_id == plan.id,
            OfferNegotiationEvent.appointment_id == appointment_id,
            OfferNegotiationEvent.event_type == "field_offer_presented",
            OfferNegotiationEvent.amount_cents == amount_cents,
        )
    )
    if duplicate is None:
        if concession is not None and concession.status in {"authorized", "approved"}:
            concession.status = "presented"
            concession.presented_by_user_id = principal.user_id
            concession.presented_at = datetime.now(UTC)
        add_event(
            db,
            principal,
            lead,
            plan,
            event_type="field_offer_presented",
            channel="in_person",
            notes=notes,
            previous_offer_cents=latest_presented_amount(db, plan),
            amount_cents=amount_cents,
            seller_counter_cents=seller_counter_cents,
            seller_response=None,
            objections=[],
            appointment_id=appointment_id,
            concession_id=concession.id if concession else None,
            metadata={"source": "field_negotiation"},
        )
    return plan, concession


def record_field_agreement(
    db: Session,
    principal: Principal,
    lead_id: UUID,
    appointment_id: UUID,
    amount_cents: int,
    notes: str,
) -> OfferConcession | None:
    lead = scoped_lead(db, principal, lead_id)
    if lead is None:
        raise ValueError("The lead is no longer available.")
    plan = latest_approved_plan(db, principal.organization_id, lead.id)
    if plan is None:
        raise ValueError("An approved offer plan is required before recording an agreement.")
    concession = authority_for_amount(db, plan, amount_cents)
    duplicate = db.scalar(
        select(OfferNegotiationEvent.id).where(
            OfferNegotiationEvent.offer_negotiation_plan_id == plan.id,
            OfferNegotiationEvent.appointment_id == appointment_id,
            OfferNegotiationEvent.event_type == "agreement",
            OfferNegotiationEvent.amount_cents == amount_cents,
        )
    )
    if duplicate is None:
        add_event(
            db,
            principal,
            lead,
            plan,
            event_type="agreement",
            channel="in_person",
            notes=notes,
            previous_offer_cents=latest_presented_amount(db, plan),
            amount_cents=amount_cents,
            seller_counter_cents=None,
            seller_response="Seller accepted the governed amount.",
            objections=[],
            appointment_id=appointment_id,
            concession_id=concession.id if concession else None,
            metadata={"source": "field_negotiation"},
        )
    return concession


def authority_for_field_offer(
    db: Session, plan: OfferNegotiationPlan, amount_cents: int
) -> OfferConcession | None:
    if amount_cents > plan.seller_ceiling_cents:
        raise ValueError("The amount exceeds the approved seller ceiling.")
    if amount_cents <= plan.opening_offer_cents:
        return None
    concession = db.scalar(
        select(OfferConcession)
        .where(
            OfferConcession.offer_negotiation_plan_id == plan.id,
            OfferConcession.proposed_offer_cents == amount_cents,
            OfferConcession.status.in_(("authorized", "approved", "presented")),
        )
        .order_by(OfferConcession.created_at.desc())
    )
    if concession is None:
        raise ValueError(
            "Record the concession reason and obtain any required approval before presenting "
            "this amount."
        )
    return concession


def approved_current_plan(
    db: Session,
    organization_id: UUID,
    lead: Lead,
    plan_id: UUID,
) -> OfferNegotiationPlan:
    plan = db.scalar(
        select(OfferNegotiationPlan).where(
            OfferNegotiationPlan.id == plan_id,
            OfferNegotiationPlan.organization_id == organization_id,
            OfferNegotiationPlan.lead_id == lead.id,
            OfferNegotiationPlan.status == "approved",
        )
    )
    if plan is None:
        raise ValueError("Select the current approved offer plan.")
    approval = (
        db.get(ApprovalRequest, plan.approval_request_id) if plan.approval_request_id else None
    )
    if approval is None or approval.status != "approved":
        raise ValueError("The offer plan does not have an approved decision.")
    latest_version = db.scalar(
        select(func.max(UnderwritingVersion.version_number)).where(
            UnderwritingVersion.organization_id == organization_id,
            UnderwritingVersion.lead_id == lead.id,
        )
    )
    version = db.get(UnderwritingVersion, plan.underwriting_version_id)
    if version is None or version.version_number != latest_version:
        raise ValueError(
            "A newer underwriting version exists. Approve a new offer plan before negotiating."
        )
    return plan


def latest_approved_plan(
    db: Session, organization_id: UUID, lead_id: UUID
) -> OfferNegotiationPlan | None:
    plans = list(
        db.scalars(
            select(OfferNegotiationPlan)
            .where(
                OfferNegotiationPlan.organization_id == organization_id,
                OfferNegotiationPlan.lead_id == lead_id,
                OfferNegotiationPlan.status == "approved",
            )
            .order_by(OfferNegotiationPlan.created_at.desc())
        )
    )
    lead = db.get(Lead, lead_id)
    if lead is None:
        return None
    for plan in plans:
        try:
            return approved_current_plan(db, organization_id, lead, plan.id)
        except ValueError:
            continue
    return None


def latest_presented_amount(db: Session, plan: OfferNegotiationPlan) -> int | None:
    return db.scalar(
        select(OfferNegotiationEvent.amount_cents)
        .where(
            OfferNegotiationEvent.offer_negotiation_plan_id == plan.id,
            OfferNegotiationEvent.amount_cents.is_not(None),
            OfferNegotiationEvent.event_type.in_(
                ("concession_presented", "field_offer_presented", "price_discussion", "agreement")
            ),
        )
        .order_by(OfferNegotiationEvent.occurred_at.desc(), OfferNegotiationEvent.created_at.desc())
        .limit(1)
    )


def authority_for(plan: OfferNegotiationPlan, proposed: int) -> tuple[str, str]:
    if proposed <= plan.target_contract_cents:
        return "approved_target", "authorized"
    if proposed <= plan.stretch_contract_cents:
        return "approved_stretch", "authorized"
    return "manager_exception", "pending"


def validate_appointment(
    db: Session, principal: Principal, lead: Lead, appointment_id: UUID | None
) -> None:
    if appointment_id is None:
        return
    appointment = db.scalar(
        select(Appointment.id).where(
            Appointment.id == appointment_id,
            Appointment.organization_id == principal.organization_id,
            Appointment.lead_id == lead.id,
        )
    )
    if appointment is None:
        raise ValueError("The selected appointment does not belong to this lead.")


def scoped_lead(db: Session, principal: Principal, lead_id: UUID) -> Lead | None:
    return db.scalar(
        select(Lead).where(
            Lead.id == lead_id,
            Lead.organization_id == principal.organization_id,
        )
    )


def add_event(
    db: Session,
    principal: Principal,
    lead: Lead,
    plan: OfferNegotiationPlan,
    *,
    event_type: str,
    channel: str,
    notes: str,
    previous_offer_cents: int | None,
    amount_cents: int | None,
    seller_counter_cents: int | None,
    seller_response: str | None,
    objections: list[dict[str, object]],
    appointment_id: UUID | None,
    concession_id: UUID | None,
    metadata: dict[str, object],
    occurred_at: datetime | None = None,
) -> OfferNegotiationEvent:
    event = OfferNegotiationEvent(
        organization_id=principal.organization_id,
        lead_id=lead.id,
        property_id=lead.property_id,
        offer_negotiation_plan_id=plan.id,
        concession_id=concession_id,
        appointment_id=appointment_id,
        actor_user_id=principal.user_id,
        event_type=event_type,
        channel=channel,
        previous_offer_cents=previous_offer_cents,
        amount_cents=amount_cents,
        seller_counter_cents=seller_counter_cents,
        notes=notes,
        seller_response=seller_response,
        objections=objections,
        occurred_at=occurred_at or datetime.now(UTC),
        event_metadata=metadata,
    )
    db.add(event)
    db.flush()
    return event


def concession_read(db: Session, concession: OfferConcession) -> OfferConcessionRead:
    requester = db.get(User, concession.requested_by_user_id)
    return OfferConcessionRead(
        id=concession.id,
        lead_id=concession.lead_id,
        offer_negotiation_plan_id=concession.offer_negotiation_plan_id,
        underwriting_version_id=concession.underwriting_version_id,
        appointment_id=concession.appointment_id,
        approval_request_id=concession.approval_request_id,
        sequence_number=concession.sequence_number,
        status=concession.status,
        authority_basis=concession.authority_basis,
        previous_offer_cents=concession.previous_offer_cents,
        proposed_offer_cents=concession.proposed_offer_cents,
        concession_delta_cents=concession.concession_delta_cents,
        seller_counter_cents=concession.seller_counter_cents,
        reason=concession.reason,
        seller_exchange=concession.seller_exchange,
        decision_notes=concession.decision_notes,
        requested_by_user_id=concession.requested_by_user_id,
        requested_by_name=requester.display_name if requester else "Unknown user",
        decided_by_user_id=concession.decided_by_user_id,
        presented_by_user_id=concession.presented_by_user_id,
        decided_at=concession.decided_at,
        presented_at=concession.presented_at,
        source_snapshot=concession.source_snapshot,
        created_at=concession.created_at,
    )


def event_read(db: Session, event: OfferNegotiationEvent) -> OfferNegotiationEventRead:
    actor = db.get(User, event.actor_user_id)
    return OfferNegotiationEventRead(
        id=event.id,
        offer_negotiation_plan_id=event.offer_negotiation_plan_id,
        concession_id=event.concession_id,
        appointment_id=event.appointment_id,
        actor_user_id=event.actor_user_id,
        actor_name=actor.display_name if actor else "Unknown user",
        event_type=event.event_type,
        channel=event.channel,
        previous_offer_cents=event.previous_offer_cents,
        amount_cents=event.amount_cents,
        seller_counter_cents=event.seller_counter_cents,
        notes=event.notes,
        seller_response=event.seller_response,
        objections=[str(item.get("details", "")) for item in event.objections],
        occurred_at=event.occurred_at,
        created_at=event.created_at,
    )


def add_activity(
    db: Session, principal: Principal, lead_id: UUID, event_type: str, summary: str
) -> None:
    db.add(
        ActivityEvent(
            organization_id=principal.organization_id,
            actor_user_id=principal.user_id,
            entity_type="lead",
            entity_id=lead_id,
            event_type=event_type,
            summary=summary,
        )
    )


def add_audit(
    db: Session,
    principal: Principal,
    action: str,
    entity_type: str,
    entity_id: UUID,
    new_value: dict[str, object],
    reason: str,
) -> None:
    db.add(
        AuditEvent(
            organization_id=principal.organization_id,
            actor_user_id=principal.user_id,
            actor_type="user",
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            previous_value=None,
            new_value=new_value,
            reason=reason,
        )
    )


def clean_optional(value: str | None) -> str | None:
    cleaned = (value or "").strip()
    return cleaned or None


def as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)
