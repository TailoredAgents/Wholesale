from datetime import UTC, datetime, timedelta
from hashlib import sha256
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.auth import Principal
from app.models.foundation import (
    AccountingAccount,
    AuditEvent,
    BusinessCounterparty,
    Deal,
    FinanceDocument,
    FinancialObligation,
    Transaction,
    VendorBill,
    VendorBillLine,
    VendorProfile,
)
from app.schemas.vendor_accounting import (
    FinanceDocumentRead,
    VendorAccountingSummary,
    VendorAccountingWorkspaceRead,
    VendorBillCreate,
    VendorBillLineRead,
    VendorBillRead,
    VendorProfileCreate,
    VendorProfileRead,
    VendorProfileUpdate,
    VendorW9StatusUpdate,
)
from app.services.document_storage import delete_content, read_content, store_content
from app.services.finance import ensure_accounting_foundation

MAX_FINANCE_DOCUMENT_BYTES = 15 * 1024 * 1024
VENDOR_TYPES = {
    "vendor",
    "contractor",
    "closing_service",
    "funding_partner",
    "other",
}
FINANCE_DOCUMENT_TYPES = {
    "invoice",
    "receipt",
    "w9",
    "payment_evidence",
    "closing_statement",
    "contract",
    "other",
}
OPEN_BILL_STATUSES = {"approved", "payable", "disputed"}


def get_vendor_accounting_workspace(
    db: Session,
    principal: Principal,
) -> VendorAccountingWorkspaceRead:
    vendors = list(
        db.scalars(
            select(VendorProfile)
            .where(VendorProfile.organization_id == principal.organization_id)
            .order_by(VendorProfile.created_at.desc())
        ).all()
    )
    counterparty_ids = {vendor.counterparty_id for vendor in vendors}
    counterparties = {
        item.id: item
        for item in db.scalars(
            select(BusinessCounterparty).where(
                BusinessCounterparty.organization_id == principal.organization_id,
                BusinessCounterparty.id.in_(counterparty_ids),
            )
        ).all()
    }
    bills = list(
        db.scalars(
            select(VendorBill)
            .where(VendorBill.organization_id == principal.organization_id)
            .order_by(VendorBill.issue_at.desc(), VendorBill.created_at.desc())
            .limit(250)
        ).all()
    )
    bill_ids = {bill.id for bill in bills}
    lines_by_bill: dict[UUID, list[VendorBillLine]] = {}
    for line in db.scalars(
        select(VendorBillLine)
        .where(
            VendorBillLine.organization_id == principal.organization_id,
            VendorBillLine.vendor_bill_id.in_(bill_ids),
        )
        .order_by(VendorBillLine.line_number)
    ).all():
        lines_by_bill.setdefault(line.vendor_bill_id, []).append(line)
    documents = list(
        db.scalars(
            select(FinanceDocument)
            .where(
                FinanceDocument.organization_id == principal.organization_id,
                FinanceDocument.deleted_at.is_(None),
            )
            .order_by(FinanceDocument.occurred_at.desc())
            .limit(250)
        ).all()
    )
    documents_by_bill: dict[UUID, list[FinanceDocument]] = {}
    document_counts_by_vendor: dict[UUID, int] = {}
    for document in documents:
        if document.vendor_bill_id is not None:
            documents_by_bill.setdefault(document.vendor_bill_id, []).append(document)
        if document.vendor_profile_id is not None:
            document_counts_by_vendor[document.vendor_profile_id] = (
                document_counts_by_vendor.get(document.vendor_profile_id, 0) + 1
            )
    paid_by_vendor: dict[UUID, int] = {}
    open_by_vendor: dict[UUID, int] = {}
    year_start = datetime(datetime.now(UTC).year, 1, 1, tzinfo=UTC)
    for bill in bills:
        if bill.status in OPEN_BILL_STATUSES:
            open_by_vendor[bill.vendor_profile_id] = (
                open_by_vendor.get(bill.vendor_profile_id, 0) + 1
            )
        if (
            bill.status == "paid"
            and bill.paid_at
            and comparable_datetime(bill.paid_at) >= comparable_datetime(year_start)
        ):
            paid_by_vendor[bill.vendor_profile_id] = (
                paid_by_vendor.get(bill.vendor_profile_id, 0) + bill.amount_cents
            )
    now = datetime.now(UTC)
    overdue_bills = [
        bill
        for bill in bills
        if bill.status in OPEN_BILL_STATUSES
        and bill.due_at is not None
        and comparable_datetime(bill.due_at) < comparable_datetime(now)
    ]
    return VendorAccountingWorkspaceRead(
        summary=VendorAccountingSummary(
            active_vendors=sum(vendor.status == "active" for vendor in vendors),
            contractors=sum(
                vendor.status == "active" and vendor.vendor_type == "contractor"
                for vendor in vendors
            ),
            w9_action_required=sum(
                vendor.status == "active"
                and vendor.tax_reportable
                and vendor.w9_status not in {"verified", "not_required"}
                for vendor in vendors
            ),
            draft_bills=sum(bill.status == "draft" for bill in bills),
            open_payables=sum(bill.status in OPEN_BILL_STATUSES for bill in bills),
            overdue_bills=len(overdue_bills),
            open_payable_cents=sum(
                bill.amount_cents for bill in bills if bill.status in OPEN_BILL_STATUSES
            ),
            paid_year_to_date_cents=sum(paid_by_vendor.values()),
            private_documents=len(documents),
        ),
        vendors=[
            vendor_to_read(
                vendor,
                counterparties[vendor.counterparty_id],
                paid_by_vendor.get(vendor.id, 0),
                open_by_vendor.get(vendor.id, 0),
                document_counts_by_vendor.get(vendor.id, 0),
            )
            for vendor in vendors
            if vendor.counterparty_id in counterparties
        ],
        bills=[
            bill_to_read(
                bill,
                counterparties[
                    next(
                        vendor.counterparty_id
                        for vendor in vendors
                        if vendor.id == bill.vendor_profile_id
                    )
                ],
                lines_by_bill.get(bill.id, []),
                documents_by_bill.get(bill.id, []),
            )
            for bill in bills
        ],
        documents=[finance_document_to_read(document) for document in documents],
    )


