from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.auth import Principal
from app.domain.assets import normalize_asset_class, property_identity_label
from app.domain.rbac import PermissionKeys
from app.models.foundation import (
    Buyer,
    BuyerOffer,
    Contact,
    ContractPackage,
    Deal,
    DealReconciliation,
    DispositionCase,
    DispositionMatch,
    Lead,
    Property,
    Task,
    Transaction,
    TransactionChecklistItem,
    TransactionDocument,
    User,
)
from app.schemas.deals import (
    DealBlockerRead,
    DealDetailRead,
    DealMetricsRead,
    DealNextActionRead,
    DealOverviewRead,
    DealQueueItemRead,
)
from app.schemas.tasks import PrimaryNextActionRead
from app.services.tasks import OPEN_TASK_STATUSES, get_due_status, get_primary_next_action

COMPLETED_TRANSACTION_STATUSES = {"funded", "closed", "cancelled"}


@dataclass(frozen=True)
class _DealOverviewContext:
    leads: dict[UUID, Lead]
    contacts: dict[UUID, Contact]
    properties: dict[UUID, Property]
    packages: dict[UUID, ContractPackage]
    cases: dict[UUID, DispositionCase]
    reconciliations: dict[UUID, DealReconciliation]
    checklists: dict[UUID, list[TransactionChecklistItem]]
    document_counts: dict[UUID, int]
    match_counts: dict[UUID, int]
    offer_counts: dict[UUID, int]
    buyers: dict[UUID, Buyer]
    users: dict[UUID, User]
    primary_actions: dict[UUID, PrimaryNextActionRead]


def _utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def _address(property_record: Property | None) -> str:
    if property_record is None:
        return "Unknown property"
    return property_identity_label(
        street_address=property_record.street_address,
        city=property_record.city,
        state=property_record.state,
        postal_code=property_record.postal_code,
        parcel_id=property_record.parcel_id,
        county=property_record.county,
    ) or "Unknown property"


def _contract_status(transaction: Transaction, package: ContractPackage | None) -> str:
    if transaction.cancelled_at or transaction.status == "cancelled":
        return "cancelled"
    if transaction.contract_executed_at or transaction.status in {
        "executed",
        "closing",
        "funded",
        "closed",
    }:
        return "executed"
    if transaction.contract_sent_at or package and package.sent_at:
        return "awaiting_signature"
    if transaction.status == "approval_pending" or package and package.status == "approval_pending":
        return "approval_pending"
    return "preparing"


def _closing_status(transaction: Transaction) -> str:
    if transaction.cancelled_at or transaction.status == "cancelled":
        return "cancelled"
    if transaction.funded_at or transaction.status in {"funded", "closed"}:
        return "funded"
    if transaction.status == "closing":
        return "in_closing"
    if transaction.contract_executed_at or transaction.status == "executed":
        return "not_started" if transaction.title_opened_at is None else "in_closing"
    return "waiting_for_contract"


def _disposition_status(transaction: Transaction, case: DispositionCase | None) -> str:
    if transaction.cancelled_at or transaction.status == "cancelled":
        return "cancelled"
    if case is None:
        return (
            "ready_to_open"
            if transaction.status in {"executed", "closing", "funded", "closed"}
            else "waiting_for_contract"
        )
    return case.status


def _finance_status(
    transaction: Transaction,
    case: DispositionCase | None,
    reconciliation: DealReconciliation | None,
) -> str:
    if transaction.cancelled_at or transaction.status == "cancelled":
        return "not_applicable"
    if reconciliation is not None:
        return reconciliation.status
    if case and case.selected_buyer_id:
        return "ready_for_reconciliation"
    if transaction.funded_at or transaction.status in {"funded", "closed"}:
        return "reconciliation_required"
    return "waiting_for_outcome"


def _next_deadline(
    transaction: Transaction, checklist: list[TransactionChecklistItem]
) -> datetime | None:
    deadlines = [
        value
        for value in (
            transaction.earnest_money_due_at,
            transaction.due_diligence_deadline,
            transaction.assignment_deadline,
            transaction.closing_date,
            *(
                item.due_at
                for item in checklist
                if item.status not in {"complete", "not_applicable"}
            ),
        )
        if value is not None
    ]
    return min(deadlines, key=_utc) if deadlines else None


