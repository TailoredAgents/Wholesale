from datetime import UTC, datetime, timedelta
from typing import Any, cast
from uuid import UUID

from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.auth import principal_for_user
from app.main import app
from app.models.foundation import (
    ActivityEvent,
    AiOrchestratorEvent,
    Appointment,
    ApprovalRequest,
    AuditEvent,
    CalendarEvent,
    CallingList,
    CallingListEntry,
    CallRecord,
    Conversation,
    Deal,
    FollowUpEnrollment,
    FollowUpPlan,
    Lead,
    LeadManagementCase,
    Notification,
    Task,
    User,
)
from app.services.bootstrap import bootstrap_foundation
from app.services.inbox import update_conversation_activity
from app.services.management_intelligence import build_management_facts
from app.services.voice import ensure_missed_call_task

OWNER_EMAIL = "owner@example.com"
HEADERS = {"X-Dev-User-Email": OWNER_EMAIL}


def seed_owner(db: Session) -> User:
    bootstrap_foundation(
        db,
        organization_name="Stonegate Home Buyers",
        admin_email=OWNER_EMAIL,
        admin_name="Owner",
    )
    owner = db.scalar(select(User).where(User.email == OWNER_EMAIL))
    assert owner is not None
    return owner


def lead_payload(
    name: str = "Closed Seller", street: str = "123 Closeout Lane"
) -> dict[str, Any]:
    return {
        "contact": {"legal_name": name, "contact_type": "seller"},
        "property": {
            "street_address": street,
            "city": "Atlanta",
            "state": "GA",
            "postal_code": "30303",
            "property_type": "single_family",
        },
        "source": "manual",
        "stage_key": "new",
    }


def create_lead(client: TestClient, **kwargs: str) -> dict[str, Any]:
    response = client.post("/api/v1/leads", headers=HEADERS, json=lead_payload(**kwargs))
    assert response.status_code == 201, response.text
    return cast(dict[str, Any], response.json())


