from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.auth import Principal
from app.domain.rbac import PermissionKeys
from app.models.foundation import (
    AuditEvent,
    CommunicationProviderEvent,
    Conversation,
    EmailSenderAlias,
    Role,
    RoleAssignment,
    Team,
    User,
)
from app.schemas.email import (
    EmailAdminOptionsRead,
    EmailAdminTeamRead,
    EmailAdminUserRead,
    EmailDeadLetterListResponse,
    EmailDeadLetterRead,
    EmailDeadLetterRequeueRequest,
    EmailRoutingExceptionListResponse,
    EmailRoutingExceptionRead,
    EmailRoutingResolutionRequest,
)
from app.services.resend_email_events import inbound_visibility_scope

ROUTING_EXCEPTION_STATUSES = ("ambiguous", "unmatched")
RESEND_DEAD_LETTER_STATUS = "dead_letter"


def get_email_admin_options(
    db: Session,
    principal: Principal,
) -> EmailAdminOptionsRead:
    require_email_manager(principal)
    users = db.scalars(
        select(User)
        .where(
            User.organization_id == principal.organization_id,
            User.is_active.is_(True),
        )
        .order_by(User.display_name.asc(), User.email.asc())
    ).all()
    role_rows = db.execute(
        select(RoleAssignment.user_id, Role.key)
        .join(Role, Role.id == RoleAssignment.role_id)
        .where(RoleAssignment.organization_id == principal.organization_id)
    ).all()
    role_keys_by_user: dict[UUID, list[str]] = {}
    for user_id, role_key in role_rows:
        role_keys_by_user.setdefault(user_id, []).append(role_key)
    teams = db.scalars(
        select(Team)
        .where(
            Team.organization_id == principal.organization_id,
            Team.is_active.is_(True),
        )
        .order_by(Team.name.asc())
    ).all()
    return EmailAdminOptionsRead(
        users=[
            EmailAdminUserRead(
                id=user.id,
                email=user.email,
                display_name=user.display_name,
                role_keys=sorted(role_keys_by_user.get(user.id, [])),
            )
            for user in users
        ],
        teams=[
            EmailAdminTeamRead(
                id=team.id,
                name=team.name,
                team_type=team.team_type,
            )
            for team in teams
        ],
    )


def list_email_routing_exceptions(
    db: Session,
    principal: Principal,
) -> EmailRoutingExceptionListResponse:
    require_email_manager(principal)
    events = db.scalars(
        select(CommunicationProviderEvent)
        .where(
            CommunicationProviderEvent.organization_id == principal.organization_id,
            CommunicationProviderEvent.provider == "resend",
            CommunicationProviderEvent.event_type == "email.received",
            CommunicationProviderEvent.processing_status.in_(ROUTING_EXCEPTION_STATUSES),
        )
        .order_by(CommunicationProviderEvent.received_at.desc())
        .limit(100)
    ).all()
    return EmailRoutingExceptionListResponse(
        items=[routing_exception_to_read(event) for event in events]
    )


def resolve_email_routing_exception(
    db: Session,
    principal: Principal,
    event_id: UUID,
    payload: EmailRoutingResolutionRequest,
) -> EmailRoutingExceptionRead | None:
    require_email_manager(principal)
    event = db.scalar(
        select(CommunicationProviderEvent).where(
            CommunicationProviderEvent.organization_id == principal.organization_id,
            CommunicationProviderEvent.id == event_id,
            CommunicationProviderEvent.provider == "resend",
            CommunicationProviderEvent.event_type == "email.received",
            CommunicationProviderEvent.processing_status.in_(ROUTING_EXCEPTION_STATUSES),
        )
    )
    if event is None:
        return None
    conversation = db.scalar(
        select(Conversation).where(
            Conversation.organization_id == principal.organization_id,
            Conversation.id == payload.conversation_id,
        )
    )
    if conversation is None:
        raise ValueError("Select a Stonegate conversation from this workspace.")
    enforce_restricted_routing_destination(db, principal.organization_id, event, conversation)
    previous_status = event.processing_status
    previous_routing = routing_payload(event.payload)
    event.payload = {
        **event.payload,
        "_routing": {
            **previous_routing,
            "status": "matched",
            "reason": "Manually assigned by a Stonegate email administrator.",
            "conversation_id": str(conversation.id),
            "candidate_conversation_ids": [str(conversation.id)],
            "manually_routed_by_user_id": str(principal.user_id),
            "manually_routed_at": datetime.now(UTC).isoformat(),
        },
    }
    event.conversation_id = conversation.id
    event.processing_status = "received"
    event.processed_at = None
    event.attempt_count = 0
    event.next_attempt_at = None
    event.processing_started_at = None
    event.processing_token = None
    event.error_message = None
    db.add(
        AuditEvent(
            organization_id=principal.organization_id,
            actor_user_id=principal.user_id,
            actor_type="user",
            action="email.routing_exception_resolved",
            entity_type="communication_provider_event",
            entity_id=event.id,
            previous_value={
                "processing_status": previous_status,
                "routing": previous_routing,
            },
            new_value={
                "processing_status": "received",
                "conversation_id": str(conversation.id),
            },
            reason="Owner manually assigned an inbound email conversation",
        )
    )
    db.commit()
    return routing_exception_to_read(event)


