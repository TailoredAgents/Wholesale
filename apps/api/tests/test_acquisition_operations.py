from datetime import UTC, datetime, timedelta
from typing import Any, cast
from uuid import UUID

from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.main import app
from app.models.foundation import (
    ApprovalRequest,
    CalendarEvent,
    ContactMethod,
    Conversation,
    Lead,
    LeadMergeEvent,
    Notification,
    StaffLeadAlert,
    Task,
    User,
)
from app.services.acquisition_operations import process_next_acquisition_reminder
from app.services.bootstrap import bootstrap_foundation
from app.services.meta_lead_ads import process_next_staff_lead_alert

OWNER_EMAIL = "owner@example.com"
VA_EMAIL = "caller@example.com"
ACQUISITIONS_EMAIL = "acquisitions@example.com"


def lead_payload(street_address: str, seller_name: str = "Test Seller") -> dict[str, object]:
    return {
        "contact": {"legal_name": seller_name, "contact_type": "seller"},
        "property": {
            "street_address": street_address,
            "city": "Atlanta",
            "state": "GA",
            "postal_code": "30303",
            "property_type": "single_family",
        },
        "source": "cold_call",
        "stage_key": "new",
    }


def seed_owner(db_session: Session) -> None:
    bootstrap_foundation(
        db_session,
        organization_name="Stonegate Home Buyers",
        admin_email=OWNER_EMAIL,
        admin_name="Owner",
    )


def create_user(
    client: TestClient,
    headers: dict[str, str],
    email: str,
    role: str,
) -> dict[str, Any]:
    response = client.post(
        "/api/v1/operations/users",
        headers=headers,
        json={"email": email, "display_name": email.split("@")[0].title(), "role_key": role},
    )
    assert response.status_code == 201, response.text
    return cast(dict[str, Any], response.json())


def create_lead(
    client: TestClient,
    headers: dict[str, str],
    address: str,
) -> dict[str, Any]:
    response = client.post(
        "/api/v1/leads",
        headers=headers,
        json=lead_payload(address),
    )
    assert response.status_code == 201, response.text
    return cast(dict[str, Any], response.json())


def test_acquisitions_team_routes_inactive_and_qualified_leads(
    db_session: Session,
    api_db_override: None,
) -> None:
    seed_owner(db_session)
    client = TestClient(app)
    headers = {"X-Dev-User-Email": OWNER_EMAIL}
    gracie = create_user(client, headers, "gracie@example.com", "acquisition_rep")
    devon = create_user(client, headers, "devon@example.com", "acquisition_manager")
    tina = create_user(client, headers, "tina@example.com", "acquisition_rep")

    team_response = client.post(
        "/api/v1/operations/teams",
        headers=headers,
        json={
            "name": "Acquisitions",
            "team_type": "acquisitions",
            "manager_user_id": devon["id"],
        },
    )
    assert team_response.status_code == 201, team_response.text
    team_id = team_response.json()["id"]
    member_response = client.post(
        f"/api/v1/operations/teams/{team_id}/members",
        headers=headers,
        json={"user_id": gracie["id"], "membership_role": "member"},
    )
    assert member_response.status_code == 200, member_response.text

    automatic_lead_response = client.post(
        "/api/v1/leads",
        headers=headers,
        json=lead_payload("303 Automatic Route Way"),
    )
    assert automatic_lead_response.status_code == 201, automatic_lead_response.text
    automatic_lead = db_session.get(Lead, UUID(automatic_lead_response.json()["id"]))
    assert automatic_lead is not None
    assert automatic_lead.assigned_user_id == UUID(gracie["id"])

    payload = lead_payload("404 Routing Way")
    payload["assigned_user_id"] = tina["id"]
    lead_response = client.post("/api/v1/leads", headers=headers, json=payload)
    assert lead_response.status_code == 201, lead_response.text
    lead_id = lead_response.json()["id"]

    deactivate_response = client.patch(
        f"/api/v1/operations/users/{tina['id']}",
        headers=headers,
        json={
            "is_active": False,
            "reason": "Former employee no longer manages seller leads.",
        },
    )
    assert deactivate_response.status_code == 200, deactivate_response.text

    route_response = client.post(
        f"/api/v1/operations/teams/{team_id}/apply-lead-routing",
        headers=headers,
    )
    assert route_response.status_code == 200, route_response.text
    assert route_response.json() == {
        "initial_owner_name": "Gracie",
        "qualified_owner_name": "Devon",
        "reassigned_to_initial": 1,
        "reassigned_to_qualified": 0,
        "reassigned_total": 1,
    }
    lead = db_session.get(Lead, UUID(lead_id))
    assert lead is not None
    assert lead.assigned_user_id == UUID(gracie["id"])

    stage_response = client.patch(
        f"/api/v1/leads/{lead_id}/stage",
        headers=headers,
        json={"stage_key": "qualified", "expected_stage_key": "new"},
    )
    assert stage_response.status_code == 200, stage_response.text
    db_session.refresh(lead)
    assert lead.assigned_user_id == UUID(devon["id"])

    conversation = db_session.scalar(
        select(Conversation).where(Conversation.lead_id == lead.id)
    )
    assert conversation is not None
    assert conversation.assigned_user_id == UUID(devon["id"])
    assert conversation.assigned_team_id == UUID(team_id)


