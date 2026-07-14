import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.foundation import ConversionEvent, Organization
from app.schemas.public_intake import ConversionEventCreate, SellerIntakeAttribution


def record_public_conversion_event(
    db: Session,
    payload: ConversionEventCreate,
    *,
    ip_address: str | None,
    user_agent: str | None,
) -> ConversionEvent:
    organization = get_default_organization(db)
    event = record_conversion_event(
        db,
        organization_id=organization.id,
        event_type=payload.event_type,
        attribution=payload.attribution,
        ip_address=ip_address,
        user_agent=user_agent,
        session_id=payload.session_id,
        metadata=payload.metadata,
    )
    db.commit()
    db.refresh(event)
    return event


def record_conversion_event(
    db: Session,
    *,
    organization_id: uuid.UUID,
    event_type: str,
    attribution: SellerIntakeAttribution,
    ip_address: str | None,
    user_agent: str | None,
    lead_id: uuid.UUID | None = None,
    session_id: str | None = None,
    metadata: dict[str, object] | None = None,
) -> ConversionEvent:
    event = ConversionEvent(
        organization_id=organization_id,
        lead_id=lead_id,
        event_type=event_type,
        landing_page=attribution.landing_page,
        referrer=attribution.referrer,
        source=attribution.utm_source,
        medium=attribution.utm_medium,
        campaign=attribution.utm_campaign,
        term=attribution.utm_term,
        content=attribution.utm_content,
        gclid=attribution.gclid,
        fbclid=attribution.fbclid,
        session_id=session_id,
        ip_address=ip_address,
        user_agent=user_agent,
        event_metadata=metadata,
    )
    db.add(event)
    db.flush()
    return event


def get_default_organization(db: Session) -> Organization:
    settings = get_settings()
    organization = db.scalar(
        select(Organization).where(Organization.name == settings.default_organization_name)
    )
    if organization is None:
        organization = db.scalar(select(Organization).order_by(Organization.created_at.asc()))
    if organization is None:
        raise RuntimeError("No organization exists. Run bootstrap before accepting public events.")
    return organization
