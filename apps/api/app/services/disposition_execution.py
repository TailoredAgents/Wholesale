from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from typing import Any, cast
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.auth import Principal
from app.models.foundation import (
    ActivityEvent,
    AuditEvent,
    Buyer,
    BuyerEngagement,
    Contact,
    Conversation,
    ConversationContextLink,
    DispositionBuyerPoolCandidate,
    DispositionCase,
    Lead,
    Property,
    Task,
    User,
)
from app.schemas.disposition_execution import (
    DispositionExecutionCallCreate,
    DispositionExecutionCandidateRead,
    DispositionExecutionOutcomeCreate,
    DispositionExecutionPermissionRead,
    DispositionExecutionSmsCreate,
    DispositionExecutionWorkspaceRead,
    DispositionShowingCreate,
    DispositionShowingRead,
    DispositionShowingUpdate,
    ShowingAccessStatus,
    ShowingStatus,
)
from app.schemas.inbox import SmsSendRead, SmsSendRequest
from app.schemas.voice import VoiceCallIntentCreate, VoiceCallIntentRead
from app.services import buyers as buyer_service
from app.services import disposition_buyer_pool, disposition_packages, dispositions
from app.services.communication_compliance import (
    evaluate_sms_eligibility,
    evaluate_voice_eligibility,
)
from app.services.disposition_state import ACTIVE_DISPOSITION_CASE_STATUSES
from app.services.inbox import ensure_buyer_conversation
from app.services.messaging import send_conversation_sms
from app.services.voice import create_call_intent, start_forwarded_call

EXECUTION_CASE_STATUSES = set(ACTIVE_DISPOSITION_CASE_STATUSES)
CALL_OUTCOME_STAGE = {
    "interested": "interested",
    "showing_scheduled": "showing",
    "offer_expected": "offer",
    "callback": "contacted",
    "no_answer": "contacted",
    "voicemail": "contacted",
    "not_interested": "pass",
    "wrong_number": "pass",
    "do_not_contact": "pass",
}
TERMINAL_OUTCOMES = {"not_interested", "wrong_number", "do_not_contact"}
VALID_SHOWING_STATUSES = {"scheduled", "confirmed", "completed", "cancelled", "no_show"}
VALID_ACCESS_STATUSES = {
    "not_requested",
    "pending",
    "confirmed",
    "shared_privately",
    "not_required",
}
BUYER_DO_NOT_CONTACT_BLOCKER = "This buyer is marked do not contact."


def read_workspace(
    db: Session,
    principal: Principal,
    case_id: UUID,
) -> DispositionExecutionWorkspaceRead | None:
    case = dispositions.scoped_case(db, principal, case_id)
    if case is None:
        return None
    lead = db.get(Lead, case.lead_id)
    property_record = db.get(Property, case.property_id)
    if lead is None or property_record is None:
        raise ValueError("The disposition property is unavailable.")

    asset_class = (lead.asset_class or "house").strip().lower()
    blockers: list[str] = []
    if asset_class != "house":
        blockers.append("The dispositions call queue is currently available for house deals only.")
    if case.status not in EXECUTION_CASE_STATUSES:
        blockers.append("Move the deal into buyer placement before beginning buyer calls.")

    package = None
    try:
        package = disposition_packages.require_package_artifact(
            db,
            principal,
            case,
            action="opening the one-to-one buyer workbench",
        )
    except ValueError:
        # Package readiness is advisory. Calls may still proceed without an attachment.
        package = None
    package_is_current = bool(
        package is not None
        and disposition_packages.package_version_currentness(db, principal, case, package)
    )

    try:
        pool = disposition_buyer_pool.read_buyer_pool(
            db,
            principal,
            case.id,
            page=1,
            page_size=100,
            include_all=True,
        )
    except ValueError:
        # Ranking is optional context. A failed or unreadable run must never make
        # the canonical Buyer Network unavailable for one-to-one work.
        pool = None
    ranked_entries_by_buyer = {
        entry.buyer_id: entry
        for entry in (pool.entries if pool is not None else [])
        if entry.buyer_id is not None
    }
    buyers = list(
        db.scalars(
            select(Buyer).where(
                Buyer.organization_id == principal.organization_id,
                Buyer.archived_at.is_(None),
                Buyer.status != "archived",
            )
        ).all()
    )
    buyer_ids = {buyer.id for buyer in buyers}
    case_candidates = (
        list(
            db.scalars(
                select(DispositionBuyerPoolCandidate).where(
                    DispositionBuyerPoolCandidate.organization_id
                    == principal.organization_id,
                    DispositionBuyerPoolCandidate.disposition_case_id == case.id,
                    DispositionBuyerPoolCandidate.buyer_id.in_(buyer_ids),
                )
            ).all()
        )
        if buyer_ids
        else []
    )
    candidate_by_buyer = {
        candidate.buyer_id: candidate
        for candidate in case_candidates
        if candidate.buyer_id is not None
    }
    visible_buyers = list(buyers)
    visible_buyers.sort(
        key=lambda buyer: (
            0 if buyer.id in ranked_entries_by_buyer else 1,
            (
                ranked_entries_by_buyer[buyer.id].rank
                if buyer.id in ranked_entries_by_buyer
                else 0
            ),
            buyer.name.casefold(),
            str(buyer.id),
        )
    )
    handled_buyer_ids, deferred_buyer_ids = _candidate_queue_state(db, case)
    available_buyers = [
        buyer
        for buyer in visible_buyers
        if buyer.id not in handled_buyer_ids
        and buyer.id not in deferred_buyer_ids
        and not _candidate_is_passed(candidate_by_buyer.get(buyer.id))
        and not _buyer_is_do_not_contact(buyer)
        and (
            candidate_by_buyer.get(buyer.id) is None
            or candidate_by_buyer[buyer.id].lifecycle_stage
            not in {"selected", "backup", "fallout"}
        )
    ]
    candidates = (
        [
            _candidate_read(
                db,
                principal,
                property_record,
                buyer,
                candidate_by_buyer.get(buyer.id),
                ranked_entries_by_buyer.get(buyer.id),
            )
            for buyer in visible_buyers
        ]
        if asset_class == "house"
        else []
    )
    candidate_read_by_buyer = {item.buyer_id: item for item in candidates}
    current = (
        candidate_read_by_buyer.get(available_buyers[0].id)
        if asset_class == "house" and available_buyers
        else None
    )
    return DispositionExecutionWorkspaceRead(
        case_id=case.id,
        deal_id=case.deal_id,
        asset_class=asset_class,
        property_address=_property_address(property_record),
        package_status=package.status if package is not None else case.package_status,
        package_is_preliminary=bool(
            package is not None
            and (package.status != "approved" or not package_is_current)
        ),
        package_pdf_path=(
            f"/api/v1/dispositions/cases/{case.id}/package/versions/{package.id}/package.pdf"
            if package is not None
            else None
        ),
        ready=not blockers and bool(available_buyers),
        blockers=blockers,
        remaining_candidate_count=len(available_buyers),
        current_candidate=current,
        candidates=candidates,
        showings=_showing_reads(db, case),
    )