def test_team_members_can_be_reviewed_updated_and_removed(
    db_session: Session,
    api_db_override: None,
) -> None:
    seed_owner(db_session)
    client = TestClient(app)
    headers = {"X-Dev-User-Email": OWNER_EMAIL}
    rep = create_user(client, headers, "rep@example.com", "acquisition_rep")
    team_response = client.post(
        "/api/v1/operations/teams",
        headers=headers,
        json={"name": "Acquisitions", "team_type": "acquisitions"},
    )
    assert team_response.status_code == 201, team_response.text
    team_id = team_response.json()["id"]

    add_response = client.post(
        f"/api/v1/operations/teams/{team_id}/members",
        headers=headers,
        json={"user_id": rep["id"], "membership_role": "manager"},
    )
    assert add_response.status_code == 200, add_response.text
    assert add_response.json()["manager_user_id"] == rep["id"]
    assert add_response.json()["members"][0]["display_name"] == "Rep"

    remove_response = client.delete(
        f"/api/v1/operations/teams/{team_id}/members/{rep['id']}",
        headers=headers,
    )
    assert remove_response.status_code == 200, remove_response.text
    assert remove_response.json()["manager_user_id"] is None
    assert remove_response.json()["members"] == []


def test_owner_can_create_another_full_access_owner(
    db_session: Session,
    api_db_override: None,
) -> None:
    seed_owner(db_session)
    client = TestClient(app)
    owner_headers = {"X-Dev-User-Email": OWNER_EMAIL}
    second_owner_email = "devon@example.com"
    second_owner = create_user(client, owner_headers, second_owner_email, "owner")
    assert second_owner["role_keys"] == ["owner"]

    profile = client.get(
        "/api/v1/me",
        headers={"X-Dev-User-Email": second_owner_email},
    )
    assert profile.status_code == 200, profile.text
    assert "owner" in profile.json()["role_keys"]
    assert "integrations:manage_credentials" in profile.json()["permissions"]


def test_operations_assistant_has_broad_work_access_without_sensitive_authority(
    db_session: Session,
    api_db_override: None,
) -> None:
    seed_owner(db_session)
    client = TestClient(app)
    owner_headers = {"X-Dev-User-Email": OWNER_EMAIL}
    assistant_email = "assistant@example.com"
    assistant_headers = {"X-Dev-User-Email": assistant_email}

    assistant = create_user(
        client,
        owner_headers,
        assistant_email,
        "operations_assistant",
    )
    assert assistant["role_keys"] == ["operations_assistant"]

    profile_response = client.get("/api/v1/me", headers=assistant_headers)
    assert profile_response.status_code == 200, profile_response.text
    permissions = set(profile_response.json()["permissions"])
    assert permissions == {
        "buyers:edit",
        "buyers:view",
        "communications:access_recordings",
        "communications:place_calls",
        "communications:send_email",
        "communications:send_sms",
        "communications:view_conversations",
        "calling_lists:work_assigned",
        "deals:edit",
        "deals:view",
        "dispositions:view",
        "leads:edit",
        "leads:view",
        "operations:view",
        "underwriting:edit",
    }

    acceptance_response = client.post(
        "/api/v1/operating-model/setup/role-acceptances",
        headers=owner_headers,
        json={
            "user_id": assistant["id"],
            "role_key": "operations_assistant",
            "manual_key": "operations_assistant",
            "manual_version": "2026.08",
        },
    )
    assert acceptance_response.status_code == 201, acceptance_response.text
    assert acceptance_response.json()["status"] == "assigned"

    lead = create_lead(client, assistant_headers, "303 Operations Assistant Way")
    for path in (
        "/api/v1/inbox/conversations",
        "/api/v1/tasks/workspace",
        "/api/v1/operations",
        "/api/v1/prospecting",
        "/api/v1/deals",
        "/api/v1/dispositions",
        "/api/v1/buyers",
    ):
        response = client.get(path, headers=assistant_headers)
        assert response.status_code == 200, f"{path}: {response.text}"

    dashboard = client.get("/api/v1/dashboard/summary", headers=assistant_headers)
    assert dashboard.status_code == 200, dashboard.text
    assert dashboard.json()["source_performance"] == []
    assert dashboard.json()["collected_revenue_cents"] == 0

    for path in ("/api/v1/finance", "/api/v1/marketing"):
        response = client.get(path, headers=assistant_headers)
        assert response.status_code == 403, f"{path}: {response.text}"

    user_admin = client.post(
        "/api/v1/operations/users",
        headers=assistant_headers,
        json={
            "email": "unauthorized@example.com",
            "display_name": "Unauthorized",
            "role_key": "operations_assistant",
        },
    )
    assert user_admin.status_code == 403, user_admin.text

    archive = client.delete(f"/api/v1/leads/{lead['id']}", headers=assistant_headers)
    assert archive.status_code == 403, archive.text


