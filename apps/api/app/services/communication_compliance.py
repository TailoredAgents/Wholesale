from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.models.foundation import (
    ConsentRecord,
    Contact,
    ContactMethod,
    Conversation,
    SuppressionRecord,
)


@dataclass(frozen=True)
class SmsEligibility:
    can_send: bool
    recipient: str | None
    consent_status: str
    is_suppressed: bool
    provider_configured: bool
    within_allowed_hours: bool
    blockers: tuple[str, ...]


@dataclass(frozen=True)
class VoiceEligibility:
    can_call: bool
    recipient: str | None
    consent_status: str
    is_suppressed: bool
    provider_configured: bool
    within_allowed_hours: bool
    blockers: tuple[str, ...]


def evaluate_contact_eligibility_batch(
    db: Session,
    contacts: Iterable[Contact],
    *,
    settings: Settings | None = None,
    now: datetime | None = None,
    require_permission: bool = True,
) -> dict[UUID, tuple[SmsEligibility, VoiceEligibility]]:
    """Evaluate a contact collection with three shared queries instead of six per contact."""

    contact_list = list(contacts)
    if not contact_list:
        return {}
    settings = settings or get_settings()
    organization_id = contact_list[0].organization_id
    contact_ids = {contact.id for contact in contact_list}
    if any(contact.organization_id != organization_id for contact in contact_list):
        raise ValueError("Communication eligibility contacts must share an organization.")

    phone_methods = list(
        db.scalars(
            select(ContactMethod)
            .where(
                ContactMethod.organization_id == organization_id,
                ContactMethod.contact_id.in_(contact_ids),
                ContactMethod.method_type == "phone",
            )
            .order_by(
                ContactMethod.contact_id.asc(),
                ContactMethod.is_primary.desc(),
                ContactMethod.created_at.asc(),
            )
        ).all()
    )
    recipients: dict[UUID, str | None] = dict.fromkeys(contact_ids)
    for method in phone_methods:
        if recipients[method.contact_id] is None:
            recipients[method.contact_id] = format_e164(method.normalized_value)

    consent_records = list(
        db.scalars(
            select(ConsentRecord)
            .where(
                ConsentRecord.organization_id == organization_id,
                ConsentRecord.contact_id.in_(contact_ids),
                ConsentRecord.channel.in_(("sms", "phone")),
            )
            .order_by(ConsentRecord.created_at.desc(), ConsentRecord.id.desc())
        ).all()
    )
    consent_statuses: dict[tuple[UUID, str], str] = {}
    for consent in consent_records:
        key = (consent.contact_id, consent.channel)
        if key in consent_statuses:
            continue
        recipient = recipients[consent.contact_id]
        if consent.normalized_address in (None, recipient):
            consent_statuses[key] = consent.status

    normalized_recipients = {recipient for recipient in recipients.values() if recipient}
    suppressions = (
        list(
            db.scalars(
                select(SuppressionRecord).where(
                    SuppressionRecord.organization_id == organization_id,
                    SuppressionRecord.channel.in_(("sms", "phone", "all")),
                    SuppressionRecord.normalized_address.in_(normalized_recipients),
                    SuppressionRecord.status == "active",
                )
            ).all()
        )
        if normalized_recipients
        else []
    )
    suppression_keys = {
        (suppression.channel, suppression.normalized_address)
        for suppression in suppressions
    }
    sms_within_hours = is_within_sms_allowed_hours(settings, now=now)
    voice_within_hours = is_within_voice_allowed_hours(settings, now=now)
    return {
        contact.id: (
            _sms_eligibility_from_state(
                settings=settings,
                recipient=recipients[contact.id],
                consent_status=consent_statuses.get((contact.id, "sms"), "missing"),
                is_suppressed=(
                    ("sms", recipients[contact.id]) in suppression_keys
                    or ("all", recipients[contact.id]) in suppression_keys
                ),
                within_allowed_hours=sms_within_hours,
                require_permission=require_permission,
            ),
            _voice_eligibility_from_state(
                settings=settings,
                recipient=recipients[contact.id],
                consent_status=consent_statuses.get((contact.id, "phone"), "missing"),
                is_suppressed=(
                    ("phone", recipients[contact.id]) in suppression_keys
                    or ("all", recipients[contact.id]) in suppression_keys
                ),
                within_allowed_hours=voice_within_hours,
                require_permission=require_permission,
            ),
        )
        for contact in contact_list
    }