def seed_close_out_work(db: Session, lead: Lead, owner: User) -> dict[str, Any]:
    now = datetime.now(UTC)
    conversation = db.scalar(select(Conversation).where(Conversation.lead_id == lead.id))
    assert conversation is not None
    conversation.unread_count = 3

    supporting_task = Task(
        organization_id=lead.organization_id,
        lead_id=lead.id,
        deal_id=None,
        responsible_user_id=owner.id,
        task_type="seller_research",
        work_kind="supporting",
        title="Research seller situation",
        status="in_progress",
        priority="normal",
        due_at=now - timedelta(hours=1),
        completed_at=None,
    )
    appointment = Appointment(
        organization_id=lead.organization_id,
        lead_id=lead.id,
        contact_id=lead.contact_id,
        property_id=lead.property_id,
        owner_user_id=owner.id,
        appointment_type="seller_visit",
        status="scheduled",
        scheduled_start_at=now + timedelta(days=1),
        scheduled_end_at=now + timedelta(days=1, hours=1),
        location_type="property",
        location="123 Closeout Lane",
        notes="Walkthrough",
        outcome=None,
        external_calendar_id=None,
        appointment_metadata={"source": "test"},
    )
    plan = FollowUpPlan(
        organization_id=lead.organization_id,
        name="Closeout regression plan",
        description=None,
        status="active",
        created_by_user_id=owner.id,
        steps=[{"delay_days": 1, "action_type": "sms", "title": "Check in"}],
    )
    calling_list = CallingList(
        organization_id=lead.organization_id,
        name="Closeout calling list",
        description=None,
        status="active",
        created_by_user_id=owner.id,
        default_assignee_user_id=owner.id,
    )
    db.add_all((supporting_task, appointment, plan, calling_list))
    db.flush()
    calendar_event = CalendarEvent(
        organization_id=lead.organization_id,
        appointment_id=appointment.id,
        owner_user_id=owner.id,
        provider="internal",
        external_event_id=None,
        status="scheduled",
        event_payload={"status": "scheduled"},
        last_error=None,
        synced_at=None,
    )
    prior_enrollment = FollowUpEnrollment(
        organization_id=lead.organization_id,
        follow_up_plan_id=plan.id,
        lead_id=lead.id,
        enrolled_by_user_id=owner.id,
        status="cancelled",
        started_at=now - timedelta(days=10),
        completed_at=now - timedelta(days=5),
        current_step=1,
    )
    active_enrollment = FollowUpEnrollment(
        organization_id=lead.organization_id,
        follow_up_plan_id=plan.id,
        lead_id=lead.id,
        enrolled_by_user_id=owner.id,
        status="active",
        started_at=now,
        completed_at=None,
        current_step=0,
    )
    approval = ApprovalRequest(
        organization_id=lead.organization_id,
        requested_by_user_id=owner.id,
        assigned_to_user_id=owner.id,
        decided_by_user_id=None,
        request_type="follow_up_sms",
        entity_type="lead",
        entity_id=lead.id,
        status="pending",
        title="Send follow-up",
        summary="Future follow-up message",
        decision_notes=None,
        due_at=now + timedelta(days=1),
        decided_at=None,
        approval_metadata={"source": "test"},
    )
    call_notes_approval = ApprovalRequest(
        organization_id=lead.organization_id,
        requested_by_user_id=owner.id,
        assigned_to_user_id=owner.id,
        decided_by_user_id=None,
        request_type="call_notes_review",
        entity_type="call_transcript",
        entity_id=None,
        status="pending",
        title="Review call notes",
        summary="Review historical call notes before applying them.",
        decision_notes=None,
        due_at=now + timedelta(days=1),
        decided_at=None,
        approval_metadata={"lead_id": str(lead.id), "source": "test"},
    )
    management_case = LeadManagementCase(
        organization_id=lead.organization_id,
        lead_id=lead.id,
        handoff_id=None,
        assigned_user_id=owner.id,
        status="active",
        acceptance_due_at=now,
        accepted_at=now,
        accepted_by_user_id=owner.id,
        escalated_at=None,
        qualification_script_version_id=None,
        qualification_started_at=now,
        qualification_completed_at=None,
        qualification_quality_basis_points=None,
        next_action_type="call",
        next_action_due_at=now + timedelta(hours=2),
        last_contact_at=None,
        closed_at=None,
    )
    entry = CallingListEntry(
        organization_id=lead.organization_id,
        calling_list_id=calling_list.id,
        lead_id=lead.id,
        assigned_user_id=owner.id,
        status="queued",
        attempt_count=0,
        disposition=None,
        notes=None,
        last_attempt_at=None,
        completed_at=None,
    )
    ai_event = AiOrchestratorEvent(
        organization_id=lead.organization_id,
        event_key=f"closeout-next-action:{lead.id}",
        event_type="lead.created",
        entity_type="lead",
        entity_id=lead.id,
        status="needs_review",
        payload={"capability_key": "lead.next_action"},
        occurred_at=now,
        processed_at=None,
        last_error=None,
    )
    db.add_all(
        (
            calendar_event,
            prior_enrollment,
            active_enrollment,
            approval,
            call_notes_approval,
            management_case,
            entry,
            ai_event,
        )
    )
    db.flush()
    for index, (entity_type, entity_id) in enumerate(
        (
            ("lead", lead.id),
            ("task", supporting_task.id),
            ("appointment", appointment.id),
            ("lead_management_case", management_case.id),
            ("conversation", conversation.id),
        )
    ):
        db.add(
            Notification(
                organization_id=lead.organization_id,
                recipient_user_id=owner.id,
                notification_type="overdue_task",
                title="Action required",
                body="Actionable warning",
                entity_type=entity_type,
                entity_id=entity_id,
                action_url=f"/test/{index}",
                dedupe_key=f"closeout-warning:{lead.id}:{index}",
                read_at=None,
            )
        )
    db.commit()
    return {
        "appointment": appointment,
        "calendar_event": calendar_event,
        "management_case": management_case,
        "conversation": conversation,
        "prior_enrollment": prior_enrollment,
        "active_enrollment": active_enrollment,
        "approval": approval,
        "call_notes_approval": call_notes_approval,
        "entry": entry,
        "ai_event": ai_event,
    }


