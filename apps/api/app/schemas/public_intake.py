from uuid import UUID

from pydantic import BaseModel, EmailStr, Field, model_validator

CONSENT_WORDING_VERSION = "seller-web-v1"
CONSENT_WORDING = (
    "By submitting this form, you agree that the company may contact you about your "
    "property using the phone number or email provided. Message and data rates may apply. "
    "Consent is not required as a condition of purchase."
)


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


class ConversionEventCreate(BaseModel):
    event_type: str = Field(min_length=1, max_length=80)
    session_id: str | None = Field(default=None, max_length=120)
    metadata: dict[str, object] | None = None
    attribution: SellerIntakeAttribution = Field(default_factory=SellerIntakeAttribution)


class ConversionEventResponse(BaseModel):
    id: UUID
    event_type: str


class SellerIntakeCreate(BaseModel):
    property_address: str = Field(min_length=3, max_length=255)
    property_city: str = Field(min_length=1, max_length=120)
    property_state: str = Field(default="GA", min_length=2, max_length=2)
    property_postal_code: str = Field(min_length=1, max_length=20)
    name: str = Field(min_length=1, max_length=255)
    phone: str | None = Field(default=None, max_length=40)
    email: EmailStr | None = None
    preferred_contact_method: str = Field(default="phone", max_length=40)
    reason_for_selling: str | None = Field(default=None, max_length=500)
    desired_timeline: str | None = Field(default=None, max_length=120)
    asking_price: str | None = Field(default=None, max_length=120)
    comments: str | None = Field(default=None, max_length=1000)
    company_website: str | None = Field(default=None, max_length=255)
    consent_to_contact: bool
    consent_wording_version: str = Field(default=CONSENT_WORDING_VERSION, max_length=80)
    attribution: SellerIntakeAttribution = Field(default_factory=SellerIntakeAttribution)

    @model_validator(mode="after")
    def require_contact_channel(self) -> "SellerIntakeCreate":
        if not self.phone and not self.email:
            raise ValueError("Either phone or email is required.")
        if not self.consent_to_contact:
            raise ValueError("Consent to contact is required.")
        return self


class SellerIntakeResponse(BaseModel):
    lead_id: UUID
    contact_id: UUID
    property_id: UUID
    duplicate_status: str
    matched_existing_lead: bool
    consent_wording_version: str
    message: str
