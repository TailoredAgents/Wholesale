import re
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from pydantic import ValidationError
from sqlalchemy import and_, false, or_, select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.integrations.communications import (
    CommunicationProvider,
    OutboundMessageRequest,
    SimulatedCommunicationProvider,
)
from app.integrations.rentcast_client import RentCastClientError
from app.integrations.twilio_messaging import (
    TwilioMessagingError,
    get_twilio_messaging_provider,
)
from app.models.foundation import (
    ActivityEvent,
    Contact,
    Lead,
    MetaLeadEvent,
    Property,
    StaffLeadAlert,
    User,
)
from app.schemas.public_intake import SellerIntakeCreate
from app.schemas.zapier import ZapierFacebookLeadCreate
from app.services.communication_compliance import format_e164
from app.services.property_validation import (
    PropertyRecordClient,
    normalize_postal_code,
    validate_property_with_provider,
)
from app.services.public_intake import create_public_seller_lead, get_default_organization

META_CONTACT_CONSENT_VERSION = "meta-lead-form-contact-v1"
META_CONTACT_CONSENT_WORDING = (
    "Seller submitted a Meta instant form requesting contact about a property offer."
)

FIELD_ALIASES = {
    "name": ("full_name", "name", "your_name"),
    "first_name": ("first_name",),
    "last_name": ("last_name",),
    "email": ("email", "email_address"),
    "phone": ("phone_number", "phone", "mobile_phone", "mobile_number"),
    "property_address": (
        "property_address",
        "street_address",
        "address",
        "property_street_address",
    ),
    "property_city": ("property_city", "city"),
    "property_state": ("property_state", "state", "state_code"),
    "property_postal_code": (
        "property_zip_code",
        "property_postal_code",
        "zip_code",
        "postal_code",
        "post_code",
    ),
    "property_type": ("property_type", "home_type"),
    "reason_for_selling": ("reason_for_selling", "selling_reason", "motivation"),
    "desired_timeline": ("desired_timeline", "selling_timeline", "timeline"),
    "property_condition": ("property_condition", "condition"),
    "occupancy_status": ("occupancy_status", "occupancy"),
    "asking_price": ("asking_price", "desired_price"),
    "mortgage_balance": ("mortgage_balance",),
    "comments": ("comments", "additional_details", "notes"),
}


class MetaLeadNeedsReview(ValueError):
    pass


def receive_zapier_facebook_lead(
    db: Session,
    payload: ZapierFacebookLeadCreate,
    settings: Settings,
) -> int:
    organization = get_default_organization(db)
    if payload.page_id != settings.zapier_facebook_page_id:
        raise ValueError("Zapier Facebook lead does not belong to the configured Page.")
    existing = db.scalar(
        select(MetaLeadEvent.id).where(
            MetaLeadEvent.organization_id == organization.id,
            MetaLeadEvent.provider_lead_id == payload.provider_lead_id,
        )
    )
    if existing is not None:
        return 0
    lead_payload = payload.normalized_lead_payload()
    db.add(
        MetaLeadEvent(
            organization_id=organization.id,
            lead_id=None,
            provider_lead_id=payload.provider_lead_id,
            ingestion_method="zapier",
            page_id=payload.page_id,
            form_id=payload.form_id,
            ad_id=payload.ad_id,
            campaign_id=payload.campaign_id,
            status="pending",
            attempt_count=0,
            received_at=datetime.now(UTC),
            lead_created_at=parse_meta_datetime(payload.created_time),
            last_attempt_at=None,
            next_attempt_at=None,
            processed_at=None,
            webhook_payload=payload.raw_payload(),
            lead_payload=lead_payload,
            last_error=None,
        )
    )
    db.commit()
    return 1


