import uuid
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.foundation import (
    ActivityEvent,
    AttributionTouch,
    AuditEvent,
    ConsentRecord,
    Contact,
    ContactMethod,
    Lead,
    LeadFormSubmission,
    Organization,
    Property,
    Role,
    RoleAssignment,
    User,
)
from app.schemas.public_intake import (
    CONSENT_WORDING,
    CONSENT_WORDING_VERSION,
    SMS_CONSENT_WORDING,
    SMS_CONSENT_WORDING_VERSION,
    SellerIntakeCreate,
    SellerIntakeResponse,
)
from app.services.bootstrap import bootstrap_foundation
from app.services.conversion_events import record_conversion_event
from app.services.inbox import ensure_primary_conversation
from app.services.property_validation import canonical_address_key
from app.services.tasks import ensure_speed_to_lead_task

ACTIVE_LEAD_STAGES = {
    "new",
    "contact_attempt_due",
    "attempting_contact",
    "contacted",
    "qualification_in_progress",
    "qualified",
    "appointment_scheduled",
    "underwriting",
    "offer_pending_approval",
    "offer_ready",
    "offer_presented",
    "negotiating",
    "long_term_follow_up",
    "under_contract",
    "reopened",
}


@dataclass(frozen=True)
class DuplicateMatch:
    contact: Contact | None
    property_record: Property | None
    lead: Lead | None


def create_public_seller_lead(
    db: Session,
    payload: SellerIntakeCreate,
    *,
    ip_address: str | None,
    user_agent: str | None,
) -> SellerIntakeResponse:
    organization = get_default_organization(db)
    duplicate_match = find_duplicate_match(db, organization, payload)
    contact = duplicate_match.contact or create_contact(db, organization, payload)
    ensure_contact_methods(db, organization, contact, payload)
    property_record = duplicate_match.property_record or create_property(db, organization, payload)
    lead = duplicate_match.lead or create_lead(db, organization, contact, property_record, payload)
    ensure_primary_conversation(db, lead)
    matched_existing_lead = duplicate_match.lead is not None
    ensure_speed_to_lead_task(db, lead, contact)

    contact_channels = []
    if payload.phone:
        contact_channels.append("phone")
    if payload.email:
        contact_channels.append("email")
    for channel in contact_channels:
        db.add(
            ConsentRecord(
                organization_id=organization.id,
                contact_id=contact.id,
                channel=channel,
                status="granted",
                source="seller_website",
                wording_version=CONSENT_WORDING_VERSION,
                wording=CONSENT_WORDING,
                captured_ip=ip_address,
                user_agent=user_agent,
            )
        )
    if payload.sms_consent:
        db.add(
            ConsentRecord(
                organization_id=organization.id,
                contact_id=contact.id,
                channel="sms",
                status="granted",
                source="seller_website",
                wording_version=SMS_CONSENT_WORDING_VERSION,
                wording=SMS_CONSENT_WORDING,
                captured_ip=ip_address,
                user_agent=user_agent,
            )
        )
    db.add(
        LeadFormSubmission(
            organization_id=organization.id,
            lead_id=lead.id,
            landing_page=payload.attribution.landing_page,
            referrer=payload.attribution.referrer,
            ip_address=ip_address,
            user_agent=user_agent,
            raw_payload=payload.model_dump(mode="json"),
        )
    )
    db.add_all(
        [
            create_attribution_touch(organization.id, lead.id, "first_touch", payload),
            create_attribution_touch(organization.id, lead.id, "lead_creation", payload),
        ]
    )
    record_conversion_event(
        db,
        organization_id=organization.id,
        lead_id=lead.id,
        event_type="form_submit",
        attribution=payload.attribution,
        ip_address=ip_address,
        user_agent=user_agent,
        metadata={"matched_existing_lead": matched_existing_lead},
    )
    db.add(
        ActivityEvent(
            organization_id=organization.id,
            actor_user_id=None,
            entity_type="lead",
            entity_id=lead.id,
            event_type=(
                "lead.public_duplicate_submitted"
                if matched_existing_lead
                else "lead.public_form_submitted"
            ),
            summary=(
                f"Duplicate website seller form matched {contact.legal_name}."
                if matched_existing_lead
                else f"Website seller form submitted by {contact.legal_name}."
            ),
        )
    )
    db.add(
        AuditEvent(
            organization_id=organization.id,
            actor_user_id=None,
            actor_type="public",
            action="lead.public_duplicate" if matched_existing_lead else "lead.public_create",
            entity_type="lead",
            entity_id=lead.id,
            previous_value=None,
            new_value={
                "source": lead.source,
                "stage_key": lead.stage_key,
                "consent_wording_version": CONSENT_WORDING_VERSION,
                "sms_consent": payload.sms_consent,
                "sms_consent_wording_version": (
                    SMS_CONSENT_WORDING_VERSION if payload.sms_consent else None
                ),
                "matched_existing_lead": matched_existing_lead,
            },
            reason="Public seller website form submission",
        )
    )
    from app.services.acquisition_operations import create_notification

    recipients = db.scalars(
        select(User)
        .join(RoleAssignment, RoleAssignment.user_id == User.id)
        .join(Role, Role.id == RoleAssignment.role_id)
        .where(
            User.organization_id == organization.id,
            User.is_active.is_(True),
            Role.key.in_(("owner", "founder_operator", "acquisition_manager")),
        )
    ).unique()
    for recipient in recipients:
        create_notification(
            db,
            organization_id=organization.id,
            recipient_user_id=recipient.id,
            notification_type="new_lead" if not matched_existing_lead else "duplicate_submission",
            title="New seller lead" if not matched_existing_lead else "Seller submitted again",
            body=f"{contact.legal_name} submitted property information from the public website.",
            entity_type="lead",
            entity_id=lead.id,
            action_url=f"/os/leads/{lead.id}",
            dedupe_key=(
                f"new-public-lead:{lead.id}"
                if not matched_existing_lead
                else f"duplicate-public-lead:{lead.id}:{uuid.uuid4()}"
            ),
        )
    db.commit()
    return SellerIntakeResponse(
        lead_id=lead.id,
        contact_id=contact.id,
        property_id=property_record.id,
        duplicate_status="matched_existing_lead" if matched_existing_lead else "created",
        matched_existing_lead=matched_existing_lead,
        consent_wording_version=CONSENT_WORDING_VERSION,
        message=(
            "Thanks. We received your updated information."
            if matched_existing_lead
            else "Thanks. Your information was received."
        ),
    )