def create_vendor_profile(
    db: Session,
    principal: Principal,
    payload: VendorProfileCreate,
) -> VendorProfileRead:
    if payload.vendor_type not in VENDOR_TYPES:
        raise ValueError("Unsupported vendor type.")
    validate_expense_account(
        db,
        principal,
        payload.default_expense_account_key,
        required=False,
    )
    counterparty = None
    if payload.counterparty_id is not None:
        counterparty = db.scalar(
            select(BusinessCounterparty).where(
                BusinessCounterparty.organization_id == principal.organization_id,
                BusinessCounterparty.id == payload.counterparty_id,
            )
        )
        if counterparty is None:
            raise ValueError("Business counterparty not found.")
    else:
        counterparty = BusinessCounterparty(
            organization_id=principal.organization_id,
            market_id=None,
            counterparty_type=payload.vendor_type,
            name=(payload.name or "").strip(),
            company_name=clean(payload.company_name),
            email=clean(payload.email),
            phone=clean(payload.phone),
            status="verified",
            verified_by_user_id=principal.user_id,
            verified_at=datetime.now(UTC),
            notes=clean(payload.notes),
        )
        db.add(counterparty)
        db.flush()
    existing = db.scalar(
        select(VendorProfile).where(
            VendorProfile.organization_id == principal.organization_id,
            VendorProfile.counterparty_id == counterparty.id,
        )
    )
    if existing is not None:
        raise ValueError("This counterparty already has a finance vendor profile.")
    now = datetime.now(UTC)
    vendor = VendorProfile(
        organization_id=principal.organization_id,
        counterparty_id=counterparty.id,
        vendor_type=payload.vendor_type,
        status="active",
        default_expense_account_key=payload.default_expense_account_key,
        payment_terms_days=payload.payment_terms_days,
        tax_reportable=payload.tax_reportable,
        w9_status=payload.w9_status,
        w9_requested_at=now if payload.w9_status == "requested" else None,
        w9_received_at=None,
        w9_verified_at=None,
        w9_verified_by_user_id=None,
        remittance_address=clean(payload.remittance_address),
        created_by_user_id=principal.user_id,
        notes=clean(payload.notes),
    )
    db.add(vendor)
    db.flush()
    add_vendor_audit(
        db,
        principal,
        "finance.vendor_create",
        "vendor_profile",
        vendor.id,
        None,
        vendor_snapshot(vendor),
        "Finance vendor profile created on the shared counterparty.",
    )
    db.commit()
    db.refresh(vendor)
    return vendor_to_read(vendor, counterparty, 0, 0, 0)


