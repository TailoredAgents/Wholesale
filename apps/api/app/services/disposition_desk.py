from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Literal
from uuid import UUID
from zoneinfo import ZoneInfo

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.core.auth import Principal
from app.domain.rbac import PermissionKeys
from app.models.foundation import (
    Buyer,
    BuyerCriteria,
    BuyerDiscoveryRun,
    BuyerEngagement,
    BuyerOffer,
    Conversation,
    ConversationContextLink,
    DispositionCase,
    DispositionMatch,
    Role,
    RoleAssignment,
    Task,
    Team,
    TeamMembership,
    Transaction,
    TransactionChecklistItem,
    User,
)
from app.schemas.deals import DealQueueItemRead
from app.schemas.disposition_desk import (
    DispositionDeskActionRead,
    DispositionDeskBuyerHealthRead,
    DispositionDeskCategory,
    DispositionDeskItemRead,
    DispositionDeskMetricsRead,
    DispositionDeskRead,
    DispositionDeskScope,
    DispositionDeskSectionsRead,
    DispositionDeskSectionStatusRead,
    DispositionDeskSourceHealthRead,
)
from app.services import buyer_discovery, deals

ACTIVE_CASE_STATUSES = {
    "package_prep",
    "buyer_matching",
    "marketed",
    "offers_received",
    "buyer_selected",
}
COMPLETE_WORK_STATUSES = {"complete", "completed", "cancelled", "canceled", "not_applicable"}
EXECUTIVE_ROLE_KEYS = {"owner", "founder_operator", "ceo"}
EASTERN = ZoneInfo("America/New_York")
MAX_SECTION_ITEMS = 100
DispositionDeskSeverity = Literal["info", "warning", "danger"]


