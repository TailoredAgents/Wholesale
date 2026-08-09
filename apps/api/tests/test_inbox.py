from datetime import UTC, datetime
from uuid import UUID

from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.main import app
from app.models.foundation import (
    Appointment,
    AuditEvent,
    CallRecord,
    CallRecording,
    CallTranscript,
    CommunicationParticipant,
    CommunicationProviderEvent,
    CommunicationRecord,
    Contact,
    ContactMethod,
    Conversation,
    ConversationAssignmentEvent,
    ConversationContextLink,
    ConversationWatcher,
    EmailSenderAlias,
    Lead,
    Organization,
    Property,
    Role,
    RoleAssignment,
    Task,
    Team,
    TeamMembership,
    UnderwritingVersion,
    User,
)
from app.services.bootstrap import bootstrap_foundation
from app.services.communication_participants import record_email_participants
from app.services.inbox import create_general_conversation, update_conversation_activity

OWNER_EMAIL = "owner@example.com"
VA_EMAIL = "caller@example.com"
ACQUISITIONS_EMAIL = "acquisitions@example.com"


def lead_payload(street_address: str) -> dict[str, object]:
    return {
        "contact": {
            "legal_name": f"Seller at {street_address}",
            "contact_type": "seller",
        },
        "property": {
            "street_address": street_address,
            "city": "Atlanta",
            "state": "GA",
            "postal_code": "30303",
            "property_type": "single_family",
        },
        "source": "cold_call",
        "stage_key": "qualification_in_progress",
    }


def seed_workspace(db: Session) -> tuple[User, User, User]:
    result = bootstrap_foundation(
        db,
        organization_name="Stonegate Home Buyers",
        admin_email=OWNER_EMAIL,
        admin_name="Owner",
    )
    assert result.admin_user is not None
    organization = result.organization
    va = create_user_with_role(
        db,
        organization,
        email=VA_EMAIL,
        name="VA Caller",
        role_key="prospecting_caller",
    )
    acquisitions = create_user_with_role(
        db,
        organization,
        email=ACQUISITIONS_EMAIL,
        name="Acquisitions Specialist",
        role_key="acquisition_rep",
    )
    db.commit()
    return result.admin_user, va, acquisitions


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


