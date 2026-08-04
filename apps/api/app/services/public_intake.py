import hashlib
import secrets
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from fastapi import HTTPException, status
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
    SellerIntakeEnrichmentCreate,
    SellerIntakeEnrichmentResponse,
    SellerIntakeResponse,
)
from app.services.ai_operations import enqueue_lead_created_ai_work
from app.services.bootstrap import bootstrap_foundation
from app.services.conversion_events import record_conversion_event, with_meta_browser_metadata
from app.services.inbox import ensure_primary_conversation
from app.services.lead_manager import ensure_inbound_case
from app.services.marketing import enqueue_meta_web_conversion
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
ENRICHMENT_TOKEN_LIFETIME = timedelta(hours=24)


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
    submitted_at = datetime.now(UTC)
    enrichment_token = secrets.token_urlsafe(32)
    enrichment_expires_at = submitted_at + ENRICHMENT_TOKEN_LIFETIME
    organization = get_default_organization(db)
    duplicate_match = find_duplicate_match(db, organization, payload)
    contact = duplicate_match.contact or create_contact(db, organization, payload)
    ensure_contact_methods(db, organization, contact, payload)
    property_record = duplicate_match.property_record or create_property(db, organization, payload)
    lead = duplicate_match.lead or create_lead(db, organization, contact, property_record, payload)
    apply_public_intake_context(lead, property_record, payload)
    ensure_primary_conversation(db, lead)
    matched_existing_lead = duplicate_match.lead is not None
    if not matched_existing_lead:
        enqueue_lead_created_ai_work(db, lead, source="public_website")
    ensure_inbound_case(
        db,
        organization_id=organization.id,
        lead=lead,
        submitted_at=submitted_at,
        sla_minutes=get_settings().speed_to_lead_due_minutes,
    )
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
            enrichment_token_hash=hash_enrichment_token(enrichment_token),
            enrichment_expires_at=enrichment_expires_at,
        )
    )
    db.add_all(
        [
            create_attribution_touch(organization.id, lead.id, "first_touch", payload),
            create_attribution_touch(organization.id, lead.id, "lead_creation", payload),
        ]
    )
    conversion_event = record_conversion_event(
        db,
        organization_id=organization.id,
        lead_id=lead.id,
        event_type="form_submit",
        attribution=payload.attribution,
        ip_address=ip_address,
        user_agent=user_agent,
        session_id=payload.conversion_session_id,
        experiment_key=payload.experiment_key,
        experiment_variant=payload.experiment_variant,
        device_category=payload.device_category,
        metadata=with_meta_browser_metadata(
            {"matched_existing_lead": matched_existing_lead},
            payload.meta_browser_event,
        ),
    )
    if payload.meta_browser_event is not None:
        enqueue_meta_web_conversion(
            db,
            event=conversion_event,
            event_name="Contact",
            event_id=payload.meta_browser_event.event_id,
            event_source_url=payload.meta_browser_event.event_source_url,
            fbc=payload.meta_browser_event.fbc,
            fbp=payload.meta_browser_event.fbp,
            email=str(payload.email) if payload.email else None,
            phone=payload.phone,
            external_id=f"{organization.id}:{lead.id}",
            occurred_at=submitted_at,
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
        enrichment_token=enrichment_token,
        enrichment_expires_at=enrichment_expires_at,
        message=(
            "Thanks. We received your updated information."
            if matched_existing_lead
            else "Thanks. Your information was received."
        ),
    )