def _blockers(
    transaction: Transaction,
    package: ContractPackage | None,
    case: DispositionCase | None,
    reconciliation: DealReconciliation | None,
    checklist: list[TransactionChecklistItem],
    match_count: int,
    offer_count: int,
) -> list[DealBlockerRead]:
    if transaction.status in COMPLETED_TRANSACTION_STATUSES:
        return []
    now = datetime.now(UTC)
    result: list[DealBlockerRead] = []
    contract = _contract_status(transaction, package)
    if contract in {"preparing", "approval_pending", "awaiting_signature"}:
        labels = {
            "preparing": "Contract package is not ready",
            "approval_pending": "Contract approval is pending",
            "awaiting_signature": "Seller signature is pending",
        }
        result.append(
            DealBlockerRead(
                key=contract,
                domain="contract",
                label=labels[contract],
                severity="warning",
            )
        )
    overdue = [
        item
        for item in checklist
        if item.due_at
        and _utc(item.due_at) < now
        and item.status not in {"complete", "not_applicable"}
    ]
    if overdue:
        result.append(
            DealBlockerRead(
                key="overdue_checklist",
                domain="closing",
                label=(f"{len(overdue)} closing item{'s' if len(overdue) != 1 else ''} overdue"),
                severity="danger",
            )
        )
    if transaction.contract_executed_at and transaction.coordinator_user_id is None:
        result.append(
            DealBlockerRead(
                key="coordinator_unassigned",
                domain="closing",
                label="Closing coordinator is unassigned",
                severity="warning",
            )
        )
    if case is None and transaction.status in {"executed", "closing"}:
        result.append(
            DealBlockerRead(
                key="disposition_not_open",
                domain="disposition",
                label="Disposition case has not been opened",
                severity="warning",
            )
        )
    elif case is not None:
        if case.package_status != "approved":
            result.append(
                DealBlockerRead(
                    key="package_pending",
                    domain="disposition",
                    label="Investor package needs approval",
                    severity="warning",
                )
            )
        elif match_count == 0:
            result.append(
                DealBlockerRead(
                    key="buyers_unmatched",
                    domain="disposition",
                    label="Buyer ranking has not been generated",
                    severity="warning",
                )
            )
        elif offer_count == 0:
            result.append(
                DealBlockerRead(
                    key="offers_missing",
                    domain="disposition",
                    label="No buyer offers recorded",
                    severity="warning",
                )
            )
        elif case.selected_buyer_id is None:
            result.append(
                DealBlockerRead(
                    key="buyer_unselected",
                    domain="disposition",
                    label="Buyer selection is pending",
                    severity="warning",
                )
            )
    if (
        case
        and case.selected_buyer_id
        and (reconciliation is None or reconciliation.status != "approved")
    ):
        result.append(
            DealBlockerRead(
                key="reconciliation_pending",
                domain="finance",
                label="Deal reconciliation needs review",
                severity="warning",
            )
        )
    return result


