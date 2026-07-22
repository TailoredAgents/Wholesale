from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, field_validator, model_validator


class CloserProfileUpsert(BaseModel):
    timezone: str = Field(default="America/New_York", min_length=1, max_length=80)
    working_days: list[int] = Field(default_factory=lambda: [0, 1, 2, 3, 4], min_length=1)
    workday_start_minute: int = Field(default=540, ge=0, le=1439)
    workday_end_minute: int = Field(default=1020, ge=1, le=1440)
    daily_capacity: int = Field(default=4, ge=1, le=20)
    default_appointment_minutes: int = Field(default=90, ge=15, le=480)
    travel_buffer_minutes: int = Field(default=30, ge=0, le=240)
    home_base_postal_code: str | None = Field(default=None, max_length=20)
    territory_enforcement_enabled: bool = True
    is_active: bool = True
    territory_ids: list[UUID] = Field(default_factory=list)

    @field_validator("working_days")
    @classmethod
    def validate_working_days(cls, value: list[int]) -> list[int]:
        if any(day < 0 or day > 6 for day in value):
            raise ValueError("Working days must use Monday=0 through Sunday=6.")
        return sorted(set(value))

    @model_validator(mode="after")
    def validate_workday(self) -> "CloserProfileUpsert":
        if self.workday_end_minute <= self.workday_start_minute:
            raise ValueError("Workday end must be after workday start.")
        return self


class CloserAvailabilityBlockCreate(BaseModel):
    block_type: Literal["unavailable", "personal", "company", "travel"] = "unavailable"
    starts_at: datetime
    ends_at: datetime
    reason: str = Field(min_length=1, max_length=500)

    @model_validator(mode="after")
    def validate_window(self) -> "CloserAvailabilityBlockCreate":
        if self.ends_at <= self.starts_at:
            raise ValueError("Availability block end must be after its start.")
        return self


class CloserAvailabilityBlockRead(BaseModel):
    id: UUID
    block_type: str
    starts_at: datetime
    ends_at: datetime
    reason: str


class CloserProfileRead(BaseModel):
    id: UUID
    user_id: UUID
    user_name: str
    timezone: str
    working_days: list[int]
    workday_start_minute: int
    workday_end_minute: int
    daily_capacity: int
    default_appointment_minutes: int
    travel_buffer_minutes: int
    home_base_postal_code: str | None
    territory_enforcement_enabled: bool
    is_active: bool
    territory_ids: list[UUID]
    territory_names: list[str]
    blocks: list[CloserAvailabilityBlockRead]


class DispatchUserRead(BaseModel):
    id: UUID
    name: str
    email: str
    profile_configured: bool


class DispatchTerritoryRead(BaseModel):
    id: UUID
    name: str
    market_name: str
    county_names: list[str]
    postal_codes: list[str]


class DispatchLeadRead(BaseModel):
    id: UUID
    seller_name: str
    property_address: str
    county: str | None
    postal_code: str
    stage_key: str
    current_owner_name: str | None
    next_follow_up_at: datetime | None
    lead_url: str


class DispatchCandidateRead(BaseModel):
    profile_id: UUID
    user_id: UUID
    user_name: str
    eligible: bool
    territory_match: bool
    territory_name: str | None
    daily_booked_count: int
    daily_capacity: int
    remaining_capacity: int
    travel_buffer_minutes: int
    violations: list[str]


class DispatchSlotRequest(BaseModel):
    lead_id: UUID
    scheduled_start_at: datetime
    scheduled_end_at: datetime | None = None

    @model_validator(mode="after")
    def validate_window(self) -> "DispatchSlotRequest":
        if self.scheduled_end_at is not None and self.scheduled_end_at <= self.scheduled_start_at:
            raise ValueError("Appointment end must be after its start.")
        return self


class DispatchSlotEvaluation(BaseModel):
    lead_id: UUID
    scheduled_start_at: datetime
    scheduled_end_at: datetime
    territory_id: UUID | None
    territory_name: str | None
    candidates: list[DispatchCandidateRead]


class AppointmentDispatchCreate(DispatchSlotRequest):
    closer_user_id: UUID
    appointment_type: Literal[
        "seller_appointment", "property_walkthrough", "offer_presentation"
    ] = "seller_appointment"
    location_type: Literal["property", "office", "phone", "video"] = "property"
    location: str | None = Field(default=None, max_length=500)
    notes: str | None = Field(default=None, max_length=1000)
    override_conflicts: bool = False
    override_reason: str | None = Field(default=None, max_length=1000)

    @model_validator(mode="after")
    def require_override_reason(self) -> "AppointmentDispatchCreate":
        if self.override_conflicts and not (self.override_reason or "").strip():
            raise ValueError("An override reason is required when conflicts are overridden.")
        return self


class AppointmentDispatchRead(BaseModel):
    appointment_id: UUID
    dispatch_record_id: UUID
    lead_id: UUID
    closer_user_id: UUID
    closer_name: str
    decision_status: str
    scheduled_start_at: datetime
    scheduled_end_at: datetime
    violations: list[str]


class DispatchAppointmentRead(BaseModel):
    id: UUID
    lead_id: UUID
    seller_name: str
    property_address: str
    closer_name: str
    status: str
    scheduled_start_at: datetime
    scheduled_end_at: datetime | None
    decision_status: str | None
    violations: list[str]
    lead_url: str


class FieldOperationsMetrics(BaseModel):
    ready_to_schedule: int
    appointments_today: int
    unassigned_today: int
    at_capacity_today: int


class FieldOperationsOverview(BaseModel):
    can_manage: bool
    metrics: FieldOperationsMetrics
    users: list[DispatchUserRead]
    profiles: list[CloserProfileRead]
    territories: list[DispatchTerritoryRead]
    ready_leads: list[DispatchLeadRead]
    upcoming_appointments: list[DispatchAppointmentRead]
