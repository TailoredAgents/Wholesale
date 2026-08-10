from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID

import structlog
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.foundation import (
    ActivityEvent,
    AuditEvent,
    Contact,
    Lead,
    LeadFormSubmission,
    Notification,
    Property,
    StaffLeadAlert,
    User,
)
from app.services.communication_compliance import format_e164
from app.services.lead_lifecycle import INACTIVE_LEAD_STAGES

logger = structlog.get_logger()
STAFF_ALERT_RECOVERY_WINDOW = timedelta(hours=24)


@dataclass(frozen=True)
class StaffAlertRecipientDiagnostics:
    active_opted_in: int
    ready: int
    missing_phone: int
    invalid_phone: int


def eligible_staff_alert_recipients(
    db: Session,
    *,
    organization_id: UUID | None = None,
) -> tuple[list[User], StaffAlertRecipientDiagnostics]:
    statement = select(User).where(
        User.is_active.is_(True),
        User.lead_alert_sms_enabled.is_(True),
    )
    if organization_id is not None:
        statement = statement.where(User.organization_id == organization_id)
    opted_in = list(db.scalars(statement).all())
    ready: list[User] = []
    missing_phone = 0
    invalid_phone = 0
    for user in opted_in:
        if not user.voice_forwarding_number:
            missing_phone += 1
            continue
        if format_e164(user.voice_forwarding_number) is None:
            invalid_phone += 1
            continue
        ready.append(user)
    return ready, StaffAlertRecipientDiagnostics(
        active_opted_in=len(opted_in),
        ready=len(ready),
        missing_phone=missing_phone,
        invalid_phone=invalid_phone,
    )


