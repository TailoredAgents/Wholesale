import hashlib
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session

from app.core.auth import Principal
from app.core.config import Settings, get_settings
from app.domain.rbac import PermissionKeys
from app.integrations.communications import (
    OutboundMessageRequest,
    SimulatedCommunicationProvider,
)
from app.integrations.twilio_media import twilio_inbound_media_count
from app.integrations.twilio_messaging import (
    TwilioMessagingError,
    get_twilio_messaging_provider,
)
from app.models.foundation import (
    ActivityEvent,
    AuditEvent,
    CommunicationDispatch,
    CommunicationProviderEvent,
    CommunicationRecord,
    ConsentRecord,
    Contact,
    ContactMethod,
    Conversation,
    ConversationContextLink,
    Lead,
    Organization,
    StaffLeadAlert,
    SuppressionRecord,
    TeamMembership,
    VoiceLine,
)
from app.schemas.inbox import SmsSendRead, SmsSendRequest
from app.services.communication_compliance import (
    evaluate_sms_eligibility,
    format_e164,
    phone_lookup_values,
)
from app.services.inbound_contacts import create_unknown_inbound_sms_conversation
from app.services.inbox import get_scoped_conversation, update_conversation_activity
from app.services.lead_lifecycle import (
    LeadLifecycleConflictError,
    lock_organization_lead,
    require_lead_open_for_work,
)
from app.services.staff_lead_alerts import (
    is_staff_cellphone,
    queue_staff_inbound_sms_alert,
)

STOP_WORDS = {"cancel", "end", "quit", "stop", "stopall", "unsubscribe"}
START_WORDS = {"start", "unstop"}
TWILIO_MESSAGE_STATUS_RANK = {
    "pending": 0,
    "processing": 0,
    "retry": 0,
    "simulated": 5,
    "accepted": 10,
    "scheduled": 15,
    "queued": 20,
    "sending": 30,
    "sent": 40,
}
TWILIO_MESSAGE_TERMINAL_STATUSES = {
    "canceled",
    "delivered",
    "failed",
    "read",
    "undelivered",
}
TWILIO_STATUS_RECOVERY_MAX_ATTEMPTS = 6
TWILIO_STATUS_RECOVERY_ORPHANED = "orphaned"
TWILIO_STATUS_TENANT_RESOLUTION_KEY = "_tenant_resolution"


@dataclass(frozen=True)
class TwilioStatusRecoveryClaim:
    event_id: UUID
    processing_token: UUID | None


@dataclass(frozen=True)
class TwilioStatusTenantResolution:
    organization_id: UUID | None
    status: str
    candidate_organization_ids: tuple[UUID, ...]


class SmsComplianceError(RuntimeError):
    def __init__(self, blockers: tuple[str, ...]) -> None:
        super().__init__(" ".join(blockers))
        self.blockers = blockers


class SmsDispatchConflictError(RuntimeError):
    pass


class SmsConfigurationError(RuntimeError):
    pass


