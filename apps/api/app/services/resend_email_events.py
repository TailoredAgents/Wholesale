import hashlib
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from email.utils import getaddresses
from html.parser import HTMLParser
from typing import Any
from urllib.parse import urlsplit
from uuid import UUID, uuid4

from sqlalchemy import and_, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.integrations.resend_email import (
    ResendAttachmentTooLargeError,
    ResendEmailDeliveryProvider,
    attachment_size,
)
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
    User,
)
from app.services.communication_participants import record_email_participants
from app.services.document_storage import store_content
from app.services.email_identity import fallback_email_contact_name, general_email_display_name
from app.services.inbox import create_general_conversation, update_conversation_activity

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
RESEND_DEAD_LETTER_STATUS = "dead_letter"


class ResendLeaseLostError(RuntimeError):
    pass


class ResendLifecycleNotReadyError(RuntimeError):
    pass


@dataclass(frozen=True)
class ResendEventClaim:
    event: CommunicationProviderEvent
    processing_token: UUID


class _HtmlTextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []
        self.links: list[tuple[str, str]] = []
        self._link_stack: list[tuple[str | None, int]] = []

    def handle_starttag(
        self,
        tag: str,
        attrs: list[tuple[str, str | None]],
    ) -> None:
        if tag.lower() != "a":
            return
        href = next(
            (
                safe_link
                for key, value in attrs
                if key.lower() == "href" and value and (safe_link := _safe_email_link(value))
            ),
            None,
        )
        self._link_stack.append((href, len(self.parts)))

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() != "a" or not self._link_stack:
            return
        href, start_index = self._link_stack.pop()
        if not href:
            return
        label = " ".join(self.parts[start_index:]).strip()
        if not any(existing_href == href for _, existing_href in self.links):
            self.links.append((label, href))

    def handle_data(self, data: str) -> None:
        normalized = data.strip()
        if normalized:
            self.parts.append(normalized)


def _safe_email_link(value: str) -> str | None:
    candidate = value.strip()
    if not candidate or len(candidate) > 8192 or "\\" in candidate:
        return None
    if any(character.isspace() or ord(character) < 32 for character in candidate):
        return None
    try:
        parsed = urlsplit(candidate)
        _ = parsed.port
    except ValueError:
        return None
    if (
        parsed.scheme.lower() not in {"http", "https"}
        or not parsed.hostname
        or parsed.username
        or parsed.password
    ):
        return None
    return candidate


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
        attempt_count=0,
        next_attempt_at=None,
        processing_started_at=None,
        processing_token=None,
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
    claim = claim_next_resend_event(db, settings)
    if claim is None:
        return None
    event = claim.event
    event_id = event.id
    provider = client or ResendEmailDeliveryProvider(api_key=settings.resend_api_key or "")
    try:
        if event.event_type == "email.received":
            process_received_email(
                db,
                event,
                provider,
                settings,
                processing_token=claim.processing_token,
            )
        elif event.event_type in LIFECYCLE_STATUSES:
            process_lifecycle_event(db, event)
        else:
            complete_resend_event(event, "ignored")
        finalize_resend_event_claim(db, event, claim.processing_token)
    except ResendLeaseLostError:
        db.rollback()
        return event_id
    except Exception as exc:
        db.rollback()
        record_resend_event_failure(
            db,
            event_id,
            exc,
            settings,
            processing_token=claim.processing_token,
        )
        raise
    return event_id


