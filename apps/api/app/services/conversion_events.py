import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.foundation import (
    ConversionEvent,
    MarketingExperiment,
    MarketingExperimentAssignment,
    Organization,
)
from app.schemas.public_intake import (
    ConversionEventCreate,
    MetaBrowserEvent,
    SellerIntakeAttribution,
)
from app.services.marketing import enqueue_meta_web_conversion


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
        experiment_key=payload.experiment_key,
        experiment_variant=payload.experiment_variant,
        device_category=payload.device_category,
        metadata=with_meta_browser_metadata(payload.metadata, payload.meta_browser_event),
    )
    if payload.event_type == "page_view" and payload.meta_browser_event is not None:
        enqueue_meta_web_conversion(
            db,
            event=event,
            event_name="ViewContent",
            event_id=payload.meta_browser_event.event_id,
            event_source_url=payload.meta_browser_event.event_source_url,
            fbc=payload.meta_browser_event.fbc,
            fbp=payload.meta_browser_event.fbp,
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
    experiment_key: str | None = None,
    experiment_variant: str | None = None,
    device_category: str = "unknown",
    metadata: dict[str, object] | None = None,
) -> ConversionEvent:
    experiment_id, assigned_variant = resolve_experiment_assignment(
        db,
        organization_id=organization_id,
        session_id=session_id,
        experiment_key=experiment_key,
        experiment_variant=experiment_variant,
        device_category=device_category,
        lead_id=lead_id,
    )
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
        fbclid_captured_at=attribution.fbclid_captured_at,
        session_id=session_id,
        experiment_id=experiment_id,
        experiment_variant=assigned_variant,
        device_category=normalize_device_category(device_category),
        ip_address=ip_address,
        user_agent=user_agent,
        event_metadata=metadata,
    )
    db.add(event)
    db.flush()
    return event


def resolve_experiment_assignment(
    db: Session,
    *,
    organization_id: uuid.UUID,
    session_id: str | None,
    experiment_key: str | None,
    experiment_variant: str | None,
    device_category: str,
    lead_id: uuid.UUID | None,
) -> tuple[uuid.UUID | None, str | None]:
    if not session_id or not experiment_key or not experiment_variant:
        return None, None
    experiment = db.scalar(
        select(MarketingExperiment).where(
            MarketingExperiment.organization_id == organization_id,
            MarketingExperiment.experiment_key == experiment_key,
        )
    )
    if experiment is None:
        return None, None
    valid_variants = {
        str(variant.get("key"))
        for variant in experiment.variants
        if isinstance(variant, dict) and variant.get("key")
    }
    assignment = db.scalar(
        select(MarketingExperimentAssignment).where(
            MarketingExperimentAssignment.experiment_id == experiment.id,
            MarketingExperimentAssignment.session_id == session_id,
        )
    )
    if assignment is not None:
        if lead_id is not None and assignment.lead_id is None:
            assignment.lead_id = lead_id
        return experiment.id, assignment.variant_key
    if experiment.status != "running" or experiment_variant not in valid_variants:
        return None, None
    assignment = MarketingExperimentAssignment(
        organization_id=organization_id,
        experiment_id=experiment.id,
        session_id=session_id,
        variant_key=experiment_variant,
        device_category=normalize_device_category(device_category),
        lead_id=lead_id,
    )
    db.add(assignment)
    db.flush()
    return experiment.id, experiment_variant


def normalize_device_category(value: str) -> str:
    return value if value in {"desktop", "tablet", "mobile"} else "unknown"


def with_meta_browser_metadata(
    metadata: dict[str, object] | None,
    meta_browser_event: MetaBrowserEvent | None,
) -> dict[str, object] | None:
    if meta_browser_event is None:
        return metadata
    result = dict(metadata or {})
    result["meta_browser_event"] = {
        "event_id": meta_browser_event.event_id,
        "event_source_url": meta_browser_event.event_source_url,
        "fbc": meta_browser_event.fbc,
        "fbp": meta_browser_event.fbp,
    }
    return result


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