def send_pre_call_sms(
    db: Session,
    principal: Principal,
    case_id: UUID,
    payload: DispositionExecutionSmsCreate,
) -> SmsSendRead:
    case = _mutable_house_case(db, principal, case_id)
    referenced_buyer_id = _referenced_buyer_id(
        db,
        principal,
        case,
        candidate_id=payload.candidate_id,
        buyer_id=payload.buyer_id,
    )
    request_fingerprint = _request_fingerprint(
        payload,
        buyer_id=referenced_buyer_id,
    )
    existing = _engagement_by_idempotency(
        db,
        principal,
        case,
        payload.idempotency_key,
        request_fingerprint=request_fingerprint,
    )
    case, candidate, buyer = _candidate_for_action(
        db,
        principal,
        case_id,
        candidate_id=payload.candidate_id,
        buyer_id=payload.buyer_id,
    )
    conversation = ensure_buyer_conversation(db, buyer, actor_user_id=principal.user_id)
    db.commit()
    result = send_conversation_sms(
        db,
        principal,
        conversation.id,
        SmsSendRequest(body=payload.body, idempotency_key=payload.idempotency_key),
        require_permission=False,
    )
    if result is None:
        raise ValueError("The buyer conversation is unavailable.")
    if existing is not None:
        return result
    _log_engagement(
        db,
        principal,
        case,
        buyer,
        candidate,
        engagement_type="sms",
        status="sent",
        notes="One-to-one pre-call SMS sent from the disposition execution queue.",
        idempotency_key=payload.idempotency_key,
        metadata={
            "communication_id": str(result.communication_id),
            "request_fingerprint": request_fingerprint,
        },
    )
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        replay = _engagement_by_idempotency(
            db,
            principal,
            case,
            payload.idempotency_key,
            request_fingerprint=request_fingerprint,
        )
        if replay is None:
            raise
    return result


def start_candidate_call(
    db: Session,
    principal: Principal,
    case_id: UUID,
    payload: DispositionExecutionCallCreate,
) -> VoiceCallIntentRead:
    _, _, buyer = _candidate_for_action(
        db,
        principal,
        case_id,
        candidate_id=payload.candidate_id,
        buyer_id=payload.buyer_id,
    )
    conversation = ensure_buyer_conversation(db, buyer, actor_user_id=principal.user_id)
    result = create_call_intent(
        db,
        principal,
        conversation.id,
        VoiceCallIntentCreate(idempotency_key=payload.idempotency_key),
        intent_source="disposition_execution",
        require_browser_voice=True,
        require_recorded_permission=False,
    )
    if result is None:
        raise ValueError("The buyer conversation is unavailable.")
    return result


def start_candidate_forwarded_call(
    db: Session,
    principal: Principal,
    case_id: UUID,
    payload: DispositionExecutionCallCreate,
) -> VoiceCallIntentRead:
    """Start a disposition call through the staff member's configured cellphone.

    This deliberately remains separate from ``start_candidate_call`` so the browser
    SDK path may require browser-only Twilio credentials without disabling the
    cellphone bridge fallback.
    """

    _, _, buyer = _candidate_for_action(
        db,
        principal,
        case_id,
        candidate_id=payload.candidate_id,
        buyer_id=payload.buyer_id,
    )
    conversation = ensure_buyer_conversation(db, buyer, actor_user_id=principal.user_id)
    result = start_forwarded_call(
        db,
        principal,
        conversation.id,
        VoiceCallIntentCreate(idempotency_key=payload.idempotency_key),
        require_recorded_permission=False,
    )
    if result is None:
        raise ValueError("The buyer conversation is unavailable.")
    return result


