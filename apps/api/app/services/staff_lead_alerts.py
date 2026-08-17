from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Literal
from uuid import UUID

import structlog
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.foundation import (
    ActivityEvent,
    AuditEvent,
    CommunicationRecord,
    Contact,
    ContactMethod,
    Conversation,
    Lead,
    LeadFormSubmission,
    Notification,
    Property,
    Role,
    RoleAssignment,
    StaffLeadAlert,
    Team,
    TeamMembership,
    User,
    VoiceLine,
)
from app.services.communication_compliance import format_e164
from app.services.lead_lifecycle import INACTIVE_LEAD_STAGES

logger = structlog.get_logger()
STAFF_ALERT_RECOVERY_WINDOW = timedelta(hours=24)
OWNER_ROLE_KEYS = {"owner", "founder_operator", "ceo"}
WEBSITE_STAGE_1_ALERT_SOURCE_TYPE = "website_form_stage_1"
WEBSITE_STAGE_2_ALERT_SOURCE_TYPE = "website_form"
WEBSITE_STAGE_ALERT_FLOW_VERSION = "website-staged-alerts-v1"


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
    return _ready_staff_alert_recipients(opted_in)


def eligible_staff_inbound_message_alert_recipients(
    db: Session,
    *,
    organization_id: UUID | None = None,
) -> tuple[list[User], StaffAlertRecipientDiagnostics]:
    statement = select(User).where(
        User.is_active.is_(True),
        User.inbound_message_alert_sms_enabled.is_(True),
    )
    if organization_id is not None:
        statement = statement.where(User.organization_id == organization_id)
    opted_in = list(db.scalars(statement).all())
    return _ready_staff_alert_recipients(opted_in)


