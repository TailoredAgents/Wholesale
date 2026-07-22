from datetime import UTC, datetime, timedelta
from hashlib import sha256
from typing import Any
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.auth import Principal
from app.models.foundation import (
    ApprovalRequest,
    AuditEvent,
    Contact,
    ContractPackage,
    ContractTemplate,
    Deal,
    Lead,
    Property,
    Transaction,
    TransactionChecklistItem,
    TransactionDocument,
    TransactionEvent,
    TransactionParty,
    User,
)
from app.schemas.approvals import ApprovalDecision
from app.schemas.transactions import (
    ChecklistItemUpdate,
    ContractPackageCreate,
    ContractPackageRead,
    ContractTemplateRead,
    TransactionChecklistRead,
    TransactionClose,
    TransactionDetail,
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

ACTIVE_STATUSES = ("contract_prep", "approval_pending", "sent", "executed", "closing")
SIGNED_DOCUMENT_TYPES = {"signed_purchase_agreement", "executed_addendum"}
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
        .where(TransactionDocument.transaction_id == transaction.id)
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
        documents=[document_read(item) for item in documents],
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
    db.commit()
    return get_transaction_detail(db, principal, transaction.id)


def create_contract_package(
    db: Session, principal: Principal, transaction_id: UUID, payload: ContractPackageCreate
) -> ContractPackageRead | None:
    transaction = scoped_transaction(db, principal, transaction_id)
    if transaction is None:
        return None
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
        earnest_money_cents=payload.earnest_money_cents,
        closing_date=payload.closing_date,
        inspection_period_days=payload.inspection_period_days,
        terms_snapshot={"special_terms": payload.special_terms},
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
    transaction = scoped_transaction(db, principal, transaction_id)
    package = db.scalar(
        select(ContractPackage).where(
            ContractPackage.id == package_id,
            ContractPackage.transaction_id == transaction_id,
            ContractPackage.organization_id == principal.organization_id,
        )
    )
    if transaction is None or package is None:
        return None
    if package.status != "draft":
        raise ValueError("Only a draft contract package can be submitted for approval.")
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
    package = db.scalar(
        select(ContractPackage).where(
            ContractPackage.id == request.entity_id,
            ContractPackage.organization_id == principal.organization_id,
        )
    )
    if package is None or package.status != "pending_approval":
        raise ValueError("The contract package is no longer pending approval.")
    transaction = scoped_transaction(db, principal, package.transaction_id)
    if transaction is None:
        raise ValueError("The transaction is no longer available.")
    if payload.status in {"rejected", "cancelled"} and not payload.decision_notes:
        raise ValueError("Decision notes are required when a contract package is not approved.")
    if payload.status == "approved":
        package.status = "approved"
        package.approved_at = datetime.now(UTC)
        transaction.status = "contract_prep"
    else:
        package.status = "draft" if payload.status == "rejected" else "void"
        transaction.status = "contract_prep"
        if payload.status == "cancelled":
            package.voided_at = datetime.now(UTC)
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
    transaction = scoped_transaction(db, principal, transaction_id)
    package = db.scalar(
        select(ContractPackage).where(
            ContractPackage.id == package_id,
            ContractPackage.transaction_id == transaction_id,
            ContractPackage.organization_id == principal.organization_id,
        )
    )
    if transaction is None or package is None:
        return None
    if package.status != "approved":
        raise ValueError("The contract package must be approved before it is sent.")
    now = datetime.now(UTC)
    package.status = "sent"
    package.sent_at = now
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
    transaction = scoped_transaction(db, principal, transaction_id)
    if transaction is None:
        return None
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
    document = TransactionDocument(
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
        sha256=sha256(content).hexdigest(),
        file_data=content,
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


def get_document(
    db: Session, principal: Principal, transaction_id: UUID, document_id: UUID
) -> TransactionDocument | None:
    return db.scalar(
        select(TransactionDocument).where(
            TransactionDocument.organization_id == principal.organization_id,
            TransactionDocument.transaction_id == transaction_id,
            TransactionDocument.id == document_id,
        )
    )


def mark_contract_executed(
    db: Session, principal: Principal, transaction_id: UUID, package_id: UUID, document_id: UUID
) -> ContractPackageRead | None:
    transaction = scoped_transaction(db, principal, transaction_id)
    package = db.scalar(
        select(ContractPackage).where(
            ContractPackage.id == package_id,
            ContractPackage.transaction_id == transaction_id,
            ContractPackage.organization_id == principal.organization_id,
        )
    )
    document = get_document(db, principal, transaction_id, document_id)
    if transaction is None or package is None:
        return None
    if package.status not in {"approved", "sent"}:
        raise ValueError("Only an approved or sent contract package can be executed.")
    if (
        document is None
        or document.contract_package_id != package.id
        or document.document_type not in SIGNED_DOCUMENT_TYPES
    ):
        raise ValueError(
            "Upload the signed purchase agreement to this package before marking it executed."
        )
    now = datetime.now(UTC)
    package.status = "executed"
    package.executed_at = now
    transaction.status = "executed"
    transaction.contract_executed_at = now
    lead = db.get(Lead, transaction.lead_id)
    deal = db.get(Deal, transaction.deal_id)
    if lead:
        lead.stage_key = "under_contract"
    if deal:
        deal.stage_key = "under_contract"
    add_event(
        db,
        principal,
        transaction,
        "contract.executed",
        f"Contract package v{package.version_number} executed.",
        {"document_id": str(document.id)},
    )
    db.commit()
    db.refresh(package)
    return package_read(package)


def add_party(
    db: Session, principal: Principal, transaction_id: UUID, payload: TransactionPartyCreate
) -> TransactionPartyRead | None:
    transaction = scoped_transaction(db, principal, transaction_id)
    if transaction is None:
        return None
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
    transaction = scoped_transaction(db, principal, transaction_id)
    item = db.scalar(
        select(TransactionChecklistItem).where(
            TransactionChecklistItem.id == item_id,
            TransactionChecklistItem.transaction_id == transaction_id,
            TransactionChecklistItem.organization_id == principal.organization_id,
        )
    )
    if transaction is None or item is None:
        return None
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
    db.commit()
    return get_transaction_detail(db, principal, transaction.id)


def record_note(
    db: Session, principal: Principal, transaction_id: UUID, payload: TransactionEventCreate
) -> TransactionEventRead | None:
    transaction = scoped_transaction(db, principal, transaction_id)
    if transaction is None:
        return None
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
    transaction = scoped_transaction(db, principal, transaction_id)
    if transaction is None:
        return None
    now = datetime.now(UTC)
    lead = db.get(Lead, transaction.lead_id)
    deal = db.get(Deal, transaction.deal_id)
    if payload.outcome == "funded":
        executed = db.scalar(
            select(ContractPackage.id).where(
                ContractPackage.transaction_id == transaction.id,
                ContractPackage.status == "executed",
            )
        )
        funding = db.scalar(
            select(TransactionDocument.id).where(
                TransactionDocument.transaction_id == transaction.id,
                TransactionDocument.document_type == "funding_confirmation",
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
        if not executed:
            raise ValueError("An executed purchase agreement is required before funding.")
        if not funding:
            raise ValueError("Upload funding confirmation before closing the transaction.")
        if incomplete:
            raise ValueError(f"Complete the {incomplete} required closing checklist item(s) first.")
        transaction.status = "funded"
        transaction.funded_at = now
        transaction.closed_at = now
        if lead:
            lead.stage_key = "closed"
        if deal:
            deal.stage_key = "closed"
    else:
        transaction.status = "cancelled"
        transaction.cancelled_at = now
        if lead:
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
        {"notes": payload.notes},
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
    template = ContractTemplate(
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
        file_data=content,
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


def package_read(item: ContractPackage) -> ContractPackageRead:
    return ContractPackageRead(
        id=item.id,
        version_number=item.version_number,
        template_id=item.template_id,
        status=item.status,
        seller_name=item.seller_name,
        buyer_entity_name=item.buyer_entity_name,
        purchase_price_cents=item.purchase_price_cents,
        earnest_money_cents=item.earnest_money_cents,
        closing_date=item.closing_date,
        inspection_period_days=item.inspection_period_days,
        approval_request_id=item.approval_request_id,
        notes=item.notes,
        approved_at=item.approved_at,
        sent_at=item.sent_at,
        executed_at=item.executed_at,
        created_at=item.created_at,
    )


def document_read(item: TransactionDocument) -> TransactionDocumentRead:
    return TransactionDocumentRead(
        id=item.id,
        contract_package_id=item.contract_package_id,
        document_type=item.document_type,
        title=item.title,
        status=item.status,
        file_name=item.file_name,
        content_type=item.content_type,
        file_size=item.file_size,
        occurred_at=item.occurred_at,
        notes=item.notes,
        download_url=f"/api/v1/transactions/{item.transaction_id}/documents/{item.id}/content",
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
        approved_at=item.approved_at,
        created_at=item.created_at,
    )