def update_vendor_profile(
    db: Session,
    principal: Principal,
    vendor_id: UUID,
    payload: VendorProfileUpdate,
) -> VendorProfileRead | None:
    vendor = scoped_vendor(db, principal, vendor_id, for_update=True)
    if vendor is None:
        return None
    validate_expense_account(
        db,
        principal,
        payload.default_expense_account_key,
        required=False,
    )
    previous = vendor_snapshot(vendor)
    vendor.vendor_type = payload.vendor_type
    vendor.status = payload.status
    vendor.default_expense_account_key = payload.default_expense_account_key
    vendor.payment_terms_days = payload.payment_terms_days
    vendor.tax_reportable = payload.tax_reportable
    vendor.remittance_address = clean(payload.remittance_address)
    vendor.notes = clean(payload.notes)
    add_vendor_audit(
        db,
        principal,
        "finance.vendor_update",
        "vendor_profile",
        vendor.id,
        previous,
        vendor_snapshot(vendor),
        "Finance vendor profile updated.",
    )
    db.commit()
    db.refresh(vendor)
    counterparty = db.get(BusinessCounterparty, vendor.counterparty_id)
    if counterparty is None:
        raise ValueError("Vendor counterparty is unavailable.")
    return vendor_to_read(vendor, counterparty, 0, 0, 0)


def update_vendor_w9_status(
    db: Session,
    principal: Principal,
    vendor_id: UUID,
    payload: VendorW9StatusUpdate,
) -> VendorProfileRead | None:
    vendor = scoped_vendor(db, principal, vendor_id, for_update=True)
    if vendor is None:
        return None
    if payload.status == "verified":
        document = db.scalar(
            select(FinanceDocument).where(
                FinanceDocument.organization_id == principal.organization_id,
                FinanceDocument.vendor_profile_id == vendor.id,
                FinanceDocument.document_type == "w9",
                FinanceDocument.deleted_at.is_(None),
            )
        )
        if document is None:
            raise ValueError("Upload the vendor W-9 before marking it verified.")
    previous = vendor_snapshot(vendor)
    now = datetime.now(UTC)
    vendor.w9_status = payload.status
    if payload.status == "requested":
        vendor.w9_requested_at = now
    if payload.status == "verified":
        vendor.w9_verified_at = now
        vendor.w9_verified_by_user_id = principal.user_id
    if payload.notes:
        vendor.notes = append_note(vendor.notes, payload.notes)
    add_vendor_audit(
        db,
        principal,
        "finance.vendor_w9_status",
        "vendor_profile",
        vendor.id,
        previous,
        vendor_snapshot(vendor),
        payload.notes or "Vendor W-9 status updated.",
    )
    db.commit()
    db.refresh(vendor)
    counterparty = db.get(BusinessCounterparty, vendor.counterparty_id)
    if counterparty is None:
        raise ValueError("Vendor counterparty is unavailable.")
    return vendor_to_read(vendor, counterparty, 0, 0, 0)


