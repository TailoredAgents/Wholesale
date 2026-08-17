from datetime import UTC, datetime, timedelta
from uuid import UUID

import structlog
from pydantic import ValidationError
from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.models.foundation import (
    ActivityEvent,
    Appointment,
    AttributionTouch,
    ConsentRecord,
    Contact,
    ContactMethod,
    Lead,
    LeadFormSubmission,
    Property,
    ProspectingProviderEvent,
    SuppressionRecord,
    User,
)
from app.schemas.public_intake import SellerIntakeAttribution, SellerIntakeCreate
from app.schemas.zapier import ZapierBatchDialerEventCreate
from app.services.acquisition_operations import (
    create_notification,
    upsert_internal_calendar_event,
)
from app.services.communication_compliance import format_e164
from app.services.marketing import enqueue_meta_schedule_conversion
from app.services.public_intake import create_public_seller_lead, get_default_organization
from app.services.staff_lead_alerts import queue_staff_lead_alerts_for_lead

PROVIDER = "batchdialer"
CONTRACT_VERSION = "zapier_batchdialer_v1"
CONTACT_CONSENT_VERSION = "batchdialer-va-follow-up-v1"
CONTACT_CONSENT_WORDING = (
    "Seller explicitly authorized follow-up through the mapped channel during a "
    "BatchDialer conversation with a Stonegate representative."
)
SMS_CONSENT_VERSION = "batchdialer-va-sms-follow-up-v1"
SMS_CONSENT_WORDING = (
    "Seller explicitly authorized SMS follow-up during a BatchDialer conversation; "
    "Stonegate received that permission through its authenticated Zapier handoff."
)
DNC_CONSENT_VERSION = "batchdialer-dnc-v1"
ACTIVE_APPOINTMENT_STATUSES = {"scheduled", "rescheduled", "confirmed"}
CALENDAR_LEAD_MISSING_ERROR = "Calendar event is waiting for its matching BatchDialer lead."
EXPLICIT_LEAD_MISSING_ERROR = "The explicitly linked BatchDialer lead event has not arrived yet."
LEAD_PROCESSING_PENDING_ERROR = "Related BatchDialer lead has not finished processing."
CALENDAR_DEPENDENCY_ERRORS = frozenset(
    {
        CALENDAR_LEAD_MISSING_ERROR,
        EXPLICIT_LEAD_MISSING_ERROR,
        LEAD_PROCESSING_PENDING_ERROR,
    }
)

logger = structlog.get_logger()


class BatchDialerNeedsReview(ValueError):
    """The event is durable but requires a manager to resolve ambiguous data."""


class BatchDialerDependencyPending(RuntimeError):
    """A related lead event has not arrived or completed yet."""


def receive_zapier_batchdialer_event(
    db: Session,
    payload: ZapierBatchDialerEventCreate,
    settings: Settings,
) -> int:
    organization = get_default_organization(db)
    if payload.campaign_id not in settings.zapier_batchdialer_allowed_campaign_ids:
        raise ValueError("BatchDialer event does not belong to an allowed campaign.")
    existing = db.scalar(
        select(ProspectingProviderEvent.id).where(
            ProspectingProviderEvent.organization_id == organization.id,
            ProspectingProviderEvent.provider == PROVIDER,
            ProspectingProviderEvent.external_event_id == payload.event_id,
        )
    )
    if existing is not None:
        return 0
    event = ProspectingProviderEvent(
        organization_id=organization.id,
        provider_campaign_sync_id=None,
        provider_contact_sync_id=None,
        batch_entry_id=None,
        attempt_id=None,
        provider=PROVIDER,
        external_event_id=payload.event_id,
        event_type=payload.event_type,
        processing_status="pending",
        provider_call_id=payload.provider_call_id,
        provider_recording_id=payload.provider_recording_id,
        payload={**payload.raw_payload(), "_stonegate_contract": CONTRACT_VERSION},
        retry_count=0,
        error_message=None,
        received_at=datetime.now(UTC),
        processed_at=None,
    )
    db.add(event)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        return 0
    return 1


