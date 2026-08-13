import hashlib
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.integrations.twilio_media import (
    TwilioMediaClient,
    TwilioMediaRejectedError,
    get_twilio_media_client,
    parse_twilio_inbound_media,
)
from app.models.foundation import (
    CommunicationProviderEvent,
    CommunicationRecord,
    EmailAttachment,
)
from app.services.document_storage import store_content

MEDIA_PENDING = "media_pending"
MEDIA_PROCESSING = "media_processing"
MEDIA_RETRY = "media_retry"
MEDIA_PROCESSED = "media_processed"
MEDIA_REJECTED = "media_rejected"
MEDIA_DEAD_LETTER = "media_dead_letter"


@dataclass(frozen=True)
class TwilioMmsClaim:
    event_id: UUID
    processing_token: UUID


def process_next_twilio_mms_media(
    db: Session,
    settings: Settings,
    *,
    client: TwilioMediaClient | None = None,
) -> UUID | None:
    claim = claim_next_twilio_mms_event(db, settings)
    if claim is None:
        return None
    event_id = claim.event_id
    owned_client = None if client is not None else get_twilio_media_client(settings)
    active_client = client or owned_client
    assert active_client is not None
    try:
        event = require_active_claim(db, claim)
        retain_twilio_mms_media(
            db,
            event,
            settings,
            client=active_client,
        )
        event = require_active_claim(db, claim)
        event.processing_status = MEDIA_PROCESSED
        event.processing_started_at = None
        event.processing_token = None
        event.next_attempt_at = None
        event.processed_at = datetime.now(UTC)
        event.error_message = None
        db.commit()
    except TwilioMediaRejectedError as exc:
        db.rollback()
        finish_rejected_twilio_mms_event(db, claim, exc)
    except Exception as exc:
        db.rollback()
        record_twilio_mms_failure(db, claim, exc, settings)
        raise
    finally:
        if owned_client is not None:
            owned_client.close()
    return event_id


