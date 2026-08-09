from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.models.foundation import (
    CommunicationRecord,
    Contact,
    Conversation,
    ConversationWatcher,
    EmailSenderAlias,
    EmailSenderGrant,
    Notification,
    Role,
    RoleAssignment,
    Team,
    TeamMembership,
    User,
)
from app.services.lead_lifecycle import INACTIVE_LEAD_STAGES, lock_organization_lead

OWNER_ROLE_KEYS = {"owner", "founder_operator", "ceo"}
MAILBOX_NOTIFICATION_TYPES = {
    "mailbox_inbound",
    "mailbox_response_due",
    "mailbox_owner_escalation",
}


@dataclass(frozen=True)
class MailboxResponseStatus:
    state: str
    kind: str | None
    age_minutes: int | None
    target_minutes: int | None
    due_at: datetime | None


def mailbox_response_status(
    conversation: Conversation,
    settings: Settings,
    *,
    latest_inbound_channel: str | None = None,
    now: datetime | None = None,
) -> MailboxResponseStatus:
    if (
        conversation.status == "closed"
        or latest_inbound_channel not in {None, "email", "sms"}
        or conversation.last_inbound_at is None
        or (
            conversation.last_outbound_at is not None
            and _as_utc(conversation.last_outbound_at) >= _as_utc(conversation.last_inbound_at)
        )
    ):
        return MailboxResponseStatus(
            state="none",
            kind=None,
            age_minutes=None,
            target_minutes=None,
            due_at=None,
        )
    current_time = _as_utc(now or datetime.now(UTC))
    inbound_at = _as_utc(conversation.last_inbound_at)
    kind = "first" if conversation.last_outbound_at is None else "follow_up"
    target_minutes = (
        settings.mailbox_first_response_target_minutes
        if kind == "first"
        else settings.mailbox_next_response_target_minutes
    )
    due_at = inbound_at + timedelta(minutes=target_minutes)
    age_minutes = max(0, int((current_time - inbound_at).total_seconds() // 60))
    remaining_minutes = int((due_at - current_time).total_seconds() // 60)
    state = (
        "overdue"
        if current_time >= due_at
        else "due_soon"
        if remaining_minutes <= max(5, target_minutes // 4)
        else "waiting"
    )
    return MailboxResponseStatus(
        state=state,
        kind=kind,
        age_minutes=age_minutes,
        target_minutes=target_minutes,
        due_at=due_at,
    )


def process_next_mailbox_notification(
    db: Session,
    settings: Settings,
) -> UUID | None:
    resolved = _resolve_answered_notification(db)
    if resolved is not None:
        return resolved

    now = datetime.now(UTC)
    conversations = db.scalars(
        select(Conversation)
        .where(
            Conversation.status == "open",
            Conversation.last_inbound_at.is_not(None),
            or_(
                Conversation.last_outbound_at.is_(None),
                Conversation.last_inbound_at > Conversation.last_outbound_at,
            ),
        )
        .order_by(Conversation.last_inbound_at.asc())
        .limit(100)
    ).all()
    for conversation in conversations:
        if conversation.lead_id is not None:
            lead = lock_organization_lead(
                db,
                organization_id=conversation.organization_id,
                lead_id=conversation.lead_id,
            )
            if (
                lead is None
                or lead.archived_at is not None
                or lead.stage_key in INACTIVE_LEAD_STAGES
            ):
                db.rollback()
                continue
        locked_conversation = db.scalar(
            select(Conversation)
            .where(
                Conversation.id == conversation.id,
                Conversation.status == "open",
                Conversation.last_inbound_at.is_not(None),
                or_(
                    Conversation.last_outbound_at.is_(None),
                    Conversation.last_inbound_at > Conversation.last_outbound_at,
                ),
            )
            .execution_options(populate_existing=True)
            .with_for_update()
        )
        if locked_conversation is None:
            db.rollback()
            continue
        conversation = locked_conversation
        channel = latest_inbound_channel(db, conversation)
        response = mailbox_response_status(
            conversation,
            settings,
            latest_inbound_channel=channel,
            now=now,
        )
        if response.state == "none" or conversation.last_inbound_at is None:
            continue
        inbound_key = str(int(_as_utc(conversation.last_inbound_at).timestamp()))
        channel = channel or "message"
        contact = db.get(Contact, conversation.contact_id)
        contact_name = contact.legal_name if contact is not None else "A contact"
        action_url = f"/os/inbox?conversation={conversation.id}"

        recipients = _notification_recipient_ids(db, conversation, important=False)
        for recipient_id in recipients:
            notification = _create_notification(
                db,
                conversation=conversation,
                recipient_user_id=recipient_id,
                notification_type="mailbox_inbound",
                title=f"New {channel} needs a reply",
                body=f"{contact_name} sent a {channel} in the Stonegate Inbox.",
                action_url=action_url,
                dedupe_key=f"mailbox-inbound:{conversation.id}:{inbound_key}",
            )
            if notification is not None:
                db.commit()
                return notification.id

        if response.state == "overdue":
            important_recipients = _notification_recipient_ids(
                db,
                conversation,
                important=True,
            )
            for recipient_id in important_recipients:
                notification = _create_notification(
                    db,
                    conversation=conversation,
                    recipient_user_id=recipient_id,
                    notification_type="mailbox_response_due",
                    title="Inbox response target missed",
                    body=(
                        f"{contact_name} has waited {response.age_minutes or 0} minutes "
                        "for a reply."
                    ),
                    action_url=action_url,
                    dedupe_key=f"mailbox-due:{conversation.id}:{inbound_key}",
                )
                if notification is not None:
                    db.commit()
                    return notification.id

        owner_escalation_due = response.age_minutes is not None and response.age_minutes >= (
            settings.mailbox_unassigned_escalation_minutes
            if conversation.assigned_user_id is None and conversation.assigned_team_id is None
            else settings.mailbox_owner_escalation_minutes
        )
        if owner_escalation_due:
            for owner_id in _owner_user_ids(db, conversation.organization_id):
                notification = _create_notification(
                    db,
                    conversation=conversation,
                    recipient_user_id=owner_id,
                    notification_type="mailbox_owner_escalation",
                    title=(
                        "Unassigned Inbox reply needs attention"
                        if conversation.assigned_user_id is None
                        and conversation.assigned_team_id is None
                        else "Inbox reply escalation"
                    ),
                    body=(
                        f"{contact_name} has waited {response.age_minutes or 0} minutes "
                        "for a reply."
                    ),
                    action_url=action_url,
                    dedupe_key=f"mailbox-owner:{conversation.id}:{inbound_key}",
                )
                if notification is not None:
                    db.commit()
                    return notification.id
        db.rollback()
    db.commit()
    return None


def _notification_recipient_ids(
    db: Session,
    conversation: Conversation,
    *,
    important: bool,
) -> list[UUID]:
    recipient_ids: set[UUID] = set()
    if conversation.assigned_user_id is not None:
        recipient_ids.add(conversation.assigned_user_id)
    elif conversation.assigned_team_id is not None:
        recipient_ids.update(_team_user_ids(db, conversation.assigned_team_id))

    alias = (
        db.get(EmailSenderAlias, conversation.source_alias_id)
        if conversation.source_alias_id is not None
        else None
    )
    if alias is not None:
        if (
            conversation.assigned_user_id is None
            and conversation.assigned_team_id is None
            and alias.owner_user_id is not None
        ):
            recipient_ids.add(alias.owner_user_id)
        if (
            conversation.assigned_user_id is None
            and conversation.assigned_team_id is None
            and alias.assigned_team_id is not None
        ):
            recipient_ids.update(_team_user_ids(db, alias.assigned_team_id))
        recipient_ids.update(
            db.scalars(
                select(EmailSenderGrant.user_id).where(
                    EmailSenderGrant.organization_id == conversation.organization_id,
                    EmailSenderGrant.email_sender_alias_id == alias.id,
                    EmailSenderGrant.receives_notifications.is_(True),
                )
            ).all()
        )

    watcher_levels = {"all", "important"} if important else {"all"}
    recipient_ids.update(
        db.scalars(
            select(ConversationWatcher.user_id).where(
                ConversationWatcher.organization_id == conversation.organization_id,
                ConversationWatcher.conversation_id == conversation.id,
                ConversationWatcher.is_muted.is_(False),
                ConversationWatcher.notification_level.in_(watcher_levels),
            )
        ).all()
    )
    if not recipient_ids and conversation.assigned_team_id is None:
        recipient_ids.update(_owner_user_ids(db, conversation.organization_id))
    active_ids = set(
        db.scalars(
            select(User.id).where(
                User.organization_id == conversation.organization_id,
                User.id.in_(recipient_ids),
                User.is_active.is_(True),
            )
        ).all()
    )
    return sorted(active_ids, key=str)


def _team_user_ids(db: Session, team_id: UUID) -> set[UUID]:
    team = db.get(Team, team_id)
    user_ids = set(
        db.scalars(select(TeamMembership.user_id).where(TeamMembership.team_id == team_id)).all()
    )
    if team is not None and team.is_active and team.manager_user_id is not None:
        user_ids.add(team.manager_user_id)
    return user_ids


def _owner_user_ids(db: Session, organization_id: UUID) -> list[UUID]:
    return list(
        dict.fromkeys(
            db.scalars(
                select(User.id)
                .join(RoleAssignment, RoleAssignment.user_id == User.id)
                .join(Role, Role.id == RoleAssignment.role_id)
                .where(
                    User.organization_id == organization_id,
                    User.is_active.is_(True),
                    Role.key.in_(OWNER_ROLE_KEYS),
                )
                .order_by(User.id)
            ).all()
        )
    )


def latest_inbound_channel(db: Session, conversation: Conversation) -> str | None:
    return db.scalar(
        select(CommunicationRecord.channel)
        .where(
            CommunicationRecord.organization_id == conversation.organization_id,
            CommunicationRecord.conversation_id == conversation.id,
            CommunicationRecord.direction == "inbound",
        )
        .order_by(
            CommunicationRecord.occurred_at.desc(),
            CommunicationRecord.created_at.desc(),
        )
        .limit(1)
    )


def _create_notification(
    db: Session,
    *,
    conversation: Conversation,
    recipient_user_id: UUID,
    notification_type: str,
    title: str,
    body: str,
    action_url: str,
    dedupe_key: str,
) -> Notification | None:
    existing = db.scalar(
        select(Notification.id).where(
            Notification.organization_id == conversation.organization_id,
            Notification.recipient_user_id == recipient_user_id,
            Notification.dedupe_key == dedupe_key,
        )
    )
    if existing is not None:
        return None
    notification = Notification(
        organization_id=conversation.organization_id,
        recipient_user_id=recipient_user_id,
        notification_type=notification_type,
        title=title,
        body=body,
        entity_type="conversation",
        entity_id=conversation.id,
        action_url=action_url,
        dedupe_key=dedupe_key,
        read_at=None,
    )
    db.add(notification)
    db.flush()
    return notification


def _resolve_answered_notification(db: Session) -> UUID | None:
    notification = db.scalar(
        select(Notification)
        .join(
            Conversation,
            Conversation.id == Notification.entity_id,
        )
        .where(
            Notification.notification_type.in_(MAILBOX_NOTIFICATION_TYPES),
            Notification.read_at.is_(None),
            or_(
                Conversation.status == "closed",
                Conversation.last_inbound_at.is_(None),
                Conversation.last_outbound_at >= Conversation.last_inbound_at,
            ),
        )
        .order_by(Notification.created_at.asc())
        .limit(1)
    )
    if notification is None:
        return None
    notification.read_at = datetime.now(UTC)
    db.commit()
    return notification.id


def _as_utc(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)
