from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.auth import Principal
from app.domain.rbac import PermissionKeys
from app.models.foundation import (
    ActivityEvent,
    Appointment,
    AuditEvent,
    Contact,
    Conversation,
    ConversationAssignmentEvent,
    ConversationWatcher,
    Lead,
    Property,
    Role,
    RoleAssignment,
    Task,
    User,
)
from app.schemas.inbox import (
    ConversationAssignmentEventRead,
    ConversationHandoffRequest,
    ConversationRead,
    ConversationWatcherCreate,
    ConversationWatcherRead,
    InboxAssigneeRead,
)

CONVERSATION_QUEUE_KEYS = {
    "unassigned",
    "va_prospecting",
    "qualified",
    "appointment_set",
    "acquisitions_follow_up",
    "closed",
}
ELIGIBLE_ACQUISITION_ROLE_KEYS = {
    "owner",
    "founder_operator",
    "ceo",
    "acquisition_manager",
    "acquisition_rep",
}
ELIGIBLE_ASSIGNMENT_ROLE_KEYS = {
    *ELIGIBLE_ACQUISITION_ROLE_KEYS,
    "prospecting_caller",
}
OWNER_WATCHER_ROLE_KEYS = {"owner", "founder_operator", "ceo"}
PRE_QUALIFIED_STAGES = {
    "new",
    "contact_attempt_due",
    "attempting_contact",
    "contacted",
    "qualification_in_progress",
}
PRE_APPOINTMENT_STAGES = {*PRE_QUALIFIED_STAGES, "qualified"}


def ensure_primary_conversation(
    db: Session,
    lead: Lead,
    *,
    queue_key: str | None = None,
) -> Conversation:
    existing = db.scalar(
        select(Conversation).where(
            Conversation.organization_id == lead.organization_id,
            Conversation.lead_id == lead.id,
        )
    )
    if existing is not None:
        return existing

    conversation = Conversation(
        organization_id=lead.organization_id,
        lead_id=lead.id,
        contact_id=lead.contact_id,
        assigned_user_id=lead.assigned_user_id,
        status="open",
        queue_key=queue_key
        or ("acquisitions_follow_up" if lead.assigned_user_id else "unassigned"),
        priority="normal",
        unread_count=0,
        last_activity_at=lead.created_at,
        last_inbound_at=None,
        last_outbound_at=None,
        closed_at=None,
        conversation_metadata={"source": "lead", "unified_timeline": True},
    )
    db.add(conversation)
    db.flush()
    db.add(
        ConversationAssignmentEvent(
            organization_id=lead.organization_id,
            conversation_id=conversation.id,
            lead_id=lead.id,
            actor_user_id=lead.assigned_user_id,
            previous_assigned_user_id=None,
            assigned_user_id=lead.assigned_user_id,
            previous_queue_key="unassigned",
            queue_key=conversation.queue_key,
            reason="Conversation created from lead.",
        )
    )
    return conversation


def update_conversation_activity(
    conversation: Conversation,
    *,
    direction: str,
    occurred_at: datetime,
) -> None:
    conversation.last_activity_at = occurred_at
    if direction == "inbound":
        conversation.last_inbound_at = occurred_at
        conversation.unread_count += 1
    elif direction == "outbound":
        conversation.last_outbound_at = occurred_at


def sync_conversation_to_lead_stage(
    db: Session,
    lead: Lead,
    *,
    actor_user_id: UUID,
    reason: str | None,
) -> None:
    queue_by_stage = {
        "qualified": "qualified",
        "appointment_scheduled": "appointment_set",
        "disqualified": "closed",
        "dead": "closed",
        "reopened": "acquisitions_follow_up",
    }
    queue_key = queue_by_stage.get(lead.stage_key)
    if queue_key is None:
        return

    conversation = ensure_primary_conversation(db, lead)
    if lead.stage_key in {"qualified", "appointment_scheduled"}:
        add_automatic_owner_watchers(db, conversation)
    if conversation.queue_key == queue_key:
        return

    previous_queue_key = conversation.queue_key
    conversation.queue_key = queue_key
    conversation.last_activity_at = datetime.now(UTC)
    if queue_key == "closed":
        conversation.status = "closed"
        conversation.closed_at = datetime.now(UTC)
    else:
        conversation.status = "open"
        conversation.closed_at = None
    db.add(
        ConversationAssignmentEvent(
            organization_id=lead.organization_id,
            conversation_id=conversation.id,
            lead_id=lead.id,
            actor_user_id=actor_user_id,
            previous_assigned_user_id=conversation.assigned_user_id,
            assigned_user_id=conversation.assigned_user_id,
            previous_queue_key=previous_queue_key,
            queue_key=queue_key,
            reason=reason or f"Lead stage changed to {lead.stage_key}.",
            created_at=datetime.now(UTC),
        )
    )