def _aware(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def _money(cents: int) -> str:
    return f"${cents / 100:,.0f}"


def _role_keys(db: Session, principal: Principal) -> set[str]:
    return set(
        db.scalars(
            select(Role.key)
            .join(RoleAssignment, RoleAssignment.role_id == Role.id)
            .where(
                RoleAssignment.organization_id == principal.organization_id,
                RoleAssignment.user_id == principal.user_id,
            )
        ).all()
    )


def _team_scope(
    db: Session,
    principal: Principal,
    requested_scope: DispositionDeskScope,
) -> tuple[DispositionDeskScope, set[UUID] | None, str, int, bool, str | None]:
    roles = _role_keys(db, principal)
    can_view_team = PermissionKeys.EXPORT_BUYERS in principal.permission_keys
    if requested_scope == "mine":
        user = db.get(User, principal.user_id)
        return (
            "mine",
            {principal.user_id},
            user.display_name if user else "My work",
            1,
            can_view_team,
            None,
        )
    if not can_view_team:
        raise PermissionError("Team disposition scope requires disposition manager access.")

    if roles & EXECUTIVE_ROLE_KEYS:
        active_count = len(
            db.scalars(
                select(User.id).where(
                    User.organization_id == principal.organization_id,
                    User.is_active.is_(True),
                )
            ).all()
        )
        return "team", None, "Organization", active_count, True, None

    membership_team_ids = select(TeamMembership.team_id).where(
        TeamMembership.organization_id == principal.organization_id,
        TeamMembership.user_id == principal.user_id,
    )
    teams = list(
        db.scalars(
            select(Team).where(
                Team.organization_id == principal.organization_id,
                Team.team_type == "dispositions",
                Team.is_active.is_(True),
                or_(
                    Team.manager_user_id == principal.user_id,
                    Team.id.in_(membership_team_ids),
                ),
            )
        ).all()
    )
    team_ids = [team.id for team in teams]
    member_ids = {principal.user_id}
    if team_ids:
        member_ids.update(
            db.scalars(
                select(TeamMembership.user_id)
                .join(User, User.id == TeamMembership.user_id)
                .where(
                    TeamMembership.organization_id == principal.organization_id,
                    TeamMembership.team_id.in_(team_ids),
                    User.organization_id == principal.organization_id,
                    User.is_active.is_(True),
                )
            ).all()
        )
        member_ids.update(team.manager_user_id for team in teams if team.manager_user_id)
    notice = "Unassigned records are excluded from this team view."
    if not teams:
        notice = (
            "No active Dispositions team is connected, so Team currently shows only your work. "
            "Unassigned records are excluded."
        )
    label = ", ".join(team.name for team in teams) if teams else "My work"
    return "team", member_ids, label, len(member_ids), True, notice


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
    elif item.selected_buyer_name and case.backup_buyer_id is None:
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
    if PermissionKeys.VIEW_BUYERS not in principal.permission_keys:
        raise PermissionError("The Disposition Desk requires buyer-network access.")

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
    cases = [case for case in case_rows if _scoped(case.owner_user_id, allowed_user_ids)]
    case_by_deal = {case.deal_id: case for case in cases}
    case_by_id = {case.id: case for case in cases}
    case_ids = {case.id for case in cases}

    deal_overview = deals.overview(db, principal, deal_ids=set(case_by_deal))
    active_records_by_id: dict[UUID, DealQueueItemRead] = {}
    for item in deal_overview.items:
        if item.closing_status not in {"funded", "cancelled"} and item.id in case_by_deal:
            active_records_by_id.setdefault(item.id, item)
    active_records = list(active_records_by_id.values())
    active_deal_ids = {item.id for item in active_records}

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
    task_rows = list(
        db.scalars(
            select(Task).where(
                Task.organization_id == principal.organization_id,
                Task.deal_id.in_(active_deal_ids) if active_deal_ids else Task.id.is_(None),
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
    user_ids.update(buyer.relationship_owner_user_id for buyer in buyers)
    user_ids.update(buyer.relationship_owner_user_id for buyer in proof_buyers)
    user_ids.update(checklist.responsible_user_id for checklist in checklist_rows)

    followup_rows = list(
        db.scalars(
            select(BuyerEngagement).where(
                BuyerEngagement.organization_id == principal.organization_id,
                BuyerEngagement.engagement_type == "follow_up",
                BuyerEngagement.status.notin_(COMPLETE_WORK_STATUSES),
                BuyerEngagement.disposition_case_id.in_(case_ids)
                if case_ids
                else BuyerEngagement.id.is_(None),
            )
        ).all()
    )
    followups: list[BuyerEngagement] = []
    for followup in followup_rows:
        case = case_by_id.get(followup.disposition_case_id)
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
    users = _users(db, principal.organization_id, user_ids)
    deal_by_id = {item.id: item for item in active_records}

    active_items: list[DispositionDeskItemRead] = []
    coverage_warnings: list[DispositionDeskItemRead] = []
    for item in active_records:
        case = case_by_deal.get(item.id)
        blocker = next(
            (value.label for value in item.blockers if value.domain == "disposition"),
            None,
        )
        active_items.append(
            DispositionDeskItemRead(
                key=f"deal:{item.id}",
                category="active_deals",
                title=item.property_address,
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
                disposition_case_id=case.id if case else None,
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
            )
        )
        warning = _coverage_warning(item, case)
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
        case = next(value for value in cases if value.id == followup.disposition_case_id)
        deal = deal_by_id.get(case.deal_id)
        buyer = buyer_by_id.get(followup.buyer_id)
        if deal is None or buyer is None:
            continue
        owner_id = buyer.relationship_owner_user_id or case.owner_user_id or followup.actor_user_id
        followup_items.append(
            DispositionDeskItemRead(
                key=f"followup:{followup.id}",
                category="buyer_follow_ups",
                title=f"Follow up with {buyer.name}",
                context=deal.property_address,
                owner_user_id=owner_id,
                owner_name=_owner_name(owner_id, users),
                due_at=followup.scheduled_at,
                reason=followup.notes or "A buyer follow-up was scheduled for this deal.",
                blocker=None if followup.scheduled_at else "No follow-up time was recorded.",
                severity=_severity(followup.scheduled_at, blocker=followup.scheduled_at is None),
                deal_id=deal.id,
                buyer_id=buyer.id,
                disposition_case_id=case.id,
                primary_action=DispositionDeskActionRead(
                    label="Open buyer",
                    href=f"/os/buyers?buyer={buyer.id}&tab=summary",
                ),
                secondary_action=DispositionDeskActionRead(
                    label="Log follow-up",
                    href=_deal_href(deal.id, section="buyers"),
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
        proof_due_at = buyer.proof_of_funds_expires_at
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
                blocker="Current proof of funds is required." if proof_is_overdue else None,
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
            select(BuyerCriteria.buyer_id).where(
                BuyerCriteria.organization_id == principal.organization_id,
                BuyerCriteria.buyer_id.in_(buyer_ids) if buyer_ids else BuyerCriteria.id.is_(None),
                BuyerCriteria.is_current.is_(True),
            )
        ).all()
    )
    active_buyers = [
        buyer for buyer in buyers if buyer.archived_at is None and buyer.status == "active"
    ]
    current_proof = {"received", "verified"}
    missing_proof = sum(
        buyer.proof_of_funds_status not in current_proof
        or bool(buyer.proof_of_funds_expires_at and _aware(buyer.proof_of_funds_expires_at) < now)
        for buyer in active_buyers
    )
    expiring_proof = sum(
        bool(
            buyer.proof_of_funds_expires_at
            and now <= _aware(buyer.proof_of_funds_expires_at) <= now + timedelta(days=30)
        )
        for buyer in active_buyers
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