def record_call_outcome(
    db: Session,
    principal: Principal,
    case_id: UUID,
    payload: DispositionExecutionOutcomeCreate,
) -> DispositionExecutionWorkspaceRead:
    case = _mutable_house_case(db, principal, case_id)
    referenced_buyer_id = _referenced_buyer_id(
        db,
        principal,
        case,
        candidate_id=payload.candidate_id,
        buyer_id=payload.buyer_id,
    )
    request_fingerprint = _request_fingerprint(
        payload,
        buyer_id=referenced_buyer_id,
    )
    existing = _engagement_by_idempotency(
        db,
        principal,
        case,
        payload.idempotency_key,
        request_fingerprint=request_fingerprint,
    )
    if existing is not None:
        result = read_workspace(db, principal, case.id)
        if result is None:
            raise ValueError("The disposition case is unavailable.")
        return result
    case, candidate, buyer = _candidate_for_action(
        db,
        principal,
        case_id,
        candidate_id=payload.candidate_id,
        buyer_id=payload.buyer_id,
    )
    now = datetime.now(UTC)
    if payload.outcome == "callback":
        _require_future_time(payload.follow_up_at, now=now, label="callback follow-up")
    _complete_prior_follow_up_task(db, principal, case, buyer, now=now)
    previous = {
        "decision_status": candidate.decision_status,
        "lifecycle_stage": candidate.lifecycle_stage,
        "lock_version": candidate.lock_version,
    }
    candidate.lifecycle_stage = CALL_OUTCOME_STAGE[payload.outcome]
    if payload.outcome in TERMINAL_OUTCOMES:
        candidate.decision_status = "passed"
        candidate.decision_reason = payload.notes or payload.outcome.replace("_", " ")
    elif payload.outcome in {"interested", "showing_scheduled", "offer_expected", "callback"}:
        candidate.decision_status = "shortlisted"
        candidate.decision_reason = payload.notes
    candidate.lock_version += 1
    candidate.decision_updated_by_user_id = principal.user_id
    candidate.decision_updated_at = datetime.now(UTC)
    if payload.outcome == "do_not_contact":
        buyer_service.mark_buyer_do_not_contact(
            db,
            principal,
            buyer,
            reason=payload.notes or "Buyer requested do-not-contact during disposition outreach.",
        )
    follow_up_task = _call_follow_up_task(
        db,
        case,
        buyer,
        outcome=payload.outcome,
        requested_at=payload.follow_up_at,
        now=now,
    )
    engagement = _log_engagement(
        db,
        principal,
        case,
        buyer,
        candidate,
        engagement_type="call",
        status=payload.outcome,
        notes=payload.notes,
        idempotency_key=payload.idempotency_key,
        metadata={
            "request_fingerprint": request_fingerprint,
            "follow_up_task_id": str(follow_up_task.id) if follow_up_task is not None else None,
            "follow_up_at": (
                follow_up_task.due_at.isoformat()
                if follow_up_task is not None and follow_up_task.due_at is not None
                else None
            ),
        },
    )
    db.add(
        AuditEvent(
            organization_id=principal.organization_id,
            actor_user_id=principal.user_id,
            actor_type="user",
            action="disposition.execution.call_outcome",
            entity_type="disposition_buyer_pool_candidate",
            entity_id=candidate.id,
            previous_value=previous,
            new_value={
                "decision_status": candidate.decision_status,
                "lifecycle_stage": candidate.lifecycle_stage,
                "lock_version": candidate.lock_version,
                "outcome": payload.outcome,
                "engagement_id": str(engagement.id),
                "follow_up_task_id": (
                    str(follow_up_task.id) if follow_up_task is not None else None
                ),
            },
            reason=payload.notes or "Disposition call outcome recorded",
        )
    )
    return _commit_idempotent_workspace(
        db,
        principal,
        case.id,
        idempotency_key=payload.idempotency_key,
        request_fingerprint=request_fingerprint,
    )


def _call_follow_up_task(
    db: Session,
    case: DispositionCase,
    buyer: Buyer,
    *,
    outcome: str,
    requested_at: datetime | None,
    now: datetime,
) -> Task | None:
    if outcome == "callback":
        if requested_at is None:
            raise ValueError("A callback outcome requires a follow-up date and time.")
        due_at = requested_at
        title = f"Call {buyer.name} back about the deal"
        priority = "high"
    elif outcome == "no_answer":
        due_at = now + timedelta(hours=4)
        title = f"Retry disposition call to {buyer.name}"
        priority = "normal"
    elif outcome == "voicemail":
        due_at = now + timedelta(hours=24)
        title = f"Follow up after voicemail to {buyer.name}"
        priority = "normal"
    else:
        return None
    task = Task(
        organization_id=case.organization_id,
        lead_id=case.lead_id,
        deal_id=case.deal_id,
        responsible_user_id=case.owner_user_id,
        task_type="disposition_buyer_follow_up",
        work_kind="supporting",
        title=title[:255],
        status="open",
        priority=priority,
        due_at=due_at,
        completed_at=None,
        completed_by_user_id=None,
        outcome=None,
    )
    db.add(task)
    db.flush()
    return task


