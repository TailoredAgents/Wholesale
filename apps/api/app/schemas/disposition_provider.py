from datetime import datetime
from typing import Any, Literal, cast
from uuid import UUID

from pydantic import BaseModel, Field, HttpUrl, field_validator, model_validator

ProviderKey = Literal["investorlift"]
ProviderMode = Literal["manual"]
ProviderAccountStatus = Literal["manual_ready"]
ProviderListingStatus = Literal[
    "draft",
    "release_approved",
    "manual_published",
    "disconnected",
]
ProviderRevisionStatus = Literal["draft", "approved", "superseded"]
ProviderManualStatus = Literal[
    "draft",
    "active",
    "paused",
    "under_contract",
    "sold",
    "archived",
    "unknown",
]
ProviderEvidenceType = Literal["inquiry", "offer", "engagement"]
ProviderEvidenceReviewStatus = Literal["staged", "reviewed", "dismissed"]


def _require_investorlift_url(value: HttpUrl | None) -> HttpUrl | None:
    if value is None:
        return None
    hostname = (value.host or "").lower()
    if value.scheme != "https" or not (
        hostname == "investorlift.com" or hostname.endswith(".investorlift.com")
    ):
        raise ValueError("InvestorLift links must use HTTPS on an investorlift.com host.")
    return value


class ProviderPermissionRead(BaseModel):
    can_prepare: bool
    can_approve: bool
    can_record_manual: bool
    can_disconnect: bool
    can_export: bool


class ProviderVerificationGateRead(BaseModel):
    provider_key: ProviderKey
    mode: ProviderMode
    api_contract_verified: bool
    live_transport_enabled: bool
    credential_required: bool
    house_only: bool
    blockers: list[str]
    supported_manual_capabilities: list[str]
    unverified_capabilities: list[str]


class ProviderAccountRead(BaseModel):
    id: UUID
    provider_key: ProviderKey
    provider_label: str
    mode: ProviderMode
    status: ProviderAccountStatus
    capability_snapshot: dict[str, Any]
    connected_at: datetime


class ProviderApprovedPackageRead(BaseModel):
    package_version_id: UUID
    version_number: int
    source_fingerprint: str
    approved_at: datetime
    is_current: bool


class ProviderListingRead(BaseModel):
    id: UUID
    provider_account_id: UUID
    disposition_case_id: UUID
    status: ProviderListingStatus
    lock_version: int
    package_version_id: UUID | None
    latest_revision_id: UUID | None
    approved_revision_id: UUID | None
    external_property_id: str | None
    external_url: str | None
    provider_status: ProviderManualStatus | None
    public_payload_sha256: str | None
    package_source_fingerprint: str | None
    manual_published_at: datetime | None
    last_refreshed_at: datetime | None
    disconnected_at: datetime | None
    disconnect_reason: str | None
    created_at: datetime
    updated_at: datetime


class ProviderListingRevisionRead(BaseModel):
    id: UUID
    listing_id: UUID
    package_version_id: UUID
    revision_number: int
    lock_version: int
    status: ProviderRevisionStatus
    public_payload: dict[str, Any]
    public_payload_sha256: str
    package_source_fingerprint: str
    created_by_user_id: UUID
    approved_by_user_id: UUID | None
    approval_reason: str | None
    approved_at: datetime | None
    created_at: datetime
    is_current: bool


class ProviderSourceLinkRead(BaseModel):
    id: UUID
    listing_id: UUID
    listing_revision_id: UUID
    external_property_id: str
    external_url: str
    provider_status: ProviderManualStatus
    source_snapshot_sha256: str
    observed_at: datetime
    note: str | None
    created_by_user_id: UUID
    created_at: datetime


class ProviderEvidenceRead(BaseModel):
    id: UUID
    listing_id: UUID
    event_type: ProviderEvidenceType
    external_event_id: str | None
    review_status: ProviderEvidenceReviewStatus
    lock_version: int
    occurred_at: datetime
    buyer_name: str | None
    buyer_email: str | None
    buyer_phone: str | None
    offer_amount_cents: int | None
    message: str | None
    metadata: dict[str, Any]
    evidence_sha256: str
    review_note: str | None
    reviewed_by_user_id: UUID | None
    reviewed_at: datetime | None
    created_at: datetime
    selection_eligible: Literal[False] = False


class ProviderSyncRunRead(BaseModel):
    id: UUID
    listing_id: UUID | None
    operation: str
    status: Literal["completed", "failed"]
    mode: ProviderMode
    request_sha256: str
    result_summary: dict[str, Any]
    error_message: str | None
    started_at: datetime
    completed_at: datetime


