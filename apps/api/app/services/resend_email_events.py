import hashlib
from datetime import UTC, datetime
from email.utils import getaddresses
from html.parser import HTMLParser
from typing import Any
from uuid import UUID

from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.integrations.resend_email import ResendEmailDeliveryProvider
from app.models.foundation import (
    ActivityEvent,
    CommunicationDispatch,
    CommunicationProviderEvent,
    CommunicationRecord,
    Contact,
    ContactMethod,
    Conversation,
    EmailAttachment,
    EmailSenderAlias,
    Lead,
    Organization,
)
from app.services.communication_participants import record_email_participants
from app.services.document_storage import store_content
from app.services.inbox import update_conversation_activity

LIFECYCLE_STATUSES = {
    "email.sent": "sent",
    "email.delivered": "delivered",
    "email.delivery_delayed": "delivery_delayed",
    "email.bounced": "bounced",
    "email.complained": "complained",
    "email.failed": "failed",
    "email.suppressed": "suppressed",
}
STATUS_RANK = {
    "pending": 0,
    "sent": 10,
    "delivery_delayed": 20,
    "delivered": 30,
    "bounced": 40,
    "failed": 40,
    "suppressed": 40,
    "complained": 50,
}
TERMINAL_STATUSES = {"bounced", "failed", "suppressed", "complained"}


class _HtmlTextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []

    def handle_data(self, data: str) -> None:
        normalized = data.strip()
        if normalized:
            self.parts.append(normalized)


def ingest_resend_event(
    db: Session,
    *,
    external_event_id: str,
    payload: dict[str, Any],
) -> tuple[CommunicationProviderEvent, bool]:
    event_type = required_string(payload, "type")
    data = payload.get("data")
    if not isinstance(data, dict):
        raise ValueError("Resend webhook payload is missing event data.")
    organization = organization_for_recipients(
        db,
        string_list(data.get("to")) + string_list(data.get("received_for")),
    )
    existing = db.scalar(
        select(CommunicationProviderEvent).where(
            CommunicationProviderEvent.organization_id == organization.id,
            CommunicationProviderEvent.provider == "resend",
            CommunicationProviderEvent.external_event_id == external_event_id,
        )
    )
    if existing is not None:
        return existing, False
    event = CommunicationProviderEvent(
        organization_id=organization.id,
        conversation_id=None,
        provider="resend",
        event_type=event_type,
        external_event_id=external_event_id[:255],
        processing_status="received",
        payload=payload,
        received_at=datetime.now(UTC),
        processed_at=None,
        error_message=None,
    )
    db.add(event)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        duplicate = db.scalar(
            select(CommunicationProviderEvent).where(
                CommunicationProviderEvent.organization_id == organization.id,
                CommunicationProviderEvent.provider == "resend",
                CommunicationProviderEvent.external_event_id == external_event_id,
            )
        )
        if duplicate is None:
            raise
        return duplicate, False
    return event, True


def process_next_resend_event(
    db: Session,
    settings: Settings,
    *,
    client: ResendEmailDeliveryProvider | None = None,
) -> UUID | None:
    if not resend_processing_enabled(settings):
        return None
    event = db.scalar(
        select(CommunicationProviderEvent)
        .where(
            CommunicationProviderEvent.provider == "resend",
            CommunicationProviderEvent.processing_status.in_(("received", "retry")),
        )
        .order_by(CommunicationProviderEvent.received_at.asc())
    )
    if event is None:
        return None
    event.processing_status = "processing"
    event.error_message = None
    db.commit()
    provider = client or ResendEmailDeliveryProvider(api_key=settings.resend_api_key or "")
    try:
        if event.event_type == "email.received":
            process_received_email(db, event, provider, settings)
        elif event.event_type in LIFECYCLE_STATUSES:
            process_lifecycle_event(db, event)
        else:
            event.processing_status = "ignored"
            event.processed_at = datetime.now(UTC)
            db.commit()
    except Exception as exc:
        db.rollback()
        failed_event = db.get(CommunicationProviderEvent, event.id)
        if failed_event is not None:
            failed_event.processing_status = "retry"
            failed_event.error_message = str(exc)[:2000]
            db.commit()
        raise
    return event.id