def process_next_batchdialer_event(db: Session, settings: Settings) -> UUID | None:
    if not settings.zapier_batchdialer_enabled:
        return None
    if not settings.zapier_batchdialer_configured:
        return None
    now = datetime.now(UTC)
    retry_cutoff = now - timedelta(seconds=settings.zapier_batchdialer_retry_base_seconds)
    stale_cutoff = now - timedelta(minutes=5)
    event = db.scalar(
        select(ProspectingProviderEvent)
        .where(
            ProspectingProviderEvent.provider == PROVIDER,
            ProspectingProviderEvent.event_type.in_(
                ("lead.created", "calendar.created", "dnc.added")
            ),
            ProspectingProviderEvent.payload["_stonegate_contract"].as_string() == CONTRACT_VERSION,
            or_(
                ProspectingProviderEvent.processing_status == "pending",
                (
                    (ProspectingProviderEvent.processing_status == "retry")
                    & (ProspectingProviderEvent.updated_at <= retry_cutoff)
                ),
                (
                    (ProspectingProviderEvent.processing_status == "processing")
                    & (ProspectingProviderEvent.updated_at <= stale_cutoff)
                ),
            ),
        )
        .order_by(ProspectingProviderEvent.received_at, ProspectingProviderEvent.created_at)
        .with_for_update(skip_locked=True)
    )
    if event is None:
        return None
    event.processing_status = "processing"
    event.retry_count += 1
    event.error_message = None
    event_id = event.id
    db.commit()

    try:
        raw_payload = dict(event.payload or {})
        raw_payload.pop("_stonegate", None)
        raw_payload.pop("_stonegate_contract", None)
        payload = ZapierBatchDialerEventCreate.model_validate(raw_payload)
        if payload.campaign_id not in settings.zapier_batchdialer_allowed_campaign_ids:
            raise BatchDialerNeedsReview(
                "BatchDialer event campaign is no longer on the configured allowlist."
            )
        if payload.event_type == "lead.created":
            result = process_batchdialer_lead(db, event, payload)
        elif payload.event_type == "calendar.created":
            result = process_batchdialer_calendar(db, event, payload)
        else:
            result = process_batchdialer_dnc(db, event, payload)
    except (BatchDialerNeedsReview, ValidationError) as exc:
        db.rollback()
        mark_batchdialer_needs_review(db, event_id, str(exc))
        return event_id
    except BatchDialerDependencyPending as exc:
        db.rollback()
        mark_batchdialer_failure(db, event_id, settings, str(exc))
        return event_id
    except Exception as exc:
        db.rollback()
        logger.exception(
            "batchdialer_event_processing_failed",
            event_id=str(event_id),
        )
        mark_batchdialer_failure(db, event_id, settings, str(exc))
        return event_id

    refreshed = db.get(ProspectingProviderEvent, event_id)
    if refreshed is None:
        raise RuntimeError("BatchDialer provider event disappeared during processing.")
    refreshed.processing_status = "processed"
    refreshed.processed_at = datetime.now(UTC)
    refreshed.error_message = None
    refreshed.payload = {**dict(refreshed.payload or {}), "_stonegate": result}
    db.commit()
    return refreshed.id