def test_close_out_is_atomic_visible_and_idempotent_then_reopens_with_one_task(
    db_session: Session,
    api_db_override: None,
) -> None:
    owner = seed_owner(db_session)
    client = TestClient(app)
    created = create_lead(client)
    lead = db_session.get(Lead, UUID(created["id"]))
    assert lead is not None
    seeded = seed_close_out_work(db_session, lead, owner)

    response = client.post(
        f"/api/v1/leads/{lead.id}/close-out",
        headers=HEADERS,
        json={
            "disposition": "disqualified",
            "reason": "The submission is spam and has no valid seller contact.",
        },
    )

    assert response.status_code == 200, response.text
    result = response.json()
    assert result["changed"] is True
    assert result["cancelled_tasks"] >= 2
    assert result["cancelled_appointments"] == 1
    assert result["cancelled_follow_up_enrollments"] == 1
    assert result["cancelled_follow_up_approvals"] == 1
    assert result["cancelled_pending_approvals"] == 2
    assert result["completed_calling_list_entries"] == 1
    assert result["dismissed_ai_next_action_events"] >= 1
    assert result["dismissed_notifications"] == 5
    assert result["closed_lead_management_case"] is True
    assert result["closed_conversation"] is True
    assert result["lead"]["stage_key"] == "disqualified"
    assert result["lead"]["archived_at"] is not None
    assert result["lead"]["close_out_disposition"] == "disqualified"
    assert result["lead"]["close_out_reason"].startswith("The submission is spam")
    assert result["lead"]["closed_out_by_user_email"] == OWNER_EMAIL

    db_session.expire_all()
    lead = db_session.get(Lead, lead.id)
    assert lead is not None and lead.next_follow_up_at is None
    tasks = db_session.scalars(select(Task).where(Task.lead_id == lead.id)).all()
    assert tasks and all(task.status == "cancelled" for task in tasks)
    assert db_session.get(Appointment, seeded["appointment"].id).status == "cancelled"  # type: ignore[union-attr]
    assert db_session.get(CalendarEvent, seeded["calendar_event"].id).status == "cancelled"  # type: ignore[union-attr]
    case = db_session.get(LeadManagementCase, seeded["management_case"].id)
    assert case is not None and case.status == "closed" and case.next_action_due_at is None
    conversation = db_session.get(Conversation, seeded["conversation"].id)
    assert conversation is not None
    assert (conversation.status, conversation.queue_key, conversation.unread_count) == (
        "closed",
        "closed",
        0,
    )
    prior = db_session.get(FollowUpEnrollment, seeded["prior_enrollment"].id)
    active = db_session.get(FollowUpEnrollment, seeded["active_enrollment"].id)
    assert prior is not None and prior.status == "cancelled"
    assert active is not None and active.status.startswith("cancelled:")
    assert db_session.get(ApprovalRequest, seeded["approval"].id).status == "cancelled"  # type: ignore[union-attr]
    assert db_session.get(ApprovalRequest, seeded["call_notes_approval"].id).status == "cancelled"  # type: ignore[union-attr]
    assert db_session.get(CallingListEntry, seeded["entry"].id).status == "completed"  # type: ignore[union-attr]
    assert db_session.get(AiOrchestratorEvent, seeded["ai_event"].id).status == "dismissed"  # type: ignore[union-attr]
    assert db_session.scalar(
        select(func.count(Notification.id)).where(Notification.read_at.is_(None))
    ) == 0

    closed = client.get("/api/v1/leads?closed=true", headers=HEADERS).json()["items"]
    archived = client.get("/api/v1/leads?archived=true", headers=HEADERS).json()["items"]
    active_leads = client.get("/api/v1/leads", headers=HEADERS).json()["items"]
    assert [item["id"] for item in closed] == [str(lead.id)]
    assert archived == []
    assert active_leads == []

    repeat = client.post(
        f"/api/v1/leads/{lead.id}/close-out",
        headers=HEADERS,
        json={
            "disposition": "disqualified",
            "reason": "The submission is spam and has no valid seller contact.",
        },
    )
    assert repeat.status_code == 200
    assert repeat.json()["changed"] is False
    assert db_session.scalar(
        select(func.count(AuditEvent.id)).where(AuditEvent.action == "lead.close_out")
    ) == 1

    stale_ai_event = db_session.get(AiOrchestratorEvent, seeded["ai_event"].id)
    assert stale_ai_event is not None
    stale_ai_event.status = "needs_review"
    db_session.commit()
    blocked_review = client.patch(
        f"/api/v1/tasks/ai-work/{stale_ai_event.id}/review",
        headers=HEADERS,
        json={"decision": "accepted", "notes": "This stale review must not be applied."},
    )
    assert blocked_review.status_code == 422
    assert "Reopen the closed lead" in blocked_review.json()["detail"]
    stale_ai_event.status = "dismissed"
    db_session.commit()

    due_at = datetime.now(UTC) + timedelta(days=2)
    reopen = client.post(
        f"/api/v1/leads/{lead.id}/reopen",
        headers=HEADERS,
        json={
            "reason": "The seller supplied valid information and asked us to reconnect.",
            "next_action_due_at": due_at.isoformat(),
            "next_action_title": "Call the seller about the corrected submission",
        },
    )
    assert reopen.status_code == 200, reopen.text
    assert reopen.json()["lead"]["stage_key"] == "reopened"
    assert reopen.json()["lead"]["archived_at"] is None
    assert reopen.json()["lead"]["close_out_disposition"] == "disqualified"
    db_session.expire_all()
    primary = db_session.scalars(
        select(Task).where(
            Task.lead_id == lead.id,
            Task.work_kind == "primary_next_action",
            Task.status.in_(("open", "in_progress")),
        )
    ).all()
    assert len(primary) == 1
    case = db_session.get(LeadManagementCase, seeded["management_case"].id)
    assert case is not None
    assert case.status == "active" and case.accepted_at is not None
    assert case.next_action_due_at is not None
    conversation = db_session.get(Conversation, seeded["conversation"].id)
    assert conversation is not None
    assert (conversation.status, conversation.queue_key) == ("open", "acquisitions_follow_up")

    archive_reopened = client.delete(f"/api/v1/leads/{lead.id}", headers=HEADERS)
    assert archive_reopened.status_code == 200
    assert client.get("/api/v1/leads?closed=true", headers=HEADERS).json()["items"] == []
    archived_reopened = client.get(
        "/api/v1/leads?archived=true", headers=HEADERS
    ).json()["items"]
    assert [item["id"] for item in archived_reopened] == [str(lead.id)]
    restore_reopened = client.post(f"/api/v1/leads/{lead.id}/restore", headers=HEADERS)
    assert restore_reopened.status_code == 200, restore_reopened.text
    assert restore_reopened.json()["close_out_disposition"] == "disqualified"