def process_received_email(
    db: Session,
    event: CommunicationProviderEvent,
    provider: ResendEmailDeliveryProvider,
    settings: Settings,
) -> None:
    data = event_data(event)
    provider_message_id = required_string(data, "email_id")
    existing = db.scalar(
        select(CommunicationRecord).where(
            CommunicationRecord.organization_id == event.organization_id,
            CommunicationRecord.provider == "resend",
            CommunicationRecord.provider_message_id == provider_message_id,
        )
    )
    if existing is not None:
        event.conversation_id = existing.conversation_id
        event.processing_status = "duplicate"
        event.processed_at = datetime.now(UTC)
        db.commit()
        return

    message = provider.retrieve_received_email(provider_message_id)
    stored_route = event.payload.get("_routing")
    route = (
        stored_route
        if isinstance(stored_route, dict)
        and stored_route.get("status") == "matched"
        and stored_route.get("conversation_id")
        else resolve_inbound_route(db, event.organization_id, message)
    )
    event.payload = {
        **event.payload,
        "_routing": route,
    }
    if route["status"] != "matched":
        event.processing_status = str(route["status"])
        event.processed_at = datetime.now(UTC)
        db.commit()
        return

    conversation = db.get(Conversation, UUID(str(route["conversation_id"])))
    if conversation is None:
        raise RuntimeError("Matched Resend conversation no longer exists.")
    lead = db.get(Lead, conversation.lead_id) if conversation.lead_id is not None else None
    contact = db.get(Contact, conversation.contact_id)
    if contact is None:
        raise RuntimeError("Matched Resend conversation is missing contact context.")
    headers = normalized_headers(message.get("headers"))
    occurred_at = parse_datetime(message.get("created_at")) or datetime.now(UTC)
    communication = CommunicationRecord(
        organization_id=event.organization_id,
        conversation_id=conversation.id,
        lead_id=conversation.lead_id,
        contact_id=contact.id,
        actor_user_id=None,
        direction="inbound",
        channel="email",
        status="received",
        provider="resend",
        provider_message_id=provider_message_id,
        subject=optional_string(message.get("subject"))[:255] or None,
        body=received_message_body(message),
        occurred_at=occurred_at,
        external_payload={
            "id": provider_message_id,
            "message_id": optional_string(message.get("message_id")),
            "attachment_count": len(message.get("attachments", [])),
        },
        communication_metadata={
            "source": "resend_receiving",
            "email_sender_alias_ids": route["email_sender_alias_ids"],
            "provider_thread_id": route.get("provider_thread_id") or provider_message_id,
            "rfc_message_id": optional_string(message.get("message_id")),
            "references": headers.get("references", ""),
            "in_reply_to": headers.get("in-reply-to", ""),
            "from": optional_string(message.get("from")),
            "to": string_list(message.get("to")),
            "cc": string_list(message.get("cc")),
            "bcc": string_list(message.get("bcc")),
            "html_available": bool(message.get("html")),
        },
    )
    db.add(communication)
    db.flush()
    record_email_participants(
        db,
        communication,
        from_values=message.get("from"),
        to_values=message.get("to"),
        cc_values=message.get("cc"),
        bcc_values=message.get("bcc"),
        external_contact_id=contact.id,
        external_roles={"from"},
        sender_alias_ids=[
            UUID(str(alias_id))
            for alias_id in route["email_sender_alias_ids"]
        ],
        source="resend_receiving",
    )
    retain_received_attachments(
        db,
        communication,
        message,
        route["email_sender_alias_ids"],
        provider,
        settings,
    )
    update_conversation_activity(
        conversation,
        direction="inbound",
        occurred_at=occurred_at,
    )
    db.add(
        ActivityEvent(
            organization_id=event.organization_id,
            actor_user_id=None,
            entity_type="lead" if lead is not None else "conversation",
            entity_id=lead.id if lead is not None else conversation.id,
            event_type=(
                "lead.email_received"
                if lead is not None
                else "conversation.email_received"
            ),
            summary=f"Email received from {optional_string(message.get('from'))}.",
        )
    )
    event.conversation_id = conversation.id
    event.processing_status = "processed"
    event.processed_at = datetime.now(UTC)
    db.commit()


