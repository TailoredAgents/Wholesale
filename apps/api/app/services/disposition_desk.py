from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Literal
from uuid import UUID
from zoneinfo import ZoneInfo

from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session

from app.core.auth import Principal
from app.domain.assets import ASSET_CLASSES, property_identity_label
from app.domain.rbac import PermissionKeys
from app.models.foundation import (
    AuditEvent,
    Buyer,
    BuyerBuyBox,
    BuyerBuyBoxVersion,
    BuyerDiscoveryRun,
    BuyerEngagement,
    BuyerOffer,
    BuyerProofDocument,
    Contact,
    Conversation,
    ConversationContextLink,
    Deal,
    DispositionBuyerSelection,
    DispositionBuyerSelectionSlot,
    DispositionCase,
    DispositionClosingCheckpoint,
    DispositionDeadlineAlert,
    DispositionMatch,
    Lead,
    Property,
    Task,
    Transaction,
    TransactionChecklistItem,
    User,
)
from app.schemas.deals import DealQueueItemRead
from app.schemas.disposition_desk import (
    DispositionDeskActionRead,
    DispositionDeskBuyerHealthRead,
    DispositionDeskCategory,
    DispositionDeskChecklistIssueRead,
    DispositionDeskChecklistSummaryRead,
    DispositionDeskItemRead,
    DispositionDeskMetricsRead,
    DispositionDeskParallelActionRead,
    DispositionDeskRead,
    DispositionDeskScope,
    DispositionDeskSectionsRead,
    DispositionDeskSectionStatusRead,
    DispositionDeskSourceHealthRead,
)
from app.services import buyer_discovery, deals, disposition_readiness
from app.services.disposition_handoff import (
    HANDOFF_PENDING_BLOCKER,
    HANDOFF_SETUP_TASK_TYPE,
    active_authorized_disposition_user,
)
from app.services.dispositions import _proof_is_current_verified
from app.services.lead_lifecycle import INACTIVE_LEAD_STAGES

ACTIVE_CASE_STATUSES = {
    "package_prep",
    "buyer_matching",
    "marketed",
    "offers_received",
    "buyer_selected",
}
COMPLETE_WORK_STATUSES = {"complete", "completed", "cancelled", "canceled", "not_applicable"}
INACTIVE_DEAL_STAGES = {"cancelled", "canceled", "closed", "dead", "funded"}
EASTERN = ZoneInfo("America/New_York")
MAX_SECTION_ITEMS = 100
DispositionDeskSeverity = Literal["info", "warning", "danger"]