def test_va_access_is_assigned_only_and_handoff_preserves_history(
    db_session: Session,
    api_db_override: None,
) -> None:
    owner, va, acquisitions = seed_workspace(db_session)
    client = TestClient(app)
    headers = {"X-Dev-User-Email": OWNER_EMAIL}
    assigned_lead = client.post(
        "/api/v1/leads",
        headers=headers,
        json=lead_payload("101 Assigned Ave"),
    ).json()
    other_lead = client.post(
        "/api/v1/leads",
        headers=headers,
        json=lead_payload("202 Private Ave"),
    ).json()
    qualified_response = client.patch(
        f"/api/v1/leads/{other_lead['id']}/stage",
        headers=headers,
        json={"stage_key": "qualified", "reason": "Seller qualification completed."},
    )
    assert qualified_response.status_code == 200
    qualified_conversation = db_session.scalar(
        select(Conversation).where(Conversation.lead_id == UUID(other_lead["id"]))
    )
    assert qualified_conversation is not None
    assert qualified_conversation.queue_key == "qualified"
    assert (
        db_session.scalar(
            select(func.count())
            .select_from(ConversationWatcher)
            .where(
                ConversationWatcher.conversation_id == qualified_conversation.id,
                ConversationWatcher.user_id == owner.id,
            )
        )
        == 1
    )

    conversation = db_session.scalar(
        select(Conversation).where(Conversation.lead_id == UUID(assigned_lead["id"]))
    )
    assert conversation is not None
    assign_response = client.post(
        f"/api/v1/inbox/conversations/{conversation.id}/handoff",
        headers=headers,
        json={
            "assigned_user_id": str(va.id),
            "queue_key": "va_prospecting",
            "reason": "Assigned to the VA prospecting queue.",
        },
    )
    assert assign_response.status_code == 200
    assert assign_response.json()["assigned_user_id"] == str(va.id)
    assert assign_response.json()["queue_key"] == "va_prospecting"

    lead = db_session.get(Lead, UUID(assigned_lead["id"]))
    assert lead is not None
    db_session.add(
        UnderwritingVersion(
            organization_id=lead.organization_id,
            lead_id=lead.id,
            property_id=lead.property_id,
            created_by_user_id=owner.id,
            version_number=1,
            status="draft",
            arv_low_cents=20000000,
            arv_high_cents=22000000,
            repair_low_cents=2000000,
            repair_high_cents=3000000,
            max_offer_cents=12000000,
            recommended_offer_cents=11000000,
            offer_strategy="cash_offer",
            notes="Owner-only underwriting.",
            source="manual",
            underwriting_metadata=None,
        )
    )
    db_session.add(
        Task(
            organization_id=lead.organization_id,
            lead_id=lead.id,
            responsible_user_id=va.id,
            task_type="follow_up",
            title="Confirm appointment",
            status="open",
            priority="high",
            due_at=None,
            completed_at=None,
        )
    )
    db_session.commit()

    va_headers = {"X-Dev-User-Email": VA_EMAIL}
    me_response = client.get("/api/v1/me", headers=va_headers)
    assert me_response.status_code == 200
    assert "leads:view_assigned" in me_response.json()["permissions"]
    assert "leads:view" not in me_response.json()["permissions"]

    lead_list = client.get("/api/v1/leads", headers=va_headers)
    assert lead_list.status_code == 200
    assert [item["id"] for item in lead_list.json()["items"]] == [assigned_lead["id"]]
    assert (
        client.get(
            f"/api/v1/leads/{other_lead['id']}",
            headers=va_headers,
        ).status_code
        == 404
    )
    assigned_detail = client.get(
        f"/api/v1/leads/{assigned_lead['id']}",
        headers=va_headers,
    )
    assert assigned_detail.status_code == 200
    assert assigned_detail.json()["underwriting_versions"] == []
    assert assigned_detail.json()["transactions"] == []
    assert assigned_detail.json()["buyer_offers"] == []
    assert (
        client.get(
            f"/api/v1/leads/{assigned_lead['id']}/underwriting/market-analysis",
            headers=va_headers,
        ).status_code
        == 403
    )

    inbox_response = client.get("/api/v1/inbox/conversations", headers=va_headers)
    assert inbox_response.status_code == 200
    assert [item["id"] for item in inbox_response.json()["items"]] == [str(conversation.id)]
    assert (
        client.post(
            f"/api/v1/leads/{assigned_lead['id']}/notes",
            headers=va_headers,
            json={"note": "VA should not have general note access."},
        ).status_code
        == 403
    )

    communication_response = client.post(
        f"/api/v1/leads/{assigned_lead['id']}/communications",
        headers=va_headers,
        json={
            "direction": "outbound",
            "channel": "call",
            "status": "logged",
            "body": "Seller is interested and requested an appointment.",
        },
    )
    assert communication_response.status_code == 201
    appointment_response = client.post(
        f"/api/v1/leads/{assigned_lead['id']}/appointments",
        headers=va_headers,
        json={
            "appointment_type": "seller_call",
            "status": "scheduled",
            "scheduled_start_at": "2026-07-20T15:00:00Z",
            "location_type": "phone",
        },
    )
    assert appointment_response.status_code == 201

    handoff_response = client.post(
        f"/api/v1/inbox/conversations/{conversation.id}/handoff",
        headers=va_headers,
        json={
            "assigned_user_id": str(acquisitions.id),
            "queue_key": "appointment_set",
            "reason": "Seller requested an acquisitions appointment.",
        },
    )
    assert handoff_response.status_code == 200
    handoff = handoff_response.json()
    assert handoff["assigned_user_id"] == str(acquisitions.id)
    assert handoff["queue_key"] == "appointment_set"
    assert {watcher["email"] for watcher in handoff["watchers"]} == {
        OWNER_EMAIL,
        ACQUISITIONS_EMAIL,
    }
    assert handoff["assignment_history"][0]["previous_assigned_user_id"] == str(va.id)
    assert handoff["assignment_history"][0]["assigned_user_id"] == str(acquisitions.id)

    db_session.expire_all()
    reassigned_lead = db_session.get(Lead, UUID(assigned_lead["id"]))
    assert reassigned_lead is not None
    assert reassigned_lead.assigned_user_id == acquisitions.id
    assert reassigned_lead.stage_key == "appointment_scheduled"
    appointment = db_session.scalar(
        select(Appointment).where(Appointment.lead_id == reassigned_lead.id)
    )
    assert appointment is not None
    assert appointment.owner_user_id == acquisitions.id
    task = db_session.scalar(select(Task).where(Task.lead_id == reassigned_lead.id))
    assert task is not None
    assert task.responsible_user_id == acquisitions.id

    assert (
        client.get(
            f"/api/v1/leads/{assigned_lead['id']}",
            headers=va_headers,
        ).status_code
        == 404
    )
    assert (
        client.post(
            f"/api/v1/leads/{assigned_lead['id']}/communications",
            headers=va_headers,
            json={
                "direction": "outbound",
                "channel": "sms",
                "status": "logged",
                "body": "This should be blocked after handoff.",
            },
        ).status_code
        == 404
    )
    assert (
        client.get(
            f"/api/v1/inbox/conversations/{conversation.id}",
            headers=va_headers,
        ).status_code
        == 404
    )
    assert (
        int(
            db_session.scalar(
                select(func.count())
                .select_from(AuditEvent)
                .where(AuditEvent.action == "conversation.handoff")
            )
            or 0
        )
        == 1
    )
    assert (
        int(
            db_session.scalar(
                select(func.count())
                .select_from(ConversationAssignmentEvent)
                .where(ConversationAssignmentEvent.conversation_id == conversation.id)
            )
            or 0
        )
        == 3
    )
    assert (
        int(
            db_session.scalar(
                select(func.count())
                .select_from(ConversationWatcher)
                .where(ConversationWatcher.conversation_id == conversation.id)
            )
            or 0
        )
        == 2
    )