def process_next_meta_lead_event(
    db: Session,
    settings: Settings,
) -> UUID | None:
    if not settings.zapier_facebook_leads_enabled:
        return None
    now = datetime.now(UTC)
    configured = settings.zapier_facebook_leads_configured
    event = db.scalar(
        select(MetaLeadEvent)
        .where(
            or_(
                MetaLeadEvent.status.in_({"pending", "retry"}),
                MetaLeadEvent.status == "blocked" if configured else false(),
                and_(
                    MetaLeadEvent.status == "processing",
                    MetaLeadEvent.last_attempt_at <= now - timedelta(minutes=5),
                ),
            ),
            or_(MetaLeadEvent.next_attempt_at.is_(None), MetaLeadEvent.next_attempt_at <= now),
        )
        .order_by(MetaLeadEvent.received_at, MetaLeadEvent.created_at)
        .with_for_update(skip_locked=True)
    )
    if event is None:
        return None
    event.attempt_count += 1
    event.last_attempt_at = now
    event.next_attempt_at = None
    if not configured:
        event.status = "blocked"
        event.last_error = (
            "Missing configuration: "
            + ", ".join(settings.zapier_facebook_leads_configuration_blockers)
        )
        db.commit()
        return event.id

    event.status = "processing"
    db.commit()
    try:
        lead_payload = event.lead_payload
        if not isinstance(lead_payload, dict):
            raise MetaLeadNeedsReview("Zapier event does not contain normalized lead data.")
        intake = meta_lead_to_intake(event, lead_payload)
        response = create_public_seller_lead(
            db,
            intake,
            ip_address=None,
            user_agent="Zapier Facebook Lead Ads",
            intake_source="facebook_lead_ads",
            contact_consent_wording_version=META_CONTACT_CONSENT_VERSION,
            contact_consent_wording=META_CONTACT_CONSENT_WORDING,
            provider_record_id=event.provider_lead_id,
            notification_source_label="Facebook lead form",
        )
    except (MetaLeadNeedsReview, ValidationError) as exc:
        refreshed = db.get(MetaLeadEvent, event.id)
        if refreshed is not None:
            refreshed.status = "needs_review"
            refreshed.last_error = str(exc)[:2000]
            refreshed.processed_at = datetime.now(UTC)
            db.commit()
        return event.id
    except Exception as exc:
        db.rollback()
        mark_meta_lead_failure(db, event.id, settings, str(exc))
        return event.id

    refreshed = db.get(MetaLeadEvent, event.id)
    if refreshed is None:
        raise RuntimeError("Meta lead event disappeared during processing.")
    refreshed.lead_id = response.lead_id
    refreshed.status = "processed"
    refreshed.processed_at = datetime.now(UTC)
    refreshed.last_error = None
    queue_staff_lead_alerts(db, refreshed)
    db.commit()
    return refreshed.id


def mark_meta_lead_failure(
    db: Session,
    event_id: UUID,
    settings: Settings,
    error: str,
) -> None:
    event = db.get(MetaLeadEvent, event_id)
    if event is None:
        return
    event.last_error = error[:2000]
    if event.attempt_count >= settings.facebook_lead_intake_max_attempts:
        event.status = "exhausted"
        event.next_attempt_at = None
    else:
        event.status = "retry"
        event.next_attempt_at = datetime.now(UTC) + timedelta(
            seconds=settings.facebook_lead_intake_retry_base_seconds
            * (2 ** max(0, event.attempt_count - 1))
        )
    db.commit()


