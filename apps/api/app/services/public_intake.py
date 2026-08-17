import hashlib
import secrets
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Literal, cast

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.domain.assets import asset_class_for_property_type
from app.models.base import Base
from app.models.foundation import (
    ActivityEvent,
    AttributionTouch,
    AuditEvent,
    ConsentRecord,
    Contact,
    ContactMethod,
    ConversionEvent,
    Lead,
    LeadFormSubmission,
    OfflineConversionExport,
    Organization,
    Property,
    Role,
    RoleAssignment,
    StaffLeadAlert,
    User,
)
from app.schemas.public_intake import (
    CONTACT_CONSENT_WORDINGS,
    SMS_CONSENT_WORDINGS,
    MetaBrowserEvent,
    SellerIntakeAttribution,
    SellerIntakeCreate,
    SellerIntakeEnrichmentCreate,
    SellerIntakeEnrichmentResponse,
    SellerIntakeResponse,
    WebsiteSellerAddressCaptureCreate,
    WebsiteSellerAddressCaptureResponse,
)
from app.services.ai_operations import enqueue_lead_created_ai_work
from app.services.bootstrap import bootstrap_foundation
from app.services.communication_compliance import format_e164
from app.services.conversion_events import record_conversion_event, with_meta_browser_metadata
from app.services.inbox import ensure_primary_conversation
from app.services.lead_manager import ensure_inbound_case
from app.services.marketing import (
    can_enrich_meta_web_conversion_identifiers,
    enqueue_meta_web_conversion,
    enrich_meta_web_conversion_identifiers,
    payload_hash,
    sha256,
)
from app.services.property_identity import (
    find_property_by_identity,
    normalized_address_key_or_none,
    refresh_property_identity_keys,
)
from app.services.property_intelligence import enqueue_property_research
from app.services.staff_lead_alerts import (
    WEBSITE_STAGE_1_ALERT_SOURCE_TYPE,
    WEBSITE_STAGE_ALERT_FLOW_VERSION,
    queue_staff_lead_alerts_for_lead,
    queue_website_stage_lead_alerts,
)
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
ADDRESS_ONLY_CONTACT_NAME = "Contact pending (website form)"
ADDRESS_ONLY_INTAKE_STATUS = "address_only"
COMPLETED_INTAKE_STATUS = "completed"


def address_lead_event_id(intake_attempt_id: uuid.UUID) -> str:
    return f"stonegate-lead-{intake_attempt_id}"


def contact_event_id(intake_attempt_id: uuid.UUID) -> str:
    return f"stonegate-contact-{intake_attempt_id}"


def resolve_website_attribution(
    attribution: SellerIntakeAttribution,
) -> SellerIntakeAttribution:
    """Give paid clicks a stable source even when an ad omits UTM parameters."""
    source = attribution.utm_source
    if not source and attribution.fbclid:
        source = "meta_ads"
    elif not source and attribution.gclid:
        source = "google_ads"
    if not source:
        source = "website"
    if source == attribution.utm_source:
        return attribution
    return attribution.model_copy(update={"utm_source": source})


def address_lead_meta_event(
    intake_attempt_id: uuid.UUID,
    browser_event: MetaBrowserEvent,
) -> MetaBrowserEvent:
    return browser_event.model_copy(update={"event_id": address_lead_event_id(intake_attempt_id)})


@dataclass(frozen=True)
class DuplicateMatch:
    contact: Contact | None
    property_record: Property | None
    lead: Lead | None


@dataclass(frozen=True)
class FullIntakeResolution:
    contact: Contact
    property_record: Property
    lead: Lead
    partial_submission: LeadFormSubmission | None
    matched_existing_lead: bool
    promoted_address_capture: bool


def find_conversion_event_by_meta_id(
    db: Session,
    *,
    organization_id: uuid.UUID,
    lead_id: uuid.UUID,
    event_type: str,
    event_id: str,
) -> ConversionEvent | None:
    candidates = db.scalars(
        select(ConversionEvent)
        .where(
            ConversionEvent.organization_id == organization_id,
            ConversionEvent.lead_id == lead_id,
            ConversionEvent.event_type == event_type,
        )
        .order_by(ConversionEvent.created_at.desc())
    )
    for candidate in candidates:
        metadata = candidate.event_metadata or {}
        browser_event = metadata.get("meta_browser_event")
        if isinstance(browser_event, dict) and browser_event.get("event_id") == event_id:
            return candidate
    return None


def ensure_address_lead_conversion(
    db: Session,
    *,
    organization: Organization,
    lead: Lead,
    intake_attempt_id: uuid.UUID,
    attribution: SellerIntakeAttribution,
    meta_browser_event: MetaBrowserEvent,
    ip_address: str | None,
    user_agent: str | None,
    session_id: str | None,
    experiment_key: str | None,
    experiment_variant: str | None,
    device_category: str,
) -> bool:
    """Persist the address-stage event once, regardless of request arrival order."""
    event_id = address_lead_event_id(intake_attempt_id)
    existing_export = db.scalar(
        select(OfflineConversionExport)
        .where(
            OfflineConversionExport.organization_id == organization.id,
            OfflineConversionExport.platform == "meta",
            OfflineConversionExport.event_key == event_id,
        )
        .with_for_update()
    )
    if existing_export is not None:
        if existing_export.event_name != "Lead" or existing_export.lead_id != lead.id:
            raise RuntimeError("Address-lead conversion identity is already in use.")
        if can_enrich_meta_web_conversion_identifiers(existing_export):
            enrich_meta_web_conversion_identifiers(
                existing_export,
                fbc=meta_browser_event.fbc,
                fbp=meta_browser_event.fbp,
                fbclid=attribution.fbclid,
                click_captured_at=attribution.fbclid_captured_at,
            )
            conversion_event = (
                db.get(ConversionEvent, existing_export.conversion_event_id)
                if existing_export.conversion_event_id is not None
                else None
            )
            if conversion_event is None:
                conversion_event = find_conversion_event_by_meta_id(
                    db,
                    organization_id=organization.id,
                    lead_id=lead.id,
                    event_type="address_capture",
                    event_id=event_id,
                )
            if conversion_event is not None:
                enrich_address_conversion_event_identifiers(
                    conversion_event,
                    attribution=attribution,
                    meta_browser_event=meta_browser_event,
                )
        return False

    conversion_event = find_conversion_event_by_meta_id(
        db,
        organization_id=organization.id,
        lead_id=lead.id,
        event_type="address_capture",
        event_id=event_id,
    )
    if conversion_event is None:
        conversion_event = record_conversion_event(
            db,
            organization_id=organization.id,
            lead_id=lead.id,
            event_type="address_capture",
            attribution=attribution,
            ip_address=ip_address,
            user_agent=user_agent,
            session_id=session_id,
            experiment_key=experiment_key,
            experiment_variant=experiment_variant,
            device_category=device_category,
            metadata=with_meta_browser_metadata(
                {
                    "website_intake_status": ADDRESS_ONLY_INTAKE_STATUS,
                    "intake_attempt_id": str(intake_attempt_id),
                },
                meta_browser_event,
            ),
        )
    enqueue_meta_web_conversion(
        db,
        event=conversion_event,
        event_name="Lead",
        event_id=event_id,
        event_source_url=meta_browser_event.event_source_url,
        fbc=meta_browser_event.fbc,
        fbp=meta_browser_event.fbp,
        external_id=f"{organization.id}:{lead.id}",
    )
    return True