def claim_next_twilio_mms_event(
    db: Session,
    settings: Settings,
) -> TwilioMmsClaim | None:
    while True:
        now = datetime.now(UTC)
        stale_before = now - timedelta(seconds=settings.worker_operation_stall_seconds)
        event = db.scalar(
            select(CommunicationProviderEvent)
            .where(
                CommunicationProviderEvent.provider == "twilio",
                CommunicationProviderEvent.event_type == "messaging.inbound",
                or_(
                    CommunicationProviderEvent.processing_status == MEDIA_PENDING,
                    and_(
                        CommunicationProviderEvent.processing_status == MEDIA_RETRY,
                        or_(
                            CommunicationProviderEvent.next_attempt_at.is_(None),
                            CommunicationProviderEvent.next_attempt_at <= now,
                        ),
                    ),
                    and_(
                        CommunicationProviderEvent.processing_status == MEDIA_PROCESSING,
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
            media_count = CommunicationProviderEvent.payload["NumMedia"].as_string()
            event = db.scalar(
                select(CommunicationProviderEvent)
                .where(
                    CommunicationProviderEvent.provider == "twilio",
                    CommunicationProviderEvent.event_type == "messaging.inbound",
                    CommunicationProviderEvent.processing_status == "processed",
                    media_count.is_not(None),
                    media_count != "0",
                )
                .order_by(CommunicationProviderEvent.received_at.asc())
                .limit(1)
                .with_for_update(skip_locked=True)
            )
        if event is None:
            return None
        if event.attempt_count >= settings.twilio_mms_max_attempts:
            event.processing_status = MEDIA_DEAD_LETTER
            event.processing_started_at = None
            event.processing_token = None
            event.next_attempt_at = None
            event.processed_at = now
            event.error_message = (
                event.error_message or "Twilio MMS recovery exhausted its attempts."
            )
            db.commit()
            continue
        token = uuid4()
        event.processing_status = MEDIA_PROCESSING
        event.processing_started_at = now
        event.processing_token = token
        event.next_attempt_at = None
        event.processed_at = None
        event.attempt_count += 1
        event.error_message = None
        db.commit()
        return TwilioMmsClaim(event_id=event.id, processing_token=token)


def retain_twilio_mms_media(
    db: Session,
    event: CommunicationProviderEvent,
    settings: Settings,
    *,
    client: TwilioMediaClient,
) -> None:
    items = parse_twilio_inbound_media(event.payload, settings)
    message_sid = str(event.payload.get("MessageSid", "")).strip()
    communication = db.scalar(
        select(CommunicationRecord).where(
            CommunicationRecord.organization_id == event.organization_id,
            CommunicationRecord.provider == "twilio",
            CommunicationRecord.provider_message_id == message_sid,
        )
    )
    if communication is None:
        raise TwilioMediaRejectedError("The Twilio MMS message is missing its Inbox record.")
    existing = db.scalars(
        select(EmailAttachment).where(
            EmailAttachment.organization_id == event.organization_id,
            EmailAttachment.communication_record_id == communication.id,
        )
    ).all()
    existing_by_provider_id = {item.provider_attachment_id: item for item in existing}
    total_bytes = sum(
        item.size_bytes
        for item in existing
        if (item.attachment_metadata or {}).get("source") == "twilio_mms"
    )
    for media in items:
        if media.media_sid in existing_by_provider_id:
            continue
        downloaded = client.download(media)
        if total_bytes + len(downloaded.content) > settings.twilio_mms_max_total_bytes:
            raise TwilioMediaRejectedError("The MMS photos exceed Stonegate's total size limit.")
        attachment = EmailAttachment(
            organization_id=event.organization_id,
            communication_record_id=communication.id,
            email_account_id=None,
            email_sender_alias_id=None,
            provider_message_id=message_sid,
            provider_attachment_id=media.media_sid,
            filename=downloaded.filename,
            content_type=downloaded.content_type,
            size_bytes=len(downloaded.content),
            content_id=None,
            disposition="inline",
            sha256=None,
            content_data=None,
            storage_provider=None,
            storage_key=None,
            malware_scan_status=None,
            retention_until=None,
            attachment_metadata={
                "source": "twilio_mms",
                "media_index": media.index,
                "storage_status": "pending",
            },
        )
        db.add(attachment)
        db.flush()
        try:
            stored = store_content(
                organization_id=event.organization_id,
                namespace="message-attachments",
                record_id=attachment.id,
                file_name=downloaded.filename,
                content_type=downloaded.content_type,
                content=downloaded.content,
                settings=settings,
            )
        except ValueError as exc:
            raise TwilioMediaRejectedError(str(exc)) from exc
        attachment.sha256 = hashlib.sha256(downloaded.content).hexdigest()
        attachment.content_data = stored.database_bytes
        attachment.storage_provider = stored.provider
        attachment.storage_key = stored.key
        attachment.malware_scan_status = stored.malware_scan_status
        attachment.retention_until = stored.retention_until
        attachment.attachment_metadata = {
            "source": "twilio_mms",
            "media_index": media.index,
            "storage_status": "retained",
        }
        total_bytes += len(downloaded.content)
        db.commit()

    refreshed_event = db.get(CommunicationProviderEvent, event.id)
    if refreshed_event is None:
        raise RuntimeError("The Twilio MMS provider event disappeared.")
    refreshed_event.payload = {
        **refreshed_event.payload,
        "_mms": {
            "stored_count": len(items),
            "stored_bytes": total_bytes,
        },
    }


def require_active_claim(db: Session, claim: TwilioMmsClaim) -> CommunicationProviderEvent:
    event = db.scalar(
        select(CommunicationProviderEvent)
        .where(
            CommunicationProviderEvent.id == claim.event_id,
            CommunicationProviderEvent.processing_status == MEDIA_PROCESSING,
            CommunicationProviderEvent.processing_token == claim.processing_token,
        )
        .with_for_update()
    )
    if event is None:
        raise RuntimeError("The Twilio MMS processing lease was lost.")
    return event


def finish_rejected_twilio_mms_event(
    db: Session,
    claim: TwilioMmsClaim,
    exc: Exception,
) -> None:
    event = require_active_claim(db, claim)
    event.processing_status = MEDIA_REJECTED
    event.processing_started_at = None
    event.processing_token = None
    event.next_attempt_at = None
    event.processed_at = datetime.now(UTC)
    event.error_message = str(exc)[:2000]
    db.commit()


def record_twilio_mms_failure(
    db: Session,
    claim: TwilioMmsClaim,
    exc: Exception,
    settings: Settings,
) -> None:
    event = require_active_claim(db, claim)
    now = datetime.now(UTC)
    event.processing_started_at = None
    event.processing_token = None
    event.error_message = str(exc)[:2000]
    if event.attempt_count >= settings.twilio_mms_max_attempts:
        event.processing_status = MEDIA_DEAD_LETTER
        event.next_attempt_at = None
        event.processed_at = now
    else:
        retry_delay = min(
            settings.worker_retry_base_seconds * (2 ** max(0, event.attempt_count - 1)),
            settings.worker_retry_max_seconds,
        )
        event.processing_status = MEDIA_RETRY
        event.next_attempt_at = now + timedelta(seconds=retry_delay)
        event.processed_at = None
    db.commit()