def test_close_out_validates_lifecycle_and_blocks_active_deal(
    db_session: Session,
    api_db_override: None,
) -> None:
    seed_owner(db_session)
    client = TestClient(app)
    created = create_lead(client, name="Contract Seller", street="9 Contract Road")
    lead = db_session.get(Lead, UUID(created["id"]))
    assert lead is not None
    deal = Deal(
        organization_id=lead.organization_id,
        lead_id=lead.id,
        property_id=lead.property_id,
        stage_key="under_contract",
        contract_price_cents=100_000_00,
        assignment_fee_cents=10_000_00,
    )
    db_session.add(deal)
    db_session.commit()

    too_short = client.post(
        f"/api/v1/leads/{lead.id}/close-out",
        headers=HEADERS,
        json={"disposition": "dead", "reason": "No"},
    )
    assert too_short.status_code == 422
    blocked = client.post(
        f"/api/v1/leads/{lead.id}/close-out",
        headers=HEADERS,
        json={"disposition": "dead", "reason": "Seller declined the offer and ended talks."},
    )
    assert blocked.status_code == 409
    db_session.refresh(lead)
    assert lead.archived_at is None and lead.stage_key == "new"

    direct_terminal = client.patch(
        f"/api/v1/leads/{lead.id}/stage",
        headers=HEADERS,
        json={"stage_key": "dead", "reason": "Trying to bypass close out."},
    )
    assert direct_terminal.status_code == 422
    assert "Close out lead" in direct_terminal.json()["detail"]

    lead.stage_key = "dead"
    db_session.commit()
    archive_terminal = client.delete(f"/api/v1/leads/{lead.id}", headers=HEADERS)
    assert archive_terminal.status_code == 422
    assert "Close out lead" in archive_terminal.json()["detail"]


