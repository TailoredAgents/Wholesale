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
            ConsentRecord.channel.in_(("sms", "phone")),
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
    within_allowed_hours = is_within_allowed_hours(settings, now=now)
    blockers: list[str] = []
    if recipient is None:
        blockers.append("A valid seller mobile number is required.")
    if consent_status != "granted":
        blockers.append("Recorded SMS consent is required.")
    if suppression is not None:
        blockers.append("This number is suppressed from text messaging.")
    if not within_allowed_hours:
        blockers.append("Text messaging is outside Stonegate's allowed contact hours.")
    if not settings.twilio_sms_configured:
        blockers.append("Twilio SMS is not configured.")
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
) -> VoiceEligibility:
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
            ConsentRecord.channel.in_(("phone", "sms")),
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
    within_allowed_hours = is_within_allowed_hours(settings, now=now)
    blockers: list[str] = []
    if recipient is None:
        blockers.append("A valid seller phone number is required.")
    if consent_status != "granted":
        blockers.append("Recorded phone contact permission is required.")
    if suppression is not None:
        blockers.append("This number is suppressed from phone calls.")
    if not within_allowed_hours:
        blockers.append("Calling is outside Stonegate's allowed contact hours.")
    if not settings.twilio_voice_configured:
        blockers.append("Twilio Voice is not configured.")
    return VoiceEligibility(
        can_call=not blockers,
        recipient=recipient,
        consent_status=consent_status,
        is_suppressed=suppression is not None,
        provider_configured=settings.twilio_voice_configured,
        within_allowed_hours=within_allowed_hours,
        blockers=tuple(blockers),
    )


def phone_lookup_values(value: str) -> tuple[str, ...]:
    digits = "".join(character for character in value if character.isdigit())
    values = {digits}
    if len(digits) == 11 and digits.startswith("1"):
        values.add(digits[1:])
    return tuple(value for value in values if value)


def is_within_allowed_hours(settings: Settings, *, now: datetime | None = None) -> bool:
    current = now or datetime.now(UTC)
    try:
        local_time = current.astimezone(ZoneInfo(settings.twilio_sms_timezone))
    except ZoneInfoNotFoundError:
        return False
    return (
        settings.twilio_sms_allowed_start_hour
        <= local_time.hour
        < settings.twilio_sms_allowed_end_hour
    )