def process_lifecycle_event(
    db: Session,
    event: CommunicationProviderEvent,
) -> None:
    data = event_data(event)
    provider_message_id = required_string(data, "email_id")
    communication = db.scalar(
        select(CommunicationRecord).where(
            CommunicationRecord.organization_id == event.organization_id,
            CommunicationRecord.provider == "resend",
            CommunicationRecord.provider_message_id == provider_message_id,
        )
    )
    if communication is None:
        event.processing_status = "unmatched"
        event.processed_at = datetime.now(UTC)
        db.commit()
        return
    new_status = LIFECYCLE_STATUSES[event.event_type]
    metadata = communication.communication_metadata or {}
    current_status = communication.status
    event_at = parse_datetime(event.payload.get("created_at")) or event.received_at
    current_at = parse_datetime(metadata.get("provider_status_at"))
    if should_apply_status(current_status, new_status, current_at, event_at):
        communication.status = new_status
        communication.communication_metadata = {
            **metadata,
            "provider_status_at": event_at.isoformat(),
            "provider_event_type": event.event_type,
        }
        communication.external_payload = {
            **(communication.external_payload or {}),
            "last_provider_event": data,
        }
        dispatch = db.scalar(
            select(CommunicationDispatch).where(
                CommunicationDispatch.organization_id == event.organization_id,
                CommunicationDispatch.provider == "resend",
                CommunicationDispatch.provider_message_id == provider_message_id,
            )
        )
        if dispatch is not None:
            dispatch.status = new_status
            dispatch.completed_at = event_at
            if new_status in TERMINAL_STATUSES:
                dispatch.error_code = new_status
                dispatch.error_message = provider_failure_message(data)
    event.conversation_id = communication.conversation_id
    event.processing_status = "processed"
    event.processed_at = datetime.now(UTC)
    db.commit()


def recover_next_received_email(
    db: Session,
    settings: Settings,
    *,
    client: ResendEmailDeliveryProvider | None = None,
    max_pages: int = 5,
) -> UUID | None:
    if not resend_processing_enabled(settings) or not settings.email_sync_enabled:
        return None
    provider = client or ResendEmailDeliveryProvider(api_key=settings.resend_api_key or "")
    after: str | None = None
    for _page in range(max_pages):
        response = provider.list_received_emails(limit=100, after=after)
        items = response.get("data")
        if not isinstance(items, list):
            raise ValueError("Resend receiving recovery returned invalid data.")
        for item in items:
            if not isinstance(item, dict):
                continue
            provider_message_id = optional_string(item.get("id"))
            if not provider_message_id or received_email_is_known(
                db,
                provider_message_id,
            ):
                continue
            payload = {
                "type": "email.received",
                "created_at": optional_string(item.get("created_at"))
                or datetime.now(UTC).isoformat(),
                "data": {
                    **item,
                    "email_id": provider_message_id,
                },
                "_source": "resend_receiving_recovery",
            }
            event, created = ingest_resend_event(
                db,
                external_event_id=f"recovery:{provider_message_id}",
                payload=payload,
            )
            if created:
                return event.id
        if not response.get("has_more") or not items:
            break
        last_item = items[-1]
        after = optional_string(last_item.get("id")) if isinstance(last_item, dict) else ""
        if not after:
            break
    return None