def test_inbox_provider_call_recording_and_transcript_records_persist(
    db_session: Session,
    api_db_override: None,
) -> None:
    owner, _, _ = seed_workspace(db_session)
    client = TestClient(app)
    lead_id = UUID(
        client.post(
            "/api/v1/leads",
            headers={"X-Dev-User-Email": OWNER_EMAIL},
            json=lead_payload("303 Provider Ave"),
        ).json()["id"]
    )
    conversation = db_session.scalar(select(Conversation).where(Conversation.lead_id == lead_id))
    lead = db_session.get(Lead, lead_id)
    assert conversation is not None
    assert lead is not None

    provider_event = CommunicationProviderEvent(
        organization_id=lead.organization_id,
        conversation_id=conversation.id,
        provider="twilio",
        event_type="call.completed",
        external_event_id="CA-test-event",
        processing_status="pending",
        payload={"CallSid": "CA-test-call"},
        received_at=datetime.now(UTC),
        processed_at=None,
        error_message=None,
    )
    call = CallRecord(
        organization_id=lead.organization_id,
        conversation_id=conversation.id,
        lead_id=lead.id,
        contact_id=lead.contact_id,
        actor_user_id=owner.id,
        communication_record_id=None,
        provider="twilio",
        provider_call_id="CA-test-call",
        direction="outbound",
        status="completed",
        from_number="+14045550101",
        to_number="+14045550102",
        started_at=datetime.now(UTC),
        answered_at=None,
        ended_at=None,
        duration_seconds=180,
        disposition="interested",
        call_metadata={"source": "test"},
    )
    db_session.add_all([provider_event, call])
    db_session.flush()
    recording = CallRecording(
        organization_id=lead.organization_id,
        call_record_id=call.id,
        provider="twilio",
        provider_recording_id="RE-test-recording",
        status="completed",
        media_reference="twilio://recordings/RE-test-recording",
        duration_seconds=175,
        channel_count=2,
        consent_status="confirmed",
        recorded_at=datetime.now(UTC),
        deleted_at=None,
        recording_metadata={"encrypted": True},
    )
    db_session.add(recording)
    db_session.flush()
    db_session.add(
        CallTranscript(
            organization_id=lead.organization_id,
            recording_id=recording.id,
            provider="openai",
            model_name="gpt-4o-transcribe-diarize",
            status="draft",
            language="en",
            transcript_text="Agent: Hello. Seller: I am interested.",
            speaker_segments=[{"speaker": "agent", "start": 0, "end": 1, "text": "Hello."}],
            confidence_score=95,
            approved_by_user_id=None,
            approved_at=None,
            error_message=None,
            transcript_metadata={"human_review_required": True},
        )
    )
    db_session.commit()

    assert int(db_session.scalar(select(func.count()).select_from(CallRecord)) or 0) == 1
    assert int(db_session.scalar(select(func.count()).select_from(CallRecording)) or 0) == 1
    assert int(db_session.scalar(select(func.count()).select_from(CallTranscript)) or 0) == 1