def list_conversations(
    db: Session,
    principal: Principal,
    *,
    queue_key: str | None = None,
    assigned_to_me: bool = False,
    limit: int = 100,
) -> list[ConversationRead]:
    filters = [Conversation.organization_id == principal.organization_id]
    if PermissionKeys.VIEW_CONVERSATIONS not in principal.permission_keys or assigned_to_me:
        filters.append(Conversation.assigned_user_id == principal.user_id)
    if queue_key:
        if queue_key not in CONVERSATION_QUEUE_KEYS:
            raise ValueError(f"Unsupported conversation queue: {queue_key}")
        filters.append(Conversation.queue_key == queue_key)

    conversations = db.scalars(
        select(Conversation)
        .where(*filters)
        .order_by(
            Conversation.last_activity_at.is_(None),
            Conversation.last_activity_at.desc(),
            Conversation.created_at.desc(),
        )
        .limit(limit)
    ).all()
    return [conversation_to_read(db, conversation) for conversation in conversations]


def get_conversation(
    db: Session,
    principal: Principal,
    conversation_id: UUID,
) -> ConversationRead | None:
    conversation = get_scoped_conversation(db, principal, conversation_id)
    return conversation_to_read(db, conversation) if conversation is not None else None


def list_eligible_assignees(db: Session, principal: Principal) -> list[InboxAssigneeRead]:
    role_keys = (
        ELIGIBLE_ASSIGNMENT_ROLE_KEYS
        if PermissionKeys.MANAGE_CONVERSATION_ASSIGNMENTS in principal.permission_keys
        else ELIGIBLE_ACQUISITION_ROLE_KEYS
    )
    rows = db.execute(
        select(User, Role.key)
        .join(RoleAssignment, RoleAssignment.user_id == User.id)
        .join(Role, Role.id == RoleAssignment.role_id)
        .where(
            User.organization_id == principal.organization_id,
            User.is_active.is_(True),
            Role.key.in_(role_keys),
        )
        .order_by(User.display_name.asc(), User.email.asc())
    ).all()
    users: dict[UUID, InboxAssigneeRead] = {}
    for user, role_key in rows:
        if user.id not in users:
            users[user.id] = InboxAssigneeRead(
                user_id=user.id,
                email=user.email,
                display_name=user.display_name,
                role_keys=[],
            )
        users[user.id].role_keys.append(role_key)
    for item in users.values():
        item.role_keys.sort()
    return list(users.values())