def test_phase_two_acquisition_workflow(
    db_session: Session,
    api_db_override: None,
) -> None:
    seed_owner(db_session)
    client = TestClient(app)
    owner_headers = {"X-Dev-User-Email": OWNER_EMAIL}
    va_headers = {"X-Dev-User-Email": VA_EMAIL}

    va = create_user(client, owner_headers, VA_EMAIL, "prospecting_caller")
    acquisitions = create_user(client, owner_headers, ACQUISITIONS_EMAIL, "acquisition_rep")
    team_response = client.post(
        "/api/v1/operations/teams",
        headers=owner_headers,
        json={
            "name": "Georgia Prospecting",
            "team_type": "prospecting",
            "manager_user_id": acquisitions["id"],
        },
    )
    assert team_response.status_code == 201, team_response.text
    team_id = team_response.json()["id"]
    member_response = client.post(
        f"/api/v1/operations/teams/{team_id}/members",
        headers=owner_headers,
        json={"user_id": va["id"], "membership_role": "member"},
    )
    assert member_response.status_code == 200, member_response.text

    assigned_lead = create_lead(client, owner_headers, "101 Assigned Ave")
    private_lead = create_lead(client, owner_headers, "202 Management Ave")
    list_response = client.post(
        "/api/v1/operations/calling-lists",
        headers=owner_headers,
        json={
            "name": "July Atlanta Outreach",
            "description": "Phase 2 validation list",
            "default_assignee_user_id": va["id"],
        },
    )
    assert list_response.status_code == 201, list_response.text
    calling_list_id = list_response.json()["id"]
    add_response = client.post(
        f"/api/v1/operations/calling-lists/{calling_list_id}/leads",
        headers=owner_headers,
        json={"lead_ids": [assigned_lead["id"]]},
    )
    assert add_response.status_code == 200, add_response.text
    entry = add_response.json()["entries"][0]

    va_overview = client.get("/api/v1/operations", headers=va_headers)
    assert va_overview.status_code == 200, va_overview.text
    va_payload = va_overview.json()
    assert va_payload["can_manage"] is False
    assert [item["lead_id"] for item in va_payload["calling_lists"][0]["entries"]] == [
        assigned_lead["id"]
    ]
    assert private_lead["id"] not in str(va_payload)

    handoff_response = client.patch(
        f"/api/v1/operations/calling-list-entries/{entry['id']}",
        headers=va_headers,
        json={
            "status": "completed",
            "disposition": "interested",
            "notes": "Seller wants an appointment this week.",
            "handoff_user_id": acquisitions["id"],
        },
    )
    assert handoff_response.status_code == 200, handoff_response.text
    db_session.expire_all()
    lead = db_session.get(Lead, UUID(assigned_lead["id"]))
    assert lead is not None
    assert str(lead.assigned_user_id) == acquisitions["id"]
    acquisitions_overview = client.get(
        "/api/v1/operations",
        headers={"X-Dev-User-Email": ACQUISITIONS_EMAIL},
    )
    assert acquisitions_overview.status_code == 200, acquisitions_overview.text
    assert acquisitions_overview.json()["can_manage"] is False
    assert (
        db_session.scalar(
            select(func.count())
            .select_from(Notification)
            .where(Notification.recipient_user_id == UUID(acquisitions["id"]))
        )
        == 1
    )

    start = datetime.now(UTC) + timedelta(days=2)
    appointment_response = client.post(
        f"/api/v1/leads/{assigned_lead['id']}/appointments",
        headers=owner_headers,
        json={
            "appointment_type": "walkthrough",
            "status": "scheduled",
            "scheduled_start_at": start.isoformat(),
            "scheduled_end_at": (start + timedelta(hours=1)).isoformat(),
            "location_type": "property",
            "location": "101 Assigned Ave, Atlanta, GA 30303",
        },
    )
    assert appointment_response.status_code == 201, appointment_response.text
    appointment_id = appointment_response.json()["appointments"][0]["id"]
    outcome_response = client.patch(
        f"/api/v1/leads/{assigned_lead['id']}/appointments/{appointment_id}",
        headers=owner_headers,
        json={
            "status": "completed",
            "outcome": "Walkthrough completed; prepare an offer.",
            "reason": "Appointment outcome recorded after the property visit.",
        },
    )
    assert outcome_response.status_code == 200, outcome_response.text
    assert outcome_response.json()["stage_key"] == "underwriting"
    assert outcome_response.json()["appointment_status"] == "completed"
    calendar_event = db_session.scalar(
        select(CalendarEvent).where(CalendarEvent.appointment_id == UUID(appointment_id))
    )
    assert calendar_event is not None
    assert calendar_event.provider == "internal"
    assert calendar_event.status == "completed"

    plan_response = client.post(
        "/api/v1/operations/follow-up-plans",
        headers=owner_headers,
        json={
            "name": "Seller Decision Follow-Up",
            "steps": [
                {"delay_days": 1, "action_type": "call", "title": "Call seller"},
                {
                    "delay_days": 2,
                    "action_type": "sms",
                    "title": "Seller check-in",
                    "body": "Checking in about the property and your preferred timing.",
                },
            ],
        },
    )
    assert plan_response.status_code == 201, plan_response.text
    enroll_response = client.post(
        f"/api/v1/operations/follow-up-plans/{plan_response.json()['id']}/enroll",
        headers=owner_headers,
        json={"lead_id": assigned_lead["id"]},
    )
    assert enroll_response.status_code == 200, enroll_response.text
    assert int(db_session.scalar(select(func.count()).select_from(Task)) or 0) >= 1
    approval = db_session.scalar(
        select(ApprovalRequest).where(ApprovalRequest.request_type == "follow_up_sms")
    )
    assert approval is not None
    assert approval.status == "pending"