def create_vendor_bill(
    db: Session,
    principal: Principal,
    payload: VendorBillCreate,
) -> VendorBillRead:
    vendor = scoped_vendor(db, principal, payload.vendor_profile_id)
    if vendor is None or vendor.status != "active":
        raise ValueError("Select an active finance vendor.")
    profile = ensure_accounting_foundation(db, principal)
    account_keys = {line.expense_account_key for line in payload.lines}
    accounts = list(
        db.scalars(
            select(AccountingAccount).where(
                AccountingAccount.organization_id == principal.organization_id,
                AccountingAccount.policy_version == profile.policy_version,
                AccountingAccount.system_key.in_(account_keys),
                AccountingAccount.is_active.is_(True),
            )
        ).all()
    )
    if {account.system_key for account in accounts} != account_keys:
        raise ValueError("Every bill line must use an active expense account.")
    if any(
        account.account_type not in {"expense", "cost_of_revenue"}
        for account in accounts
    ):
        raise ValueError("Bill lines must use expense or cost-of-revenue accounts.")
    for line in payload.lines:
        validate_bill_line_links(db, principal, line.deal_id, line.transaction_id)
    issue_at = payload.issue_at or datetime.now(UTC)
    due_at = payload.due_at or (
        issue_at + timedelta(days=vendor.payment_terms_days)
        if vendor.payment_terms_days
        else None
    )
    if due_at is not None and comparable_datetime(due_at) < comparable_datetime(issue_at):
        raise ValueError("Bill due date cannot be before its issue date.")
    bill_id = uuid4()
    bill_number = clean(payload.bill_number) or f"BILL-{str(bill_id)[:8].upper()}"
    duplicate_bill = db.scalar(
        select(VendorBill.id).where(
            VendorBill.organization_id == principal.organization_id,
            VendorBill.vendor_profile_id == vendor.id,
            VendorBill.bill_number == bill_number,
        )
    )
    if duplicate_bill is not None:
        raise ValueError("This vendor bill number is already recorded.")
    bill = VendorBill(
        id=bill_id,
        organization_id=principal.organization_id,
        vendor_profile_id=vendor.id,
        financial_obligation_id=None,
        deal_id=single_link({line.deal_id for line in payload.lines}),
        transaction_id=single_link({line.transaction_id for line in payload.lines}),
        bill_number=bill_number,
        status="draft",
        issue_at=issue_at,
        due_at=due_at,
        amount_cents=sum(line.amount_cents for line in payload.lines),
        currency=profile.currency,
        description=payload.description.strip(),
        created_by_user_id=principal.user_id,
        approved_by_user_id=None,
        approved_at=None,
        paid_at=None,
        payment_reference=None,
        notes=clean(payload.notes),
    )
    db.add(bill)
    db.flush()
    bill_lines: list[VendorBillLine] = []
    for line_number, payload_line in enumerate(payload.lines, start=1):
        vendor_bill_line = VendorBillLine(
            organization_id=principal.organization_id,
            vendor_bill_id=bill.id,
            line_number=line_number,
            description=payload_line.description.strip(),
            amount_cents=payload_line.amount_cents,
            expense_account_key=payload_line.expense_account_key,
            deal_id=payload_line.deal_id,
            transaction_id=payload_line.transaction_id,
        )
        db.add(vendor_bill_line)
        bill_lines.append(vendor_bill_line)
    add_vendor_audit(
        db,
        principal,
        "finance.vendor_bill_create",
        "vendor_bill",
        bill.id,
        None,
        bill_snapshot(bill),
        "Vendor bill created as a draft.",
    )
    db.commit()
    db.refresh(bill)
    counterparty = db.get(BusinessCounterparty, vendor.counterparty_id)
    if counterparty is None:
        raise ValueError("Vendor counterparty is unavailable.")
    return bill_to_read(bill, counterparty, bill_lines, [])