def handoff_conversation(
    db: Session,
    principal: Principal,
    conversation_id: UUID,
    payload: ConversationHandoffRequest,
) -> ConversationRead | None:
    conversation = db.scalar(
        select(Conversation).where(
            Conversation.organization_id == principal.organization_id,
            Conversation.id == conversation_id,
        )
    )
    if conversation is None:
        return None

    can_manage_all = PermissionKeys.MANAGE_CONVERSATION_ASSIGNMENTS in principal.permission_keys
    if not can_manage_all and (
        PermissionKeys.HANDOFF_ASSIGNED_CONVERSATIONS not in principal.permission_keys
        or conversation.assigned_user_id != principal.user_id
    ):
        raise PermissionError("Conversation is not assigned to the current user.")

    allowed_queue_keys = {
        "qualified",
        "appointment_set",
        "acquisitions_follow_up",
    }
    if can_manage_all:
        allowed_queue_keys.add("va_prospecting")
    if payload.queue_key not in allowed_queue_keys:
        raise ValueError(f"Unsupported handoff queue: {payload.queue_key}")

    target = db.scalar(
        select(User).where(
            User.organization_id == principal.organization_id,
            User.id == payload.assigned_user_id,
            User.is_active.is_(True),
        )
    )
    if target is None:
        raise ValueError("Assignment target must be an active workspace user.")
    target_role_keys = get_user_role_keys(db, target)
    if not target_role_keys.intersection(ELIGIBLE_ASSIGNMENT_ROLE_KEYS):
        raise ValueError("Assignment target must have an operational acquisitions role.")
    if (
        payload.queue_key == "va_prospecting"
        and "prospecting_caller" not in target_role_keys
    ):
        raise ValueError("VA prospecting conversations must be assigned to a prospecting caller.")
    if (
        payload.queue_key != "va_prospecting"
        and not target_role_keys.intersection(ELIGIBLE_ACQUISITION_ROLE_KEYS)
    ):
        raise ValueError("Handoff target must be an active acquisition user.")

    lead = db.scalar(
        select(Lead).where(
            Lead.organization_id == principal.organization_id,
            Lead.id == conversation.lead_id,
        )
    )
    if lead is None:
        return None
    contact = db.get(Contact, lead.contact_id)

    previous_assigned_user_id = conversation.assigned_user_id
    previous_queue_key = conversation.queue_key
    previous_stage_key = lead.stage_key
    conversation.assigned_user_id = target.id
    conversation.queue_key = payload.queue_key
    conversation.status = "open"
    conversation.closed_at = None
    conversation.last_activity_at = datetime.now(UTC)
    lead.assigned_user_id = target.id
    if contact is not None:
        contact.assigned_user_id = target.id
    if payload.queue_key == "va_prospecting" and lead.stage_key in {
        "new",
        "contact_attempt_due",
        "attempting_contact",
        "contacted",
    }:
        lead.stage_key = "qualification_in_progress"
    elif payload.queue_key == "qualified" and lead.stage_key in PRE_QUALIFIED_STAGES:
        lead.stage_key = "qualified"
    elif payload.queue_key == "appointment_set" and lead.stage_key in PRE_APPOINTMENT_STAGES:
        lead.stage_key = "appointment_scheduled"

    for task in db.scalars(
        select(Task).where(
            Task.organization_id == principal.organization_id,
            Task.lead_id == lead.id,
            Task.status.in_(("open", "in_progress")),
        )
    ):
        task.responsible_user_id = target.id
    for appointment in db.scalars(
        select(Appointment).where(
            Appointment.organization_id == principal.organization_id,
            Appointment.lead_id == lead.id,
            Appointment.status.in_(("scheduled", "rescheduled")),
        )
    ):
        appointment.owner_user_id = target.id

    assignment_event = ConversationAssignmentEvent(
        organization_id=principal.organization_id,
        conversation_id=conversation.id,
        lead_id=lead.id,
        actor_user_id=principal.user_id,
        previous_assigned_user_id=previous_assigned_user_id,
        assigned_user_id=target.id,
        previous_queue_key=previous_queue_key,
        queue_key=payload.queue_key,
        reason=payload.reason,
        created_at=datetime.now(UTC),
    )
    db.add(assignment_event)
    if target_role_keys.intersection(ELIGIBLE_ACQUISITION_ROLE_KEYS):
        ensure_watcher(
            db,
            conversation,
            target,
            source="assignment",
            notification_level="all",
        )
    if payload.queue_key != "va_prospecting":
        add_automatic_owner_watchers(db, conversation)
    action = (
        "conversation.assign"
        if payload.queue_key == "va_prospecting"
        else "conversation.handoff"
    )
    activity_verb = "assigned" if payload.queue_key == "va_prospecting" else "handed off"
    db.add(
        ActivityEvent(
            organization_id=principal.organization_id,
            actor_user_id=principal.user_id,
            entity_type="lead",
            entity_id=lead.id,
            event_type=(
                "lead.assigned_to_prospecting"
                if payload.queue_key == "va_prospecting"
                else "lead.handed_off"
            ),
            summary=(
                f"Conversation {activity_verb} to {target.display_name} "
                f"in {payload.queue_key}."
            ),
        )
    )
    db.add(
        AuditEvent(
            organization_id=principal.organization_id,
            actor_user_id=principal.user_id,
            actor_type="user",
            action=action,
            entity_type="conversation",
            entity_id=conversation.id,
            previous_value={
                "assigned_user_id": str(previous_assigned_user_id)
                if previous_assigned_user_id
                else None,
                "queue_key": previous_queue_key,
                "lead_stage_key": previous_stage_key,
            },
            new_value={
                "assigned_user_id": str(target.id),
                "queue_key": payload.queue_key,
                "lead_stage_key": lead.stage_key,
            },
            reason=payload.reason,
        )
    )
    db.commit()
    db.refresh(conversation)
    return conversation_to_read(db, conversation)