def find_duplicate_match(
    db: Session,
    organization: Organization,
    payload: SellerIntakeCreate,
) -> DuplicateMatch:
    contact = find_matching_contact(db, organization, payload)
    property_record = find_matching_property(db, organization, payload)
    lead = None
    if contact is not None and property_record is not None:
        lead = db.scalar(
            select(Lead).where(
                Lead.organization_id == organization.id,
                Lead.archived_at.is_(None),
                Lead.contact_id == contact.id,
                Lead.property_id == property_record.id,
                Lead.stage_key.in_(ACTIVE_LEAD_STAGES),
            )
        )
    return DuplicateMatch(contact=contact, property_record=property_record, lead=lead)


def find_matching_contact(
    db: Session,
    organization: Organization,
    payload: SellerIntakeCreate,
) -> Contact | None:
    normalized_values = []
    if payload.email:
        normalized_values.append(("email", normalize_email(str(payload.email))))
    if payload.phone:
        normalized_values.append(("phone", normalize_phone(payload.phone)))

    for method_type, normalized_value in normalized_values:
        if not normalized_value:
            continue
        contact_method = db.scalar(
            select(ContactMethod).where(
                ContactMethod.organization_id == organization.id,
                ContactMethod.method_type == method_type,
                ContactMethod.normalized_value == normalized_value,
            )
        )
        if contact_method is not None:
            return db.get(Contact, contact_method.contact_id)
    return None


def find_matching_property(
    db: Session,
    organization: Organization,
    payload: SellerIntakeCreate,
) -> Property | None:
    normalized_address_key = normalize_address_key(payload)
    return db.scalar(
        select(Property).where(
            Property.organization_id == organization.id,
            Property.normalized_address_key == normalized_address_key,
        )
    )