def send_conversation_sms(
    db: Session,
    principal: Principal,
    conversation_id: UUID,
    payload: SmsSendRequest,
) -> SmsSendRead | None:
    conversation = get_scoped_conversation(db, principal, conversation_id)
    if conversation is None:
        return None
    if PermissionKeys.SEND_SMS not in principal.permission_keys and (
        PermissionKeys.SEND_ASSIGNED_SMS not in principal.permission_keys
        or conversation.assigned_user_id != principal.user_id
    ):
        raise PermissionError("SMS can only be sent from an assigned conversation.")
    if conversation.conversation_type not in {"lead", "buyer"}:
        raise SmsConfigurationError("SMS is only available from seller and buyer conversations.")
    active_lead: Lead | None = None
    if conversation.conversation_type == "lead" and conversation.lead_id is not None:
        active_lead = lock_organization_lead(
            db,
            organization_id=principal.organization_id,
            lead_id=conversation.lead_id,
        )
        if active_lead is None:
            return None
        require_lead_open_for_work(active_lead)

    body = payload.body.strip()
    body_hash = hashlib.sha256(body.encode("utf-8")).hexdigest()
    existing_dispatch = db.scalar(
        select(CommunicationDispatch).where(
            CommunicationDispatch.organization_id == principal.organization_id,
            CommunicationDispatch.idempotency_key == payload.idempotency_key,
        )
    )
    if existing_dispatch is not None:
        if (
            existing_dispatch.conversation_id != conversation.id
            or existing_dispatch.request_body_hash != body_hash
        ):
            raise SmsDispatchConflictError(
                "The idempotency key was already used for a different SMS request."
            )
        if existing_dispatch.communication_record_id is not None:
            communication = db.get(
                CommunicationRecord,
                existing_dispatch.communication_record_id,
            )
            if communication is not None and communication.provider_message_id:
                return SmsSendRead(
                    communication_id=communication.id,
                    provider_message_id=communication.provider_message_id,
                    status=communication.status,
                    recipient=existing_dispatch.recipient,
                )
        raise SmsDispatchConflictError(
            f"This SMS request is already {existing_dispatch.status}; use a new request to retry."
        )

    lead = active_lead if conversation.conversation_type == "lead" else None
    contact = db.get(Contact, conversation.contact_id)
    if conversation.conversation_type == "lead" and lead is None:
        return None
    if contact is None:
        return None
    eligibility = evaluate_sms_eligibility(db, contact)
    if not eligibility.can_send or eligibility.recipient is None:
        raise SmsComplianceError(eligibility.blockers)

    settings = get_settings()
    provider_name = "simulated" if settings.communication_simulation_enabled else "twilio"
    sender_line = select_sms_sender_line(
        db,
        principal.organization_id,
        conversation=conversation,
    )
    sender_number = (
        sender_line.phone_number if sender_line is not None else settings.twilio_sms_from_number
    )
    if conversation.conversation_type == "buyer" and sender_line is None:
        raise SmsConfigurationError(
            "No active Stonegate dispositions line is configured for buyer SMS."
        )
    if (
        conversation.conversation_type == "buyer"
        and sender_line is not None
        and not user_can_use_line(
            db,
            sender_line,
            user_id=principal.user_id,
        )
    ):
        raise PermissionError("Buyer SMS requires assignment to the Stonegate dispositions line.")
    if not settings.communication_simulation_enabled and not sender_number:
        raise SmsConfigurationError(
            "No active Stonegate SMS line is configured for this conversation."
        )
    dispatch = CommunicationDispatch(
        organization_id=principal.organization_id,
        conversation_id=conversation.id,
        lead_id=lead.id if lead is not None else None,
        contact_id=contact.id,
        actor_user_id=principal.user_id,
        communication_record_id=None,
        idempotency_key=payload.idempotency_key,
        channel="sms",
        recipient=eligibility.recipient,
        request_body_hash=body_hash,
        status="pending",
        provider=provider_name,
        provider_message_id=None,
        error_code=None,
        error_message=None,
        completed_at=None,
        dispatch_metadata={
            "compliance_checked_at": datetime.now(UTC).isoformat(),
            "sender_number": sender_number,
            "voice_line_id": str(sender_line.id) if sender_line is not None else None,
        },
    )
    db.add(dispatch)
    db.commit()
    dispatch_id = dispatch.id

    if lead is not None:
        lead = lock_organization_lead(
            db,
            organization_id=principal.organization_id,
            lead_id=lead.id,
        )
        try:
            if lead is None:
                raise LeadLifecycleConflictError("The SMS seller lead is unavailable.")
            require_lead_open_for_work(lead)
        except LeadLifecycleConflictError:
            cancelled_dispatch = db.scalar(
                select(CommunicationDispatch)
                .where(CommunicationDispatch.id == dispatch_id)
                .with_for_update()
            )
            if cancelled_dispatch is not None and cancelled_dispatch.status == "pending":
                cancelled_dispatch.status = "cancelled"
                cancelled_dispatch.error_code = "lead_closed"
                cancelled_dispatch.error_message = (
                    "SMS cancelled because the seller lead was closed before provider delivery."
                )
                cancelled_dispatch.completed_at = datetime.now(UTC)
            db.commit()
            raise
        locked_conversation = db.scalar(
            select(Conversation)
            .where(
                Conversation.id == conversation.id,
                Conversation.organization_id == principal.organization_id,
            )
            .execution_options(populate_existing=True)
        )
        if locked_conversation is None:
            raise SmsConfigurationError("SMS conversation is unavailable.")
        conversation = locked_conversation
        locked_dispatch = db.scalar(
            select(CommunicationDispatch)
            .where(
                CommunicationDispatch.id == dispatch_id,
                CommunicationDispatch.status == "pending",
            )
            .with_for_update()
        )
        if locked_dispatch is None:
            raise SmsDispatchConflictError("The SMS dispatch is no longer pending.")

    if settings.communication_provider_mode == "disabled" or (
        not settings.communication_simulation_enabled and not settings.twilio_sms_configured
    ):
        mark_dispatch_failed(
            db,
            dispatch_id,
            error_code="configuration",
            error_message="Live Twilio SMS is not fully configured.",
        )
        raise SmsConfigurationError("Live Twilio SMS is not fully configured.")
    provider = (
        SimulatedCommunicationProvider()
        if settings.communication_simulation_enabled
        else get_twilio_messaging_provider()
    )
    try:
        result = provider.send(
            OutboundMessageRequest(
                lead_id=str(lead.id if lead is not None else conversation.id),
                contact_id=str(contact.id),
                channel="sms",
                recipient=eligibility.recipient,
                body=body,
                idempotency_key=payload.idempotency_key,
                metadata={
                    "conversation_id": str(conversation.id),
                    "sender_number": sender_number or "",
                    "voice_line_id": str(sender_line.id) if sender_line is not None else "",
                },
            ),
            dry_run=settings.communication_simulation_enabled,
        )
    except TwilioMessagingError as exc:
        mark_dispatch_failed(
            db,
            dispatch_id,
            error_code="provider_error",
            error_message=str(exc),
        )
        raise

    if not result.provider_message_id:
        mark_dispatch_failed(
            db,
            dispatch_id,
            error_code="missing_provider_id",
            error_message="Twilio accepted the request without a message identifier.",
        )
        raise TwilioMessagingError("Twilio did not return a message identifier.")

    occurred_at = datetime.now(UTC)
    communication = CommunicationRecord(
        organization_id=principal.organization_id,
        conversation_id=conversation.id,
        lead_id=lead.id if lead is not None else None,
        contact_id=contact.id,
        actor_user_id=principal.user_id,
        direction="outbound",
        channel="sms",
        status=result.status,
        provider=result.provider,
        provider_message_id=result.provider_message_id,
        subject=None,
        body=body,
        occurred_at=occurred_at,
        external_payload=result.raw_payload,
        communication_metadata={
            "source": "shared_inbox",
            "idempotency_key": payload.idempotency_key,
            "compliance_checked": True,
            "sender_number": sender_number,
            "voice_line_id": str(sender_line.id) if sender_line is not None else None,
        },
    )
    db.add(communication)
    db.flush()
    completed_dispatch = db.get(CommunicationDispatch, dispatch_id)
    if completed_dispatch is None:
        raise RuntimeError("SMS dispatch disappeared before completion.")
    completed_dispatch.communication_record_id = communication.id
    completed_dispatch.status = result.status
    completed_dispatch.provider_message_id = result.provider_message_id
    completed_dispatch.completed_at = occurred_at
    update_conversation_activity(
        conversation,
        direction="outbound",
        occurred_at=occurred_at,
        db=db,
    )
    entity_type, entity_id = conversation_activity_entity(db, conversation)
    db.add(
        ActivityEvent(
            organization_id=principal.organization_id,
            actor_user_id=principal.user_id,
            entity_type=entity_type,
            entity_id=entity_id,
            event_type=f"{entity_type}.sms_sent",
            summary=(
                "Outbound buyer SMS accepted for delivery."
                if entity_type == "buyer"
                else "Outbound seller SMS accepted for delivery."
            ),
        )
    )
    db.add(
        AuditEvent(
            organization_id=principal.organization_id,
            actor_user_id=principal.user_id,
            actor_type="user",
            action="communication.sms_send",
            entity_type="communication_record",
            entity_id=communication.id,
            previous_value=None,
            new_value={
                "conversation_id": str(conversation.id),
                "provider": result.provider,
                "provider_message_id": result.provider_message_id,
                "status": result.status,
                "recipient": eligibility.recipient,
            },
            reason="One-to-one SMS sent from shared inbox",
        )
    )
    db.commit()
    return SmsSendRead(
        communication_id=communication.id,
        provider_message_id=result.provider_message_id,
        status=result.status,
        recipient=eligibility.recipient,
    )


