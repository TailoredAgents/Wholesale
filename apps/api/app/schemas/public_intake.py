from uuid import UUID

from pydantic import BaseModel, EmailStr, Field, model_validator

CONSENT_WORDING_VERSION = "seller-contact-web-v2"
CONSENT_WORDING = (
    "By submitting this form, you authorize Stonegate Home Buyers to contact you by "
    "phone call or email about your property and cash offer request. This permission "
    "does not include text messages."
)
SMS_CONSENT_WORDING_VERSION = "seller-sms-web-v2"
SMS_CONSENT_WORDING = (
    "By checking this optional box, I agree to receive recurring automated text "
    "messages from Stonegate Home Buyers about my property inquiry, appointments, "
    "and cash offer updates at the number provided. Message frequency varies. "
    "Message and data rates may apply. Reply STOP to opt out or HELP for help. "
    "Consent is not a condition of purchase. See the Stonegate Home Buyers Terms "
    "and Conditions and Privacy Policy."
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
    sms_consent: bool = False
    sms_consent_wording_version: str = Field(
        default=SMS_CONSENT_WORDING_VERSION,
        max_length=80,
    )
    attribution: SellerIntakeAttribution = Field(default_factory=SellerIntakeAttribution)

    @model_validator(mode="after")
    def require_contact_channel(self) -> "SellerIntakeCreate":
        if not self.phone and not self.email:
            raise ValueError("Either phone or email is required.")
        if not self.consent_to_contact:
            raise ValueError("Consent to contact is required.")
        if self.sms_consent and not self.phone:
            raise ValueError("A phone number is required to consent to text messages.")
        if self.preferred_contact_method == "sms" and not self.sms_consent:
            raise ValueError("Text message consent is required when text is selected.")
        return self


class SellerIntakeResponse(BaseModel):
    lead_id: UUID
    contact_id: UUID
    property_id: UUID
    duplicate_status: str
    matched_existing_lead: bool
    consent_wording_version: str
    message: str
