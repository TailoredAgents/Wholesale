import csv
import io
from dataclasses import dataclass
from datetime import UTC, date, datetime
from hashlib import sha256
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.auth import Principal
from app.models.foundation import (
    AccountingAccount,
    AuditEvent,
    BankAccount,
    BankReconciliation,
    BankStatementImport,
    BankTransaction,
    BankTransactionMatch,
    JournalEntry,
    JournalLine,
)
from app.schemas.banking import (
    BankAccountCreate,
    BankAccountRead,
    BankingWorkspaceRead,
    BankImportPreview,
    BankImportPreviewRow,
    BankImportRequest,
    BankReconciliationCreate,
    BankReconciliationRead,
    BankStatementImportRead,
    BankTransactionMatchCreate,
    BankTransactionRead,
    BankTransactionStatusUpdate,
)
from app.services.document_storage import store_content
from app.services.finance import ensure_accounting_foundation

MAX_BANK_IMPORT_ROWS = 10_000
MAX_BANK_IMPORT_BYTES = 5_000_000


@dataclass
class PreparedBankRow:
    row_number: int
    occurred_on: date | None
    posted_on: date | None
    description: str | None
    amount_cents: int | None
    balance_cents: int | None
    external_id: str | None
    fingerprint: str | None
    status: str
    validation_errors: list[str]


def get_banking_workspace(db: Session, principal: Principal) -> BankingWorkspaceRead:
    accounts = list(
        db.scalars(
            select(BankAccount)
            .where(BankAccount.organization_id == principal.organization_id)
            .order_by(BankAccount.status, BankAccount.name)
        ).all()
    )
    imports = list(
        db.scalars(
            select(BankStatementImport)
            .where(BankStatementImport.organization_id == principal.organization_id)
            .order_by(BankStatementImport.created_at.desc())
            .limit(100)
        ).all()
    )
    transactions = list(
        db.scalars(
            select(BankTransaction)
            .where(BankTransaction.organization_id == principal.organization_id)
            .order_by(BankTransaction.occurred_on.desc(), BankTransaction.created_at.desc())
            .limit(250)
        ).all()
    )
    matches = {
        match.bank_transaction_id: match
        for match in db.scalars(
            select(BankTransactionMatch).where(
                BankTransactionMatch.organization_id == principal.organization_id,
                BankTransactionMatch.bank_transaction_id.in_({item.id for item in transactions}),
            )
        ).all()
    }
    journal_ids = {match.journal_entry_id for match in matches.values()}
    journals = {
        entry.id: entry
        for entry in db.scalars(
            select(JournalEntry).where(
                JournalEntry.organization_id == principal.organization_id,
                JournalEntry.id.in_(journal_ids),
            )
        ).all()
    }
    reconciliations = list(
        db.scalars(
            select(BankReconciliation)
            .where(BankReconciliation.organization_id == principal.organization_id)
            .order_by(BankReconciliation.statement_end_on.desc())
            .limit(100)
        ).all()
    )
    unmatched_by_account: dict[UUID, int] = {}
    for transaction in transactions:
        if transaction.status == "unmatched":
            unmatched_by_account[transaction.bank_account_id] = (
                unmatched_by_account.get(transaction.bank_account_id, 0) + 1
            )
    profile = ensure_accounting_foundation(db, principal)
    posted_entries = list(
        db.scalars(
            select(JournalEntry)
            .where(
                JournalEntry.organization_id == principal.organization_id,
                JournalEntry.status == "posted",
            )
            .order_by(JournalEntry.entry_date.desc())
            .limit(200)
        ).all()
    )
    cash_deltas = posted_journal_cash_deltas(db, principal, posted_entries, profile.policy_version)
    return BankingWorkspaceRead(
        accounts=[bank_account_read(item, unmatched_by_account.get(item.id, 0)) for item in accounts],
        imports=[statement_import_read(item) for item in imports],
        transactions=[transaction_read(item, matches.get(item.id), journals) for item in transactions],
        reconciliations=[reconciliation_read(db, principal, item) for item in reconciliations],
        posted_journals=[
            {"id": str(entry.id), "entry_number": entry.entry_number, "memo": entry.memo, "cash_delta_cents": cash_deltas.get(entry.id, 0)}
            for entry in posted_entries
            if cash_deltas.get(entry.id, 0)
        ],
        summary={
            "active_accounts": sum(item.status == "active" for item in accounts),
            "unmatched_transactions": sum(item.status == "unmatched" for item in transactions),
            "unreconciled_imports": sum(item.status == "complete" for item in imports),
            "open_reconciliations": sum(item.status != "approved" for item in reconciliations),
        },
    )