def test_inbox_detail_combines_context_timeline_and_read_state(
    db_session: Session,
    api_db_override: None,
) -> None:
    seed_workspace(db_session)
    client = TestClient(app)
    headers = {"X-Dev-User-Email": OWNER_EMAIL}
    lead_response = client.post(
        "/api/v1/leads",
        headers=headers,
        json={
            **lead_payload("404 Timeline Street"),
            "contact": {
                "legal_name": "Jordan Seller",
                "preferred_name": "Jordan",
                "contact_type": "seller",
            },
            "motivation": "Inherited property",
            "desired_timeline": "30_days",
        },
    )
    assert lead_response.status_code == 201
    lead_id = lead_response.json()["id"]
    conversation = db_session.scalar(
        select(Conversation).where(Conversation.lead_id == UUID(lead_id))
    )
    assert conversation is not None
    assert conversation.conversation_type == "lead"
    context_link = db_session.scalar(
        select(ConversationContextLink).where(
            ConversationContextLink.conversation_id == conversation.id,
            ConversationContextLink.lead_id == UUID(lead_id),
        )
    )
    assert context_link is not None
    assert context_link.is_primary is True
    db_session.add_all(
        [
            ContactMethod(
                organization_id=conversation.organization_id,
                contact_id=conversation.contact_id,
                method_type="phone",
                value="+14045550199",
                normalized_value="+14045550199",
                is_primary=True,
            ),
            ContactMethod(
                organization_id=conversation.organization_id,
                contact_id=conversation.contact_id,
                method_type="email",
                value="jordan@example.com",
                normalized_value="jordan@example.com",
                is_primary=False,
            ),
        ]
    )
    db_session.commit()

    inbound_response = client.post(
        f"/api/v1/leads/{lead_id}/communications",
        headers=headers,
        json={
            "direction": "inbound",
            "channel": "sms",
            "status": "received",
            "body": "I can talk tomorrow afternoon.",
        },
    )
    assert inbound_response.status_code == 201
    appointment_response = client.post(
        f"/api/v1/leads/{lead_id}/appointments",
        headers=headers,
        json={
            "appointment_type": "seller_call",
            "status": "scheduled",
            "scheduled_start_at": "2026-07-20T18:00:00Z",
            "location_type": "phone",
        },
    )
    assert appointment_response.status_code == 201

    detail_response = client.get(
        f"/api/v1/inbox/conversations/{conversation.id}",
        headers=headers,
    )
    assert detail_response.status_code == 200
    detail = detail_response.json()
    assert detail["seller_name"] == "Jordan Seller"
    assert detail["preferred_name"] == "Jordan"
    assert detail["motivation"] == "Inherited property"
    assert {method["method_type"] for method in detail["contact_methods"]} == {
        "phone",
        "email",
    }
    assert {item["item_type"] for item in detail["timeline"]} == {
        "assignment",
        "communication",
        "appointment",
    }
    assert detail["unread_count"] == 1

    read_response = client.patch(
        f"/api/v1/inbox/conversations/{conversation.id}/read",
        headers=headers,
    )
    assert read_response.status_code == 200
    assert read_response.json()["unread_count"] == 0


