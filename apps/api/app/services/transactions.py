from datetime import UTC, datetime, timedelta
from hashlib import sha256
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.auth import Principal
from app.domain.assets import require_house_workflow
from app.models.foundation import (
    ApprovalRequest,
    AuditEvent,
    Contact,
    ContractPackage,
    ContractTemplate,
    Deal,
    EsignEnvelope,
    Lead,
    Property,
    Transaction,
    TransactionChecklistItem,
    TransactionDocument,
    TransactionDocumentFact,
    TransactionEvent,
    TransactionParty,
    User,
)
from app.schemas.approvals import ApprovalDecision
from app.schemas.transactions import (
    ChecklistItemUpdate,
    ContractPackageCreate,
    ContractPackageRead,
    ContractTemplateProviderUpdate,
    ContractTemplateRead,
    DocumentDeleteRequest,
    DocumentDownloadLinkRead,
    ManualContractExecutionAttestation,
    ManualContractWithdrawalAttestation,
    TransactionChecklistRead,
    TransactionClose,
    TransactionDetail,
    TransactionDocumentFactCreate,
    TransactionDocumentFactRead,
    TransactionDocumentRead,
    TransactionEventCreate,
    TransactionEventRead,
    TransactionMetrics,
    TransactionOverview,
    TransactionPartyCreate,
    TransactionPartyRead,
    TransactionQueueItem,
    TransactionUpdate,
)
from app.services.contract_authority import (
    ACCEPTABLE_EXECUTION_SCAN_STATUSES,
    PURCHASE_AGREEMENT,
    PURCHASE_AUTHORITY_SNAPSHOT_KEY,
    capture_purchase_authority,
    package_document_type,
    package_purchase_authority_snapshot,
    validate_contract_package_authority,
)
from app.services.document_storage import (
    create_download_url,
    delete_content,
    read_content,
    store_content,
)
from app.services.esign import list_envelopes

ACTIVE_STATUSES = ("contract_prep", "approval_pending", "sent", "executed", "closing")
TERMINAL_TRANSACTION_STATUSES = {"cancelled", "canceled", "closed", "funded"}
TERMINAL_LEAD_STAGES = {"dead", "disqualified", "lost", "closed"}
EXECUTED_DOCUMENT_TYPE_BY_PACKAGE = {
    PURCHASE_AGREEMENT: "signed_purchase_agreement",
    "assignment_contract": "assignment_contract",
    "addendum": "executed_addendum",
}
MAX_DOCUMENT_BYTES = 15 * 1024 * 1024