def create_bank_account(db: Session, principal: Principal, payload: BankAccountCreate) -> BankAccountRead:
    profile = ensure_accounting_foundation(db, principal)
    account = BankAccount(
        organization_id=principal.organization_id,
        name=payload.name.strip(),
        institution_name=clean(payload.institution_name),
        account_type=payload.account_type,
        last_four=payload.last_four,
        currency=profile.currency,
        status="active",
        created_by_user_id=principal.user_id,
        notes=clean(payload.notes),
    )
    db.add(account)
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise ValueError("A bank or card account with this name already exists.") from exc
    add_audit(db, principal, "finance.bank_account_create", "bank_account", account.id, {"name": account.name, "account_type": account.account_type, "last_four": account.last_four}, "Bank account created without credentials or payment authority.")
    db.commit()
    return bank_account_read(account, 0)


def preview_bank_import(db: Session, principal: Principal, payload: BankImportRequest) -> BankImportPreview:
    account = scoped_account(db, principal, payload.bank_account_id)
    if account is None or account.status != "active":
        raise ValueError("Select an active bank or card account.")
    headers, rows = parse_csv(payload.csv_content)
    validate_mapping_headers(headers, payload.field_mapping)
    existing = set(
        db.scalars(
            select(BankTransaction.fingerprint).where(
                BankTransaction.organization_id == principal.organization_id,
                BankTransaction.bank_account_id == account.id,
            )
        ).all()
    )
    prepared = prepare_rows(rows, payload.field_mapping, existing)
    return import_preview(headers, prepared)


def create_bank_import(db: Session, principal: Principal, payload: BankImportRequest) -> BankStatementImportRead:
    account = scoped_account(db, principal, payload.bank_account_id)
    if account is None or account.status != "active":
        raise ValueError("Select an active bank or card account.")
    content = payload.csv_content.encode("utf-8")
    if len(content) > MAX_BANK_IMPORT_BYTES:
        raise ValueError("Statement files are limited to 5 MB.")
    headers, rows = parse_csv(payload.csv_content)
    validate_mapping_headers(headers, payload.field_mapping)
    existing = set(
        db.scalars(
            select(BankTransaction.fingerprint).where(
                BankTransaction.organization_id == principal.organization_id,
                BankTransaction.bank_account_id == account.id,
            )
        ).all()
    )
    prepared = prepare_rows(rows, payload.field_mapping, existing)
    file_sha = sha256(content).hexdigest()
    duplicate_file = db.scalar(
        select(BankStatementImport.id).where(
            BankStatementImport.organization_id == principal.organization_id,
            BankStatementImport.bank_account_id == account.id,
            BankStatementImport.file_sha256 == file_sha,
        )
    )
    if duplicate_file is not None:
        raise ValueError("This exact statement file has already been imported for this account.")
    stored = store_content(
        organization_id=principal.organization_id,
        namespace=f"finance/banking/{account.id}",
        record_id=UUID(int=int(file_sha[:32], 16)),
        file_name=payload.file_name.strip(),
        content_type="text/csv",
        content=content,
    )
    valid = [item for item in prepared if item.status == "valid"]
    now = datetime.now(UTC)
    statement_import = BankStatementImport(
        organization_id=principal.organization_id,
        bank_account_id=account.id,
        imported_by_user_id=principal.user_id,
        file_name=payload.file_name.strip(),
        file_sha256=file_sha,
        source_format="csv",
        field_mapping=payload.field_mapping,
        status="processing",
        total_rows=len(prepared),
        imported_rows=0,
        invalid_rows=sum(item.status == "invalid" for item in prepared),
        duplicate_rows=sum(item.status == "duplicate" for item in prepared),
        statement_start_on=min(
            (item.occurred_on for item in valid if item.occurred_on is not None),
            default=None,
        ),
        statement_end_on=max(
            (item.occurred_on for item in valid if item.occurred_on is not None),
            default=None,
        ),
        opening_balance_cents=payload.opening_balance_cents,
        closing_balance_cents=payload.closing_balance_cents,
        file_data=stored.database_bytes,
        storage_provider=stored.provider,
        storage_key=stored.key,
        malware_scan_status=stored.malware_scan_status,
        retention_until=stored.retention_until,
        completed_at=None,
    )
    db.add(statement_import)
    db.flush()
    for item in valid:
        db.add(BankTransaction(
            organization_id=principal.organization_id,
            bank_account_id=account.id,
            statement_import_id=statement_import.id,
            row_number=item.row_number,
            external_id=item.external_id,
            occurred_on=item.occurred_on,
            posted_on=item.posted_on,
            description=item.description,
            amount_cents=item.amount_cents,
            balance_cents=item.balance_cents,
            fingerprint=item.fingerprint,
            status="unmatched",
            notes=None,
        ))
    statement_import.imported_rows = len(valid)
    statement_import.status = "complete"
    statement_import.completed_at = now
    add_audit(db, principal, "finance.bank_statement_import", "bank_statement_import", statement_import.id, {"bank_account_id": str(account.id), "file_name": statement_import.file_name, "imported_rows": len(valid), "invalid_rows": statement_import.invalid_rows, "duplicate_rows": statement_import.duplicate_rows}, "Private bank statement imported after row-level validation.")
    db.commit()
    return statement_import_read(statement_import)