class ProviderWorkspaceRead(BaseModel):
    case_id: UUID
    provider_key: ProviderKey
    provider_label: str
    house_only: bool
    eligible: bool
    eligibility_blockers: list[str]
    permissions: ProviderPermissionRead
    verification_gate: ProviderVerificationGateRead
    account: ProviderAccountRead | None
    approved_package: ProviderApprovedPackageRead | None
    listing: ProviderListingRead | None
    revisions: list[ProviderListingRevisionRead]
    source_links: list[ProviderSourceLinkRead]
    staged_events: list[ProviderEvidenceRead]
    recent_runs: list[ProviderSyncRunRead]
    warnings: list[str]


class ProviderListingRevisionCreate(BaseModel):
    expected_latest_revision: int = Field(ge=0)


class ProviderListingRevisionApproval(BaseModel):
    expected_lock_version: int = Field(ge=1)
    attestation: bool
    reason: str = Field(min_length=3, max_length=2000)

    @field_validator("attestation")
    @classmethod
    def require_attestation(cls, value: bool) -> bool:
        if not value:
            raise ValueError(
                "Release approval requires confirmation that this exact public payload "
                "is approved for manual publication."
            )
        return value

    @field_validator("reason")
    @classmethod
    def normalize_reason(cls, value: str) -> str:
        normalized = " ".join(value.split())
        if len(normalized) < 3:
            raise ValueError("Release approval requires a meaningful reason.")
        return normalized


class ProviderManualLinkCreate(BaseModel):
    revision_id: UUID
    expected_listing_version: int = Field(ge=1)
    external_property_id: str = Field(min_length=1, max_length=255)
    external_url: HttpUrl
    provider_status: ProviderManualStatus = "active"
    note: str | None = Field(default=None, max_length=1000)

    @field_validator("external_property_id")
    @classmethod
    def normalize_external_property_id(cls, value: str) -> str:
        normalized = " ".join(value.split())
        if not normalized:
            raise ValueError("External property ID is required.")
        return normalized

    @field_validator("external_url")
    @classmethod
    def require_investorlift_url(cls, value: HttpUrl) -> HttpUrl:
        return cast(HttpUrl, _require_investorlift_url(value))


class ProviderManualEventCreate(BaseModel):
    event_type: ProviderEvidenceType
    external_event_id: str | None = Field(default=None, max_length=255)
    occurred_at: datetime
    buyer_name: str | None = Field(default=None, max_length=255)
    buyer_email: str | None = Field(default=None, max_length=320)
    buyer_phone: str | None = Field(default=None, max_length=80)
    offer_amount_cents: int | None = Field(default=None, ge=1)
    message: str | None = Field(default=None, max_length=4000)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("occurred_at")
    @classmethod
    def require_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("Manual provider event time must include a UTC offset.")
        return value

    @model_validator(mode="after")
    def require_event_evidence(self) -> "ProviderManualEventCreate":
        if self.event_type == "offer" and self.offer_amount_cents is None:
            raise ValueError("Manual offer evidence requires an offer amount.")
        if not any(
            (
                self.external_event_id,
                self.buyer_name,
                self.buyer_email,
                self.buyer_phone,
                self.offer_amount_cents,
                self.message,
                self.metadata,
            )
        ):
            raise ValueError("Manual provider evidence cannot be empty.")
        return self


class ProviderManualEventReview(BaseModel):
    expected_lock_version: int = Field(ge=1)
    review_status: Literal["reviewed", "dismissed"]
    review_note: str | None = Field(default=None, max_length=2000)


class ProviderManualRefresh(BaseModel):
    provider_status: ProviderManualStatus
    external_property_id: str | None = Field(default=None, max_length=255)
    external_url: HttpUrl | None = None
    note: str | None = Field(default=None, max_length=1000)

    @field_validator("external_url")
    @classmethod
    def require_investorlift_url(cls, value: HttpUrl | None) -> HttpUrl | None:
        return _require_investorlift_url(value)


class ProviderDisconnectRequest(BaseModel):
    attestation: bool
    reason: str = Field(min_length=3, max_length=2000)

    @field_validator("attestation")
    @classmethod
    def require_attestation(cls, value: bool) -> bool:
        if not value:
            raise ValueError(
                "Disconnect requires confirmation that Stonegate history will be preserved "
                "and future provider activity will be recorded manually if needed."
            )
        return value

    @field_validator("reason")
    @classmethod
    def normalize_reason(cls, value: str) -> str:
        normalized = " ".join(value.split())
        if len(normalized) < 3:
            raise ValueError("Disconnect requires a meaningful reason.")
        return normalized
