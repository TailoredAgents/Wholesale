import re
from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator, model_validator

from app.services.communication_compliance import format_e164

METADATA_FIELDS = {
    "provider_lead_id",
    "page_id",
    "form_id",
    "form_name",
    "created_time",
    "ad_id",
    "ad_name",
    "adset_id",
    "adset_name",
    "campaign_id",
    "campaign_name",
    "platform",
    "is_organic",
}
SAFE_FIELD_NAME = re.compile(r"^[A-Za-z0-9_. -]{1,120}$")


class ZapierFacebookLeadCreate(BaseModel):
    model_config = ConfigDict(
        extra="allow",
        str_strip_whitespace=True,
        coerce_numbers_to_str=True,
    )

    provider_lead_id: str = Field(min_length=1, max_length=255, pattern=r"^\d+$")
    page_id: str = Field(min_length=1, max_length=255, pattern=r"^\d+$")
    form_id: str | None = Field(default=None, max_length=255)
    form_name: str | None = Field(default=None, max_length=255)
    created_time: str | None = Field(default=None, max_length=100)
    ad_id: str | None = Field(default=None, max_length=255)
    ad_name: str | None = Field(default=None, max_length=500)
    adset_id: str | None = Field(default=None, max_length=255)
    adset_name: str | None = Field(default=None, max_length=500)
    campaign_id: str | None = Field(default=None, max_length=255)
    campaign_name: str | None = Field(default=None, max_length=500)
    platform: str | None = Field(default="facebook", max_length=80)
    is_organic: bool | None = False

    full_name: str | None = Field(default=None, max_length=255)
    first_name: str | None = Field(default=None, max_length=120)
    last_name: str | None = Field(default=None, max_length=120)
    email: str | None = Field(default=None, max_length=320)
    phone_number: str | None = Field(default=None, max_length=80)
    property_address: str | None = Field(default=None, max_length=500)
    property_city: str | None = Field(default=None, max_length=255)
    property_state: str | None = Field(default=None, max_length=120)
    property_zip_code: str | None = Field(default=None, max_length=40)
    property_county: str | None = Field(default=None, max_length=120)
    property_type: str | None = Field(default=None, max_length=255)
    asset_class: str | None = Field(default=None, max_length=40)
    parcel_id: str | None = Field(default=None, max_length=255)
    reason_for_selling: str | None = Field(default=None, max_length=1000)
    desired_timeline: str | None = Field(default=None, max_length=500)
    property_condition: str | None = Field(default=None, max_length=500)
    occupancy_status: str | None = Field(default=None, max_length=500)
    asking_price: str | None = Field(default=None, max_length=255)
    mortgage_balance: str | None = Field(default=None, max_length=255)
    comments: str | None = Field(default=None, max_length=2000)

    @model_validator(mode="after")
    def validate_custom_fields(self) -> "ZapierFacebookLeadCreate":
        extras = self.model_extra or {}
        if len(extras) > 75:
            raise ValueError("Zapier lead payload contains too many custom fields.")
        for key, value in extras.items():
            if not SAFE_FIELD_NAME.fullmatch(key):
                raise ValueError(f"Zapier custom field name is invalid: {key[:40]}")
            if isinstance(value, (dict, tuple, set)):
                raise ValueError(f"Zapier custom field must be a scalar or list: {key}")
            values = value if isinstance(value, list) else [value]
            if len(values) > 25:
                raise ValueError(f"Zapier custom field contains too many values: {key}")
            if any(isinstance(item, (dict, list, tuple, set)) for item in values):
                raise ValueError(f"Zapier custom field contains a nested value: {key}")
            if sum(len(str(item)) for item in values if item is not None) > 4000:
                raise ValueError(f"Zapier custom field is too long: {key}")
        return self

    def raw_payload(self) -> dict[str, Any]:
        return self.model_dump(mode="json")

    def normalized_lead_payload(self) -> dict[str, object]:
        raw = self.raw_payload()
        field_data: list[dict[str, object]] = []
        for name, value in raw.items():
            if name in METADATA_FIELDS or value is None or value == "":
                continue
            values = value if isinstance(value, list) else [value]
            clean_values = [str(item).strip() for item in values if str(item).strip()]
            if clean_values:
                field_data.append({"name": name, "values": clean_values})
        return {
            "id": self.provider_lead_id,
            "created_time": self.created_time,
            "page_id": self.page_id,
            "form_id": self.form_id,
            "form_name": self.form_name,
            "ad_id": self.ad_id,
            "ad_name": self.ad_name,
            "adset_id": self.adset_id,
            "adset_name": self.adset_name,
            "campaign_id": self.campaign_id,
            "campaign_name": self.campaign_name,
            "platform": self.platform,
            "is_organic": self.is_organic,
            "field_data": field_data,
        }


BatchDialerEventType = Literal["lead.created", "calendar.created", "dnc.added"]
BatchDialerFollowUpPermission = Literal[
    "phone",
    "email",
    "sms",
    "phone_and_email",
    "phone_and_sms",
    "email_and_sms",
    "phone_email_and_sms",
]