def mark_dispatch_failed(
    db: Session,
    dispatch_id: UUID,
    *,
    error_code: str,
    error_message: str,
) -> None:
    dispatch = db.get(CommunicationDispatch, dispatch_id)
    if dispatch is None:
        return
    dispatch.status = "failed"
    dispatch.error_code = error_code
    dispatch.error_message = error_message[:2000]
    dispatch.completed_at = datetime.now(UTC)
    db.commit()


def process_twilio_inbound(db: Session, payload: dict[str, str]) -> str:
    organization = get_default_organization(db)
    message_sid = required_twilio_value(payload, "MessageSid")
    event_id = f"inbound:{message_sid}"
    existing_event = get_provider_event(db, organization.id, event_id)
    if existing_event is not None:
        return existing_event.processing_status

    sender = required_twilio_value(payload, "From")
    recipient = required_twilio_value(payload, "To")
    body = payload.get("Body", "").strip()
    media_count = twilio_inbound_media_count(payload)
    opt_out_type = classify_opt_out(payload, body)
    sender_line = find_sms_line_by_number(db, organization.id, recipient)
    conversation_type = (
        "buyer"
        if sender_line is not None and sender_line.purpose_key == "buyer_relations"
        else "lead"
    )
    staff_sender = is_staff_cellphone(
        db,
        organization_id=organization.id,
        phone_number=sender,
    )
    conversation = (
        None
        if staff_sender
        else find_conversation_by_phone(
            db,
            organization.id,
            sender,
            conversation_type=conversation_type,
        )
    )
    event = CommunicationProviderEvent(
        organization_id=organization.id,
        conversation_id=conversation.id if conversation else None,
        provider="twilio",
        event_type="messaging.inbound",
        external_event_id=event_id,
        processing_status="received",
        payload=payload,
        received_at=datetime.now(UTC),
        processed_at=None,
        error_message=None,
    )
    db.add(event)
    db.flush()
    if staff_sender:
        event.processing_status = "ignored_staff_sender"
        event.processed_at = datetime.now(UTC)
        db.commit()
        return event.processing_status
    if conversation is None:
        if opt_out_type in {"STOP", "START"}:
            apply_sms_preference(
                db,
                organization_id=organization.id,
                contact=None,
                sender=sender,
                message_sid=message_sid,
                preference=opt_out_type,
            )
            event.processing_status = "compliance_applied"
            event.processed_at = datetime.now(UTC)
            db.commit()
            return event.processing_status
        if sender_line is None:
            event.processing_status = "unmatched"
            event.processed_at = datetime.now(UTC)
            db.commit()
            return event.processing_status
        if opt_out_type == "HELP":
            event.processing_status = "ignored_compliance_keyword"
            event.processed_at = datetime.now(UTC)
            db.commit()
            return event.processing_status
        conversation = create_unknown_inbound_sms_conversation(
            db,
            line=sender_line,
            sender=sender,
        )
        event.conversation_id = conversation.id

    lead = db.get(Lead, conversation.lead_id) if conversation.lead_id is not None else None
    contact = db.get(Contact, conversation.contact_id)
    if conversation.conversation_type == "lead" and lead is None:
        raise RuntimeError("Matched Twilio seller conversation is missing lead context.")
    if contact is None:
        raise RuntimeError("Matched Twilio conversation is missing contact context.")
    occurred_at = datetime.now(UTC)
    communication = CommunicationRecord(
        organization_id=organization.id,
        conversation_id=conversation.id,
        lead_id=lead.id if lead is not None else None,
        contact_id=contact.id,
        actor_user_id=None,
        direction="inbound",
        channel="sms",
        status="received",
        provider="twilio",
        provider_message_id=message_sid,
        subject=None,
        body=body,
        occurred_at=occurred_at,
        external_payload={
            "from": sender,
            "to": recipient,
            "messaging_service_sid": payload.get("MessagingServiceSid"),
            "opt_out_type": opt_out_type,
            "voice_line_id": str(sender_line.id) if sender_line is not None else None,
            "department_key": sender_line.department_key if sender_line is not None else None,
            "media_count": media_count,
        },
        communication_metadata={
            "source": "twilio_webhook",
            "sender_number": recipient,
            "voice_line_id": str(sender_line.id) if sender_line is not None else None,
            "media_count": media_count,
        },
    )
    db.add(communication)
    db.flush()
    update_conversation_activity(
        conversation,
        direction="inbound",
        occurred_at=occurred_at,
        db=db,
        reactivate_closed_lead=opt_out_type not in {"STOP", "START"},
    )
    if opt_out_type in {"STOP", "START"}:
        apply_sms_preference(
            db,
            organization_id=organization.id,
            contact=contact,
            sender=sender,
            message_sid=message_sid,
            preference=opt_out_type,
        )
    entity_type, entity_id = conversation_activity_entity(db, conversation)
    party_label = "buyer" if entity_type == "buyer" else "seller"
    db.add(
        ActivityEvent(
            organization_id=organization.id,
            actor_user_id=None,
            entity_type=entity_type,
            entity_id=entity_id,
            event_type=f"{entity_type}.sms_received",
            summary=(
                f"Inbound {party_label} SMS received ({opt_out_type})."
                if opt_out_type
                else (
                    f"Inbound {party_label} MMS received with {media_count} photo(s)."
                    if media_count
                    else f"Inbound {party_label} SMS received."
                )
            ),
        )
    )
    if opt_out_type not in {"STOP", "START", "HELP"}:
        queue_staff_inbound_sms_alert(
            db,
            communication=communication,
            conversation=conversation,
            sender_line=sender_line,
            sender_phone=sender,
        )
    event.processing_status = "media_pending" if media_count else "processed"
    event.processed_at = None if media_count else datetime.now(UTC)
    db.commit()
    return event.processing_status


