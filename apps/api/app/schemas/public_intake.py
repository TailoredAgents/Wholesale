from datetime import UTC, datetime, timedelta
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field, field_validator, model_validator

from app.domain.assets import LAND_ASSET_CLASS, asset_class_for_property_type
from app.services.communication_compliance import format_e164

CONTACT_CONSENT_WORDINGS = {
    "seller-contact-web-v2": (
        "By submitting this form, you authorize Stonegate Home Buyers to contact you by "
        "phone call or email about your property and cash offer request. This permission "
        "does not include text messages."
    ),
    "seller-contact-web-v3": (
        "By submitting this form, you authorize Stonegate Home Buyers to contact you by "
        "phone call or email about your property inquiry and possible selling options. "
        "This permission does not include text messages."
    ),
}
CONSENT_WORDING_VERSION = "seller-contact-web-v3"
CONSENT_WORDING = CONTACT_CONSENT_WORDINGS[CONSENT_WORDING_VERSION]

SMS_CONSENT_WORDINGS = {
    "seller-sms-web-v1": (
        "Yes, I agree to receive recurring automated text messages from Stonegate Home Buyers "
        "about my property inquiry, appointments, and cash offer updates at the number provided. "
        "Message frequency varies. Message and data rates may apply. Reply STOP to opt out or "
        "HELP for help. Consent is not a condition of purchase. See our Terms & Conditions and "
        "Privacy Policy."
    ),
    "seller-sms-web-v2": (
        "By checking this optional box, I agree to receive recurring automated text messages "
        "from Stonegate Home Buyers about my property inquiry, appointments, and cash offer "
        "updates at the number provided. Message frequency varies. Message and data rates may "
        "apply. Reply STOP to opt out or HELP for help. Consent is not a condition of purchase. "
        "See our Terms & Conditions and Privacy Policy."
    ),
    "seller-sms-web-v3": (
        "By checking this optional box, I agree to receive recurring automated text messages "
        "from Stonegate Home Buyers about my property inquiry, appointments, and possible "
        "selling options at the number provided. Message frequency varies. Message and data "
        "rates may apply. Reply STOP to opt out or HELP for help. Consent is not a condition of "
        "purchase. See our Terms & Conditions and Privacy Policy."
    ),
}
SMS_CONSENT_WORDING_VERSION = "seller-sms-web-v3"
SMS_CONSENT_WORDING = SMS_CONSENT_WORDINGS[SMS_CONSENT_WORDING_VERSION]


class SellerIntakeAttribution(BaseModel):
    landing_page: str | None = Field(default=None, max_length=255)
    referrer: str | None = Field(default=None, max_length=500)
    utm_source: str | None = Field(default=None, max_length=120)
    utm_medium: str | None = Field(default=None, max_length=120)
    utm_campaign: str | None = Field(default=None, max_length=255)
    utm_term: str | None = Field(default=None, max_length=255)
    utm_content: str | None = Field(default=None, max_length=255)
    gclid: str | None = Field(default=None, max_length=255)
    fbclid: str | None = Field(default=None, max_length=255)
    fbclid_captured_at: datetime | None = None

    @field_validator("fbclid_captured_at", mode="before")
    @classmethod
    def parse_optional_meta_click_capture(cls, value: object) -> datetime | None:
        if isinstance(value, datetime):
            return value
        if not isinstance(value, str) or not value.strip():
            return None
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None

    @model_validator(mode="after")
    def validate_meta_click_capture(self) -> "SellerIntakeAttribution":
        """Keep a click's original timestamp bound to the click that supplied it."""
        captured_at = self.fbclid_captured_at
        if captured_at is None:
            return self
        if (
            not self.fbclid
            or not self.fbclid.strip()
            or captured_at.tzinfo is None
            or captured_at.utcoffset() is None
            or captured_at.astimezone(UTC) > datetime.now(UTC) + timedelta(minutes=5)
        ):
            self.fbclid_captured_at = None
        return self


class MetaBrowserEvent(BaseModel):
    event_id: str = Field(min_length=8, max_length=255)
    event_source_url: str = Field(min_length=1, max_length=500)
    fbc: str | None = Field(default=None, max_length=255)
    fbp: str | None = Field(default=None, max_length=255)


class ConversionEventCreate(BaseModel):
    event_type: str = Field(min_length=1, max_length=80)
    session_id: str | None = Field(default=None, max_length=120)
    experiment_key: str | None = Field(default=None, max_length=80)
    experiment_variant: str | None = Field(default=None, max_length=80)
    device_category: str = Field(default="unknown", max_length=20)
    metadata: dict[str, object] | None = None
    attribution: SellerIntakeAttribution = Field(default_factory=SellerIntakeAttribution)
    meta_browser_event: MetaBrowserEvent | None = None


