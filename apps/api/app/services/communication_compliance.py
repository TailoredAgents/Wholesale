from dataclasses import dataclass
from datetime import UTC, datetime
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


def evaluate_sms_eligibility(
    db: Session,
    contact: Contact,
    *,
    settings: Settings | None = None,
    now: datetime | None = None,
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
                SuppressionRecord.channel == "sms",
                SuppressionRecord.normalized_address == recipient,
                SuppressionRecord.status == "active",
            )
        )
        if recipient
        else None
    )
    within_allowed_hours = is_within_sms_allowed_hours(settings, now=now)
    blockers: list[str] = []
    if recipient is None:
        blockers.append("A valid recipient mobile number is required.")
    if consent_status != "granted":
        blockers.append("Recorded SMS consent is required.")
    if suppression is not None:
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
        is_suppressed=suppression is not None,
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
    blockers: list[str] = []
    if recipient is None:
        blockers.append("A valid seller phone number is required.")
    if consent_status != "granted" and (require_permission or latest_consent is not None):
        blockers.append("Recorded phone contact permission is required.")
    if suppression is not None:
        blockers.append("This number is suppressed from phone calls.")
    # Voice calls launched here are deliberate, human-initiated calls from an assigned Inbox
    # conversation. Keep suppression, permission, provider, and line-authorization gates, but do
    # not prevent staff from returning a seller's call after the configured inbound coverage
    # window. Automated calling must enforce its own contact-hour policy before using Voice.
    if not settings.twilio_voice_configured:
        blockers.append(
            "Twilio Voice needs: " + ", ".join(settings.twilio_voice_configuration_blockers) + "."
        )
    return VoiceEligibility(
        can_call=not blockers,
        recipient=recipient,
        consent_status=consent_status,
        is_suppressed=suppression is not None,
        provider_configured=settings.twilio_voice_configured,
        within_allowed_hours=within_allowed_hours,
        blockers=tuple(blockers),
    )


def business_voice_permission_not_required(
    conversation: Conversation,
    contact: Contact,
) -> bool:
    """Allow deliberate B2B Quick Dial calls without fabricating consent evidence.

    A generic inbound caller or email contact is not automatically a verified business call.
    The explicit Quick Dial preparation marker is the evidence that staff intentionally chose
    the business-call workflow. An existing denial/revocation still blocks the call in
    ``evaluate_voice_eligibility``.
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