def approve_vendor_bill(
    db: Session,
    principal: Principal,
    bill_id: UUID,
) -> VendorBillRead | None:
    bill = scoped_bill(db, principal, bill_id, for_update=True)
    if bill is None:
        return None
    if bill.status != "draft":
        if bill.status in {"approved", "payable", "paid"}:
            return load_bill_read(db, principal, bill)
        raise ValueError("Only a draft bill can be approved.")
    vendor = scoped_vendor(db, principal, bill.vendor_profile_id)
    if vendor is None or vendor.status != "active":
        raise ValueError("The bill vendor is not active.")
    lines = bill_lines(db, principal, bill.id)
    if not lines or sum(line.amount_cents for line in lines) != bill.amount_cents:
        raise ValueError("Bill line totals do not match the bill amount.")
    evidence = bill_evidence_references(db, principal, bill.id)
    now = datetime.now(UTC)
    obligation = FinancialObligation(
        organization_id=principal.organization_id,
        obligation_type=(
            "contractor_payable"
            if vendor.vendor_type == "contractor"
            else "vendor_payable"
        ),
        direction="outbound",
        counterparty_name=vendor_name(db, vendor),
        user_id=None,
        expense_account_key=lines[0].expense_account_key,
        amount_cents=bill.amount_cents,
        status="approved",
        source_type="vendor_bill",
        source_id=str(bill.id),
        due_at=bill.due_at,
        approved_by_user_id=principal.user_id,
        approved_at=now,
        paid_at=None,
        payment_reference=None,
        evidence_references=evidence,
        notes=bill.description,
    )
    db.add(obligation)
    db.flush()
    previous = bill_snapshot(bill)
    bill.status = "approved"
    bill.financial_obligation_id = obligation.id
    bill.approved_by_user_id = principal.user_id
    bill.approved_at = now
    existing_documents = list(
        db.scalars(
            select(FinanceDocument).where(
                FinanceDocument.organization_id == principal.organization_id,
                FinanceDocument.vendor_bill_id == bill.id,
                FinanceDocument.deleted_at.is_(None),
            )
        ).all()
    )
    for document in existing_documents:
        document.financial_obligation_id = obligation.id
    add_vendor_audit(
        db,
        principal,
        "finance.vendor_bill_approve",
        "vendor_bill",
        bill.id,
        previous,
        bill_snapshot(bill),
        "Bill approved and linked to an existing F6C obligation.",
    )
    db.commit()
    db.refresh(bill)
    return load_bill_read(db, principal, bill)


def upload_finance_document(
    db: Session,
    principal: Principal,
    *,
    content: bytes,
    file_name: str,
    content_type: str,
    document_type: str,
    title: str,
    vendor_profile_id: UUID | None,
    vendor_bill_id: UUID | None,
    transaction_id: UUID | None,
    notes: str | None,
) -> FinanceDocumentRead:
    if document_type not in FINANCE_DOCUMENT_TYPES:
        raise ValueError("Unsupported finance document type.")
    if not content or len(content) > MAX_FINANCE_DOCUMENT_BYTES:
        raise ValueError("Document must be between 1 byte and 15 MB.")
    vendor = (
        scoped_vendor(db, principal, vendor_profile_id)
        if vendor_profile_id is not None
        else None
    )
    if vendor_profile_id is not None and vendor is None:
        raise ValueError("Finance vendor not found.")
    bill = (
        scoped_bill(db, principal, vendor_bill_id)
        if vendor_bill_id is not None
        else None
    )
    if vendor_bill_id is not None and bill is None:
        raise ValueError("Vendor bill not found.")
    if bill is not None:
        if vendor is not None and vendor.id != bill.vendor_profile_id:
            raise ValueError("The bill does not belong to the selected vendor.")
        vendor = scoped_vendor(db, principal, bill.vendor_profile_id)
        vendor_profile_id = bill.vendor_profile_id
    if document_type == "w9" and vendor is None:
        raise ValueError("A W-9 must be attached to a finance vendor.")
    if transaction_id is not None:
        transaction = db.scalar(
            select(Transaction.id).where(
                Transaction.organization_id == principal.organization_id,
                Transaction.id == transaction_id,
            )
        )
        if transaction is None:
            raise ValueError("Transaction not found.")
    checksum = sha256(content).hexdigest()
    duplicate = db.scalar(
        select(FinanceDocument).where(
            FinanceDocument.organization_id == principal.organization_id,
            FinanceDocument.sha256 == checksum,
            FinanceDocument.deleted_at.is_(None),
        )
    )
    if duplicate is not None:
        raise ValueError(f"This file is already stored as '{duplicate.title}'.")
    document_id = uuid4()
    stored = store_content(
        organization_id=principal.organization_id,
        namespace=(
            f"finance/vendors/{vendor_profile_id}"
            if vendor_profile_id
            else "finance/general"
        ),
        record_id=document_id,
        file_name=file_name,
        content_type=content_type,
        content=content,
    )
    document = FinanceDocument(
        id=document_id,
        organization_id=principal.organization_id,
        vendor_profile_id=vendor_profile_id,
        vendor_bill_id=bill.id if bill else None,
        financial_obligation_id=bill.financial_obligation_id if bill else None,
        transaction_id=transaction_id or (bill.transaction_id if bill else None),
        uploaded_by_user_id=principal.user_id,
        document_type=document_type,
        title=title.strip(),
        status="available",
        is_sensitive=document_type == "w9",
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
        notes=clean(notes),
    )
    db.add(document)
    db.flush()
    reference = f"finance_document:{document.id}"
    if bill is not None and bill.financial_obligation_id is not None:
        obligation = db.get(FinancialObligation, bill.financial_obligation_id)
        if (
            obligation is not None
            and obligation.organization_id == principal.organization_id
            and reference not in obligation.evidence_references
        ):
            obligation.evidence_references = [
                *obligation.evidence_references,
                reference,
            ]
    if vendor is not None and document_type == "w9":
        vendor.w9_status = "received"
        vendor.w9_received_at = datetime.now(UTC)
        vendor.w9_verified_at = None
        vendor.w9_verified_by_user_id = None
    add_vendor_audit(
        db,
        principal,
        "finance.document_upload",
        "finance_document",
        document.id,
        None,
        {
            "document_type": document.document_type,
            "vendor_profile_id": (
                str(document.vendor_profile_id) if document.vendor_profile_id else None
            ),
            "vendor_bill_id": (
                str(document.vendor_bill_id) if document.vendor_bill_id else None
            ),
            "is_sensitive": document.is_sensitive,
            "sha256": document.sha256,
        },
        "Private finance evidence uploaded.",
    )
    db.commit()
    db.refresh(document)
    return finance_document_to_read(document)


