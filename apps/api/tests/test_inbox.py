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
    CommunicationProviderEvent,
    ContactMethod,
    Conversation,
    ConversationAssignmentEvent,
    ConversationWatcher,
    Lead,
    Organization,
    Role,
    RoleAssignment,
    Task,
    UnderwritingVersion,
    User,
)
from app.services.bootstrap import bootstrap_foundation

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
    assert db_session.scalar(
        select(func.count())
        .select_from(ConversationWatcher)
        .where(
            ConversationWatcher.conversation_id == qualified_conversation.id,
            ConversationWatcher.user_id == owner.id,
        )
    ) == 1

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
