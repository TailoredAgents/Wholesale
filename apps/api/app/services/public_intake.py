import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.foundation import (
    ActivityEvent,
    AttributionTouch,
    AuditEvent,
    ConsentRecord,
    Contact,
    Lead,
    LeadFormSubmission,
    Organization,
    Property,
)
from app.schemas.public_intake import (
    CONSENT_WORDING,
    SellerIntakeCreate,
    SellerIntakeResponse,
)


def create_public_seller_lead(
    db: Session,
    payload: SellerIntakeCreate,
    *,
    ip_address: str | None,
    user_agent: str | None,
) -> SellerIntakeResponse:
    organization = get_default_organization(db)
    contact = Contact(
        organization_id=organization.id,
        legal_name=payload.name,
        preferred_name=None,
        contact_type="seller",
        assigned_user_id=None,
    )
    db.add(contact)
    db.flush()

    property_record = Property(
        organization_id=organization.id,
        street_address=payload.property_address,
        city=payload.property_city,
        state=payload.property_state.upper(),
        postal_code=payload.property_postal_code,
        county=None,
        property_type=None,
    )
    db.add(property_record)
    db.flush()

    lead = Lead(
        organization_id=organization.id,
        contact_id=contact.id,
        property_id=property_record.id,
        assigned_user_id=None,
        source=payload.attribution.utm_source or "website",
        stage_key="new",
        lead_temperature=None,
    )
    db.add(lead)
    db.flush()

    db.add(
        ConsentRecord(
            organization_id=organization.id,
            contact_id=contact.id,
            channel=payload.preferred_contact_method,
            status="granted",
            source="seller_website",
            wording_version=payload.consent_wording_version,
            wording=CONSENT_WORDING,
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
    db.add(
        ActivityEvent(
            organization_id=organization.id,
            actor_user_id=None,
            entity_type="lead",
            entity_id=lead.id,
            event_type="lead.public_form_submitted",
            summary=f"Website seller form submitted by {contact.legal_name}.",
        )
    )
    db.add(
        AuditEvent(
            organization_id=organization.id,
            actor_user_id=None,
            actor_type="public",
            action="lead.public_create",
            entity_type="lead",
            entity_id=lead.id,
            previous_value=None,
            new_value={
                "source": lead.source,
                "stage_key": lead.stage_key,
                "consent_wording_version": payload.consent_wording_version,
            },
            reason="Public seller website form submission",
        )
    )
    db.commit()
    return SellerIntakeResponse(
        lead_id=lead.id,
        contact_id=contact.id,
        property_id=property_record.id,
        consent_wording_version=payload.consent_wording_version,
        message="Thanks. Your information was received.",
    )


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


def get_default_organization(db: Session) -> Organization:
    settings = get_settings()
    organization = db.scalar(
        select(Organization).where(Organization.name == settings.default_organization_name)
    )
    if organization is None:
        organization = db.scalar(select(Organization).order_by(Organization.created_at.asc()))
    if organization is None:
        raise RuntimeError("No organization exists. Run bootstrap before accepting public leads.")
    return organization