def resolve_twilio_status_tenant(
    db: Session,
    payload: dict[str, object],
) -> TwilioStatusTenantResolution:
    message_sid = required_twilio_value(payload, "MessageSid")
    provider_organization_ids = set(
        db.scalars(
            select(CommunicationRecord.organization_id).where(
                CommunicationRecord.provider == "twilio",
                CommunicationRecord.provider_message_id == message_sid,
            )
        ).all()
    )
    provider_organization_ids.update(
        db.scalars(
            select(CommunicationDispatch.organization_id).where(
                CommunicationDispatch.provider == "twilio",
                CommunicationDispatch.provider_message_id == message_sid,
            )
        ).all()
    )
    provider_organization_ids.update(
        db.scalars(
            select(StaffLeadAlert.organization_id).where(
                StaffLeadAlert.provider_message_id == message_sid,
            )
        ).all()
    )
    provider_candidates = sorted_organization_ids(provider_organization_ids)
    if len(provider_candidates) == 1:
        return TwilioStatusTenantResolution(
            organization_id=provider_candidates[0],
            status="resolved_provider_message",
            candidate_organization_ids=provider_candidates,
        )
    if len(provider_candidates) > 1:
        return TwilioStatusTenantResolution(
            organization_id=None,
            status="ambiguous_provider_message",
            candidate_organization_ids=provider_candidates,
        )

    sender_candidates = twilio_voice_line_organization_ids(db, payload.get("From"))
    if len(sender_candidates) == 1:
        return TwilioStatusTenantResolution(
            organization_id=sender_candidates[0],
            status="resolved_sender_line",
            candidate_organization_ids=sender_candidates,
        )
    if len(sender_candidates) > 1:
        return TwilioStatusTenantResolution(
            organization_id=None,
            status="ambiguous_sender_line",
            candidate_organization_ids=sender_candidates,
        )

    recipient_candidates = twilio_voice_line_organization_ids(db, payload.get("To"))
    if len(recipient_candidates) == 1:
        return TwilioStatusTenantResolution(
            organization_id=recipient_candidates[0],
            status="resolved_recipient_line",
            candidate_organization_ids=recipient_candidates,
        )
    if len(recipient_candidates) > 1:
        return TwilioStatusTenantResolution(
            organization_id=None,
            status="ambiguous_recipient_line",
            candidate_organization_ids=recipient_candidates,
        )
    return TwilioStatusTenantResolution(
        organization_id=None,
        status="unresolved",
        candidate_organization_ids=(),
    )