def process_batchdialer_lead(
    db: Session,
    event: ProspectingProviderEvent,
    payload: ZapierBatchDialerEventCreate,
) -> dict[str, object]:
    ensure_provider_contact_is_consistent(db, event, payload)
    ensure_permission_does_not_override_suppression(db, event, payload)
    duplicate_provider_handoff = False
    existing_submission = provider_intake_submission(db, event)
    if existing_submission is not None:
        lead = db.get(Lead, existing_submission.lead_id)
        if lead is None:
            raise BatchDialerNeedsReview("Prior BatchDialer intake is missing its CRM lead.")
        matched_existing_lead = True
    else:
        prior_lead = related_lead_for_provider_contact(db, event, payload, allow_pending=False)
        if prior_lead is not None:
            lead = prior_lead
            matched_existing_lead = True
            duplicate_provider_handoff = True
        else:
            permission_channels = payload.follow_up_channels()
            intake = batchdialer_lead_to_intake(payload, permission_channels)
            response = create_public_seller_lead(
                db,
                intake,
                ip_address=None,
                user_agent="Authenticated Zapier BatchDialer handoff",
                intake_source=PROVIDER,
                contact_consent_wording_version=CONTACT_CONSENT_VERSION,
                contact_consent_wording=CONTACT_CONSENT_WORDING,
                contact_consent_channels=frozenset(
                    channel for channel in permission_channels if channel in {"phone", "email"}
                ),
                sms_consent_wording_version=(
                    SMS_CONSENT_VERSION if "sms" in permission_channels else None
                ),
                sms_consent_wording=(SMS_CONSENT_WORDING if "sms" in permission_channels else None),
                provider_record_id=event.external_event_id,
                notification_source_label="BatchDialer VA handoff",
            )
            lead = db.get(Lead, response.lead_id)
            if lead is None:
                raise RuntimeError("BatchDialer intake did not create or match a CRM lead.")
            matched_existing_lead = response.matched_existing_lead

    if not duplicate_provider_handoff:
        apply_batchdialer_lead_context(lead, event, payload)
        if matched_existing_lead:
            ensure_batchdialer_attribution_touch(db, lead, event, payload)
        db.add(
            ActivityEvent(
                organization_id=lead.organization_id,
                actor_user_id=None,
                entity_type="lead",
                entity_id=lead.id,
                event_type="lead.batchdialer_warm_handoff_received",
                summary=(
                    f"BatchDialer {payload.disposition or 'warm'} handoff received from "
                    f"{payload.va_name or payload.va_email or 'assigned VA'}."
                ),
            )
        )
        queue_staff_lead_alerts_for_lead(
            db,
            lead=lead,
            source_type="batchdialer_warm_handoff",
            source_event_id=event.id,
            source_label="BatchDialer",
            source_entity_type="prospecting_provider_event",
        )
    revived_dependency_count = revive_batchdialer_calendar_dependencies(db, event, payload)
    db.flush()
    return {
        "lead_id": str(lead.id),
        "contact_id": str(lead.contact_id),
        "property_id": str(lead.property_id),
        "matched_existing_lead": matched_existing_lead,
        "duplicate_provider_handoff": duplicate_provider_handoff,
        "revived_dependency_count": revived_dependency_count,
    }