def match_bank_transaction(db: Session, principal: Principal, transaction_id: UUID, payload: BankTransactionMatchCreate) -> BankTransactionRead | None:
    transaction = scoped_transaction(db, principal, transaction_id)
    if transaction is None:
        return None
    if transaction.status == "reconciled":
        raise ValueError("A reconciled transaction cannot be rematched.")
    entry = db.scalar(select(JournalEntry).where(JournalEntry.organization_id == principal.organization_id, JournalEntry.id == payload.journal_entry_id, JournalEntry.status == "posted"))
    if entry is None:
        raise ValueError("Select a posted journal entry.")
    profile = ensure_accounting_foundation(db, principal)
    delta = posted_journal_cash_deltas(db, principal, [entry], profile.policy_version).get(entry.id, 0)
    if delta != transaction.amount_cents:
        raise ValueError("The bank transaction amount must equal the journal's operating-cash movement.")
    used = db.scalar(select(BankTransactionMatch.id).where(BankTransactionMatch.organization_id == principal.organization_id, BankTransactionMatch.journal_entry_id == entry.id, BankTransactionMatch.bank_transaction_id != transaction.id))
    if used is not None:
        raise ValueError("This posted journal is already matched to another bank transaction.")
    match = db.scalar(select(BankTransactionMatch).where(BankTransactionMatch.bank_transaction_id == transaction.id))
    if match is None:
        match = BankTransactionMatch(organization_id=principal.organization_id, bank_transaction_id=transaction.id, journal_entry_id=entry.id, match_type="manual_exact", matched_by_user_id=principal.user_id, notes=clean(payload.notes), matched_at=datetime.now(UTC))
        db.add(match)
    else:
        match.journal_entry_id = entry.id
        match.matched_by_user_id = principal.user_id
        match.notes = clean(payload.notes)
        match.matched_at = datetime.now(UTC)
    transaction.status = "matched"
    add_audit(db, principal, "finance.bank_transaction_match", "bank_transaction", transaction.id, {"journal_entry_id": str(entry.id), "amount_cents": transaction.amount_cents}, "Bank transaction manually matched to a posted journal.")
    db.commit()
    return transaction_read(transaction, match, {entry.id: entry})


def update_bank_transaction_status(db: Session, principal: Principal, transaction_id: UUID, payload: BankTransactionStatusUpdate) -> BankTransactionRead | None:
    transaction = scoped_transaction(db, principal, transaction_id)
    if transaction is None:
        return None
    if transaction.status == "reconciled":
        raise ValueError("A reconciled transaction cannot be changed.")
    if payload.status == "unmatched":
        match = db.scalar(select(BankTransactionMatch).where(BankTransactionMatch.bank_transaction_id == transaction.id))
        if match is not None:
            db.delete(match)
    transaction.status = payload.status
    transaction.notes = clean(payload.notes)
    add_audit(db, principal, "finance.bank_transaction_status", "bank_transaction", transaction.id, {"status": payload.status}, "Bank transaction status updated.")
    db.commit()
    return transaction_read(transaction, None, {})


