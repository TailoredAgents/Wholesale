import hashlib
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.auth import Principal
from app.core.config import get_settings
from app.domain.rbac import PermissionKeys
from app.integrations.communications import (
    OutboundMessageRequest,
    SimulatedCommunicationProvider,
)
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
from app.services.inbox import get_scoped_conversation, update_conversation_activity

STOP_WORDS = {"cancel", "end", "quit", "stop", "stopall", "unsubscribe"}
START_WORDS = {"start", "unstop"}


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
    if (
        PermissionKeys.SEND_SMS not in principal.permission_keys
        and (
            PermissionKeys.SEND_ASSIGNED_SMS not in principal.permission_keys
            or conversation.assigned_user_id != principal.user_id
        )
    ):
        raise PermissionError("SMS can only be sent from an assigned conversation.")
    if conversation.conversation_type not in {"lead", "buyer"}:
        raise SmsConfigurationError(
            "SMS is only available from seller and buyer conversations."
        )

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

    lead = db.get(Lead, conversation.lead_id) if conversation.lead_id is not None else None
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
        raise PermissionError(
            "Buyer SMS requires assignment to the Stonegate dispositions line."
        )
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

    if (
        settings.communication_provider_mode == "disabled"
        or (
            not settings.communication_simulation_enabled
            and not settings.twilio_sms_configured
        )
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
    sender_line = find_sms_line_by_number(db, organization.id, recipient)
    conversation_type = (
        "buyer"
        if sender_line is not None and sender_line.purpose_key == "buyer_relations"
        else "lead"
    )
    conversation = find_conversation_by_phone(
        db,
        organization.id,
        sender,
        conversation_type=conversation_type,
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
    if conversation is None:
        event.processing_status = "unmatched"
        event.processed_at = datetime.now(UTC)
        db.commit()
        return event.processing_status

    lead = db.get(Lead, conversation.lead_id) if conversation.lead_id is not None else None
    contact = db.get(Contact, conversation.contact_id)
    if conversation.conversation_type == "lead" and lead is None:
        raise RuntimeError("Matched Twilio seller conversation is missing lead context.")
    if contact is None:
        raise RuntimeError("Matched Twilio conversation is missing contact context.")
    opt_out_type = classify_opt_out(payload, body)
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
        },
        communication_metadata={
            "source": "twilio_webhook",
            "sender_number": recipient,
            "voice_line_id": str(sender_line.id) if sender_line is not None else None,
        },
    )
    db.add(communication)
    update_conversation_activity(
        conversation,
        direction="inbound",
        occurred_at=occurred_at,
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
                else f"Inbound {party_label} SMS received."
            ),
        )
    )
    event.processing_status = "processed"
    event.processed_at = datetime.now(UTC)
    db.commit()
    return event.processing_status


def process_twilio_status(db: Session, payload: dict[str, str]) -> str:
    message_sid = required_twilio_value(payload, "MessageSid")
    message_status = required_twilio_value(payload, "MessageStatus").lower()
    error_code = payload.get("ErrorCode") or "none"
    communication = db.scalar(
        select(CommunicationRecord).where(
            CommunicationRecord.provider == "twilio",
            CommunicationRecord.provider_message_id == message_sid,
        )
    )
    organization = (
        db.get(Organization, communication.organization_id)
        if communication is not None
        else get_default_organization(db)
    )
    if organization is None:
        raise RuntimeError("Twilio status callback has no organization.")
    event_id = f"status:{message_sid}:{message_status}:{error_code}"
    existing_event = get_provider_event(db, organization.id, event_id)
    if existing_event is not None:
        return existing_event.processing_status

    event = CommunicationProviderEvent(
        organization_id=organization.id,
        conversation_id=communication.conversation_id if communication else None,
        provider="twilio",
        event_type="messaging.status",
        external_event_id=event_id,
        processing_status="received",
        payload=payload,
        received_at=datetime.now(UTC),
        processed_at=None,
        error_message=None,
    )
    db.add(event)
    if communication is None:
        event.processing_status = "unmatched"
    else:
        communication.status = message_status
        communication.external_payload = {
            **(communication.external_payload or {}),
            "message_status": message_status,
            "error_code": payload.get("ErrorCode"),
            "error_message": payload.get("ErrorMessage"),
        }
        dispatch = db.scalar(
            select(CommunicationDispatch).where(
                CommunicationDispatch.organization_id == organization.id,
                CommunicationDispatch.provider == "twilio",
                CommunicationDispatch.provider_message_id == message_sid,
            )
        )
        if dispatch is not None:
            dispatch.status = message_status
            dispatch.error_code = payload.get("ErrorCode")
            dispatch.error_message = payload.get("ErrorMessage")
            dispatch.completed_at = datetime.now(UTC)
        event.processing_status = "processed"
    event.processed_at = datetime.now(UTC)
    db.commit()
    return event.processing_status


def apply_sms_preference(
    db: Session,
    *,
    organization_id: UUID,
    contact: Contact,
    sender: str,
    message_sid: str,
    preference: str,
) -> None:
    normalized_address = format_e164(sender)
    if normalized_address is None:
        return
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
            contact_id=contact.id,
            channel="sms",
            normalized_address=normalized_address,
            status="active" if preference == "STOP" else "lifted",
            reason="Seller texted STOP" if preference == "STOP" else "Seller texted START",
            source="twilio_advanced_opt_out",
            provider="twilio",
            external_event_id=message_sid,
            suppressed_at=now,
            lifted_at=None if preference == "STOP" else now,
            suppression_metadata={"opt_out_type": preference},
        )
        db.add(suppression)
    else:
        suppression.contact_id = contact.id
        suppression.status = "active" if preference == "STOP" else "lifted"
        suppression.reason = (
            "Seller texted STOP" if preference == "STOP" else "Seller texted START"
        )
        suppression.external_event_id = message_sid
        suppression.suppressed_at = now if preference == "STOP" else suppression.suppressed_at
        suppression.lifted_at = None if preference == "STOP" else now
        suppression.suppression_metadata = {"opt_out_type": preference}
    consent_status = "revoked" if preference == "STOP" else "granted"
    db.add(
        ConsentRecord(
            organization_id=organization_id,
            contact_id=contact.id,
            channel="sms",
            status=consent_status,
            source="twilio_advanced_opt_out",
            wording_version="twilio-keyword-v1",
            wording=f"Seller sent {preference} by SMS.",
            captured_ip=None,
            user_agent=None,
            created_at=now,
            updated_at=now,
        )
    )
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
            entity_type="contact",
            entity_id=contact.id,
            previous_value=None,
            new_value={
                "channel": "sms",
                "status": consent_status,
                "provider_message_id": message_sid,
            },
            reason=f"Twilio inbound {preference} keyword",
        )
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
    return db.scalar(
        select(TeamMembership.id).where(
            TeamMembership.organization_id == line.organization_id,
            TeamMembership.team_id == line.assigned_team_id,
            TeamMembership.user_id == user_id,
        )
    ) is not None


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


def required_twilio_value(payload: dict[str, str], key: str) -> str:
    value = payload.get(key, "").strip()
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
