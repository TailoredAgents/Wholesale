from datetime import date, datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, model_validator

from app.schemas.operations import CampaignRead, OperationsUserRead

SUPPORTED_IMPORT_FIELDS = {
    "source_record_key",
    "legal_name",
    "phone",
    "email",
    "street_address",
    "city",
    "state_code",
    "postal_code",
    "dnc_status",
}


class ProspectImportMappingRead(BaseModel):
    id: UUID
    name: str
    source_name: str | None
    field_mapping: dict[str, str]
    default_values: dict[str, str]
    created_by_user_id: UUID
    created_by_name: str
    is_active: bool
    created_at: datetime


class ProspectImportMappingCreate(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    source_name: str | None = Field(default=None, max_length=160)
    field_mapping: dict[str, str] = Field(min_length=2, max_length=20)
    default_values: dict[str, str] = Field(default_factory=dict, max_length=20)

    @model_validator(mode="after")
    def mapping_is_supported(self) -> "ProspectImportMappingCreate":
        unsupported = set(self.field_mapping) - SUPPORTED_IMPORT_FIELDS
        if unsupported:
            raise ValueError(f"Unsupported import fields: {', '.join(sorted(unsupported))}.")
        if "legal_name" not in self.field_mapping:
            raise ValueError("Map a seller or owner name column.")
        if not {"phone", "email"}.intersection(self.field_mapping):
            raise ValueError("Map a phone or email column.")
        if len(set(self.field_mapping.values())) != len(self.field_mapping):
            raise ValueError("Each CSV column can map to only one Stonegate field.")
        unsupported_defaults = set(self.default_values) - SUPPORTED_IMPORT_FIELDS
        if unsupported_defaults:
            raise ValueError("Default values contain unsupported fields.")
        return self


class ProspectImportRequest(BaseModel):
    campaign_id: UUID
    mapping_id: UUID
    default_assignee_user_id: UUID | None = None
    file_name: str = Field(min_length=1, max_length=255)
    csv_content: str = Field(min_length=1, max_length=5_000_000)


class ProspectImportPreviewRow(BaseModel):
    row_number: int
    status: str
    legal_name: str | None
    phone: str | None
    property_address: str | None
    validation_errors: list[str]
    eligibility_reasons: list[str]
    duplicate_prospect_id: UUID | None


class ProspectImportPreview(BaseModel):
    headers: list[str]
    total_rows: int
    valid_rows: int
    invalid_rows: int
    duplicate_rows: int
    suppressed_rows: int
    review_required_rows: int
    eligible_rows: int
    can_import: bool
    rows: list[ProspectImportPreviewRow]


class ProspectImportRowRead(BaseModel):
    id: UUID
    row_number: int
    status: str
    prospect_id: UUID | None
    duplicate_prospect_id: UUID | None
    legal_name: str | None
    phone: str | None
    property_address: str | None
    validation_errors: list[str]
    eligibility_reasons: list[str]


class ProspectImportBatchRead(BaseModel):
    id: UUID
    campaign_id: UUID
    campaign_name: str
    mapping_id: UUID
    mapping_name: str
    default_assignee_user_id: UUID | None
    default_assignee_name: str | None
    imported_by_user_id: UUID
    imported_by_name: str
    file_name: str
    file_sha256: str
    status: str
    total_rows: int
    valid_rows: int
    imported_rows: int
    invalid_rows: int
    duplicate_rows: int
    suppressed_rows: int
    review_required_rows: int
    completed_at: datetime | None
    created_at: datetime
    rows: list[ProspectImportRowRead]


class CampaignCostRead(BaseModel):
    id: UUID
    campaign_id: UUID
    campaign_name: str
    import_batch_id: UUID | None
    worker_user_id: UUID | None
    worker_name: str | None
    category: str
    vendor_name: str | None
    amount_cents: int
    labor_minutes: int | None
    hourly_rate_cents: int | None
    incurred_on: date
    notes: str | None
    created_at: datetime


class CampaignCostCreate(BaseModel):
    campaign_id: UUID
    import_batch_id: UUID | None = None
    worker_user_id: UUID | None = None
    category: Literal[
        "list_purchase",
        "va_labor",
        "data_enrichment",
        "direct_mail",
        "ad_spend",
        "software",
        "other",
    ]
    vendor_name: str | None = Field(default=None, max_length=160)
    amount_cents: int = Field(ge=0, le=1_000_000_000)
    labor_minutes: int | None = Field(default=None, ge=1, le=100_000)
    hourly_rate_cents: int | None = Field(default=None, ge=0, le=1_000_000)
    incurred_on: date
    notes: str | None = Field(default=None, max_length=1000)

    @model_validator(mode="after")
    def labor_cost_is_coherent(self) -> "CampaignCostCreate":
        labor_values = (self.worker_user_id, self.labor_minutes, self.hourly_rate_cents)
        if self.category == "va_labor" and not all(value is not None for value in labor_values):
            raise ValueError("VA labor requires a worker, labor minutes, and hourly rate.")
        if self.category != "va_labor" and any(value is not None for value in labor_values):
            raise ValueError("Worker, labor minutes, and hourly rate apply only to VA labor.")
        if (
            self.category == "va_labor"
            and self.labor_minutes
            and self.hourly_rate_cents is not None
        ):
            expected = round(self.labor_minutes * self.hourly_rate_cents / 60)
            if abs(self.amount_cents - expected) > 1:
                raise ValueError("Labor amount must equal hours multiplied by the hourly rate.")
        return self


class ProspectCallingBatchEntryRead(BaseModel):
    id: UUID
    prospect_id: UUID
    legal_name: str
    phone: str | None
    property_address: str | None
    sequence_number: int
    status: str
    attempt_count: int
    disposition: str | None
    call_eligibility: str


class ProspectCallingBatchRead(BaseModel):
    id: UUID
    campaign_id: UUID
    campaign_name: str
    import_batch_id: UUID | None
    assigned_user_id: UUID
    assigned_user_name: str
    name: str
    status: str
    due_at: datetime | None
    notes: str | None
    total_entries: int
    completed_entries: int
    entries: list[ProspectCallingBatchEntryRead]
    created_at: datetime


class ProspectCallingBatchCreate(BaseModel):
    campaign_id: UUID
    import_batch_id: UUID | None = None
    assigned_user_id: UUID
    name: str = Field(min_length=1, max_length=160)
    due_at: datetime | None = None
    maximum_records: int = Field(default=100, ge=1, le=1000)
    notes: str | None = Field(default=None, max_length=1000)


class CampaignQualityRead(BaseModel):
    campaign_id: UUID
    campaign_name: str
    budget_cents: int | None
    actual_cost_cents: int
    remaining_budget_cents: int | None
    total_import_rows: int
    imported_prospects: int
    callable_prospects: int
    review_required_prospects: int
    blocked_prospects: int
    converted_prospects: int
    invalid_rows: int
    duplicate_rows: int
    suppressed_rows: int
    bad_data_rate_basis_points: int
    duplicate_rate_basis_points: int
    conversion_rate_basis_points: int
    cost_per_imported_prospect_cents: int | None
    cost_per_callable_prospect_cents: int | None
    calling_batch_entries: int
    calling_batch_completed: int


class ProspectScreeningReviewRead(BaseModel):
    id: UUID
    campaign_id: UUID
    campaign_name: str
    legal_name: str
    phone: str | None
    property_address: str | None
    call_eligibility: str
    suppression_status: str
    suppression_checked_at: datetime | None


class ProspectScreeningDecision(BaseModel):
    dnc_status: Literal["clear", "blocked"]
    source: str = Field(min_length=2, max_length=120)
    evidence_reference: str = Field(min_length=2, max_length=500)
    notes: str | None = Field(default=None, max_length=1000)


class CampaignManagementOverview(BaseModel):
    users: list[OperationsUserRead]
    campaigns: list[CampaignRead]
    mappings: list[ProspectImportMappingRead]
    import_batches: list[ProspectImportBatchRead]
    costs: list[CampaignCostRead]
    calling_batches: list[ProspectCallingBatchRead]
    screening_review: list[ProspectScreeningReviewRead]
    quality: list[CampaignQualityRead]