def create_showing(
    db: Session,
    principal: Principal,
    case_id: UUID,
    payload: DispositionShowingCreate,
) -> DispositionExecutionWorkspaceRead:
    case, candidate, buyer = _candidate_for_action(
        db,
        principal,
        case_id,
        candidate_id=payload.candidate_id,
        buyer_id=payload.buyer_id,
    )
    request_fingerprint = _request_fingerprint(payload, buyer_id=buyer.id)
    existing = _engagement_by_idempotency(
        db,
        principal,
        case,
        payload.idempotency_key,
        request_fingerprint=request_fingerprint,
    )
    if existing is not None:
        result = read_workspace(db, principal, case.id)
        if result is None:
            raise ValueError("The disposition case is unavailable.")
        return result
    now = datetime.now(UTC)
    _require_future_time(payload.scheduled_at, now=now, label="showing")
    engagement = BuyerEngagement(
        organization_id=principal.organization_id,
        disposition_case_id=case.id,
        buyer_id=buyer.id,
        actor_user_id=principal.user_id,
        engagement_type="showing",
        status="scheduled",
        scheduled_at=payload.scheduled_at,
        occurred_at=now,
        completed_at=None,
        notes=payload.notes,
        idempotency_key=payload.idempotency_key,
        engagement_metadata={
            "candidate_id": str(candidate.id),
            "request_fingerprint": request_fingerprint,
            "access_status": payload.access_status,
            "follow_up_task_id": None,
        },
    )
    db.add(engagement)
    candidate.decision_status = "shortlisted"
    candidate.lifecycle_stage = "showing"
    candidate.lock_version += 1
    candidate.decision_updated_by_user_id = principal.user_id
    candidate.decision_updated_at = now
    db.add(
        ActivityEvent(
            organization_id=principal.organization_id,
            actor_user_id=principal.user_id,
            entity_type="deal",
            entity_id=case.deal_id,
            event_type="deal.buyer_showing_scheduled",
            summary=f"Buyer showing scheduled with {buyer.name}.",
        )
    )
    db.add(
        AuditEvent(
            organization_id=principal.organization_id,
            actor_user_id=principal.user_id,
            actor_type="user",
            action="disposition.execution.showing_create",
            entity_type="buyer_engagement",
            entity_id=engagement.id,
            previous_value=None,
            new_value={
                "candidate_id": str(candidate.id),
                "buyer_id": str(buyer.id),
                "status": "scheduled",
                "scheduled_at": payload.scheduled_at.isoformat(),
                "access_status": payload.access_status,
            },
            reason=payload.notes or "Buyer showing scheduled",
        )
    )
    return _commit_idempotent_workspace(
        db,
        principal,
        case.id,
        idempotency_key=payload.idempotency_key,
        request_fingerprint=request_fingerprint,
    )


def update_showing(
    db: Session,
    principal: Principal,
    case_id: UUID,
    showing_id: UUID,
    payload: DispositionShowingUpdate,
) -> DispositionExecutionWorkspaceRead | None:
    case = _mutable_house_case(db, principal, case_id)
    showing = db.scalar(
        select(BuyerEngagement)
        .where(
            BuyerEngagement.id == showing_id,
            BuyerEngagement.organization_id == principal.organization_id,
            BuyerEngagement.disposition_case_id == case.id,
            BuyerEngagement.engagement_type == "showing",
        )
        .with_for_update()
    )
    if showing is None:
        return None
    buyer = db.get(Buyer, showing.buyer_id)
    if buyer is None:
        raise ValueError("The showing buyer is unavailable.")
    if showing.status in {"completed", "cancelled", "no_show"} and (
        payload.status != showing.status
    ):
        raise ValueError(
            "A finished showing cannot be reopened. "
            "Schedule a new showing or add a correction note."
        )
    previous = {
        "status": showing.status,
        "scheduled_at": showing.scheduled_at.isoformat() if showing.scheduled_at else None,
        "metadata": dict(showing.engagement_metadata or {}),
    }
    now = datetime.now(UTC)
    effective_scheduled_at = payload.scheduled_at or showing.scheduled_at
    if payload.status in {"scheduled", "confirmed"}:
        _require_future_time(effective_scheduled_at, now=now, label="showing")
    if (
        showing.status == "completed"
        and payload.scheduled_at is not None
        and showing.scheduled_at is not None
        and _aware_utc(payload.scheduled_at) != _aware_utc(showing.scheduled_at)
    ):
        raise ValueError("A completed showing's scheduled time cannot be changed.")
    metadata = dict(showing.engagement_metadata or {})
    metadata["access_status"] = payload.access_status
    showing.status = payload.status
    showing.scheduled_at = payload.scheduled_at or showing.scheduled_at
    showing.notes = payload.notes
    if payload.status == "completed" and showing.completed_at is None:
        showing.completed_at = now
        task = Task(
            organization_id=principal.organization_id,
            lead_id=case.lead_id,
            deal_id=case.deal_id,
            responsible_user_id=case.owner_user_id,
            task_type="buyer_showing_follow_up",
            work_kind="supporting",
            title=(f"Follow up with {buyer.name} after showing")[:255],
            status="open",
            priority="high",
            due_at=now + timedelta(hours=24),
            completed_at=None,
            completed_by_user_id=None,
            outcome=None,
        )
        db.add(task)
        db.flush()
        metadata["follow_up_task_id"] = str(task.id)
        db.add(
            ActivityEvent(
                organization_id=principal.organization_id,
                actor_user_id=principal.user_id,
                entity_type="deal",
                entity_id=case.deal_id,
                event_type="deal.buyer_showing_completed",
                summary=(
                    f"Buyer showing completed with {buyer.name}; "
                    "a 24-hour follow-up task was created."
                ),
            )
        )
    showing.engagement_metadata = metadata
    db.add(
        AuditEvent(
            organization_id=principal.organization_id,
            actor_user_id=principal.user_id,
            actor_type="user",
            action="disposition.execution.showing_update",
            entity_type="buyer_engagement",
            entity_id=showing.id,
            previous_value=previous,
            new_value={
                "status": showing.status,
                "scheduled_at": (
                    showing.scheduled_at.isoformat() if showing.scheduled_at else None
                ),
                "metadata": metadata,
            },
            reason=payload.notes or "Buyer showing status updated",
        )
    )
    db.commit()
    result = read_workspace(db, principal, case.id)
    if result is None:
        raise ValueError("The disposition case is unavailable.")
    return result