def _ready_staff_alert_recipients(
    opted_in: list[User],
) -> tuple[list[User], StaffAlertRecipientDiagnostics]:
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
    message_body: str | None = None,
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
            property_record.city or property_record.county or property_record.state
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
                message_body=message_body
                or (
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


def queue_website_stage_lead_alerts(
    db: Session,
    *,
    lead: Lead,
    submission: LeadFormSubmission,
    stage: Literal[1, 2],
) -> int:
    """Queue one durable, idempotent website-stage SMS per eligible employee."""
    property_record = db.get(Property, lead.property_id)
    property_address = format_property_address(property_record)
    if stage == 1:
        source_type = WEBSITE_STAGE_1_ALERT_SOURCE_TYPE
        message_body = (
            f"Stonegate Stage 1 filled: {property_address}. Address only; no contact details "
            "or permission yet. "
            "https://www.stonegatehb.com/os/leads?view=address_only"
        )
    else:
        source_type = WEBSITE_STAGE_2_ALERT_SOURCE_TYPE
        contact = db.get(Contact, lead.contact_id)
        contact_name = (
            " ".join(contact.legal_name.split())[:100]
            if contact is not None and contact.legal_name.strip()
            else "Seller"
        )
        submitted_phone = (submission.raw_payload or {}).get("phone")
        if not isinstance(submitted_phone, str) or not submitted_phone.strip():
            phone_method = db.scalar(
                select(ContactMethod)
                .where(
                    ContactMethod.organization_id == lead.organization_id,
                    ContactMethod.contact_id == lead.contact_id,
                    ContactMethod.method_type == "phone",
                )
                .order_by(
                    ContactMethod.is_primary.desc(),
                    ContactMethod.created_at.desc(),
                    ContactMethod.id,
                )
            )
            stored_phone = (
                phone_method.normalized_value or phone_method.value
                if phone_method is not None
                else None
            )
        else:
            stored_phone = submitted_phone
        phone = format_e164(stored_phone or "") or stored_phone or "phone unavailable"
        message_body = (
            f"Stonegate Stage 2 filled: {contact_name}, {phone}, {property_address}. "
            f"Contact details received. https://www.stonegatehb.com/os/leads/{lead.id}"
        )
    # A rolling deploy may encounter an older pending website alert with the same
    # durable Stage 2 identity. Refresh only unsent snapshots; never rewrite the
    # evidence for a message that already left Stonegate.
    for existing_alert in db.scalars(
        select(StaffLeadAlert).where(
            StaffLeadAlert.organization_id == lead.organization_id,
            StaffLeadAlert.source_type == source_type,
            StaffLeadAlert.source_event_id == submission.id,
            StaffLeadAlert.status.in_({"pending", "retry", "blocked"}),
        )
    ):
        existing_alert.message_body = message_body
    return queue_staff_lead_alerts_for_lead(
        db,
        lead=lead,
        source_type=source_type,
        source_event_id=submission.id,
        source_label=f"Website Stage {stage}",
        source_entity_type="lead_form_submission",
        message_body=message_body,
    )


def format_property_address(property_record: Property | None) -> str:
    if property_record is None:
        return "address unavailable"
    city_state_zip = " ".join(
        compact_sms_value(part, 20)
        for part in (property_record.state, property_record.postal_code)
        if part
    )
    locality = ", ".join(
        part
        for part in (compact_sms_value(property_record.city, 80), city_state_zip)
        if part
    )
    return ", ".join(
        part
        for part in (compact_sms_value(property_record.street_address, 140), locality)
        if part
    ) or "address unavailable"


def compact_sms_value(value: str | None, limit: int) -> str:
    return " ".join((value or "").split())[:limit]


def queue_staff_inbound_sms_alert(
    db: Session,
    *,
    communication: CommunicationRecord,
    conversation: Conversation,
    sender_line: VoiceLine | None,
    sender_phone: str,
) -> int:
    existing = db.scalar(
        select(StaffLeadAlert.id).where(
            StaffLeadAlert.organization_id == conversation.organization_id,
            StaffLeadAlert.source_type == "inbound_sms",
            StaffLeadAlert.source_event_id == communication.id,
        )
    )
    if existing is not None:
        return 0

    recipient, routing_snapshot = select_inbound_sms_alert_recipient(
        db,
        conversation=conversation,
        sender_line=sender_line,
        sender_phone=sender_phone,
    )
    contact = db.get(Contact, conversation.contact_id)
    party_label = "buyer" if conversation.conversation_type == "buyer" else "seller"
    contact_name = (
        " ".join(contact.legal_name.split())[:80]
        if contact is not None and contact.legal_name.strip()
        else "Unknown contact"
    )
    created = 0
    if recipient is not None:
        recipient_phone = format_e164(recipient.voice_forwarding_number or "")
        assert recipient_phone is not None
        db.add(
            StaffLeadAlert(
                organization_id=conversation.organization_id,
                meta_lead_event_id=None,
                source_type="inbound_sms",
                source_event_id=communication.id,
                lead_id=conversation.lead_id,
                conversation_id=conversation.id,
                recipient_user_id=recipient.id,
                recipient_phone=recipient_phone,
                message_body=(
                    f"New {party_label} text from {contact_name}. "
                    "Alert only - reply in Stonegate: "
                    f"https://www.stonegatehb.com/os/inbox?conversation={conversation.id}"
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
        created = 1

    queue_snapshot = {
        "communication_id": str(communication.id),
        "conversation_id": str(conversation.id),
        "lead_id": str(conversation.lead_id) if conversation.lead_id is not None else None,
        "recipient_user_id": str(recipient.id) if recipient is not None else None,
        **routing_snapshot,
    }
    db.add(
        AuditEvent(
            organization_id=conversation.organization_id,
            actor_user_id=None,
            actor_type="system",
            action=(
                "communication.staff_inbound_sms_alert_queued"
                if created
                else "communication.staff_inbound_sms_alert_not_queued"
            ),
            entity_type="communication_record",
            entity_id=communication.id,
            previous_value=None,
            new_value=queue_snapshot,
            reason=(
                "Queued a private cellphone alert for the responsible staff member."
                if created
                else "No active opted-in staff cellphone was eligible for this inbound SMS."
            ),
        )
    )
    log = logger.info if created else logger.warning
    log(
        "staff_inbound_sms_alert_queue_evaluated",
        alerts_created=created,
        **queue_snapshot,
    )
    db.flush()
    return created


def select_inbound_sms_alert_recipient(
    db: Session,
    *,
    conversation: Conversation,
    sender_line: VoiceLine | None,
    sender_phone: str,
) -> tuple[User | None, dict[str, object]]:
    candidates: list[tuple[UUID | None, str]] = [
        (conversation.assigned_user_id, "conversation_owner"),
    ]
    if sender_line is not None:
        candidates.append((sender_line.assigned_user_id, "line_primary_owner"))
        if sender_line.assigned_team_id is not None:
            team = db.get(Team, sender_line.assigned_team_id)
            if team is not None and team.is_active:
                candidates.append((team.manager_user_id, "line_team_manager"))
            candidates.extend(
                (user_id, "line_team_member")
                for user_id in db.scalars(
                    select(TeamMembership.user_id)
                    .join(User, User.id == TeamMembership.user_id)
                    .where(
                        TeamMembership.organization_id == conversation.organization_id,
                        TeamMembership.team_id == sender_line.assigned_team_id,
                        User.is_active.is_(True),
                    )
                    .order_by(
                        (TeamMembership.membership_role == "manager").desc(),
                        TeamMembership.created_at.asc(),
                    )
                ).all()
            )
        candidates.append((sender_line.fallback_user_id, "line_fallback_owner"))
    candidates.extend(
        (user_id, "organization_owner")
        for user_id in db.scalars(
            select(User.id)
            .join(RoleAssignment, RoleAssignment.user_id == User.id)
            .join(Role, Role.id == RoleAssignment.role_id)
            .where(
                User.organization_id == conversation.organization_id,
                User.is_active.is_(True),
                Role.key.in_(OWNER_ROLE_KEYS),
            )
            .order_by(User.created_at.asc())
        ).all()
    )

    sender_normalized = format_e164(sender_phone)
    seen: set[UUID] = set()
    checked = 0
    opted_out = 0
    missing_or_invalid_phone = 0
    for candidate_id, route in candidates:
        if candidate_id is None or candidate_id in seen:
            continue
        seen.add(candidate_id)
        user = db.get(User, candidate_id)
        if (
            user is None
            or not user.is_active
            or user.organization_id != conversation.organization_id
        ):
            continue
        checked += 1
        if not user.inbound_message_alert_sms_enabled:
            opted_out += 1
            continue
        candidate_phone = format_e164(user.voice_forwarding_number)
        if candidate_phone is None or candidate_phone == sender_normalized:
            missing_or_invalid_phone += 1
            continue
        return user, {
            "candidate_recipients_checked": checked,
            "candidate_recipients_opted_out": opted_out,
            "candidate_recipients_without_usable_phone": missing_or_invalid_phone,
            "routing_result": route,
        }
    return None, {
        "candidate_recipients_checked": checked,
        "candidate_recipients_opted_out": opted_out,
        "candidate_recipients_without_usable_phone": missing_or_invalid_phone,
        "routing_result": "no_eligible_recipient",
    }


def is_staff_cellphone(
    db: Session,
    *,
    organization_id: UUID,
    phone_number: str,
) -> bool:
    normalized = format_e164(phone_number)
    if normalized is None:
        return False
    users = db.scalars(
        select(User).where(
            User.organization_id == organization_id,
            User.is_active.is_(True),
            User.voice_forwarding_number.is_not(None),
        )
    ).all()
    return any(format_e164(user.voice_forwarding_number) == normalized for user in users)


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
        recipient_ids_by_organization.setdefault(recipient.organization_id, set()).add(recipient.id)
    if not recipient_ids_by_organization:
        return 0

    intake_activity_at = func.coalesce(
        LeadFormSubmission.completed_at,
        LeadFormSubmission.created_at,
    )
    submissions = list(
        db.scalars(
            select(LeadFormSubmission)
            .where(
                LeadFormSubmission.completion_status.in_({"address_only", "completed"}),
                intake_activity_at >= datetime.now(UTC) - STAFF_ALERT_RECOVERY_WINDOW,
            )
            .order_by(intake_activity_at, LeadFormSubmission.id)
            .limit(250)
        ).all()
    )
    for submission in submissions:
        raw_payload = submission.raw_payload or {}
        if raw_payload.get("_intake_source") != "seller_website":
            continue
        if submission.completion_status == "address_only":
            if raw_payload.get("_staff_alert_flow_version") != WEBSITE_STAGE_ALERT_FLOW_VERSION:
                continue
            stages: tuple[Literal[1, 2], ...] = (1,)
        else:
            # Legacy website submissions without an attempt ID only represented a
            # new lead when this flag was false. Attempt-aware submissions represent
            # renewed seller intent even when they resolve to an existing CRM lead.
            if (
                submission.intake_attempt_id is None
                and raw_payload.get("_matched_existing_lead") is not False
            ):
                continue
            stages = (
                (1, 2)
                if raw_payload.get("_staff_alert_flow_version")
                == WEBSITE_STAGE_ALERT_FLOW_VERSION
                and submission.intake_attempt_id is not None
                else (2,)
            )
        recipient_ids = recipient_ids_by_organization.get(submission.organization_id, set())
        if not recipient_ids:
            continue
        lead = db.get(Lead, submission.lead_id)
        if lead is None or lead.archived_at is not None or lead.stage_key in INACTIVE_LEAD_STAGES:
            continue
        for stage in stages:
            source_type = (
                WEBSITE_STAGE_1_ALERT_SOURCE_TYPE
                if stage == 1
                else WEBSITE_STAGE_2_ALERT_SOURCE_TYPE
            )
            existing_recipient_ids = set(
                db.scalars(
                    select(StaffLeadAlert.recipient_user_id).where(
                        StaffLeadAlert.organization_id == submission.organization_id,
                        StaffLeadAlert.source_type == source_type,
                        StaffLeadAlert.source_event_id == submission.id,
                        StaffLeadAlert.recipient_user_id.in_(recipient_ids),
                    )
                ).all()
            )
            if recipient_ids <= existing_recipient_ids:
                continue
            created = queue_website_stage_lead_alerts(
                db,
                lead=lead,
                submission=submission,
                stage=stage,
            )
            if created:
                db.commit()
                logger.warning(
                    "staff_lead_alert_missing_rows_recovered",
                    source_type=source_type,
                    website_stage=stage,
                    source_event_id=str(submission.id),
                    lead_id=str(lead.id),
                    alerts_created=created,
                    recovery_window_hours=int(
                        STAFF_ALERT_RECOVERY_WINDOW.total_seconds() // 3600
                    ),
                )
                return created
    return 0
