from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.main import app
from app.models.foundation import (
    Appointment,
    AppointmentDispatchRecord,
    AuditEvent,
    CalendarEvent,
    Contact,
    Lead,
    LeadManagementCase,
    Property,
    User,
)
from app.schemas.lead_manager import QualificationCompleteRequest
from app.services.bootstrap import bootstrap_foundation
from app.services.lead_manager import apply_next_action

OWNER_EMAIL = "owner@example.com"


def create_ready_lead(db: Session, *, seller: str, street: str) -> Lead:
    owner = db.scalar(select(User).where(User.email == OWNER_EMAIL))
    assert owner is not None
    contact = Contact(
        organization_id=owner.organization_id,
        legal_name=seller,
        preferred_name=None,
        contact_type="seller",
        assigned_user_id=owner.id,
    )
    property_record = Property(
        organization_id=owner.organization_id,
        street_address=street,
        city="Atlanta",
        state="GA",
        postal_code="30303",
        county="Fulton",
        property_type="single_family",
        normalized_address_key=f"{street.lower()}|atlanta|GA|30303",
        address_validation_status="unverified",
    )
    db.add_all([contact, property_record])
    db.flush()
    lead = Lead(
        organization_id=owner.organization_id,
        contact_id=contact.id,
        property_id=property_record.id,
        assigned_user_id=owner.id,
        source="test",
        stage_key="qualified",
        lead_temperature="warm",
    )
    db.add(lead)
    db.commit()
    return lead


def test_dispatch_evaluates_capacity_and_audits_manager_override(
    db_session: Session,
    api_db_override: None,
) -> None:
    bootstrap_foundation(
        db_session,
        organization_name="Stonegate Home Buyers",
        admin_email=OWNER_EMAIL,
        admin_name="Owner",
    )
    client = TestClient(app)
    headers = {"X-Dev-User-Email": OWNER_EMAIL}
    owner = db_session.scalar(select(User).where(User.email == OWNER_EMAIL))
    assert owner is not None
    first_lead = create_ready_lead(db_session, seller="Sam Seller", street="101 Main St")
    second_lead = create_ready_lead(db_session, seller="Taylor Seller", street="102 Main St")

    market = client.post(
        "/api/v1/operations/markets",
        headers=headers,
        json={
            "name": "Atlanta Metro",
            "code": "atlanta-metro",
            "state_code": "GA",
            "timezone": "America/New_York",
            "is_primary": True,
        },
    )
    assert market.status_code == 201, market.text
    territory = client.post(
        "/api/v1/operations/territories",
        headers=headers,
        json={
            "market_id": market.json()["id"],
            "name": "Central Atlanta",
            "code": "central-atlanta",
            "county_names": ["Fulton"],
            "postal_codes": ["30303"],
        },
    )
    assert territory.status_code == 201, territory.text
    configured = client.put(
        f"/api/v1/field-operations/profiles/{owner.id}",
        headers=headers,
        json={
            "timezone": "America/New_York",
            "working_days": [0, 1, 2, 3, 4, 5, 6],
            "workday_start_minute": 0,
            "workday_end_minute": 1440,
            "daily_capacity": 1,
            "default_appointment_minutes": 90,
            "travel_buffer_minutes": 30,
            "territory_enforcement_enabled": True,
            "is_active": True,
            "territory_ids": [territory.json()["id"]],
        },
    )
    assert configured.status_code == 200, configured.text

    start = (datetime.now(UTC) + timedelta(days=3)).replace(
        hour=15, minute=0, second=0, microsecond=0
    )
    end = start + timedelta(minutes=90)
    evaluation = client.post(
        "/api/v1/field-operations/evaluate",
        headers=headers,
        json={
            "lead_id": str(first_lead.id),
            "scheduled_start_at": start.isoformat(),
            "scheduled_end_at": end.isoformat(),
        },
    )
    assert evaluation.status_code == 200, evaluation.text
    assert evaluation.json()["territory_name"] == "Central Atlanta"
    assert evaluation.json()["candidates"][0]["eligible"] is True

    dispatched = client.post(
        "/api/v1/field-operations/dispatch",
        headers=headers,
        json={
            "lead_id": str(first_lead.id),
            "closer_user_id": str(owner.id),
            "scheduled_start_at": start.isoformat(),
            "scheduled_end_at": end.isoformat(),
            "notes": "Seller confirmed access.",
        },
    )
    assert dispatched.status_code == 201, dispatched.text
    assert dispatched.json()["decision_status"] == "scheduled"
    assert int(db_session.scalar(select(func.count()).select_from(Appointment)) or 0) == 1
    assert int(db_session.scalar(select(func.count()).select_from(CalendarEvent)) or 0) == 1
    db_session.refresh(first_lead)
    assert first_lead.stage_key == "appointment_scheduled"

    second_start = start + timedelta(hours=4)
    second_end = second_start + timedelta(minutes=90)
    second_evaluation = client.post(
        "/api/v1/field-operations/evaluate",
        headers=headers,
        json={
            "lead_id": str(second_lead.id),
            "scheduled_start_at": second_start.isoformat(),
            "scheduled_end_at": second_end.isoformat(),
        },
    )
    candidate = second_evaluation.json()["candidates"][0]
    assert candidate["eligible"] is False
    assert candidate["violations"] == ["daily_capacity_reached"]

    rejected = client.post(
        "/api/v1/field-operations/dispatch",
        headers=headers,
        json={
            "lead_id": str(second_lead.id),
            "closer_user_id": str(owner.id),
            "scheduled_start_at": second_start.isoformat(),
            "scheduled_end_at": second_end.isoformat(),
        },
    )
    assert rejected.status_code == 422
    overridden = client.post(
        "/api/v1/field-operations/dispatch",
        headers=headers,
        json={
            "lead_id": str(second_lead.id),
            "closer_user_id": str(owner.id),
            "scheduled_start_at": second_start.isoformat(),
            "scheduled_end_at": second_end.isoformat(),
            "override_conflicts": True,
            "override_reason": "Owner approved a fifth-hour appointment for this seller.",
        },
    )
    assert overridden.status_code == 201, overridden.text
    assert overridden.json()["decision_status"] == "override"
    assert overridden.json()["violations"] == ["daily_capacity_reached"]
    dispatch_records = db_session.scalars(select(AppointmentDispatchRecord)).all()
    assert len(dispatch_records) == 2
    assert dispatch_records[-1].decision_reason is not None
    audit_events = db_session.scalars(
        select(AuditEvent).where(AuditEvent.action == "field_operations.appointment_dispatch")
    ).all()
    assert len(audit_events) == 2