def _mutable_house_case(
    db: Session,
    principal: Principal,
    case_id: UUID,
) -> DispositionCase:
    case = dispositions.scoped_case_for_mutation(
        db,
        principal,
        case_id,
        allowed_statuses=EXECUTION_CASE_STATUSES,
    )
    if case is None:
        raise ValueError("Disposition case not found.")
    dispositions.require_house_case_workflow(db, case)
    return case


def _candidate_for_action(
    db: Session,
    principal: Principal,
    case_id: UUID,
    *,
    candidate_id: UUID | None,
    buyer_id: UUID | None,
) -> tuple[DispositionCase, DispositionBuyerPoolCandidate, Buyer]:
    case = _mutable_house_case(db, principal, case_id)
    candidate = None
    if candidate_id is not None:
        candidate = db.scalar(
            select(DispositionBuyerPoolCandidate)
            .where(
                DispositionBuyerPoolCandidate.id == candidate_id,
                DispositionBuyerPoolCandidate.organization_id
                == principal.organization_id,
                DispositionBuyerPoolCandidate.disposition_case_id == case.id,
            )
            .with_for_update()
        )
        if candidate is None:
            raise ValueError("The buyer candidate is stale or unavailable for this deal.")
        if candidate.buyer_id is None:
            raise ValueError("Approve this candidate into the Buyer Network before contact.")
        if buyer_id is not None and candidate.buyer_id != buyer_id:
            raise ValueError(
                "The candidate and canonical buyer references do not match. Refresh and retry."
            )
        buyer_id = candidate.buyer_id
    if buyer_id is None:
        raise ValueError("Provide a ranked candidate or canonical buyer reference.")
    buyer = db.scalar(
        select(Buyer).where(
            Buyer.id == buyer_id,
            Buyer.organization_id == principal.organization_id,
            Buyer.archived_at.is_(None),
            Buyer.status != "archived",
        )
    )
    if buyer is None:
        raise ValueError("The canonical buyer record is unavailable.")
    if candidate is None:
        candidate = _ensure_case_candidate(db, principal, case, buyer)
    if _buyer_is_do_not_contact(buyer):
        raise ValueError(BUYER_DO_NOT_CONTACT_BLOCKER)
    if _candidate_is_passed(candidate):
        raise ValueError(
            "This buyer is explicitly passed. Clear the buyer-pool decision before contact."
        )
    return case, candidate, buyer


def _referenced_buyer_id(
    db: Session,
    principal: Principal,
    case: DispositionCase,
    *,
    candidate_id: UUID | None,
    buyer_id: UUID | None,
) -> UUID:
    if candidate_id is None:
        if buyer_id is None:
            raise ValueError("Provide a ranked candidate or canonical buyer reference.")
        return buyer_id
    candidate_buyer_id = db.scalar(
        select(DispositionBuyerPoolCandidate.buyer_id).where(
            DispositionBuyerPoolCandidate.id == candidate_id,
            DispositionBuyerPoolCandidate.organization_id == principal.organization_id,
            DispositionBuyerPoolCandidate.disposition_case_id == case.id,
        )
    )
    if candidate_buyer_id is None:
        raise ValueError("The buyer candidate is stale or unavailable for this deal.")
    if buyer_id is not None and buyer_id != candidate_buyer_id:
        raise ValueError(
            "The candidate and canonical buyer references do not match. Refresh and retry."
        )
    return candidate_buyer_id