def add_conversation_watcher(
    db: Session,
    principal: Principal,
    conversation_id: UUID,
    payload: ConversationWatcherCreate,
) -> ConversationRead | None:
    conversation = get_scoped_conversation(db, principal, conversation_id, require_all=True)
    if conversation is None:
        return None
    user = db.scalar(
        select(User).where(
            User.organization_id == principal.organization_id,
            User.id == payload.user_id,
            User.is_active.is_(True),
        )
    )
    if user is None:
        raise ValueError("Watcher must be an active workspace user.")
    watcher = ensure_watcher(
        db,
        conversation,
        user,
        source="manual",
        notification_level=payload.notification_level,
    )
    db.add(
        AuditEvent(
            organization_id=principal.organization_id,
            actor_user_id=principal.user_id,
            actor_type="user",
            action="conversation.watcher_add",
            entity_type="conversation_watcher",
            entity_id=watcher.id,
            previous_value=None,
            new_value={
                "conversation_id": str(conversation.id),
                "user_id": str(user.id),
                "notification_level": watcher.notification_level,
            },
            reason="Manual conversation watcher",
        )
    )
    db.commit()
    return conversation_to_read(db, conversation)


def remove_conversation_watcher(
    db: Session,
    principal: Principal,
    conversation_id: UUID,
    user_id: UUID,
) -> ConversationRead | None:
    conversation = get_scoped_conversation(db, principal, conversation_id, require_all=True)
    if conversation is None:
        return None
    watcher = db.scalar(
        select(ConversationWatcher).where(
            ConversationWatcher.organization_id == principal.organization_id,
            ConversationWatcher.conversation_id == conversation.id,
            ConversationWatcher.user_id == user_id,
        )
    )
    if watcher is not None:
        watcher_id = watcher.id
        db.delete(watcher)
        db.add(
            AuditEvent(
                organization_id=principal.organization_id,
                actor_user_id=principal.user_id,
                actor_type="user",
                action="conversation.watcher_remove",
                entity_type="conversation_watcher",
                entity_id=watcher_id,
                previous_value={"conversation_id": str(conversation.id), "user_id": str(user_id)},
                new_value=None,
                reason="Manual conversation watcher removal",
            )
        )
        db.commit()
    return conversation_to_read(db, conversation)


def add_automatic_owner_watchers(db: Session, conversation: Conversation) -> None:
    owners = db.scalars(
        select(User)
        .join(RoleAssignment, RoleAssignment.user_id == User.id)
        .join(Role, Role.id == RoleAssignment.role_id)
        .where(
            User.organization_id == conversation.organization_id,
            User.is_active.is_(True),
            Role.key.in_(OWNER_WATCHER_ROLE_KEYS),
        )
        .distinct()
    ).all()
    for owner in owners:
        ensure_watcher(
            db,
            conversation,
            owner,
            source="automatic_owner",
            notification_level="important",
        )


def ensure_watcher(
    db: Session,
    conversation: Conversation,
    user: User,
    *,
    source: str,
    notification_level: str,
) -> ConversationWatcher:
    watcher = db.scalar(
        select(ConversationWatcher).where(
            ConversationWatcher.conversation_id == conversation.id,
            ConversationWatcher.user_id == user.id,
        )
    )
    if watcher is None:
        watcher = ConversationWatcher(
            organization_id=conversation.organization_id,
            conversation_id=conversation.id,
            user_id=user.id,
            source=source,
            notification_level=notification_level,
            is_muted=False,
        )
        db.add(watcher)
        db.flush()
    return watcher


