from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.main import app
from app.models.foundation import (
    CommunicationRecord,
    Contact,
    Conversation,
    ConversationWatcher,
    EmailSenderAlias,
    EmailSenderGrant,
    Notification,
    Organization,
    Role,
    RoleAssignment,
    Team,
    TeamMembership,
    User,
)
from app.services.bootstrap import bootstrap_foundation
from app.services.inbox import create_general_conversation
from app.services.mailbox_notifications import process_next_mailbox_notification

OWNER_EMAIL = "owner@example.com"


def create_user_with_role(
    db: Session,
    organization: Organization,
    *,
    email: str,
    name: str,
    role_key: str,
) -> User:
    role = db.scalar(
        select(Role).where(
            Role.organization_id == organization.id,
            Role.key == role_key,
        )
    )
    assert role is not None
    user = User(
        organization_id=organization.id,
        email=email,
        display_name=name,
        is_active=True,
    )
    db.add(user)
    db.flush()
    db.add(
        RoleAssignment(
            organization_id=organization.id,
            user_id=user.id,
            role_id=role.id,
        )
    )
    db.flush()
    return user


def add_inbound_email(
    db: Session,
    conversation: Conversation,
    contact: Contact,
    *,
    occurred_at: datetime,
) -> None:
    conversation.last_activity_at = occurred_at
    conversation.last_inbound_at = occurred_at
    conversation.unread_count = 1
    db.add(
        CommunicationRecord(
            organization_id=conversation.organization_id,
            conversation_id=conversation.id,
            lead_id=None,
            contact_id=contact.id,
            actor_user_id=None,
            direction="inbound",
            channel="email",
            status="received",
            provider="resend",
            provider_message_id=f"email-{conversation.id}",
            subject="Stonegate question",
            body="Please follow up.",
            occurred_at=occurred_at,
            external_payload=None,
            communication_metadata={"source": "test"},
        )
    )


def test_mailbox_notification_deduplicates_assignee_watcher_and_alias_grant(
    db_session: Session,
    api_db_override: None,
) -> None:
    bootstrap = bootstrap_foundation(
        db_session,
        organization_name="Stonegate Home Buyers",
        admin_email=OWNER_EMAIL,
        admin_name="Owner",
    )
    assert bootstrap.admin_user is not None
    assignee = create_user_with_role(
        db_session,
        bootstrap.organization,
        email="devon@example.com",
        name="Devon",
        role_key="acquisition_rep",
    )
    alias = EmailSenderAlias(
        organization_id=bootstrap.organization.id,
        owner_user_id=assignee.id,
        assigned_team_id=None,
        created_by_user_id=bootstrap.admin_user.id,
        provider="resend",
        provider_identity_id=None,
        email_address="devon@stonegatehb.com",
        display_name="Devon",
        alias_type="named",
        purpose_key="acquisitions",
        status="active",
        inbound_enabled=True,
        outbound_enabled=True,
        is_default=False,
        signature_text=None,
        routing_metadata={},
    )
    contact = Contact(
        organization_id=bootstrap.organization.id,
        legal_name="Seller One",
        preferred_name=None,
        contact_type="seller",
        assigned_user_id=assignee.id,
    )
    db_session.add_all([alias, contact])
    db_session.flush()
    conversation = create_general_conversation(
        db_session,
        organization_id=bootstrap.organization.id,
        contact_id=contact.id,
        assigned_user_id=assignee.id,
        source_alias_id=alias.id,
    )
    db_session.add_all(
        [
            ConversationWatcher(
                organization_id=bootstrap.organization.id,
                conversation_id=conversation.id,
                user_id=assignee.id,
                source="manual",
                notification_level="all",
                is_muted=False,
            ),
            EmailSenderGrant(
                organization_id=bootstrap.organization.id,
                email_sender_alias_id=alias.id,
                user_id=assignee.id,
                granted_by_user_id=bootstrap.admin_user.id,
                access_level="sender",
                can_send=True,
                receives_notifications=True,
            ),
        ]
    )
    add_inbound_email(
        db_session,
        conversation,
        contact,
        occurred_at=datetime.now(UTC) - timedelta(minutes=5),
    )
    db_session.commit()

    settings = get_settings()
    first = process_next_mailbox_notification(db_session, settings)
    second = process_next_mailbox_notification(db_session, settings)
    assert first is not None
    assert second is None
    notifications = db_session.scalars(select(Notification)).all()
    assert len(notifications) == 1
    assert notifications[0].recipient_user_id == assignee.id
    assert notifications[0].notification_type == "mailbox_inbound"
    assert notifications[0].action_url == f"/os/inbox?conversation={conversation.id}"

    client = TestClient(app)
    response = client.get(
        "/api/v1/inbox/conversations",
        headers={"X-Dev-User-Email": assignee.email},
    )
    assert response.status_code == 200, response.text
    item = response.json()["items"][0]
    assert item["response_state"] == "waiting"
    assert item["response_kind"] == "first"
    assert item["response_target_minutes"] == 30
    assert item["response_age_minutes"] >= 5
    overview_response = client.get(
        "/api/v1/inbox/response-overview",
        headers={"X-Dev-User-Email": assignee.email},
    )
    assert overview_response.status_code == 200, overview_response.text
    overview = overview_response.json()
    assert overview["needs_reply_count"] == 1
    assert overview["overdue_count"] == 0
    assert overview["by_alias"][0]["scope_id"] == str(alias.id)
    assert overview["by_assignee"][0]["scope_id"] == str(assignee.id)

    read_response = client.patch(
        f"/api/v1/inbox/conversations/{conversation.id}/read",
        headers={"X-Dev-User-Email": assignee.email},
    )
    assert read_response.status_code == 200, read_response.text
    db_session.refresh(notifications[0])
    assert notifications[0].read_at is not None