def get_finance_document(
    db: Session,
    principal: Principal,
    document_id: UUID,
) -> FinanceDocument | None:
    return db.scalar(
        select(FinanceDocument).where(
            FinanceDocument.organization_id == principal.organization_id,
            FinanceDocument.id == document_id,
            FinanceDocument.deleted_at.is_(None),
        )
    )


def get_finance_document_content(
    db: Session,
    principal: Principal,
    document: FinanceDocument,
) -> bytes:
    content = read_content(
        provider=document.storage_provider,
        key=document.storage_key,
        database_bytes=document.file_data,
    )
    add_vendor_audit(
        db,
        principal,
        "finance.document_access",
        "finance_document",
        document.id,
        None,
        {
            "document_type": document.document_type,
            "is_sensitive": document.is_sensitive,
        },
        "Private finance evidence accessed.",
    )
    db.commit()
    return content


def delete_finance_document(
    db: Session,
    principal: Principal,
    document_id: UUID,
    reason: str,
) -> bool:
    document = get_finance_document(db, principal, document_id)
    if document is None:
        return False
    delete_content(provider=document.storage_provider, key=document.storage_key)
    now = datetime.now(UTC)
    previous: dict[str, object] = {
        "status": document.status,
        "sha256": document.sha256,
        "document_type": document.document_type,
    }
    document.status = "deleted"
    document.deleted_at = now
    document.file_data = None
    if document.vendor_profile_id is not None and document.document_type == "w9":
        remaining_w9 = db.scalar(
            select(FinanceDocument.id).where(
                FinanceDocument.organization_id == principal.organization_id,
                FinanceDocument.vendor_profile_id == document.vendor_profile_id,
                FinanceDocument.document_type == "w9",
                FinanceDocument.id != document.id,
                FinanceDocument.deleted_at.is_(None),
            )
        )
        if remaining_w9 is None:
            vendor = scoped_vendor(db, principal, document.vendor_profile_id)
            if vendor is not None:
                vendor.w9_status = "not_requested"
                vendor.w9_received_at = None
                vendor.w9_verified_at = None
                vendor.w9_verified_by_user_id = None
    add_vendor_audit(
        db,
        principal,
        "finance.document_delete",
        "finance_document",
        document.id,
        previous,
        {"status": "deleted", "deleted_at": now.isoformat()},
        reason,
    )
    db.commit()
    return True


def scoped_vendor(
    db: Session,
    principal: Principal,
    vendor_id: UUID,
    *,
    for_update: bool = False,
) -> VendorProfile | None:
    query = select(VendorProfile).where(
        VendorProfile.organization_id == principal.organization_id,
        VendorProfile.id == vendor_id,
    )
    if for_update:
        query = query.with_for_update()
    return db.scalar(query)