def get_scoped_conversation(
    db: Session,
    principal: Principal,
    conversation_id: UUID,
    *,
    require_all: bool = False,
) -> Conversation | None:
    filters = [
        Conversation.organization_id == principal.organization_id,
        Conversation.id == conversation_id,
    ]
    if (require_all or PermissionKeys.VIEW_CONVERSATIONS not in principal.permission_keys) and (
        PermissionKeys.MANAGE_CONVERSATION_ASSIGNMENTS not in principal.permission_keys
    ):
        filters.append(Conversation.assigned_user_id == principal.user_id)
    return db.scalar(select(Conversation).where(*filters))


def get_user_role_keys(db: Session, user: User) -> set[str]:
    return set(
        db.scalars(
            select(Role.key)
            .join(RoleAssignment, RoleAssignment.role_id == Role.id)
            .where(
                RoleAssignment.organization_id == user.organization_id,
                RoleAssignment.user_id == user.id,
            )
        )
    )


def conversation_to_read(db: Session, conversation: Conversation) -> ConversationRead:
    lead = db.get(Lead, conversation.lead_id)
    contact = db.get(Contact, conversation.contact_id)
    assigned_user = (
        db.get(User, conversation.assigned_user_id) if conversation.assigned_user_id else None
    )
    if lead is None or contact is None:
        raise RuntimeError("Conversation is missing its lead or contact.")
    property_record = db.get(Property, lead.property_id)
    if property_record is None:
        raise RuntimeError("Conversation lead is missing its property.")

    watcher_rows = db.execute(
        select(ConversationWatcher, User)
        .join(User, User.id == ConversationWatcher.user_id)
        .where(
            ConversationWatcher.organization_id == conversation.organization_id,
            ConversationWatcher.conversation_id == conversation.id,
        )
        .order_by(User.display_name.asc(), User.email.asc())
    ).all()
    assignment_events = db.scalars(
        select(ConversationAssignmentEvent)
        .where(
            ConversationAssignmentEvent.organization_id == conversation.organization_id,
            ConversationAssignmentEvent.conversation_id == conversation.id,
        )
        .order_by(
            ConversationAssignmentEvent.created_at.desc(),
            ConversationAssignmentEvent.id.desc(),
        )
        .limit(20)
    ).all()
    return ConversationRead(
        id=conversation.id,
        lead_id=conversation.lead_id,
        contact_id=conversation.contact_id,
        seller_name=contact.legal_name,
        property_address=(
            f"{property_record.street_address}, {property_record.city}, "
            f"{property_record.state} {property_record.postal_code}"
        ),
        assigned_user_id=conversation.assigned_user_id,
        assigned_user_email=assigned_user.email if assigned_user else None,
        status=conversation.status,
        queue_key=conversation.queue_key,
        priority=conversation.priority,
        unread_count=conversation.unread_count,
        last_activity_at=conversation.last_activity_at,
        last_inbound_at=conversation.last_inbound_at,
        last_outbound_at=conversation.last_outbound_at,
        closed_at=conversation.closed_at,
        watchers=[
            ConversationWatcherRead(
                user_id=user.id,
                email=user.email,
                display_name=user.display_name,
                source=watcher.source,
                notification_level=watcher.notification_level,
                is_muted=watcher.is_muted,
            )
            for watcher, user in watcher_rows
        ],
        assignment_history=[
            ConversationAssignmentEventRead(
                id=event.id,
                actor_user_id=event.actor_user_id,
                previous_assigned_user_id=event.previous_assigned_user_id,
                assigned_user_id=event.assigned_user_id,
                previous_queue_key=event.previous_queue_key,
                queue_key=event.queue_key,
                reason=event.reason,
                created_at=event.created_at,
            )
            for event in assignment_events
        ],
        created_at=conversation.created_at,
        updated_at=conversation.updated_at,
    )