def twilio_voice_line_organization_ids(
    db: Session,
    value: object | None,
) -> tuple[UUID, ...]:
    normalized_phone = format_e164(str(value)) if value is not None else None
    if normalized_phone is None:
        return ()
    active_lines = db.execute(
        select(VoiceLine.organization_id, VoiceLine.phone_number).where(
            VoiceLine.provider == "twilio",
            VoiceLine.status == "active",
        )
    ).all()
    return sorted_organization_ids(
        organization_id
        for organization_id, phone_number in active_lines
        if format_e164(phone_number) == normalized_phone
    )


def sorted_organization_ids(organization_ids: Iterable[UUID]) -> tuple[UUID, ...]:
    return tuple(sorted(set(organization_ids), key=str))


def twilio_status_payload_with_tenant_resolution(
    payload: dict[str, object],
    resolution: TwilioStatusTenantResolution,
) -> dict[str, object]:
    return {
        **payload,
        TWILIO_STATUS_TENANT_RESOLUTION_KEY: {
            "status": resolution.status,
            "organization_id": (
                str(resolution.organization_id)
                if resolution.organization_id is not None
                else None
            ),
            "candidate_organization_ids": [
                str(organization_id)
                for organization_id in resolution.candidate_organization_ids
            ],
            "storage_only": resolution.organization_id is None,
        },
    }


def refresh_twilio_status_tenant_resolution(
    db: Session,
    event: CommunicationProviderEvent,
) -> UUID | None:
    resolution = resolve_twilio_status_tenant(db, event.payload)
    event.payload = twilio_status_payload_with_tenant_resolution(
        event.payload,
        resolution,
    )
    if resolution.organization_id is None:
        return None
    if event.organization_id != resolution.organization_id:
        event.conversation_id = None
    event.organization_id = resolution.organization_id
    return resolution.organization_id


def twilio_status_recovery_error_message(event: CommunicationProviderEvent) -> str:
    tenant_metadata = event.payload.get(TWILIO_STATUS_TENANT_RESOLUTION_KEY)
    resolution_status = (
        tenant_metadata.get("status") if isinstance(tenant_metadata, dict) else None
    )
    if isinstance(resolution_status, str) and resolution_status.startswith("ambiguous_"):
        return (
            "Twilio status callback tenant resolution is ambiguous; no tenant records "
            "were changed."
        )
    if resolution_status == "unresolved":
        return (
            "Twilio status callback tenant is unresolved; no tenant records were changed."
        )
    return (
        "Twilio status callback arrived before its outbound message record was committed."
    )


def process_twilio_status(db: Session, payload: dict[str, str]) -> str:
    message_sid = required_twilio_value(payload, "MessageSid")
    message_status = required_twilio_value(payload, "MessageStatus").lower()
    callback_error_code = payload.get("ErrorCode") or None
    event_error_code = callback_error_code or "none"
    event_id = f"status:{message_sid}:{message_status}:{event_error_code}"
    existing_event = get_twilio_status_provider_event(db, event_id)
    if existing_event is not None:
        return existing_event.processing_status

    tenant_resolution = resolve_twilio_status_tenant(db, payload)
    if tenant_resolution.organization_id is not None:
        organization = db.get(Organization, tenant_resolution.organization_id)
        if organization is None:
            raise RuntimeError("Twilio status callback resolved to a missing organization.")
    else:
        # CommunicationProviderEvent currently requires an organization. The default
        # organization is custody only for an unresolved callback; the routing metadata
        # prevents this event from mutating any tenant record until a unique binding exists.
        organization = get_default_organization(db)

    event = CommunicationProviderEvent(
        organization_id=organization.id,
        conversation_id=None,
        provider="twilio",
        event_type="messaging.status",
        external_event_id=event_id,
        processing_status="received",
        payload=twilio_status_payload_with_tenant_resolution(
            payload,
            tenant_resolution,
        ),
        received_at=datetime.now(UTC),
        processed_at=None,
        error_message=None,
    )
    db.add(event)
    db.flush()
    if not apply_twilio_status_event(db, event):
        event.processing_status = "unmatched"
        event.error_message = twilio_status_recovery_error_message(event)
    else:
        event.processing_status = "processed"
        event.error_message = None
    event.processed_at = datetime.now(UTC) if event.processing_status == "processed" else None
    db.commit()
    return event.processing_status


def process_next_twilio_status_recovery(
    db: Session,
    settings: Settings,
) -> UUID | None:
    claim = claim_next_twilio_status_event(db, settings)
    if claim is None:
        return None
    if claim.processing_token is None:
        return claim.event_id
    try:
        event = require_twilio_status_recovery_claim(db, claim)
        if apply_twilio_status_event(db, event):
            complete_twilio_status_recovery(event)
        else:
            defer_or_orphan_twilio_status_event(
                event,
                settings,
                error_message=twilio_status_recovery_error_message(event),
            )
        db.commit()
    except Exception as exc:
        db.rollback()
        record_twilio_status_recovery_failure(db, claim, exc, settings)
        raise
    return claim.event_id