def _ensure_case_candidate(
    db: Session,
    principal: Principal,
    case: DispositionCase,
    buyer: Buyer,
) -> DispositionBuyerPoolCandidate:
    candidate = _case_candidate(db, principal, case, buyer, lock=True)
    if candidate is not None:
        return candidate
    candidate = DispositionBuyerPoolCandidate(
        organization_id=principal.organization_id,
        disposition_case_id=case.id,
        identity_key=f"buyer:{buyer.id}",
        source_type="internal",
        buyer_id=buyer.id,
        latest_discovery_candidate_id=None,
        provider=None,
        external_key=None,
        display_name=buyer.name,
        company_name=buyer.company_name,
        email=buyer.email,
        phone=buyer.phone,
        provenance_snapshot={
            "buyer_id": str(buyer.id),
            "buyer_source": {
                "source_key": buyer.source_key,
                "source_detail": buyer.source_detail,
                "source_external_key": buyer.source_external_key,
            },
            "execution_source": "buyer_network",
        },
        overlap_status="none",
        possible_buyer_id=None,
        overlap_evidence={"merged_external_candidate_ids": []},
        decision_status="undecided",
        lifecycle_stage="discovered",
        decision_reason=None,
        lock_version=1,
    )
    try:
        with db.begin_nested():
            db.add(candidate)
            db.flush()
    except IntegrityError:
        winner = _case_candidate(db, principal, case, buyer, lock=True)
        if winner is None:
            raise
        return winner
    return candidate


def _case_candidate(
    db: Session,
    principal: Principal,
    case: DispositionCase,
    buyer: Buyer,
    *,
    lock: bool,
) -> DispositionBuyerPoolCandidate | None:
    statement = (
        select(DispositionBuyerPoolCandidate)
        .where(
            DispositionBuyerPoolCandidate.organization_id == principal.organization_id,
            DispositionBuyerPoolCandidate.disposition_case_id == case.id,
            DispositionBuyerPoolCandidate.buyer_id == buyer.id,
        )
    )
    return db.scalar(statement.with_for_update() if lock else statement)


def _candidate_read(
    db: Session,
    principal: Principal,
    property_record: Property,
    buyer: Buyer,
    candidate: DispositionBuyerPoolCandidate | None,
    entry: Any | None,
) -> DispositionExecutionCandidateRead:
    action_blockers: list[str] = []
    if _candidate_is_passed(candidate):
        action_blockers.append(
            "This buyer is explicitly passed. Clear the buyer-pool decision before contact."
        )
    if _buyer_is_do_not_contact(buyer):
        action_blockers.append(BUYER_DO_NOT_CONTACT_BLOCKER)
    conversation = _buyer_conversation(db, principal, buyer.id)
    contact = db.get(Contact, conversation.contact_id) if conversation is not None else None
    if contact is not None:
        sms = evaluate_sms_eligibility(db, contact, require_permission=False)
        voice = evaluate_voice_eligibility(db, contact, require_permission=False)
        sms_read = DispositionExecutionPermissionRead(
            status=sms.consent_status,
            allowed=sms.can_send,
            blockers=list(sms.blockers),
        )
        voice_read = DispositionExecutionPermissionRead(
            status=voice.consent_status,
            allowed=voice.can_call,
            blockers=list(voice.blockers),
        )
    else:
        sms_read = DispositionExecutionPermissionRead(
            status="missing",
            allowed=False,
            blockers=["The canonical buyer conversation is unavailable."],
        )
        voice_read = DispositionExecutionPermissionRead(
            status="missing",
            allowed=False,
            blockers=["The canonical buyer conversation is unavailable."],
        )
    if _buyer_is_do_not_contact(buyer):
        sms_read = _blocked_permission_read(sms_read, BUYER_DO_NOT_CONTACT_BLOCKER)
        voice_read = _blocked_permission_read(voice_read, BUYER_DO_NOT_CONTACT_BLOCKER)
    reference = _purchase_reference(entry.supporting_evidence) if entry is not None else None
    return DispositionExecutionCandidateRead(
        candidate_id=candidate.id if candidate is not None else None,
        buyer_id=buyer.id,
        conversation_id=conversation.id if conversation is not None else None,
        name=buyer.name,
        company_name=buyer.company_name,
        phone=buyer.phone,
        email=buyer.email,
        ranking_status="ranked" if entry is not None else "unranked",
        rank=int(entry.rank) if entry is not None else None,
        score_basis_points=entry.score_basis_points if entry is not None else None,
        relationship_status=buyer.relationship_status,
        tier=buyer.tier,
        temperature=buyer.temperature,
        decision_status=candidate.decision_status if candidate is not None else "undecided",
        lifecycle_stage=candidate.lifecycle_stage if candidate is not None else "discovered",
        decision_reason=candidate.decision_reason if candidate is not None else None,
        lock_version=candidate.lock_version if candidate is not None else None,
        actionable=not action_blockers,
        action_blockers=action_blockers,
        score_explanation=entry.score_explanation if entry is not None else [],
        recent_purchase_reference=reference,
        sms=sms_read,
        voice=voice_read,
        sms_draft=_sms_draft(
            buyer.name,
            property_record,
            reference,
            sender_name=_sender_name(db, principal.user_id),
        ),
    )


def _candidate_is_passed(candidate: DispositionBuyerPoolCandidate | None) -> bool:
    return bool(
        candidate is not None
        and (
            candidate.decision_status == "passed"
            or candidate.lifecycle_stage == "pass"
        )
    )


def _buyer_is_do_not_contact(buyer: Buyer) -> bool:
    return (
        buyer.status == "do_not_contact"
        or buyer.relationship_status == "do_not_contact"
    )


def _blocked_permission_read(
    permission: DispositionExecutionPermissionRead,
    blocker: str,
) -> DispositionExecutionPermissionRead:
    return DispositionExecutionPermissionRead(
        status=permission.status,
        allowed=False,
        blockers=list(dict.fromkeys([*permission.blockers, blocker])),
    )