def test_duplicate_review_archives_evidence_instead_of_deleting_it(
    db_session: Session,
    api_db_override: None,
) -> None:
    seed_owner(db_session)
    client = TestClient(app)
    headers = {"X-Dev-User-Email": OWNER_EMAIL}
    primary = create_lead(client, headers, "303 Duplicate St")
    duplicate = create_lead(client, headers, "303 Duplicate St")
    primary_lead = db_session.get(Lead, UUID(primary["id"]))
    duplicate_lead = db_session.get(Lead, UUID(duplicate["id"]))
    assert primary_lead is not None and duplicate_lead is not None
    for lead in (primary_lead, duplicate_lead):
        db_session.add(
            ContactMethod(
                organization_id=lead.organization_id,
                contact_id=lead.contact_id,
                method_type="phone",
                value="+1 404 555 0100",
                normalized_value="+14045550100",
                is_primary=True,
            )
        )
    db_session.commit()

    scan_response = client.post("/api/v1/operations/duplicates/scan", headers=headers)
    assert scan_response.status_code == 200, scan_response.text
    assert scan_response.json()["created"] == 1
    overview = client.get("/api/v1/operations", headers=headers).json()
    candidate = overview["duplicate_candidates"][0]
    merge_response = client.post(
        f"/api/v1/operations/duplicates/{candidate['id']}/resolve",
        headers=headers,
        json={"action": "merge", "notes": "Confirmed duplicate test submission."},
    )
    assert merge_response.status_code == 200, merge_response.text
    assert merge_response.json()["status"] == "merged"
    db_session.expire_all()
    archived_duplicate = db_session.get(Lead, UUID(candidate["duplicate_lead_id"]))
    assert archived_duplicate is not None
    assert archived_duplicate.archived_at is not None
    assert archived_duplicate.stage_key == "merged_duplicate"
    assert db_session.scalar(select(func.count()).select_from(LeadMergeEvent)) == 1