def claim_next_twilio_status_event(
    db: Session,
    settings: Settings,
) -> TwilioStatusRecoveryClaim | None:
    now = datetime.now(UTC)
    stale_before = now - timedelta(seconds=settings.worker_operation_stall_seconds)
    event = db.scalar(
        select(CommunicationProviderEvent)
        .where(
            CommunicationProviderEvent.provider == "twilio",
            CommunicationProviderEvent.event_type == "messaging.status",
            or_(
                CommunicationProviderEvent.processing_status == "unmatched",
                and_(
                    CommunicationProviderEvent.processing_status == "retry",
                    or_(
                        CommunicationProviderEvent.next_attempt_at.is_(None),
                        CommunicationProviderEvent.next_attempt_at <= now,
                    ),
                ),
                and_(
                    CommunicationProviderEvent.processing_status == "processing",
                    or_(
                        CommunicationProviderEvent.processing_started_at.is_(None),
                        CommunicationProviderEvent.processing_started_at <= stale_before,
                    ),
                ),
            ),
        )
        .order_by(CommunicationProviderEvent.received_at.asc())
        .limit(1)
        .with_for_update(skip_locked=True)
    )
    if event is None:
        return None
    if event.attempt_count >= TWILIO_STATUS_RECOVERY_MAX_ATTEMPTS:
        mark_twilio_status_event_orphaned(
            event,
            now=now,
            error_message=(
                event.error_message
                or "Twilio status recovery exhausted without a matching outbound message."
            ),
        )
        db.commit()
        return TwilioStatusRecoveryClaim(event_id=event.id, processing_token=None)
    processing_token = uuid4()
    event.processing_status = "processing"
    event.processing_started_at = now
    event.processing_token = processing_token
    event.processed_at = None
    event.next_attempt_at = None
    event.attempt_count += 1
    event.error_message = None
    db.commit()
    return TwilioStatusRecoveryClaim(
        event_id=event.id,
        processing_token=processing_token,
    )


def require_twilio_status_recovery_claim(
    db: Session,
    claim: TwilioStatusRecoveryClaim,
) -> CommunicationProviderEvent:
    if claim.processing_token is None:
        raise RuntimeError("A terminal Twilio status event has no active recovery lease.")
    event = db.scalar(
        select(CommunicationProviderEvent)
        .where(
            CommunicationProviderEvent.id == claim.event_id,
            CommunicationProviderEvent.provider == "twilio",
            CommunicationProviderEvent.event_type == "messaging.status",
            CommunicationProviderEvent.processing_status == "processing",
            CommunicationProviderEvent.processing_token == claim.processing_token,
        )
        .with_for_update()
    )
    if event is None:
        raise RuntimeError("The Twilio status recovery lease was lost.")
    return event


def apply_twilio_status_event(
    db: Session,
    event: CommunicationProviderEvent,
) -> bool:
    organization_id = refresh_twilio_status_tenant_resolution(db, event)
    if organization_id is None:
        event.conversation_id = None
        return False
    message_sid = required_twilio_value(event.payload, "MessageSid")
    message_status = required_twilio_value(event.payload, "MessageStatus").lower()
    error_code = event.payload.get("ErrorCode") or None
    error_message = event.payload.get("ErrorMessage") or None
    communication = db.scalar(
        select(CommunicationRecord).where(
            CommunicationRecord.organization_id == organization_id,
            CommunicationRecord.provider == "twilio",
            CommunicationRecord.provider_message_id == message_sid,
        )
    )
    staff_alert = db.scalar(
        select(StaffLeadAlert).where(
            StaffLeadAlert.organization_id == organization_id,
            StaffLeadAlert.provider_message_id == message_sid,
        )
    )
    if communication is None and staff_alert is None:
        return False
    now = datetime.now(UTC)
    if staff_alert is not None:
        event.conversation_id = staff_alert.conversation_id
        if should_apply_twilio_message_status(staff_alert.status, message_status):
            staff_alert.status = message_status
            staff_alert.last_error = error_message or (
                f"Twilio error {error_code}" if error_code else None
            )
            staff_alert.provider_response = {
                **(staff_alert.provider_response or {}),
                "message_status": message_status,
                "error_code": error_code,
                "error_message": error_message,
            }
            if message_status == "delivered":
                staff_alert.delivered_at = now
        else:
            staff_alert.provider_response = {
                **(staff_alert.provider_response or {}),
                "last_ignored_status_callback": {
                    "message_status": message_status,
                    "error_code": error_code,
                    "error_message": error_message,
                },
            }
        return True

    assert communication is not None
    event.conversation_id = communication.conversation_id
    if should_apply_twilio_message_status(communication.status, message_status):
        communication.status = message_status
        communication.external_payload = {
            **(communication.external_payload or {}),
            "message_status": message_status,
            "error_code": error_code,
            "error_message": error_message,
        }
    else:
        communication.external_payload = {
            **(communication.external_payload or {}),
            "last_ignored_status_callback": {
                "message_status": message_status,
                "error_code": error_code,
                "error_message": error_message,
            },
        }
    dispatch = db.scalar(
        select(CommunicationDispatch).where(
            CommunicationDispatch.organization_id == organization_id,
            CommunicationDispatch.provider == "twilio",
            CommunicationDispatch.provider_message_id == message_sid,
        )
    )
    if dispatch is not None and should_apply_twilio_message_status(
        dispatch.status,
        message_status,
    ):
        dispatch.status = message_status
        dispatch.error_code = error_code
        dispatch.error_message = error_message
        dispatch.completed_at = now
    return True