def test_general_conversation_retains_email_without_a_lead(
    db_session: Session,
    api_db_override: None,
) -> None:
    owner, _va, _acquisitions = seed_workspace(db_session)
    contact = Contact(
        organization_id=owner.organization_id,
        legal_name="Taylor Vendor",
        preferred_name="Taylor",
        contact_type="business_contact",
        assigned_user_id=owner.id,
    )
    db_session.add(contact)
    db_session.flush()
    db_session.add(
        ContactMethod(
            organization_id=owner.organization_id,
            contact_id=contact.id,
            method_type="email",
            value="taylor@example.com",
            normalized_value="taylor@example.com",
            is_primary=True,
        )
    )
    conversation = create_general_conversation(
        db_session,
        organization_id=owner.organization_id,
        contact_id=contact.id,
        assigned_user_id=owner.id,
    )
    occurred_at = datetime.now(UTC)
    communication = CommunicationRecord(
        organization_id=owner.organization_id,
        conversation_id=conversation.id,
        lead_id=None,
        contact_id=contact.id,
        actor_user_id=None,
        direction="inbound",
        channel="email",
        status="received",
        provider="resend",
        provider_message_id="general-inbound-1",
        subject="General company question",
        body="Can you send the requested company information?",
        occurred_at=occurred_at,
        external_payload={"id": "general-inbound-1"},
        communication_metadata={"source": "test"},
    )
    db_session.add(communication)
    db_session.flush()
    participants = record_email_participants(
        db_session,
        communication,
        from_values="Taylor Vendor <taylor@example.com>",
        to_values="austin@stonegatehb.com",
        external_contact_id=contact.id,
        external_roles={"from"},
        sender_user_id=None,
        source="test",
    )
    update_conversation_activity(
        conversation,
        direction="inbound",
        occurred_at=occurred_at,
    )
    db_session.commit()

    assert conversation.lead_id is None
    assert conversation.conversation_type == "general"
    assert len(participants) == 2
    assert {participant.participant_role for participant in participants} == {"from", "to"}
    sender = db_session.scalar(
        select(CommunicationParticipant).where(
            CommunicationParticipant.communication_record_id == communication.id,
            CommunicationParticipant.participant_role == "from",
        )
    )
    assert sender is not None
    assert sender.contact_id == contact.id
    assignment = db_session.scalar(
        select(ConversationAssignmentEvent).where(
            ConversationAssignmentEvent.conversation_id == conversation.id
        )
    )
    assert assignment is not None
    assert assignment.lead_id is None

    client = TestClient(app)
    headers = {"X-Dev-User-Email": OWNER_EMAIL}
    list_response = client.get("/api/v1/inbox/conversations", headers=headers)
    assert list_response.status_code == 200
    listed = next(
        item for item in list_response.json()["items"] if item["id"] == str(conversation.id)
    )
    assert listed["conversation_type"] == "general"
    assert listed["lead_id"] is None
    assert listed["property_address"] == "General correspondence"

    detail_response = client.get(
        f"/api/v1/inbox/conversations/{conversation.id}",
        headers=headers,
    )
    assert detail_response.status_code == 200
    detail = detail_response.json()
    assert detail["seller_name"] == "Taylor Vendor"
    assert detail["source"] is None
    assert detail["stage_key"] is None
    assert detail["open_tasks"] == []
    assert detail["appointments"] == []
    assert [item["subject"] for item in detail["timeline"] if item["channel"] == "email"] == [
        "General company question"
    ]