def _build_item(
    db: Session,
    principal: Principal,
    deal: Deal,
    transaction: Transaction,
    *,
    can_view_economics: bool,
    context: _DealOverviewContext | None = None,
) -> DealQueueItemRead:
    lead = context.leads.get(transaction.lead_id) if context else db.get(Lead, transaction.lead_id)
    contact = (
        context.contacts.get(transaction.contact_id)
        if context
        else db.get(Contact, transaction.contact_id)
    )
    property_record = (
        context.properties.get(transaction.property_id)
        if context
        else db.get(Property, transaction.property_id)
    )
    package = context.packages.get(transaction.id) if context else db.scalar(
        select(ContractPackage)
        .where(ContractPackage.transaction_id == transaction.id)
        .order_by(ContractPackage.version_number.desc())
        .limit(1)
    )
    case = context.cases.get(transaction.id) if context else db.scalar(
        select(DispositionCase).where(DispositionCase.transaction_id == transaction.id)
    )
    reconciliation = context.reconciliations.get(transaction.id) if context else db.scalar(
        select(DealReconciliation).where(DealReconciliation.transaction_id == transaction.id)
    )
    checklist = context.checklists.get(transaction.id, []) if context else list(
        db.scalars(
            select(TransactionChecklistItem).where(
                TransactionChecklistItem.transaction_id == transaction.id
            )
        ).all()
    )
    document_count = context.document_counts.get(transaction.id, 0) if context else (
        db.scalar(
            select(func.count(TransactionDocument.id)).where(
                TransactionDocument.transaction_id == transaction.id,
                TransactionDocument.deleted_at.is_(None),
            )
        )
        or 0
    )
    match_count = 0
    offer_count = 0
    selected_buyer = None
    disposition_owner = None
    if case is not None:
        match_count = context.match_counts.get(case.id, 0) if context else (
            db.scalar(
                select(func.count(DispositionMatch.id)).where(
                    DispositionMatch.disposition_case_id == case.id
                )
            )
            or 0
        )
        offer_count = context.offer_counts.get(case.id, 0) if context else (
            db.scalar(
                select(func.count(BuyerOffer.id)).where(BuyerOffer.disposition_case_id == case.id)
            )
            or 0
        )
        selected_buyer = (
            context.buyers.get(case.selected_buyer_id) if context and case.selected_buyer_id
            else db.get(Buyer, case.selected_buyer_id) if case.selected_buyer_id
            else None
        )
        disposition_owner = (
            context.users.get(case.owner_user_id)
            if context and case.owner_user_id
            else db.get(User, case.owner_user_id)
        )
    owner = (
        context.users.get(transaction.owner_user_id)
        if context and transaction.owner_user_id
        else db.get(User, transaction.owner_user_id) if transaction.owner_user_id
        else None
    )
    coordinator = (
        context.users.get(transaction.coordinator_user_id)
        if context and transaction.coordinator_user_id
        else db.get(User, transaction.coordinator_user_id)
        if transaction.coordinator_user_id
        else None
    )
    required = [item for item in checklist if item.is_required]
    complete = sum(item.status in {"complete", "not_applicable"} for item in required)
    primary = context.primary_actions.get(deal.id) if context else get_primary_next_action(
        db, organization_id=principal.organization_id, deal_id=deal.id
    )
    blockers = _blockers(
        transaction,
        package,
        case,
        reconciliation,
        checklist,
        match_count,
        offer_count,
    )
    return DealQueueItemRead(
        id=deal.id,
        lead_id=transaction.lead_id,
        asset_class=normalize_asset_class(lead.asset_class if lead else None),
        transaction_id=transaction.id,
        disposition_case_id=case.id if case else None,
        seller_name=contact.legal_name if contact else "Unknown seller",
        property_address=_address(property_record),
        property_type=property_record.property_type if property_record else None,
        stage_key=deal.stage_key or (lead.stage_key if lead else "deal"),
        contract_status=_contract_status(transaction, package),
        closing_status=_closing_status(transaction),
        disposition_status=_disposition_status(transaction, case),
        finance_status=_finance_status(transaction, case, reconciliation),
        owner_name=owner.display_name if owner else None,
        coordinator_name=coordinator.display_name if coordinator else None,
        disposition_owner_name=disposition_owner.display_name if disposition_owner else None,
        closing_date=transaction.closing_date,
        next_deadline=_next_deadline(transaction, checklist),
        checklist_complete=complete,
        checklist_total=len(required),
        document_count=int(document_count),
        buyer_match_count=int(match_count),
        buyer_offer_count=int(offer_count),
        selected_buyer_name=selected_buyer.name if selected_buyer else None,
        contract_price_cents=transaction.purchase_price_cents,
        assignment_fee_cents=transaction.assignment_fee_cents if can_view_economics else None,
        company_profit_cents=(
            reconciliation.company_profit_cents if can_view_economics and reconciliation else None
        ),
        company_margin_basis_points=(
            reconciliation.company_margin_basis_points
            if can_view_economics and reconciliation
            else None
        ),
        primary_next_action=DealNextActionRead(**primary.model_dump()) if primary else None,
        blockers=blockers,
        created_at=deal.created_at,
    )


