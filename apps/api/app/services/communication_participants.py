from collections.abc import Iterable
from email.utils import getaddresses
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.foundation import (
    CommunicationParticipant,
    CommunicationRecord,
    EmailSenderAlias,
)


def record_email_participants(
    db: Session,
    communication: CommunicationRecord,
    *,
    from_values: object,
    to_values: object,
    cc_values: object = None,
    bcc_values: object = None,
    external_contact_id: UUID | None,
    external_roles: set[str],
    external_contact_email: str | None = None,
    sender_user_id: UUID | None = None,
    sender_alias_ids: Iterable[UUID] = (),
    source: str,
) -> list[CommunicationParticipant]:
    if communication.channel != "email" or communication.conversation_id is None:
        raise ValueError("Structured email participants require a conversation email record.")

    alias_ids = list(dict.fromkeys(sender_alias_ids))
    aliases = (
        db.scalars(
            select(EmailSenderAlias).where(
                EmailSenderAlias.organization_id == communication.organization_id,
                EmailSenderAlias.id.in_(alias_ids),
            )
        ).all()
        if alias_ids
        else []
    )
    alias_by_address = {alias.email_address.strip().lower(): alias.id for alias in aliases}
    existing_keys: set[tuple[str, str]] = {
        (role, normalized_email)
        for role, normalized_email in db.execute(
            select(
                CommunicationParticipant.participant_role,
                CommunicationParticipant.normalized_email,
            ).where(
                CommunicationParticipant.communication_record_id == communication.id,
            )
        ).all()
    }
    created: list[CommunicationParticipant] = []
    normalized_external_email = (
        external_contact_email.strip().lower() if external_contact_email else None
    )
    role_values = {
        "from": from_values,
        "to": to_values,
        "cc": cc_values,
        "bcc": bcc_values,
    }
    for role, raw_values in role_values.items():
        seen: set[str] = set()
        for display_name, address in getaddresses(_string_values(raw_values)):
            normalized = address.strip().lower()
            if not _valid_email(normalized) or normalized in seen:
                continue
            seen.add(normalized)
            key = (role, normalized)
            if key in existing_keys:
                continue
            participant = CommunicationParticipant(
                organization_id=communication.organization_id,
                communication_record_id=communication.id,
                conversation_id=communication.conversation_id,
                contact_id=(
                    external_contact_id
                    if role in external_roles
                    and (
                        normalized_external_email is None or normalized == normalized_external_email
                    )
                    else None
                ),
                user_id=sender_user_id if role == "from" else None,
                email_sender_alias_id=alias_by_address.get(normalized),
                participant_role=role,
                email_address=address.strip(),
                normalized_email=normalized,
                display_name=display_name.strip() or None,
                participant_metadata={"source": source},
            )
            db.add(participant)
            created.append(participant)
            existing_keys.add(key)
    db.flush()
    return created


def _string_values(value: object) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, Iterable) and not isinstance(value, (bytes, dict)):
        return [item for item in value if isinstance(item, str)]
    return []


def _valid_email(value: str) -> bool:
    local, separator, domain = value.rpartition("@")
    return bool(separator and local and "." in domain and not any(char.isspace() for char in value))