def test_restricted_general_mailbox_is_visible_only_to_owner_or_assigned_team(
    db_session: Session,
    api_db_override: None,
) -> None:
    owner, va, acquisitions = seed_workspace(db_session)
    organization = db_session.get(Organization, owner.organization_id)
    assert organization is not None
    finance = create_user_with_role(
        db_session,
        organization,
        email="finance@example.com",
        name="Finance Specialist",
        role_key="finance_accounting",
    )
    accounting_team = Team(
        organization_id=organization.id,
        name="Accounting",
        team_type="finance",
        manager_user_id=finance.id,
        is_active=True,
    )
    db_session.add(accounting_team)
    db_session.flush()
    db_session.add(
        TeamMembership(
            organization_id=organization.id,
            team_id=accounting_team.id,
            user_id=finance.id,
            membership_role="member",
        )
    )
    alias = EmailSenderAlias(
        organization_id=organization.id,
        owner_user_id=None,
        assigned_team_id=accounting_team.id,
        created_by_user_id=owner.id,
        provider="resend",
        provider_identity_id=None,
        email_address="accounting@stonegatehb.com",
        display_name="Stonegate Accounting",
        alias_type="department",
        purpose_key="accounting",
        status="active",
        inbound_enabled=True,
        outbound_enabled=True,
        is_default=False,
        signature_text=None,
        routing_metadata={"visibility_scope": "restricted"},
    )
    contact = Contact(
        organization_id=organization.id,
        legal_name="Accounting Vendor",
        preferred_name=None,
        contact_type="business_contact",
        assigned_user_id=None,
    )
    db_session.add_all([alias, contact])
    db_session.flush()
    conversation = create_general_conversation(
        db_session,
        organization_id=organization.id,
        contact_id=contact.id,
        assigned_team_id=accounting_team.id,
        source_alias_id=alias.id,
        visibility_scope="restricted",
    )
    db_session.commit()

    client = TestClient(app)
    owner_items = client.get(
        "/api/v1/inbox/conversations",
        headers={"X-Dev-User-Email": OWNER_EMAIL},
    )
    assert owner_items.status_code == 200
    assert str(conversation.id) in {item["id"] for item in owner_items.json()["items"]}

    finance_items = client.get(
        "/api/v1/inbox/conversations",
        headers={"X-Dev-User-Email": finance.email},
    )
    assert finance_items.status_code == 200
    assert [item["id"] for item in finance_items.json()["items"]] == [str(conversation.id)]

    acquisitions_items = client.get(
        "/api/v1/inbox/conversations",
        headers={"X-Dev-User-Email": acquisitions.email},
    )
    assert acquisitions_items.status_code == 200
    assert str(conversation.id) not in {item["id"] for item in acquisitions_items.json()["items"]}

    va_items = client.get(
        "/api/v1/inbox/conversations",
        headers={"X-Dev-User-Email": va.email},
    )
    assert va_items.status_code == 200
    assert str(conversation.id) not in {item["id"] for item in va_items.json()["items"]}