def list_email_dead_letters(
    db: Session,
    principal: Principal,
) -> EmailDeadLetterListResponse:
    require_email_manager(principal)
    events = db.scalars(
        select(CommunicationProviderEvent)
        .where(
            CommunicationProviderEvent.organization_id == principal.organization_id,
            CommunicationProviderEvent.provider == "resend",
            CommunicationProviderEvent.processing_status == RESEND_DEAD_LETTER_STATUS,
        )
        .order_by(CommunicationProviderEvent.processed_at.desc())
        .limit(100)
    ).all()
    return EmailDeadLetterListResponse(items=[dead_letter_to_read(event) for event in events])


def requeue_email_dead_letter(
    db: Session,
    principal: Principal,
    event_id: UUID,
    payload: EmailDeadLetterRequeueRequest,
) -> EmailDeadLetterRead | None:
    require_email_manager(principal)
    event = db.scalar(
        select(CommunicationProviderEvent)
        .where(
            CommunicationProviderEvent.organization_id == principal.organization_id,
            CommunicationProviderEvent.id == event_id,
            CommunicationProviderEvent.provider == "resend",
            CommunicationProviderEvent.processing_status == RESEND_DEAD_LETTER_STATUS,
        )
        .with_for_update()
    )
    if event is None:
        return None
    previous_value = {
        "processing_status": event.processing_status,
        "attempt_count": event.attempt_count,
        "error_message": event.error_message,
        "processed_at": event.processed_at.isoformat() if event.processed_at else None,
    }
    now = datetime.now(UTC)
    event.processing_status = "retry"
    event.processed_at = None
    event.attempt_count = 0
    event.next_attempt_at = now
    event.processing_started_at = None
    event.processing_token = None
    event.error_message = None
    db.add(
        AuditEvent(
            organization_id=principal.organization_id,
            actor_user_id=principal.user_id,
            actor_type="user",
            action="email.dead_letter_requeued",
            entity_type="communication_provider_event",
            entity_id=event.id,
            previous_value=previous_value,
            new_value={
                "processing_status": "retry",
                "attempt_count": 0,
                "next_attempt_at": now.isoformat(),
            },
            reason=payload.reason.strip(),
        )
    )
    db.commit()
    return dead_letter_to_read(event)


def routing_exception_to_read(
    event: CommunicationProviderEvent,
) -> EmailRoutingExceptionRead:
    data = event.payload.get("data")
    normalized_data = data if isinstance(data, dict) else {}
    routing = routing_payload(event.payload)
    return EmailRoutingExceptionRead(
        id=event.id,
        processing_status=event.processing_status,
        provider_message_id=string_value(normalized_data.get("email_id")),
        sender=string_value(normalized_data.get("from")),
        recipients=string_list(normalized_data.get("to")),
        subject=string_value(normalized_data.get("subject")) or None,
        received_at=event.received_at,
        reason=string_value(routing.get("reason")) or "The email needs manual routing.",
        candidate_conversation_ids=uuid_list(routing.get("candidate_conversation_ids")),
    )


def dead_letter_to_read(event: CommunicationProviderEvent) -> EmailDeadLetterRead:
    data = event.payload.get("data")
    normalized_data = data if isinstance(data, dict) else {}
    return EmailDeadLetterRead(
        id=event.id,
        event_type=event.event_type,
        provider_message_id=string_value(normalized_data.get("email_id")),
        sender=string_value(normalized_data.get("from")),
        recipients=string_list(normalized_data.get("to")),
        subject=string_value(normalized_data.get("subject")) or None,
        received_at=event.received_at,
        processed_at=event.processed_at,
        attempt_count=event.attempt_count,
        error_message=event.error_message,
        processing_status=event.processing_status,
    )


def enforce_restricted_routing_destination(
    db: Session,
    organization_id: UUID,
    event: CommunicationProviderEvent,
    conversation: Conversation,
) -> None:
    routing = routing_payload(event.payload)
    alias_ids = uuid_list(routing.get("email_sender_alias_ids"))
    if not alias_ids:
        return
    aliases = db.scalars(
        select(EmailSenderAlias).where(
            EmailSenderAlias.organization_id == organization_id,
            EmailSenderAlias.id.in_(alias_ids),
        )
    ).all()
    if any(inbound_visibility_scope(alias) == "restricted" for alias in aliases) and (
        conversation.visibility_scope != "restricted"
    ):
        raise ValueError(
            "Restricted mailbox email can only be assigned to a restricted conversation."
        )


def routing_payload(payload: dict[str, Any]) -> dict[str, Any]:
    routing = payload.get("_routing")
    return routing if isinstance(routing, dict) else {}


def string_list(value: object) -> list[str]:
    if isinstance(value, list):
        return [str(item) for item in value if str(item).strip()]
    if isinstance(value, str) and value.strip():
        return [value.strip()]
    return []


def uuid_list(value: object) -> list[UUID]:
    values = string_list(value)
    result: list[UUID] = []
    for item in values:
        try:
            result.append(UUID(item))
        except ValueError:
            continue
    return result


def string_value(value: object) -> str:
    return str(value).strip() if value is not None else ""


def require_email_manager(principal: Principal) -> None:
    if PermissionKeys.MANAGE_EMAIL_ACCOUNTS not in principal.permission_keys:
        raise PermissionError("Email administration requires owner or manager access.")