def enrich_address_conversion_event_identifiers(
    event: ConversionEvent,
    *,
    attribution: SellerIntakeAttribution,
    meta_browser_event: MetaBrowserEvent,
) -> bool:
    """Fill missing identifier evidence on a still-mutable address event."""
    changed = False
    incoming_fbclid = (
        attribution.fbclid.strip()
        if attribution.fbclid and attribution.fbclid.strip()
        else None
    )
    persisted_fbclid = event.fbclid.strip() if event.fbclid and event.fbclid.strip() else None
    if persisted_fbclid is None and incoming_fbclid is not None:
        event.fbclid = incoming_fbclid
        persisted_fbclid = incoming_fbclid
        changed = True
    if (
        event.fbclid_captured_at is None
        and attribution.fbclid_captured_at is not None
        and incoming_fbclid is not None
        and persisted_fbclid == incoming_fbclid
    ):
        event.fbclid_captured_at = attribution.fbclid_captured_at
        changed = True

    metadata = dict(event.event_metadata or {})
    browser_metadata_value = metadata.get("meta_browser_event")
    browser_metadata = (
        dict(browser_metadata_value) if isinstance(browser_metadata_value, dict) else {}
    )
    for key, incoming in (
        ("event_id", meta_browser_event.event_id),
        ("event_source_url", meta_browser_event.event_source_url),
        ("fbc", meta_browser_event.fbc),
        ("fbp", meta_browser_event.fbp),
    ):
        existing = browser_metadata.get(key)
        if incoming and not (isinstance(existing, str) and existing.strip()):
            browser_metadata[key] = incoming
            changed = True
    if changed:
        metadata["meta_browser_event"] = browser_metadata
        event.event_metadata = metadata
    return changed


def ensure_contact_conversion(
    db: Session,
    *,
    organization: Organization,
    lead: Lead,
    attribution: SellerIntakeAttribution,
    meta_browser_event: MetaBrowserEvent,
    event_name: Literal["Lead", "Contact"],
    email: str | None,
    full_name: str,
    ip_address: str | None,
    user_agent: str | None,
    session_id: str | None,
    experiment_key: str | None,
    experiment_variant: str | None,
    device_category: str,
    occurred_at: datetime,
    event_metadata: dict[str, object],
    allow_legacy_event_name: bool = False,
) -> Literal["Lead", "Contact"]:
    internal_event_type = "contact_complete" if event_name == "Contact" else "form_submit"
    existing_export = db.scalar(
        select(OfflineConversionExport).where(
            OfflineConversionExport.organization_id == organization.id,
            OfflineConversionExport.platform == "meta",
            OfflineConversionExport.event_key == meta_browser_event.event_id,
        )
    )
    if existing_export is not None:
        if existing_export.lead_id != lead.id:
            raise RuntimeError("Contact conversion identity is already in use.")
        if existing_export.event_name != event_name:
            if allow_legacy_event_name and existing_export.event_name in {"Lead", "Contact"}:
                return cast(Literal["Lead", "Contact"], existing_export.event_name)
            raise RuntimeError("Contact conversion event name does not match its identity.")
        return event_name

    conversion_event = find_conversion_event_by_meta_id(
        db,
        organization_id=organization.id,
        lead_id=lead.id,
        event_type=internal_event_type,
        event_id=meta_browser_event.event_id,
    )
    if conversion_event is None:
        conversion_event = record_conversion_event(
            db,
            organization_id=organization.id,
            lead_id=lead.id,
            event_type=internal_event_type,
            attribution=attribution,
            ip_address=ip_address,
            user_agent=user_agent,
            session_id=session_id,
            experiment_key=experiment_key,
            experiment_variant=experiment_variant,
            device_category=device_category,
            metadata=with_meta_browser_metadata(event_metadata, meta_browser_event),
        )
    # Keep the submitted phone number inside Stonegate. The current public privacy
    # promise permits advertising identifiers such as hashed email, but explicitly
    # excludes mobile phone information from marketing-platform disclosure.
    enqueue_meta_web_conversion(
        db,
        event=conversion_event,
        event_name=event_name,
        event_id=meta_browser_event.event_id,
        event_source_url=meta_browser_event.event_source_url,
        fbc=meta_browser_event.fbc,
        fbp=meta_browser_event.fbp,
        email=email,
        full_name=full_name,
        external_id=f"{organization.id}:{lead.id}",
        occurred_at=occurred_at,
    )
    return event_name