def test_general_email_can_be_converted_to_a_lead_without_losing_the_thread(
    db_session: Session,
    api_db_override: None,
) -> None:
    owner, _, _ = seed_workspace(db_session)
    contact = Contact(
        organization_id=owner.organization_id,
        legal_name="Email Seller",
        preferred_name="Email",
        contact_type="business_contact",
        assigned_user_id=owner.id,
    )
    db_session.add(contact)
    db_session.flush()
    db_session.add(
        ContactMethod(
            organization_id=owner.organization_id,
            contact_id=contact.id,
            method_type="email",
            value="seller@example.com",
            normalized_value="seller@example.com",
            is_primary=True,
        )
    )
    conversation = create_general_conversation(
        db_session,
        organization_id=owner.organization_id,
        contact_id=contact.id,
        assigned_user_id=owner.id,
    )
    communication = CommunicationRecord(
        organization_id=owner.organization_id,
        conversation_id=conversation.id,
        lead_id=None,
        contact_id=contact.id,
        actor_user_id=None,
        direction="inbound",
        channel="email",
        status="received",
        provider="resend",
        provider_message_id="convert-email-1",
        subject="I need to sell",
        body="I would like an offer for my vacant land.",
        occurred_at=datetime.now(UTC),
        external_payload=None,
        communication_metadata={"source": "test"},
    )
    db_session.add(communication)
    db_session.commit()

    response = TestClient(app).post(
        f"/api/v1/inbox/conversations/{conversation.id}/convert-to-lead",
        headers={"X-Dev-User-Email": OWNER_EMAIL},
        json={
            "property": {
                "street_address": "123 Email Way",
                "city": "Atlanta",
                "state": "GA",
                "postal_code": "30303",
                "property_type": "vacant_land",
                "parcel_id": "INBOX-123-LAND",
            },
            "source": "inbound_email",
            "asset_class": "land",
        },
    )

    assert response.status_code == 201
    result = response.json()
    assert result["conversation_id"] == str(conversation.id)
    lead = db_session.get(Lead, UUID(result["lead_id"]))
    db_session.refresh(conversation)
    db_session.refresh(contact)
    db_session.refresh(communication)
    assert lead is not None
    assert lead.asset_class == "land"
    assert lead.contact_id == contact.id
    assert conversation.conversation_type == "lead"
    assert conversation.lead_id == lead.id
    assert conversation.queue_key == "acquisitions_follow_up"
    assert contact.contact_type == "seller"
    assert communication.lead_id == lead.id
    property_record = db_session.get(Property, lead.property_id)
    assert property_record is not None
    assert property_record.street_address == "123 Email Way"
    assert property_record.property_type == "vacant_land"
    assert property_record.parcel_id == "INBOX-123-LAND"
    assert db_session.scalar(
        select(func.count()).select_from(Task).where(Task.lead_id == lead.id)
    ) == 1
    assert db_session.scalar(
        select(func.count())
        .select_from(ConversationContextLink)
        .where(
            ConversationContextLink.conversation_id == conversation.id,
            ConversationContextLink.lead_id == lead.id,
            ConversationContextLink.is_primary.is_(True),
        )
    ) == 1


