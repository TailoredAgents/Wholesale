from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, model_validator


class BusinessUserRead(BaseModel):
    id: UUID
    display_name: str
    email: str
    is_active: bool


class BusinessMarketRead(BaseModel):
    id: UUID
    name: str
    state_code: str
    status: str


class CompensationPlanRoleRead(BaseModel):
    id: UUID
    role_key: str
    basis_points: int
    cap_cents: int | None
    notes: str | None


class DispositionOperatingModeRead(BaseModel):
    id: UUID
    key: str
    name: str
    status: str
    human_share_min_basis_points: int
    human_share_max_basis_points: int
    expected_company_share_min_basis_points: int
    expected_company_share_max_basis_points: int
    ai_authority_level: str
    activation_requirements: dict[str, object]


class CompensationPlanRead(BaseModel):
    id: UUID
    name: str
    version_number: int
    status: str
    acquisition_reserve_cents: int
    target_company_margin_basis_points: int
    effective_start_at: datetime | None
    effective_end_at: datetime | None
    created_by_user_id: UUID
    created_by_name: str
    approved_by_user_id: UUID | None
    approved_by_name: str | None
    approved_at: datetime | None
    notes: str | None
    roles: list[CompensationPlanRoleRead]
    disposition_modes: list[DispositionOperatingModeRead]


class CompensationPlanCreate(BaseModel):
    name: str = Field(default="Stonegate Standard", min_length=1, max_length=160)
    acquisition_reserve_cents: int = Field(default=250000, ge=0, le=10000000)
    target_company_margin_basis_points: int = Field(default=3000, ge=0, le=10000)
    lead_manager_basis_points: int = Field(default=1000, ge=0, le=5000)
    acquisitions_closer_basis_points: int = Field(default=1000, ge=0, le=5000)
    ceo_management_basis_points: int = Field(default=1000, ge=0, le=5000)
    dispositions_basis_points: int = Field(default=2000, ge=0, le=5000)
    transaction_coordinator_basis_points: int = Field(default=500, ge=0, le=5000)
    transaction_coordinator_cap_cents: int | None = Field(default=100000, ge=0, le=10000000)
    ai_managed_disposition_basis_points: int = Field(default=1000, ge=0, le=5000)
    ai_oversight_disposition_min_basis_points: int = Field(default=500, ge=0, le=5000)
    ai_oversight_disposition_max_basis_points: int = Field(default=750, ge=0, le=5000)
    notes: str | None = Field(default=None, max_length=2000)

    @model_validator(mode="after")
    def economics_are_coherent(self) -> "CompensationPlanCreate":
        human_role_total = (
            self.lead_manager_basis_points
            + self.acquisitions_closer_basis_points
            + self.ceo_management_basis_points
            + self.dispositions_basis_points
            + self.transaction_coordinator_basis_points
        )
        if human_role_total + self.target_company_margin_basis_points > 10000:
            raise ValueError("Role shares and target company margin cannot exceed 100%.")
        if self.ai_managed_disposition_basis_points > self.dispositions_basis_points:
            raise ValueError("AI-managed disposition share cannot exceed the human-led share.")
        if (
            self.ai_oversight_disposition_min_basis_points
            > self.ai_oversight_disposition_max_basis_points
        ):
            raise ValueError("AI-oversight minimum share cannot exceed its maximum share.")
        if (
            self.ai_oversight_disposition_max_basis_points
            > self.ai_managed_disposition_basis_points
        ):
            raise ValueError("AI-oversight share cannot exceed the AI-managed share.")
        return self


class CompensationPlanActivation(BaseModel):
    reason: str = Field(min_length=3, max_length=1000)


class RoleCreditRead(BaseModel):
    id: UUID
    compensation_plan_version_id: UUID
    plan_label: str
    lead_id: UUID
    seller_name: str
    user_id: UUID
    user_name: str
    role_key: str
    credit_basis_points: int
    status: str
    assigned_by_user_id: UUID
    assigned_by_name: str
    approved_by_user_id: UUID | None
    approved_by_name: str | None
    approved_at: datetime | None
    notes: str | None
    created_at: datetime


class RoleCreditCreate(BaseModel):
    compensation_plan_version_id: UUID
    lead_id: UUID
    user_id: UUID
    role_key: Literal[
        "lead_manager",
        "acquisitions_closer",
        "ceo_management",
        "dispositions",
        "transaction_coordinator",
    ]
    credit_basis_points: int = Field(default=10000, ge=1, le=10000)
    notes: str | None = Field(default=None, max_length=1000)


class RoleCreditDecision(BaseModel):
    decision: Literal["approve", "reject"]
    reason: str = Field(min_length=3, max_length=1000)


class MarketLaunchChecklistItemRead(BaseModel):
    id: UUID
    item_key: str
    category: str
    label: str
    status: str
    responsible_user_id: UUID | None
    responsible_user_name: str | None
    evidence_notes: str | None
    completed_by_user_id: UUID | None
    completed_by_name: str | None
    completed_at: datetime | None
    sort_order: int