def process_batchdialer_calendar(
    db: Session,
    event: ProspectingProviderEvent,
    payload: ZapierBatchDialerEventCreate,
) -> dict[str, object]:
    lead = require_related_lead(db, event, payload)
    assert payload.provider_appointment_id is not None
    assert payload.appointment_start_at is not None
    appointments = db.scalars(
        select(Appointment)
        .where(
            Appointment.organization_id == lead.organization_id,
            Appointment.lead_id == lead.id,
        )
        .order_by(Appointment.created_at)
    ).all()
    existing = next(
        (
            appointment
            for appointment in appointments
            if (appointment.appointment_metadata or {}).get("provider") == PROVIDER
            and (appointment.appointment_metadata or {}).get("provider_appointment_id")
            == payload.provider_appointment_id
        ),
        None,
    )
    if existing is not None:
        return {
            "lead_id": str(lead.id),
            "appointment_id": str(existing.id),
            "matched_existing_appointment": True,
        }
    prior_initial = next(
        (
            appointment
            for appointment in appointments
            if (appointment.appointment_metadata or {}).get("source") == "batchdialer_calendar"
            and appointment.status in ACTIVE_APPOINTMENT_STATUSES
        ),
        None,
    )
    if prior_initial is not None:
        raise BatchDialerNeedsReview(
            "The lead already has an active initial BatchDialer appointment with a different ID."
        )
    owner = resolve_appointment_owner(db, lead, payload)
    property_record = db.get(Property, lead.property_id)
    location_type = payload.appointment_location_type or "seller_property"
    location = payload.appointment_location
    if location is None and location_type == "seller_property" and property_record is not None:
        location = format_property_address(property_record)
    appointment = Appointment(
        organization_id=lead.organization_id,
        lead_id=lead.id,
        contact_id=lead.contact_id,
        property_id=lead.property_id,
        owner_user_id=owner.id if owner is not None else lead.assigned_user_id,
        appointment_type=payload.appointment_type or "acquisition_consultation",
        status="scheduled",
        scheduled_start_at=payload.appointment_start_at,
        scheduled_end_at=payload.appointment_end_at
        or payload.appointment_start_at + timedelta(hours=1),
        location_type=location_type,
        location=location,
        notes=payload.appointment_notes,
        outcome=None,
        external_calendar_id=payload.provider_appointment_id,
        appointment_metadata={
            "source": "batchdialer_calendar",
            "provider": PROVIDER,
            "provider_appointment_id": payload.provider_appointment_id,
            "provider_contact_id": payload.provider_contact_id,
            "provider_event_id": event.external_event_id,
            "campaign_id": payload.campaign_id,
            "calendar_synced": False,
        },
    )
    db.add(appointment)
    db.flush()
    upsert_internal_calendar_event(db, appointment)
    enqueue_meta_schedule_conversion(db, appointment=appointment, lead=lead)
    lead.appointment_status = "scheduled"
    lead.next_follow_up_at = payload.appointment_start_at
    if lead.stage_key in {
        "new",
        "contact_attempt_due",
        "attempting_contact",
        "contacted",
        "qualification_in_progress",
        "qualified",
    }:
        lead.stage_key = "appointment_scheduled"
    if appointment.owner_user_id is not None:
        create_notification(
            db,
            organization_id=lead.organization_id,
            recipient_user_id=appointment.owner_user_id,
            notification_type="appointment_scheduled",
            title="BatchDialer appointment scheduled",
            body="A VA-sourced seller appointment was added to the Stonegate calendar.",
            entity_type="appointment",
            entity_id=appointment.id,
            action_url=f"/os/leads/{lead.id}?tab=communications",
            dedupe_key=f"batchdialer-appointment:{payload.provider_appointment_id}",
        )
    db.add(
        ActivityEvent(
            organization_id=lead.organization_id,
            actor_user_id=None,
            entity_type="lead",
            entity_id=lead.id,
            event_type="lead.batchdialer_appointment_scheduled",
            summary=(
                f"BatchDialer appointment scheduled for {payload.appointment_start_at.isoformat()}."
            ),
        )
    )
    db.flush()
    return {
        "lead_id": str(lead.id),
        "appointment_id": str(appointment.id),
        "matched_existing_appointment": False,
    }