def complete_twilio_status_recovery(event: CommunicationProviderEvent) -> None:
    event.processing_status = "processed"
    event.processing_started_at = None
    event.processing_token = None
    event.next_attempt_at = None
    event.processed_at = datetime.now(UTC)
    event.error_message = None


def defer_or_orphan_twilio_status_event(
    event: CommunicationProviderEvent,
    settings: Settings,
    *,
    error_message: str,
) -> None:
    now = datetime.now(UTC)
    if event.attempt_count >= TWILIO_STATUS_RECOVERY_MAX_ATTEMPTS:
        mark_twilio_status_event_orphaned(
            event,
            now=now,
            error_message=error_message,
        )
        return
    retry_delay = min(
        settings.worker_retry_base_seconds * (2 ** max(0, event.attempt_count - 1)),
        settings.worker_retry_max_seconds,
    )
    event.processing_status = "retry"
    event.processing_started_at = None
    event.processing_token = None
    event.next_attempt_at = now + timedelta(seconds=retry_delay)
    event.processed_at = None
    event.error_message = error_message[:2000]


def mark_twilio_status_event_orphaned(
    event: CommunicationProviderEvent,
    *,
    now: datetime,
    error_message: str,
) -> None:
    event.processing_status = TWILIO_STATUS_RECOVERY_ORPHANED
    event.processing_started_at = None
    event.processing_token = None
    event.next_attempt_at = None
    event.processed_at = now
    event.error_message = error_message[:2000]


def record_twilio_status_recovery_failure(
    db: Session,
    claim: TwilioStatusRecoveryClaim,
    exc: Exception,
    settings: Settings,
) -> bool:
    if claim.processing_token is None:
        return False
    event = db.scalar(
        select(CommunicationProviderEvent)
        .where(
            CommunicationProviderEvent.id == claim.event_id,
            CommunicationProviderEvent.processing_status == "processing",
            CommunicationProviderEvent.processing_token == claim.processing_token,
        )
        .with_for_update()
    )
    if event is None:
        return False
    defer_or_orphan_twilio_status_event(
        event,
        settings,
        error_message=str(exc),
    )
    db.commit()
    return True


def apply_sms_preference(
    db: Session,
    *,
    organization_id: UUID,
    contact: Contact | None,
    sender: str,
    message_sid: str,
    preference: str,
) -> None:
    normalized_address = format_e164(sender)
    if normalized_address is None:
        raise ValueError("Twilio compliance keyword has an invalid sender number.")
    now = datetime.now(UTC)
    suppression = db.scalar(
        select(SuppressionRecord).where(
            SuppressionRecord.organization_id == organization_id,
            SuppressionRecord.channel == "sms",
            SuppressionRecord.normalized_address == normalized_address,
        )
    )
    if suppression is None:
        suppression = SuppressionRecord(
            organization_id=organization_id,
            contact_id=contact.id if contact is not None else None,
            channel="sms",
            normalized_address=normalized_address,
            status="active" if preference == "STOP" else "lifted",
            reason="Recipient texted STOP" if preference == "STOP" else "Recipient texted START",
            source="twilio_advanced_opt_out",
            provider="twilio",
            external_event_id=message_sid,
            suppressed_at=now,
            lifted_at=None if preference == "STOP" else now,
            suppression_metadata={"opt_out_type": preference},
        )
        db.add(suppression)
    else:
        if contact is not None:
            suppression.contact_id = contact.id
        suppression.status = "active" if preference == "STOP" else "lifted"
        suppression.reason = (
            "Recipient texted STOP" if preference == "STOP" else "Recipient texted START"
        )
        suppression.source = "twilio_advanced_opt_out"
        suppression.provider = "twilio"
        suppression.external_event_id = message_sid
        suppression.suppressed_at = now if preference == "STOP" else suppression.suppressed_at
        suppression.lifted_at = None if preference == "STOP" else now
        suppression.suppression_metadata = {"opt_out_type": preference}
    consent_status = "revoked" if preference == "STOP" else "granted"
    if contact is not None:
        db.add(
            ConsentRecord(
                organization_id=organization_id,
                contact_id=contact.id,
                channel="sms",
                status=consent_status,
                source="twilio_advanced_opt_out",
                wording_version="twilio-keyword-v1",
                wording=f"Recipient sent {preference} by SMS.",
                normalized_address=normalized_address,
                captured_ip=None,
                user_agent=None,
                created_at=now,
                updated_at=now,
            )
        )
    db.flush()
    db.add(
        AuditEvent(
            organization_id=organization_id,
            actor_user_id=None,
            actor_type="provider",
            action=(
                "communication.sms_suppress"
                if preference == "STOP"
                else "communication.sms_unsuppress"
            ),
            entity_type="contact" if contact is not None else "suppression_record",
            entity_id=contact.id if contact is not None else suppression.id,
            previous_value=None,
            new_value={
                "channel": "sms",
                "status": consent_status,
                "provider_message_id": message_sid,
                "normalized_address": normalized_address,
                "matched_contact": contact is not None,
            },
            reason=f"Twilio inbound {preference} keyword",
        )
    )