def create_reconciliation(db: Session, principal: Principal, payload: BankReconciliationCreate) -> BankReconciliationRead:
    account = scoped_account(db, principal, payload.bank_account_id)
    if account is None:
        raise ValueError("Bank account not found.")
    if payload.statement_end_on < payload.statement_start_on:
        raise ValueError("Statement end date cannot be before the statement start date.")
    statement_import = None
    if payload.statement_import_id:
        statement_import = db.scalar(select(BankStatementImport).where(BankStatementImport.organization_id == principal.organization_id, BankStatementImport.id == payload.statement_import_id, BankStatementImport.bank_account_id == account.id))
        if statement_import is None:
            raise ValueError("Select a statement import from this account.")
    rows = reconciliation_rows(db, principal, account.id, payload.statement_start_on, payload.statement_end_on, statement_import.id if statement_import else None)
    difference = payload.closing_balance_cents - (payload.opening_balance_cents + sum(item.amount_cents for item in rows))
    unresolved = sum(item.status == "unmatched" for item in rows)
    reconciliation = BankReconciliation(
        organization_id=principal.organization_id,
        bank_account_id=account.id,
        statement_import_id=statement_import.id if statement_import else None,
        statement_start_on=payload.statement_start_on,
        statement_end_on=payload.statement_end_on,
        opening_balance_cents=payload.opening_balance_cents,
        closing_balance_cents=payload.closing_balance_cents,
        calculated_closing_balance_cents=payload.closing_balance_cents - difference,
        difference_cents=difference,
        status="review" if difference == 0 and unresolved == 0 else "draft",
        prepared_by_user_id=principal.user_id,
        approved_by_user_id=None,
        approved_at=None,
        notes=clean(payload.notes),
    )
    db.add(reconciliation)
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise ValueError("A reconciliation already exists for this account and statement end date.") from exc
    add_audit(db, principal, "finance.bank_reconciliation_prepare", "bank_reconciliation", reconciliation.id, {"difference_cents": difference, "unresolved_transactions": unresolved}, "Bank reconciliation prepared for review.")
    db.commit()
    return reconciliation_read(db, principal, reconciliation)


def approve_reconciliation(db: Session, principal: Principal, reconciliation_id: UUID) -> BankReconciliationRead | None:
    reconciliation = db.scalar(select(BankReconciliation).where(BankReconciliation.organization_id == principal.organization_id, BankReconciliation.id == reconciliation_id))
    if reconciliation is None:
        return None
    if reconciliation.status == "approved":
        return reconciliation_read(db, principal, reconciliation)
    rows = reconciliation_rows(db, principal, reconciliation.bank_account_id, reconciliation.statement_start_on, reconciliation.statement_end_on, reconciliation.statement_import_id)
    unresolved = [item for item in rows if item.status == "unmatched"]
    difference = reconciliation.closing_balance_cents - (reconciliation.opening_balance_cents + sum(item.amount_cents for item in rows))
    if difference != 0 or unresolved:
        raise ValueError("Resolve every statement transaction and the balance difference before approval.")
    reconciliation.calculated_closing_balance_cents = reconciliation.closing_balance_cents
    reconciliation.difference_cents = 0
    reconciliation.status = "approved"
    reconciliation.approved_by_user_id = principal.user_id
    reconciliation.approved_at = datetime.now(UTC)
    for item in rows:
        if item.status == "matched":
            item.status = "reconciled"
    add_audit(db, principal, "finance.bank_reconciliation_approve", "bank_reconciliation", reconciliation.id, {"statement_end_on": reconciliation.statement_end_on.isoformat(), "transaction_count": len(rows)}, "Balanced bank reconciliation approved.")
    db.commit()
    return reconciliation_read(db, principal, reconciliation)


def parse_csv(content: str) -> tuple[list[str], list[dict[str, str]]]:
    cleaned = content.lstrip("\ufeff")
    try:
        dialect = csv.Sniffer().sniff(cleaned[:4096], delimiters=",;\t|")
    except csv.Error:
        dialect = csv.excel
    reader = csv.DictReader(io.StringIO(cleaned, newline=""), dialect=dialect)
    if not reader.fieldnames:
        raise ValueError("The CSV requires a header row.")
    headers = [item.strip() for item in reader.fieldnames if item is not None]
    if len(headers) != len(set(headers)):
        raise ValueError("CSV column names must be unique.")
    rows = []
    for row in reader:
        cleaned_row = {str(key).strip(): str(value or "").strip() for key, value in row.items() if key is not None}
        if any(cleaned_row.values()):
            rows.append(cleaned_row)
        if len(rows) > MAX_BANK_IMPORT_ROWS:
            raise ValueError(f"Imports are limited to {MAX_BANK_IMPORT_ROWS:,} data rows.")
    if not rows:
        raise ValueError("The CSV does not contain any transaction rows.")
    return headers, rows