class ConversionEventResponse(BaseModel):
    id: UUID
    event_type: str


class PublicAddressSuggestion(BaseModel):
    provider_id: str | None = Field(default=None, max_length=128)
    label: str = Field(min_length=1, max_length=300)
    street_address: str = Field(min_length=1, max_length=200)
    city: str = Field(min_length=1, max_length=120)
    state: str = Field(min_length=2, max_length=2)
    postal_code: str = Field(min_length=5, max_length=10)


class PublicAddressSuggestionsResponse(BaseModel):
    available: bool
    suggestions: list[PublicAddressSuggestion] = Field(default_factory=list, max_length=6)


class WebsiteSellerAddressCaptureCreate(BaseModel):
    intake_attempt_id: UUID
    property_address: str = Field(min_length=1, max_length=255)
    property_city: str = Field(min_length=1, max_length=120)
    property_state: str = Field(default="GA", pattern=r"^[A-Za-z]{2}$")
    property_postal_code: str = Field(pattern=r"^\d{5}(?:-\d{4})?$")
    # Kept optional for rolling compatibility with the earlier Step 1 payload. New
    # website journeys collect timeline only in post-submit enrichment.
    desired_timeline: str | None = Field(default=None, min_length=1, max_length=120)
    company_website: str | None = Field(default=None, max_length=255)
    conversion_session_id: str | None = Field(default=None, max_length=120)
    experiment_key: str | None = Field(default=None, max_length=80)
    experiment_variant: str | None = Field(default=None, max_length=80)
    device_category: str = Field(default="unknown", max_length=20)
    attribution: SellerIntakeAttribution = Field(default_factory=SellerIntakeAttribution)
    meta_browser_event: MetaBrowserEvent

    @field_validator(
        "property_address",
        "property_city",
        "property_state",
        "property_postal_code",
        "desired_timeline",
        mode="before",
    )
    @classmethod
    def normalize_address_capture_values(cls, value: object) -> object:
        return value.strip() if isinstance(value, str) else value

    @field_validator("property_state")
    @classmethod
    def uppercase_address_capture_state(cls, value: str) -> str:
        return value.upper()

    @model_validator(mode="after")
    def require_complete_property_address(self) -> "WebsiteSellerAddressCaptureCreate":
        if self.company_website:
            raise ValueError("Invalid form submission.")
        if not all(
            value.strip()
            for value in (
                self.property_address,
                self.property_city,
                self.property_state,
                self.property_postal_code,
            )
        ):
            raise ValueError("A complete property address is required.")
        expected_event_id = f"stonegate-lead-{self.intake_attempt_id}"
        if self.meta_browser_event.event_id != expected_event_id:
            raise ValueError("The address-lead event identity is invalid.")
        return self


class WebsiteSellerAddressCaptureResponse(BaseModel):
    lead_id: UUID
    contact_id: UUID
    property_id: UUID
    completion_status: str
    created: bool


