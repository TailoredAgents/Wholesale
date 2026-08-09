import re
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

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