def create_contact(db: Session, organization: Organization, payload: SellerIntakeCreate) -> Contact:
    contact = Contact(
        organization_id=organization.id,
        legal_name=payload.name,
        preferred_name=None,
        contact_type="seller",
        assigned_user_id=None,
    )
    db.add(contact)
    db.flush()
    return contact


def ensure_contact_methods(
    db: Session,
    organization: Organization,
    contact: Contact,
    payload: SellerIntakeCreate,
) -> None:
    if payload.email:
        ensure_contact_method(
            db,
            organization,
            contact,
            method_type="email",
            value=str(payload.email),
            normalized_value=normalize_email(str(payload.email)),
        )
    if payload.phone:
        ensure_contact_method(
            db,
            organization,
            contact,
            method_type="phone",
            value=payload.phone,
            normalized_value=normalize_phone(payload.phone),
        )


def ensure_contact_method(
    db: Session,
    organization: Organization,
    contact: Contact,
    *,
    method_type: str,
    value: str,
    normalized_value: str,
) -> None:
    if not normalized_value:
        return
    existing = db.scalar(
        select(ContactMethod).where(
            ContactMethod.organization_id == organization.id,
            ContactMethod.contact_id == contact.id,
            ContactMethod.method_type == method_type,
            ContactMethod.normalized_value == normalized_value,
        )
    )
    if existing is not None:
        return
    db.add(
        ContactMethod(
            organization_id=organization.id,
            contact_id=contact.id,
            method_type=method_type,
            value=value,
            normalized_value=normalized_value,
            is_primary=True,
        )
    )
    db.flush()


def create_property(
    db: Session,
    organization: Organization,
    payload: SellerIntakeCreate,
) -> Property:
    property_record = Property(
        organization_id=organization.id,
        street_address=payload.property_address,
        city=payload.property_city,
        state=payload.property_state.upper(),
        postal_code=payload.property_postal_code,
        county=None,
        property_type=None,
        normalized_address_key=normalize_address_key(payload),
    )
    db.add(property_record)
    db.flush()
    return property_record


def create_lead(
    db: Session,
    organization: Organization,
    contact: Contact,
    property_record: Property,
    payload: SellerIntakeCreate,
) -> Lead:
    lead = Lead(
        organization_id=organization.id,
        contact_id=contact.id,
        property_id=property_record.id,
        assigned_user_id=None,
        source=payload.attribution.utm_source or "website",
        stage_key="new",
        lead_temperature=None,
        motivation=payload.reason_for_selling,
        desired_timeline=payload.desired_timeline,
        property_condition=None,
        occupancy_status=None,
        asking_price=payload.asking_price,
        mortgage_balance=None,
        appointment_status=None,
        next_follow_up_at=None,
    )
    db.add(lead)
    db.flush()
    ensure_primary_conversation(db, lead)
    return lead


def create_attribution_touch(
    organization_id: uuid.UUID,
    lead_id: uuid.UUID,
    touch_type: str,
    payload: SellerIntakeCreate,
) -> AttributionTouch:
    attribution = payload.attribution
    return AttributionTouch(
        organization_id=organization_id,
        lead_id=lead_id,
        touch_type=touch_type,
        source=attribution.utm_source,
        medium=attribution.utm_medium,
        campaign=attribution.utm_campaign,
        term=attribution.utm_term,
        content=attribution.utm_content,
        gclid=attribution.gclid,
        fbclid=attribution.fbclid,
        landing_page=attribution.landing_page,
        referrer=attribution.referrer,
    )


def normalize_email(value: str) -> str:
    return value.strip().lower()


def normalize_phone(value: str) -> str:
    return "".join(character for character in value if character.isdigit())


def normalize_address_key(payload: SellerIntakeCreate) -> str:
    return canonical_address_key(
        payload.property_address,
        payload.property_city,
        payload.property_state,
        payload.property_postal_code,
    )


def get_default_organization(db: Session) -> Organization:
    settings = get_settings()
    organization = db.scalar(
        select(Organization).where(Organization.name == settings.default_organization_name)
    )
    if organization is None:
        organization = db.scalar(select(Organization).order_by(Organization.created_at.asc()))
    if organization is None:
        result = bootstrap_foundation(
            db,
            organization_name=settings.default_organization_name,
            admin_email=None,
            admin_name=None,
        )
        organization = result.organization
    return organization