def test_general_email_can_merge_into_an_existing_lead_conversation(
    db_session: Session,
    api_db_override: None,
) -> None:
    owner, _, _ = seed_workspace(db_session)
    client = TestClient(app)
    headers = {"X-Dev-User-Email": OWNER_EMAIL}
    lead_response = client.post(
        "/api/v1/leads",
        headers=headers,
        json=lead_payload("456 Existing Lead St"),
    )
    assert lead_response.status_code == 201
    lead = db_session.get(Lead, UUID(lead_response.json()["id"]))
    assert lead is not None
    target = db_session.scalar(select(Conversation).where(Conversation.lead_id == lead.id))
    assert target is not None

    source_contact = Contact(
        organization_id=owner.organization_id,
        legal_name="Existing Seller Alias",
        preferred_name=None,
        contact_type="business_contact",
        assigned_user_id=owner.id,
    )
    db_session.add(source_contact)
    db_session.flush()
    db_session.add(
        ContactMethod(
            organization_id=owner.organization_id,
            contact_id=source_contact.id,
            method_type="email",
            value="existing.seller@example.com",
            normalized_value="existing.seller@example.com",
            is_primary=True,
        )
    )
    source = create_general_conversation(
        db_session,
        organization_id=owner.organization_id,
        contact_id=source_contact.id,
        assigned_user_id=owner.id,
    )
    communication = CommunicationRecord(
        organization_id=owner.organization_id,
        conversation_id=source.id,
        lead_id=None,
        contact_id=source_contact.id,
        actor_user_id=None,
        direction="inbound",
        channel="email",
        status="received",
        provider="resend",
        provider_message_id="link-email-1",
        subject="More property details",
        body="Here is the information you requested.",
        occurred_at=datetime.now(UTC),
        external_payload=None,
        communication_metadata={"source": "test"},
    )
    db_session.add(communication)
    db_session.flush()
    participant = record_email_participants(
        db_session,
        communication,
        from_values="Existing Seller <existing.seller@example.com>",
        to_values="austin@stonegatehb.com",
        external_contact_id=source_contact.id,
        external_roles={"from"},
        sender_user_id=None,
        source="test",
    )[0]
    update_conversation_activity(source, direction="inbound", occurred_at=communication.occurred_at)
    db_session.commit()

    response = client.post(
        f"/api/v1/inbox/conversations/{source.id}/link-to-lead",
        headers=headers,
        json={"lead_id": str(lead.id)},
    )

    assert response.status_code == 200
    assert response.json()["conversation_id"] == str(target.id)
    db_session.refresh(source)
    db_session.refresh(target)
    db_session.refresh(communication)
    db_session.refresh(participant)
    assert source.status == "closed"
    assert source.conversation_metadata["merged_into_conversation_id"] == str(target.id)
    assert communication.conversation_id == target.id
    assert communication.lead_id == lead.id
    assert communication.contact_id == lead.contact_id
    assert participant.conversation_id == target.id
    assert participant.contact_id == lead.contact_id
    archived_source = client.get(
        f"/api/v1/inbox/conversations/{source.id}",
        headers=headers,
    )
    assert archived_source.status_code == 200
    assert archived_source.json()["merged_into_conversation_id"] == str(target.id)
    assert db_session.scalar(
        select(func.count())
        .select_from(ContactMethod)
        .where(
            ContactMethod.contact_id == lead.contact_id,
            ContactMethod.normalized_value == "existing.seller@example.com",
        )
    ) == 1


def test_general_email_classification_archives_and_restores_the_conversation(
    db_session: Session,
    api_db_override: None,
) -> None:
    owner, _, _ = seed_workspace(db_session)
    contact = Contact(
        organization_id=owner.organization_id,
        legal_name="Supply Vendor",
        preferred_name=None,
        contact_type="business_contact",
        assigned_user_id=owner.id,
    )
    db_session.add(contact)
    db_session.flush()
    conversation = create_general_conversation(
        db_session,
        organization_id=owner.organization_id,
        contact_id=contact.id,
        assigned_user_id=owner.id,
    )
    db_session.commit()
    client = TestClient(app)
    headers = {"X-Dev-User-Email": OWNER_EMAIL}

    archived = client.post(
        f"/api/v1/inbox/conversations/{conversation.id}/classification",
        headers=headers,
        json={"category": "vendor", "close": True, "reason": "Supply invoice"},
    )
    assert archived.status_code == 200
    db_session.refresh(conversation)
    assert conversation.status == "closed"
    assert conversation.queue_key == "closed"
    assert conversation.conversation_metadata["mail_category"] == "vendor"
    detail = client.get(
        f"/api/v1/inbox/conversations/{conversation.id}",
        headers=headers,
    )
    assert detail.status_code == 200
    assert detail.json()["mail_category"] == "vendor"

    restored = client.post(
        f"/api/v1/inbox/conversations/{conversation.id}/classification",
        headers=headers,
        json={"category": "vendor", "close": False},
    )
    assert restored.status_code == 200
    db_session.refresh(conversation)
    assert conversation.status == "open"
    assert conversation.queue_key == "unassigned"
    assert conversation.closed_at is None