def process_batchdialer_dnc(
    db: Session,
    event: ProspectingProviderEvent,
    payload: ZapierBatchDialerEventCreate,
) -> dict[str, object]:
    lead = related_lead_for_event(db, event, payload, allow_pending=False)
    normalized_phone = format_e164(payload.phone)
    if normalized_phone is None:
        raise BatchDialerNeedsReview("DNC event does not resolve to a valid phone number.")
    method = contact_method_for_phone(db, event.organization_id, normalized_phone)
    contact = db.get(Contact, method.contact_id) if method is not None else None
    if lead is not None and contact is None:
        contact = db.get(Contact, lead.contact_id)
    elif lead is not None and contact is not None and contact.id != lead.contact_id:
        logger.warning(
            "batchdialer_dnc_contact_link_mismatch",
            event_id=str(event.id),
            related_lead_id=str(lead.id),
            phone_contact_id=str(contact.id),
        )
        lead = None
    now = datetime.now(UTC)
    reason = payload.dnc_reason or "Seller requested no further calls"
    suppression = db.scalar(
        select(SuppressionRecord).where(
            SuppressionRecord.organization_id == event.organization_id,
            SuppressionRecord.channel == "phone",
            SuppressionRecord.normalized_address == normalized_phone,
        )
    )
    if suppression is None:
        suppression = db.scalar(
            select(SuppressionRecord).where(
                SuppressionRecord.organization_id == event.organization_id,
                SuppressionRecord.channel == "phone",
                SuppressionRecord.normalized_address.in_(
                    normalized_phone_variants(normalized_phone)
                ),
            )
        )
    if suppression is None:
        suppression = SuppressionRecord(
            organization_id=event.organization_id,
            contact_id=contact.id if contact is not None else None,
            channel="phone",
            normalized_address=normalized_phone,
            status="active",
            reason=reason,
            source="batchdialer_dnc",
            provider=PROVIDER,
            external_event_id=event.external_event_id,
            suppressed_at=now,
            lifted_at=None,
            suppression_metadata={
                "provider_contact_id": payload.provider_contact_id,
                "campaign_id": payload.campaign_id,
            },
        )
        db.add(suppression)
    else:
        suppression.contact_id = contact.id if contact is not None else suppression.contact_id
        suppression.normalized_address = normalized_phone
        suppression.status = "active"
        suppression.reason = reason
        suppression.source = "batchdialer_dnc"
        suppression.provider = PROVIDER
        suppression.external_event_id = event.external_event_id
        suppression.suppressed_at = now
        suppression.lifted_at = None
    for channel in ("phone", "sms") if contact is not None else ():
        assert contact is not None
        wording_version = f"{DNC_CONSENT_VERSION}:{event.external_event_id}"[:80]
        existing_revoke = db.scalar(
            select(ConsentRecord.id).where(
                ConsentRecord.organization_id == event.organization_id,
                ConsentRecord.contact_id == contact.id,
                ConsentRecord.channel == channel,
                ConsentRecord.wording_version == wording_version,
            )
        )
        if existing_revoke is None:
            db.add(
                ConsentRecord(
                    organization_id=event.organization_id,
                    contact_id=contact.id,
                    channel=channel,
                    status="revoked",
                    source="batchdialer_dnc",
                    wording_version=wording_version,
                    wording=f"BatchDialer reported the seller's DNC request: {reason}",
                    normalized_address=normalized_phone,
                    captured_ip=None,
                    user_agent="Authenticated Zapier BatchDialer handoff",
                    created_at=now,
                    updated_at=now,
                )
            )
    db.flush()
    db.add(
        ActivityEvent(
            organization_id=event.organization_id,
            actor_user_id=None,
            entity_type="contact" if contact is not None else "suppression_record",
            entity_id=contact.id if contact is not None else suppression.id,
            event_type="contact.batchdialer_dnc_recorded",
            summary=(
                "BatchDialer DNC request suppressed phone follow-up"
                + (" and revoked contact consent." if contact is not None else ".")
            ),
        )
    )
    db.flush()
    return {
        "lead_id": str(lead.id) if lead is not None else None,
        "contact_id": str(contact.id) if contact is not None else None,
        "suppression_id": str(suppression.id),
    }


def batchdialer_lead_to_intake(
    payload: ZapierBatchDialerEventCreate,
    permission_channels: frozenset[str],
) -> SellerIntakeCreate:
    preferred_contact_method = (
        "phone"
        if "phone" in permission_channels
        else "email"
        if "email" in permission_channels
        else "sms"
    )
    return SellerIntakeCreate(
        property_address=payload.property_address or "",
        property_city=payload.property_city or "",
        property_state=payload.property_state or "GA",
        property_postal_code=payload.property_zip_code or "",
        property_county=payload.property_county,
        property_type=payload.property_type,
        asset_class=payload.asset_class,
        parcel_id=payload.parcel_id,
        name=payload.full_name or "",
        phone=payload.phone,
        email=payload.email,
        preferred_contact_method=preferred_contact_method,
        reason_for_selling=payload.reason_for_selling,
        desired_timeline=payload.desired_timeline,
        property_condition=payload.property_condition,
        occupancy_status=payload.occupancy_status,
        asking_price=payload.asking_price,
        mortgage_balance=payload.mortgage_balance,
        comments=payload.notes,
        consent_to_contact=True,
        sms_consent="sms" in permission_channels,
        attribution=SellerIntakeAttribution(
            utm_source=PROVIDER,
            utm_medium="va_outbound",
            utm_campaign=payload.campaign_name or payload.campaign_id,
            utm_term=payload.provider_agent_id
            or (str(payload.va_email) if payload.va_email else None),
            utm_content=payload.event_id,
        ),
    )