def validate_mapping_headers(headers: list[str], mapping: dict[str, str]) -> None:
    missing = sorted(set(mapping.values()) - set(headers))
    if missing:
        raise ValueError(f"CSV is missing mapped columns: {', '.join(missing)}.")
    if ("debit" in mapping) != ("credit" in mapping) and "amount" not in mapping:
        raise ValueError("Map both debit and credit columns, or map one signed amount column.")


def prepare_rows(rows: list[dict[str, str]], mapping: dict[str, str], existing: set[str]) -> list[PreparedBankRow]:
    seen: set[str] = set()
    prepared = []
    for row_number, raw in enumerate(rows, start=2):
        errors: list[str] = []
        occurred_on = parse_date(raw.get(mapping["date"], ""))
        if occurred_on is None:
            errors.append("Date is invalid.")
        description = clean(raw.get(mapping["description"]))
        if not description:
            errors.append("Description is required.")
        amount = parse_amount(raw.get(mapping["amount"])) if "amount" in mapping else None
        if amount is None and "amount" not in mapping:
            debit = parse_amount(raw.get(mapping["debit"]))
            credit = parse_amount(raw.get(mapping["credit"]))
            if debit is None and credit is None:
                errors.append("Debit or credit amount is required.")
            else:
                amount = (credit or 0) - (debit or 0)
        if amount is None or amount == 0:
            errors.append("Amount must be non-zero.")
        balance = parse_amount(raw.get(mapping["balance"])) if "balance" in mapping else None
        external_id = clean(raw.get(mapping["external_id"])) if "external_id" in mapping else None
        fingerprint = None
        if occurred_on and description and amount is not None:
            fingerprint = sha256(f"{external_id or ''}|{occurred_on.isoformat()}|{description.lower()}|{amount}".encode()).hexdigest()
        status = "invalid" if errors else "valid"
        if status == "valid" and fingerprint in existing | seen:
            status = "duplicate"
        if fingerprint:
            seen.add(fingerprint)
        prepared.append(PreparedBankRow(row_number, occurred_on, None, description, amount, balance, external_id, fingerprint, status, errors))
    return prepared


def import_preview(headers: list[str], rows: list[PreparedBankRow]) -> BankImportPreview:
    return BankImportPreview(headers=headers, total_rows=len(rows), valid_rows=sum(item.status == "valid" for item in rows), invalid_rows=sum(item.status == "invalid" for item in rows), duplicate_rows=sum(item.status == "duplicate" for item in rows), can_import=any(item.status == "valid" for item in rows), rows=[BankImportPreviewRow(row_number=item.row_number, status=item.status, occurred_on=item.occurred_on, description=item.description, amount_cents=item.amount_cents, balance_cents=item.balance_cents, validation_errors=item.validation_errors) for item in rows[:100]])


def parse_date(value: str | None) -> date | None:
    if not value:
        return None
    for pattern in ("%Y-%m-%d", "%m/%d/%Y", "%m/%d/%y"):
        try:
            return datetime.strptime(value.strip(), pattern).date()
        except ValueError:
            continue
    return None


def parse_amount(value: str | None) -> int | None:
    if value is None or not value.strip():
        return None
    cleaned = value.strip().replace("$", "").replace(",", "")
    negative = cleaned.startswith("(") and cleaned.endswith(")")
    if negative:
        cleaned = cleaned[1:-1]
    try:
        cents = round(float(cleaned) * 100)
    except ValueError:
        return None
    return -abs(cents) if negative else cents


def scoped_account(db: Session, principal: Principal, account_id: UUID) -> BankAccount | None:
    return db.scalar(select(BankAccount).where(BankAccount.organization_id == principal.organization_id, BankAccount.id == account_id))


def scoped_transaction(db: Session, principal: Principal, transaction_id: UUID) -> BankTransaction | None:
    return db.scalar(select(BankTransaction).where(BankTransaction.organization_id == principal.organization_id, BankTransaction.id == transaction_id))