def test_reopen_then_reclose_refreshes_timestamp_and_normalizes_stale_appointment_state(
    db_session: Session,
    api_db_override: None,
) -> None:
    seed_owner(db_session)
    client = TestClient(app)
    first = create_lead(client, name="Repeat Seller", street="15 Repeat Way")
    first_id = UUID(first["id"])
    first_lead = db_session.get(Lead, first_id)
    assert first_lead is not None
    first_lead.appointment_status = "scheduled"
    db_session.commit()
    payload = {
        "disposition": "dead",
        "reason": "The seller confirmed they do not want any further contact.",
    }
    initial_close = client.post(
        f"/api/v1/leads/{first_id}/close-out", headers=HEADERS, json=payload
    )
    assert initial_close.status_code == 200, initial_close.text
    initial_closed_at = datetime.fromisoformat(initial_close.json()["lead"]["closed_out_at"])
    assert initial_close.json()["lead"]["appointment_status"] == "cancelled"

    reopen = client.post(
        f"/api/v1/leads/{first_id}/reopen",
        headers=HEADERS,
        json={
            "reason": "The seller contacted Stonegate again and requested a new conversation.",
            "next_action_due_at": (datetime.now(UTC) + timedelta(days=1)).isoformat(),
            "next_action_title": "Return the seller's new call",
        },
    )
    assert reopen.status_code == 200, reopen.text

    second = create_lead(client, name="Other Closed Seller", street="16 Repeat Way")
    second_close = client.post(
        f"/api/v1/leads/{second['id']}/close-out", headers=HEADERS, json=payload
    )
    assert second_close.status_code == 200, second_close.text

    reclose = client.post(
        f"/api/v1/leads/{first_id}/close-out", headers=HEADERS, json=payload
    )
    assert reclose.status_code == 200, reclose.text
    refreshed_closed_at = datetime.fromisoformat(reclose.json()["lead"]["closed_out_at"])
    assert refreshed_closed_at > initial_closed_at
    closed = client.get("/api/v1/leads?closed=true", headers=HEADERS).json()["items"]
    assert [item["id"] for item in closed[:2]] == [str(first_id), second["id"]]

    conversation = db_session.scalar(select(Conversation).where(Conversation.lead_id == first_id))
    lead = db_session.get(Lead, first_id)
    assert conversation is not None and lead is not None
    delayed_missed_call = CallRecord(
        organization_id=lead.organization_id,
        conversation_id=conversation.id,
        lead_id=lead.id,
        contact_id=lead.contact_id,
        actor_user_id=None,
        communication_record_id=None,
        voice_line_id=None,
        call_intent_id=None,
        provider="twilio",
        provider_call_id=f"stale-missed-{lead.id}",
        child_provider_call_id=None,
        direction="inbound",
        status="no-answer",
        from_number="+14045550123",
        to_number="+16785550123",
        started_at=initial_closed_at - timedelta(minutes=1),
        answered_at=None,
        ended_at=initial_closed_at,
        duration_seconds=0,
        disposition=None,
        recording_consent_status="not_requested",
        call_metadata={},
    )
    db_session.add(delayed_missed_call)
    db_session.flush()
    ensure_missed_call_task(db_session, delayed_missed_call)
    db_session.commit()
    assert db_session.scalar(
        select(func.count(Task.id)).where(
            Task.lead_id == first_id,
            Task.status.in_(("open", "in_progress")),
        )
    ) == 0


def test_funded_deal_cannot_be_reclassified_as_dead(
    db_session: Session,
    api_db_override: None,
) -> None:
    seed_owner(db_session)
    client = TestClient(app)
    created = create_lead(client, name="Funded Seller", street="44 Success Street")
    lead = db_session.get(Lead, UUID(created["id"]))
    assert lead is not None
    deal = Deal(
        organization_id=lead.organization_id,
        lead_id=lead.id,
        property_id=lead.property_id,
        stage_key="funded",
        contract_price_cents=100_000_00,
        assignment_fee_cents=10_000_00,
    )
    db_session.add(deal)
    db_session.commit()

    response = client.post(
        f"/api/v1/leads/{lead.id}/close-out",
        headers=HEADERS,
        json={
            "disposition": "dead",
            "reason": "This should never reclassify a successfully funded seller lead.",
        },
    )
    assert response.status_code == 409
    assert "funded deal" in response.json()["detail"].lower()