def ensure_provider_contact_is_consistent(
    db: Session,
    event: ProspectingProviderEvent,
    payload: ZapierBatchDialerEventCreate,
) -> None:
    contact_ids: set[UUID] = set()
    if payload.email is not None:
        email_method = db.scalar(
            select(ContactMethod).where(
                ContactMethod.organization_id == event.organization_id,
                ContactMethod.method_type == "email",
                ContactMethod.normalized_value == str(payload.email).strip().lower(),
            )
        )
        if email_method is not None:
            contact_ids.add(email_method.contact_id)
    normalized_phone = format_e164(payload.phone)
    if normalized_phone is not None:
        phone_method = contact_method_for_phone(db, event.organization_id, normalized_phone)
        if phone_method is not None:
            contact_ids.add(phone_method.contact_id)
    if len(contact_ids) > 1:
        raise BatchDialerNeedsReview(
            "BatchDialer email and phone match different CRM contacts; automatic merge stopped."
        )


def ensure_permission_does_not_override_suppression(
    db: Session,
    event: ProspectingProviderEvent,
    payload: ZapierBatchDialerEventCreate,
) -> None:
    channels = payload.follow_up_channels()
    normalized_phone = format_e164(payload.phone)
    if normalized_phone is None:
        return
    suppression_channels: list[str] = []
    if "phone" in channels:
        suppression_channels.extend(("phone", "all"))
    if "sms" in channels:
        suppression_channels.append("sms")
    if not suppression_channels:
        return
    suppression = db.scalar(
        select(SuppressionRecord.id).where(
            SuppressionRecord.organization_id == event.organization_id,
            SuppressionRecord.channel.in_(suppression_channels),
            SuppressionRecord.normalized_address.in_(normalized_phone_variants(normalized_phone)),
            SuppressionRecord.status == "active",
        )
    )
    if suppression is not None:
        raise BatchDialerNeedsReview(
            "BatchDialer follow-up permission conflicts with an active suppression record."
        )


def provider_intake_submission(
    db: Session,
    event: ProspectingProviderEvent,
) -> LeadFormSubmission | None:
    return db.scalar(
        select(LeadFormSubmission)
        .where(
            LeadFormSubmission.organization_id == event.organization_id,
            LeadFormSubmission.raw_payload["_intake_source"].as_string() == PROVIDER,
            LeadFormSubmission.raw_payload["_provider_record_id"].as_string()
            == event.external_event_id,
        )
        .order_by(LeadFormSubmission.created_at)
    )


def related_lead_for_provider_contact(
    db: Session,
    event: ProspectingProviderEvent,
    payload: ZapierBatchDialerEventCreate,
    *,
    allow_pending: bool,
) -> Lead | None:
    prior = db.scalar(
        select(ProspectingProviderEvent)
        .where(
            ProspectingProviderEvent.organization_id == event.organization_id,
            ProspectingProviderEvent.provider == PROVIDER,
            ProspectingProviderEvent.event_type == "lead.created",
            ProspectingProviderEvent.id != event.id,
            ProspectingProviderEvent.payload["provider_contact_id"].as_string()
            == payload.provider_contact_id,
            ProspectingProviderEvent.processing_status == "processed",
        )
        .order_by(ProspectingProviderEvent.received_at.desc())
    )
    if prior is None:
        return None
    return lead_from_provider_event(db, prior, allow_pending=allow_pending)


def related_lead_for_event(
    db: Session,
    event: ProspectingProviderEvent,
    payload: ZapierBatchDialerEventCreate,
    *,
    allow_pending: bool,
) -> Lead | None:
    related = None
    if payload.related_lead_event_id:
        related = db.scalar(
            select(ProspectingProviderEvent).where(
                ProspectingProviderEvent.organization_id == event.organization_id,
                ProspectingProviderEvent.provider == PROVIDER,
                ProspectingProviderEvent.external_event_id == payload.related_lead_event_id,
                ProspectingProviderEvent.event_type == "lead.created",
            )
        )
        if related is None:
            if allow_pending:
                raise BatchDialerDependencyPending(EXPLICIT_LEAD_MISSING_ERROR)
            return None
        related_contact_id = (related.payload or {}).get("provider_contact_id")
        if related_contact_id != payload.provider_contact_id:
            raise BatchDialerNeedsReview(
                "The explicitly linked BatchDialer lead belongs to a different provider contact."
            )
        return lead_from_provider_event(db, related, allow_pending=allow_pending)
    if related is None:
        related = db.scalar(
            select(ProspectingProviderEvent)
            .where(
                ProspectingProviderEvent.organization_id == event.organization_id,
                ProspectingProviderEvent.provider == PROVIDER,
                ProspectingProviderEvent.event_type == "lead.created",
                ProspectingProviderEvent.payload["provider_contact_id"].as_string()
                == payload.provider_contact_id,
            )
            .order_by(ProspectingProviderEvent.received_at.desc())
        )
    if related is None:
        return None
    return lead_from_provider_event(db, related, allow_pending=allow_pending)