class MarketLaunchChecklistRead(BaseModel):
    id: UUID
    market_id: UUID
    market_name: str
    version_number: int
    status: str
    owner_user_id: UUID
    owner_name: str
    approved_by_user_id: UUID | None
    approved_by_name: str | None
    approved_at: datetime | None
    notes: str | None
    completed_items: int
    total_items: int
    items: list[MarketLaunchChecklistItemRead]


class MarketLaunchChecklistCreate(BaseModel):
    owner_user_id: UUID
    notes: str | None = Field(default=None, max_length=2000)


class MarketLaunchChecklistItemUpdate(BaseModel):
    status: Literal["pending", "in_progress", "complete", "blocked"]
    responsible_user_id: UUID | None = None
    evidence_notes: str | None = Field(default=None, max_length=2000)

    @model_validator(mode="after")
    def completed_item_has_evidence(self) -> "MarketLaunchChecklistItemUpdate":
        if self.status == "complete" and not (self.evidence_notes or "").strip():
            raise ValueError("Completed launch items require evidence notes.")
        return self


class MarketLaunchChecklistApproval(BaseModel):
    reason: str = Field(min_length=3, max_length=1000)


class OperatingSeatRead(BaseModel):
    id: UUID
    seat_key: str
    label: str
    role_key: str
    status: str
    primary_user_id: UUID | None
    primary_user_name: str | None
    backup_user_id: UUID | None
    backup_user_name: str | None
    notes: str | None


class OperatingSeatUpdate(BaseModel):
    status: Literal["planned", "hiring", "covered", "paused"]
    primary_user_id: UUID | None = None
    backup_user_id: UUID | None = None
    notes: str | None = Field(default=None, max_length=1000)

    @model_validator(mode="after")
    def covered_seat_has_an_owner(self) -> "OperatingSeatUpdate":
        if self.status == "covered" and self.primary_user_id is None:
            raise ValueError("A covered operating seat requires a primary user.")
        if (
            self.primary_user_id is not None
            and self.backup_user_id is not None
            and self.primary_user_id == self.backup_user_id
        ):
            raise ValueError("Primary and backup coverage must be different users.")
        return self


class BusinessCounterpartyRead(BaseModel):
    id: UUID
    market_id: UUID | None
    market_name: str | None
    counterparty_type: str
    name: str
    company_name: str | None
    email: str | None
    phone: str | None
    status: str
    verified_by_user_id: UUID | None
    verified_by_name: str | None
    verified_at: datetime | None
    notes: str | None


class BusinessCounterpartyCreate(BaseModel):
    market_id: UUID | None = None
    counterparty_type: Literal[
        "closing_attorney",
        "title_company",
        "funding_partner",
        "inspector",
        "other",
    ]
    name: str = Field(min_length=1, max_length=255)
    company_name: str | None = Field(default=None, max_length=255)
    email: str | None = Field(default=None, max_length=320)
    phone: str | None = Field(default=None, max_length=40)
    notes: str | None = Field(default=None, max_length=2000)


class BusinessCounterpartyDecision(BaseModel):
    decision: Literal["verify", "deactivate"]
    reason: str = Field(min_length=3, max_length=1000)


class StaffRoleAcceptanceRead(BaseModel):
    id: UUID
    user_id: UUID
    user_name: str
    role_key: str
    manual_key: str
    manual_version: str
    status: str
    assigned_by_user_id: UUID
    assigned_by_name: str
    workspace_test_evidence: str | None
    employee_notes: str | None
    accepted_at: datetime | None
    approved_by_user_id: UUID | None
    approved_by_name: str | None
    manager_notes: str | None
    approved_at: datetime | None


class StaffRoleAcceptanceAssign(BaseModel):
    user_id: UUID
    role_key: str = Field(min_length=1, max_length=120)
    manual_key: str = Field(min_length=1, max_length=160)
    manual_version: str = Field(min_length=1, max_length=40)


class StaffRoleAcceptanceSubmit(BaseModel):
    workspace_test_evidence: str = Field(min_length=10, max_length=2000)
    employee_notes: str | None = Field(default=None, max_length=2000)


class StaffRoleAcceptanceDecision(BaseModel):
    decision: Literal["approve", "needs_changes", "revoke"]
    manager_notes: str = Field(min_length=3, max_length=2000)


class CompanySetupCheckRead(BaseModel):
    key: str
    label: str
    status: Literal["complete", "attention", "not_started"]
    detail: str


class CompanySetupRead(BaseModel):
    seats: list[OperatingSeatRead]
    counterparties: list[BusinessCounterpartyRead]
    role_acceptances: list[StaffRoleAcceptanceRead]
    checks: list[CompanySetupCheckRead]
    completed_check_count: int
    total_check_count: int


class CompanySetupInstallRead(BaseModel):
    created_seat_count: int
    setup: CompanySetupRead


class MyRoleSetupRead(BaseModel):
    user_id: UUID
    user_name: str
    role_keys: list[str]
    acceptances: list[StaffRoleAcceptanceRead]


class OperatingModelOverview(BaseModel):
    users: list[BusinessUserRead]
    markets: list[BusinessMarketRead]
    compensation_plans: list[CompensationPlanRead]
    role_credits: list[RoleCreditRead]
    launch_checklists: list[MarketLaunchChecklistRead]
    company_setup: CompanySetupRead