def _buyer_conversation(
    db: Session,
    principal: Principal,
    buyer_id: UUID,
) -> Conversation | None:
    return db.scalar(
        select(Conversation)
        .join(
            ConversationContextLink,
            ConversationContextLink.conversation_id == Conversation.id,
        )
        .where(
            Conversation.organization_id == principal.organization_id,
            ConversationContextLink.organization_id == principal.organization_id,
            ConversationContextLink.context_type == "buyer",
            ConversationContextLink.buyer_id == buyer_id,
        )
    )


def _candidate_queue_state(
    db: Session,
    case: DispositionCase,
) -> tuple[set[UUID], set[UUID]]:
    handled: set[UUID] = set()
    deferred: set[UUID] = set()
    engagements = list(
        db.scalars(
            select(BuyerEngagement)
            .where(
                BuyerEngagement.organization_id == case.organization_id,
                BuyerEngagement.disposition_case_id == case.id,
                BuyerEngagement.engagement_type == "call",
            )
            .order_by(BuyerEngagement.occurred_at.asc(), BuyerEngagement.created_at.asc())
        ).all()
    )
    latest_by_buyer: dict[UUID, BuyerEngagement] = {}
    for engagement in engagements:
        latest_by_buyer[engagement.buyer_id] = engagement
    now = datetime.now(UTC)
    for buyer_id, engagement in latest_by_buyer.items():
        if engagement.status not in {"callback", "no_answer", "voicemail"}:
            handled.add(buyer_id)
            continue
        task = _engagement_follow_up_task(db, engagement)
        if task is not None:
            if task.status == "open" and task.due_at is not None:
                task_due_at = _aware_utc(task.due_at)
                if task_due_at > now:
                    deferred.add(buyer_id)
            continue
        metadata_due_at = _metadata_datetime(
            (engagement.engagement_metadata or {}).get("follow_up_at")
        )
        if metadata_due_at is None or metadata_due_at > now:
            deferred.add(buyer_id)
    return handled, deferred


def _complete_prior_follow_up_task(
    db: Session,
    principal: Principal,
    case: DispositionCase,
    buyer: Buyer,
    *,
    now: datetime,
) -> None:
    engagements = db.scalars(
        select(BuyerEngagement)
        .where(
            BuyerEngagement.organization_id == principal.organization_id,
            BuyerEngagement.disposition_case_id == case.id,
            BuyerEngagement.buyer_id == buyer.id,
            BuyerEngagement.engagement_type == "call",
        )
        .order_by(BuyerEngagement.occurred_at.desc(), BuyerEngagement.created_at.desc())
    ).all()
    for engagement in engagements:
        task = _engagement_follow_up_task(db, engagement)
        if task is not None and task.status == "open":
            task.status = "completed"
            task.completed_at = now
            task.completed_by_user_id = principal.user_id
            task.outcome = "Buyer recontacted from the disposition execution queue."
        return


def _engagement_follow_up_task(
    db: Session,
    engagement: BuyerEngagement,
) -> Task | None:
    raw_task_id = (engagement.engagement_metadata or {}).get("follow_up_task_id")
    if not raw_task_id:
        return None
    try:
        task_id = UUID(str(raw_task_id))
    except ValueError:
        return None
    return db.scalar(
        select(Task).where(
            Task.id == task_id,
            Task.organization_id == engagement.organization_id,
        )
    )


def _metadata_datetime(value: object) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    return _aware_utc(parsed)


