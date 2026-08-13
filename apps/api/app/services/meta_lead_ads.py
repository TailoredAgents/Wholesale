import re
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

import structlog
from pydantic import ValidationError
from sqlalchemy import and_, false, func, or_, select
from sqlalchemy.orm import Session

from app.core.auth import Principal
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
    AuditEvent,
    Lead,
    MetaLeadEvent,
    Property,
    StaffLeadAlert,
)
from app.schemas.public_intake import SellerIntakeCreate
from app.schemas.staff_lead_alerts import (
    StaffLeadAlertRecoveryRead,
)
from app.schemas.zapier import ZapierFacebookLeadCreate
from app.services.communication_compliance import format_e164
from app.services.lead_lifecycle import INACTIVE_LEAD_STAGES, lock_organization_lead
from app.services.property_validation import (
    PropertyRecordClient,
    normalize_postal_code,
    validate_property_with_provider,
)
from app.services.public_intake import create_public_seller_lead, get_default_organization
from app.services.staff_lead_alerts import (
    eligible_staff_alert_recipients,
    queue_staff_lead_alerts_for_lead,
    recover_recent_unalerted_website_lead,
)

META_CONTACT_CONSENT_VERSION = "meta-lead-form-contact-v1"
META_CONTACT_CONSENT_WORDING = (
    "Seller submitted a Meta instant form requesting contact about a property offer."
)
STAFF_ALERT_RECOVERY_WINDOW = timedelta(hours=24)
STAFF_ALERT_REQUEUEABLE_STATUSES = {
    "blocked",
    "canceled",
    "exhausted",
    "failed",
    "retry",
    "simulated",
    "undelivered",
}
STAFF_ALERT_PROVIDER_FAILURE_STATUSES = {"canceled", "failed", "undelivered"}
logger = structlog.get_logger()


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
    "property_county": ("property_county", "county", "county_name"),
    "property_postal_code": (
        "property_zip_code",
        "property_postal_code",
        "zip_code",
        "postal_code",
        "post_code",
    ),
    "property_type": ("property_type", "home_type"),
    "asset_class": ("asset_class", "lead_type", "asset_type"),
    "parcel_id": ("parcel_id", "parcel_number", "apn"),
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


class MetaLeadIntakeThrottled(ValueError):
    def __init__(self, message: str, *, retry_after_seconds: int) -> None:
        super().__init__(message)
        self.retry_after_seconds = retry_after_seconds