def reconciliation_rows(db: Session, principal: Principal, account_id: UUID, start: date, end: date, import_id: UUID | None) -> list[BankTransaction]:
    query = select(BankTransaction).where(BankTransaction.organization_id == principal.organization_id, BankTransaction.bank_account_id == account_id)
    if import_id:
        query = query.where(BankTransaction.statement_import_id == import_id)
    else:
        query = query.where(BankTransaction.occurred_on >= start, BankTransaction.occurred_on <= end)
    return list(db.scalars(query).all())


def posted_journal_cash_deltas(db: Session, principal: Principal, entries: list[JournalEntry], policy_version: int) -> dict[UUID, int]:
    if not entries:
        return {}
    cash_account = db.scalar(select(AccountingAccount).where(AccountingAccount.organization_id == principal.organization_id, AccountingAccount.policy_version == policy_version, AccountingAccount.system_key == "operating_cash", AccountingAccount.is_active.is_(True)))
    if cash_account is None:
        return {}
    totals: dict[UUID, int] = {}
    for line in db.scalars(select(JournalLine).where(JournalLine.journal_entry_id.in_({entry.id for entry in entries}), JournalLine.accounting_account_id == cash_account.id)).all():
        totals[line.journal_entry_id] = totals.get(line.journal_entry_id, 0) + line.debit_cents - line.credit_cents
    return totals


def bank_account_read(item: BankAccount, unmatched: int) -> BankAccountRead:
    return BankAccountRead(id=item.id, name=item.name, institution_name=item.institution_name, account_type=item.account_type, last_four=item.last_four, currency=item.currency, status=item.status, notes=item.notes, unmatched_transaction_count=unmatched, created_at=item.created_at)


def statement_import_read(item: BankStatementImport) -> BankStatementImportRead:
    return BankStatementImportRead(id=item.id, bank_account_id=item.bank_account_id, file_name=item.file_name, status=item.status, total_rows=item.total_rows, imported_rows=item.imported_rows, invalid_rows=item.invalid_rows, duplicate_rows=item.duplicate_rows, statement_start_on=item.statement_start_on, statement_end_on=item.statement_end_on, opening_balance_cents=item.opening_balance_cents, closing_balance_cents=item.closing_balance_cents, malware_scan_status=item.malware_scan_status, completed_at=item.completed_at, created_at=item.created_at)


def transaction_read(item: BankTransaction, match: BankTransactionMatch | None, journals: dict[UUID, JournalEntry]) -> BankTransactionRead:
    entry = journals.get(match.journal_entry_id) if match else None
    return BankTransactionRead(id=item.id, bank_account_id=item.bank_account_id, statement_import_id=item.statement_import_id, occurred_on=item.occurred_on, posted_on=item.posted_on, description=item.description, amount_cents=item.amount_cents, balance_cents=item.balance_cents, status=item.status, journal_entry_id=entry.id if entry else None, journal_entry_number=entry.entry_number if entry else None, notes=item.notes)


def reconciliation_read(db: Session, principal: Principal, item: BankReconciliation) -> BankReconciliationRead:
    rows = reconciliation_rows(db, principal, item.bank_account_id, item.statement_start_on, item.statement_end_on, item.statement_import_id)
    return BankReconciliationRead(id=item.id, bank_account_id=item.bank_account_id, statement_import_id=item.statement_import_id, statement_start_on=item.statement_start_on, statement_end_on=item.statement_end_on, opening_balance_cents=item.opening_balance_cents, closing_balance_cents=item.closing_balance_cents, calculated_closing_balance_cents=item.calculated_closing_balance_cents, difference_cents=item.difference_cents, status=item.status, matched_transaction_count=sum(row.status in {"matched", "reconciled"} for row in rows), unresolved_transaction_count=sum(row.status == "unmatched" for row in rows), approved_at=item.approved_at, notes=item.notes)


def add_audit(db: Session, principal: Principal, action: str, entity_type: str, entity_id: UUID, new: dict[str, object], reason: str) -> None:
    db.add(AuditEvent(organization_id=principal.organization_id, actor_user_id=principal.user_id, actor_type="user", action=action, entity_type=entity_type, entity_id=entity_id, previous_value=None, new_value=new, reason=reason))


def clean(value: str | None) -> str | None:
    return value.strip() or None if value else None