def test_closer_block_prevents_dispatch_without_override(
    db_session: Session,
    api_db_override: None,
) -> None:
    bootstrap_foundation(
        db_session,
        organization_name="Stonegate Home Buyers",
        admin_email=OWNER_EMAIL,
        admin_name="Owner",
    )
    client = TestClient(app)
    headers = {"X-Dev-User-Email": OWNER_EMAIL}
    owner = db_session.scalar(select(User).where(User.email == OWNER_EMAIL))
    assert owner is not None
    lead = create_ready_lead(db_session, seller="Blocked Seller", street="201 Main St")
    configured = client.put(
        f"/api/v1/field-operations/profiles/{owner.id}",
        headers=headers,
        json={
            "working_days": [0, 1, 2, 3, 4, 5, 6],
            "workday_start_minute": 0,
            "workday_end_minute": 1440,
            "daily_capacity": 4,
            "territory_enforcement_enabled": False,
        },
    )
    assert configured.status_code == 200, configured.text
    start = (datetime.now(UTC) + timedelta(days=2)).replace(
        hour=15, minute=0, second=0, microsecond=0
    )
    end = start + timedelta(minutes=90)
    blocked = client.post(
        f"/api/v1/field-operations/profiles/{configured.json()['id']}/blocks",
        headers=headers,
        json={
            "block_type": "personal",
            "starts_at": start.isoformat(),
            "ends_at": end.isoformat(),
            "reason": "Personal appointment",
        },
    )
    assert blocked.status_code == 201, blocked.text
    evaluation = client.post(
        "/api/v1/field-operations/evaluate",
        headers=headers,
        json={
            "lead_id": str(lead.id),
            "scheduled_start_at": start.isoformat(),
            "scheduled_end_at": end.isoformat(),
        },
    )
    assert evaluation.status_code == 200, evaluation.text
    assert evaluation.json()["candidates"][0]["violations"] == ["availability_block"]


def test_lead_manager_routes_new_field_appointment_to_dispatch_queue(
    db_session: Session,
) -> None:
    bootstrap_foundation(
        db_session,
        organization_name="Stonegate Home Buyers",
        admin_email=OWNER_EMAIL,
        admin_name="Owner",
    )
    lead = create_ready_lead(db_session, seller="Ready Seller", street="301 Main St")
    owner = db_session.scalar(select(User).where(User.email == OWNER_EMAIL))
    assert owner is not None
    now = datetime.now(UTC)
    case = LeadManagementCase(
        organization_id=owner.organization_id,
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
        next_action_type=None,
        next_action_due_at=None,
        last_contact_at=now,
        closed_at=None,
    )
    db_session.add(case)
    db_session.flush()
    requested_time = now + timedelta(days=2)

    apply_next_action(
        db_session,
        case,
        lead,
        QualificationCompleteRequest(
            answers={},
            next_action_type="appointment",
            next_action_due_at=requested_time,
        ),
        now,
    )
    db_session.commit()

    assert case.status == "appointment_ready"
    assert lead.stage_key == "appointment_scheduling"
    assert lead.appointment_status == "needs_scheduling"
    assert lead.next_follow_up_at == requested_time.replace(tzinfo=None)
    assert int(db_session.scalar(select(func.count()).select_from(Appointment)) or 0) == 0