def _overview_context(
    db: Session,
    principal: Principal,
    rows: list[tuple[Deal, Transaction]],
) -> _DealOverviewContext:
    transactions = [transaction for _, transaction in rows]
    transaction_ids = {transaction.id for transaction in transactions}
    deal_ids = {deal.id for deal, _ in rows}
    lead_ids = {transaction.lead_id for transaction in transactions}
    contact_ids = {transaction.contact_id for transaction in transactions}
    property_ids = {transaction.property_id for transaction in transactions}

    leads = {
        item.id: item
        for item in db.scalars(
            select(Lead).where(
                Lead.organization_id == principal.organization_id,
                Lead.id.in_(lead_ids),
            )
        ).all()
    } if lead_ids else {}
    contacts = {
        item.id: item
        for item in db.scalars(
            select(Contact).where(
                Contact.organization_id == principal.organization_id,
                Contact.id.in_(contact_ids),
            )
        ).all()
    } if contact_ids else {}
    properties = {
        item.id: item
        for item in db.scalars(
            select(Property).where(
                Property.organization_id == principal.organization_id,
                Property.id.in_(property_ids),
            )
        ).all()
    } if property_ids else {}

    package_rows = list(
        db.scalars(
            select(ContractPackage)
            .where(ContractPackage.transaction_id.in_(transaction_ids))
            .order_by(
                ContractPackage.transaction_id,
                ContractPackage.version_number.desc(),
                ContractPackage.created_at.desc(),
            )
        ).all()
    ) if transaction_ids else []
    packages: dict[UUID, ContractPackage] = {}
    for package in package_rows:
        packages.setdefault(package.transaction_id, package)

    case_rows = list(
        db.scalars(
            select(DispositionCase).where(
                DispositionCase.organization_id == principal.organization_id,
                DispositionCase.transaction_id.in_(transaction_ids),
            )
        ).all()
    ) if transaction_ids else []
    cases = {item.transaction_id: item for item in case_rows}
    case_ids = {item.id for item in case_rows}
    reconciliations = {
        item.transaction_id: item
        for item in db.scalars(
            select(DealReconciliation).where(
                DealReconciliation.organization_id == principal.organization_id,
                DealReconciliation.transaction_id.in_(transaction_ids),
            )
        ).all()
    } if transaction_ids else {}

    checklist_rows = list(
        db.scalars(
            select(TransactionChecklistItem).where(
                TransactionChecklistItem.organization_id == principal.organization_id,
                TransactionChecklistItem.transaction_id.in_(transaction_ids),
            )
        ).all()
    ) if transaction_ids else []
    checklists: dict[UUID, list[TransactionChecklistItem]] = {}
    for item in checklist_rows:
        checklists.setdefault(item.transaction_id, []).append(item)

    document_counts = {
        transaction_id: int(count)
        for transaction_id, count in db.execute(
            select(TransactionDocument.transaction_id, func.count(TransactionDocument.id))
            .where(
                TransactionDocument.transaction_id.in_(transaction_ids),
                TransactionDocument.deleted_at.is_(None),
            )
            .group_by(TransactionDocument.transaction_id)
        ).all()
    } if transaction_ids else {}
    match_counts = {
        disposition_case_id: int(count)
        for disposition_case_id, count in db.execute(
            select(DispositionMatch.disposition_case_id, func.count(DispositionMatch.id))
            .where(DispositionMatch.disposition_case_id.in_(case_ids))
            .group_by(DispositionMatch.disposition_case_id)
        ).all()
    } if case_ids else {}
    offer_counts = {
        disposition_case_id: int(count)
        for disposition_case_id, count in db.execute(
            select(BuyerOffer.disposition_case_id, func.count(BuyerOffer.id))
            .where(BuyerOffer.disposition_case_id.in_(case_ids))
            .group_by(BuyerOffer.disposition_case_id)
        ).all()
    } if case_ids else {}

    primary_task_rows = list(
        db.scalars(
            select(Task)
            .where(
                Task.organization_id == principal.organization_id,
                Task.deal_id.in_(deal_ids),
                Task.work_kind == "primary_next_action",
                Task.status.in_(OPEN_TASK_STATUSES),
            )
            .order_by(Task.created_at.desc())
        ).all()
    ) if deal_ids else []
    primary_task_by_deal: dict[UUID, Task] = {}
    for task in primary_task_rows:
        if task.deal_id is not None:
            primary_task_by_deal.setdefault(task.deal_id, task)

    user_ids = {
        user_id
        for user_id in (
            *(transaction.owner_user_id for transaction in transactions),
            *(transaction.coordinator_user_id for transaction in transactions),
            *(case.owner_user_id for case in case_rows),
            *(task.responsible_user_id for task in primary_task_by_deal.values()),
        )
        if user_id is not None
    }
    users = {
        item.id: item
        for item in db.scalars(
            select(User).where(
                User.organization_id == principal.organization_id,
                User.id.in_(user_ids),
            )
        ).all()
    } if user_ids else {}
    selected_buyer_ids = {
        case.selected_buyer_id for case in case_rows if case.selected_buyer_id is not None
    }
    buyers = {
        item.id: item
        for item in db.scalars(
            select(Buyer).where(
                Buyer.organization_id == principal.organization_id,
                Buyer.id.in_(selected_buyer_ids),
            )
        ).all()
    } if selected_buyer_ids else {}
    now = datetime.now(UTC)
    primary_actions = {
        deal_id: PrimaryNextActionRead(
            task_id=task.id,
            title=task.title,
            action_type=task.task_type,
            due_at=task.due_at,
            responsible_user_id=task.responsible_user_id,
            responsible_user_email=(
                users[task.responsible_user_id].email
                if task.responsible_user_id in users
                else None
            ),
            due_status=get_due_status(task, now),
        )
        for deal_id, task in primary_task_by_deal.items()
    }
    return _DealOverviewContext(
        leads=leads,
        contacts=contacts,
        properties=properties,
        packages=packages,
        cases=cases,
        reconciliations=reconciliations,
        checklists=checklists,
        document_counts=document_counts,
        match_counts=match_counts,
        offer_counts=offer_counts,
        buyers=buyers,
        users=users,
        primary_actions=primary_actions,
    )