def test_inbound_activity_auto_reopens_closed_lead_once_and_terminal_intelligence_is_quiet(
    db_session: Session,
    api_db_override: None,
) -> None:
    owner = seed_owner(db_session)
    client = TestClient(app)
    created = create_lead(client, name="Returning Seller", street="88 Return Street")
    lead_id = UUID(created["id"])
    close = client.post(
        f"/api/v1/leads/{lead_id}/close-out",
        headers=HEADERS,
        json={
            "disposition": "dead",
            "reason": "The seller stopped responding after several documented attempts.",
        },
    )
    assert close.status_code == 200, close.text
    detail = client.get(f"/api/v1/leads/{lead_id}", headers=HEADERS).json()
    assert detail["intelligence"]["urgency_score"] == 0
    assert detail["intelligence"]["missing_fields"] == []
    assert detail["intelligence"]["next_best_action"]["action_type"] == "reopen_required"

    conversation = db_session.scalar(select(Conversation).where(Conversation.lead_id == lead_id))
    assert conversation is not None
    update_conversation_activity(
        conversation,
        direction="inbound",
        occurred_at=datetime.now(UTC),
        db=db_session,
    )
    db_session.commit()
    db_session.expire_all()
    lead = db_session.get(Lead, lead_id)
    assert lead is not None
    assert lead.archived_at is None and lead.stage_key == "reopened"
    assert lead.close_out_disposition == "dead"
    conversation = db_session.get(Conversation, conversation.id)
    assert conversation is not None
    assert conversation.status == "open" and conversation.unread_count == 1
    primary = db_session.scalars(
        select(Task).where(
            Task.lead_id == lead_id,
            Task.work_kind == "primary_next_action",
            Task.status.in_(("open", "in_progress")),
        )
    ).all()
    assert len(primary) == 1 and primary[0].priority == "urgent"

    missed_call = CallRecord(
        organization_id=lead.organization_id,
        conversation_id=conversation.id,
        lead_id=lead.id,
        contact_id=lead.contact_id,
        actor_user_id=None,
        communication_record_id=None,
        voice_line_id=None,
        call_intent_id=None,
        provider="twilio",
        provider_call_id=f"missed-after-reopen-{lead.id}",
        child_provider_call_id=None,
        direction="inbound",
        status="no-answer",
        from_number="+14045550123",
        to_number="+16785550123",
        started_at=datetime.now(UTC),
        answered_at=None,
        ended_at=datetime.now(UTC),
        duration_seconds=0,
        disposition=None,
        recording_consent_status="not_requested",
        call_metadata={},
    )
    db_session.add(missed_call)
    db_session.flush()
    ensure_missed_call_task(db_session, missed_call)
    db_session.commit()
    assert db_session.scalar(
        select(func.count(Task.id)).where(
            Task.lead_id == lead_id,
            Task.status.in_(("open", "in_progress")),
        )
    ) == 1

    update_conversation_activity(
        conversation,
        direction="inbound",
        occurred_at=datetime.now(UTC),
        db=db_session,
    )
    db_session.commit()
    assert db_session.scalar(
        select(func.count(Task.id)).where(
            Task.lead_id == lead_id,
            Task.work_kind == "primary_next_action",
            Task.status.in_(("open", "in_progress")),
        )
    ) == 1
    assert db_session.scalar(
        select(func.count(ActivityEvent.id)).where(
            ActivityEvent.event_type == "lead.auto_reopened_from_inbound"
        )
    ) == 1

    primary[0].status = "cancelled"
    primary[0].due_at = datetime.now(UTC) - timedelta(days=1)
    db_session.commit()
    facts = build_management_facts(
        db_session,
        principal_for_user(db_session, owner),
        "operations.brief",
        30,
    )
    assert facts["context"]["pipeline"]["overdue_tasks"] == 0