def revive_batchdialer_calendar_dependencies(
    db: Session,
    lead_event: ProspectingProviderEvent,
    payload: ZapierBatchDialerEventCreate,
) -> int:
    """Revive appointments that arrived before their independent lead Zap."""

    candidates = db.scalars(
        select(ProspectingProviderEvent).where(
            ProspectingProviderEvent.organization_id == lead_event.organization_id,
            ProspectingProviderEvent.provider == PROVIDER,
            ProspectingProviderEvent.event_type == "calendar.created",
            ProspectingProviderEvent.processing_status.in_(("retry", "exhausted")),
            ProspectingProviderEvent.payload["_stonegate_contract"].as_string() == CONTRACT_VERSION,
        )
    ).all()
    revived = 0
    for candidate in candidates:
        candidate_payload = dict(candidate.payload or {})
        explicit_lead_event_id = candidate_payload.get("related_lead_event_id")
        matches = (
            explicit_lead_event_id == lead_event.external_event_id
            if explicit_lead_event_id
            else candidate_payload.get("provider_contact_id") == payload.provider_contact_id
        )
        if not matches or candidate.error_message not in CALENDAR_DEPENDENCY_ERRORS:
            continue
        candidate.processing_status = "pending"
        candidate.retry_count = 0
        candidate.error_message = None
        candidate.processed_at = None
        revived += 1
    if revived:
        logger.info(
            "batchdialer_calendar_dependencies_revived",
            lead_event_id=str(lead_event.id),
            external_lead_event_id=lead_event.external_event_id,
            provider_contact_id=payload.provider_contact_id,
            revived_count=revived,
        )
    return revived


def require_related_lead(
    db: Session,
    event: ProspectingProviderEvent,
    payload: ZapierBatchDialerEventCreate,
) -> Lead:
    lead = related_lead_for_event(db, event, payload, allow_pending=True)
    if lead is None:
        raise BatchDialerDependencyPending(CALENDAR_LEAD_MISSING_ERROR)
    return lead


def lead_from_provider_event(
    db: Session,
    event: ProspectingProviderEvent,
    *,
    allow_pending: bool,
) -> Lead | None:
    stonegate = (event.payload or {}).get("_stonegate")
    lead_id = stonegate.get("lead_id") if isinstance(stonegate, dict) else None
    if lead_id is None:
        if allow_pending:
            raise BatchDialerDependencyPending(LEAD_PROCESSING_PENDING_ERROR)
        return None
    try:
        parsed_lead_id = UUID(str(lead_id))
    except ValueError as exc:
        raise BatchDialerNeedsReview("Related BatchDialer event has an invalid lead ID.") from exc
    lead = db.get(Lead, parsed_lead_id)
    if lead is None:
        raise BatchDialerNeedsReview("Related BatchDialer event references a missing lead.")
    return lead


def apply_batchdialer_lead_context(
    lead: Lead,
    event: ProspectingProviderEvent,
    payload: ZapierBatchDialerEventCreate,
) -> None:
    context = dict(lead.qualification_context or {})
    context["batchdialer"] = {
        "provider_event_id": event.external_event_id,
        "provider_contact_id": payload.provider_contact_id,
        "provider_call_id": payload.provider_call_id,
        "provider_recording_id": payload.provider_recording_id,
        "provider_agent_id": payload.provider_agent_id,
        "campaign_id": payload.campaign_id,
        "campaign_name": payload.campaign_name,
        "va_name": payload.va_name,
        "va_email": str(payload.va_email) if payload.va_email else None,
        "disposition": payload.disposition,
        "follow_up_permission": payload.follow_up_permission,
        "occurred_at": payload.occurred_at.isoformat(),
        "notes": payload.notes,
    }
    lead.qualification_context = context