def resolve_inbound_route(
    db: Session,
    organization_id: UUID,
    message: dict[str, Any],
) -> dict[str, Any]:
    recipients = normalized_addresses(
        string_list(message.get("to")) + string_list(message.get("received_for"))
    )
    aliases = db.scalars(
        select(EmailSenderAlias).where(
            EmailSenderAlias.organization_id == organization_id,
            EmailSenderAlias.email_address.in_(recipients),
            EmailSenderAlias.status == "active",
            EmailSenderAlias.inbound_enabled.is_(True),
        )
    ).all()
    alias_ids = [str(alias.id) for alias in aliases]
    if not aliases:
        return {
            "status": "unmatched",
            "reason": "No active inbound Stonegate alias matched the recipient.",
            "email_sender_alias_ids": [],
            "candidate_conversation_ids": [],
        }

    headers = normalized_headers(message.get("headers"))
    thread_values = [
        headers.get("in-reply-to", ""),
        headers.get("references", ""),
    ]
    communications = db.scalars(
        select(CommunicationRecord).where(
            CommunicationRecord.organization_id == organization_id,
            CommunicationRecord.channel == "email",
            CommunicationRecord.conversation_id.is_not(None),
        )
    ).all()
    thread_matches: dict[UUID, CommunicationRecord] = {}
    for communication in communications:
        metadata = communication.communication_metadata or {}
        rfc_message_id = optional_string(metadata.get("rfc_message_id"))
        if rfc_message_id and any(rfc_message_id in value for value in thread_values):
            if communication.conversation_id is not None:
                thread_matches[communication.conversation_id] = communication
    if len(thread_matches) == 1:
        conversation_id, matched_message = next(iter(thread_matches.items()))
        metadata = matched_message.communication_metadata or {}
        return {
            "status": "matched",
            "reason": "Matched exact RFC reply headers.",
            "conversation_id": str(conversation_id),
            "provider_thread_id": metadata.get("provider_thread_id"),
            "email_sender_alias_ids": alias_ids,
            "candidate_conversation_ids": [str(conversation_id)],
        }
    if len(thread_matches) > 1:
        return {
            "status": "ambiguous",
            "reason": "Reply headers matched more than one Stonegate conversation.",
            "email_sender_alias_ids": alias_ids,
            "candidate_conversation_ids": [
                str(conversation_id) for conversation_id in thread_matches
            ],
        }

    senders = normalized_addresses([optional_string(message.get("from"))])
    contact_ids = list(
        db.scalars(
            select(ContactMethod.contact_id).where(
                ContactMethod.organization_id == organization_id,
                ContactMethod.method_type == "email",
                or_(
                    ContactMethod.normalized_value.in_(senders),
                    ContactMethod.value.in_(senders),
                ),
            )
        )
    )
    candidates = db.scalars(
        select(Conversation)
        .where(
            Conversation.organization_id == organization_id,
            Conversation.contact_id.in_(contact_ids),
        )
        .order_by(
            Conversation.status == "closed",
            Conversation.last_activity_at.desc(),
        )
    ).all()
    candidate_ids = list(dict.fromkeys(conversation.id for conversation in candidates))
    if len(candidate_ids) == 1:
        return {
            "status": "matched",
            "reason": "Matched the seller email address to one conversation.",
            "conversation_id": str(candidate_ids[0]),
            "provider_thread_id": None,
            "email_sender_alias_ids": alias_ids,
            "candidate_conversation_ids": [str(candidate_ids[0])],
        }
    return {
        "status": "ambiguous" if candidate_ids else "unmatched",
        "reason": (
            "Seller email address matched more than one Stonegate conversation."
            if candidate_ids
            else "No seller conversation matched the sender or reply headers."
        ),
        "email_sender_alias_ids": alias_ids,
        "candidate_conversation_ids": [str(item) for item in candidate_ids],
    }


def retain_received_attachments(
    db: Session,
    communication: CommunicationRecord,
    message: dict[str, Any],
    alias_ids: list[str],
    provider: ResendEmailDeliveryProvider,
    settings: Settings,
) -> None:
    attachments = message.get("attachments")
    if not isinstance(attachments, list):
        return
    alias_id = UUID(alias_ids[0]) if alias_ids else None
    for item in attachments:
        if not isinstance(item, dict):
            continue
        attachment_id = optional_string(item.get("id"))
        if not attachment_id:
            continue
        existing = db.scalar(
            select(EmailAttachment).where(
                EmailAttachment.communication_record_id == communication.id,
                EmailAttachment.provider_attachment_id == attachment_id,
            )
        )
        if existing is not None:
            continue
        filename = optional_string(item.get("filename"))[:500] or "attachment"
        content_type = (
            optional_string(item.get("content_type"))[:255]
            or "application/octet-stream"
        )
        record = EmailAttachment(
            organization_id=communication.organization_id,
            communication_record_id=communication.id,
            email_account_id=None,
            email_sender_alias_id=alias_id,
            provider_message_id=communication.provider_message_id or "",
            provider_attachment_id=attachment_id,
            filename=filename,
            content_type=content_type,
            size_bytes=int(item.get("size") or 0),
            content_id=optional_string(item.get("content_id"))[:500] or None,
            disposition=optional_string(item.get("content_disposition")) or "attachment",
            sha256=None,
            content_data=None,
            storage_provider=None,
            storage_key=None,
            malware_scan_status=None,
            retention_until=None,
            attachment_metadata={"storage_status": "pending"},
        )
        db.add(record)
        db.flush()
        try:
            provider_metadata, content = provider.download_received_attachment(
                communication.provider_message_id or "",
                attachment_id,
                max_bytes=settings.email_max_attachment_bytes,
            )
            stored = store_content(
                organization_id=communication.organization_id,
                namespace="email-attachments",
                record_id=record.id,
                file_name=filename,
                content_type=content_type,
                content=content,
                settings=settings,
            )
            record.size_bytes = len(content)
            record.sha256 = hashlib.sha256(content).hexdigest()
            record.content_data = stored.database_bytes
            record.storage_provider = stored.provider
            record.storage_key = stored.key
            record.malware_scan_status = stored.malware_scan_status
            record.retention_until = stored.retention_until
            record.attachment_metadata = {
                "storage_status": "retained",
                "provider_expires_at": provider_metadata.get("expires_at"),
            }
        except ValueError as exc:
            record.attachment_metadata = {
                "storage_status": "rejected",
                "error": str(exc)[:500],
            }