def process_next_meta_address_enrichment(
    db: Session,
    settings: Settings,
    client: PropertyRecordClient | None = None,
) -> UUID | None:
    if not settings.zapier_facebook_leads_enabled:
        return None
    now = datetime.now(UTC)
    configured = not settings.facebook_address_enrichment_configuration_blockers
    event = db.scalar(
        select(MetaLeadEvent)
        .where(
            MetaLeadEvent.status == "processed",
            MetaLeadEvent.lead_id.is_not(None),
            or_(
                MetaLeadEvent.address_enrichment_status.in_({"pending", "retry"}),
                MetaLeadEvent.address_enrichment_status == "blocked" if configured else false(),
                and_(
                    MetaLeadEvent.address_enrichment_status == "processing",
                    MetaLeadEvent.address_enrichment_last_attempt_at
                    <= now - timedelta(minutes=5),
                ),
            ),
            or_(
                MetaLeadEvent.address_enrichment_next_attempt_at.is_(None),
                MetaLeadEvent.address_enrichment_next_attempt_at <= now,
            ),
        )
        .order_by(MetaLeadEvent.processed_at, MetaLeadEvent.created_at)
        .with_for_update(skip_locked=True)
    )
    if event is None:
        return None
    event.address_enrichment_attempt_count += 1
    event.address_enrichment_last_attempt_at = now
    event.address_enrichment_next_attempt_at = None
    if not configured:
        event.address_enrichment_status = "blocked"
        event.address_enrichment_last_error = (
            "Missing configuration: "
            + ", ".join(settings.facebook_address_enrichment_configuration_blockers)
        )
        db.commit()
        return event.id
    event.address_enrichment_status = "processing"
    event.address_enrichment_last_error = None
    db.commit()
    event_id = event.id

    lead = db.get(Lead, event.lead_id)
    property_record = db.get(Property, lead.property_id) if lead is not None else None
    if lead is None or property_record is None:
        return finish_meta_address_enrichment(
            db,
            event_id,
            status="needs_review",
            error="Facebook lead is missing its CRM lead or property record.",
        )
    if not usable_meta_property_address(property_record):
        return finish_meta_address_enrichment(
            db,
            event_id,
            status="skipped",
            error="Facebook form did not provide a usable street address and city.",
        )

    try:
        metadata = validate_property_with_provider(property_record, settings, client=client)
    except RentCastClientError as exc:
        db.rollback()
        return mark_meta_address_enrichment_failure(db, event_id, settings, str(exc))
    except ValueError as exc:
        db.rollback()
        event = db.get(MetaLeadEvent, event_id)
        if event is not None:
            event.address_enrichment_status = "blocked"
            event.address_enrichment_last_error = str(exc)[:2000]
            db.commit()
        return event_id

    postal_code = normalize_postal_code(property_record.postal_code)
    if property_record.address_validation_status == "provider_confirmed" and postal_code:
        status_value = "enriched"
        error = None
    else:
        status_value = "needs_review"
        issues = metadata.get("issues")
        issue_values = issues if isinstance(issues, list) else []
        error = "; ".join(str(item) for item in issue_values) or (
            "Provider validation did not return a confident address with a ZIP code."
        )
    db.add(
        ActivityEvent(
            organization_id=event.organization_id,
            actor_user_id=None,
            entity_type="lead",
            entity_id=lead.id,
            event_type=f"property.address_enrichment_{status_value}",
            summary=(
                "Facebook lead address was enriched from provider property data."
                if status_value == "enriched"
                else "Facebook lead address enrichment requires review."
            ),
        )
    )
    event.address_enrichment_status = status_value
    event.address_enrichment_last_error = error[:2000] if error else None
    event.address_enriched_at = datetime.now(UTC)
    db.commit()
    return event.id


def usable_meta_property_address(property_record: Property) -> bool:
    street_address = property_record.street_address.strip().lower()
    city = property_record.city.strip().lower()
    return bool(
        street_address
        and city
        and not street_address.startswith("address pending (meta ")
        and city != "unknown"
    )


def finish_meta_address_enrichment(
    db: Session,
    event_id: UUID,
    *,
    status: str,
    error: str,
) -> UUID:
    event = db.get(MetaLeadEvent, event_id)
    if event is not None:
        event.address_enrichment_status = status
        event.address_enrichment_last_error = error[:2000]
        event.address_enriched_at = datetime.now(UTC)
        db.commit()
    return event_id


def mark_meta_address_enrichment_failure(
    db: Session,
    event_id: UUID,
    settings: Settings,
    error: str,
) -> UUID:
    event = db.get(MetaLeadEvent, event_id)
    if event is None:
        return event_id
    event.address_enrichment_last_error = error[:2000]
    if (
        event.address_enrichment_attempt_count
        >= settings.facebook_address_enrichment_max_attempts
    ):
        event.address_enrichment_status = "exhausted"
        event.address_enrichment_next_attempt_at = None
    else:
        event.address_enrichment_status = "retry"
        event.address_enrichment_next_attempt_at = datetime.now(UTC) + timedelta(
            seconds=settings.facebook_address_enrichment_retry_base_seconds
            * (2 ** max(0, event.address_enrichment_attempt_count - 1))
        )
    db.commit()
    return event_id