def evaluate_sms_eligibility(
    db: Session,
    contact: Contact,
    *,
    settings: Settings | None = None,
    now: datetime | None = None,
    require_permission: bool = True,
) -> SmsEligibility:
    settings = settings or get_settings()
    phone_method = db.scalar(
        select(ContactMethod)
        .where(
            ContactMethod.organization_id == contact.organization_id,
            ContactMethod.contact_id == contact.id,
            ContactMethod.method_type == "phone",
        )
        .order_by(ContactMethod.is_primary.desc(), ContactMethod.created_at.asc())
    )
    recipient = format_e164(phone_method.normalized_value) if phone_method else None
    latest_consent = db.scalar(
        select(ConsentRecord)
        .where(
            ConsentRecord.organization_id == contact.organization_id,
            ConsentRecord.contact_id == contact.id,
            ConsentRecord.channel == "sms",
            (
                (ConsentRecord.normalized_address == recipient)
                | ConsentRecord.normalized_address.is_(None)
            ),
        )
        .order_by(ConsentRecord.created_at.desc(), ConsentRecord.id.desc())
    )
    consent_status = latest_consent.status if latest_consent else "missing"
    suppression = (
        db.scalar(
            select(SuppressionRecord).where(
                SuppressionRecord.organization_id == contact.organization_id,
                SuppressionRecord.channel.in_(("sms", "all")),
                SuppressionRecord.normalized_address == recipient,
                SuppressionRecord.status == "active",
            )
        )
        if recipient
        else None
    )
    within_allowed_hours = is_within_sms_allowed_hours(settings, now=now)
    return _sms_eligibility_from_state(
        settings=settings,
        recipient=recipient,
        consent_status=consent_status,
        is_suppressed=suppression is not None,
        within_allowed_hours=within_allowed_hours,
        require_permission=require_permission,
    )


def _sms_eligibility_from_state(
    *,
    settings: Settings,
    recipient: str | None,
    consent_status: str,
    is_suppressed: bool,
    within_allowed_hours: bool,
    require_permission: bool,
) -> SmsEligibility:
    blockers: list[str] = []
    if recipient is None:
        blockers.append("A valid recipient mobile number is required.")
    if require_permission and consent_status != "granted":
        blockers.append("Recorded SMS consent is required.")
    if is_suppressed:
        blockers.append("This number is suppressed from text messaging.")
    if not within_allowed_hours:
        blockers.append("Text messaging is outside Stonegate's allowed contact hours.")
    if not settings.twilio_sms_configured:
        missing = "; ".join(settings.twilio_sms_configuration_blockers)
        blockers.append(f"Twilio SMS is not configured. Missing: {missing}.")
    return SmsEligibility(
        can_send=not blockers,
        recipient=recipient,
        consent_status=consent_status,
        is_suppressed=is_suppressed,
        provider_configured=settings.twilio_sms_configured,
        within_allowed_hours=within_allowed_hours,
        blockers=tuple(blockers),
    )


def format_e164(value: str | None) -> str | None:
    if not value:
        return None
    digits = "".join(character for character in value if character.isdigit())
    if len(digits) == 10:
        return f"+1{digits}"
    if len(digits) == 11 and digits.startswith("1"):
        return f"+{digits}"
    if 11 <= len(digits) <= 15:
        return f"+{digits}"
    return None


def evaluate_voice_eligibility(
    db: Session,
    contact: Contact,
    *,
    settings: Settings | None = None,
    now: datetime | None = None,
    require_permission: bool = True,
    requested_phone_number: str | None = None,
) -> VoiceEligibility:
    settings = settings or get_settings()
    requested_recipient = (
        format_e164(requested_phone_number) if requested_phone_number is not None else None
    )
    phone_method_query = select(ContactMethod).where(
        ContactMethod.organization_id == contact.organization_id,
        ContactMethod.contact_id == contact.id,
        ContactMethod.method_type == "phone",
    )
    if requested_phone_number is not None:
        phone_method_query = phone_method_query.where(
            ContactMethod.normalized_value.in_(
                phone_lookup_values(requested_recipient or requested_phone_number)
            )
        )
    phone_method = db.scalar(
        phone_method_query.order_by(
            ContactMethod.is_primary.desc(),
            ContactMethod.created_at.asc(),
        )
    )
    recipient = (
        requested_recipient
        if requested_recipient is not None and phone_method is not None
        else format_e164(phone_method.normalized_value)
        if phone_method is not None
        else None
    )
    latest_consent = db.scalar(
        select(ConsentRecord)
        .where(
            ConsentRecord.organization_id == contact.organization_id,
            ConsentRecord.contact_id == contact.id,
            ConsentRecord.channel == "phone",
            (
                (ConsentRecord.normalized_address == recipient)
                | ConsentRecord.normalized_address.is_(None)
            ),
        )
        .order_by(ConsentRecord.created_at.desc(), ConsentRecord.id.desc())
    )
    consent_status = latest_consent.status if latest_consent else "missing"
    suppression = (
        db.scalar(
            select(SuppressionRecord).where(
                SuppressionRecord.organization_id == contact.organization_id,
                SuppressionRecord.channel.in_(("phone", "all")),
                SuppressionRecord.normalized_address == recipient,
                SuppressionRecord.status == "active",
            )
        )
        if recipient
        else None
    )
    within_allowed_hours = is_within_voice_allowed_hours(settings, now=now)
    return _voice_eligibility_from_state(
        settings=settings,
        recipient=recipient,
        consent_status=consent_status,
        is_suppressed=suppression is not None,
        within_allowed_hours=within_allowed_hours,
        require_permission=require_permission,
    )