def overview(
    db: Session,
    principal: Principal,
    *,
    deal_ids: set[UUID] | None = None,
) -> DealOverviewRead:
    can_view_economics = bool(
        {PermissionKeys.VIEW_FINANCIALS, PermissionKeys.VIEW_COMPENSATION}
        & principal.permission_keys
    )
    statement = (
        select(Deal, Transaction)
        .join(Transaction, Transaction.deal_id == Deal.id)
        .where(Deal.organization_id == principal.organization_id)
        .order_by(Transaction.closing_date.asc().nullslast(), Deal.created_at.desc())
    )
    if deal_ids is not None:
        statement = statement.where(
            Deal.id.in_(deal_ids) if deal_ids else Deal.id.is_(None)
        )
    rows = list(db.execute(statement).tuples().all())
    context = _overview_context(db, principal, rows)
    items = [
        _build_item(
            db,
            principal,
            deal,
            transaction,
            can_view_economics=can_view_economics,
            context=context,
        )
        for deal, transaction in rows
    ]
    active = [item for item in items if item.closing_status not in {"funded", "cancelled"}]
    return DealOverviewRead(
        can_view_economics=can_view_economics,
        metrics=DealMetricsRead(
            active=len(active),
            closing_exceptions=sum(
                any(blocker.domain == "closing" for blocker in item.blockers) for item in active
            ),
            ready_for_disposition=sum(
                item.disposition_status == "ready_to_open" for item in active
            ),
            buyer_needed=sum(
                item.disposition_status in {"buyer_matching", "marketing", "offer_review"}
                and item.selected_buyer_name is None
                for item in active
            ),
            finance_review=sum(
                item.finance_status
                in {"draft", "ready_for_reconciliation", "reconciliation_required"}
                for item in items
            ),
            completed=sum(item.closing_status in {"funded", "cancelled"} for item in items),
        ),
        items=items,
    )


def detail(db: Session, principal: Principal, deal_id: UUID) -> DealDetailRead | None:
    row = db.execute(
        select(Deal, Transaction)
        .join(Transaction, Transaction.deal_id == Deal.id)
        .where(Deal.organization_id == principal.organization_id, Deal.id == deal_id)
    ).first()
    if row is None:
        return None
    can_view_economics = bool(
        {PermissionKeys.VIEW_FINANCIALS, PermissionKeys.VIEW_COMPENSATION}
        & principal.permission_keys
    )
    item = _build_item(db, principal, row[0], row[1], can_view_economics=can_view_economics)
    return DealDetailRead(**item.model_dump(), can_view_economics=can_view_economics)