def organization_for_recipients(
    db: Session,
    recipients: list[str],
) -> Organization:
    normalized = normalized_addresses(recipients)
    alias = db.scalar(
        select(EmailSenderAlias).where(
            EmailSenderAlias.email_address.in_(normalized),
        )
    )
    if alias is not None:
        organization = db.get(Organization, alias.organization_id)
        if organization is not None:
            return organization
    settings = get_settings()
    organization = db.scalar(
        select(Organization).where(
            Organization.name == settings.default_organization_name
        )
    )
    if organization is None:
        organization = db.scalar(
            select(Organization).order_by(Organization.created_at.asc())
        )
    if organization is None:
        raise RuntimeError("Resend webhook received before an organization was configured.")
    return organization


def resend_processing_enabled(settings: Settings) -> bool:
    return (
        settings.email_enabled
        and settings.email_provider == "resend"
        and not settings.email_configuration_blockers
    )


def received_email_is_known(db: Session, provider_message_id: str) -> bool:
    communication = db.scalar(
        select(CommunicationRecord.id).where(
            CommunicationRecord.provider == "resend",
            CommunicationRecord.provider_message_id == provider_message_id,
        )
    )
    if communication is not None:
        return True
    recovery_event = db.scalar(
        select(CommunicationProviderEvent.id).where(
            CommunicationProviderEvent.provider == "resend",
            CommunicationProviderEvent.external_event_id
            == f"recovery:{provider_message_id}",
        )
    )
    return recovery_event is not None


def should_apply_status(
    current_status: str,
    new_status: str,
    current_at: datetime | None,
    event_at: datetime,
) -> bool:
    if current_status in TERMINAL_STATUSES:
        return new_status in TERMINAL_STATUSES and (
            current_at is None or event_at >= current_at
        )
    if new_status in TERMINAL_STATUSES:
        return True
    if current_at is not None and event_at < current_at:
        return False
    return STATUS_RANK.get(new_status, 0) >= STATUS_RANK.get(current_status, 0)


def provider_failure_message(data: dict[str, Any]) -> str | None:
    for key in ("bounce", "failed", "suppressed"):
        details = data.get(key)
        if isinstance(details, dict):
            message = optional_string(details.get("message"))
            if message:
                return message[:2000]
    return None


def event_data(event: CommunicationProviderEvent) -> dict[str, Any]:
    data = event.payload.get("data")
    if not isinstance(data, dict):
        raise ValueError("Stored Resend event is missing data.")
    return data


def normalized_addresses(values: list[str]) -> list[str]:
    addresses = [
        address.strip().lower()
        for _name, address in getaddresses(values)
        if address.strip()
    ]
    return list(dict.fromkeys(addresses))


def normalized_headers(value: object) -> dict[str, str]:
    if not isinstance(value, dict):
        return {}
    return {
        str(key).strip().lower(): optional_string(item)
        for key, item in value.items()
    }


def string_list(value: object) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        return [str(item) for item in value if str(item).strip()]
    return []


def received_message_body(message: dict[str, Any]) -> str:
    text = optional_string(message.get("text")).strip()
    if text:
        return text
    html = optional_string(message.get("html"))
    if html:
        parser = _HtmlTextExtractor()
        parser.feed(html)
        extracted = "\n".join(parser.parts).strip()
        if extracted:
            return extracted
    return "(Email contained no readable message body.)"


def parse_datetime(value: object) -> datetime | None:
    normalized = optional_string(value)
    if not normalized:
        return None
    try:
        parsed = datetime.fromisoformat(normalized.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def required_string(payload: dict[str, Any], key: str) -> str:
    value = optional_string(payload.get(key))
    if not value:
        raise ValueError(f"Resend payload is missing {key}.")
    return value


def optional_string(value: object) -> str:
    return str(value).strip() if value is not None else ""
