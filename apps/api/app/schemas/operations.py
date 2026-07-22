from datetime import date, datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field, model_validator


class OperationsUserRead(BaseModel):
    id: UUID
    email: str
    display_name: str
    is_active: bool
    role_keys: list[str]
    open_leads: int
    open_tasks: int


class OperationsUserCreate(BaseModel):
    email: str = Field(min_length=3, max_length=320)
    display_name: str = Field(min_length=1, max_length=255)
    role_key: str = Field(min_length=1, max_length=120)


class OperationsUserUpdate(BaseModel):
    display_name: str | None = Field(default=None, min_length=1, max_length=255)
    role_key: str | None = Field(default=None, min_length=1, max_length=120)
    is_active: bool | None = None
    reason: str = Field(min_length=3, max_length=500)


class TeamMemberRead(BaseModel):
    user_id: UUID
    display_name: str
    email: str
    membership_role: str


class TeamRead(BaseModel):
    id: UUID
    name: str
    team_type: str
    manager_user_id: UUID | None
    manager_name: str | None
    is_active: bool
    members: list[TeamMemberRead]


class TeamCreate(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    team_type: Literal["acquisitions", "prospecting", "dispositions", "operations"]
    manager_user_id: UUID | None = None


class TeamMemberCreate(BaseModel):
    user_id: UUID
    membership_role: Literal["manager", "member"] = "member"


class CallingListEntryRead(BaseModel):
    id: UUID
    lead_id: UUID
    seller_name: str
    property_address: str
    assigned_user_id: UUID | None
    assigned_user_name: str | None
    status: str
    attempt_count: int
    disposition: str | None
    notes: str | None
    last_attempt_at: datetime | None
    completed_at: datetime | None


class CallingListRead(BaseModel):
    id: UUID
    name: str
    description: str | None
    status: str
    default_assignee_user_id: UUID | None
    total_records: int
    completed_records: int
    interested_records: int
    entries: list[CallingListEntryRead]


class CallingListCreate(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    description: str | None = Field(default=None, max_length=1000)
    default_assignee_user_id: UUID | None = None


class CallingListLeadAdd(BaseModel):
    lead_ids: list[UUID] = Field(min_length=1, max_length=500)
    assigned_user_id: UUID | None = None


class CallingListEntryUpdate(BaseModel):
    status: Literal["new", "in_progress", "completed"]
    disposition: Literal[
        "no_answer",
        "callback",
        "follow_up",
        "interested",
        "appointment_set",
        "not_interested",
        "wrong_number",
        "dnc",
    ]
    notes: str | None = Field(default=None, max_length=1000)
    handoff_user_id: UUID | None = None


class SavedViewRead(BaseModel):
    id: UUID
    name: str
    resource_type: str
    filters: dict[str, Any]
    is_shared: bool
    team_id: UUID | None


class SavedViewCreate(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    resource_type: Literal["leads", "inbox", "calling_lists", "appointments"]
    filters: dict[str, Any]
    is_shared: bool = False
    team_id: UUID | None = None


class NotificationRead(BaseModel):
    id: UUID
    notification_type: str
    title: str
    body: str
    entity_type: str | None
    entity_id: UUID | None
    action_url: str | None
    read_at: datetime | None
    created_at: datetime


class DuplicateCandidateRead(BaseModel):
    id: UUID
    primary_lead_id: UUID
    duplicate_lead_id: UUID
    primary_label: str
    duplicate_label: str
    status: str
    match_score: int
    match_reasons: list[str]
    resolution_notes: str | None
    created_at: datetime


class DuplicateResolution(BaseModel):
    action: Literal["merge", "not_duplicate"]
    notes: str = Field(min_length=3, max_length=1000)


class FollowUpStep(BaseModel):
    delay_days: int = Field(ge=0, le=365)
    action_type: Literal["task", "call", "sms", "email"]
    title: str = Field(min_length=1, max_length=255)
    body: str | None = Field(default=None, max_length=4000)

    @model_validator(mode="after")
    def communication_requires_body(self) -> "FollowUpStep":
        if self.action_type in {"sms", "email"} and not self.body:
            raise ValueError("SMS and email follow-up steps require draft content.")
        return self


class FollowUpPlanRead(BaseModel):
    id: UUID
    name: str
    description: str | None
    status: str
    steps: list[FollowUpStep]
    active_enrollments: int


class FollowUpPlanCreate(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    description: str | None = Field(default=None, max_length=1000)
    steps: list[FollowUpStep] = Field(min_length=1, max_length=20)


class FollowUpEnrollmentCreate(BaseModel):
    lead_id: UUID


class AppointmentOperationsRead(BaseModel):
    id: UUID
    lead_id: UUID
    seller_name: str
    property_address: str
    owner_user_id: UUID | None
    owner_name: str | None
    appointment_type: str
    status: str
    scheduled_start_at: datetime
    scheduled_end_at: datetime | None
    outcome: str | None
    calendar_status: str


class MarketRead(BaseModel):
    id: UUID
    name: str
    code: str
    state_code: str
    timezone: str
    status: str
    is_primary: bool
    territory_count: int
    campaign_count: int
    prospect_count: int


class MarketCreate(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    code: str = Field(min_length=2, max_length=80, pattern=r"^[a-z0-9][a-z0-9_-]*$")
    state_code: str = Field(min_length=2, max_length=2)
    timezone: str = Field(min_length=3, max_length=80)
    is_primary: bool = False


class TerritoryRead(BaseModel):
    id: UUID
    market_id: UUID
    market_name: str
    assigned_team_id: UUID | None
    assigned_team_name: str | None
    name: str
    code: str
    status: str
    county_names: list[str]
    postal_codes: list[str]
    campaign_count: int
    prospect_count: int


class TerritoryCreate(BaseModel):
    market_id: UUID
    assigned_team_id: UUID | None = None
    name: str = Field(min_length=1, max_length=160)
    code: str = Field(min_length=2, max_length=80, pattern=r"^[a-z0-9][a-z0-9_-]*$")
    county_names: list[str] = Field(default_factory=list, max_length=100)
    postal_codes: list[str] = Field(default_factory=list, max_length=500)


class CampaignRead(BaseModel):
    id: UUID
    market_id: UUID
    market_name: str
    territory_id: UUID | None
    territory_name: str | None
    owner_user_id: UUID | None
    owner_name: str | None
    name: str
    code: str
    channel: str
    status: str
    starts_on: date | None
    ends_on: date | None
    budget_cents: int | None
    prospect_count: int
    converted_prospect_count: int


class CampaignCreate(BaseModel):
    market_id: UUID
    territory_id: UUID | None = None
    owner_user_id: UUID | None = None
    name: str = Field(min_length=1, max_length=160)
    code: str = Field(min_length=2, max_length=80, pattern=r"^[a-z0-9][a-z0-9_-]*$")
    channel: Literal[
        "cold_call",
        "cold_email",
        "direct_mail",
        "paid_search",
        "paid_social",
        "organic",
        "referral",
        "other",
    ]
    starts_on: date | None = None
    ends_on: date | None = None
    budget_cents: int | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def dates_are_ordered(self) -> "CampaignCreate":
        if self.starts_on and self.ends_on and self.ends_on < self.starts_on:
            raise ValueError("Campaign end date cannot be before its start date.")
        return self


class ProspectRead(BaseModel):
    id: UUID
    campaign_id: UUID
    campaign_name: str
    territory_id: UUID | None
    territory_name: str | None
    assigned_user_id: UUID | None
    assigned_user_name: str | None
    converted_lead_id: UUID | None
    source_record_key: str | None
    status: str
    legal_name: str
    phone: str | None
    email: str | None
    property_address: str | None
    suppression_status: str
    created_at: datetime


class ProspectCreate(BaseModel):
    campaign_id: UUID
    territory_id: UUID | None = None
    assigned_user_id: UUID | None = None
    source_record_key: str | None = Field(default=None, max_length=255)
    legal_name: str = Field(min_length=1, max_length=255)
    phone: str | None = Field(default=None, max_length=80)
    email: str | None = Field(default=None, max_length=320)
    street_address: str | None = Field(default=None, max_length=255)
    city: str | None = Field(default=None, max_length=120)
    state_code: str | None = Field(default=None, min_length=2, max_length=2)
    postal_code: str | None = Field(default=None, max_length=20)
    source_payload: dict[str, Any] | None = None

    @model_validator(mode="after")
    def contact_and_address_are_coherent(self) -> "ProspectCreate":
        if not self.phone and not self.email:
            raise ValueError("A prospect requires a phone number or email address.")
        address_values = (self.street_address, self.city, self.state_code, self.postal_code)
        if any(address_values) and not all(address_values):
            raise ValueError(
                "Enter the complete property address or leave every address field blank."
            )
        return self


class AcquisitionOperationsOverview(BaseModel):
    can_manage: bool
    users: list[OperationsUserRead]
    teams: list[TeamRead]
    calling_lists: list[CallingListRead]
    appointments: list[AppointmentOperationsRead]
    saved_views: list[SavedViewRead]
    notifications: list[NotificationRead]
    unread_notification_count: int
    duplicate_candidates: list[DuplicateCandidateRead]
    follow_up_plans: list[FollowUpPlanRead]
    markets: list[MarketRead]
    territories: list[TerritoryRead]
    campaigns: list[CampaignRead]
    prospects: list[ProspectRead]