class SellerIntakeCreate(BaseModel):
    intake_attempt_id: UUID | None = None
    property_address: str = Field(default="", max_length=255)
    property_city: str = Field(default="", max_length=120)
    property_state: str = Field(default="GA", min_length=2, max_length=2)
    property_postal_code: str = Field(default="", max_length=20)
    property_county: str | None = Field(default=None, max_length=120)
    property_type: str | None = Field(default=None, max_length=80)
    asset_class: str | None = Field(default=None, max_length=40)
    parcel_id: str | None = Field(default=None, max_length=255)
    name: str = Field(min_length=1, max_length=255)
    phone: str | None = Field(default=None, max_length=40)
    email: EmailStr | None = None
    preferred_contact_method: str = Field(default="phone", max_length=40)
    reason_for_selling: str | None = Field(default=None, max_length=500)
    desired_timeline: str | None = Field(default=None, max_length=120)
    property_condition: str | None = Field(default=None, max_length=120)
    occupancy_status: str | None = Field(default=None, max_length=120)
    asking_price: str | None = Field(default=None, max_length=120)
    mortgage_balance: str | None = Field(default=None, max_length=120)
    comments: str | None = Field(default=None, max_length=1000)
    company_website: str | None = Field(default=None, max_length=255)
    consent_to_contact: bool
    consent_wording_version: str = Field(default=CONSENT_WORDING_VERSION, max_length=80)
    sms_consent: bool = False
    sms_consent_wording_version: str = Field(
        default=SMS_CONSENT_WORDING_VERSION,
        max_length=80,
    )
    conversion_session_id: str | None = Field(default=None, max_length=120)
    experiment_key: str | None = Field(default=None, max_length=80)
    experiment_variant: str | None = Field(default=None, max_length=80)
    device_category: str = Field(default="unknown", max_length=20)
    attribution: SellerIntakeAttribution = Field(default_factory=SellerIntakeAttribution)
    meta_browser_event: MetaBrowserEvent | None = None

    @model_validator(mode="after")
    def require_contact_channel(self) -> "SellerIntakeCreate":
        if self.company_website:
            raise ValueError("Invalid form submission.")
        if self.consent_wording_version not in CONTACT_CONSENT_WORDINGS:
            raise ValueError("Unsupported contact-consent wording version.")
        if self.sms_consent_wording_version not in SMS_CONSENT_WORDINGS:
            raise ValueError("Unsupported SMS-consent wording version.")
        if not self.phone and not self.email:
            raise ValueError("Either phone or email is required.")
        if not self.consent_to_contact:
            raise ValueError("Consent to contact is required.")
        if self.sms_consent and format_e164(self.phone) is None:
            raise ValueError("A valid phone number is required to consent to text messages.")
        if self.preferred_contact_method == "sms" and not self.sms_consent:
            raise ValueError("Text message consent is required when text is selected.")
        if self.preferred_contact_method == "phone" and not self.phone:
            raise ValueError("A phone number is required when phone is selected.")
        if self.preferred_contact_method == "email" and not self.email:
            raise ValueError("An email address is required when email is selected.")
        asset_class = asset_class_for_property_type(
            self.property_type,
            explicit_asset_class=self.asset_class,
        )
        has_address = all(
            value.strip()
            for value in (
                self.property_address,
                self.property_city,
                self.property_state,
                self.property_postal_code,
            )
        )
        has_parcel = bool(
            self.parcel_id
            and self.parcel_id.strip()
            and self.property_county
            and self.property_county.strip()
            and self.property_state.strip()
        )
        if asset_class == LAND_ASSET_CLASS and not (has_address or has_parcel):
            raise ValueError(
                "Land leads require either a complete address or APN with county and state."
            )
        if asset_class != LAND_ASSET_CLASS and not has_address:
            raise ValueError("A complete property address is required.")
        return self


class WebsiteSellerIntakeCreate(SellerIntakeCreate):
    phone: str | None = Field(max_length=40)

    @model_validator(mode="after")
    def require_website_phone(self) -> "WebsiteSellerIntakeCreate":
        if not self.phone or not self.phone.strip():
            raise ValueError("A phone number is required.")
        digits = "".join(character for character in self.phone if character.isdigit())
        if not 10 <= len(digits) <= 15:
            raise ValueError("Enter a complete phone number.")
        if self.intake_attempt_id is not None and self.meta_browser_event is None:
            raise ValueError(
                "The website intake attempt and Meta browser event must be provided together."
            )
        if self.intake_attempt_id is not None and self.meta_browser_event is not None:
            expected_event_id = f"stonegate-contact-{self.intake_attempt_id}"
            if self.meta_browser_event.event_id != expected_event_id:
                raise ValueError("The contact event identity is invalid.")
        return self


class SellerIntakeResponse(BaseModel):
    lead_id: UUID
    contact_id: UUID
    property_id: UUID
    duplicate_status: str
    matched_existing_lead: bool
    consent_wording_version: str
    enrichment_token: str
    enrichment_expires_at: datetime
    message: str
    meta_pixel_event_name: Literal["Lead", "Contact"] | None = None


class SellerIntakeEnrichmentCreate(BaseModel):
    enrichment_token: str = Field(min_length=32, max_length=255)
    property_type: str | None = Field(default=None, max_length=80)
    reason_for_selling: str | None = Field(default=None, max_length=500)
    desired_timeline: str | None = Field(default=None, max_length=120)
    property_condition: str | None = Field(default=None, max_length=120)
    occupancy_status: str | None = Field(default=None, max_length=120)
    asking_price: str | None = Field(default=None, max_length=120)
    mortgage_balance: str | None = Field(default=None, max_length=120)
    comments: str | None = Field(default=None, max_length=1000)
    conversion_session_id: str | None = Field(default=None, max_length=120)

    @model_validator(mode="after")
    def require_enrichment_detail(self) -> "SellerIntakeEnrichmentCreate":
        values = (
            self.property_type,
            self.reason_for_selling,
            self.desired_timeline,
            self.property_condition,
            self.occupancy_status,
            self.asking_price,
            self.mortgage_balance,
            self.comments,
        )
        if not any(value and value.strip() for value in values):
            raise ValueError("Add at least one optional property detail.")
        return self


class SellerIntakeEnrichmentResponse(BaseModel):
    lead_id: UUID
    enriched_at: datetime
    message: str