def claim_next_resend_event(
    db: Session,
    settings: Settings,
) -> ResendEventClaim | None:
    while True:
        now = datetime.now(UTC)
        stale_before = now - timedelta(
            seconds=settings.resend_event_processing_lease_seconds
        )
        event = db.scalar(
            select(CommunicationProviderEvent)
            .where(
                CommunicationProviderEvent.provider == "resend",
                or_(
                    CommunicationProviderEvent.processing_status == "received",
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
                            CommunicationProviderEvent.processing_started_at <= stale_before,
                            and_(
                                CommunicationProviderEvent.processing_started_at.is_(None),
                                CommunicationProviderEvent.updated_at <= stale_before,
                            ),
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
        if event.attempt_count >= settings.resend_event_max_attempts:
            dead_letter_resend_event(
                event,
                now=now,
                fallback_error="Resend event exhausted its processing attempts.",
            )
            db.commit()
            continue
        event.processing_status = "processing"
        processing_token = uuid4()
        event.processing_started_at = now
        event.processing_token = processing_token
        event.processed_at = None
        event.next_attempt_at = None
        event.attempt_count += 1
        event.error_message = None
        db.commit()
        return ResendEventClaim(event=event, processing_token=processing_token)


def finalize_resend_event_claim(
    db: Session,
    event: CommunicationProviderEvent,
    processing_token: UUID,
) -> None:
    ensure_resend_event_claim(db, event.id, processing_token)
    event.processing_token = None
    db.commit()


def checkpoint_resend_event_claim(
    db: Session,
    event: CommunicationProviderEvent,
    processing_token: UUID,
) -> None:
    ensure_resend_event_claim(db, event.id, processing_token)
    event.processing_started_at = datetime.now(UTC)
    db.commit()


def ensure_resend_event_claim(
    db: Session,
    event_id: UUID,
    processing_token: UUID,
) -> None:
    with db.no_autoflush:
        active_claim = db.execute(
            select(
                CommunicationProviderEvent.processing_token,
                CommunicationProviderEvent.processing_status,
            )
            .where(CommunicationProviderEvent.id == event_id)
            .with_for_update()
        ).one_or_none()
    if (
        active_claim is None
        or active_claim.processing_token != processing_token
        or active_claim.processing_status != "processing"
    ):
        raise ResendLeaseLostError(
            "Resend event processing lease was reclaimed by another worker."
        )


def record_resend_event_failure(
    db: Session,
    event_id: UUID,
    exc: Exception,
    settings: Settings,
    *,
    processing_token: UUID,
) -> bool:
    event = db.scalar(
        select(CommunicationProviderEvent)
        .where(
            CommunicationProviderEvent.id == event_id,
            CommunicationProviderEvent.processing_status == "processing",
            CommunicationProviderEvent.processing_token == processing_token,
        )
        .with_for_update()
    )
    if event is None:
        return False
    now = datetime.now(UTC)
    event.processing_started_at = None
    event.processing_token = None
    event.error_message = str(exc)[:2000]
    if event.attempt_count >= settings.resend_event_max_attempts:
        dead_letter_resend_event(event, now=now)
    else:
        retry_delay = min(
            settings.resend_event_retry_base_seconds
            * (2 ** max(0, event.attempt_count - 1)),
            settings.resend_event_retry_max_seconds,
        )
        event.processing_status = "retry"
        event.processed_at = None
        event.next_attempt_at = now + timedelta(seconds=retry_delay)
    db.commit()
    return True


def dead_letter_resend_event(
    event: CommunicationProviderEvent,
    *,
    now: datetime,
    fallback_error: str | None = None,
) -> None:
    event.processing_status = RESEND_DEAD_LETTER_STATUS
    event.processing_started_at = None
    event.processing_token = None
    event.next_attempt_at = None
    event.processed_at = now
    if not event.error_message and fallback_error:
        event.error_message = fallback_error[:2000]


def complete_resend_event(event: CommunicationProviderEvent, status: str) -> None:
    event.processing_status = status
    event.processing_started_at = None
    event.next_attempt_at = None
    event.processed_at = datetime.now(UTC)


def process_received_email(
    db: Session,
    event: CommunicationProviderEvent,
    provider: ResendEmailDeliveryProvider,
    settings: Settings,
    *,
    processing_token: UUID,
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
        complete_resend_event(event, "duplicate")
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
        complete_resend_event(event, str(route["status"]))
        return

    # Preserve the exact validated destination before attachment downloads or other
    # provider work can fail. The lease fence prevents a stale worker from changing it.
    checkpoint_resend_event_claim(db, event, processing_token)

    conversation = db.get(Conversation, UUID(str(route["conversation_id"])))
    if conversation is None:
        raise RuntimeError("Matched Resend conversation no longer exists.")
    route_alias_ids = [UUID(str(alias_id)) for alias_id in route["email_sender_alias_ids"]]
    if conversation.source_alias_id is None and len(route_alias_ids) == 1:
        conversation.source_alias_id = route_alias_ids[0]
    lead = db.get(Lead, conversation.lead_id) if conversation.lead_id is not None else None
    contact = db.get(Contact, conversation.contact_id)
    if contact is None:
        raise RuntimeError("Matched Resend conversation is missing contact context.")
    headers = normalized_headers(message.get("headers"))
    email_category = inbound_email_category(message, headers)
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
            "email_category": email_category,
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
            *route_alias_ids,
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
        db=db,
        reactivate_closed_lead=email_category == "correspondence",
    )
    db.add(
        ActivityEvent(
            organization_id=event.organization_id,
            actor_user_id=None,
            entity_type="lead" if lead is not None else "conversation",
            entity_id=lead.id if lead is not None else conversation.id,
            event_type=(
                "lead.email_received" if lead is not None else "conversation.email_received"
            ),
            summary=f"Email received from {optional_string(message.get('from'))}.",
        )
    )
    event.conversation_id = conversation.id
    complete_resend_event(event, "processed")


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
        raise ResendLifecycleNotReadyError(
            "Resend lifecycle event arrived before its outbound email record was committed."
        )
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
    complete_resend_event(event, "processed")


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
    now = datetime.now(UTC)
    stale_before = now - timedelta(
        seconds=settings.resend_event_processing_lease_seconds
    )
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
                processing_stale_before=stale_before,
            ):
                continue
            recovery_event = db.scalar(
                select(CommunicationProviderEvent)
                .where(
                    CommunicationProviderEvent.provider == "resend",
                    CommunicationProviderEvent.external_event_id
                    == f"recovery:{provider_message_id}",
                )
                .with_for_update(skip_locked=True)
            )
            if recovery_event is not None:
                if recovery_event.processing_status == "processing" and event_lease_expired(
                    recovery_event,
                    stale_before=stale_before,
                ):
                    if recovery_event.attempt_count >= settings.resend_event_max_attempts:
                        dead_letter_resend_event(
                            recovery_event,
                            now=now,
                            fallback_error="Resend event exhausted its processing attempts.",
                        )
                    else:
                        recovery_event.processing_status = "retry"
                        recovery_event.processing_started_at = None
                        recovery_event.processing_token = None
                        recovery_event.next_attempt_at = now
                        recovery_event.processed_at = None
                        recovery_event.error_message = (
                            "Recovered after the Resend processing lease expired."
                        )
                    db.commit()
                    return recovery_event.id
                # Dead-letter events intentionally require review; they are not successful
                # imports and must not be resurrected into an automatic poison loop.
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
    aliases = list(
        db.scalars(
            select(EmailSenderAlias).where(
                EmailSenderAlias.organization_id == organization_id,
                EmailSenderAlias.email_address.in_(recipients),
                EmailSenderAlias.status == "active",
                EmailSenderAlias.inbound_enabled.is_(True),
            )
        )
    )
    aliases.sort(
        key=lambda alias: (
            recipients.index(alias.email_address)
            if alias.email_address in recipients
            else len(recipients),
            alias.email_address,
        )
    )
    alias_ids = [str(alias.id) for alias in aliases]
    if not aliases:
        return {
            "status": "unmatched",
            "rule": "recipient_alias",
            "confidence": 0,
            "reason": "No active inbound Stonegate alias matched the recipient.",
            "email_sender_alias_ids": [],
            "candidate_conversation_ids": [],
        }

    senders = normalized_addresses([optional_string(message.get("from"))])
    if not senders:
        return {
            "status": "unmatched",
            "rule": "sender_address",
            "confidence": 0,
            "reason": "Inbound email did not contain one valid sender address.",
            "email_sender_alias_ids": alias_ids,
            "candidate_conversation_ids": [],
        }
    if internal_sender(db, organization_id, senders):
        return {
            "status": "ignored",
            "rule": "internal_loop_protection",
            "confidence": 100,
            "reason": "Ignored an inbound loop from a Stonegate address or staff identity.",
            "email_sender_alias_ids": alias_ids,
            "candidate_conversation_ids": [],
        }

    restricted_alias_received = any(
        inbound_visibility_scope(alias) == "restricted" for alias in aliases
    )
    routing_aliases = (
        [alias for alias in aliases if inbound_visibility_scope(alias) == "restricted"]
        if restricted_alias_received
        else aliases
    )

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
        if (
            rfc_message_id
            and any(rfc_message_id in value for value in thread_values)
            and communication.conversation_id is not None
        ):
            thread_matches[communication.conversation_id] = communication
    if restricted_alias_received and thread_matches:
        allowed_ids = set(
            conversations_for_aliases(
                db,
                organization_id,
                list(
                    db.scalars(
                        select(Conversation).where(
                            Conversation.organization_id == organization_id,
                            Conversation.id.in_(thread_matches),
                        )
                    )
                ),
                routing_aliases,
            )
        )
        thread_matches = {
            conversation_id: communication
            for conversation_id, communication in thread_matches.items()
            if conversation_id in allowed_ids
        }
    if len(thread_matches) == 1:
        conversation_id, matched_message = next(iter(thread_matches.items()))
        metadata = matched_message.communication_metadata or {}
        return {
            "status": "matched",
            "rule": "exact_rfc_reply",
            "confidence": 100,
            "reason": "Matched exact RFC reply headers.",
            "conversation_id": str(conversation_id),
            "provider_thread_id": metadata.get("provider_thread_id"),
            "email_sender_alias_ids": alias_ids,
            "candidate_conversation_ids": [str(conversation_id)],
        }
    if len(thread_matches) > 1:
        return {
            "status": "ambiguous",
            "rule": "exact_rfc_reply",
            "confidence": 0,
            "reason": "Reply headers matched more than one Stonegate conversation.",
            "email_sender_alias_ids": alias_ids,
            "candidate_conversation_ids": [
                str(conversation_id) for conversation_id in thread_matches
            ],
        }

    provider_thread_values = {
        value
        for value in (
            optional_string(message.get("thread_id")),
            optional_string(message.get("provider_thread_id")),
            headers.get("x-resend-thread-id", ""),
        )
        if value
    }
    provider_thread_matches: dict[UUID, CommunicationRecord] = {}
    if provider_thread_values:
        for communication in communications:
            metadata = communication.communication_metadata or {}
            provider_thread_id = optional_string(metadata.get("provider_thread_id"))
            if (
                provider_thread_id
                and provider_thread_id in provider_thread_values
                and communication.conversation_id is not None
            ):
                provider_thread_matches[communication.conversation_id] = communication
    if restricted_alias_received and provider_thread_matches:
        allowed_ids = set(
            conversations_for_aliases(
                db,
                organization_id,
                list(
                    db.scalars(
                        select(Conversation).where(
                            Conversation.organization_id == organization_id,
                            Conversation.id.in_(provider_thread_matches),
                        )
                    )
                ),
                routing_aliases,
            )
        )
        provider_thread_matches = {
            conversation_id: communication
            for conversation_id, communication in provider_thread_matches.items()
            if conversation_id in allowed_ids
        }
    if len(provider_thread_matches) == 1:
        conversation_id, matched_message = next(iter(provider_thread_matches.items()))
        metadata = matched_message.communication_metadata or {}
        return {
            "status": "matched",
            "rule": "provider_thread",
            "confidence": 100,
            "reason": "Matched retained Resend thread evidence.",
            "conversation_id": str(conversation_id),
            "provider_thread_id": metadata.get("provider_thread_id"),
            "email_sender_alias_ids": alias_ids,
            "candidate_conversation_ids": [str(conversation_id)],
        }
    if len(provider_thread_matches) > 1:
        return {
            "status": "ambiguous",
            "rule": "provider_thread",
            "confidence": 0,
            "reason": "Resend thread evidence matched more than one Stonegate conversation.",
            "email_sender_alias_ids": alias_ids,
            "candidate_conversation_ids": [
                str(conversation_id) for conversation_id in provider_thread_matches
            ],
        }

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
    candidates = list(
        db.scalars(
            select(Conversation)
            .where(
                Conversation.organization_id == organization_id,
                Conversation.contact_id.in_(contact_ids),
            )
            .order_by(
                Conversation.status == "closed",
                Conversation.last_activity_at.desc(),
            )
        )
    )
    candidate_ids = list(dict.fromkeys(conversation.id for conversation in candidates))

    alias_candidate_ids = conversations_for_aliases(
        db,
        organization_id,
        candidates,
        routing_aliases,
    )
    if len(alias_candidate_ids) == 1:
        return {
            "status": "matched",
            "rule": "sender_and_alias",
            "confidence": 95,
            "reason": "Matched one conversation for this sender and Stonegate address.",
            "conversation_id": str(alias_candidate_ids[0]),
            "provider_thread_id": None,
            "email_sender_alias_ids": alias_ids,
            "candidate_conversation_ids": [str(alias_candidate_ids[0])],
        }
    if len(alias_candidate_ids) > 1:
        return {
            "status": "ambiguous",
            "rule": "sender_and_alias",
            "confidence": 0,
            "reason": "The sender and Stonegate address matched more than one conversation.",
            "email_sender_alias_ids": alias_ids,
            "candidate_conversation_ids": [str(item) for item in alias_candidate_ids],
        }

    active_candidate_ids = list(
        dict.fromkeys(
            conversation.id for conversation in candidates if conversation.status != "closed"
        )
    )
    if not restricted_alias_received and len(active_candidate_ids) == 1:
        return {
            "status": "matched",
            "rule": "unique_active_contact_context",
            "confidence": 85,
            "reason": "Matched the sender to one active Stonegate conversation.",
            "conversation_id": str(active_candidate_ids[0]),
            "provider_thread_id": None,
            "email_sender_alias_ids": alias_ids,
            "candidate_conversation_ids": [str(active_candidate_ids[0])],
        }
    if not restricted_alias_received and len(active_candidate_ids) > 1:
        return {
            "status": "ambiguous",
            "rule": "unique_active_contact_context",
            "confidence": 0,
            "reason": "The sender is connected to more than one active Stonegate conversation.",
            "email_sender_alias_ids": alias_ids,
            "candidate_conversation_ids": [str(item) for item in active_candidate_ids],
        }

    routing_alias = next(
        (
            alias
            for alias in routing_aliases
            if alias.owner_user_id is not None or alias.assigned_team_id is not None
        ),
        None,
    )
    if routing_alias is not None:
        contact = ensure_inbound_contact(
            db,
            organization_id,
            message,
            senders[0],
            contact_ids,
            assigned_user_id=routing_alias.owner_user_id,
        )
        visibility_scope = inbound_visibility_scope(routing_alias)
        conversation = create_general_conversation(
            db,
            organization_id=organization_id,
            contact_id=contact.id,
            assigned_user_id=routing_alias.owner_user_id,
            assigned_team_id=routing_alias.assigned_team_id,
            source_alias_id=routing_alias.id,
            visibility_scope=visibility_scope,
        )
        conversation.conversation_metadata = {
            **(conversation.conversation_metadata or {}),
            "routing_rule": "alias_owner_or_team",
            "routing_confidence": 80,
            "email_category": inbound_email_category(message, headers),
            "initial_subject": optional_string(message.get("subject"))[:255] or None,
        }
        db.flush()
        return {
            "status": "matched",
            "rule": "alias_owner_or_team",
            "confidence": 80,
            "reason": ("Created a general conversation in the receiving Stonegate mailbox."),
            "conversation_id": str(conversation.id),
            "provider_thread_id": None,
            "email_sender_alias_ids": alias_ids,
            "candidate_conversation_ids": [str(conversation.id)],
            "created_general_conversation": True,
        }

    return {
        "status": "unmatched",
        "rule": "alias_owner_or_team",
        "confidence": 0,
        "reason": (
            "The receiving Stonegate address needs an owner or team before new mail can route."
        ),
        "email_sender_alias_ids": alias_ids,
        "candidate_conversation_ids": [str(item) for item in candidate_ids],
    }


def internal_sender(
    db: Session,
    organization_id: UUID,
    senders: list[str],
) -> bool:
    alias_id = db.scalar(
        select(EmailSenderAlias.id).where(
            EmailSenderAlias.organization_id == organization_id,
            EmailSenderAlias.email_address.in_(senders),
        )
    )
    if alias_id is not None:
        return True
    user_id = db.scalar(
        select(User.id).where(
            User.organization_id == organization_id,
            User.email.in_(senders),
        )
    )
    return user_id is not None


def conversations_for_aliases(
    db: Session,
    organization_id: UUID,
    candidates: list[Conversation],
    aliases: list[EmailSenderAlias],
) -> list[UUID]:
    if not candidates or not aliases:
        return []
    restricted_alias_received = any(
        inbound_visibility_scope(alias) == "restricted" for alias in aliases
    )
    eligible_candidates = (
        [
            conversation
            for conversation in candidates
            if conversation.visibility_scope == "restricted"
        ]
        if restricted_alias_received
        else candidates
    )
    if not eligible_candidates:
        return []
    candidate_ids = {conversation.id for conversation in eligible_candidates}
    alias_ids = {str(alias.id) for alias in aliases}
    matches = {
        conversation.id
        for conversation in eligible_candidates
        if conversation.source_alias_id is not None
        and str(conversation.source_alias_id) in alias_ids
    }
    for communication in db.scalars(
        select(CommunicationRecord).where(
            CommunicationRecord.organization_id == organization_id,
            CommunicationRecord.conversation_id.in_(candidate_ids),
            CommunicationRecord.channel == "email",
        )
    ):
        metadata = communication.communication_metadata or {}
        sender_alias_id = optional_string(metadata.get("email_sender_alias_id"))
        raw_alias_ids = metadata.get("email_sender_alias_ids")
        inbound_alias_ids = (
            {
                alias_id
                for value in raw_alias_ids
                if (alias_id := optional_string(value)) is not None
            }
            if isinstance(raw_alias_ids, list)
            else set()
        )
        if communication.conversation_id is not None and (
            sender_alias_id in alias_ids or bool(alias_ids.intersection(inbound_alias_ids))
        ):
            matches.add(communication.conversation_id)
    ordered = [
        conversation.id
        for conversation in eligible_candidates
        if conversation.id in matches and conversation.status != "closed"
    ]
    if ordered:
        return list(dict.fromkeys(ordered))
    return list(
        dict.fromkeys(
            conversation.id
            for conversation in eligible_candidates
            if conversation.id in matches
        )
    )


def ensure_inbound_contact(
    db: Session,
    organization_id: UUID,
    message: dict[str, Any],
    sender: str,
    contact_ids: list[UUID],
    *,
    assigned_user_id: UUID | None,
) -> Contact:
    if contact_ids:
        contact = db.scalar(
            select(Contact)
            .where(
                Contact.organization_id == organization_id,
                Contact.id.in_(contact_ids),
            )
            .order_by(Contact.created_at.asc())
        )
        if contact is not None:
            return contact

    parsed = getaddresses([optional_string(message.get("from"))])
    display_name = next(
        (
            name.strip()
            for name, address in parsed
            if address.strip().lower() == sender and name.strip()
        ),
        "",
    )
    fallback_name = fallback_email_contact_name(sender)
    resolved_name = (
        general_email_display_name(display_name, sender) if display_name else fallback_name
    )
    contact = Contact(
        organization_id=organization_id,
        legal_name=(resolved_name or sender)[:255],
        preferred_name=resolved_name[:255] or None,
        contact_type="business_contact",
        assigned_user_id=assigned_user_id,
    )
    db.add(contact)
    db.flush()
    db.add(
        ContactMethod(
            organization_id=organization_id,
            contact_id=contact.id,
            method_type="email",
            value=sender,
            normalized_value=sender,
            is_primary=True,
        )
    )
    db.flush()
    return contact


def inbound_visibility_scope(alias: EmailSenderAlias) -> str:
    metadata = alias.routing_metadata or {}
    configured_scope = optional_string(metadata.get("visibility_scope")).lower()
    if configured_scope in {"standard", "restricted"}:
        return configured_scope
    if alias.purpose_key in {
        "accounting",
        "closing",
        "legal",
        "transaction",
        "transactions",
    }:
        return "restricted"
    return "standard"


def inbound_email_category(
    message: dict[str, Any],
    headers: dict[str, str],
) -> str:
    sender = optional_string(message.get("from")).lower()
    subject = optional_string(message.get("subject")).lower()
    auto_submitted = headers.get("auto-submitted", "").lower()
    if "dmarc" in subject or "report domain" in subject:
        return "dmarc_report"
    if "mailer-daemon" in sender or "postmaster" in sender:
        return "delivery_notice"
    if auto_submitted and auto_submitted != "no":
        return "automated"
    return "correspondence"


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
        content_type = optional_string(item.get("content_type"))[:255] or "application/octet-stream"
        declared_size = attachment_size(item.get("size"))
        record = EmailAttachment(
            organization_id=communication.organization_id,
            communication_record_id=communication.id,
            email_account_id=None,
            email_sender_alias_id=alias_id,
            provider_message_id=communication.provider_message_id or "",
            provider_attachment_id=attachment_id,
            filename=filename,
            content_type=content_type,
            size_bytes=declared_size or 0,
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
            if declared_size is not None and declared_size > settings.email_max_attachment_bytes:
                raise ResendAttachmentTooLargeError(
                    "The received attachment exceeds Stonegate's size limit."
                )
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
        except (ResendAttachmentTooLargeError, ValueError) as exc:
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
        select(Organization).where(Organization.name == settings.default_organization_name)
    )
    if organization is None:
        organization = db.scalar(select(Organization).order_by(Organization.created_at.asc()))
    if organization is None:
        raise RuntimeError("Resend webhook received before an organization was configured.")
    return organization


def resend_processing_enabled(settings: Settings) -> bool:
    return (
        settings.email_enabled
        and settings.email_provider == "resend"
        and not settings.email_configuration_blockers
    )


def received_email_is_known(
    db: Session,
    provider_message_id: str,
    *,
    processing_stale_before: datetime | None = None,
) -> bool:
    communication = db.scalar(
        select(CommunicationRecord.id).where(
            CommunicationRecord.provider == "resend",
            CommunicationRecord.provider_message_id == provider_message_id,
        )
    )
    if communication is not None:
        return True
    recovery_event = db.scalar(
        select(CommunicationProviderEvent).where(
            CommunicationProviderEvent.provider == "resend",
            CommunicationProviderEvent.external_event_id == f"recovery:{provider_message_id}",
        )
    )
    if recovery_event is None or recovery_event.processing_status == RESEND_DEAD_LETTER_STATUS:
        return False
    return not (
        processing_stale_before is not None
        and recovery_event.processing_status == "processing"
        and event_lease_expired(recovery_event, stale_before=processing_stale_before)
    )


def event_lease_expired(
    event: CommunicationProviderEvent,
    *,
    stale_before: datetime,
) -> bool:
    lease_timestamp = event.processing_started_at or event.updated_at
    if lease_timestamp.tzinfo is None:
        lease_timestamp = lease_timestamp.replace(tzinfo=UTC)
    else:
        lease_timestamp = lease_timestamp.astimezone(UTC)
    return lease_timestamp <= stale_before


def should_apply_status(
    current_status: str,
    new_status: str,
    current_at: datetime | None,
    event_at: datetime,
) -> bool:
    if current_status in TERMINAL_STATUSES:
        return new_status in TERMINAL_STATUSES and (current_at is None or event_at >= current_at)
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
        address.strip().lower() for _name, address in getaddresses(values) if address.strip()
    ]
    return list(dict.fromkeys(addresses))


def normalized_headers(value: object) -> dict[str, str]:
    if not isinstance(value, dict):
        return {}
    return {str(key).strip().lower(): optional_string(item) for key, item in value.items()}


def string_list(value: object) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        return [str(item) for item in value if str(item).strip()]
    return []


def received_message_body(message: dict[str, Any]) -> str:
    text = optional_string(message.get("text")).strip()
    html = optional_string(message.get("html"))
    if not html:
        return text or "(Email contained no readable message body.)"

    parser = _HtmlTextExtractor()
    parser.feed(html)
    body = text or "\n".join(parser.parts).strip()
    missing_links = [
        f"{label}: {href}" if label and label != href else href
        for label, href in parser.links
        if href not in body
    ]
    if missing_links:
        body = "\n".join(part for part in (body, *missing_links) if part).strip()
    if body:
        return body
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
