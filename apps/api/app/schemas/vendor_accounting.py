from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, model_validator


class VendorProfileCreate(BaseModel):
    counterparty_id: UUID | None = None
    name: str | None = Field(default=None, max_length=255)
    company_name: str | None = Field(default=None, max_length=255)
    email: str | None = Field(default=None, max_length=320)
    phone: str | None = Field(default=None, max_length=40)
    vendor_type: Literal[
        "vendor",
        "contractor",
        "closing_service",
        "funding_partner",
        "other",
    ]
    default_expense_account_key: str | None = Field(default=None, max_length=120)
    payment_terms_days: int = Field(default=0, ge=0, le=365)
    tax_reportable: bool = False
    w9_status: Literal["not_requested", "requested", "not_required"] = "not_requested"
    remittance_address: str | None = Field(default=None, max_length=1000)
    notes: str | None = Field(default=None, max_length=2000)

    @model_validator(mode="after")
    def require_existing_or_new_counterparty(self) -> "VendorProfileCreate":
        if self.counterparty_id is None and not (self.name or "").strip():
            raise ValueError("Enter a vendor name or select an existing counterparty.")
        return self


class VendorProfileUpdate(BaseModel):
    vendor_type: Literal[
        "vendor",
        "contractor",
        "closing_service",
        "funding_partner",
        "other",
    ]
    status: Literal["active", "inactive"]
    default_expense_account_key: str | None = Field(default=None, max_length=120)
    payment_terms_days: int = Field(default=0, ge=0, le=365)
    tax_reportable: bool = False
    remittance_address: str | None = Field(default=None, max_length=1000)
    notes: str | None = Field(default=None, max_length=2000)


class VendorW9StatusUpdate(BaseModel):
    status: Literal["requested", "verified", "not_required"]
    notes: str | None = Field(default=None, max_length=1000)


class VendorProfileRead(BaseModel):
    id: UUID
    counterparty_id: UUID
    vendor_type: str
    status: str
    name: str
    company_name: str | None
    email: str | None
    phone: str | None
    default_expense_account_key: str | None
    payment_terms_days: int
    tax_reportable: bool
    w9_status: str
    w9_requested_at: datetime | None
    w9_received_at: datetime | None
    w9_verified_at: datetime | None
    remittance_address: str | None
    notes: str | None
    paid_year_to_date_cents: int
    open_bill_count: int
    document_count: int
    created_at: datetime


class VendorBillLineCreate(BaseModel):
    description: str = Field(min_length=1, max_length=1000)
    amount_cents: int = Field(ge=1)
    expense_account_key: str = Field(min_length=1, max_length=120)
    deal_id: UUID | None = None
    transaction_id: UUID | None = None


class VendorBillCreate(BaseModel):
    vendor_profile_id: UUID
    bill_number: str | None = Field(default=None, max_length=120)
    issue_at: datetime | None = None
    due_at: datetime | None = None
    description: str = Field(min_length=1, max_length=1000)
    notes: str | None = Field(default=None, max_length=2000)
    lines: list[VendorBillLineCreate] = Field(min_length=1, max_length=50)


class VendorBillLineRead(BaseModel):
    id: UUID
    line_number: int
    description: str
    amount_cents: int
    expense_account_key: str
    deal_id: UUID | None
    transaction_id: UUID | None


class VendorBillRead(BaseModel):
    id: UUID
    vendor_profile_id: UUID
    vendor_name: str
    financial_obligation_id: UUID | None
    bill_number: str
    status: str
    issue_at: datetime
    due_at: datetime | None
    amount_cents: int
    currency: str
    description: str
    approved_at: datetime | None
    paid_at: datetime | None
    payment_reference: str | None
    notes: str | None
    evidence_count: int
    evidence_references: list[str]
    lines: list[VendorBillLineRead]
    created_at: datetime


class FinanceDocumentRead(BaseModel):
    id: UUID
    vendor_profile_id: UUID | None
    vendor_bill_id: UUID | None
    financial_obligation_id: UUID | None
    transaction_id: UUID | None
    document_type: str
    title: str
    status: str
    is_sensitive: bool
    file_name: str
    content_type: str
    file_size: int
    storage_provider: str
    malware_scan_status: str
    retention_until: datetime | None
    occurred_at: datetime
    notes: str | None
    content_path: str


class FinanceDocumentDelete(BaseModel):
    reason: str = Field(min_length=3, max_length=1000)


class VendorAccountingSummary(BaseModel):
    active_vendors: int
    contractors: int
    w9_action_required: int
    draft_bills: int
    open_payables: int
    overdue_bills: int
    open_payable_cents: int
    paid_year_to_date_cents: int
    private_documents: int


class VendorAccountingWorkspaceRead(BaseModel):
    summary: VendorAccountingSummary
    vendors: list[VendorProfileRead]
    bills: list[VendorBillRead]
    documents: list[FinanceDocumentRead]