def _voice_eligibility_from_state(
    *,
    settings: Settings,
    recipient: str | None,
    consent_status: str,
    is_suppressed: bool,
    within_allowed_hours: bool,
    require_permission: bool,
) -> VoiceEligibility:
    blockers: list[str] = []
    if recipient is None:
        blockers.append("A valid seller phone number is required.")
    if require_permission and consent_status != "granted":
        blockers.append("Recorded phone contact permission is required.")
    if is_suppressed:
        blockers.append("This number is suppressed from phone calls.")
    # Voice calls launched here are deliberate, human-initiated calls from an assigned Inbox
    # conversation. Keep suppression, provider, and line-authorization gates, but do not prevent
    # staff from returning a seller's call after the configured inbound coverage window.
    # Automated calling must enforce permission and contact-hour policy before using Voice.
    if not settings.twilio_voice_configured:
        blockers.append(
            "Twilio Voice needs: " + ", ".join(settings.twilio_voice_configuration_blockers) + "."
        )
    return VoiceEligibility(
        can_call=not blockers,
        recipient=recipient,
        consent_status=consent_status,
        is_suppressed=is_suppressed,
        provider_configured=settings.twilio_voice_configured,
        within_allowed_hours=within_allowed_hours,
        blockers=tuple(blockers),
    )


def business_voice_permission_not_required(
    conversation: Conversation,
    contact: Contact,
) -> bool:
    """Recognize a deliberate B2B Quick Dial call without fabricating consent evidence.

    A generic inbound caller or email contact is not automatically a verified business call.
    The explicit Quick Dial preparation marker is the evidence that staff intentionally chose
    the business-call workflow. Recorded permission remains visible as an advisory label, while
    suppression and provider controls remain enforceable in ``evaluate_voice_eligibility``.
    """

    return business_voice_requested_phone_number(conversation, contact) is not None


def business_voice_requested_phone_number(
    conversation: Conversation,
    contact: Contact,
) -> str | None:
    quick_dial = (conversation.conversation_metadata or {}).get("quick_dial")
    if not (
        conversation.conversation_type == "general"
        and contact.contact_type == "business_contact"
        and isinstance(quick_dial, dict)
        and quick_dial.get("prepared_by_user_id")
    ):
        return None
    phone_number = quick_dial.get("phone_number")
    return phone_number if isinstance(phone_number, str) and format_e164(phone_number) else None


def phone_lookup_values(value: str) -> tuple[str, ...]:
    digits = "".join(character for character in value if character.isdigit())
    values = {digits}
    if len(digits) == 11 and digits.startswith("1"):
        values.add(digits[1:])
        values.add(f"+{digits}")
    elif len(digits) == 10:
        values.add(f"1{digits}")
        values.add(f"+1{digits}")
    return tuple(value for value in values if value)


def is_within_sms_allowed_hours(
    settings: Settings,
    *,
    now: datetime | None = None,
) -> bool:
    return is_within_contact_hours(
        timezone=settings.twilio_sms_timezone,
        start_hour=settings.twilio_sms_allowed_start_hour,
        end_hour=settings.twilio_sms_allowed_end_hour,
        now=now,
    )


def is_within_voice_allowed_hours(
    settings: Settings,
    *,
    now: datetime | None = None,
) -> bool:
    return is_within_contact_hours(
        timezone=settings.twilio_voice_timezone,
        start_hour=settings.twilio_voice_allowed_start_hour,
        end_hour=settings.twilio_voice_allowed_end_hour,
        now=now,
    )


def is_within_contact_hours(
    *,
    timezone: str,
    start_hour: int,
    end_hour: int,
    now: datetime | None = None,
) -> bool:
    current = now or datetime.now(UTC)
    try:
        local_time = current.astimezone(ZoneInfo(timezone))
    except ZoneInfoNotFoundError:
        return False
    return start_hour <= local_time.hour < end_hour
