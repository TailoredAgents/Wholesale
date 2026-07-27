from datetime import date, datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, model_validator


class BankAccountCreate(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    institution_name: str | None = Field(default=None, max_length=160)
    account_type: Literal["checking", "savings", "credit_card", "other"]
    last_four: str | None = Field(default=None, pattern=r"^\d{4}$")
    notes: str | None = Field(default=None, max_length=1000)


class BankAccountRead(BaseModel):
    id: UUID
    name: str
    institution_name: str | None
    account_type: str
    last_four: str | None
    currency: str
    status: str
    notes: str | None
    unmatched_transaction_count: int
    created_at: datetime


class BankImportRequest(BaseModel):
    bank_account_id: UUID
    file_name: str = Field(min_length=1, max_length=255)
    csv_content: str = Field(min_length=1, max_length=5_000_000)
    field_mapping: dict[str, str] = Field(min_length=3, max_length=8)
    opening_balance_cents: int | None = None
    closing_balance_cents: int | None = None

    @model_validator(mode="after")
    def mapping_is_supported(self) -> "BankImportRequest":
        allowed = {"date", "description", "amount", "debit", "credit", "balance", "external_id"}
        unsupported = set(self.field_mapping) - allowed
        if unsupported:
            raise ValueError(f"Unsupported bank mapping fields: {', '.join(sorted(unsupported))}.")
        if not {"amount", "debit", "credit"}.intersection(self.field_mapping):
            raise ValueError("Map an amount column or both debit and credit columns.")
        if "date" not in self.field_mapping or "description" not in self.field_mapping:
            raise ValueError("Map a date and description column.")
        if len(set(self.field_mapping.values())) != len(self.field_mapping):
            raise ValueError("Each CSV column can map to only one bank field.")
        return self


class BankImportPreviewRow(BaseModel):
    row_number: int
    status: str
    occurred_on: date | None
    description: str | None
    amount_cents: int | None
    balance_cents: int | None
    validation_errors: list[str]


class BankImportPreview(BaseModel):
    headers: list[str]
    total_rows: int
    valid_rows: int
    invalid_rows: int
    duplicate_rows: int
    can_import: bool
    rows: list[BankImportPreviewRow]


class BankStatementImportRead(BaseModel):
    id: UUID
    bank_account_id: UUID
    file_name: str
    status: str
    total_rows: int
    imported_rows: int
    invalid_rows: int
    duplicate_rows: int
    statement_start_on: date | None
    statement_end_on: date | None
    opening_balance_cents: int | None
    closing_balance_cents: int | None
    malware_scan_status: str
    completed_at: datetime | None
    created_at: datetime


class BankTransactionRead(BaseModel):
    id: UUID
    bank_account_id: UUID
    statement_import_id: UUID
    occurred_on: date
    posted_on: date | None
    description: str
    amount_cents: int
    balance_cents: int | None
    status: str
    journal_entry_id: UUID | None
    journal_entry_number: str | None
    notes: str | None


class BankTransactionMatchCreate(BaseModel):
    journal_entry_id: UUID
    notes: str | None = Field(default=None, max_length=1000)


class BankTransactionStatusUpdate(BaseModel):
    status: Literal["unmatched", "ignored"]
    notes: str | None = Field(default=None, max_length=1000)


class BankReconciliationCreate(BaseModel):
    bank_account_id: UUID
    statement_import_id: UUID | None = None
    statement_start_on: date
    statement_end_on: date
    opening_balance_cents: int
    closing_balance_cents: int
    notes: str | None = Field(default=None, max_length=1000)


class BankReconciliationRead(BaseModel):
    id: UUID
    bank_account_id: UUID
    statement_import_id: UUID | None
    statement_start_on: date
    statement_end_on: date
    opening_balance_cents: int
    closing_balance_cents: int
    calculated_closing_balance_cents: int
    difference_cents: int
    status: str
    matched_transaction_count: int
    unresolved_transaction_count: int
    approved_at: datetime | None
    notes: str | None


class BankingWorkspaceRead(BaseModel):
    accounts: list[BankAccountRead]
    imports: list[BankStatementImportRead]
    transactions: list[BankTransactionRead]
    reconciliations: list[BankReconciliationRead]
    posted_journals: list[dict[str, str | int]]
    summary: dict[str, int]