def queue_staff_lead_alerts_for_lead(
    db: Session,
    *,
    lead: Lead,
    source_type: str,
    source_event_id: UUID,
    source_label: str,
    source_entity_type: str,
    meta_lead_event_id: UUID | None = None,
) -> int:
    contact = db.get(Contact, lead.contact_id)
    property_record = db.get(Property, lead.property_id)
    recipients, diagnostics = eligible_staff_alert_recipients(
        db,
        organization_id=lead.organization_id,
    )
    created = 0
    existing_count = 0
    for recipient in recipients:
        phone = format_e164(recipient.voice_forwarding_number or "")
        assert phone is not None
        existing = db.scalar(
            select(StaffLeadAlert.id).where(
                StaffLeadAlert.organization_id == lead.organization_id,
                StaffLeadAlert.source_type == source_type,
                StaffLeadAlert.source_event_id == source_event_id,
                StaffLeadAlert.recipient_user_id == recipient.id,
            )
        )
        if existing is not None:
            existing_count += 1
            continue
        contact_name = contact.legal_name if contact else "New seller"
        market = (
            property_record.city
            or property_record.county
            or property_record.state
            if property_record
            else "Georgia"
        )
        asset_label = lead.asset_class.title()
        db.add(
            StaffLeadAlert(
                organization_id=lead.organization_id,
                meta_lead_event_id=meta_lead_event_id,
                source_type=source_type,
                source_event_id=source_event_id,
                lead_id=lead.id,
                recipient_user_id=recipient.id,
                recipient_phone=phone,
                message_body=(
                    f"New {source_label} {asset_label} lead: {contact_name}, {market}. "
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
    queue_snapshot = {
        "lead_id": str(lead.id),
        "source_type": source_type,
        "source_event_id": str(source_event_id),
        "active_opted_in_recipients": diagnostics.active_opted_in,
        "ready_recipients": diagnostics.ready,
        "recipients_missing_phone": diagnostics.missing_phone,
        "recipients_with_invalid_phone": diagnostics.invalid_phone,
        "alerts_created": created,
        "alerts_already_present": existing_count,
    }
    if created:
        audit_action = "communication.staff_lead_alerts_queued"
        audit_reason = "Queued internal SMS alerts for active opted-in staff recipients."
    elif existing_count:
        audit_action = "communication.staff_lead_alerts_already_queued"
        audit_reason = "Internal SMS alerts already existed for every eligible staff recipient."
    else:
        audit_action = "communication.staff_lead_alerts_not_queued"
        audit_reason = f"No internal SMS alert could be queued for this {source_label} lead."
    db.add(
        AuditEvent(
            organization_id=lead.organization_id,
            actor_user_id=None,
            actor_type="system",
            action=audit_action,
            entity_type=source_entity_type,
            entity_id=source_event_id,
            previous_value=None,
            new_value=queue_snapshot,
            reason=audit_reason,
        )
    )
    log = logger.info if created or existing_count else logger.warning
    log("staff_lead_alert_queue_evaluated", **queue_snapshot)
    if not created and not existing_count:
        record_staff_alert_queue_gap(
            db,
            lead=lead,
            source_type=source_type,
            source_event_id=source_event_id,
            source_label=source_label,
        )
    db.flush()
    return created


def record_staff_alert_queue_gap(
    db: Session,
    *,
    lead: Lead,
    source_type: str,
    source_event_id: UUID,
    source_label: str,
) -> None:
    event_type = "lead.staff_sms_alert_not_queued"
    existing_activity = db.scalar(
        select(ActivityEvent.id).where(
            ActivityEvent.organization_id == lead.organization_id,
            ActivityEvent.entity_type == "lead",
            ActivityEvent.entity_id == lead.id,
            ActivityEvent.event_type == event_type,
        )
    )
    if existing_activity is None:
        db.add(
            ActivityEvent(
                organization_id=lead.organization_id,
                actor_user_id=None,
                entity_type="lead",
                entity_id=lead.id,
                event_type=event_type,
                summary=(
                    "Internal new-lead SMS was not queued because no active opted-in staff "
                    "cellphone was eligible."
                ),
            )
        )
    if lead.assigned_user_id is None:
        return
    dedupe_key = f"staff-lead-alert-gap:{source_type}:{source_event_id}"
    existing_notification = db.scalar(
        select(Notification.id).where(
            Notification.organization_id == lead.organization_id,
            Notification.recipient_user_id == lead.assigned_user_id,
            Notification.dedupe_key == dedupe_key,
        )
    )
    if existing_notification is None:
        db.add(
            Notification(
                organization_id=lead.organization_id,
                recipient_user_id=lead.assigned_user_id,
                notification_type="staff_lead_alert_not_queued",
                title="New lead text alert was not queued",
                body=(
                    f"This {source_label} lead reached the CRM, but no active opted-in staff "
                    "cellphone was eligible for the internal SMS alert."
                ),
                entity_type="lead",
                entity_id=lead.id,
                action_url=f"/os/leads/{lead.id}",
                dedupe_key=dedupe_key,
                read_at=None,
            )
        )


def recover_recent_unalerted_website_lead(db: Session) -> int:
    ready_recipients, _diagnostics = eligible_staff_alert_recipients(db)
    recipient_ids_by_organization: dict[UUID, set[UUID]] = {}
    for recipient in ready_recipients:
        recipient_ids_by_organization.setdefault(recipient.organization_id, set()).add(
            recipient.id
        )
    if not recipient_ids_by_organization:
        return 0

    submissions = list(
        db.scalars(
            select(LeadFormSubmission)
            .where(
                LeadFormSubmission.created_at
                >= datetime.now(UTC) - STAFF_ALERT_RECOVERY_WINDOW
            )
            .order_by(LeadFormSubmission.created_at, LeadFormSubmission.id)
            .limit(250)
        ).all()
    )
    for submission in submissions:
        raw_payload = submission.raw_payload or {}
        if raw_payload.get("_intake_source") != "seller_website":
            continue
        if raw_payload.get("_matched_existing_lead") is not False:
            continue
        recipient_ids = recipient_ids_by_organization.get(submission.organization_id, set())
        if not recipient_ids:
            continue
        existing_recipient_ids = set(
            db.scalars(
                select(StaffLeadAlert.recipient_user_id).where(
                    StaffLeadAlert.organization_id == submission.organization_id,
                    StaffLeadAlert.source_type == "website_form",
                    StaffLeadAlert.source_event_id == submission.id,
                    StaffLeadAlert.recipient_user_id.in_(recipient_ids),
                )
            ).all()
        )
        if recipient_ids <= existing_recipient_ids:
            continue
        lead = db.get(Lead, submission.lead_id)
        if (
            lead is None
            or lead.archived_at is not None
            or lead.stage_key in INACTIVE_LEAD_STAGES
        ):
            continue
        created = queue_staff_lead_alerts_for_lead(
            db,
            lead=lead,
            source_type="website_form",
            source_event_id=submission.id,
            source_label="Website",
            source_entity_type="lead_form_submission",
        )
        if created:
            db.commit()
            logger.warning(
                "staff_lead_alert_missing_rows_recovered",
                source_type="website_form",
                source_event_id=str(submission.id),
                lead_id=str(lead.id),
                alerts_created=created,
                recovery_window_hours=int(
                    STAFF_ALERT_RECOVERY_WINDOW.total_seconds() // 3600
                ),
            )
            return created
    return 0