class ZapierBatchDialerEventCreate(BaseModel):
    """Canonical, provider-safe payload mapped by Zapier from BatchDialer.

    This intentionally describes Stonegate's intake contract instead of assuming
    the shape or availability of a private BatchDialer API.
    """

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True, coerce_numbers_to_str=True)

    event_id: str = Field(min_length=1, max_length=255)
    event_type: BatchDialerEventType
    occurred_at: datetime
    campaign_id: str = Field(min_length=1, max_length=255)
    campaign_name: str | None = Field(default=None, max_length=500)
    provider_contact_id: str = Field(min_length=1, max_length=255)
    provider_call_id: str | None = Field(default=None, max_length=255)
    provider_recording_id: str | None = Field(default=None, max_length=255)
    provider_agent_id: str | None = Field(default=None, max_length=255)
    va_name: str | None = Field(default=None, max_length=255)
    va_email: EmailStr | None = None
    related_lead_event_id: str | None = Field(default=None, max_length=255)

    full_name: str | None = Field(default=None, max_length=255)
    phone: str | None = Field(default=None, max_length=80)
    email: EmailStr | None = None
    property_address: str | None = Field(default=None, max_length=255)
    property_city: str | None = Field(default=None, max_length=120)
    property_state: str | None = Field(default=None, min_length=2, max_length=2)
    property_zip_code: str | None = Field(default=None, max_length=20)
    property_county: str | None = Field(default=None, max_length=120)
    property_type: str | None = Field(default=None, max_length=80)
    asset_class: Literal["house", "land"] = "house"
    parcel_id: str | None = Field(default=None, max_length=255)
    reason_for_selling: str | None = Field(default=None, max_length=500)
    desired_timeline: str | None = Field(default=None, max_length=120)
    property_condition: str | None = Field(default=None, max_length=120)
    occupancy_status: str | None = Field(default=None, max_length=120)
    asking_price: str | None = Field(default=None, max_length=120)
    mortgage_balance: str | None = Field(default=None, max_length=120)
    notes: str | None = Field(default=None, max_length=2000)
    disposition: Literal["interested", "appointment_set"] | None = None
    follow_up_permission: BatchDialerFollowUpPermission | None = None

    provider_appointment_id: str | None = Field(default=None, max_length=255)
    appointment_start_at: datetime | None = None
    appointment_end_at: datetime | None = None
    appointment_type: str | None = Field(default=None, max_length=80)
    appointment_location_type: (
        Literal["seller_property", "phone", "video", "office", "other"] | None
    ) = None
    appointment_location: str | None = Field(default=None, max_length=500)
    appointment_notes: str | None = Field(default=None, max_length=1000)
    appointment_owner_email: EmailStr | None = None

    dnc_reason: str | None = Field(default=None, max_length=255)

    @field_validator("property_state")
    @classmethod
    def uppercase_state(cls, value: str | None) -> str | None:
        return value.upper() if value else value

    @field_validator("occurred_at", "appointment_start_at", "appointment_end_at")
    @classmethod
    def require_timezone(cls, value: datetime | None) -> datetime | None:
        if value is not None and (value.tzinfo is None or value.utcoffset() is None):
            raise ValueError("BatchDialer event timestamps must include a timezone.")
        return value.astimezone(UTC) if value is not None else None

    @model_validator(mode="after")
    def validate_event_contract(self) -> "ZapierBatchDialerEventCreate":
        if self.event_type == "lead.created":
            if not self.full_name:
                raise ValueError("lead.created requires full_name.")
            if format_e164(self.phone) is None:
                raise ValueError("lead.created requires a valid phone number.")
            if self.disposition is None:
                raise ValueError("lead.created requires a warm disposition.")
            if self.follow_up_permission is None:
                raise ValueError("lead.created requires follow_up_permission.")
            channels = self.follow_up_channels()
            if "email" in channels and self.email is None:
                raise ValueError("Email follow-up permission requires an email address.")
            has_address = all(
                value and value.strip()
                for value in (
                    self.property_address,
                    self.property_city,
                    self.property_state,
                    self.property_zip_code,
                )
            )
            has_land_parcel = bool(
                self.asset_class == "land"
                and self.parcel_id
                and self.property_county
                and self.property_state
            )
            if not has_address and not has_land_parcel:
                raise ValueError(
                    "lead.created requires a complete property address, or land APN/county/state."
                )
        elif self.event_type == "calendar.created":
            if not self.provider_appointment_id or self.appointment_start_at is None:
                raise ValueError(
                    "calendar.created requires provider_appointment_id and appointment_start_at."
                )
            if (
                self.appointment_end_at is not None
                and self.appointment_end_at <= self.appointment_start_at
            ):
                raise ValueError("Appointment end must be after its start.")
        elif format_e164(self.phone) is None:
            raise ValueError("dnc.added requires the valid phone number being suppressed.")
        return self

    def follow_up_channels(self) -> frozenset[str]:
        permission = self.follow_up_permission
        if permission is None:
            return frozenset()
        if permission == "phone_email_and_sms":
            return frozenset({"phone", "email", "sms"})
        return frozenset(permission.split("_and_"))

    def raw_payload(self) -> dict[str, Any]:
        return self.model_dump(mode="json")