def queue_staff_lead_alerts(db: Session, event: MetaLeadEvent) -> int:
    if event.lead_id is None:
        return 0
    lead = db.get(Lead, event.lead_id)
    if lead is None:
        return 0
    contact = db.get(Contact, lead.contact_id)
    property_record = db.get(Property, lead.property_id)
    recipients = db.scalars(
        select(User).where(
            User.organization_id == event.organization_id,
            User.is_active.is_(True),
            User.lead_alert_sms_enabled.is_(True),
            User.voice_forwarding_number.is_not(None),
        )
    ).all()
    created = 0
    for recipient in recipients:
        phone = format_e164(recipient.voice_forwarding_number or "")
        if phone is None:
            continue
        existing = db.scalar(
            select(StaffLeadAlert.id).where(
                StaffLeadAlert.meta_lead_event_id == event.id,
                StaffLeadAlert.recipient_user_id == recipient.id,
            )
        )
        if existing is not None:
            continue
        contact_name = contact.legal_name if contact else "New seller"
        market = property_record.city if property_record else "Georgia"
        db.add(
            StaffLeadAlert(
                organization_id=event.organization_id,
                meta_lead_event_id=event.id,
                lead_id=lead.id,
                recipient_user_id=recipient.id,
                recipient_phone=phone,
                message_body=(
                    f"New Facebook seller lead: {contact_name}, {market}. "
                    f"Open Stonegate: https://www.stonegatehb.com/os/leads/{lead.id}"
                ),
                status="pending",
                attempt_count=0,
                last_attempt_at=None,
                next_attempt_at=None,
                sent_at=None,
                delivered_at=None,
                provider=None,
                provider_message_id=None,
                provider_response=None,
                last_error=None,
            )
        )
        created += 1
    db.flush()
    return created


def process_next_staff_lead_alert(
    db: Session,
    settings: Settings,
    provider: CommunicationProvider | None = None,
) -> UUID | None:
    if settings.staff_lead_alert_sms_mode == "disabled":
        return None
    now = datetime.now(UTC)
    configured = not settings.staff_lead_alert_configuration_blockers
    alert = db.scalar(
        select(StaffLeadAlert)
        .where(
            or_(
                StaffLeadAlert.status.in_({"pending", "retry"}),
                StaffLeadAlert.status == "blocked" if configured else false(),
            ),
            or_(StaffLeadAlert.next_attempt_at.is_(None), StaffLeadAlert.next_attempt_at <= now),
        )
        .order_by(StaffLeadAlert.created_at)
        .with_for_update(skip_locked=True)
    )
    if alert is None:
        return None
    alert.attempt_count += 1
    alert.last_attempt_at = now
    alert.next_attempt_at = None
    if not configured:
        alert.status = "blocked"
        alert.last_error = (
            "Missing configuration: "
            + ", ".join(settings.staff_lead_alert_configuration_blockers)
        )
        db.commit()
        return alert.id
    delivery_provider = provider
    if delivery_provider is None:
        delivery_provider = (
            SimulatedCommunicationProvider()
            if settings.staff_lead_alert_sms_mode == "simulate"
            else get_twilio_messaging_provider()
        )
    try:
        result = delivery_provider.send(
            OutboundMessageRequest(
                lead_id=str(alert.lead_id),
                contact_id=str(alert.recipient_user_id),
                channel="sms",
                recipient=alert.recipient_phone,
                body=alert.message_body,
                idempotency_key=f"meta-lead-alert:{alert.id}",
                metadata={"purpose": "staff_new_lead_alert"},
            ),
            dry_run=settings.staff_lead_alert_sms_mode == "simulate",
        )
    except TwilioMessagingError as exc:
        alert.last_error = str(exc)[:2000]
        if alert.attempt_count >= settings.staff_lead_alert_max_attempts:
            alert.status = "exhausted"
        else:
            alert.status = "retry"
            alert.next_attempt_at = now + timedelta(
                seconds=settings.staff_lead_alert_retry_base_seconds
                * (2 ** max(0, alert.attempt_count - 1))
            )
        db.commit()
        return alert.id
    alert.provider = result.provider
    alert.provider_message_id = result.provider_message_id
    alert.provider_response = result.raw_payload
    alert.status = (
        "simulated" if settings.staff_lead_alert_sms_mode == "simulate" else result.status
    )
    alert.sent_at = now
    alert.last_error = None
    db.commit()
    return alert.id


