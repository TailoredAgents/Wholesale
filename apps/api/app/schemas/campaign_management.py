from datetime import date, datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field, model_validator

from app.schemas.operations import CampaignRead, OperationsUserRead

DialerMode = Literal["one_line_power"]

SUPPORTED_IMPORT_FIELDS = {
    "source_record_key",
    "legal_name",
    "legal_first_name",
    "legal_last_name",
    "phone",
    "phone_2",
    "phone_3",
    "phone_4",
    "phone_5",
    "phone_type",
    "phone_2_type",
    "phone_3_type",
    "phone_4_type",
    "phone_5_type",
    "phone_dnc",
    "phone_2_dnc",
    "phone_3_dnc",
    "phone_4_dnc",
    "phone_5_dnc",
    "email",
    "email_2",
    "email_3",
    "email_4",
    "street_address",
    "city",
    "state_code",
    "postal_code",
    "county",
    "parcel_id",
    "property_type",
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
    field_mapping: dict[str, str] = Field(min_length=2, max_length=32)
    default_values: dict[str, str] = Field(default_factory=dict, max_length=32)

    @model_validator(mode="after")
    def mapping_is_supported(self) -> "ProspectImportMappingCreate":
        unsupported = set(self.field_mapping) - SUPPORTED_IMPORT_FIELDS
        if unsupported:
            raise ValueError(f"Unsupported import fields: {', '.join(sorted(unsupported))}.")
        has_full_name = "legal_name" in self.field_mapping
        has_split_name = {
            "legal_first_name",
            "legal_last_name",
        }.issubset(self.field_mapping)
        if not has_full_name and not has_split_name:
            raise ValueError("Map an owner name or both owner first and last name columns.")
        if not {
            "phone",
            "phone_2",
            "phone_3",
            "phone_4",
            "phone_5",
            "email",
            "email_2",
            "email_3",
            "email_4",
        }.intersection(self.field_mapping):
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
    cohort_id: UUID | None = None
    default_assignee_user_id: UUID | None = None
    file_name: str = Field(min_length=1, max_length=255)
    csv_content: str = Field(min_length=1, max_length=5_000_000)
    source_profile: Literal["general_csv", "propstream"] = "general_csv"
    source_export_id: str | None = Field(default=None, max_length=255)
    source_list_id: str | None = Field(default=None, max_length=255)
    source_list_name: str | None = Field(default=None, max_length=255)
    source_exported_at: datetime | None = None
    source_filters: dict[str, Any] = Field(default_factory=dict, max_length=50)

    @model_validator(mode="after")
    def source_evidence_is_coherent(self) -> "ProspectImportRequest":
        if self.source_profile == "propstream" and not (
            self.source_export_id or self.source_list_id or self.source_list_name
        ):
            raise ValueError(
                "PropStream imports require an export ID, list ID, or saved list name."
            )
        return self


class ProspectImportPreviewRow(BaseModel):
    row_number: int
    status: str
    legal_name: str | None
    phone: str | None
    property_address: str | None
    validation_errors: list[str]
    eligibility_reasons: list[str]
    duplicate_prospect_id: UUID | None
    relationship_state: str
    contact_point_count: int


class ProspectImportPreview(BaseModel):
    headers: list[str]
    state_counts: dict[str, int]
    campaign_state_code: str | None
    outside_campaign_state_rows: int
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
    source_membership_id: UUID | None
    relationship_state: str
    contact_point_count: int
    legal_name: str | None
    phone: str | None
    property_address: str | None
    validation_errors: list[str]
    eligibility_reasons: list[str]


class ProspectImportBatchRead(BaseModel):
    id: UUID
    campaign_id: UUID
    campaign_name: str
    cohort_id: UUID | None
    cohort_name: str | None
    mapping_id: UUID
    mapping_name: str
    default_assignee_user_id: UUID | None
    default_assignee_name: str | None
    imported_by_user_id: UUID
    imported_by_name: str
    file_name: str
    file_sha256: str
    source_name: str
    source_profile: str
    source_export_id: str | None
    source_list_id: str | None
    source_list_name: str | None
    source_exported_at: datetime | None
    source_filters: dict[str, Any]
    status: str
    total_rows: int
    valid_rows: int
    imported_rows: int
    matched_existing_rows: int
    invalid_rows: int
    duplicate_rows: int
    suppressed_rows: int
    review_required_rows: int
    completed_at: datetime | None
    created_at: datetime
    rows: list[ProspectImportRowRead]


class ProspectSourceMembershipRead(BaseModel):
    id: UUID
    prospect_id: UUID
    legal_name: str
    campaign_id: UUID
    campaign_name: str
    cohort_id: UUID | None
    cohort_name: str | None
    source_name: str
    source_profile: str
    source_record_key: str | None
    source_list_key: str
    source_list_name: str | None
    first_import_batch_id: UUID
    latest_import_batch_id: UUID
    first_seen_at: datetime
    last_seen_at: datetime
    appearance_count: int
    relationship_state_at_latest_import: str
    source_metadata: dict[str, Any]


class ProspectContactPointRead(BaseModel):
    id: UUID
    prospect_id: UUID
    legal_name: str
    source_membership_id: UUID | None
    contact_type: str
    value: str
    normalized_value: str
    rank: int
    is_primary: bool
    validation_status: str
    contact_metadata: dict[str, Any]
    first_seen_at: datetime
    last_seen_at: datetime


class CampaignCostRead(BaseModel):
    id: UUID
    campaign_id: UUID
    campaign_name: str
    cohort_id: UUID | None
    cohort_name: str | None
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
    cohort_id: UUID | None = None
    import_batch_id: UUID | None = None
    worker_user_id: UUID | None = None
    category: Literal[
        "list_purchase",
        "va_labor",
        "data_enrichment",
        "phone_number",
        "voice_usage",
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


class ProspectingCohortRead(BaseModel):
    id: UUID
    campaign_id: UUID
    campaign_name: str
    asset_class: Literal["house", "land"]
    script_version_id: UUID | None
    created_by_user_id: UUID
    created_by_name: str
    name: str
    code: str
    status: str
    source_name: str
    list_type: str
    market_label: str
    dialer_mode: str
    call_window_start_hour: int
    call_window_end_hour: int
    timezone: str
    starts_on: date
    ends_on: date | None
    cohort_metadata: dict[str, Any]
    created_at: datetime


class ProspectingCohortCreate(BaseModel):
    campaign_id: UUID
    script_version_id: UUID | None = None
    name: str = Field(min_length=1, max_length=160)
    code: str = Field(pattern=r"^[a-z0-9][a-z0-9_-]{1,79}$")
    source_name: str = Field(min_length=1, max_length=160)
    list_type: str = Field(min_length=1, max_length=160)
    market_label: str = Field(min_length=1, max_length=160)
    dialer_mode: DialerMode = "one_line_power"
    call_window_start_hour: int = Field(ge=0, le=23)
    call_window_end_hour: int = Field(ge=1, le=24)
    timezone: str = Field(min_length=1, max_length=80)
    starts_on: date
    ends_on: date | None = None
    cohort_metadata: dict[str, Any] = Field(default_factory=dict, max_length=50)

    @model_validator(mode="after")
    def cohort_dates_and_window_are_coherent(self) -> "ProspectingCohortCreate":
        if self.ends_on and self.ends_on < self.starts_on:
            raise ValueError("Cohort end date cannot be before its start date.")
        if self.call_window_start_hour == self.call_window_end_hour:
            raise ValueError("Calling window must include at least one hour.")
        return self


class ProspectingWorkSessionRead(BaseModel):
    id: UUID
    campaign_id: UUID
    campaign_name: str
    cohort_id: UUID
    cohort_name: str
    caller_user_id: UUID
    caller_name: str
    campaign_cost_id: UUID
    work_date: date
    paid_minutes: int
    productive_calling_minutes: int
    utilization_rate_basis_points: int
    hourly_rate_cents: int
    labor_cost_cents: int
    source: str
    provider_session_id: str | None
    notes: str | None
    created_at: datetime


class ProspectingWorkSessionCreate(BaseModel):
    campaign_id: UUID
    cohort_id: UUID
    caller_user_id: UUID
    work_date: date
    paid_minutes: int = Field(ge=1, le=1_440)
    productive_calling_minutes: int = Field(ge=0, le=1_440)
    hourly_rate_cents: int = Field(ge=0, le=1_000_000)
    source: Literal["manual", "provider_import"] = "manual"
    provider_session_id: str | None = Field(default=None, max_length=255)
    notes: str | None = Field(default=None, max_length=1000)

    @model_validator(mode="after")
    def work_time_is_coherent(self) -> "ProspectingWorkSessionCreate":
        if self.productive_calling_minutes > self.paid_minutes:
            raise ValueError("Productive calling time cannot exceed paid time.")
        if self.source == "provider_import" and not self.provider_session_id:
            raise ValueError("Provider-imported work requires a provider session ID.")
        if self.source == "manual" and self.provider_session_id:
            raise ValueError("Provider session ID applies only to provider-imported work.")
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
    cohort_id: UUID | None
    cohort_name: str | None
    dialer_mode: str
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
    cohort_id: UUID | None = None
    dialer_mode: DialerMode = "one_line_power"
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
    submitted_handoffs: int
    accepted_warm_leads: int
    rejected_handoffs: int
    invalid_rows: int
    duplicate_rows: int
    suppressed_rows: int
    bad_data_rate_basis_points: int
    duplicate_rate_basis_points: int
    conversion_rate_basis_points: int
    cost_per_imported_prospect_cents: int | None
    cost_per_callable_prospect_cents: int | None
    cost_per_accepted_warm_lead_cents: int | None
    calling_batch_entries: int
    calling_batch_completed: int


class CampaignManagementOverview(BaseModel):
    users: list[OperationsUserRead]
    campaigns: list[CampaignRead]
    mappings: list[ProspectImportMappingRead]
    import_batches: list[ProspectImportBatchRead]
    source_memberships: list[ProspectSourceMembershipRead]
    contact_points: list[ProspectContactPointRead]
    cohorts: list[ProspectingCohortRead]
    work_sessions: list[ProspectingWorkSessionRead]
    costs: list[CampaignCostRead]
    calling_batches: list[ProspectCallingBatchRead]
    quality: list[CampaignQualityRead]