def should_apply_twilio_message_status(current_status: str, new_status: str) -> bool:
    current = current_status.strip().lower()
    new = new_status.strip().lower()
    if current == new:
        return True
    if current in TWILIO_MESSAGE_TERMINAL_STATUSES:
        return False
    if new in TWILIO_MESSAGE_TERMINAL_STATUSES:
        return True
    return TWILIO_MESSAGE_STATUS_RANK.get(new, -1) >= TWILIO_MESSAGE_STATUS_RANK.get(
        current,
        -1,
    )


def find_conversation_by_phone(
    db: Session,
    organization_id: UUID,
    phone_number: str,
    *,
    conversation_type: str,
) -> Conversation | None:
    lookup_values = phone_lookup_values(phone_number)
    if not lookup_values:
        return None
    return db.scalar(
        select(Conversation)
        .join(ContactMethod, ContactMethod.contact_id == Conversation.contact_id)
        .where(
            Conversation.organization_id == organization_id,
            Conversation.conversation_type == conversation_type,
            ContactMethod.organization_id == organization_id,
            ContactMethod.method_type == "phone",
            ContactMethod.normalized_value.in_(lookup_values),
        )
        .order_by(
            Conversation.status == "closed",
            Conversation.last_activity_at.desc(),
            Conversation.created_at.desc(),
        )
    )


def conversation_activity_entity(
    db: Session,
    conversation: Conversation,
) -> tuple[str, UUID]:
    if conversation.lead_id is not None:
        return "lead", conversation.lead_id
    buyer_id = db.scalar(
        select(ConversationContextLink.buyer_id).where(
            ConversationContextLink.organization_id == conversation.organization_id,
            ConversationContextLink.conversation_id == conversation.id,
            ConversationContextLink.context_type == "buyer",
        )
    )
    return ("buyer", buyer_id) if buyer_id is not None else ("conversation", conversation.id)


def select_sms_sender_line(
    db: Session,
    organization_id: UUID,
    *,
    conversation: Conversation,
) -> VoiceLine | None:
    if conversation.conversation_type == "buyer":
        department_key = "dispositions"
        purpose_key = "buyer_relations"
    else:
        department_key = "acquisitions"
        purpose_key = "seller_conversations"
    return db.scalar(
        select(VoiceLine)
        .where(
            VoiceLine.organization_id == organization_id,
            VoiceLine.department_key == department_key,
            VoiceLine.purpose_key == purpose_key,
            VoiceLine.status == "active",
        )
        .order_by(VoiceLine.is_default.desc(), VoiceLine.created_at.asc())
    )


def find_sms_line_by_number(
    db: Session,
    organization_id: UUID,
    phone_number: str,
) -> VoiceLine | None:
    formatted = format_e164(phone_number)
    if formatted is None:
        return None
    return db.scalar(
        select(VoiceLine).where(
            VoiceLine.organization_id == organization_id,
            VoiceLine.phone_number == formatted,
            VoiceLine.status == "active",
        )
    )


def user_can_use_line(
    db: Session,
    line: VoiceLine,
    *,
    user_id: UUID,
) -> bool:
    if user_id in {line.assigned_user_id, line.fallback_user_id}:
        return True
    if line.assigned_team_id is None:
        return False
    return (
        db.scalar(
            select(TeamMembership.id).where(
                TeamMembership.organization_id == line.organization_id,
                TeamMembership.team_id == line.assigned_team_id,
                TeamMembership.user_id == user_id,
            )
        )
        is not None
    )


def classify_opt_out(payload: dict[str, str], body: str) -> str | None:
    provider_value = payload.get("OptOutType", "").strip().upper()
    if provider_value in {"STOP", "START", "HELP"}:
        return provider_value
    normalized_body = body.strip().lower()
    if normalized_body in STOP_WORDS:
        return "STOP"
    if normalized_body in START_WORDS:
        return "START"
    if normalized_body in {"help", "info"}:
        return "HELP"
    return None


def required_twilio_value(payload: Mapping[str, object], key: str) -> str:
    raw_value = payload.get(key)
    value = str(raw_value).strip() if raw_value is not None else ""
    if not value:
        raise ValueError(f"Twilio webhook is missing {key}.")
    return value


def get_provider_event(
    db: Session,
    organization_id: UUID,
    external_event_id: str,
) -> CommunicationProviderEvent | None:
    return db.scalar(
        select(CommunicationProviderEvent).where(
            CommunicationProviderEvent.organization_id == organization_id,
            CommunicationProviderEvent.provider == "twilio",
            CommunicationProviderEvent.external_event_id == external_event_id,
        )
    )


def get_twilio_status_provider_event(
    db: Session,
    external_event_id: str,
) -> CommunicationProviderEvent | None:
    return db.scalars(
        select(CommunicationProviderEvent)
        .where(
            CommunicationProviderEvent.provider == "twilio",
            CommunicationProviderEvent.event_type == "messaging.status",
            CommunicationProviderEvent.external_event_id == external_event_id,
        )
        .order_by(CommunicationProviderEvent.received_at.asc())
    ).first()


def get_default_organization(db: Session) -> Organization:
    settings = get_settings()
    organization = db.scalar(
        select(Organization).where(Organization.name == settings.default_organization_name)
    )
    if organization is None:
        organization = db.scalar(select(Organization).order_by(Organization.created_at.asc()))
    if organization is None:
        raise RuntimeError("Twilio webhook received before an organization was configured.")
    return organization