def test_inbound_does_not_reactivate_an_administratively_archived_lead(
    db_session: Session,
    api_db_override: None,
) -> None:
    seed_owner(db_session)
    client = TestClient(app)
    created = create_lead(client, name="Test Archive", street="77 Archive Avenue")
    lead_id = UUID(created["id"])
    archive = client.delete(f"/api/v1/leads/{lead_id}", headers=HEADERS)
    assert archive.status_code == 200

    conversation = db_session.scalar(select(Conversation).where(Conversation.lead_id == lead_id))
    assert conversation is not None
    update_conversation_activity(
        conversation,
        direction="inbound",
        occurred_at=datetime.now(UTC),
        db=db_session,
    )
    db_session.commit()
    db_session.expire_all()
    lead = db_session.get(Lead, lead_id)
    assert lead is not None
    assert lead.archived_at is not None and lead.stage_key == "new"
    assert lead.close_out_disposition is None and lead.closed_out_at is None
    assert db_session.scalar(
        select(func.count(Task.id)).where(
            Task.lead_id == lead_id,
            Task.task_type == "inbound_reactivation",
        )
    ) == 0
    assert client.get("/api/v1/leads?closed=true", headers=HEADERS).json()["items"] == []
    archived = client.get("/api/v1/leads?archived=true", headers=HEADERS).json()["items"]
    assert [item["id"] for item in archived] == [str(lead_id)]


def test_delayed_inbound_from_before_latest_close_out_does_not_reactivate_lead(
    db_session: Session,
    api_db_override: None,
) -> None:
    seed_owner(db_session)
    client = TestClient(app)
    created = create_lead(client, name="Delayed Event Seller", street="21 Retry Road")
    lead_id = UUID(created["id"])
    close = client.post(
        f"/api/v1/leads/{lead_id}/close-out",
        headers=HEADERS,
        json={
            "disposition": "dead",
            "reason": "The seller explicitly ended discussions after the earlier message.",
        },
    )
    assert close.status_code == 200, close.text
    db_session.expire_all()
    lead = db_session.get(Lead, lead_id)
    conversation = db_session.scalar(select(Conversation).where(Conversation.lead_id == lead_id))
    assert lead is not None and lead.closed_out_at is not None
    assert conversation is not None

    update_conversation_activity(
        conversation,
        direction="inbound",
        occurred_at=lead.closed_out_at - timedelta(seconds=1),
        db=db_session,
    )
    db_session.commit()
    db_session.expire_all()

    lead = db_session.get(Lead, lead_id)
    conversation = db_session.get(Conversation, conversation.id)
    assert lead is not None and lead.archived_at is not None and lead.stage_key == "dead"
    assert conversation is not None and conversation.status == "closed"
    assert db_session.scalar(
        select(func.count(Task.id)).where(
            Task.lead_id == lead_id,
            Task.task_type == "inbound_reactivation",
            Task.status.in_(("open", "in_progress")),
        )
    ) == 0
    assert db_session.scalar(
        select(func.count(ActivityEvent.id)).where(
            ActivityEvent.entity_id == lead_id,
            ActivityEvent.event_type == "lead.auto_reopened_from_inbound",
        )
    ) == 0


def test_close_out_is_tenant_scoped(
    db_session: Session,
    api_db_override: None,
) -> None:
    seed_owner(db_session)
    bootstrap_foundation(
        db_session,
        organization_name="Other Home Buyers",
        admin_email="other-owner@example.com",
        admin_name="Other Owner",
    )
    client = TestClient(app)
    other_response = client.post(
        "/api/v1/leads",
        headers={"X-Dev-User-Email": "other-owner@example.com"},
        json=lead_payload(name="Other Seller", street="5 Tenant Way"),
    )
    assert other_response.status_code == 201, other_response.text
    response = client.post(
        f"/api/v1/leads/{other_response.json()['id']}/close-out",
        headers=HEADERS,
        json={
            "disposition": "dead",
            "reason": "This reason must never cross an organization boundary.",
        },
    )
    assert response.status_code == 404
    other_lead = db_session.get(Lead, UUID(other_response.json()["id"]))
    assert other_lead is not None and other_lead.archived_at is None