def capture_public_seller_address(
    db: Session,
    payload: WebsiteSellerAddressCaptureCreate,
    *,
    ip_address: str | None,
    user_agent: str | None,
) -> WebsiteSellerAddressCaptureResponse:
    """Create or refresh a cold CRM lead from a completed property address.

    This deliberately avoids seller-contact automation until Step 2 supplies a real
    contact channel and the website contact notice is submitted.
    """
    organization = get_default_organization(db)
    attribution = resolve_website_attribution(payload.attribution)
    lock_intake_attempt(db, payload.intake_attempt_id)
    existing = find_intake_attempt_submission(
        db,
        organization_id=organization.id,
        intake_attempt_id=payload.intake_attempt_id,
        for_update=True,
    )
    if existing is not None:
        lead = db.get(Lead, existing.lead_id)
        if lead is None:
            raise RuntimeError("Address-capture submission is missing its CRM lead.")
        contact = db.get(Contact, lead.contact_id)
        property_record = db.get(Property, lead.property_id)
        if contact is None or property_record is None:
            raise RuntimeError("Address-capture lead is missing its contact or property.")
        if existing.completion_status == ADDRESS_ONLY_INTAKE_STATUS:
            property_record = resolve_address_capture_property(db, organization, payload)
            lead.property_id = property_record.id
            lead.desired_timeline = payload.desired_timeline or lead.desired_timeline
            refreshed_raw_payload = address_capture_raw_payload(payload)
            # During a rolling deploy, an older Step 1 may already have saved a
            # timeline. A retry from the new address-only client preserves that
            # original submission evidence without copying any later staff edit.
            if payload.desired_timeline is None:
                refreshed_raw_payload["desired_timeline"] = existing.raw_payload.get(
                    "desired_timeline"
                )
            existing.raw_payload = refreshed_raw_payload
            existing.landing_page = existing.landing_page or payload.attribution.landing_page
            existing.referrer = existing.referrer or payload.attribution.referrer
            existing.fbclid_captured_at = (
                existing.fbclid_captured_at or payload.attribution.fbclid_captured_at
            )
        ensure_address_lead_conversion(
            db,
            organization=organization,
            lead=lead,
            intake_attempt_id=payload.intake_attempt_id,
            attribution=attribution,
            meta_browser_event=payload.meta_browser_event,
            ip_address=ip_address,
            user_agent=user_agent,
            session_id=payload.conversion_session_id,
            experiment_key=payload.experiment_key,
            experiment_variant=payload.experiment_variant,
            device_category=payload.device_category,
        )
        db.commit()
        return WebsiteSellerAddressCaptureResponse(
            lead_id=lead.id,
            contact_id=contact.id,
            property_id=property_record.id,
            completion_status=existing.completion_status,
            created=False,
        )

    property_record = resolve_address_capture_property(db, organization, payload)
    contact = Contact(
        organization_id=organization.id,
        legal_name=ADDRESS_ONLY_CONTACT_NAME,
        preferred_name=None,
        contact_type="seller",
        assigned_user_id=None,
    )
    db.add(contact)
    db.flush()
    lead = Lead(
        organization_id=organization.id,
        contact_id=contact.id,
        property_id=property_record.id,
        assigned_user_id=None,
        source=attribution.utm_source or "website",
        asset_class="house",
        qualification_context={
            "website_intake_status": ADDRESS_ONLY_INTAKE_STATUS,
            "contact_details_status": "missing",
            "prospecting_status": "skip_trace_needed",
        },
        stage_key="new",
        lead_temperature="cold",
        motivation=None,
        desired_timeline=payload.desired_timeline,
        property_condition=None,
        occupancy_status=None,
        asking_price=None,
        mortgage_balance=None,
        appointment_status=None,
        next_follow_up_at=None,
    )
    db.add(lead)
    db.flush()
    submission = LeadFormSubmission(
        organization_id=organization.id,
        lead_id=lead.id,
        intake_attempt_id=payload.intake_attempt_id,
        completion_status=ADDRESS_ONLY_INTAKE_STATUS,
        completed_at=None,
        landing_page=payload.attribution.landing_page,
        referrer=payload.attribution.referrer,
        fbclid_captured_at=payload.attribution.fbclid_captured_at,
        ip_address=ip_address,
        user_agent=user_agent,
        raw_payload=address_capture_raw_payload(payload),
        enrichment_token_hash=None,
        enrichment_expires_at=None,
    )
    db.add(submission)
    db.add_all(
        [
            create_attribution_touch(
                organization.id,
                lead.id,
                "first_touch",
                payload,
                attribution=attribution,
            ),
            create_attribution_touch(
                organization.id,
                lead.id,
                "lead_creation",
                payload,
                attribution=attribution,
            ),
        ]
    )
    ensure_address_lead_conversion(
        db,
        organization=organization,
        lead=lead,
        intake_attempt_id=payload.intake_attempt_id,
        attribution=attribution,
        meta_browser_event=payload.meta_browser_event,
        ip_address=ip_address,
        user_agent=user_agent,
        session_id=payload.conversion_session_id,
        experiment_key=payload.experiment_key,
        experiment_variant=payload.experiment_variant,
        device_category=payload.device_category,
    )
    db.add(
        ActivityEvent(
            organization_id=organization.id,
            actor_user_id=None,
            entity_type="lead",
            entity_id=lead.id,
            event_type="lead.public_address_captured",
            summary=(
                "Website property address saved before contact details were completed; "
                "skip trace is needed."
            ),
        )
    )
    db.add(
        AuditEvent(
            organization_id=organization.id,
            actor_user_id=None,
            actor_type="public",
            action="lead.public_address_capture",
            entity_type="lead",
            entity_id=lead.id,
            previous_value=None,
            new_value={
                "source": lead.source,
                "stage_key": lead.stage_key,
                "lead_temperature": lead.lead_temperature,
                "website_intake_status": ADDRESS_ONLY_INTAKE_STATUS,
                "intake_attempt_id": str(payload.intake_attempt_id),
            },
            reason="Property address entered on Step 1 of the website form",
        )
    )
    try:
        db.flush()
        queue_website_stage_lead_alerts(
            db,
            lead=lead,
            submission=submission,
            stage=1,
        )
        db.commit()
    except IntegrityError:
        db.rollback()
        concurrent = find_intake_attempt_submission(
            db,
            organization_id=organization.id,
            intake_attempt_id=payload.intake_attempt_id,
        )
        if concurrent is None:
            raise
        concurrent_lead = db.get(Lead, concurrent.lead_id)
        if concurrent_lead is None:
            raise RuntimeError("Concurrent address capture is missing its lead.") from None
        ensure_address_lead_conversion(
            db,
            organization=organization,
            lead=concurrent_lead,
            intake_attempt_id=payload.intake_attempt_id,
            attribution=attribution,
            meta_browser_event=payload.meta_browser_event,
            ip_address=ip_address,
            user_agent=user_agent,
            session_id=payload.conversion_session_id,
            experiment_key=payload.experiment_key,
            experiment_variant=payload.experiment_variant,
            device_category=payload.device_category,
        )
        db.commit()
        return WebsiteSellerAddressCaptureResponse(
            lead_id=concurrent_lead.id,
            contact_id=concurrent_lead.contact_id,
            property_id=concurrent_lead.property_id,
            completion_status=concurrent.completion_status,
            created=False,
        )
    return WebsiteSellerAddressCaptureResponse(
        lead_id=lead.id,
        contact_id=contact.id,
        property_id=property_record.id,
        completion_status=ADDRESS_ONLY_INTAKE_STATUS,
        created=True,
    )


