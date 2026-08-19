from uuid import UUID

from sqlalchemy import and_, exists, literal, or_, select
from sqlalchemy.orm import Session, aliased
from sqlalchemy.sql.elements import ColumnElement

from app.core.auth import Principal
from app.domain.rbac import PermissionKeys
from app.models.foundation import (
    CallRecord,
    CallRecording,
    CommunicationRecord,
    Conversation,
    ConversationWatcher,
    EmailSenderAlias,
    EmailSenderGrant,
    ProspectingAttempt,
    Role,
    RoleAssignment,
    TeamMembership,
)

OWNER_MAILBOX_ROLE_KEYS = {"owner", "founder_operator", "ceo"}


def get_authorized_recording(
    db: Session,
    principal: Principal,
    recording_id: UUID,
) -> CallRecording | None:
    """Return a recording only inside its exact warm or cold assignment scope."""

    manager = PermissionKeys.MANAGE_ACQUISITION_OPERATIONS in principal.permission_keys
    can_view_all_conversations = PermissionKeys.VIEW_CONVERSATIONS in principal.permission_keys
    owner_mailbox_access = (
        db.scalar(
            select(Role.id)
            .join(RoleAssignment, RoleAssignment.role_id == Role.id)
            .where(
                RoleAssignment.organization_id == principal.organization_id,
                RoleAssignment.user_id == principal.user_id,
                Role.key.in_(OWNER_MAILBOX_ROLE_KEYS),
            )
            .limit(1)
        )
        is not None
    )

    linked_communication = aliased(CommunicationRecord)
    linked_conversation = aliased(Conversation)
    linked_conversation_access: list[ColumnElement[bool]] = [
        linked_conversation.assigned_user_id == principal.user_id,
        linked_conversation.assigned_team_id.in_(
            select(TeamMembership.team_id).where(
                TeamMembership.organization_id == principal.organization_id,
                TeamMembership.user_id == principal.user_id,
            )
        ),
        linked_conversation.id.in_(
            select(ConversationWatcher.conversation_id).where(
                ConversationWatcher.organization_id == principal.organization_id,
                ConversationWatcher.user_id == principal.user_id,
            )
        ),
        linked_conversation.source_alias_id.in_(
            select(EmailSenderGrant.email_sender_alias_id).where(
                EmailSenderGrant.organization_id == principal.organization_id,
                EmailSenderGrant.user_id == principal.user_id,
            )
        ),
        linked_conversation.source_alias_id.in_(
            select(EmailSenderAlias.id).where(
                EmailSenderAlias.organization_id == principal.organization_id,
                EmailSenderAlias.owner_user_id == principal.user_id,
                EmailSenderAlias.status == "active",
            )
        ),
    ]
    if can_view_all_conversations:
        linked_conversation_access.append(
            and_(
                linked_conversation.conversation_type == "lead",
                linked_conversation.visibility_scope == "standard",
            )
        )
    if PermissionKeys.VIEW_BUYERS in principal.permission_keys:
        linked_conversation_access.append(
            and_(
                linked_conversation.conversation_type == "buyer",
                linked_conversation.visibility_scope == "standard",
            )
        )
    direct_conversation_access: list[ColumnElement[bool]] = [
        Conversation.assigned_user_id == principal.user_id,
        Conversation.assigned_team_id.in_(
            select(TeamMembership.team_id).where(
                TeamMembership.organization_id == principal.organization_id,
                TeamMembership.user_id == principal.user_id,
            )
        ),
        Conversation.id.in_(
            select(ConversationWatcher.conversation_id).where(
                ConversationWatcher.organization_id == principal.organization_id,
                ConversationWatcher.user_id == principal.user_id,
            )
        ),
        Conversation.source_alias_id.in_(
            select(EmailSenderGrant.email_sender_alias_id).where(
                EmailSenderGrant.organization_id == principal.organization_id,
                EmailSenderGrant.user_id == principal.user_id,
            )
        ),
        Conversation.source_alias_id.in_(
            select(EmailSenderAlias.id).where(
                EmailSenderAlias.organization_id == principal.organization_id,
                EmailSenderAlias.owner_user_id == principal.user_id,
                EmailSenderAlias.status == "active",
            )
        ),
    ]
    if can_view_all_conversations:
        direct_conversation_access.append(
            and_(
                Conversation.conversation_type == "lead",
                Conversation.visibility_scope == "standard",
            )
        )
    if PermissionKeys.VIEW_BUYERS in principal.permission_keys:
        direct_conversation_access.append(
            and_(
                Conversation.conversation_type == "buyer",
                Conversation.visibility_scope == "standard",
            )
        )
    accepted_handoff_access = exists(
        select(linked_communication.id)
        .join(
            linked_conversation,
            linked_conversation.id == linked_communication.conversation_id,
        )
        .where(
            linked_communication.organization_id == principal.organization_id,
            linked_communication.source_call_record_id == CallRecord.id,
            linked_communication.provider == "openai_prospecting",
            linked_communication.provider_message_id.like("prospecting-call-notes:%"),
            linked_communication.channel == "note",
            linked_communication.lead_id.is_not(None),
            linked_conversation.organization_id == principal.organization_id,
            linked_conversation.conversation_type == "lead",
            linked_conversation.lead_id == linked_communication.lead_id,
            or_(literal(owner_mailbox_access), *linked_conversation_access),
        )
    )
    scope: list[ColumnElement[bool]] = [
        and_(
            CallRecord.conversation_id.is_not(None),
            Conversation.organization_id == principal.organization_id,
            or_(literal(owner_mailbox_access), *direct_conversation_access),
        )
    ]
    scope.append(
        and_(
            CallRecord.prospecting_attempt_id.is_not(None),
            or_(
                ProspectingAttempt.caller_user_id == principal.user_id,
                literal(manager),
                accepted_handoff_access,
            ),
        )
    )
    return db.scalar(
        select(CallRecording)
        .join(CallRecord, CallRecord.id == CallRecording.call_record_id)
        .outerjoin(Conversation, Conversation.id == CallRecord.conversation_id)
        .outerjoin(
            ProspectingAttempt,
            ProspectingAttempt.id == CallRecord.prospecting_attempt_id,
        )
        .where(
            CallRecording.id == recording_id,
            CallRecording.organization_id == principal.organization_id,
            CallRecord.organization_id == principal.organization_id,
            or_(*scope),
        )
    )