def test_overdue_team_reply_notifies_team_and_important_watcher_then_resolves(
    db_session: Session,
) -> None:
    bootstrap = bootstrap_foundation(
        db_session,
        organization_name="Stonegate Home Buyers",
        admin_email=OWNER_EMAIL,
        admin_name="Owner",
    )
    assert bootstrap.admin_user is not None
    finance = create_user_with_role(
        db_session,
        bootstrap.organization,
        email="finance@example.com",
        name="Finance",
        role_key="finance_accounting",
    )
    team = Team(
        organization_id=bootstrap.organization.id,
        name="Accounting",
        team_type="finance",
        manager_user_id=finance.id,
        is_active=True,
    )
    contact = Contact(
        organization_id=bootstrap.organization.id,
        legal_name="Closing Attorney",
        preferred_name=None,
        contact_type="business_contact",
        assigned_user_id=None,
    )
    db_session.add_all([team, contact])
    db_session.flush()
    db_session.add(
        TeamMembership(
            organization_id=bootstrap.organization.id,
            team_id=team.id,
            user_id=finance.id,
            membership_role="member",
        )
    )
    conversation = create_general_conversation(
        db_session,
        organization_id=bootstrap.organization.id,
        contact_id=contact.id,
        assigned_team_id=team.id,
        visibility_scope="restricted",
    )
    db_session.add(
        ConversationWatcher(
            organization_id=bootstrap.organization.id,
            conversation_id=conversation.id,
            user_id=bootstrap.admin_user.id,
            source="owner",
            notification_level="important",
            is_muted=False,
        )
    )
    add_inbound_email(
        db_session,
        conversation,
        contact,
        occurred_at=datetime.now(UTC) - timedelta(hours=5),
    )
    db_session.commit()

    settings = get_settings()
    processed_ids = []
    while True:
        processed_id = process_next_mailbox_notification(db_session, settings)
        if processed_id is None:
            break
        processed_ids.append(processed_id)
    notifications = db_session.scalars(
        select(Notification).order_by(
            Notification.notification_type,
            Notification.recipient_user_id,
        )
    ).all()
    assert len(processed_ids) == 4
    assert {
        (notification.notification_type, notification.recipient_user_id)
        for notification in notifications
    } == {
        ("mailbox_inbound", finance.id),
        ("mailbox_response_due", finance.id),
        ("mailbox_response_due", bootstrap.admin_user.id),
        ("mailbox_owner_escalation", bootstrap.admin_user.id),
    }

    conversation.last_outbound_at = datetime.now(UTC)
    for notification in notifications:
        notification.read_at = None
    db_session.commit()
    resolved_ids = []
    while True:
        resolved_id = process_next_mailbox_notification(db_session, settings)
        if resolved_id is None:
            break
        resolved_ids.append(resolved_id)
    assert len(resolved_ids) == 4
    assert all(notification.read_at is not None for notification in notifications)
