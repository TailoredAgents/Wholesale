from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field


class ComplianceUserRead(BaseModel):
    id: UUID
    display_name: str
    email: str
    is_active: bool


class CompliancePolicyRead(BaseModel):
    id: UUID
    policy_key: str
    name: str
    scope_state_code: str
    version_number: int
    status: str
    policy_config: dict[str, object]
    legal_review_status: str
    legal_reviewer_name: str | None
    legal_reviewer_company: str | None
    legal_evidence_reference: str | None
    legal_reviewed_at: datetime | None
    approved_by_user_id: UUID | None
    approved_by_name: str | None
    approved_at: datetime | None
    effective_at: datetime | None
    review_due_at: datetime | None
    superseded_at: datetime | None
    notes: str | None


class CompliancePolicyLegalReviewUpdate(BaseModel):
    legal_reviewer_name: str = Field(min_length=2, max_length=255)
    legal_reviewer_company: str = Field(min_length=2, max_length=255)
    legal_evidence_reference: str = Field(min_length=3, max_length=1000)
    legal_reviewed_at: datetime
    review_due_at: datetime
    notes: str | None = Field(default=None, max_length=2000)


class CompliancePolicyDecision(BaseModel):
    decision: Literal["approve", "retire"]
    reason: str = Field(min_length=3, max_length=1000)


class DncScreeningSourceRead(BaseModel):
    id: UUID
    name: str
    provider_type: str
    status: str
    account_reference: str | None
    coverage_area_codes: list[str]
    refresh_interval_days: int
    last_refreshed_at: datetime | None
    next_refresh_due_at: datetime | None
    latest_evidence_reference: str | None
    approved_by_user_id: UUID | None
    approved_by_name: str | None
    approved_at: datetime | None
    notes: str | None
    is_current: bool


class DncScreeningSourceCreate(BaseModel):
    name: str = Field(min_length=2, max_length=255)
    provider_type: Literal["ftc_registry", "third_party", "manual_review"]
    account_reference: str | None = Field(default=None, max_length=255)
    coverage_area_codes: list[str] = Field(default_factory=list, max_length=1000)
    refresh_interval_days: int = Field(default=31, ge=1, le=31)
    notes: str | None = Field(default=None, max_length=2000)


class DncScreeningSourceDecision(BaseModel):
    decision: Literal["approve", "deactivate"]
    reason: str = Field(min_length=3, max_length=1000)


class DncScreeningRefreshCreate(BaseModel):
    refreshed_at: datetime
    evidence_reference: str = Field(min_length=3, max_length=1000)
    notes: str | None = Field(default=None, max_length=2000)


class ComplianceTrainingRead(BaseModel):
    id: UUID
    user_id: UUID
    user_name: str
    user_email: str
    training_key: str
    training_version: str
    status: str
    assigned_by_user_id: UUID
    assigned_by_name: str
    completed_at: datetime | None
    score_basis_points: int | None
    completion_evidence: str | None
    employee_attestation: str | None
    approved_by_user_id: UUID | None
    approved_by_name: str | None
    approved_at: datetime | None
    manager_notes: str | None


class ComplianceTrainingAssign(BaseModel):
    user_id: UUID
    training_key: Literal[
        "outbound_contact",
        "sms_email_consent",
        "recording_disclosure",
        "complaints_and_escalation",
    ]
    training_version: str = Field(default="1.0", min_length=1, max_length=40)


class ComplianceTrainingSubmit(BaseModel):
    completion_evidence: str = Field(min_length=3, max_length=2000)
    employee_attestation: str = Field(min_length=10, max_length=2000)


class ComplianceTrainingDecision(BaseModel):
    decision: Literal["approve", "needs_changes", "revoke"]
    manager_notes: str = Field(min_length=3, max_length=2000)
    score_basis_points: int | None = Field(default=None, ge=0, le=10000)


class ComplianceIncidentRead(BaseModel):
    id: UUID
    contact_id: UUID | None
    lead_id: UUID | None
    prospect_id: UUID | None
    call_record_id: UUID | None
    incident_type: str
    channel: str
    severity: str
    status: str
    source: str
    summary: str
    details: str | None
    reported_by_user_id: UUID | None
    reported_by_name: str | None
    assigned_to_user_id: UUID | None
    assigned_to_name: str | None
    occurred_at: datetime
    resolved_by_user_id: UUID | None
    resolved_by_name: str | None
    resolved_at: datetime | None
    resolution: str | None


class ComplianceIncidentCreate(BaseModel):
    incident_type: Literal[
        "complaint",
        "wrong_number",
        "do_not_contact",
        "recording_objection",
        "policy_exception",
        "provider_failure",
    ]
    channel: Literal["phone", "sms", "email", "recording", "all"]
    severity: Literal["low", "medium", "high", "critical"] = "medium"
    summary: str = Field(min_length=3, max_length=500)
    details: str | None = Field(default=None, max_length=4000)
    contact_id: UUID | None = None
    lead_id: UUID | None = None
    prospect_id: UUID | None = None
    call_record_id: UUID | None = None
    assigned_to_user_id: UUID | None = None
    occurred_at: datetime | None = None


class ComplianceIncidentResolution(BaseModel):
    resolution: str = Field(min_length=3, max_length=2000)


class ComplianceControlCheckRead(BaseModel):
    key: str
    label: str
    status: Literal["pass", "attention", "fail"]
    detail: str
    affected_count: int = 0


class ComplianceControlRunRead(BaseModel):
    id: UUID
    status: str
    results: list[ComplianceControlCheckRead]
    run_by_user_id: UUID
    run_by_name: str
    started_at: datetime
    completed_at: datetime


class ComplianceOverviewRead(BaseModel):
    users: list[ComplianceUserRead]
    policies: list[CompliancePolicyRead]
    dnc_sources: list[DncScreeningSourceRead]
    training_records: list[ComplianceTrainingRead]
    incidents: list[ComplianceIncidentRead]
    control_runs: list[ComplianceControlRunRead]
    ready_check_count: int
    total_check_count: int


class ComplianceInstallRead(BaseModel):
    created_policy_count: int
    overview: ComplianceOverviewRead