def _aware(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def _money(cents: int) -> str:
    return f"${cents / 100:,.0f}"


def _team_scope(
    db: Session,
    principal: Principal,
    requested_scope: DispositionDeskScope,
) -> tuple[DispositionDeskScope, set[UUID] | None, str, int, bool, str | None]:
    if requested_scope == "mine":
        user = db.get(User, principal.user_id)
        return (
            "mine",
            {principal.user_id},
            user.display_name if user else "My work",
            1,
            True,
            "Unassigned active disposition cases are included so setup work stays visible.",
        )
    active_count = len(
        db.scalars(
            select(User.id).where(
                User.organization_id == principal.organization_id,
                User.is_active.is_(True),
            )
        ).all()
    )
    return (
        "team",
        None,
        "Company",
        active_count,
        True,
        "Company view includes every active disposition case and investor relationship.",
    )


def _scoped(user_id: UUID | None, allowed_user_ids: set[UUID] | None) -> bool:
    return allowed_user_ids is None or user_id in allowed_user_ids


def _users(db: Session, organization_id: UUID, user_ids: set[UUID | None]) -> dict[UUID, User]:
    ids = {value for value in user_ids if value is not None}
    if not ids:
        return {}
    return {
        user.id: user
        for user in db.scalars(
            select(User).where(User.organization_id == organization_id, User.id.in_(ids))
        ).all()
    }


def _owner_name(user_id: UUID | None, users: dict[UUID, User]) -> str:
    user = users.get(user_id) if user_id else None
    return user.display_name if user else "Unassigned"


def _desk_checklist(
    db: Session,
    principal: Principal,
    case: DispositionCase,
) -> DispositionDeskChecklistSummaryRead | None:
    try:
        readiness = disposition_readiness.read_case_readiness(db, principal, case.id)
    except ValueError:
        return None
    if readiness is None:
        return None
    action_by_key = {item.key: item for item in readiness.actions}
    best = action_by_key.get(readiness.best_action_key) if readiness.best_action_key else None
    issues = [
        DispositionDeskChecklistIssueRead(
            key=check.key,
            label=check.label,
            blocker_class=check.blocker_class,
            detail=check.detail,
            href=check.remediation.href if check.remediation else action.href,
        )
        for action in readiness.actions
        for check in action.checks
        if check.blocker_class is not None
    ]
    parallel_actions = [
        DispositionDeskParallelActionRead(
            key=action.key,
            label=action.label,
            href=action.href,
        )
        for key in readiness.parallel_action_keys
        if (action := action_by_key.get(key)) is not None
    ]
    return DispositionDeskChecklistSummaryRead(
        warning_count=readiness.warning_count,
        completed_count=readiness.completed_count,
        total_count=readiness.total_count,
        best_action_key=readiness.best_action_key,
        best_action_label=best.label if best else None,
        best_action_href=best.href if best else None,
        parallel_action_keys=readiness.parallel_action_keys,
        issues=issues,
        parallel_actions=parallel_actions,
    )


def _blocked_handoff_owner(
    audit: AuditEvent | None,
    transaction: Transaction,
    existing_case: DispositionCase | None,
) -> UUID | None:
    raw_owner = (audit.new_value or {}).get("owner_user_id") if audit is not None else None
    if isinstance(raw_owner, str):
        try:
            return UUID(raw_owner)
        except ValueError:
            pass
    return (
        existing_case.owner_user_id
        if existing_case is not None
        else transaction.coordinator_user_id or transaction.owner_user_id
    )


def _blocked_handoff_reasons(
    audit: AuditEvent | None,
    existing_case: DispositionCase | None,
) -> list[str]:
    if audit is not None:
        raw_blockers = (audit.new_value or {}).get("blockers")
        if isinstance(raw_blockers, list):
            blockers = [value.strip() for value in raw_blockers if isinstance(value, str)]
            if blockers:
                return blockers
        if audit.reason and audit.reason.strip():
            return [audit.reason.strip()]
    if existing_case is not None:
        return [
            "The existing Disposition case is "
            f"{existing_case.status.replace('_', ' ')} while its transaction remains active."
        ]
    return [HANDOFF_PENDING_BLOCKER]


def _asset_class(value: str | None) -> Literal["house", "land"] | None:
    if value == "house":
        return "house"
    if value == "land":
        return "land"
    return None


def _property_address(property_record: Property | None) -> str:
    if property_record is None:
        return "Address unavailable"
    return (
        property_identity_label(
            street_address=property_record.street_address,
            city=property_record.city,
            state=property_record.state,
            postal_code=property_record.postal_code,
            parcel_id=property_record.parcel_id,
            county=property_record.county,
        )
        or "Address unavailable"
    )


def _severity(
    due_at: datetime | None,
    *,
    blocker: bool = False,
) -> DispositionDeskSeverity:
    if due_at and _aware(due_at) < datetime.now(UTC):
        return "danger"
    if blocker or (due_at and _aware(due_at) <= datetime.now(UTC) + timedelta(days=1)):
        return "warning"
    return "info"


def _deal_href(deal_id: UUID, *, section: str = "package") -> str:
    return (
        f"/os/deals?view=all&display=queue&deal={deal_id}&tab=disposition&dispositionTab={section}"
    )


def _offer_room_href(deal_id: UUID) -> str:
    return f"{_deal_href(deal_id, section='offers')}#offer-room"


def _sort(items: list[DispositionDeskItemRead]) -> list[DispositionDeskItemRead]:
    severity = {"danger": 0, "warning": 1, "info": 2}
    far_future = datetime.max.replace(tzinfo=UTC)
    unique = {item.key: item for item in items}
    return sorted(
        unique.values(),
        key=lambda item: (
            severity[item.severity],
            _aware(item.due_at) if item.due_at else far_future,
            item.title.lower(),
            item.key,
        ),
    )


def _page[SectionItem](
    items: list[SectionItem],
    *,
    offset: int = 0,
) -> tuple[list[SectionItem], DispositionDeskSectionStatusRead]:
    returned = items[offset : offset + MAX_SECTION_ITEMS]
    return returned, DispositionDeskSectionStatusRead(
        total=len(items),
        returned=len(returned),
        has_more=offset + len(returned) < len(items),
        offset=offset,
    )


def _today(
    items: list[DispositionDeskItemRead],
    day_end: datetime,
) -> list[DispositionDeskItemRead]:
    selected: dict[str, DispositionDeskItemRead] = {}
    for item in items:
        urgent_without_date = item.category in {"replies", "offers"} or item.severity == "danger"
        if urgent_without_date or (item.due_at and _aware(item.due_at) <= day_end):
            selected[item.key] = item.model_copy(update={"category": "today"})
    return _sort(list(selected.values()))


def _coverage_warning(
    item: DealQueueItemRead,
    case: DispositionCase | None,
    *,
    has_viable_approved_backup: bool,
) -> DispositionDeskItemRead | None:
    blocker: str | None = None
    reason = "Buyer coverage needs review."
    if case is None:
        blocker = "Disposition case has not been opened."
    elif case.package_status != "approved":
        blocker = "Investor package is not approved."
    elif item.buyer_match_count == 0:
        blocker = "No buyers have been ranked for this deal."
    elif item.buyer_match_count < 3:
        suffix = "es" if item.buyer_match_count != 1 else ""
        blocker = f"Only {item.buyer_match_count} buyer match{suffix} are available."
    elif item.buyer_offer_count == 0:
        blocker = "No buyer offer has been recorded."
    elif item.selected_buyer_name and not has_viable_approved_backup:
        blocker = "A primary buyer is selected without backup coverage."
    if blocker is None:
        return None
    return DispositionDeskItemRead(
        key=f"coverage:{item.id}",
        category="active_deals",
        title=item.property_address,
        context=item.seller_name,
        owner_user_id=case.owner_user_id if case else None,
        owner_name=item.disposition_owner_name or "Unassigned",
        due_at=item.next_deadline,
        reason=reason,
        blocker=blocker,
        severity="danger" if item.buyer_match_count == 0 else "warning",
        deal_id=item.id,
        disposition_case_id=case.id if case else None,
        primary_action=DispositionDeskActionRead(
            label="Open deal" if case else "Open disposition",
            href=(
                _deal_href(item.id)
                if case
                else f"/os/dispositions?transaction={item.transaction_id}"
            ),
        ),
    )


def read_desk(
    db: Session,
    principal: Principal,
    *,
    requested_scope: DispositionDeskScope,
    selected_section: DispositionDeskCategory | None = None,
    offset: int = 0,
) -> DispositionDeskRead:
    if offset < 0:
        raise ValueError("Disposition Desk offset cannot be negative.")
    if selected_section is None and offset:
        raise ValueError("Disposition Desk section is required when offset is greater than zero.")
    effective_scope, allowed_user_ids, scope_label, member_count, can_view_team, scope_notice = (
        _team_scope(db, principal, requested_scope)
    )
    now = datetime.now(UTC)
    local_now = now.astimezone(EASTERN)
    day_end = local_now.replace(hour=23, minute=59, second=59, microsecond=999999).astimezone(UTC)

    case_rows = list(
        db.scalars(
            select(DispositionCase).where(
                DispositionCase.organization_id == principal.organization_id,
                DispositionCase.status.in_(ACTIVE_CASE_STATUSES),
            )
        ).all()
    )
    cases = [
        case
        for case in case_rows
        if (
            active_authorized_disposition_user(
                db,
                principal.organization_id,
                case.owner_user_id,
            )
            is None
            or _scoped(case.owner_user_id, allowed_user_ids)
        )
    ]
    case_by_deal = {case.deal_id: case for case in cases}
    case_by_id = {case.id: case for case in cases}
    case_ids = {case.id for case in cases}

    setup_rows = list(
        db.execute(
            select(Transaction, Deal, Lead, Contact, Property, DispositionCase)
            .join(
                Deal,
                (Deal.id == Transaction.deal_id)
                & (Deal.organization_id == Transaction.organization_id),
            )
            .join(
                Lead,
                (Lead.id == Transaction.lead_id)
                & (Lead.organization_id == Transaction.organization_id),
            )
            .join(
                Contact,
                (Contact.id == Transaction.contact_id)
                & (Contact.organization_id == Transaction.organization_id),
            )
            .join(
                Property,
                (Property.id == Transaction.property_id)
                & (Property.organization_id == Transaction.organization_id),
            )
            .outerjoin(
                DispositionCase,
                (DispositionCase.transaction_id == Transaction.id)
                & (DispositionCase.organization_id == Transaction.organization_id),
            )
            .where(
                Transaction.organization_id == principal.organization_id,
                or_(
                    DispositionCase.id.is_(None),
                    ~DispositionCase.status.in_(ACTIVE_CASE_STATUSES),
                ),
                Transaction.status.in_(("executed", "closing")),
                Transaction.contract_executed_at.is_not(None),
                Lead.asset_class.in_(tuple(sorted(ASSET_CLASSES))),
                Lead.archived_at.is_(None),
                ~Lead.stage_key.in_(tuple(INACTIVE_LEAD_STAGES)),
                ~Deal.stage_key.in_(tuple(INACTIVE_DEAL_STAGES)),
            )
            .order_by(Transaction.contract_executed_at, Transaction.id)
        )
        .tuples()
        .all()
    )
    setup_transaction_ids = {
        setup_transaction.id for setup_transaction, _, _, _, _, _ in setup_rows
    }
    setup_audit_by_transaction: dict[UUID, AuditEvent] = {}
    if setup_transaction_ids:
        for blocked_audit in db.scalars(
            select(AuditEvent)
            .where(
                AuditEvent.organization_id == principal.organization_id,
                AuditEvent.action == "disposition.case_auto_create_blocked",
                AuditEvent.entity_type == "transaction",
                AuditEvent.entity_id.in_(setup_transaction_ids),
            )
            .order_by(AuditEvent.created_at.desc(), AuditEvent.id.desc())
        ).all():
            if blocked_audit.entity_id is not None:
                setup_audit_by_transaction.setdefault(
                    blocked_audit.entity_id,
                    blocked_audit,
                )
    setup_intakes: list[
        tuple[
            Transaction,
            Deal,
            Lead,
            Contact,
            Property,
            DispositionCase | None,
            UUID | None,
            list[str],
        ]
    ] = []
    for (
        setup_transaction,
        setup_deal,
        setup_lead,
        setup_contact,
        setup_property,
        joined_case,
    ) in setup_rows:
        latest_blocked_audit = setup_audit_by_transaction.get(setup_transaction.id)
        setup_owner_id = _blocked_handoff_owner(
            latest_blocked_audit,
            setup_transaction,
            joined_case,
        )
        if not _scoped(setup_owner_id, allowed_user_ids):
            continue
        setup_intakes.append(
            (
                setup_transaction,
                setup_deal,
                setup_lead,
                setup_contact,
                setup_property,
                joined_case,
                setup_owner_id,
                _blocked_handoff_reasons(latest_blocked_audit, joined_case),
            )
        )
    setup_deal_ids = {setup_deal.id for _, setup_deal, _, _, _, _, _, _ in setup_intakes}

    deal_overview = deals.overview(
        db,
        principal,
        deal_ids=set(case_by_deal) | setup_deal_ids,
    )
    active_records_by_id: dict[UUID, DealQueueItemRead] = {}
    for item in deal_overview.items:
        if item.closing_status not in {"funded", "cancelled"} and item.id in case_by_deal:
            active_records_by_id.setdefault(item.id, item)
    active_records = list(active_records_by_id.values())
    active_deal_ids = {item.id for item in active_records}
    operational_deal_ids = active_deal_ids | setup_deal_ids

    transactions = list(
        db.scalars(
            select(Transaction).where(
                Transaction.organization_id == principal.organization_id,
                Transaction.deal_id.in_(active_deal_ids)
                if active_deal_ids
                else Transaction.id.is_(None),
            )
        ).all()
    )
    transaction_by_deal = {transaction.deal_id: transaction for transaction in transactions}
    transaction_ids = {transaction.id for transaction in transactions}
    checklist_rows = list(
        db.scalars(
            select(TransactionChecklistItem).where(
                TransactionChecklistItem.organization_id == principal.organization_id,
                TransactionChecklistItem.transaction_id.in_(transaction_ids)
                if transaction_ids
                else TransactionChecklistItem.id.is_(None),
                TransactionChecklistItem.due_at.is_not(None),
                TransactionChecklistItem.status.notin_(COMPLETE_WORK_STATUSES),
            )
        ).all()
    )
    checklist_by_transaction: dict[UUID, list[TransactionChecklistItem]] = {}
    for checklist_item in checklist_rows:
        checklist_by_transaction.setdefault(checklist_item.transaction_id, []).append(
            checklist_item
        )

    offer_room_checkpoints = list(
        db.scalars(
            select(DispositionClosingCheckpoint).where(
                DispositionClosingCheckpoint.organization_id == principal.organization_id,
                DispositionClosingCheckpoint.disposition_case_id.in_(case_ids)
                if case_ids
                else DispositionClosingCheckpoint.id.is_(None),
                DispositionClosingCheckpoint.status.in_(("pending", "in_progress", "missed")),
            )
        ).all()
    )
    checkpoint_ids = {checkpoint.id for checkpoint in offer_room_checkpoints}
    deadline_alerts = list(
        db.scalars(
            select(DispositionDeadlineAlert)
            .where(
                DispositionDeadlineAlert.organization_id == principal.organization_id,
                DispositionDeadlineAlert.checkpoint_id.in_(checkpoint_ids)
                if checkpoint_ids
                else DispositionDeadlineAlert.id.is_(None),
                DispositionDeadlineAlert.status.in_(("open", "acknowledged")),
            )
            .order_by(DispositionDeadlineAlert.created_at.desc())
        ).all()
    )
    active_alert_by_checkpoint: dict[UUID, DispositionDeadlineAlert] = {}
    for alert in deadline_alerts:
        active_alert_by_checkpoint.setdefault(alert.checkpoint_id, alert)

    match_rows = list(
        db.scalars(
            select(DispositionMatch).where(
                DispositionMatch.organization_id == principal.organization_id,
                DispositionMatch.disposition_case_id.in_(case_ids)
                if case_ids
                else DispositionMatch.id.is_(None),
            )
        ).all()
    )
    matched_buyer_ids = {match.buyer_id for match in match_rows}
    user_ids: set[UUID | None] = {case.owner_user_id for case in cases}
    user_ids.update(owner_id for _, _, _, _, _, _, owner_id, _ in setup_intakes)
    task_rows = list(
        db.scalars(
            select(Task).where(
                Task.organization_id == principal.organization_id,
                Task.deal_id.in_(operational_deal_ids)
                if operational_deal_ids
                else Task.id.is_(None),
                Task.status.in_(("open", "in_progress")),
            )
        ).all()
    )
    tasks = [task for task in task_rows if _scoped(task.responsible_user_id, allowed_user_ids)]
    user_ids.update(task.responsible_user_id for task in tasks)

    buyer_statement = select(Buyer).where(Buyer.organization_id == principal.organization_id)
    buyers_all = list(db.scalars(buyer_statement).all())
    buyers = [
        buyer for buyer in buyers_all if _scoped(buyer.relationship_owner_user_id, allowed_user_ids)
    ]
    buyer_by_id = {buyer.id: buyer for buyer in buyers_all}
    buyer_ids = {buyer.id for buyer in buyers}
    proof_buyer_ids = buyer_ids | matched_buyer_ids
    proof_buyers = [
        buyer for buyer in buyers_all if buyer.id in proof_buyer_ids and buyer.archived_at is None
    ]
    reviewed_proof_by_buyer: dict[UUID, BuyerProofDocument] = {}
    verified_proof_by_buyer: dict[UUID, BuyerProofDocument] = {}
    if proof_buyer_ids:
        for document in db.scalars(
            select(BuyerProofDocument)
            .where(
                BuyerProofDocument.organization_id == principal.organization_id,
                BuyerProofDocument.buyer_id.in_(proof_buyer_ids),
                BuyerProofDocument.status == "verified",
                BuyerProofDocument.deleted_at.is_(None),
            )
            .order_by(
                BuyerProofDocument.verified_at.desc(),
                BuyerProofDocument.created_at.desc(),
            )
        ).all():
            reviewed_proof_by_buyer.setdefault(document.buyer_id, document)
            if document.buyer_id not in verified_proof_by_buyer and _proof_is_current_verified(
                document, now=now
            ):
                verified_proof_by_buyer[document.buyer_id] = document
    user_ids.update(buyer.relationship_owner_user_id for buyer in buyers)
    user_ids.update(buyer.relationship_owner_user_id for buyer in proof_buyers)
    user_ids.update(checklist.responsible_user_id for checklist in checklist_rows)
    user_ids.update(checkpoint.responsible_user_id for checkpoint in offer_room_checkpoints)

    followup_rows = list(
        db.scalars(
            select(BuyerEngagement).where(
                BuyerEngagement.organization_id == principal.organization_id,
                BuyerEngagement.engagement_type == "follow_up",
                BuyerEngagement.status.notin_(COMPLETE_WORK_STATUSES),
                or_(
                    BuyerEngagement.disposition_case_id.in_(case_ids)
                    if case_ids
                    else BuyerEngagement.id.is_(None),
                    and_(
                        BuyerEngagement.disposition_case_id.is_(None),
                        BuyerEngagement.buyer_id.in_(buyer_ids)
                        if buyer_ids
                        else BuyerEngagement.id.is_(None),
                    ),
                ),
            )
        ).all()
    )
    followups: list[BuyerEngagement] = []
    for followup in followup_rows:
        case = (
            case_by_id.get(followup.disposition_case_id)
            if followup.disposition_case_id is not None
            else None
        )
        buyer = buyer_by_id.get(followup.buyer_id)
        relevant_owners = {
            followup.actor_user_id,
            case.owner_user_id if case else None,
            buyer.relationship_owner_user_id if buyer else None,
        }
        if allowed_user_ids is None or any(owner in allowed_user_ids for owner in relevant_owners):
            followups.append(followup)
            user_ids.add(followup.actor_user_id)

    reply_rows: list[tuple[Conversation, ConversationContextLink, Buyer]] = []
    if PermissionKeys.VIEW_CONVERSATIONS in principal.permission_keys:
        reply_rows = list(
            db.execute(
                select(Conversation, ConversationContextLink, Buyer)
                .join(
                    ConversationContextLink,
                    ConversationContextLink.conversation_id == Conversation.id,
                )
                .join(Buyer, Buyer.id == ConversationContextLink.buyer_id)
                .where(
                    Conversation.organization_id == principal.organization_id,
                    ConversationContextLink.organization_id == principal.organization_id,
                    Buyer.organization_id == principal.organization_id,
                    Conversation.conversation_type == "buyer",
                    Conversation.status != "closed",
                    ConversationContextLink.context_type == "buyer",
                )
            )
            .tuples()
            .all()
        )
    replies: list[tuple[Conversation, Buyer]] = []
    for conversation, _, buyer in reply_rows:
        has_reply = conversation.unread_count > 0 or (
            conversation.last_inbound_at is not None
            and (
                conversation.last_outbound_at is None
                or _aware(conversation.last_inbound_at) > _aware(conversation.last_outbound_at)
            )
        )
        if not has_reply:
            continue
        if allowed_user_ids is not None and not (
            conversation.assigned_user_id in allowed_user_ids
            or buyer.relationship_owner_user_id in allowed_user_ids
        ):
            continue
        replies.append((conversation, buyer))
        user_ids.add(conversation.assigned_user_id or buyer.relationship_owner_user_id)

    offer_rows = list(
        db.scalars(
            select(BuyerOffer).where(
                BuyerOffer.organization_id == principal.organization_id,
                BuyerOffer.disposition_case_id.in_(case_ids)
                if case_ids
                else BuyerOffer.id.is_(None),
            )
        ).all()
    )
    offers = [offer for offer in offer_rows if offer.status == "received"]
    deposit_offers = [
        offer
        for offer in offer_rows
        if offer.status == "selected"
        and offer.deposit_due_at is not None
        and offer.deposit_received_at is None
    ]
    offer_by_id = {offer.id: offer for offer in offer_rows}
    active_selections = list(
        db.scalars(
            select(DispositionBuyerSelection).where(
                DispositionBuyerSelection.organization_id == principal.organization_id,
                DispositionBuyerSelection.disposition_case_id.in_(case_ids)
                if case_ids
                else DispositionBuyerSelection.id.is_(None),
                DispositionBuyerSelection.status == "active",
            )
        ).all()
    )
    active_selection_case = {
        selection.id: selection.disposition_case_id for selection in active_selections
    }
    viable_backup_case_ids: set[UUID] = set()
    if active_selection_case:
        for slot in db.scalars(
            select(DispositionBuyerSelectionSlot).where(
                DispositionBuyerSelectionSlot.selection_id.in_(active_selection_case),
                DispositionBuyerSelectionSlot.role == "backup",
            )
        ).all():
            live_offer = offer_by_id.get(slot.offer_id)
            if (
                live_offer is not None
                and live_offer.status == "backup"
                and live_offer.lock_version == int(slot.offer_snapshot.get("lock_version", 0))
            ):
                viable_backup_case_ids.add(active_selection_case[slot.selection_id])
    users = _users(db, principal.organization_id, user_ids)
    deal_by_id = {item.id: item for item in deal_overview.items}
    setup_task_by_deal = {
        task.deal_id: task
        for task in task_rows
        if task.deal_id is not None and task.task_type == HANDOFF_SETUP_TASK_TYPE
    }

    active_items: list[DispositionDeskItemRead] = []
    coverage_warnings: list[DispositionDeskItemRead] = []
    for (
        setup_transaction,
        setup_deal,
        setup_lead,
        setup_contact,
        setup_property,
        setup_existing_case,
        setup_owner_id,
        setup_blockers,
    ) in setup_intakes:
        setup_task = setup_task_by_deal.get(setup_deal.id)
        active_items.append(
            DispositionDeskItemRead(
                key=f"setup:{setup_transaction.id}",
                category="active_deals",
                title=_property_address(setup_property),
                context=f"{setup_contact.legal_name} | Executed contract",
                owner_user_id=setup_owner_id,
                owner_name=_owner_name(setup_owner_id, users),
                due_at=(
                    setup_task.due_at
                    if setup_task is not None
                    else setup_transaction.contract_executed_at
                ),
                reason=(
                    f"Executed {setup_lead.asset_class.title()} contract is waiting for "
                    "Dispositions setup."
                ),
                blocker=" ".join(setup_blockers),
                severity="danger",
                deal_id=setup_deal.id,
                transaction_id=setup_transaction.id,
                task_id=setup_task.id if setup_task is not None else None,
                disposition_case_id=(
                    setup_existing_case.id if setup_existing_case is not None else None
                ),
                needs_setup=True,
                asset_class=_asset_class(setup_lead.asset_class),
                primary_action=DispositionDeskActionRead(
                    label="Resolve setup",
                    href=f"/os/dispositions?transaction={setup_transaction.id}",
                ),
                secondary_action=DispositionDeskActionRead(
                    label="Open deal",
                    href=_deal_href(setup_deal.id),
                ),
            )
        )
    for item in active_records:
        case = case_by_deal.get(item.id)
        case_lead = db.get(Lead, case.lead_id) if case is not None else None
        case_property = db.get(Property, case.property_id) if case is not None else None
        blocker = next(
            (value.label for value in item.blockers if value.domain == "disposition"),
            None,
        )
        active_items.append(
            DispositionDeskItemRead(
                key=f"deal:{item.id}",
                category="active_deals",
                title=_property_address(case_property) if case_property else item.property_address,
                context=(
                    f"{item.seller_name} | {item.buyer_match_count} matches | "
                    f"{item.buyer_offer_count} offers"
                ),
                owner_user_id=case.owner_user_id if case else None,
                owner_name=item.disposition_owner_name or "Unassigned",
                due_at=item.next_deadline,
                reason=f"Disposition is {item.disposition_status.replace('_', ' ')}.",
                blocker=blocker,
                severity=_severity(item.next_deadline, blocker=bool(blocker)),
                deal_id=item.id,
                transaction_id=item.transaction_id,
                disposition_case_id=case.id if case else None,
                asset_class=_asset_class(case_lead.asset_class) if case_lead else None,
                primary_action=DispositionDeskActionRead(
                    label="Open deal" if case else "Open disposition",
                    href=(
                        _deal_href(item.id)
                        if case
                        else f"/os/dispositions?transaction={item.transaction_id}"
                    ),
                ),
                secondary_action=DispositionDeskActionRead(
                    label="Buyer network",
                    href="/os/buyers",
                ),
                checklist=_desk_checklist(db, principal, case) if case else None,
            )
        )
        warning = _coverage_warning(
            item,
            case,
            has_viable_approved_backup=(case is not None and case.id in viable_backup_case_ids),
        )
        if warning:
            coverage_warnings.append(warning)

    task_items: list[DispositionDeskItemRead] = []
    for task in tasks:
        deal = deal_by_id.get(task.deal_id) if task.deal_id else None
        if deal is None:
            continue
        task_items.append(
            DispositionDeskItemRead(
                key=f"task:{task.id}",
                category="today",
                title=task.title,
                context=deal.property_address,
                owner_user_id=task.responsible_user_id,
                owner_name=_owner_name(task.responsible_user_id, users),
                due_at=task.due_at,
                reason="Open deal task requires disposition attention.",
                blocker=None,
                severity=_severity(task.due_at),
                deal_id=deal.id,
                task_id=task.id,
                disposition_case_id=deal.disposition_case_id,
                primary_action=DispositionDeskActionRead(
                    label="Open task",
                    href=(
                        f"/os/tasks?view={'team' if effective_scope == 'team' else 'mine'}"
                        f"&item=task:{task.id}"
                    ),
                ),
                secondary_action=DispositionDeskActionRead(
                    label="Open deal",
                    href=_deal_href(deal.id),
                ),
            )
        )

    followup_items: list[DispositionDeskItemRead] = []
    for followup in followups:
        case = (
            case_by_id.get(followup.disposition_case_id)
            if followup.disposition_case_id is not None
            else None
        )
        deal = deal_by_id.get(case.deal_id) if case else None
        buyer = buyer_by_id.get(followup.buyer_id)
        if buyer is None or (case is not None and deal is None):
            continue
        owner_id = (
            buyer.relationship_owner_user_id
            or (case.owner_user_id if case else None)
            or followup.actor_user_id
        )
        followup_items.append(
            DispositionDeskItemRead(
                key=f"followup:{followup.id}",
                category="buyer_follow_ups",
                title=f"Follow up with {buyer.name}",
                context=(
                    deal.property_address if deal else buyer.company_name or "Buyer relationship"
                ),
                owner_user_id=owner_id,
                owner_name=_owner_name(owner_id, users),
                due_at=followup.scheduled_at,
                reason=followup.notes
                or (
                    "A buyer follow-up was scheduled for this deal."
                    if deal
                    else "A relationship follow-up was scheduled for this buyer."
                ),
                blocker=None if followup.scheduled_at else "No follow-up time was recorded.",
                severity=_severity(followup.scheduled_at, blocker=followup.scheduled_at is None),
                deal_id=deal.id if deal else None,
                buyer_id=buyer.id,
                disposition_case_id=case.id if case else None,
                primary_action=DispositionDeskActionRead(
                    label="Open buyer",
                    href=f"/os/buyers?buyer={buyer.id}&tab=summary",
                ),
                secondary_action=(
                    DispositionDeskActionRead(
                        label="Log follow-up",
                        href=_deal_href(deal.id, section="buyers"),
                    )
                    if deal
                    else None
                ),
            )
        )

    reply_items: list[DispositionDeskItemRead] = []
    for conversation, buyer in replies:
        reply_owner_id = conversation.assigned_user_id or buyer.relationship_owner_user_id
        reply_items.append(
            DispositionDeskItemRead(
                key=f"reply:{conversation.id}",
                category="replies",
                title=f"Reply to {buyer.name}",
                context=buyer.company_name or "Buyer conversation",
                owner_user_id=reply_owner_id,
                owner_name=_owner_name(reply_owner_id, users),
                due_at=conversation.last_inbound_at,
                reason=(
                    f"{conversation.unread_count} unread buyer "
                    f"message{'s' if conversation.unread_count != 1 else ''}."
                    if conversation.unread_count
                    else "The buyer replied after Stonegate's last outbound message."
                ),
                blocker=None,
                severity="danger" if conversation.unread_count else "warning",
                buyer_id=buyer.id,
                conversation_id=conversation.id,
                primary_action=DispositionDeskActionRead(
                    label="Open reply",
                    href=f"/os/inbox?conversation={conversation.id}",
                ),
                secondary_action=DispositionDeskActionRead(
                    label="Open buyer",
                    href=f"/os/buyers?buyer={buyer.id}&tab=summary",
                ),
            )
        )

    offer_items: list[DispositionDeskItemRead] = []
    for offer in offers:
        case = case_by_id.get(offer.disposition_case_id) if offer.disposition_case_id else None
        deal = deal_by_id.get(case.deal_id) if case else None
        buyer = buyer_by_id.get(offer.buyer_id)
        if case is None or deal is None or buyer is None:
            continue
        blocker = None if offer.proof_of_funds_received else "Proof of funds is not attached."
        offer_items.append(
            DispositionDeskItemRead(
                key=f"offer:{offer.id}",
                category="offers",
                title=f"Review {_money(offer.amount_cents)} offer",
                context=f"{buyer.name} | {deal.property_address}",
                owner_user_id=case.owner_user_id,
                owner_name=_owner_name(case.owner_user_id, users),
                due_at=None,
                reason="A received buyer offer is awaiting human review.",
                blocker=blocker,
                severity=_severity(None, blocker=bool(blocker)),
                deal_id=deal.id,
                buyer_id=buyer.id,
                offer_id=offer.id,
                disposition_case_id=case.id,
                primary_action=DispositionDeskActionRead(
                    label="Review offer",
                    href=_deal_href(deal.id, section="offers"),
                ),
                secondary_action=DispositionDeskActionRead(
                    label="Request POF" if blocker else "Open buyer",
                    href=(
                        _deal_href(deal.id, section="buyers")
                        if blocker
                        else f"/os/buyers?buyer={buyer.id}&tab=evidence"
                    ),
                ),
            )
        )

    deadline_items: list[DispositionDeskItemRead] = []
    canonical_transaction_deadlines = {
        (checkpoint.source_record_id, checkpoint.checkpoint_type)
        for checkpoint in offer_room_checkpoints
        if checkpoint.canonical_source == "transaction" and checkpoint.source_record_id is not None
    }
    canonical_checklist_ids = {
        checkpoint.source_record_id
        for checkpoint in offer_room_checkpoints
        if checkpoint.canonical_source == "transaction_checklist"
        and checkpoint.source_record_id is not None
    }
    canonical_offer_ids = {
        checkpoint.source_record_id
        for checkpoint in offer_room_checkpoints
        if checkpoint.canonical_source == "buyer_offer" and checkpoint.source_record_id is not None
    }
    for checkpoint in offer_room_checkpoints:
        case = case_by_id.get(checkpoint.disposition_case_id)
        deal = active_records_by_id.get(case.deal_id) if case else None
        if case is None or deal is None:
            continue
        buyer = buyer_by_id.get(checkpoint.buyer_id) if checkpoint.buyer_id else None
        checkpoint_alert = active_alert_by_checkpoint.get(checkpoint.id)
        overdue = _aware(checkpoint.due_at) < now
        blocker = None
        if checkpoint.status == "missed" or checkpoint_alert is not None:
            blocker = "Missed closing checkpoint requires action."
        elif overdue:
            blocker = "Closing checkpoint is overdue."
        checkpoint_owner_id = checkpoint.responsible_user_id or case.owner_user_id
        context = deal.property_address
        if buyer is not None:
            context = f"{buyer.name} | {context}"
        deadline_items.append(
            DispositionDeskItemRead(
                key=f"deadline:offer_room:{checkpoint.id}",
                category="deadlines",
                title=checkpoint.label,
                context=context,
                owner_user_id=checkpoint_owner_id,
                owner_name=_owner_name(checkpoint_owner_id, users),
                due_at=checkpoint.due_at,
                reason=checkpoint.notes or "An Offer Room closing checkpoint is active.",
                blocker=blocker,
                severity=(
                    "danger"
                    if checkpoint.status == "missed" or overdue
                    else "warning"
                    if checkpoint_alert is not None
                    else _severity(checkpoint.due_at)
                ),
                deal_id=deal.id,
                buyer_id=checkpoint.buyer_id,
                offer_id=checkpoint.offer_id,
                disposition_case_id=case.id,
                primary_action=DispositionDeskActionRead(
                    label="Open Offer Room",
                    href=_offer_room_href(deal.id),
                ),
                secondary_action=(
                    DispositionDeskActionRead(
                        label="Open buyer",
                        href=f"/os/buyers?buyer={buyer.id}&tab=summary",
                    )
                    if buyer is not None
                    else None
                ),
            )
        )
    for deal_record in active_records:
        transaction = transaction_by_deal.get(deal_record.id)
        case = case_by_deal.get(deal_record.id)
        if transaction is None:
            continue
        deadline_owner_id = case.owner_user_id if case else None
        values = [
            (
                "earnest_money",
                "Earnest money due",
                transaction.earnest_money_due_at,
                transaction.earnest_money_paid_at is not None,
            ),
            (
                "closing",
                "Closing date",
                transaction.closing_date,
                transaction.funded_at is not None,
            ),
        ]
        for key, title, due_at, completed in values:
            if due_at is None or completed:
                continue
            if key == "closing" and (transaction.id, "closing") in canonical_transaction_deadlines:
                continue
            deadline_items.append(
                DispositionDeskItemRead(
                    key=f"deadline:{key}:{transaction.id}",
                    category="deadlines",
                    title=title,
                    context=deal_record.property_address,
                    owner_user_id=deadline_owner_id,
                    owner_name=_owner_name(deadline_owner_id, users),
                    due_at=due_at,
                    reason="A contract or closing deadline is active.",
                    blocker="Deadline is overdue." if _aware(due_at) < now else None,
                    severity=_severity(due_at),
                    deal_id=deal_record.id,
                    disposition_case_id=case.id if case else None,
                    primary_action=DispositionDeskActionRead(
                        label="Open deal",
                        href=_deal_href(deal_record.id),
                    ),
                )
            )

        for checklist_item in checklist_by_transaction.get(transaction.id, []):
            if checklist_item.id in canonical_checklist_ids:
                continue
            checklist_owner_id = checklist_item.responsible_user_id or deadline_owner_id
            checklist_due_at = checklist_item.due_at
            deadline_items.append(
                DispositionDeskItemRead(
                    key=f"deadline:checklist:{checklist_item.id}",
                    category="deadlines",
                    title=checklist_item.title,
                    context=deal_record.property_address,
                    owner_user_id=checklist_owner_id,
                    owner_name=_owner_name(checklist_owner_id, users),
                    due_at=checklist_due_at,
                    reason=(
                        checklist_item.description or "A required closing checklist item is due."
                    ),
                    blocker=(
                        "Checklist item is overdue."
                        if checklist_due_at and _aware(checklist_due_at) < now
                        else None
                    ),
                    severity=_severity(checklist_due_at),
                    deal_id=deal_record.id,
                    disposition_case_id=case.id if case else None,
                    primary_action=DispositionDeskActionRead(
                        label="Open deadline",
                        href=(
                            f"/os/deals?view=all&display=queue&deal={deal_record.id}&tab=closing"
                        ),
                    ),
                )
            )

    for offer in deposit_offers:
        if offer.id in canonical_offer_ids:
            continue
        deposit_due_at = offer.deposit_due_at
        case = case_by_id.get(offer.disposition_case_id) if offer.disposition_case_id else None
        offer_deal = deal_by_id.get(case.deal_id) if case else None
        buyer = buyer_by_id.get(offer.buyer_id)
        if deposit_due_at is None or case is None or offer_deal is None or buyer is None:
            continue
        deadline_items.append(
            DispositionDeskItemRead(
                key=f"deadline:offer_deposit:{offer.id}",
                category="deadlines",
                title=f"{buyer.name} deposit due",
                context=offer_deal.property_address,
                owner_user_id=case.owner_user_id,
                owner_name=_owner_name(case.owner_user_id, users),
                due_at=deposit_due_at,
                reason="The buyer's earnest-money deposit has not been recorded.",
                blocker=("Buyer deposit is overdue." if _aware(deposit_due_at) < now else None),
                severity=_severity(deposit_due_at),
                deal_id=offer_deal.id,
                buyer_id=buyer.id,
                offer_id=offer.id,
                disposition_case_id=case.id,
                primary_action=DispositionDeskActionRead(
                    label="Review offer",
                    href=_deal_href(offer_deal.id, section="offers"),
                ),
                secondary_action=DispositionDeskActionRead(
                    label="Open buyer",
                    href=f"/os/buyers?buyer={buyer.id}&tab=summary",
                ),
            )
        )

    proof_window_end = now + timedelta(days=30)
    for buyer in proof_buyers:
        reviewed_proof = verified_proof_by_buyer.get(buyer.id) or reviewed_proof_by_buyer.get(
            buyer.id
        )
        proof_due_at = reviewed_proof.expires_at if reviewed_proof else None
        if proof_due_at is None or _aware(proof_due_at) > proof_window_end:
            continue
        proof_owner_id = buyer.relationship_owner_user_id
        if not _scoped(proof_owner_id, allowed_user_ids):
            proof_owner_id = None
        proof_is_overdue = _aware(proof_due_at) < now
        deadline_items.append(
            DispositionDeskItemRead(
                key=f"deadline:buyer_pof:{buyer.id}",
                category="deadlines",
                title=f"{buyer.name} proof of funds",
                context=buyer.company_name or "Buyer network",
                owner_user_id=proof_owner_id,
                owner_name=_owner_name(proof_owner_id, users),
                due_at=proof_due_at,
                reason=(
                    "Proof of funds has expired."
                    if proof_is_overdue
                    else "Proof of funds expires within 30 days."
                ),
                blocker=(
                    "Proof of funds is expired; refreshing it is recommended."
                    if proof_is_overdue
                    else None
                ),
                severity="danger" if proof_is_overdue else "warning",
                buyer_id=buyer.id,
                primary_action=DispositionDeskActionRead(
                    label="Open buyer",
                    href=f"/os/buyers?buyer={buyer.id}&tab=evidence",
                ),
            )
        )

    criteria_buyer_ids = set(
        db.scalars(
            select(BuyerBuyBox.buyer_id)
            .join(
                BuyerBuyBoxVersion,
                BuyerBuyBoxVersion.buy_box_id == BuyerBuyBox.id,
            )
            .where(
                BuyerBuyBox.organization_id == principal.organization_id,
                BuyerBuyBox.buyer_id.in_(buyer_ids) if buyer_ids else BuyerBuyBox.id.is_(None),
                BuyerBuyBoxVersion.organization_id == principal.organization_id,
                BuyerBuyBoxVersion.is_current.is_(True),
                BuyerBuyBoxVersion.verification_status == "verified",
            )
        ).all()
    )
    active_buyers = [
        buyer for buyer in buyers if buyer.archived_at is None and buyer.status == "active"
    ]
    active_buyer_ids = {buyer.id for buyer in active_buyers}
    missing_proof = len(active_buyer_ids - set(verified_proof_by_buyer))
    expiring_proof = sum(
        bool(document.expires_at and now <= _aware(document.expires_at) <= now + timedelta(days=30))
        for buyer_id, document in verified_proof_by_buyer.items()
        if buyer_id in active_buyer_ids
    )
    buyer_health = DispositionDeskBuyerHealthRead(
        total=len(buyers),
        active=len(active_buyers),
        needs_review=sum(
            buyer.archived_at is None and buyer.status == "needs_review" for buyer in buyers
        ),
        unassigned=sum(
            buyer.relationship_owner_user_id is None
            for buyer in buyers
            if buyer.archived_at is None
        ),
        missing_proof=missing_proof,
        expiring_proof=expiring_proof,
        missing_criteria=sum(buyer.id not in criteria_buyer_ids for buyer in active_buyers),
    )

    active_items_all = _sort(active_items)
    followup_items_all = _sort(followup_items)
    reply_items_all = _sort(reply_items)
    offer_items_all = _sort(offer_items)
    deadline_items_all = _sort(deadline_items)
    coverage_warnings_all = _sort(coverage_warnings)
    today_items_all = _today(
        [
            *task_items,
            *followup_items_all,
            *reply_items_all,
            *offer_items_all,
            *deadline_items_all,
            *coverage_warnings_all,
        ],
        day_end,
    )
    metrics = DispositionDeskMetricsRead(
        today=len(today_items_all),
        active_deals=len(active_items_all),
        buyer_follow_ups=len(followup_items_all),
        replies=len(reply_items_all),
        offers=len(offer_items_all),
        deadlines=len(deadline_items_all),
        weak_coverage=len(coverage_warnings_all),
    )

    def section_offset(section: DispositionDeskCategory) -> int:
        return offset if selected_section == section else 0

    today_items, today_section = _page(today_items_all, offset=section_offset("today"))
    active_items, active_deals_section = _page(
        active_items_all,
        offset=section_offset("active_deals"),
    )
    followup_items, buyer_follow_ups_section = _page(
        followup_items_all,
        offset=section_offset("buyer_follow_ups"),
    )
    reply_items, replies_section = _page(
        reply_items_all,
        offset=section_offset("replies"),
    )
    offer_items, offers_section = _page(
        offer_items_all,
        offset=section_offset("offers"),
    )
    deadline_items, deadlines_section = _page(
        deadline_items_all,
        offset=section_offset("deadlines"),
    )
    coverage_warnings, coverage_warnings_section = _page(coverage_warnings_all)
    deal_records, deal_records_section = _page(active_records)
    sections = DispositionDeskSectionsRead(
        today=today_section,
        active_deals=active_deals_section,
        buyer_follow_ups=buyer_follow_ups_section,
        replies=replies_section,
        offers=offers_section,
        deadlines=deadlines_section,
        coverage_warnings=coverage_warnings_section,
        deal_records=deal_records_section,
    )

    provider = buyer_discovery.provider_status()
    provider_state: Literal[
        "not_configured",
        "configured_unverified",
        "available",
        "unavailable",
    ]
    if not provider.configured:
        provider_state = "not_configured"
        provider_message = provider.message
    else:
        latest_provider_run = db.scalar(
            select(BuyerDiscoveryRun)
            .where(
                BuyerDiscoveryRun.organization_id == principal.organization_id,
                BuyerDiscoveryRun.provider == provider.provider,
            )
            .order_by(BuyerDiscoveryRun.created_at.desc())
            .limit(1)
        )
        if latest_provider_run is None or latest_provider_run.status == "running":
            provider_state = "configured_unverified"
            provider_message = (
                "The external buyer-data provider is configured but has not been verified "
                "by a completed discovery run."
            )
        elif latest_provider_run.status == "failed":
            provider_state = "unavailable"
            provider_message = (
                latest_provider_run.error_message
                or "The most recent external buyer-data discovery run failed."
            )
        else:
            provider_state = "available"
            provider_message = "The most recent external buyer-data discovery run completed."
    provider_message = f"{provider_message} Stonegate's owned buyer network remains available."
    return DispositionDeskRead(
        requested_scope=requested_scope,
        effective_scope=effective_scope,
        scope_label=scope_label,
        scope_member_count=member_count,
        can_view_team=can_view_team,
        scope_notice=scope_notice,
        can_edit_buyers=PermissionKeys.EDIT_BUYERS in principal.permission_keys,
        metrics=metrics,
        sections=sections,
        buyer_network=buyer_health,
        today=today_items,
        active_deals=active_items,
        buyer_follow_ups=followup_items,
        replies=reply_items,
        offers=offer_items,
        deadlines=deadline_items,
        coverage_warnings=coverage_warnings,
        deal_records=deal_records,
        source_health=DispositionDeskSourceHealthRead(
            generated_at=now,
            external_provider_status=provider_state,
            message=provider_message,
        ),
    )