def enrich_public_seller_lead(
    db: Session,
    payload: SellerIntakeEnrichmentCreate,
    *,
    ip_address: str | None,
    user_agent: str | None,
) -> SellerIntakeEnrichmentResponse:
    submission = db.scalar(
        select(LeadFormSubmission).where(
            LeadFormSubmission.enrichment_token_hash
            == hash_enrichment_token(payload.enrichment_token)
        )
    )
    if submission is None or token_has_expired(submission.enrichment_expires_at):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="This optional-details link is no longer available.",
        )

    lead = db.get(Lead, submission.lead_id)
    if lead is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="The property request could not be found.",
        )
    property_record = db.get(Property, lead.property_id)
    if property_record is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="The property record could not be found.",
        )

    optional_values = {
        "property_type": payload.property_type,
        "reason_for_selling": payload.reason_for_selling,
        "desired_timeline": payload.desired_timeline,
        "property_condition": payload.property_condition,
        "occupancy_status": payload.occupancy_status,
        "asking_price": payload.asking_price,
        "mortgage_balance": payload.mortgage_balance,
        "comments": payload.comments,
    }
    clean_values = {
        key: value.strip()
        for key, value in optional_values.items()
        if value is not None and value.strip()
    }
    apply_public_enrichment_context(lead, property_record, clean_values)

    enriched_at = datetime.now(UTC)
    submission.raw_payload = {**submission.raw_payload, **clean_values}
    submission.enriched_at = enriched_at
    db.add(
        ActivityEvent(
            organization_id=submission.organization_id,
            actor_user_id=None,
            entity_type="lead",
            entity_id=lead.id,
            event_type="lead.public_form_enriched",
            summary="Seller added optional property details after submitting the website request.",
        )
    )
    db.add(
        AuditEvent(
            organization_id=submission.organization_id,
            actor_user_id=None,
            actor_type="public",
            action="lead.public_enrich",
            entity_type="lead",
            entity_id=lead.id,
            previous_value=None,
            new_value={
                "fields_added": sorted(clean_values),
                "submission_id": str(submission.id),
                "ip_address": ip_address,
                "user_agent": user_agent,
            },
            reason="Optional post-submission seller details",
        )
    )
    attribution = SellerIntakeCreate.model_validate(submission.raw_payload).attribution
    record_conversion_event(
        db,
        organization_id=submission.organization_id,
        lead_id=lead.id,
        event_type="form_enrichment_submit",
        attribution=attribution,
        ip_address=ip_address,
        user_agent=user_agent,
        session_id=payload.conversion_session_id,
        metadata={"fields_added": sorted(clean_values)},
    )
    db.commit()
    return SellerIntakeEnrichmentResponse(
        lead_id=lead.id,
        enriched_at=enriched_at,
        message="Thanks. The additional property details were added to your request.",
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
        property_type=payload.property_type,
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
        property_condition=payload.property_condition,
        occupancy_status=payload.occupancy_status,
        asking_price=payload.asking_price,
        mortgage_balance=payload.mortgage_balance,
        appointment_status=None,
        next_follow_up_at=None,
    )
    db.add(lead)
    db.flush()
    ensure_primary_conversation(db, lead)
    return lead


def apply_public_intake_context(
    lead: Lead,
    property_record: Property,
    payload: SellerIntakeCreate,
) -> None:
    """Fill missing CRM context without overwriting staff-reviewed values."""
    if not property_record.property_type and payload.property_type:
        property_record.property_type = payload.property_type

    fields = {
        "motivation": payload.reason_for_selling,
        "desired_timeline": payload.desired_timeline,
        "property_condition": payload.property_condition,
        "occupancy_status": payload.occupancy_status,
        "asking_price": payload.asking_price,
        "mortgage_balance": payload.mortgage_balance,
    }
    for field_name, value in fields.items():
        if value and not getattr(lead, field_name):
            setattr(lead, field_name, value)


def apply_public_enrichment_context(
    lead: Lead,
    property_record: Property,
    values: dict[str, str],
) -> None:
    """Add seller context while preserving anything staff already reviewed."""
    property_type = values.get("property_type")
    if property_type and not property_record.property_type:
        property_record.property_type = property_type

    lead_fields = {
        "motivation": values.get("reason_for_selling"),
        "desired_timeline": values.get("desired_timeline"),
        "property_condition": values.get("property_condition"),
        "occupancy_status": values.get("occupancy_status"),
        "asking_price": values.get("asking_price"),
        "mortgage_balance": values.get("mortgage_balance"),
    }
    for field_name, value in lead_fields.items():
        if value and not getattr(lead, field_name):
            setattr(lead, field_name, value)


def hash_enrichment_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def token_has_expired(expires_at: datetime | None) -> bool:
    if expires_at is None:
        return True
    comparable_expiration = (
        expires_at.replace(tzinfo=UTC) if expires_at.tzinfo is None else expires_at
    )
    return comparable_expiration <= datetime.now(UTC)


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