def ensure_batchdialer_attribution_touch(
    db: Session,
    lead: Lead,
    event: ProspectingProviderEvent,
    payload: ZapierBatchDialerEventCreate,
) -> None:
    existing = db.scalar(
        select(AttributionTouch.id).where(
            AttributionTouch.organization_id == lead.organization_id,
            AttributionTouch.lead_id == lead.id,
            AttributionTouch.touch_type == "batchdialer_handoff",
            AttributionTouch.content == event.external_event_id,
        )
    )
    if existing is not None:
        return
    db.add(
        AttributionTouch(
            organization_id=lead.organization_id,
            lead_id=lead.id,
            touch_type="batchdialer_handoff",
            source=PROVIDER,
            medium="va_outbound",
            campaign=payload.campaign_name or payload.campaign_id,
            term=payload.provider_agent_id or (str(payload.va_email) if payload.va_email else None),
            content=event.external_event_id,
            gclid=None,
            fbclid=None,
            fbclid_captured_at=None,
            landing_page=None,
            referrer=None,
        )
    )


def resolve_appointment_owner(
    db: Session,
    lead: Lead,
    payload: ZapierBatchDialerEventCreate,
) -> User | None:
    if payload.appointment_owner_email is None:
        return db.get(User, lead.assigned_user_id) if lead.assigned_user_id else None
    owner = db.scalar(
        select(User).where(
            User.organization_id == lead.organization_id,
            func.lower(User.email) == str(payload.appointment_owner_email).lower(),
            User.is_active.is_(True),
        )
    )
    if owner is None:
        raise BatchDialerNeedsReview("Appointment owner email does not match an active user.")
    return owner


def contact_method_for_phone(
    db: Session,
    organization_id: UUID,
    phone: str,
) -> ContactMethod | None:
    digits = "".join(character for character in phone if character.isdigit())
    alternatives = {digits}
    if len(digits) == 11 and digits.startswith("1"):
        alternatives.add(digits[1:])
    return db.scalar(
        select(ContactMethod).where(
            ContactMethod.organization_id == organization_id,
            ContactMethod.method_type == "phone",
            ContactMethod.normalized_value.in_(alternatives),
        )
    )


def normalized_phone_variants(phone: str) -> tuple[str, ...]:
    digits = "".join(character for character in phone if character.isdigit())
    variants = {phone, digits}
    if len(digits) == 11 and digits.startswith("1"):
        variants.add(digits[1:])
    return tuple(value for value in variants if value)


def format_property_address(property_record: Property) -> str:
    line = ", ".join(
        part for part in (property_record.street_address, property_record.city) if part
    )
    region = " ".join(part for part in (property_record.state, property_record.postal_code) if part)
    return ", ".join(part for part in (line, region) if part)


def mark_batchdialer_needs_review(db: Session, event_id: UUID, error: str) -> None:
    event = db.get(ProspectingProviderEvent, event_id)
    if event is None:
        return
    event.processing_status = "needs_review"
    event.error_message = error[:2000]
    event.processed_at = datetime.now(UTC)
    logger.warning(
        "batchdialer_event_needs_review",
        event_id=str(event.id),
        external_event_id=event.external_event_id,
        event_type=event.event_type,
        processing_status=event.processing_status,
        retry_count=event.retry_count,
        error_message=event.error_message,
    )
    db.commit()


def mark_batchdialer_failure(
    db: Session,
    event_id: UUID,
    settings: Settings,
    error: str,
) -> None:
    event = db.get(ProspectingProviderEvent, event_id)
    if event is None:
        return
    event.error_message = error[:2000]
    event.processing_status = (
        "exhausted" if event.retry_count >= settings.zapier_batchdialer_max_attempts else "retry"
    )
    event.processed_at = datetime.now(UTC) if event.processing_status == "exhausted" else None
    log = logger.error if event.processing_status == "exhausted" else logger.warning
    log(
        "batchdialer_event_processing_deferred",
        event_id=str(event.id),
        external_event_id=event.external_event_id,
        event_type=event.event_type,
        processing_status=event.processing_status,
        retry_count=event.retry_count,
        error_message=event.error_message,
    )
    db.commit()