def update_staff_alert_delivery_status(
    db: Session,
    *,
    message_sid: str,
    message_status: str,
    error_code: str | None,
    error_message: str | None,
) -> bool:
    alert = db.scalar(
        select(StaffLeadAlert).where(StaffLeadAlert.provider_message_id == message_sid)
    )
    if alert is None:
        return False
    alert.status = message_status
    alert.last_error = error_message or (f"Twilio error {error_code}" if error_code else None)
    alert.provider_response = {
        **(alert.provider_response or {}),
        "message_status": message_status,
        "error_code": error_code,
        "error_message": error_message,
    }
    if message_status == "delivered":
        alert.delivered_at = datetime.now(UTC)
    db.flush()
    return True


def meta_lead_to_intake(
    event: MetaLeadEvent,
    payload: dict[str, object],
) -> SellerIntakeCreate:
    fields = flatten_field_data(payload.get("field_data"))
    email = field_value(fields, "email")
    phone = field_value(fields, "phone")
    if not email and not phone:
        raise MetaLeadNeedsReview("Meta lead has neither an email address nor phone number.")
    name = field_value(fields, "name")
    if not name:
        name = " ".join(
            value
            for value in (
                field_value(fields, "first_name"),
                field_value(fields, "last_name"),
            )
            if value
        ).strip()
    name = name or f"Facebook Lead {event.provider_lead_id[-8:]}"
    state = (field_value(fields, "property_state") or "GA").upper()
    if len(state) != 2:
        state = "GA"
    form_id = string_or_none(payload.get("form_id")) or event.form_id or "unknown"
    return SellerIntakeCreate.model_validate(
        {
            "property_address": field_value(fields, "property_address")
            or f"Address pending (Meta {event.provider_lead_id[-8:]})",
            "property_city": field_value(fields, "property_city") or "Unknown",
            "property_state": state,
            "property_postal_code": field_value(fields, "property_postal_code") or "Unknown",
            "property_type": field_value(fields, "property_type"),
            "name": name,
            "phone": phone,
            "email": email,
            "preferred_contact_method": "email" if email else "phone",
            "reason_for_selling": field_value(fields, "reason_for_selling"),
            "desired_timeline": field_value(fields, "desired_timeline"),
            "property_condition": field_value(fields, "property_condition"),
            "occupancy_status": field_value(fields, "occupancy_status"),
            "asking_price": field_value(fields, "asking_price"),
            "mortgage_balance": field_value(fields, "mortgage_balance"),
            "comments": field_value(fields, "comments"),
            "consent_to_contact": True,
            "sms_consent": False,
            "conversion_session_id": f"meta-lead-{event.provider_lead_id}",
            "device_category": "unknown",
            "attribution": {
                "landing_page": f"facebook-instant-form:{form_id}"[:255],
                "utm_source": "facebook_lead_ads",
                "utm_medium": "paid_social",
                "utm_campaign": string_or_none(payload.get("campaign_name")),
                "utm_content": string_or_none(payload.get("ad_name")),
            },
        }
    )


def flatten_field_data(value: object) -> dict[str, str]:
    result: dict[str, str] = {}
    if not isinstance(value, list):
        return result
    for item in value:
        if not isinstance(item, dict):
            continue
        name = normalize_field_name(str(item.get("name") or ""))
        values = item.get("values")
        if not name or not isinstance(values, list):
            continue
        clean_values = [str(entry).strip() for entry in values if str(entry).strip()]
        if clean_values:
            result[name] = ", ".join(clean_values)[:1000]
    return result


def field_value(fields: dict[str, str], logical_name: str) -> str | None:
    for alias in FIELD_ALIASES[logical_name]:
        value = fields.get(alias)
        if value:
            return value
    return None


def normalize_field_name(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", value.strip().lower()).strip("_")


def parse_meta_datetime(value: object) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    with_timezone = value.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(with_timezone)
    except ValueError:
        return None
    return parsed.replace(tzinfo=UTC) if parsed.tzinfo is None else parsed


def string_or_none(value: Any) -> str | None:
    text = str(value).strip() if value is not None else ""
    return text or None