def scoped_bill(
    db: Session,
    principal: Principal,
    bill_id: UUID,
    *,
    for_update: bool = False,
) -> VendorBill | None:
    query = select(VendorBill).where(
        VendorBill.organization_id == principal.organization_id,
        VendorBill.id == bill_id,
    )
    if for_update:
        query = query.with_for_update()
    return db.scalar(query)


def validate_expense_account(
    db: Session,
    principal: Principal,
    account_key: str | None,
    *,
    required: bool,
) -> None:
    if not account_key:
        if required:
            raise ValueError("Select an expense account.")
        return
    profile = ensure_accounting_foundation(db, principal)
    account = db.scalar(
        select(AccountingAccount).where(
            AccountingAccount.organization_id == principal.organization_id,
            AccountingAccount.policy_version == profile.policy_version,
            AccountingAccount.system_key == account_key,
            AccountingAccount.is_active.is_(True),
        )
    )
    if account is None or account.account_type not in {"expense", "cost_of_revenue"}:
        raise ValueError("Select an active expense or cost-of-revenue account.")


def validate_bill_line_links(
    db: Session,
    principal: Principal,
    deal_id: UUID | None,
    transaction_id: UUID | None,
) -> None:
    if deal_id is not None:
        deal = db.scalar(
            select(Deal.id).where(
                Deal.organization_id == principal.organization_id,
                Deal.id == deal_id,
            )
        )
        if deal is None:
            raise ValueError("Bill line deal not found.")
    if transaction_id is not None:
        transaction = db.scalar(
            select(Transaction.id).where(
                Transaction.organization_id == principal.organization_id,
                Transaction.id == transaction_id,
            )
        )
        if transaction is None:
            raise ValueError("Bill line transaction not found.")


def load_bill_read(
    db: Session,
    principal: Principal,
    bill: VendorBill,
) -> VendorBillRead:
    vendor = scoped_vendor(db, principal, bill.vendor_profile_id)
    if vendor is None:
        raise ValueError("Bill vendor is unavailable.")
    counterparty = db.get(BusinessCounterparty, vendor.counterparty_id)
    if (
        counterparty is None
        or counterparty.organization_id != principal.organization_id
    ):
        raise ValueError("Bill counterparty is unavailable.")
    documents = list(
        db.scalars(
            select(FinanceDocument).where(
                FinanceDocument.organization_id == principal.organization_id,
                FinanceDocument.vendor_bill_id == bill.id,
                FinanceDocument.deleted_at.is_(None),
            )
        ).all()
    )
    return bill_to_read(
        bill,
        counterparty,
        bill_lines(db, principal, bill.id),
        documents,
    )


def bill_lines(
    db: Session,
    principal: Principal,
    bill_id: UUID,
) -> list[VendorBillLine]:
    return list(
        db.scalars(
            select(VendorBillLine)
            .where(
                VendorBillLine.organization_id == principal.organization_id,
                VendorBillLine.vendor_bill_id == bill_id,
            )
            .order_by(VendorBillLine.line_number)
        ).all()
    )


def bill_evidence_references(
    db: Session,
    principal: Principal,
    bill_id: UUID,
) -> list[str]:
    return [
        f"finance_document:{document_id}"
        for document_id in db.scalars(
            select(FinanceDocument.id).where(
                FinanceDocument.organization_id == principal.organization_id,
                FinanceDocument.vendor_bill_id == bill_id,
                FinanceDocument.deleted_at.is_(None),
            )
        ).all()
    ]


def vendor_name(db: Session, vendor: VendorProfile) -> str:
    counterparty = db.get(BusinessCounterparty, vendor.counterparty_id)
    if counterparty is None:
        raise ValueError("Vendor counterparty is unavailable.")
    return counterparty.company_name or counterparty.name


def vendor_to_read(
    vendor: VendorProfile,
    counterparty: BusinessCounterparty,
    paid_year_to_date_cents: int,
    open_bill_count: int,
    document_count: int,
) -> VendorProfileRead:
    return VendorProfileRead(
        id=vendor.id,
        counterparty_id=vendor.counterparty_id,
        vendor_type=vendor.vendor_type,
        status=vendor.status,
        name=counterparty.name,
        company_name=counterparty.company_name,
        email=counterparty.email,
        phone=counterparty.phone,
        default_expense_account_key=vendor.default_expense_account_key,
        payment_terms_days=vendor.payment_terms_days,
        tax_reportable=vendor.tax_reportable,
        w9_status=vendor.w9_status,
        w9_requested_at=vendor.w9_requested_at,
        w9_received_at=vendor.w9_received_at,
        w9_verified_at=vendor.w9_verified_at,
        remittance_address=vendor.remittance_address,
        notes=vendor.notes,
        paid_year_to_date_cents=paid_year_to_date_cents,
        open_bill_count=open_bill_count,
        document_count=document_count,
        created_at=vendor.created_at,
    )