def _aware_utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _log_engagement(
    db: Session,
    principal: Principal,
    case: DispositionCase,
    buyer: Buyer,
    candidate: DispositionBuyerPoolCandidate,
    *,
    engagement_type: str,
    status: str,
    notes: str | None,
    idempotency_key: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> BuyerEngagement:
    engagement = BuyerEngagement(
        organization_id=principal.organization_id,
        disposition_case_id=case.id,
        buyer_id=buyer.id,
        actor_user_id=principal.user_id,
        engagement_type=engagement_type,
        status=status,
        scheduled_at=None,
        occurred_at=datetime.now(UTC),
        completed_at=None,
        notes=notes,
        idempotency_key=idempotency_key,
        engagement_metadata={
            "candidate_id": str(candidate.id),
            "buyer_id": str(buyer.id),
            **(metadata or {}),
        },
    )
    db.add(engagement)
    return engagement


def _engagement_by_idempotency(
    db: Session,
    principal: Principal,
    case: DispositionCase,
    idempotency_key: str,
    *,
    request_fingerprint: str,
) -> BuyerEngagement | None:
    engagement = db.scalar(
        select(BuyerEngagement).where(
            BuyerEngagement.organization_id == principal.organization_id,
            BuyerEngagement.disposition_case_id == case.id,
            BuyerEngagement.idempotency_key == idempotency_key,
        )
    )
    if engagement is None:
        return None
    stored_fingerprint = (engagement.engagement_metadata or {}).get("request_fingerprint")
    if stored_fingerprint != request_fingerprint:
        raise ValueError(
            "The idempotency key was already used for a different disposition action."
        )
    return engagement


def _request_fingerprint(
    payload: (
        DispositionExecutionSmsCreate
        | DispositionExecutionOutcomeCreate
        | DispositionShowingCreate
    ),
    *,
    buyer_id: UUID,
) -> str:
    canonical = payload.model_dump(
        mode="json",
        exclude={"idempotency_key", "candidate_id", "buyer_id"},
    )
    canonical["buyer_id"] = str(buyer_id)
    encoded = json.dumps(canonical, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return sha256(encoded).hexdigest()


def _commit_idempotent_workspace(
    db: Session,
    principal: Principal,
    case_id: UUID,
    *,
    idempotency_key: str,
    request_fingerprint: str,
) -> DispositionExecutionWorkspaceRead:
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        case = dispositions.scoped_case(db, principal, case_id)
        if case is None:
            raise ValueError("The disposition case is unavailable.") from exc
        replay = _engagement_by_idempotency(
            db,
            principal,
            case,
            idempotency_key,
            request_fingerprint=request_fingerprint,
        )
        if replay is None:
            raise exc
    result = read_workspace(db, principal, case_id)
    if result is None:
        raise ValueError("The disposition case is unavailable.")
    return result


def _require_future_time(
    value: datetime | None,
    *,
    now: datetime,
    label: str,
) -> datetime:
    if value is None:
        raise ValueError(f"A {label} date and time is required.")
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"The {label} date and time must include a timezone.")
    normalized = value.astimezone(UTC)
    if normalized <= now:
        raise ValueError(f"The {label} date and time must be in the future.")
    return normalized


def _showing_reads(db: Session, case: DispositionCase) -> list[DispositionShowingRead]:
    showings = db.scalars(
        select(BuyerEngagement)
        .where(
            BuyerEngagement.organization_id == case.organization_id,
            BuyerEngagement.disposition_case_id == case.id,
            BuyerEngagement.engagement_type == "showing",
        )
        .order_by(BuyerEngagement.scheduled_at.desc(), BuyerEngagement.occurred_at.desc())
    ).all()
    buyer_ids = {item.buyer_id for item in showings}
    buyers = {
        buyer.id: buyer
        for buyer in db.scalars(
            select(Buyer).where(
                Buyer.id.in_(buyer_ids),
                Buyer.organization_id == case.organization_id,
            )
        ).all()
    } if buyer_ids else {}
    result: list[DispositionShowingRead] = []
    for showing in showings:
        metadata = showing.engagement_metadata or {}
        try:
            candidate_id = UUID(str(metadata.get("candidate_id")))
        except (TypeError, ValueError):
            continue
        follow_up_task_id = None
        try:
            if metadata.get("follow_up_task_id"):
                follow_up_task_id = UUID(str(metadata["follow_up_task_id"]))
        except (TypeError, ValueError):
            follow_up_task_id = None
        status = showing.status if showing.status in VALID_SHOWING_STATUSES else "scheduled"
        access_status = str(metadata.get("access_status") or "not_requested")
        if access_status not in VALID_ACCESS_STATUSES:
            access_status = "not_requested"
        result.append(
            DispositionShowingRead(
                id=showing.id,
                candidate_id=candidate_id,
                buyer_id=showing.buyer_id,
                buyer_name=(
                    buyers[showing.buyer_id].name
                    if showing.buyer_id in buyers
                    else "Buyer"
                ),
                status=cast(ShowingStatus, status),
                access_status=cast(ShowingAccessStatus, access_status),
                scheduled_at=showing.scheduled_at,
                completed_at=showing.completed_at,
                follow_up_task_id=follow_up_task_id,
                notes=showing.notes,
            )
        )
    return result


def _purchase_reference(evidence: list[dict[str, object]]) -> str | None:
    for item in evidence:
        value = _find_reference(item)
        if value:
            return value
    return None


def _find_reference(value: object) -> str | None:
    if isinstance(value, dict):
        for key in ("property_address", "address", "street_address", "street"):
            candidate = value.get(key)
            if isinstance(candidate, str) and candidate.strip():
                return candidate.strip().split(",", 1)[0]
        for child in value.values():
            result = _find_reference(child)
            if result:
                return result
    elif isinstance(value, list):
        for child in value:
            result = _find_reference(child)
            if result:
                return result
    return None


def _sender_name(db: Session, user_id: UUID) -> str:
    user = db.get(User, user_id)
    if user is None or not user.display_name.strip():
        return "Stonegate"
    return user.display_name.strip().split()[0]


def _sms_draft(
    name: str,
    property_record: Property,
    reference: str | None,
    *,
    sender_name: str,
) -> str:
    first_name = name.strip().split()[0] if name.strip() else "there"
    if reference:
        location = f"a few miles from the one you bought on {reference}"
    else:
        market = ", ".join(
            value for value in (property_record.city, property_record.state) if value
        )
        location = f"near {market}" if market else "that may fit your buy box"
    return (
        f"Hey {first_name}, this is {sender_name} with Stonegate. I have a property {location}. "
        "Would you be interested in looking at something similar?"
    )


def _property_address(property_record: Property) -> str:
    locality = ", ".join(
        value for value in (property_record.city, property_record.state) if value
    )
    postal = f" {property_record.postal_code}" if property_record.postal_code else ""
    return ", ".join(
        value for value in (property_record.street_address, f"{locality}{postal}".strip()) if value
    )
