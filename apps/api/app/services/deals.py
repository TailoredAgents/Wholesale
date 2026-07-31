from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.auth import Principal
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
from app.services.tasks import get_primary_next_action

COMPLETED_TRANSACTION_STATUSES = {"funded", "closed", "cancelled"}


def _utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def _address(property_record: Property | None) -> str:
    if property_record is None:
        return "Unknown property"
    return (
        f"{property_record.street_address}, {property_record.city}, "
        f"{property_record.state} {property_record.postal_code}"
    )


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
        item for item in checklist
        if item.due_at
        and _utc(item.due_at) < now
        and item.status not in {"complete", "not_applicable"}
    ]
    if overdue:
        result.append(
            DealBlockerRead(
                key="overdue_checklist",
                domain="closing",
                label=(
                    f"{len(overdue)} closing item"
                    f"{'s' if len(overdue) != 1 else ''} overdue"
                ),
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
) -> DealQueueItemRead:
    lead = db.get(Lead, transaction.lead_id)
    contact = db.get(Contact, transaction.contact_id)
    property_record = db.get(Property, transaction.property_id)
    package = db.scalar(
        select(ContractPackage)
        .where(ContractPackage.transaction_id == transaction.id)
        .order_by(ContractPackage.version_number.desc())
        .limit(1)
    )
    case = db.scalar(
        select(DispositionCase).where(DispositionCase.transaction_id == transaction.id)
    )
    reconciliation = db.scalar(
        select(DealReconciliation).where(
            DealReconciliation.transaction_id == transaction.id
        )
    )
    checklist = list(
        db.scalars(
            select(TransactionChecklistItem).where(
                TransactionChecklistItem.transaction_id == transaction.id
            )
        ).all()
    )
    document_count = (
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
        match_count = (
            db.scalar(
                select(func.count(DispositionMatch.id)).where(
                    DispositionMatch.disposition_case_id == case.id
                )
            )
            or 0
        )
        offer_count = (
            db.scalar(
                select(func.count(BuyerOffer.id)).where(
                    BuyerOffer.disposition_case_id == case.id
                )
            )
            or 0
        )
        selected_buyer = db.get(Buyer, case.selected_buyer_id) if case.selected_buyer_id else None
        disposition_owner = db.get(User, case.owner_user_id)
    owner = db.get(User, transaction.owner_user_id) if transaction.owner_user_id else None
    coordinator = (
        db.get(User, transaction.coordinator_user_id)
        if transaction.coordinator_user_id
        else None
    )
    required = [item for item in checklist if item.is_required]
    complete = sum(item.status in {"complete", "not_applicable"} for item in required)
    primary = get_primary_next_action(
        db,
        organization_id=principal.organization_id,
        deal_id=deal.id,
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
            reconciliation.company_profit_cents
            if can_view_economics and reconciliation
            else None
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


def overview(db: Session, principal: Principal) -> DealOverviewRead:
    can_view_economics = bool(
        {PermissionKeys.VIEW_FINANCIALS, PermissionKeys.VIEW_COMPENSATION}
        & principal.permission_keys
    )
    rows = db.execute(
        select(Deal, Transaction)
        .join(Transaction, Transaction.deal_id == Deal.id)
        .where(Deal.organization_id == principal.organization_id)
        .order_by(Transaction.closing_date.asc().nullslast(), Deal.created_at.desc())
    ).all()
    items = [
        _build_item(db, principal, deal, transaction, can_view_economics=can_view_economics)
        for deal, transaction in rows
    ]
    active = [item for item in items if item.closing_status not in {"funded", "cancelled"}]
    return DealOverviewRead(
        can_view_economics=can_view_economics,
        metrics=DealMetricsRead(
            active=len(active),
            closing_exceptions=sum(
                any(blocker.domain == "closing" for blocker in item.blockers)
                for item in active
            ),
            ready_for_disposition=sum(
                item.disposition_status == "ready_to_open" for item in active
            ),
            buyer_needed=sum(
                item.disposition_status
                in {"buyer_matching", "marketing", "offer_review"}
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