def receive_zapier_facebook_lead(
    db: Session,
    payload: ZapierFacebookLeadCreate,
    settings: Settings,
) -> int:
    organization = get_default_organization(db)
    if payload.page_id != settings.zapier_facebook_page_id:
        raise ValueError("Zapier Facebook lead does not belong to the configured Page.")
    allowed_form_ids = settings.zapier_facebook_allowed_form_ids
    if allowed_form_ids and payload.form_id not in allowed_form_ids:
        raise ValueError("Zapier Facebook lead does not belong to an allowed form.")
    existing = db.scalar(
        select(MetaLeadEvent.id).where(
            MetaLeadEvent.organization_id == organization.id,
            MetaLeadEvent.provider_lead_id == payload.provider_lead_id,
        )
    )
    if existing is not None:
        return 0
    rolling_window_started_at = datetime.now(UTC) - timedelta(days=1)
    accepted_in_window = int(
        db.scalar(
            select(func.count())
            .select_from(MetaLeadEvent)
            .where(
                MetaLeadEvent.organization_id == organization.id,
                MetaLeadEvent.received_at >= rolling_window_started_at,
            )
        )
        or 0
    )
    if accepted_in_window >= settings.zapier_facebook_leads_daily_accept_limit:
        raise MetaLeadIntakeThrottled(
            "Zapier Facebook lead intake reached its 24-hour safety limit.",
            retry_after_seconds=3600,
        )
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
        event.last_error = "Missing configuration: " + ", ".join(
            settings.zapier_facebook_leads_configuration_blockers
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
                    MetaLeadEvent.address_enrichment_last_attempt_at <= now - timedelta(minutes=5),
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
        event.address_enrichment_last_error = "Missing configuration: " + ", ".join(
            settings.facebook_address_enrichment_configuration_blockers
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
    if lead.archived_at is not None or lead.stage_key in INACTIVE_LEAD_STAGES:
        return finish_meta_address_enrichment(
            db,
            event_id,
            status="skipped",
            error="Facebook lead was closed before address enrichment started.",
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

    refreshed_lead = lock_organization_lead(
        db,
        organization_id=lead.organization_id,
        lead_id=lead.id,
    )
    lead_is_active = bool(
        refreshed_lead is not None
        and refreshed_lead.archived_at is None
        and refreshed_lead.stage_key not in INACTIVE_LEAD_STAGES
    )

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
    if status_value == "enriched" and lead_is_active:
        from app.services.property_intelligence import enqueue_property_research

        enqueue_property_research(
            db,
            property_record,
            source_lead_id=lead.id,
            trigger_source="facebook_address_enriched",
        )
    elif status_value == "enriched":
        event.address_enrichment_last_error = (
            "Address facts were saved, but property research was not queued because the lead "
            "closed during enrichment."
        )
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
    if event.address_enrichment_attempt_count >= settings.facebook_address_enrichment_max_attempts:
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
        logger.warning(
            "staff_lead_alert_queue_skipped",
            event_id=str(event.id),
            reason="missing_lead_id",
        )
        return 0
    lead = db.get(Lead, event.lead_id)
    if lead is None:
        logger.warning(
            "staff_lead_alert_queue_skipped",
            event_id=str(event.id),
            lead_id=str(event.lead_id),
            reason="missing_lead",
        )
        return 0
    return queue_staff_lead_alerts_for_lead(
        db,
        lead=lead,
        source_type="facebook_lead_form",
        source_event_id=event.id,
        source_label="Facebook",
        source_entity_type="meta_lead_event",
        meta_lead_event_id=event.id,
    )


def recover_recent_unalerted_meta_lead(db: Session) -> int:
    now = datetime.now(UTC)
    ready_recipients, _diagnostics = eligible_staff_alert_recipients(db)
    recipients_by_organization: dict[UUID, list[UUID]] = {}
    for recipient in ready_recipients:
        recipients_by_organization.setdefault(recipient.organization_id, []).append(recipient.id)
    if not recipients_by_organization:
        return 0
    missing_recipient_conditions = []
    for organization_id, recipient_ids in recipients_by_organization.items():
        missing_alert_conditions = [
            ~select(StaffLeadAlert.id)
            .where(
                StaffLeadAlert.meta_lead_event_id == MetaLeadEvent.id,
                StaffLeadAlert.recipient_user_id == recipient_id,
            )
            .exists()
            for recipient_id in recipient_ids
        ]
        missing_recipient_conditions.append(
            and_(
                MetaLeadEvent.organization_id == organization_id,
                or_(*missing_alert_conditions),
            )
        )
    event = db.scalar(
        select(MetaLeadEvent)
        .where(
            MetaLeadEvent.status == "processed",
            MetaLeadEvent.lead_id.is_not(None),
            MetaLeadEvent.processed_at.is_not(None),
            MetaLeadEvent.processed_at >= now - STAFF_ALERT_RECOVERY_WINDOW,
            or_(*missing_recipient_conditions),
        )
        .order_by(MetaLeadEvent.processed_at, MetaLeadEvent.created_at)
        .with_for_update(skip_locked=True)
    )
    if event is None:
        return 0
    created = queue_staff_lead_alerts(db, event)
    if created:
        # Persist the recovered alert before making an external provider call. If the provider
        # fails after accepting a request, the durable row preserves the idempotency boundary.
        db.commit()
        logger.warning(
            "staff_lead_alert_missing_rows_recovered",
            event_id=str(event.id),
            lead_id=str(event.lead_id),
            alerts_created=created,
            recovery_window_hours=int(STAFF_ALERT_RECOVERY_WINDOW.total_seconds() // 3600),
        )
    return created


def process_next_staff_lead_alert(
    db: Session,
    settings: Settings,
    provider: CommunicationProvider | None = None,
) -> UUID | None:
    if settings.staff_lead_alert_sms_mode == "disabled":
        return None
    recover_recent_unalerted_website_lead(db)
    recover_recent_unalerted_meta_lead(db)
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
        alert.last_error = "Missing configuration: " + ", ".join(
            settings.staff_lead_alert_configuration_blockers
        )
        db.commit()
        logger.error(
            "staff_lead_alert_delivery_blocked",
            alert_id=str(alert.id),
            event_id=(
                str(alert.meta_lead_event_id)
                if alert.meta_lead_event_id is not None
                else None
            ),
            source_type=alert.source_type,
            source_event_id=str(alert.source_event_id),
            lead_id=str(alert.lead_id) if alert.lead_id is not None else None,
            conversation_id=(
                str(alert.conversation_id) if alert.conversation_id is not None else None
            ),
            attempt_count=alert.attempt_count,
            blockers=list(settings.staff_lead_alert_configuration_blockers),
        )
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
                lead_id=str(alert.lead_id) if alert.lead_id is not None else None,
                contact_id=str(alert.recipient_user_id),
                channel="sms",
                recipient=alert.recipient_phone,
                body=alert.message_body,
                idempotency_key=f"staff-lead-alert:{alert.id}",
                metadata={
                    "purpose": (
                        "staff_inbound_sms_alert"
                        if alert.source_type == "inbound_sms"
                        else "staff_new_lead_alert"
                    ),
                    "source_type": alert.source_type,
                    "conversation_id": (
                        str(alert.conversation_id)
                        if alert.conversation_id is not None
                        else ""
                    ),
                },
            ),
            dry_run=settings.staff_lead_alert_sms_mode == "simulate",
        )
    except TwilioMessagingError as exc:
        alert.last_error = str(exc)[:2000]
        if alert.attempt_count >= settings.staff_lead_alert_max_attempts:
            alert.status = "exhausted"
            alert.next_attempt_at = None
        else:
            alert.status = "retry"
            alert.next_attempt_at = now + timedelta(
                seconds=settings.staff_lead_alert_retry_base_seconds
                * (2 ** max(0, alert.attempt_count - 1))
            )
        db.commit()
        logger.error(
            "staff_lead_alert_delivery_failed",
            alert_id=str(alert.id),
            event_id=(
                str(alert.meta_lead_event_id)
                if alert.meta_lead_event_id is not None
                else None
            ),
            source_type=alert.source_type,
            source_event_id=str(alert.source_event_id),
            lead_id=str(alert.lead_id) if alert.lead_id is not None else None,
            conversation_id=(
                str(alert.conversation_id) if alert.conversation_id is not None else None
            ),
            status=alert.status,
            attempt_count=alert.attempt_count,
            next_attempt_at=(
                alert.next_attempt_at.isoformat() if alert.next_attempt_at is not None else None
            ),
            error=alert.last_error,
        )
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
    logger.info(
        "staff_lead_alert_delivery_accepted",
        alert_id=str(alert.id),
        event_id=(
            str(alert.meta_lead_event_id) if alert.meta_lead_event_id is not None else None
        ),
        source_type=alert.source_type,
        source_event_id=str(alert.source_event_id),
        lead_id=str(alert.lead_id) if alert.lead_id is not None else None,
        conversation_id=(
            str(alert.conversation_id) if alert.conversation_id is not None else None
        ),
        provider=alert.provider,
        provider_message_id=alert.provider_message_id,
        status=alert.status,
        attempt_count=alert.attempt_count,
    )
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
    log = (
        logger.warning
        if message_status in STAFF_ALERT_PROVIDER_FAILURE_STATUSES
        else logger.info
    )
    log(
        "staff_lead_alert_delivery_status_updated",
        alert_id=str(alert.id),
        event_id=(
            str(alert.meta_lead_event_id) if alert.meta_lead_event_id is not None else None
        ),
        source_type=alert.source_type,
        source_event_id=str(alert.source_event_id),
        lead_id=str(alert.lead_id) if alert.lead_id is not None else None,
        conversation_id=(
            str(alert.conversation_id) if alert.conversation_id is not None else None
        ),
        provider_message_id=message_sid,
        status=message_status,
        error_code=error_code,
        error_message=error_message,
    )
    return True


def requeue_staff_lead_alerts(
    db: Session,
    principal: Principal,
    settings: Settings,
    event_id: UUID,
    *,
    reason: str,
) -> StaffLeadAlertRecoveryRead | None:
    event = db.scalar(
        select(MetaLeadEvent)
        .where(
            MetaLeadEvent.id == event_id,
            MetaLeadEvent.organization_id == principal.organization_id,
        )
        .with_for_update()
    )
    if event is None:
        return None
    if event.status != "processed" or event.lead_id is None:
        raise ValueError("Only a processed Facebook lead can have its staff alerts recovered.")
    recipients, _diagnostics = eligible_staff_alert_recipients(
        db, organization_id=principal.organization_id
    )
    eligible_phones: dict[UUID, str] = {}
    for recipient in recipients:
        phone = format_e164(recipient.voice_forwarding_number or "")
        if phone is not None:
            eligible_phones[recipient.id] = phone
    if not eligible_phones:
        raise ValueError(
            "No active staff member is both opted in to lead alerts and configured with a "
            "valid cellphone."
        )
    existing_alert_ids = set(
        db.scalars(
            select(StaffLeadAlert.id).where(
                StaffLeadAlert.organization_id == principal.organization_id,
                StaffLeadAlert.meta_lead_event_id == event.id,
            )
        ).all()
    )
    created = queue_staff_lead_alerts(db, event)
    alerts = list(
        db.scalars(
            select(StaffLeadAlert)
            .where(
                StaffLeadAlert.organization_id == principal.organization_id,
                StaffLeadAlert.meta_lead_event_id == event.id,
            )
            .order_by(StaffLeadAlert.created_at)
            .with_for_update()
        ).all()
    )
    requeued = 0
    skipped_active_or_delivered = 0
    skipped_ineligible = 0
    previous_alerts: list[dict[str, object]] = []
    for alert in alerts:
        if alert.id not in existing_alert_ids:
            continue
        phone = eligible_phones.get(alert.recipient_user_id)
        if phone is None:
            skipped_ineligible += 1
            continue
        if alert.status not in STAFF_ALERT_REQUEUEABLE_STATUSES:
            skipped_active_or_delivered += 1
            continue
        previous_alerts.append(
            {
                "alert_id": str(alert.id),
                "status": alert.status,
                "attempt_count": alert.attempt_count,
                "provider_message_id": alert.provider_message_id,
                "last_error": alert.last_error,
            }
        )
        alert.recipient_phone = phone
        alert.status = "pending"
        alert.attempt_count = 0
        alert.last_attempt_at = None
        alert.next_attempt_at = None
        alert.sent_at = None
        alert.delivered_at = None
        alert.provider = None
        alert.provider_message_id = None
        alert.provider_response = None
        alert.last_error = None
        requeued += 1
    blockers = list(settings.staff_lead_alert_configuration_blockers)
    db.add(
        AuditEvent(
            organization_id=principal.organization_id,
            actor_user_id=principal.user_id,
            actor_type="user",
            action="communication.staff_lead_alerts_requeued",
            entity_type="meta_lead_event",
            entity_id=event.id,
            previous_value={"alerts": previous_alerts},
            new_value={
                "created": created,
                "requeued": requeued,
                "skipped_active_or_delivered": skipped_active_or_delivered,
                "skipped_ineligible": skipped_ineligible,
                "delivery_configured": not blockers,
            },
            reason=reason.strip(),
        )
    )
    db.commit()
    logger.warning(
        "staff_lead_alert_manual_recovery_queued",
        event_id=str(event.id),
        lead_id=str(event.lead_id),
        actor_user_id=str(principal.user_id),
        created=created,
        requeued=requeued,
        skipped_active_or_delivered=skipped_active_or_delivered,
        skipped_ineligible=skipped_ineligible,
        delivery_configured=not blockers,
        blockers=blockers,
    )
    return StaffLeadAlertRecoveryRead(
        event_id=event.id,
        lead_id=event.lead_id,
        created=created,
        requeued=requeued,
        skipped_active_or_delivered=skipped_active_or_delivered,
        skipped_ineligible=skipped_ineligible,
        delivery_configured=not blockers,
        configuration_blockers=blockers,
    )


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
            "property_county": field_value(fields, "property_county"),
            "property_type": field_value(fields, "property_type"),
            "asset_class": field_value(fields, "asset_class"),
            "parcel_id": field_value(fields, "parcel_id"),
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