def bill_to_read(
    bill: VendorBill,
    counterparty: BusinessCounterparty,
    lines: list[VendorBillLine],
    documents: list[FinanceDocument],
) -> VendorBillRead:
    evidence = [f"finance_document:{document.id}" for document in documents]
    return VendorBillRead(
        id=bill.id,
        vendor_profile_id=bill.vendor_profile_id,
        vendor_name=counterparty.company_name or counterparty.name,
        financial_obligation_id=bill.financial_obligation_id,
        bill_number=bill.bill_number,
        status=bill.status,
        issue_at=bill.issue_at,
        due_at=bill.due_at,
        amount_cents=bill.amount_cents,
        currency=bill.currency,
        description=bill.description,
        approved_at=bill.approved_at,
        paid_at=bill.paid_at,
        payment_reference=bill.payment_reference,
        notes=bill.notes,
        evidence_count=len(documents),
        evidence_references=evidence,
        lines=[
            VendorBillLineRead(
                id=line.id,
                line_number=line.line_number,
                description=line.description,
                amount_cents=line.amount_cents,
                expense_account_key=line.expense_account_key,
                deal_id=line.deal_id,
                transaction_id=line.transaction_id,
            )
            for line in lines
        ],
        created_at=bill.created_at,
    )


def finance_document_to_read(document: FinanceDocument) -> FinanceDocumentRead:
    return FinanceDocumentRead(
        id=document.id,
        vendor_profile_id=document.vendor_profile_id,
        vendor_bill_id=document.vendor_bill_id,
        financial_obligation_id=document.financial_obligation_id,
        transaction_id=document.transaction_id,
        document_type=document.document_type,
        title=document.title,
        status=document.status,
        is_sensitive=document.is_sensitive,
        file_name=document.file_name,
        content_type=document.content_type,
        file_size=document.file_size,
        storage_provider=document.storage_provider,
        malware_scan_status=document.malware_scan_status,
        retention_until=document.retention_until,
        occurred_at=document.occurred_at,
        notes=document.notes,
        content_path=f"/api/v1/finance/documents/{document.id}/content",
    )


def vendor_snapshot(vendor: VendorProfile) -> dict[str, object]:
    return {
        "vendor_type": vendor.vendor_type,
        "status": vendor.status,
        "default_expense_account_key": vendor.default_expense_account_key,
        "payment_terms_days": vendor.payment_terms_days,
        "tax_reportable": vendor.tax_reportable,
        "w9_status": vendor.w9_status,
    }


def bill_snapshot(bill: VendorBill) -> dict[str, object]:
    return {
        "bill_number": bill.bill_number,
        "status": bill.status,
        "amount_cents": bill.amount_cents,
        "vendor_profile_id": str(bill.vendor_profile_id),
        "financial_obligation_id": (
            str(bill.financial_obligation_id)
            if bill.financial_obligation_id
            else None
        ),
    }


def add_vendor_audit(
    db: Session,
    principal: Principal,
    action: str,
    entity_type: str,
    entity_id: UUID,
    previous: dict[str, object] | None,
    new: dict[str, object],
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
            previous_value=previous,
            new_value=new,
            reason=reason,
        )
    )


def clean(value: str | None) -> str | None:
    if value is None:
        return None
    result = value.strip()
    return result or None


def append_note(existing: str | None, addition: str) -> str:
    return f"{existing}\n{addition}".strip() if existing else addition.strip()


def single_link(values: set[UUID | None]) -> UUID | None:
    non_null = {value for value in values if value is not None}
    return next(iter(non_null)) if len(non_null) == 1 else None


def comparable_datetime(value: datetime) -> datetime:
    return value if value.tzinfo is None else value.replace(tzinfo=None)