def test_worker_creates_reminders_for_each_upcoming_appointment(
    db_session: Session,
    api_db_override: None,
) -> None:
    seed_owner(db_session)
    client = TestClient(app)
    headers = {"X-Dev-User-Email": OWNER_EMAIL}
    start = datetime.now(UTC) + timedelta(hours=2)
    for index in range(2):
        lead = create_lead(client, headers, f"{400 + index} Reminder Ave")
        response = client.post(
            f"/api/v1/leads/{lead['id']}/appointments",
            headers=headers,
            json={
                "appointment_type": "seller_call",
                "status": "scheduled",
                "scheduled_start_at": (start + timedelta(hours=index)).isoformat(),
                "location_type": "phone",
            },
        )
        assert response.status_code == 201, response.text

    first = process_next_acquisition_reminder(db_session, get_settings())
    second = process_next_acquisition_reminder(db_session, get_settings())

    assert first is not None
    assert second is not None
    assert first != second
    assert (
        db_session.scalar(
            select(func.count())
            .select_from(Notification)
            .where(Notification.notification_type == "appointment_reminder")
        )
        == 2
    )


def test_worker_labels_a_manually_scheduled_follow_up_as_a_due_reminder(
    db_session: Session,
    api_db_override: None,
) -> None:
    seed_owner(db_session)
    client = TestClient(app)
    headers = {"X-Dev-User-Email": OWNER_EMAIL}
    lead = create_lead(client, headers, "402 Manual Reminder Ave")
    response = client.post(
        f"/api/v1/leads/{lead['id']}/tasks",
        headers=headers,
        json={
            "title": "Call the seller about the updated timeline",
            "due_at": (datetime.now(UTC) - timedelta(minutes=1)).isoformat(),
            "priority": "normal",
        },
    )
    assert response.status_code == 201, response.text

    notification_id = process_next_acquisition_reminder(db_session, get_settings())

    assert notification_id is not None
    notification = db_session.get(Notification, notification_id)
    assert notification is not None
    assert notification.title == "Reminder due"
    assert notification.body == "Call the seller about the updated timeline"


def test_manual_reminder_can_queue_one_sms_for_the_assigned_user(
    db_session: Session,
    api_db_override: None,
) -> None:
    seed_owner(db_session)
    owner = db_session.scalar(select(User).where(User.email == OWNER_EMAIL))
    assert owner is not None
    owner.voice_forwarding_number = "+16785550123"
    db_session.commit()
    client = TestClient(app)
    headers = {"X-Dev-User-Email": OWNER_EMAIL}
    lead = create_lead(client, headers, "403 Text Reminder Ave")
    response = client.post(
        f"/api/v1/leads/{lead['id']}/tasks",
        headers=headers,
        json={
            "title": "Call the seller about the six-month follow-up",
            "due_at": (datetime.now(UTC) - timedelta(minutes=1)).isoformat(),
            "priority": "normal",
            "sms_notification_enabled": True,
        },
    )
    assert response.status_code == 201, response.text
    assert response.json()["primary_next_action"]["sms_notification_enabled"] is True

    notification_id = process_next_acquisition_reminder(db_session, get_settings())

    assert notification_id is not None
    alert = db_session.scalar(
        select(StaffLeadAlert).where(StaffLeadAlert.source_type == "task_reminder")
    )
    assert alert is not None
    assert alert.recipient_user_id == owner.id
    assert alert.recipient_phone == "+16785550123"
    assert alert.status == "pending"
    assert "six-month follow-up" in alert.message_body
    assert process_next_acquisition_reminder(db_session, get_settings()) is None

    delivered_id = process_next_staff_lead_alert(
        db_session,
        get_settings().model_copy(update={"staff_lead_alert_sms_mode": "simulate"}),
    )
    assert delivered_id == alert.id
    db_session.refresh(alert)
    assert alert.status == "simulated"


def test_manual_sms_reminder_requires_an_assigned_user_cellphone(
    db_session: Session,
    api_db_override: None,
) -> None:
    seed_owner(db_session)
    client = TestClient(app)
    headers = {"X-Dev-User-Email": OWNER_EMAIL}
    lead = create_lead(client, headers, "404 Missing Cellphone Ave")

    response = client.post(
        f"/api/v1/leads/{lead['id']}/tasks",
        headers=headers,
        json={
            "title": "Call the seller later",
            "due_at": (datetime.now(UTC) + timedelta(days=1)).isoformat(),
            "priority": "normal",
            "sms_notification_enabled": True,
        },
    )

    assert response.status_code == 422, response.text
    assert "valid cellphone" in response.json()["detail"]