def create_public_seller_lead(
    db: Session,
    payload: SellerIntakeCreate,
    *,
    ip_address: str | None,
    user_agent: str | None,
    intake_source: str = "seller_website",
    contact_consent_wording_version: str | None = None,
    contact_consent_wording: str | None = None,
    contact_consent_channels: frozenset[str] | None = None,
    sms_consent_wording_version: str | None = None,
    sms_consent_wording: str | None = None,
    provider_record_id: str | None = None,
    notification_source_label: str = "public website",
) -> SellerIntakeResponse:
    if (contact_consent_wording_version is None) != (contact_consent_wording is None):
        raise ValueError("Contact-consent wording and version must be provided together.")
    if (sms_consent_wording_version is None) != (sms_consent_wording is None):
        raise ValueError("SMS-consent wording and version must be provided together.")
    if contact_consent_channels is not None and not contact_consent_channels.issubset(
        {"phone", "email"}
    ):
        raise ValueError("Contact-consent channels may only contain phone or email.")
    resolved_contact_consent_version = (
        contact_consent_wording_version
        if contact_consent_wording_version is not None
        else payload.consent_wording_version
    )
    resolved_contact_consent_wording = (
        contact_consent_wording
        if contact_consent_wording is not None
        else CONTACT_CONSENT_WORDINGS[payload.consent_wording_version]
    )
    resolved_sms_consent_version = (
        sms_consent_wording_version
        if sms_consent_wording_version is not None
        else payload.sms_consent_wording_version
    )
    resolved_sms_consent_wording = (
        sms_consent_wording
        if sms_consent_wording is not None
        else SMS_CONSENT_WORDINGS[payload.sms_consent_wording_version]
    )
    submitted_at = datetime.now(UTC)
    enrichment_token = secrets.token_urlsafe(32)
    enrichment_expires_at = submitted_at + ENRICHMENT_TOKEN_LIFETIME
    organization = get_default_organization(db)
    website_stage_flow = (
        intake_source == "seller_website" and payload.intake_attempt_id is not None
    )
    website_funnel_event = (
        website_stage_flow and payload.meta_browser_event is not None
    )
    attribution = (
        resolve_website_attribution(payload.attribution)
        if intake_source == "seller_website"
        else payload.attribution
    )
    if intake_source == "seller_website" and payload.intake_attempt_id is not None:
        lock_intake_attempt(db, payload.intake_attempt_id)
    attempt_submission = (
        find_intake_attempt_submission(
            db,
            organization_id=organization.id,
            intake_attempt_id=payload.intake_attempt_id,
            for_update=True,
        )
        if intake_source == "seller_website" and payload.intake_attempt_id is not None
        else None
    )
    if (
        attempt_submission is not None
        and attempt_submission.completion_status == COMPLETED_INTAKE_STATUS
    ):
        completed_lead = db.get(Lead, attempt_submission.lead_id)
        if completed_lead is None:
            raise RuntimeError("Completed intake submission is missing its CRM lead.")
        completed_matched_existing_lead = bool(
            (attempt_submission.raw_payload or {}).get("_matched_existing_lead")
        )
        meta_pixel_event_name: Literal["Lead", "Contact"] | None = None
        if website_funnel_event:
            assert payload.intake_attempt_id is not None
            assert payload.meta_browser_event is not None
            ensure_address_lead_conversion(
                db,
                organization=organization,
                lead=completed_lead,
                intake_attempt_id=payload.intake_attempt_id,
                attribution=attribution,
                meta_browser_event=address_lead_meta_event(
                    payload.intake_attempt_id,
                    payload.meta_browser_event,
                ),
                ip_address=ip_address,
                user_agent=user_agent,
                session_id=payload.conversion_session_id,
                experiment_key=payload.experiment_key,
                experiment_variant=payload.experiment_variant,
                device_category=payload.device_category,
            )
        if payload.meta_browser_event is not None:
            meta_pixel_event_name = ensure_contact_conversion(
                db,
                organization=organization,
                lead=completed_lead,
                attribution=attribution,
                meta_browser_event=payload.meta_browser_event,
                event_name="Contact" if website_funnel_event else "Lead",
                email=str(payload.email) if payload.email else None,
                full_name=payload.name,
                ip_address=ip_address,
                user_agent=user_agent,
                session_id=payload.conversion_session_id,
                experiment_key=payload.experiment_key,
                experiment_variant=payload.experiment_variant,
                device_category=payload.device_category,
                occurred_at=submitted_at,
                event_metadata={
                    "matched_existing_lead": completed_matched_existing_lead,
                    "completed_intake_retry_repair": True,
                },
                allow_legacy_event_name=True,
            )
        return completed_intake_retry_response(
            db,
            attempt_submission,
            enrichment_token=enrichment_token,
            enrichment_expires_at=enrichment_expires_at,
            consent_wording_version=resolved_contact_consent_version,
            meta_pixel_event_name=meta_pixel_event_name,
            matched_existing_lead=completed_matched_existing_lead,
        )
    resolution = resolve_full_intake_records(
        db,
        organization,
        payload,
        partial_submission=attempt_submission,
    )
    contact = resolution.contact
    property_record = resolution.property_record
    lead = resolution.lead
    matched_existing_lead = resolution.matched_existing_lead
    promoted_address_capture = resolution.promoted_address_capture
    if intake_source == "seller_website" and not matched_existing_lead:
        lead.source = attribution.utm_source or lead.source
    ensure_contact_methods(db, organization, contact, payload)
    apply_public_intake_context(lead, property_record, payload)
    ensure_primary_conversation(db, lead)
    event_namespace = "public" if intake_source == "seller_website" else intake_source
    if not matched_existing_lead:
        enqueue_lead_created_ai_work(db, lead, source=intake_source)
    enqueue_property_research(
        db,
        property_record,
        source_lead_id=lead.id,
        trigger_source=intake_source,
    )
    ensure_inbound_case(
        db,
        organization_id=organization.id,
        lead=lead,
        submitted_at=submitted_at,
        sla_minutes=get_settings().speed_to_lead_due_minutes,
    )
    ensure_speed_to_lead_task(db, lead, contact)

    requested_contact_channels = (
        contact_consent_channels
        if contact_consent_channels is not None
        else frozenset({"phone", "email"})
    )
    contact_channels = []
    if payload.phone and "phone" in requested_contact_channels:
        contact_channels.append("phone")
    if payload.email and "email" in requested_contact_channels:
        contact_channels.append("email")
    for channel in contact_channels:
        db.add(
            ConsentRecord(
                organization_id=organization.id,
                contact_id=contact.id,
                channel=channel,
                status="granted",
                source=intake_source,
                wording_version=resolved_contact_consent_version,
                wording=resolved_contact_consent_wording,
                normalized_address=(format_e164(payload.phone) if channel == "phone" else None),
                captured_ip=ip_address,
                user_agent=user_agent,
            )
        )
    if payload.sms_consent:
        sms_recipient = format_e164(payload.phone)
        db.add(
            ConsentRecord(
                organization_id=organization.id,
                contact_id=contact.id,
                channel="sms",
                status="granted",
                source=intake_source,
                wording_version=resolved_sms_consent_version,
                wording=resolved_sms_consent_wording,
                normalized_address=sms_recipient,
                captured_ip=ip_address,
                user_agent=user_agent,
            )
        )
    submission_payload = {
        **payload.model_dump(mode="json"),
        "_intake_source": intake_source,
        "_provider_record_id": provider_record_id,
        "_matched_existing_lead": matched_existing_lead,
        "_promoted_address_capture": promoted_address_capture,
        **(
            {"_staff_alert_flow_version": WEBSITE_STAGE_ALERT_FLOW_VERSION}
            if website_stage_flow
            else {}
        ),
    }
    if resolution.partial_submission is not None:
        submission = resolution.partial_submission
        submission.lead_id = lead.id
        submission.completion_status = COMPLETED_INTAKE_STATUS
        submission.completed_at = submitted_at
        submission.landing_page = payload.attribution.landing_page
        submission.referrer = payload.attribution.referrer
        submission.fbclid_captured_at = payload.attribution.fbclid_captured_at
        submission.ip_address = ip_address
        submission.user_agent = user_agent
        submission.raw_payload = submission_payload
        submission.enrichment_token_hash = hash_enrichment_token(enrichment_token)
        submission.enrichment_expires_at = enrichment_expires_at
    else:
        submission = LeadFormSubmission(
            organization_id=organization.id,
            lead_id=lead.id,
            intake_attempt_id=(
                payload.intake_attempt_id if intake_source == "seller_website" else None
            ),
            completion_status=COMPLETED_INTAKE_STATUS,
            completed_at=submitted_at,
            landing_page=payload.attribution.landing_page,
            referrer=payload.attribution.referrer,
            fbclid_captured_at=payload.attribution.fbclid_captured_at,
            ip_address=ip_address,
            user_agent=user_agent,
            raw_payload=submission_payload,
            enrichment_token_hash=hash_enrichment_token(enrichment_token),
            enrichment_expires_at=enrichment_expires_at,
        )
        db.add(submission)
    db.flush()
    if website_stage_flow:
        # Re-evaluate Stage 1 at contact completion so a newly eligible employee
        # still receives both ordered stage alerts. The durable source key makes
        # this a no-op for recipients who already received or queued Stage 1.
        queue_website_stage_lead_alerts(
            db,
            lead=lead,
            submission=submission,
            stage=1,
        )
        queue_website_stage_lead_alerts(
            db,
            lead=lead,
            submission=submission,
            stage=2,
        )
    elif intake_source == "seller_website" and not matched_existing_lead:
        queue_staff_lead_alerts_for_lead(
            db,
            lead=lead,
            source_type="website_form",
            source_event_id=submission.id,
            source_label="Website",
            source_entity_type="lead_form_submission",
        )
    if not promoted_address_capture and not matched_existing_lead:
        db.add_all(
            [
                create_attribution_touch(
                    organization.id,
                    lead.id,
                    "first_touch",
                    payload,
                    attribution=attribution,
                ),
                create_attribution_touch(
                    organization.id,
                    lead.id,
                    "lead_creation",
                    payload,
                    attribution=attribution,
                ),
            ]
        )
    if website_funnel_event:
        assert payload.intake_attempt_id is not None
        assert payload.meta_browser_event is not None
        ensure_address_lead_conversion(
            db,
            organization=organization,
            lead=lead,
            intake_attempt_id=payload.intake_attempt_id,
            attribution=attribution,
            meta_browser_event=address_lead_meta_event(
                payload.intake_attempt_id,
                payload.meta_browser_event,
            ),
            ip_address=ip_address,
            user_agent=user_agent,
            session_id=payload.conversion_session_id,
            experiment_key=payload.experiment_key,
            experiment_variant=payload.experiment_variant,
            device_category=payload.device_category,
        )
    conversion_metadata: dict[str, object] = {
        "matched_existing_lead": matched_existing_lead,
        **({"promoted_address_capture": True} if promoted_address_capture else {}),
        **(
            {
                "funnel_version": "website_two_step_v1",
                "intake_attempt_id": str(payload.intake_attempt_id),
            }
            if website_funnel_event
            else {}
        ),
    }
    meta_pixel_event_name = None
    if payload.meta_browser_event is not None:
        meta_pixel_event_name = ensure_contact_conversion(
            db,
            organization=organization,
            lead=lead,
            attribution=attribution,
            meta_browser_event=payload.meta_browser_event,
            event_name="Contact" if website_funnel_event else "Lead",
            email=str(payload.email) if payload.email else None,
            full_name=payload.name,
            ip_address=ip_address,
            user_agent=user_agent,
            session_id=payload.conversion_session_id,
            experiment_key=payload.experiment_key,
            experiment_variant=payload.experiment_variant,
            device_category=payload.device_category,
            occurred_at=submitted_at,
            event_metadata=conversion_metadata,
        )
    else:
        record_conversion_event(
            db,
            organization_id=organization.id,
            lead_id=lead.id,
            event_type="form_submit",
            attribution=attribution,
            ip_address=ip_address,
            user_agent=user_agent,
            session_id=payload.conversion_session_id,
            experiment_key=payload.experiment_key,
            experiment_variant=payload.experiment_variant,
            device_category=payload.device_category,
            metadata=conversion_metadata,
        )
    db.add(
        ActivityEvent(
            organization_id=organization.id,
            actor_user_id=None,
            entity_type="lead",
            entity_id=lead.id,
            event_type=(
                f"lead.{event_namespace}_duplicate_submitted"
                if matched_existing_lead
                else f"lead.{event_namespace}_form_submitted"
            ),
            summary=(
                f"Duplicate {notification_source_label} seller form matched {contact.legal_name}."
                if matched_existing_lead
                else f"{notification_source_label.title()} seller form submitted by "
                f"{contact.legal_name}."
            ),
        )
    )
    db.add(
        AuditEvent(
            organization_id=organization.id,
            actor_user_id=None,
            actor_type="provider" if provider_record_id else "public",
            action=(
                f"lead.{event_namespace}_duplicate"
                if matched_existing_lead
                else f"lead.{event_namespace}_create"
            ),
            entity_type="lead",
            entity_id=lead.id,
            previous_value=None,
            new_value={
                "source": lead.source,
                "stage_key": lead.stage_key,
                "consent_wording_version": resolved_contact_consent_version,
                "sms_consent": payload.sms_consent,
                "sms_consent_wording_version": (
                    resolved_sms_consent_version if payload.sms_consent else None
                ),
                "matched_existing_lead": matched_existing_lead,
                "promoted_address_capture": promoted_address_capture,
            },
            reason=f"Seller form submission from {notification_source_label}",
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
            title=(
                f"New {notification_source_label} seller lead"
                if not matched_existing_lead
                else f"{notification_source_label.title()} lead matched an existing seller"
            ),
            body=(
                f"{contact.legal_name} submitted property information from "
                f"the {notification_source_label}."
            ),
            entity_type="lead",
            entity_id=lead.id,
            action_url=f"/os/leads/{lead.id}",
            dedupe_key=(
                f"{intake_source}-lead:{provider_record_id}"
                if provider_record_id
                else f"new-public-lead:{lead.id}"
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
        consent_wording_version=resolved_contact_consent_version,
        enrichment_token=enrichment_token,
        enrichment_expires_at=enrichment_expires_at,
        message=(
            "Thanks. We received your updated property information."
            if matched_existing_lead
            else "Thanks. Your property inquiry was received."
        ),
        meta_pixel_event_name=meta_pixel_event_name,
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


def find_intake_attempt_submission(
    db: Session,
    *,
    organization_id: uuid.UUID,
    intake_attempt_id: uuid.UUID,
    for_update: bool = False,
) -> LeadFormSubmission | None:
    statement = select(LeadFormSubmission).where(
        LeadFormSubmission.organization_id == organization_id,
        LeadFormSubmission.intake_attempt_id == intake_attempt_id,
    )
    if for_update:
        statement = statement.with_for_update()
    return db.scalar(statement)


def lock_intake_attempt(db: Session, intake_attempt_id: uuid.UUID) -> None:
    """Serialize Step 1 and Step 2 for the same browser journey on PostgreSQL."""
    if db.get_bind().dialect.name != "postgresql":
        return
    advisory_key = intake_attempt_id.int & ((1 << 63) - 1)
    db.execute(select(func.pg_advisory_xact_lock(advisory_key)))


def resolve_address_capture_property(
    db: Session,
    organization: Organization,
    payload: WebsiteSellerAddressCaptureCreate,
) -> Property:
    property_record, normalized_address_key, _ = find_property_by_identity(
        db,
        organization_id=organization.id,
        street_address=payload.property_address,
        city=payload.property_city,
        state=payload.property_state,
        postal_code=payload.property_postal_code,
        parcel_id=None,
        county=None,
    )
    if property_record is not None:
        return property_record
    property_record = Property(
        organization_id=organization.id,
        street_address=payload.property_address.strip(),
        city=payload.property_city.strip(),
        state=payload.property_state.strip().upper(),
        postal_code=payload.property_postal_code.strip(),
        county=None,
        property_type=None,
        parcel_id=None,
        normalized_parcel_key=None,
        normalized_address_key=normalized_address_key,
    )
    db.add(property_record)
    db.flush()
    return property_record


def address_capture_raw_payload(payload: WebsiteSellerAddressCaptureCreate) -> dict[str, object]:
    return {
        **payload.model_dump(mode="json"),
        "_intake_source": "seller_website",
        "_intake_status": ADDRESS_ONLY_INTAKE_STATUS,
        "_matched_existing_lead": None,
        "_staff_alert_flow_version": WEBSITE_STAGE_ALERT_FLOW_VERSION,
    }


def resolve_full_intake_records(
    db: Session,
    organization: Organization,
    payload: SellerIntakeCreate,
    *,
    partial_submission: LeadFormSubmission | None,
) -> FullIntakeResolution:
    if (
        partial_submission is not None
        and partial_submission.completion_status == ADDRESS_ONLY_INTAKE_STATUS
    ):
        lead = db.get(Lead, partial_submission.lead_id)
        if lead is None:
            raise RuntimeError("Address-capture submission is missing its CRM lead.")
        placeholder_contact = db.get(Contact, lead.contact_id)
        if placeholder_contact is None:
            raise RuntimeError("Address-capture lead is missing its contact.")
        property_record = find_matching_property(db, organization, payload)
        if property_record is None:
            property_record = create_property(db, organization, payload)
        lead.property_id = property_record.id

        duplicate_match = find_duplicate_match(db, organization, payload)
        if duplicate_match.lead is not None and duplicate_match.lead.id != lead.id:
            surviving_lead = duplicate_match.lead
            surviving_contact = duplicate_match.contact
            surviving_property = duplicate_match.property_record
            if surviving_contact is None or surviving_property is None:
                raise RuntimeError("Matched active lead is missing its contact or property.")
            discard_placeholder = can_discard_address_only_placeholder(
                db,
                lead=lead,
                contact=placeholder_contact,
                submission=partial_submission,
            )
            reassign_address_capture_attempt(
                db,
                organization=organization,
                submission=partial_submission,
                previous_lead=lead,
                surviving_lead=surviving_lead,
            )
            if discard_placeholder:
                discard_address_only_placeholder(
                    db,
                    lead=lead,
                    contact=placeholder_contact,
                    surviving_lead=surviving_lead,
                )
            return FullIntakeResolution(
                contact=surviving_contact,
                property_record=surviving_property,
                lead=surviving_lead,
                partial_submission=partial_submission,
                matched_existing_lead=True,
                promoted_address_capture=True,
            )

        matched_contact = find_matching_contact(db, organization, payload)
        if matched_contact is not None and matched_contact.id != placeholder_contact.id:
            contact = matched_contact
            lead.contact_id = contact.id
            db.flush()
            db.delete(placeholder_contact)
        else:
            contact = placeholder_contact
            contact.legal_name = payload.name

        lead.source = payload.attribution.utm_source or "website"
        lead.lead_temperature = None
        context = dict(lead.qualification_context or {})
        context["website_intake_status"] = COMPLETED_INTAKE_STATUS
        context["contact_details_status"] = "provided"
        context.pop("prospecting_status", None)
        lead.qualification_context = context
        return FullIntakeResolution(
            contact=contact,
            property_record=property_record,
            lead=lead,
            partial_submission=partial_submission,
            matched_existing_lead=False,
            promoted_address_capture=True,
        )

    duplicate_match = find_duplicate_match(db, organization, payload)
    contact = duplicate_match.contact or create_contact(db, organization, payload)
    property_record = duplicate_match.property_record or create_property(db, organization, payload)
    lead = duplicate_match.lead or create_lead(db, organization, contact, property_record, payload)
    return FullIntakeResolution(
        contact=contact,
        property_record=property_record,
        lead=lead,
        partial_submission=None,
        matched_existing_lead=duplicate_match.lead is not None,
        promoted_address_capture=False,
    )


def reassign_address_capture_attempt(
    db: Session,
    *,
    organization: Organization,
    submission: LeadFormSubmission,
    previous_lead: Lead,
    surviving_lead: Lead,
) -> None:
    """Keep an address-stage attempt intact when its person/property already has a lead."""
    intake_attempt_id = submission.intake_attempt_id
    if intake_attempt_id is None:
        raise RuntimeError("Address-capture submission is missing its intake attempt identity.")
    event_id = address_lead_event_id(intake_attempt_id)
    conversion_event = find_conversion_event_by_meta_id(
        db,
        organization_id=organization.id,
        lead_id=previous_lead.id,
        event_type="address_capture",
        event_id=event_id,
    )
    export = db.scalar(
        select(OfflineConversionExport).where(
            OfflineConversionExport.organization_id == organization.id,
            OfflineConversionExport.platform == "meta",
            OfflineConversionExport.event_key == event_id,
        )
    )
    if export is not None:
        if export.event_name != "Lead":
            raise RuntimeError("Address-lead conversion identity is already in use.")
        if export.lead_id not in {previous_lead.id, surviving_lead.id}:
            raise RuntimeError("Address-lead conversion identity is already in use.")
        if conversion_event is None and export.conversion_event_id is not None:
            conversion_event = db.get(ConversionEvent, export.conversion_event_id)
        export.lead_id = surviving_lead.id
        if can_enrich_meta_web_conversion_identifiers(export):
            snapshot = dict(export.payload_snapshot)
            snapshot["external_id_hash"] = sha256(f"{organization.id}:{surviving_lead.id}")
            export.payload_snapshot = snapshot
            export.payload_hash = payload_hash(snapshot)
    if conversion_event is not None:
        browser_event = (conversion_event.event_metadata or {}).get("meta_browser_event")
        if (
            conversion_event.organization_id != organization.id
            or conversion_event.event_type != "address_capture"
            or not isinstance(browser_event, dict)
            or browser_event.get("event_id") != event_id
            or conversion_event.lead_id not in {previous_lead.id, surviving_lead.id}
        ):
            raise RuntimeError("Address-lead conversion event belongs to another lead.")
        conversion_event.lead_id = surviving_lead.id
    submission.lead_id = surviving_lead.id
    db.flush()


def can_discard_address_only_placeholder(
    db: Session,
    *,
    lead: Lead,
    contact: Contact,
    submission: LeadFormSubmission,
) -> bool:
    """Only delete the temporary records when they still match the Step 1 contract."""
    if (
        lead.contact_id != contact.id
        or contact.legal_name != ADDRESS_ONLY_CONTACT_NAME
        or contact.preferred_name is not None
        or contact.contact_type != "seller"
        or contact.assigned_user_id is not None
        or lead.assigned_user_id is not None
        or lead.stage_key != "new"
        or lead.lead_temperature != "cold"
        or lead.asset_class != "house"
        or lead.archived_at is not None
        or lead.close_out_disposition is not None
        or lead.close_out_reason is not None
        or lead.closed_out_at is not None
        or lead.closed_out_by_user_id is not None
        or lead.motivation is not None
        or lead.property_condition is not None
        or lead.occupancy_status is not None
        or lead.asking_price is not None
        or lead.mortgage_balance is not None
        or lead.appointment_status is not None
        or lead.next_follow_up_at is not None
        or (lead.qualification_context or {})
        != {
            "website_intake_status": ADDRESS_ONLY_INTAKE_STATUS,
            "contact_details_status": "missing",
            "prospecting_status": "skip_trace_needed",
        }
    ):
        return False
    submissions = db.scalars(
        select(LeadFormSubmission).where(LeadFormSubmission.lead_id == lead.id)
    ).all()
    if len(submissions) != 1 or submissions[0].id != submission.id:
        return False
    if submission.completion_status != ADDRESS_ONLY_INTAKE_STATUS:
        return False
    if submission.intake_attempt_id is None:
        return False
    if lead.desired_timeline != submission.raw_payload.get("desired_timeline"):
        return False
    expected_event_id = address_lead_event_id(submission.intake_attempt_id)
    conversion_events = db.scalars(
        select(ConversionEvent).where(ConversionEvent.lead_id == lead.id)
    ).all()
    for event in conversion_events:
        browser_event = (event.event_metadata or {}).get("meta_browser_event")
        if (
            event.event_type != "address_capture"
            or not isinstance(browser_event, dict)
            or browser_event.get("event_id") != expected_event_id
        ):
            return False
    exports = db.scalars(
        select(OfflineConversionExport).where(OfflineConversionExport.lead_id == lead.id)
    ).all()
    if any(
        export.event_name != "Lead" or export.event_key != expected_event_id for export in exports
    ):
        return False
    touches = db.scalars(select(AttributionTouch).where(AttributionTouch.lead_id == lead.id)).all()
    if any(touch.touch_type not in {"first_touch", "lead_creation"} for touch in touches):
        return False
    activities = db.scalars(
        select(ActivityEvent).where(
            ActivityEvent.entity_type == "lead",
            ActivityEvent.entity_id == lead.id,
        )
    ).all()
    if any(
        event.event_type
        not in {"lead.public_address_captured", "lead.staff_sms_alert_not_queued"}
        for event in activities
    ):
        return False
    audits = db.scalars(
        select(AuditEvent).where(
            AuditEvent.entity_type == "lead",
            AuditEvent.entity_id == lead.id,
        )
    ).all()
    if any(event.action != "lead.public_address_capture" for event in audits):
        return False
    staff_alerts = db.scalars(
        select(StaffLeadAlert).where(StaffLeadAlert.lead_id == lead.id)
    ).all()
    if any(
        alert.source_type != WEBSITE_STAGE_1_ALERT_SOURCE_TYPE
        or alert.source_event_id != submission.id
        or alert.meta_lead_event_id is not None
        or alert.conversation_id is not None
        for alert in staff_alerts
    ):
        return False
    if has_foreign_key_references(
        db,
        referenced_table="leads",
        record_id=lead.id,
        ignored_tables={
            "attribution_touches",
            "conversion_events",
            "lead_form_submissions",
            "offline_conversion_exports",
            "staff_lead_alerts",
        },
    ):
        return False
    contact_leads = db.scalars(select(Lead).where(Lead.contact_id == contact.id)).all()
    if len(contact_leads) != 1 or contact_leads[0].id != lead.id:
        return False
    return not has_foreign_key_references(
        db,
        referenced_table="contacts",
        record_id=contact.id,
        ignored_tables={"leads"},
    )


def has_foreign_key_references(
    db: Session,
    *,
    referenced_table: str,
    record_id: uuid.UUID,
    ignored_tables: set[str],
) -> bool:
    for table in Base.metadata.tables.values():
        if table.name in ignored_tables:
            continue
        for foreign_key in table.foreign_keys:
            if foreign_key.column.table.name != referenced_table:
                continue
            if (
                db.scalar(
                    select(foreign_key.parent).where(foreign_key.parent == record_id).limit(1)
                )
                is not None
            ):
                return True
    return False


def discard_address_only_placeholder(
    db: Session,
    *,
    lead: Lead,
    contact: Contact,
    surviving_lead: Lead,
) -> None:
    for touch in db.scalars(select(AttributionTouch).where(AttributionTouch.lead_id == lead.id)):
        touch.lead_id = surviving_lead.id
    for alert in db.scalars(select(StaffLeadAlert).where(StaffLeadAlert.lead_id == lead.id)):
        alert.lead_id = surviving_lead.id
    for activity in db.scalars(
        select(ActivityEvent).where(
            ActivityEvent.entity_type == "lead",
            ActivityEvent.entity_id == lead.id,
        )
    ):
        activity.entity_id = surviving_lead.id
    for audit in db.scalars(
        select(AuditEvent).where(
            AuditEvent.entity_type == "lead",
            AuditEvent.entity_id == lead.id,
        )
    ):
        audit.entity_id = surviving_lead.id
    db.flush()
    db.delete(lead)
    db.flush()
    db.delete(contact)
    db.flush()


def completed_intake_retry_response(
    db: Session,
    submission: LeadFormSubmission,
    *,
    enrichment_token: str,
    enrichment_expires_at: datetime,
    consent_wording_version: str,
    meta_pixel_event_name: Literal["Lead", "Contact"] | None,
    matched_existing_lead: bool,
) -> SellerIntakeResponse:
    lead = db.get(Lead, submission.lead_id)
    if lead is None:
        raise RuntimeError("Completed intake submission is missing its CRM lead.")
    contact = db.get(Contact, lead.contact_id)
    property_record = db.get(Property, lead.property_id)
    if contact is None or property_record is None:
        raise RuntimeError("Completed intake lead is missing its contact or property.")
    submission.enrichment_token_hash = hash_enrichment_token(enrichment_token)
    submission.enrichment_expires_at = enrichment_expires_at
    db.commit()
    return SellerIntakeResponse(
        lead_id=lead.id,
        contact_id=contact.id,
        property_id=property_record.id,
        duplicate_status="already_completed",
        matched_existing_lead=matched_existing_lead,
        consent_wording_version=consent_wording_version,
        enrichment_token=enrichment_token,
        enrichment_expires_at=enrichment_expires_at,
        message=(
            "Thanks. We received your updated property information."
            if matched_existing_lead
            else "Thanks. Your property inquiry was received."
        ),
        meta_pixel_event_name=meta_pixel_event_name,
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
        asset_class = asset_class_for_property_type(
            payload.property_type or property_record.property_type,
            explicit_asset_class=payload.asset_class,
        )
        lead = db.scalar(
            select(Lead).where(
                Lead.organization_id == organization.id,
                Lead.archived_at.is_(None),
                Lead.contact_id == contact.id,
                Lead.property_id == property_record.id,
                Lead.asset_class == asset_class,
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
    property_record, _, _ = find_property_by_identity(
        db,
        organization_id=organization.id,
        street_address=payload.property_address,
        city=payload.property_city,
        state=payload.property_state,
        postal_code=payload.property_postal_code,
        parcel_id=payload.parcel_id,
        county=payload.property_county,
    )
    return property_record


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
    _, normalized_address_key, normalized_parcel_key = find_property_by_identity(
        db,
        organization_id=organization.id,
        street_address=payload.property_address,
        city=payload.property_city,
        state=payload.property_state,
        postal_code=payload.property_postal_code,
        parcel_id=payload.parcel_id,
        county=payload.property_county,
    )
    property_record = Property(
        organization_id=organization.id,
        street_address=payload.property_address,
        city=payload.property_city,
        state=payload.property_state.upper(),
        postal_code=payload.property_postal_code,
        county=payload.property_county,
        property_type=payload.property_type,
        parcel_id=payload.parcel_id,
        normalized_parcel_key=normalized_parcel_key,
        normalized_address_key=normalized_address_key,
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
        asset_class=asset_class_for_property_type(
            property_record.property_type,
            explicit_asset_class=payload.asset_class,
        ),
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
    if lead.asset_class == "land" and not property_record.property_type:
        property_record.property_type = "land"
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
    if not property_record.parcel_id and payload.parcel_id:
        property_record.parcel_id = payload.parcel_id
    if not property_record.county and payload.property_county:
        property_record.county = payload.property_county
    refresh_property_identity_keys(property_record)
    if payload.asset_class is not None or payload.property_type is not None:
        lead.asset_class = asset_class_for_property_type(
            payload.property_type or property_record.property_type,
            explicit_asset_class=payload.asset_class,
        )
        if lead.asset_class == "land" and not property_record.property_type:
            property_record.property_type = "land"

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
    payload: SellerIntakeCreate | WebsiteSellerAddressCaptureCreate,
    *,
    attribution: SellerIntakeAttribution | None = None,
) -> AttributionTouch:
    resolved_attribution = attribution or payload.attribution
    return AttributionTouch(
        organization_id=organization_id,
        lead_id=lead_id,
        touch_type=touch_type,
        source=resolved_attribution.utm_source,
        medium=resolved_attribution.utm_medium,
        campaign=resolved_attribution.utm_campaign,
        term=resolved_attribution.utm_term,
        content=resolved_attribution.utm_content,
        gclid=resolved_attribution.gclid,
        fbclid=resolved_attribution.fbclid,
        fbclid_captured_at=resolved_attribution.fbclid_captured_at,
        landing_page=resolved_attribution.landing_page,
        referrer=resolved_attribution.referrer,
    )


def normalize_email(value: str) -> str:
    return value.strip().lower()


def normalize_phone(value: str) -> str:
    return "".join(character for character in value if character.isdigit())


def normalize_address_key(payload: SellerIntakeCreate) -> str | None:
    return normalized_address_key_or_none(
        street_address=payload.property_address,
        city=payload.property_city,
        state=payload.property_state,
        postal_code=payload.property_postal_code,
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