def utc_datetime(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def property_address(property_record: Property | None) -> str:
    if property_record is None:
        return "Unknown property"
    return (
        f"{property_record.street_address}, {property_record.city}, "
        f"{property_record.state} {property_record.postal_code}"
    )


def scoped_transaction(
    db: Session, principal: Principal, transaction_id: UUID
) -> Transaction | None:
    return db.scalar(
        select(Transaction).where(
            Transaction.organization_id == principal.organization_id,
            Transaction.id == transaction_id,
        )
    )


def lock_contract_package_context(
    db: Session,
    principal: Principal,
    transaction_id: UUID,
    package_id: UUID,
) -> tuple[Lead, Transaction, ContractPackage] | None:
    """Lock contract state in the lead -> transaction -> package order."""
    candidate = db.scalar(
        select(Transaction).where(
            Transaction.id == transaction_id,
            Transaction.organization_id == principal.organization_id,
        )
    )
    if candidate is None:
        return None
    lead = db.scalar(
        select(Lead)
        .where(
            Lead.id == candidate.lead_id,
            Lead.organization_id == principal.organization_id,
        )
        .execution_options(populate_existing=True)
        .with_for_update(of=Lead)
    )
    transaction = db.scalar(
        select(Transaction)
        .where(
            Transaction.id == transaction_id,
            Transaction.organization_id == principal.organization_id,
        )
        .execution_options(populate_existing=True)
        .with_for_update(of=Transaction)
    )
    package = db.scalar(
        select(ContractPackage)
        .where(
            ContractPackage.id == package_id,
            ContractPackage.transaction_id == transaction_id,
            ContractPackage.organization_id == principal.organization_id,
        )
        .execution_options(populate_existing=True)
        .with_for_update(of=ContractPackage)
    )
    if lead is None or transaction is None or package is None:
        return None
    return lead, transaction, package


def require_house_transaction_workflow(db: Session, transaction: Transaction) -> None:
    lead = db.get(Lead, transaction.lead_id)
    if lead is None:
        raise ValueError("The transaction lead is no longer available.")
    require_house_workflow(lead.asset_class, workflow="Residential contract and transaction")


def add_event(
    db: Session,
    principal: Principal,
    transaction: Transaction,
    event_type: str,
    summary: str,
    details: dict[str, Any] | None = None,
) -> TransactionEvent:
    event = TransactionEvent(
        organization_id=principal.organization_id,
        transaction_id=transaction.id,
        lead_id=transaction.lead_id,
        actor_user_id=principal.user_id,
        event_type=event_type,
        summary=summary,
        details=details or {},
        occurred_at=datetime.now(UTC),
    )
    db.add(event)
    return event


def list_transactions(db: Session, principal: Principal) -> TransactionOverview:
    now = datetime.now(UTC)
    transactions = db.scalars(
        select(Transaction)
        .where(
            Transaction.organization_id == principal.organization_id,
            Transaction.status.in_(ACTIVE_STATUSES),
        )
        .order_by(Transaction.closing_date.asc().nullslast(), Transaction.created_at.desc())
    ).all()
    rows: list[TransactionQueueItem] = []
    pending_approval = due_soon = overdue = ready = 0
    for transaction in transactions:
        contact = db.get(Contact, transaction.contact_id)
        property_record = db.get(Property, transaction.property_id)
        coordinator = (
            db.get(User, transaction.coordinator_user_id)
            if transaction.coordinator_user_id
            else None
        )
        checklist = db.scalars(
            select(TransactionChecklistItem).where(
                TransactionChecklistItem.transaction_id == transaction.id
            )
        ).all()
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
        next_deadline = min(deadlines, key=utc_datetime) if deadlines else None
        flags: list[str] = []
        if next_deadline and utc_datetime(next_deadline) < now:
            flags.append("Deadline overdue")
            overdue += 1
        elif next_deadline and utc_datetime(next_deadline) <= now + timedelta(days=7):
            due_soon += 1
        if transaction.coordinator_user_id is None:
            flags.append("Coordinator unassigned")
        required = [item for item in checklist if item.is_required]
        complete = sum(item.status in {"complete", "not_applicable"} for item in required)
        if required and complete == len(required) and transaction.contract_executed_at:
            ready += 1
        if transaction.status == "approval_pending":
            pending_approval += 1
        rows.append(
            TransactionQueueItem(
                id=transaction.id,
                lead_id=transaction.lead_id,
                seller_name=contact.legal_name if contact else "Unknown seller",
                property_address=property_address(property_record),
                status=transaction.status,
                purchase_price_cents=transaction.purchase_price_cents,
                closing_date=transaction.closing_date,
                next_deadline=next_deadline,
                coordinator_name=coordinator.display_name if coordinator else None,
                checklist_complete=complete,
                checklist_total=len(required),
                risk_flags=flags,
            )
        )
    return TransactionOverview(
        metrics=TransactionMetrics(
            active=len(rows),
            pending_approval=pending_approval,
            due_next_seven_days=due_soon,
            overdue=overdue,
            ready_to_close=ready,
        ),
        items=rows,
    )


def get_transaction_detail(
    db: Session, principal: Principal, transaction_id: UUID
) -> TransactionDetail | None:
    transaction = scoped_transaction(db, principal, transaction_id)
    if transaction is None:
        return None
    contact = db.get(Contact, transaction.contact_id)
    property_record = db.get(Property, transaction.property_id)
    coordinator = (
        db.get(User, transaction.coordinator_user_id) if transaction.coordinator_user_id else None
    )
    packages = db.scalars(
        select(ContractPackage)
        .where(ContractPackage.transaction_id == transaction.id)
        .order_by(ContractPackage.version_number.desc())
    ).all()
    documents = db.scalars(
        select(TransactionDocument)
        .where(
            TransactionDocument.transaction_id == transaction.id,
            TransactionDocument.deleted_at.is_(None),
        )
        .order_by(TransactionDocument.occurred_at.desc())
    ).all()
    parties = db.scalars(
        select(TransactionParty)
        .where(TransactionParty.transaction_id == transaction.id)
        .order_by(TransactionParty.party_type, TransactionParty.created_at)
    ).all()
    checklist = db.scalars(
        select(TransactionChecklistItem)
        .where(TransactionChecklistItem.transaction_id == transaction.id)
        .order_by(TransactionChecklistItem.sort_order)
    ).all()
    events = db.scalars(
        select(TransactionEvent)
        .where(TransactionEvent.transaction_id == transaction.id)
        .order_by(TransactionEvent.occurred_at.desc())
        .limit(100)
    ).all()
    users = {
        user.id: user.display_name
        for user in db.scalars(
            select(User).where(User.organization_id == principal.organization_id)
        ).all()
    }
    document_facts: dict[UUID, list[TransactionDocumentFactRead]] = {}
    for fact in db.scalars(
        select(TransactionDocumentFact)
        .where(TransactionDocumentFact.transaction_id == transaction.id)
        .order_by(
            TransactionDocumentFact.document_id,
            TransactionDocumentFact.field_key,
            TransactionDocumentFact.source_page,
        )
    ).all():
        document_facts.setdefault(fact.document_id, []).append(
            document_fact_read(
                fact,
                users.get(fact.reviewed_by_user_id) if fact.reviewed_by_user_id else None,
            )
        )
    return TransactionDetail(
        id=transaction.id,
        lead_id=transaction.lead_id,
        deal_id=transaction.deal_id,
        seller_name=contact.legal_name if contact else "Unknown seller",
        property_address=property_address(property_record),
        status=transaction.status,
        contract_type=transaction.contract_type,
        purchase_price_cents=transaction.purchase_price_cents,
        assignment_fee_cents=transaction.assignment_fee_cents,
        earnest_money_cents=transaction.earnest_money_cents,
        title_company=transaction.title_company,
        closing_date=transaction.closing_date,
        inspection_period_days=transaction.inspection_period_days,
        coordinator_user_id=transaction.coordinator_user_id,
        coordinator_name=coordinator.display_name if coordinator else None,
        earnest_money_due_at=transaction.earnest_money_due_at,
        earnest_money_paid_at=transaction.earnest_money_paid_at,
        due_diligence_deadline=transaction.due_diligence_deadline,
        title_opened_at=transaction.title_opened_at,
        title_cleared_at=transaction.title_cleared_at,
        assignment_deadline=transaction.assignment_deadline,
        funded_at=transaction.funded_at,
        closed_at=transaction.closed_at,
        cancelled_at=transaction.cancelled_at,
        notes=transaction.notes,
        contract_packages=[package_read(item) for item in packages],
        esign_envelopes=list_envelopes(
            db,
            principal.organization_id,
            transaction.id,
        ),
        documents=[document_read(item, document_facts.get(item.id, [])) for item in documents],
        parties=[
            TransactionPartyRead(
                id=item.id,
                party_type=item.party_type,
                name=item.name,
                company_name=item.company_name,
                email=item.email,
                phone=item.phone,
                address=item.address,
                is_primary=item.is_primary,
                notes=item.notes,
                created_at=item.created_at,
            )
            for item in parties
        ],
        checklist=[
            TransactionChecklistRead(
                id=item.id,
                item_key=item.item_key,
                category=item.category,
                title=item.title,
                description=item.description,
                status=item.status,
                is_required=item.is_required,
                responsible_user_id=item.responsible_user_id,
                responsible_name=(
                    users.get(item.responsible_user_id) if item.responsible_user_id else None
                ),
                due_at=item.due_at,
                completed_at=item.completed_at,
                dependency_item_id=item.dependency_item_id,
                evidence_document_id=item.evidence_document_id,
                evidence_notes=item.evidence_notes,
                escalated_at=item.escalated_at,
                sort_order=item.sort_order,
            )
            for item in checklist
        ],
        events=[
            TransactionEventRead(
                id=item.id,
                event_type=item.event_type,
                summary=item.summary,
                actor_name=users.get(item.actor_user_id) if item.actor_user_id else None,
                occurred_at=item.occurred_at,
            )
            for item in events
        ],
    )


def update_transaction(
    db: Session, principal: Principal, transaction_id: UUID, payload: TransactionUpdate
) -> TransactionDetail | None:
    transaction = scoped_transaction(db, principal, transaction_id)
    if transaction is None:
        return None
    require_house_transaction_workflow(db, transaction)
    changes = payload.model_dump(exclude_unset=True)
    if "coordinator_user_id" in changes and changes["coordinator_user_id"] is not None:
        user = db.scalar(
            select(User).where(
                User.id == changes["coordinator_user_id"],
                User.organization_id == principal.organization_id,
                User.is_active.is_(True),
            )
        )
        if user is None:
            raise ValueError("Coordinator must be an active workspace user.")
    previous = {key: getattr(transaction, key) for key in changes}
    for key, value in changes.items():
        setattr(transaction, key, value)
    add_event(
        db,
        principal,
        transaction,
        "transaction.updated",
        "Closing details updated.",
        {"fields": list(changes)},
    )
    db.add(
        AuditEvent(
            organization_id=principal.organization_id,
            actor_user_id=principal.user_id,
            actor_type="user",
            action="transaction.update",
            entity_type="transaction",
            entity_id=transaction.id,
            previous_value={
                key: str(value) if value is not None else None for key, value in previous.items()
            },
            new_value={
                key: str(value) if value is not None else None for key, value in changes.items()
            },
            reason="Transaction coordination update",
        )
    )
    if {"closing_date", "coordinator_user_id"} & changes.keys():
        from app.services.disposition_offer_room import (
            sync_transaction_offer_room_checkpoints,
        )

        sync_transaction_offer_room_checkpoints(db, principal, transaction)
    db.commit()
    return get_transaction_detail(db, principal, transaction.id)


def create_contract_package(
    db: Session, principal: Principal, transaction_id: UUID, payload: ContractPackageCreate
) -> ContractPackageRead | None:
    transaction = scoped_transaction(db, principal, transaction_id)
    if transaction is None:
        return None
    require_house_transaction_workflow(db, transaction)
    if transaction.status not in ACTIVE_STATUSES:
        raise ValueError("A contract package cannot be created for a completed transaction.")
    if payload.template_id:
        template = db.scalar(
            select(ContractTemplate).where(
                ContractTemplate.id == payload.template_id,
                ContractTemplate.organization_id == principal.organization_id,
                ContractTemplate.status == "approved",
            )
        )
        if template is None:
            raise ValueError("Select an approved contract template.")
        document_type = template.document_type
    else:
        document_type = payload.document_type
    disposition_buyer_binding: dict[str, Any] | None = None
    package_earnest_money_cents = payload.earnest_money_cents
    package_closing_date = payload.closing_date
    package_inspection_period_days = payload.inspection_period_days
    if document_type == "assignment_contract":
        lead = db.scalar(
            select(Lead)
            .where(
                Lead.id == transaction.lead_id,
                Lead.organization_id == principal.organization_id,
            )
            .with_for_update(of=Lead)
        )
        locked_transaction = db.scalar(
            select(Transaction)
            .where(
                Transaction.id == transaction.id,
                Transaction.organization_id == principal.organization_id,
            )
            .execution_options(populate_existing=True)
            .with_for_update(of=Transaction)
        )
        if lead is None or locked_transaction is None:
            raise ValueError("The assignment transaction is no longer available.")
        transaction = locked_transaction
        if transaction.status not in ACTIVE_STATUSES:
            raise ValueError("A contract package cannot be created for a completed transaction.")
        from app.services.disposition_offer_room import (
            build_assignment_buyer_binding,
            load_current_assignment_authority,
        )

        (
            disposition_case,
            active_selection,
            primary_slot,
            primary_offer,
            selected_buyer,
        ) = load_current_assignment_authority(
            db,
            principal.organization_id,
            transaction,
            lock=True,
        )
        package_earnest_money_cents = primary_offer.earnest_money_cents
        package_closing_date = primary_offer.proposed_closing_at
        package_inspection_period_days = primary_offer.due_diligence_days

        disposition_buyer_binding = build_assignment_buyer_binding(
            db,
            principal,
            disposition_case,
            transaction,
            active_selection,
            primary_slot,
            primary_offer,
            selected_buyer,
            base_purchase_price_cents=payload.purchase_price_cents,
            earnest_money_cents=package_earnest_money_cents,
            closing_date=package_closing_date,
            inspection_period_days=package_inspection_period_days,
        )
    authority_snapshot = (
        capture_purchase_authority(db, transaction, payload.purchase_price_cents)
        if document_type == PURCHASE_AGREEMENT
        else None
    )
    version = (
        db.scalar(
            select(func.max(ContractPackage.version_number)).where(
                ContractPackage.transaction_id == transaction.id
            )
        )
        or 0
    ) + 1
    package = ContractPackage(
        organization_id=principal.organization_id,
        transaction_id=transaction.id,
        lead_id=transaction.lead_id,
        property_id=transaction.property_id,
        template_id=payload.template_id,
        created_by_user_id=principal.user_id,
        approval_request_id=None,
        version_number=version,
        status="draft",
        seller_name=payload.seller_name,
        buyer_entity_name=payload.buyer_entity_name,
        purchase_price_cents=payload.purchase_price_cents,
        earnest_money_cents=package_earnest_money_cents,
        closing_date=package_closing_date,
        inspection_period_days=package_inspection_period_days,
        terms_snapshot={
            "document_type": document_type,
            "special_terms": payload.special_terms,
            **(
                {"disposition_buyer_binding": disposition_buyer_binding}
                if disposition_buyer_binding is not None
                else {}
            ),
            **(
                {PURCHASE_AUTHORITY_SNAPSHOT_KEY: authority_snapshot}
                if authority_snapshot is not None
                else {}
            ),
        },
        notes=payload.notes,
    )
    db.add(package)
    db.flush()
    add_event(
        db,
        principal,
        transaction,
        "contract.draft_created",
        f"Contract package v{version} drafted.",
        {"package_id": str(package.id)},
    )
    db.commit()
    db.refresh(package)
    return package_read(package)


def request_contract_approval(
    db: Session, principal: Principal, transaction_id: UUID, package_id: UUID
) -> ContractPackageRead | None:
    context = lock_contract_package_context(
        db,
        principal,
        transaction_id,
        package_id,
    )
    if context is None:
        return None
    _, transaction, package = context
    require_house_transaction_workflow(db, transaction)
    if package.status != "draft":
        raise ValueError("Only a draft contract package can be submitted for approval.")
    validate_contract_package_authority(
        db,
        transaction,
        package,
        gate="requesting contract approval",
        lock_assignment=True,
    )
    request = ApprovalRequest(
        organization_id=principal.organization_id,
        requested_by_user_id=principal.user_id,
        assigned_to_user_id=None,
        decided_by_user_id=None,
        request_type="contract_send",
        entity_type="contract_package",
        entity_id=package.id,
        status="pending",
        title=f"Approve contract package v{package.version_number}",
        summary=(
            f"{package.seller_name} at ${package.purchase_price_cents / 100:,.0f}; "
            "verify terms before sending."
        ),
        approval_metadata={
            "transaction_id": str(transaction.id),
            "lead_id": str(transaction.lead_id),
            "version_number": package.version_number,
        },
    )
    db.add(request)
    db.flush()
    package.approval_request_id = request.id
    package.status = "pending_approval"
    if package_document_type(package) == PURCHASE_AGREEMENT:
        transaction.status = "approval_pending"
    add_event(
        db,
        principal,
        transaction,
        "contract.approval_requested",
        f"Contract package v{package.version_number} submitted for approval.",
    )
    db.commit()
    db.refresh(package)
    return package_read(package)


def apply_contract_decision(
    db: Session, principal: Principal, request: ApprovalRequest, payload: ApprovalDecision
) -> tuple[ContractPackage, Transaction]:
    candidate_package = db.scalar(
        select(ContractPackage).where(
            ContractPackage.id == request.entity_id,
            ContractPackage.organization_id == principal.organization_id,
        )
    )
    if candidate_package is None:
        raise ValueError("The contract package is no longer pending approval.")
    context = lock_contract_package_context(
        db,
        principal,
        candidate_package.transaction_id,
        candidate_package.id,
    )
    if context is None:
        raise ValueError("The transaction is no longer available.")
    _, transaction, package = context
    if package.status != "pending_approval":
        raise ValueError("The contract package is no longer pending approval.")
    if payload.status == "approved":
        require_house_transaction_workflow(db, transaction)
        validate_contract_package_authority(
            db,
            transaction,
            package,
            gate="contract approval",
            lock_assignment=True,
        )
    if payload.status in {"rejected", "cancelled"} and not payload.decision_notes:
        raise ValueError("Decision notes are required when a contract package is not approved.")
    if payload.status == "approved":
        package.status = "approved"
        package.approved_at = datetime.now(UTC)
    else:
        package.status = "draft" if payload.status == "rejected" else "void"
        if payload.status == "cancelled":
            package.voided_at = datetime.now(UTC)
    if package_document_type(package) == PURCHASE_AGREEMENT:
        transaction.status = "contract_prep"
    add_event(
        db,
        principal,
        transaction,
        f"contract.{payload.status}",
        f"Contract package v{package.version_number} {payload.status}.",
        {"decision_notes": payload.decision_notes},
    )
    return package, transaction


def mark_contract_sent(
    db: Session, principal: Principal, transaction_id: UUID, package_id: UUID
) -> ContractPackageRead | None:
    context = lock_contract_package_context(
        db,
        principal,
        transaction_id,
        package_id,
    )
    if context is None:
        return None
    _, transaction, package = context
    require_house_transaction_workflow(db, transaction)
    if package.status != "approved":
        raise ValueError("The contract package must be approved before it is sent.")
    validate_contract_package_authority(
        db,
        transaction,
        package,
        gate="sending the contract",
        lock_assignment=True,
    )
    now = datetime.now(UTC)
    package.status = "sent"
    package.sent_at = now
    if package_document_type(package) == PURCHASE_AGREEMENT:
        transaction.status = "sent"
        transaction.contract_sent_at = now
    add_event(
        db,
        principal,
        transaction,
        "contract.sent",
        f"Contract package v{package.version_number} recorded as sent.",
    )
    db.commit()
    db.refresh(package)
    return package_read(package)


def withdraw_sent_contract_package(
    db: Session,
    principal: Principal,
    transaction_id: UUID,
    package_id: UUID,
    payload: ManualContractWithdrawalAttestation,
) -> ContractPackageRead | None:
    """Void an approved or manually delivered package before newer authority is recorded."""
    withdrawal_reason = payload.reason.strip()
    if len(withdrawal_reason) < 10:
        raise ValueError("Record a specific withdrawal reason of at least ten characters.")
    context = lock_contract_package_context(
        db,
        principal,
        transaction_id,
        package_id,
    )
    if context is None:
        return None
    _, transaction, package = context
    require_house_transaction_workflow(db, transaction)
    if package.status not in {"approved", "sent"}:
        raise ValueError("Only an approved or outstanding sent contract package can be withdrawn.")
    prior_package_status = package.status
    completed_envelope = db.scalar(
        select(EsignEnvelope.id).where(
            EsignEnvelope.organization_id == principal.organization_id,
            EsignEnvelope.contract_package_id == package.id,
            EsignEnvelope.status == "completed",
        )
    )
    if completed_envelope is not None:
        raise ValueError(
            "A completed SignWell envelope exists for this package; reconcile execution instead."
        )
    active_envelope = db.scalar(
        select(EsignEnvelope.id).where(
            EsignEnvelope.organization_id == principal.organization_id,
            EsignEnvelope.contract_package_id == package.id,
            EsignEnvelope.status.not_in(("completed", "declined", "expired", "cancelled", "error")),
        )
    )
    if active_envelope is not None:
        raise ValueError(
            "Cancel the active SignWell request and reconcile its terminal status before "
            "withdrawing this package."
        )
    now = datetime.now(UTC)
    package.status = "void"
    package.voided_at = now
    if package_document_type(package) == PURCHASE_AGREEMENT and transaction.status == "sent":
        transaction.status = "contract_prep"
    add_event(
        db,
        principal,
        transaction,
        "contract.withdrawn",
        f"Contract package v{package.version_number} was withdrawn and voided.",
        {
            "reason": withdrawal_reason,
            "all_recipients_confirmed": payload.confirm_withdrawn_from_all_recipients,
        },
    )
    db.add(
        AuditEvent(
            organization_id=principal.organization_id,
            actor_user_id=principal.user_id,
            actor_type="user",
            action="contract.package.withdraw",
            entity_type="contract_package",
            entity_id=package.id,
            previous_value={"status": prior_package_status},
            new_value={
                "status": "void",
                "all_recipients_confirmed": payload.confirm_withdrawn_from_all_recipients,
            },
            reason=withdrawal_reason,
        )
    )
    db.commit()
    db.refresh(package)
    return package_read(package)


def upload_document(
    db: Session,
    principal: Principal,
    transaction_id: UUID,
    *,
    content: bytes,
    file_name: str,
    content_type: str,
    document_type: str,
    title: str,
    status: str,
    package_id: UUID | None,
    notes: str | None,
) -> TransactionDocumentRead | None:
    transaction = db.scalar(
        select(Transaction)
        .where(
            Transaction.id == transaction_id,
            Transaction.organization_id == principal.organization_id,
        )
        .with_for_update(of=Transaction)
    )
    if transaction is None:
        return None
    require_house_transaction_workflow(db, transaction)
    if not content or len(content) > MAX_DOCUMENT_BYTES:
        raise ValueError("Document must be between 1 byte and 15 MB.")
    if (
        package_id
        and db.scalar(
            select(ContractPackage.id).where(
                ContractPackage.id == package_id, ContractPackage.transaction_id == transaction.id
            )
        )
        is None
    ):
        raise ValueError("Contract package does not belong to this transaction.")
    checksum = sha256(content).hexdigest()
    duplicate = db.scalar(
        select(TransactionDocument).where(
            TransactionDocument.organization_id == principal.organization_id,
            TransactionDocument.transaction_id == transaction.id,
            TransactionDocument.sha256 == checksum,
            TransactionDocument.deleted_at.is_(None),
        )
    )
    if duplicate is not None:
        raise ValueError(f"This file is already stored as '{duplicate.title}'.")
    document_id = uuid4()
    stored = store_content(
        organization_id=principal.organization_id,
        namespace=f"transactions/{transaction.id}",
        record_id=document_id,
        file_name=file_name,
        content_type=content_type,
        content=content,
    )
    document = TransactionDocument(
        id=document_id,
        organization_id=principal.organization_id,
        transaction_id=transaction.id,
        contract_package_id=package_id,
        uploaded_by_user_id=principal.user_id,
        document_type=document_type,
        title=title,
        status=status,
        file_name=file_name,
        content_type=content_type,
        file_size=len(content),
        sha256=checksum,
        file_data=stored.database_bytes,
        storage_provider=stored.provider,
        storage_key=stored.key,
        malware_scan_status=stored.malware_scan_status,
        retention_until=stored.retention_until,
        deleted_at=None,
        occurred_at=datetime.now(UTC),
        notes=notes,
    )
    db.add(document)
    db.flush()
    add_event(
        db,
        principal,
        transaction,
        "document.uploaded",
        f"Uploaded {title}.",
        {"document_id": str(document.id), "document_type": document_type},
    )
    db.commit()
    db.refresh(document)
    return document_read(document)


def add_document_fact(
    db: Session,
    principal: Principal,
    transaction_id: UUID,
    document_id: UUID,
    payload: TransactionDocumentFactCreate,
) -> TransactionDocumentFactRead | None:
    transaction = scoped_transaction(db, principal, transaction_id)
    document = get_document(db, principal, transaction_id, document_id)
    if transaction is None or document is None:
        return None
    require_house_transaction_workflow(db, transaction)
    user = db.get(User, principal.user_id)
    now = datetime.now(UTC)
    fact = TransactionDocumentFact(
        organization_id=principal.organization_id,
        transaction_id=transaction.id,
        document_id=document.id,
        field_key=payload.field_key.strip().lower().replace(" ", "_"),
        value_text=payload.value_text.strip(),
        source_page=payload.source_page,
        source_excerpt=payload.source_excerpt,
        extraction_method="manual",
        status="confirmed",
        confidence_score=100,
        created_by_user_id=principal.user_id,
        reviewed_by_user_id=principal.user_id,
        reviewed_at=now,
    )
    db.add(fact)
    db.flush()
    add_event(
        db,
        principal,
        transaction,
        "document.fact_confirmed",
        f"Confirmed {fact.field_key} from {document.title}.",
        {
            "document_id": str(document.id),
            "fact_id": str(fact.id),
            "source_page": fact.source_page,
        },
    )
    db.commit()
    db.refresh(fact)
    return document_fact_read(fact, user.display_name if user else None)


def get_document(
    db: Session, principal: Principal, transaction_id: UUID, document_id: UUID
) -> TransactionDocument | None:
    return db.scalar(
        select(TransactionDocument).where(
            TransactionDocument.organization_id == principal.organization_id,
            TransactionDocument.transaction_id == transaction_id,
            TransactionDocument.id == document_id,
            TransactionDocument.deleted_at.is_(None),
        )
    )


def get_document_content(document: TransactionDocument) -> bytes:
    return read_content(
        provider=document.storage_provider,
        key=document.storage_key,
        database_bytes=document.file_data,
    )


def create_document_download_link(
    document: TransactionDocument,
) -> DocumentDownloadLinkRead:
    fallback = f"/api/v1/transactions/{document.transaction_id}/documents/{document.id}/content"
    url, expires_at = create_download_url(
        provider=document.storage_provider,
        key=document.storage_key,
        fallback_url=fallback,
    )
    return DocumentDownloadLinkRead(url=url, expires_at=expires_at)


def delete_document(
    db: Session,
    principal: Principal,
    transaction_id: UUID,
    document_id: UUID,
    payload: DocumentDeleteRequest,
) -> bool:
    transaction = scoped_transaction(db, principal, transaction_id)
    document = get_document(db, principal, transaction_id, document_id)
    if transaction is None or document is None:
        return False
    require_house_transaction_workflow(db, transaction)
    delete_content(provider=document.storage_provider, key=document.storage_key)
    now = datetime.now(UTC)
    document.deleted_at = now
    document.status = "deleted"
    document.file_data = None
    add_event(
        db,
        principal,
        transaction,
        "document.deleted",
        f"Deleted {document.title}.",
        {"document_id": str(document.id), "reason": payload.reason},
    )
    db.add(
        AuditEvent(
            organization_id=principal.organization_id,
            actor_user_id=principal.user_id,
            actor_type="user",
            action="transaction.document_delete",
            entity_type="transaction_document",
            entity_id=document.id,
            previous_value={"status": "available", "sha256": document.sha256},
            new_value={"status": "deleted", "deleted_at": now.isoformat()},
            reason=payload.reason,
        )
    )
    db.commit()
    return True


def mark_contract_executed(
    db: Session,
    principal: Principal,
    transaction_id: UUID,
    package_id: UUID,
    attestation: ManualContractExecutionAttestation,
) -> ContractPackageRead | None:
    context = lock_contract_package_context(
        db,
        principal,
        transaction_id,
        package_id,
    )
    if context is None:
        return None
    lead, transaction, package = context
    document = db.scalar(
        select(TransactionDocument)
        .where(
            TransactionDocument.id == attestation.document_id,
            TransactionDocument.transaction_id == transaction_id,
            TransactionDocument.organization_id == principal.organization_id,
            TransactionDocument.deleted_at.is_(None),
        )
        .execution_options(populate_existing=True)
        .with_for_update(of=TransactionDocument)
    )
    require_house_transaction_workflow(db, transaction)
    if (
        transaction.status in TERMINAL_TRANSACTION_STATUSES
        or transaction.cancelled_at is not None
        or transaction.closed_at is not None
        or transaction.funded_at is not None
    ):
        raise ValueError("A terminal transaction cannot be recorded as executed.")
    if lead.archived_at is not None or lead.stage_key in TERMINAL_LEAD_STAGES:
        raise ValueError("Reopen the closed lead before recording contract execution.")
    if package.status not in {"approved", "sent"}:
        raise ValueError("Only an approved or sent contract package can be executed.")
    validate_contract_package_authority(
        db,
        transaction,
        package,
        gate="recording execution",
        lock_assignment=True,
    )
    expected_document_type = EXECUTED_DOCUMENT_TYPE_BY_PACKAGE.get(package_document_type(package))
    if expected_document_type is None:
        raise ValueError("This contract package type cannot be manually recorded as executed.")
    if document is None or document.contract_package_id != package.id:
        raise ValueError("Upload the exact executed agreement to this package first.")
    if document.document_type != expected_document_type:
        raise ValueError(
            f"Execution requires a {expected_document_type.replace('_', ' ')} for this package."
        )
    if document.status != "executed":
        raise ValueError("The execution document must be explicitly marked executed.")
    if document.malware_scan_status not in ACCEPTABLE_EXECUTION_SCAN_STATUSES:
        raise ValueError("The execution document does not have an acceptable malware scan state.")
    reason = attestation.reason.strip()
    if len(reason) < 10:
        raise ValueError("Explain how the fully executed agreement was manually verified.")
    assignment_execution_identity: dict[str, Any] | None = None
    if package_document_type(package) == "assignment_contract":
        binding = (package.terms_snapshot or {}).get("disposition_buyer_binding")
        if not isinstance(binding, dict):
            raise ValueError("The assignment package is missing its selected-buyer binding.")
        if not attestation.assignee_name or not attestation.assignee_email:
            raise ValueError(
                "Record the executed assignment's assignee name and email before attesting it."
            )
        from app.services.disposition_offer_room import (
            assignment_signer_identity_snapshot,
        )

        signer_identity = assignment_signer_identity_snapshot(
            binding,
            signer_name=attestation.assignee_name,
            signer_email=attestation.assignee_email,
            source="manual_execution_attestation",
        )
        assignment_execution_identity = {
            **signer_identity,
            "document_id": str(document.id),
            "document_sha256": document.sha256,
            "attested_by_user_id": str(principal.user_id),
        }
        package.terms_snapshot = {
            **(package.terms_snapshot or {}),
            "assignment_execution_identity": assignment_execution_identity,
        }
    now = datetime.now(UTC)
    previous_package_status = package.status
    package.status = "executed"
    package.executed_at = now
    if package_document_type(package) == PURCHASE_AGREEMENT:
        transaction.status = "executed"
        transaction.contract_executed_at = now
        deal = db.get(Deal, transaction.deal_id)
        lead.stage_key = "under_contract"
        if deal:
            deal.stage_key = "under_contract"
    add_event(
        db,
        principal,
        transaction,
        "contract.executed",
        f"Contract package v{package.version_number} executed.",
        {
            "document_id": str(document.id),
            "execution_evidence": "manual_attestation",
            "attested_by_user_id": str(principal.user_id),
            "attestation_reason": reason,
            **(
                {"assignment_execution_identity": assignment_execution_identity}
                if assignment_execution_identity is not None
                else {}
            ),
        },
    )
    db.add(
        AuditEvent(
            organization_id=principal.organization_id,
            actor_user_id=principal.user_id,
            actor_type="user",
            action="contract.execution.manual_attest",
            entity_type="contract_package",
            entity_id=package.id,
            previous_value={"status": previous_package_status},
            new_value={
                "status": package.status,
                "document_id": str(document.id),
                "document_sha256": document.sha256,
                "document_status": document.status,
                "malware_scan_status": document.malware_scan_status,
                "confirm_fully_executed": attestation.confirm_fully_executed,
                **(
                    {"assignment_execution_identity": assignment_execution_identity}
                    if assignment_execution_identity is not None
                    else {}
                ),
            },
            reason=reason,
        )
    )
    db.commit()
    db.refresh(package)
    return package_read(package)


def add_party(
    db: Session, principal: Principal, transaction_id: UUID, payload: TransactionPartyCreate
) -> TransactionPartyRead | None:
    transaction = db.scalar(
        select(Transaction)
        .where(
            Transaction.id == transaction_id,
            Transaction.organization_id == principal.organization_id,
        )
        .with_for_update(of=Transaction)
    )
    if transaction is None:
        return None
    require_house_transaction_workflow(db, transaction)
    if payload.is_primary:
        for existing in db.scalars(
            select(TransactionParty).where(
                TransactionParty.transaction_id == transaction.id,
                TransactionParty.party_type == payload.party_type,
            )
        ).all():
            existing.is_primary = False
    party = TransactionParty(
        organization_id=principal.organization_id,
        transaction_id=transaction.id,
        **payload.model_dump(),
    )
    db.add(party)
    db.flush()
    add_event(
        db,
        principal,
        transaction,
        "party.added",
        f"Added {payload.party_type.replace('_', ' ')}: {payload.name}.",
    )
    db.commit()
    db.refresh(party)
    return TransactionPartyRead(id=party.id, created_at=party.created_at, **payload.model_dump())


def update_checklist_item(
    db: Session,
    principal: Principal,
    transaction_id: UUID,
    item_id: UUID,
    payload: ChecklistItemUpdate,
) -> TransactionDetail | None:
    transaction = db.scalar(
        select(Transaction)
        .where(
            Transaction.id == transaction_id,
            Transaction.organization_id == principal.organization_id,
        )
        .execution_options(populate_existing=True)
        .with_for_update(of=Transaction)
    )
    if transaction is None:
        return None
    item = db.scalar(
        select(TransactionChecklistItem)
        .where(
            TransactionChecklistItem.id == item_id,
            TransactionChecklistItem.transaction_id == transaction_id,
            TransactionChecklistItem.organization_id == principal.organization_id,
        )
        .execution_options(populate_existing=True)
        .with_for_update(of=TransactionChecklistItem)
    )
    if item is None:
        return None
    require_house_transaction_workflow(db, transaction)
    changes = payload.model_dump(exclude_unset=True)
    if changes.get("status") == "complete" and item.dependency_item_id:
        dependency = db.get(TransactionChecklistItem, item.dependency_item_id)
        if dependency and dependency.status not in {"complete", "not_applicable"}:
            raise ValueError(f"Complete '{dependency.title}' first.")
    evidence_id = changes.get("evidence_document_id")
    if evidence_id and get_document(db, principal, transaction_id, evidence_id) is None:
        raise ValueError("Evidence document does not belong to this transaction.")
    for key, value in changes.items():
        setattr(item, key, value)
    if changes.get("status") == "complete":
        item.completed_at = datetime.now(UTC)
    elif "status" in changes:
        item.completed_at = None
    add_event(
        db,
        principal,
        transaction,
        "checklist.updated",
        f"Checklist item '{item.title}' is {item.status}.",
    )
    from app.services.disposition_offer_room import sync_transaction_offer_room_checkpoints

    sync_transaction_offer_room_checkpoints(db, principal, transaction)
    db.commit()
    return get_transaction_detail(db, principal, transaction.id)


def record_note(
    db: Session, principal: Principal, transaction_id: UUID, payload: TransactionEventCreate
) -> TransactionEventRead | None:
    transaction = scoped_transaction(db, principal, transaction_id)
    if transaction is None:
        return None
    require_house_transaction_workflow(db, transaction)
    event = add_event(db, principal, transaction, payload.event_type, payload.summary)
    db.commit()
    db.refresh(event)
    user = db.get(User, principal.user_id)
    return TransactionEventRead(
        id=event.id,
        event_type=event.event_type,
        summary=event.summary,
        actor_name=user.display_name if user else None,
        occurred_at=event.occurred_at,
    )


def close_transaction(
    db: Session, principal: Principal, transaction_id: UUID, payload: TransactionClose
) -> TransactionDetail | None:
    candidate = db.scalar(
        select(Transaction).where(
            Transaction.organization_id == principal.organization_id,
            Transaction.id == transaction_id,
        )
    )
    if candidate is None:
        return None
    lead = db.scalar(
        select(Lead)
        .where(
            Lead.id == candidate.lead_id,
            Lead.organization_id == principal.organization_id,
        )
        .execution_options(populate_existing=True)
        .with_for_update(of=Lead)
    )
    transaction = db.scalar(
        select(Transaction)
        .where(
            Transaction.organization_id == principal.organization_id,
            Transaction.id == transaction_id,
        )
        .execution_options(populate_existing=True)
        .with_for_update(of=Transaction)
    )
    if transaction is None:
        return None
    already_finalized = (payload.outcome == "funded" and transaction.status == "funded") or (
        payload.outcome == "cancelled" and transaction.status in {"cancelled", "canceled"}
    )
    if already_finalized:
        # Retried close requests are idempotent and must never rewrite a lead that was
        # subsequently closed out or otherwise moved to a terminal stage.
        db.commit()
        return get_transaction_detail(db, principal, transaction.id)
    if transaction.status in TERMINAL_TRANSACTION_STATUSES:
        raise ValueError(
            f"This transaction is already terminal with status '{transaction.status}'."
        )
    if payload.outcome == "funded":
        require_house_transaction_workflow(db, transaction)
    now = datetime.now(UTC)
    deal = db.get(Deal, transaction.deal_id)
    if payload.outcome == "funded":
        if lead is None:
            raise ValueError("The transaction lead is no longer available.")
        if lead.archived_at is not None or lead.stage_key in TERMINAL_LEAD_STAGES:
            raise ValueError("Reopen the closed lead before recording transaction funding.")
        executed_packages = list(
            db.scalars(
                select(ContractPackage).where(
                    ContractPackage.organization_id == principal.organization_id,
                    ContractPackage.transaction_id == transaction.id,
                    ContractPackage.status == "executed",
                )
            ).all()
        )
        executed_purchase = next(
            (
                package.id
                for package in executed_packages
                if package_document_type(package) == PURCHASE_AGREEMENT
            ),
            None,
        )
        funding = db.scalar(
            select(TransactionDocument.id).where(
                TransactionDocument.transaction_id == transaction.id,
                TransactionDocument.document_type == "funding_confirmation",
                TransactionDocument.deleted_at.is_(None),
            )
        )
        incomplete = db.scalar(
            select(func.count())
            .select_from(TransactionChecklistItem)
            .where(
                TransactionChecklistItem.transaction_id == transaction.id,
                TransactionChecklistItem.is_required.is_(True),
                TransactionChecklistItem.status.notin_(("complete", "not_applicable")),
            )
        )
        if transaction.contract_executed_at is None or executed_purchase is None:
            raise ValueError("An executed purchase agreement is required before funding.")
        if not funding:
            raise ValueError("Upload funding confirmation before closing the transaction.")
        if incomplete:
            raise ValueError(f"Complete the {incomplete} required closing checklist item(s) first.")
        transaction.status = "funded"
        transaction.funded_at = now
        transaction.closed_at = now
        from app.services.disposition_offer_room import (
            record_funded_transaction_buyer_outcome,
        )

        record_funded_transaction_buyer_outcome(
            db,
            principal,
            transaction,
            occurred_at=now,
        )
        if lead:
            lead.stage_key = "closed"
        if deal:
            deal.stage_key = "closed"
    else:
        signable_envelope = db.scalar(
            select(EsignEnvelope.id).where(
                EsignEnvelope.organization_id == principal.organization_id,
                EsignEnvelope.transaction_id == transaction.id,
                EsignEnvelope.status.not_in(
                    ("completed", "declined", "expired", "cancelled", "error")
                ),
            )
        )
        if signable_envelope is not None:
            raise ValueError(
                "Cancel the active SignWell request and reconcile its terminal status before "
                "cancelling this transaction."
            )
        outstanding_sent_package = db.scalar(
            select(ContractPackage.id).where(
                ContractPackage.organization_id == principal.organization_id,
                ContractPackage.transaction_id == transaction.id,
                ContractPackage.status.in_(("sending", "sent")),
            )
        )
        if outstanding_sent_package is not None:
            raise ValueError(
                "Withdraw the outstanding contract package before cancelling this transaction."
            )
        retired_packages = list(
            db.scalars(
                select(ContractPackage).where(
                    ContractPackage.organization_id == principal.organization_id,
                    ContractPackage.transaction_id == transaction.id,
                    ContractPackage.status.in_(("draft", "pending_approval", "approved")),
                )
            ).all()
        )
        for package in retired_packages:
            package.status = "void"
            package.voided_at = package.voided_at or now
        transaction.status = "cancelled"
        transaction.cancelled_at = now
        from app.services.disposition_offer_room import (
            reconcile_cancelled_transaction_checkpoints,
        )

        reconcile_cancelled_transaction_checkpoints(
            db,
            principal,
            transaction,
            cancelled_at=now,
        )
        if lead and lead.archived_at is None and lead.stage_key not in TERMINAL_LEAD_STAGES:
            lead.stage_key = "follow_up"
        if deal:
            deal.stage_key = "cancelled"
    transaction.notes = "\n".join(value for value in (transaction.notes, payload.notes) if value)
    add_event(
        db,
        principal,
        transaction,
        f"transaction.{payload.outcome}",
        f"Transaction {payload.outcome}.",
        {
            "notes": payload.notes,
            **(
                {"retired_contract_package_ids": [str(item.id) for item in retired_packages]}
                if payload.outcome == "cancelled"
                else {}
            ),
        },
    )
    db.commit()
    return get_transaction_detail(db, principal, transaction.id)


def list_templates(db: Session, principal: Principal) -> list[ContractTemplateRead]:
    return [
        template_read(item)
        for item in db.scalars(
            select(ContractTemplate)
            .where(ContractTemplate.organization_id == principal.organization_id)
            .order_by(ContractTemplate.created_at.desc())
        ).all()
    ]


def upload_template(
    db: Session,
    principal: Principal,
    *,
    content: bytes,
    file_name: str,
    content_type: str,
    document_type: str,
    state_code: str,
    name: str,
    notes: str | None,
) -> ContractTemplateRead:
    if not content or len(content) > MAX_DOCUMENT_BYTES:
        raise ValueError("Template must be between 1 byte and 15 MB.")
    state_code = state_code.upper()
    if len(state_code) != 2:
        raise ValueError("Use a two-letter state code.")
    version = (
        db.scalar(
            select(func.max(ContractTemplate.version_number)).where(
                ContractTemplate.organization_id == principal.organization_id,
                ContractTemplate.document_type == document_type,
                ContractTemplate.state_code == state_code,
            )
        )
        or 0
    ) + 1
    template_id = uuid4()
    stored = store_content(
        organization_id=principal.organization_id,
        namespace="contract-templates",
        record_id=template_id,
        file_name=file_name,
        content_type=content_type,
        content=content,
    )
    template = ContractTemplate(
        id=template_id,
        organization_id=principal.organization_id,
        created_by_user_id=principal.user_id,
        approved_by_user_id=None,
        document_type=document_type,
        state_code=state_code,
        name=name,
        version_number=version,
        status="draft",
        file_name=file_name,
        content_type=content_type,
        file_size=len(content),
        sha256=sha256(content).hexdigest(),
        file_data=stored.database_bytes,
        storage_provider=stored.provider,
        storage_key=stored.key,
        malware_scan_status=stored.malware_scan_status,
        retention_until=stored.retention_until,
        deleted_at=None,
        esign_provider_template_id=None,
        esign_field_mapping=None,
        notes=notes,
    )
    db.add(template)
    db.commit()
    db.refresh(template)
    return template_read(template)


def approve_template(
    db: Session, principal: Principal, template_id: UUID
) -> ContractTemplateRead | None:
    template = db.scalar(
        select(ContractTemplate).where(
            ContractTemplate.id == template_id,
            ContractTemplate.organization_id == principal.organization_id,
            ContractTemplate.deleted_at.is_(None),
        )
    )
    if template is None:
        return None
    template.status = "approved"
    template.approved_by_user_id = principal.user_id
    template.approved_at = datetime.now(UTC)
    db.commit()
    db.refresh(template)
    return template_read(template)


def configure_template_provider(
    db: Session,
    principal: Principal,
    template_id: UUID,
    payload: ContractTemplateProviderUpdate,
) -> ContractTemplateRead | None:
    template = db.scalar(
        select(ContractTemplate).where(
            ContractTemplate.id == template_id,
            ContractTemplate.organization_id == principal.organization_id,
            ContractTemplate.deleted_at.is_(None),
        )
    )
    if template is None:
        return None
    template.esign_provider_template_id = payload.esign_provider_template_id.strip()
    template.esign_field_mapping = {
        key.strip(): value.strip()
        for key, value in payload.esign_field_mapping.items()
        if key.strip() and value.strip()
    }
    db.add(
        AuditEvent(
            organization_id=principal.organization_id,
            actor_user_id=principal.user_id,
            actor_type="user",
            action="contract_template.esign_configure",
            entity_type="contract_template",
            entity_id=template.id,
            previous_value=None,
            new_value={
                "provider_template_id": template.esign_provider_template_id,
                "field_keys": sorted(template.esign_field_mapping),
            },
            reason="E-signature template mapping configured",
        )
    )
    db.commit()
    db.refresh(template)
    return template_read(template)


def package_read(item: ContractPackage) -> ContractPackageRead:
    binding = (item.terms_snapshot or {}).get("disposition_buyer_binding")
    buyer_identity = binding.get("buyer_identity_snapshot") if isinstance(binding, dict) else None
    assignee_name = None
    assignee_email = None
    if isinstance(buyer_identity, dict):
        assignee_name = (
            str(buyer_identity.get("company_name") or buyer_identity.get("name") or "").strip()
            or None
        )
        assignee_email = str(buyer_identity.get("email") or "").strip() or None
    return ContractPackageRead(
        id=item.id,
        version_number=item.version_number,
        template_id=item.template_id,
        document_type=str(item.terms_snapshot.get("document_type") or "purchase_agreement"),
        status=item.status,
        seller_name=item.seller_name,
        buyer_entity_name=item.buyer_entity_name,
        assignee_name=assignee_name,
        assignee_email=assignee_email,
        purchase_price_cents=item.purchase_price_cents,
        earnest_money_cents=item.earnest_money_cents,
        closing_date=item.closing_date,
        inspection_period_days=item.inspection_period_days,
        approval_request_id=item.approval_request_id,
        authority_snapshot=package_purchase_authority_snapshot(item),
        notes=item.notes,
        approved_at=item.approved_at,
        sent_at=item.sent_at,
        executed_at=item.executed_at,
        created_at=item.created_at,
    )


def document_read(
    item: TransactionDocument,
    facts: list[TransactionDocumentFactRead] | None = None,
) -> TransactionDocumentRead:
    return TransactionDocumentRead(
        id=item.id,
        contract_package_id=item.contract_package_id,
        document_type=item.document_type,
        title=item.title,
        status=item.status,
        file_name=item.file_name,
        content_type=item.content_type,
        file_size=item.file_size,
        storage_provider=item.storage_provider,
        malware_scan_status=item.malware_scan_status,
        retention_until=item.retention_until,
        occurred_at=item.occurred_at,
        notes=item.notes,
        download_url=f"/api/v1/transactions/{item.transaction_id}/documents/{item.id}/content",
        facts=facts or [],
    )


def document_fact_read(
    item: TransactionDocumentFact,
    reviewed_by_name: str | None,
) -> TransactionDocumentFactRead:
    return TransactionDocumentFactRead(
        id=item.id,
        document_id=item.document_id,
        field_key=item.field_key,
        value_text=item.value_text,
        source_page=item.source_page,
        source_excerpt=item.source_excerpt,
        extraction_method=item.extraction_method,
        status=item.status,
        confidence_score=item.confidence_score,
        reviewed_by_name=reviewed_by_name,
        reviewed_at=item.reviewed_at,
        created_at=item.created_at,
    )


def template_read(item: ContractTemplate) -> ContractTemplateRead:
    return ContractTemplateRead(
        id=item.id,
        document_type=item.document_type,
        state_code=item.state_code,
        name=item.name,
        version_number=item.version_number,
        status=item.status,
        file_name=item.file_name,
        storage_provider=item.storage_provider,
        malware_scan_status=item.malware_scan_status,
        retention_until=item.retention_until,
        esign_provider_template_id=item.esign_provider_template_id,
        esign_field_mapping={
            str(key): str(value) for key, value in (item.esign_field_mapping or {}).items()
        },
        approved_at=item.approved_at,
        created_at=item.created_at,
    )
