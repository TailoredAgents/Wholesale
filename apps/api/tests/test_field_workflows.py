from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.main import app
from app.models.foundation import (
    Appointment,
    ApprovalRequest,
    Contact,
    Lead,
    OfferNegotiationPlan,
    Property,
    RepairEstimate,
    Role,
    RoleAssignment,
    UnderwritingVersion,
    User,
)
from app.services.bootstrap import bootstrap_foundation

OWNER_EMAIL = "field-owner@example.com"


def field_appointment(db: Session) -> tuple[User, Lead, Appointment, UnderwritingVersion]:
    owner = db.scalar(select(User).where(User.email == OWNER_EMAIL))
    assert owner is not None
    contact = Contact(
        organization_id=owner.organization_id,
        legal_name="Jordan Seller",
        preferred_name="Jordan",
        contact_type="seller",
        assigned_user_id=owner.id,
    )
    property_record = Property(
        organization_id=owner.organization_id,
        street_address="125 Fieldstone Drive",
        city="Atlanta",
        state="GA",
        postal_code="30303",
        county="Fulton",
        property_type="single_family",
        normalized_address_key="125 fieldstone drive|atlanta|ga|30303",
        address_validation_status="provider_confirmed",
    )
    db.add_all([contact, property_record])
    db.flush()
    lead = Lead(
        organization_id=owner.organization_id,
        contact_id=contact.id,
        property_id=property_record.id,
        assigned_user_id=owner.id,
        source="test",
        stage_key="appointment_scheduled",
        lead_temperature="warm",
        motivation="Inherited property",
        desired_timeline="Within 30 days",
        property_condition="Needs renovation",
        occupancy_status="Vacant",
        asking_price="225000",
    )
    db.add(lead)
    db.flush()
    start = datetime.now(UTC) + timedelta(days=2)
    appointment = Appointment(
        organization_id=owner.organization_id,
        lead_id=lead.id,
        contact_id=contact.id,
        property_id=property_record.id,
        owner_user_id=owner.id,
        appointment_type="seller_appointment",
        status="scheduled",
        scheduled_start_at=start,
        scheduled_end_at=start + timedelta(minutes=90),
        location_type="property",
        location="125 Fieldstone Drive, Atlanta, GA 30303",
        notes="Seller confirmed access.",
        outcome=None,
        external_calendar_id=None,
        appointment_metadata={"source": "test"},
    )
    underwriting = UnderwritingVersion(
        organization_id=owner.organization_id,
        lead_id=lead.id,
        property_id=property_record.id,
        created_by_user_id=owner.id,
        version_number=1,
        status="approved",
        arv_low_cents=30_000_000,
        arv_high_cents=32_000_000,
        repair_low_cents=4_000_000,
        repair_high_cents=5_000_000,
        max_offer_cents=18_000_000,
        recommended_offer_cents=17_500_000,
        offer_strategy="cash",
        notes="Initial desktop analysis.",
        source="manual",
        underwriting_metadata={"report_stage": "desktop"},
    )
    db.add_all([appointment, underwriting])
    db.flush()
    approval = ApprovalRequest(
        organization_id=owner.organization_id,
        requested_by_user_id=owner.id,
        assigned_to_user_id=owner.id,
        decided_by_user_id=owner.id,
        request_type="seller_offer",
        entity_type="offer_negotiation_plan",
        entity_id=None,
        status="approved",
        title="Approve seller offer",
        summary="Approved field negotiation range.",
        decision_notes="Do not exceed the seller ceiling.",
        due_at=None,
        decided_at=datetime.now(UTC),
        approval_metadata={},
    )
    db.add(approval)
    db.flush()
    plan = OfferNegotiationPlan(
        organization_id=owner.organization_id,
        lead_id=lead.id,
        property_id=property_record.id,
        underwriting_version_id=underwriting.id,
        market_analysis_id=None,
        approval_request_id=approval.id,
        created_by_user_id=owner.id,
        status="approved",
        seller_asking_price_cents=22_500_000,
        arv_low_cents=30_000_000,
        arv_point_cents=31_000_000,
        arv_high_cents=32_000_000,
        total_rehab_cents=5_000_000,
        disposition_cents=19_000_000,
        opening_offer_cents=16_000_000,
        target_contract_cents=17_000_000,
        stretch_contract_cents=17_500_000,
        seller_ceiling_cents=18_000_000,
        seller_context="Inherited vacant property.",
        rationale="Preserves the approved deal margin.",
        source_snapshot={"underwriting_version": 1},
    )
    db.add(plan)
    db.flush()
    approval.entity_id = plan.id
    db.commit()
    return owner, lead, appointment, underwriting


def test_field_meeting_evidence_and_underwriting_transfer(
    db_session: Session,
    api_db_override: None,
) -> None:
    bootstrap_foundation(
        db_session,
        organization_name="Stonegate Home Buyers",
        admin_email=OWNER_EMAIL,
        admin_name="Owner",
    )
    owner, lead, appointment, original_underwriting = field_appointment(db_session)
    client = TestClient(app)
    headers = {"X-Dev-User-Email": OWNER_EMAIL}

    calendar = client.get(
        "/api/v1/field-operations/calendar",
        headers=headers,
        params={
            "starts_at": (appointment.scheduled_start_at - timedelta(days=1)).isoformat(),
            "ends_at": (appointment.scheduled_start_at + timedelta(days=1)).isoformat(),
        },
    )
    assert calendar.status_code == 200, calendar.text
    assert calendar.json()["appointments"][0]["id"] == str(appointment.id)

    brief = client.post(
        f"/api/v1/field-operations/appointments/{appointment.id}/brief",
        headers=headers,
    )
    assert brief.status_code == 200, brief.text
    assert brief.json()["brief_data"]["approved_offer"]["seller_ceiling_cents"] == 18_000_000

    started = client.post(
        f"/api/v1/field-operations/appointments/{appointment.id}/inspection",
        headers=headers,
    )
    assert started.status_code == 201, started.text
    inspection_id = started.json()["id"]
    saved = client.patch(
        f"/api/v1/field-operations/inspections/{inspection_id}",
        headers=headers,
        json={
            "overall_condition": "heavy",
            "occupancy_observed": "Vacant",
            "utilities_status": "Water and power off",
            "room_observations": [
                {"area": "Kitchen", "condition": "poor", "notes": "Full replacement"}
            ],
            "repair_items": [
                {
                    "category": "kitchen",
                    "estimated_cost_cents": 2_000_000,
                    "details": "Cabinets, counters, and appliances",
                }
            ],
            "inspector_notes": "Scope verified during seller walkthrough.",
        },
    )
    assert saved.status_code == 200, saved.text
    partial = client.patch(
        f"/api/v1/field-operations/inspections/{inspection_id}",
        headers=headers,
        json={"access_notes": "Lockbox at the rear door"},
    )
    assert partial.status_code == 200, partial.text
    assert partial.json()["room_observations"][0]["area"] == "Kitchen"
    assert partial.json()["repair_items"][0]["estimated_cost_cents"] == 2_000_000
    photo = client.post(
        f"/api/v1/field-operations/inspections/{inspection_id}/photos",
        headers={**headers, "Content-Type": "image/jpeg"},
        params={"area": "Kitchen", "file_name": "kitchen.jpg"},
        content=b"test-jpeg-evidence",
    )
    assert photo.status_code == 201, photo.text
    photo_content = client.get(photo.json()["content_url"], headers=headers)
    assert photo_content.status_code == 200
    assert photo_content.content == b"test-jpeg-evidence"

    submitted = client.post(
        f"/api/v1/field-operations/inspections/{inspection_id}/submit",
        headers=headers,
    )
    assert submitted.status_code == 200, submitted.text
    immutable = client.patch(
        f"/api/v1/field-operations/inspections/{inspection_id}",
        headers=headers,
        json={"overall_condition": "light"},
    )
    assert immutable.status_code == 422

    over_ceiling = client.put(
        f"/api/v1/field-operations/appointments/{appointment.id}/negotiation",
        headers=headers,
        json={"offer_presented_cents": 18_000_001, "outcome": "pending"},
    )
    assert over_ceiling.status_code == 422
    accepted = client.put(
        f"/api/v1/field-operations/appointments/{appointment.id}/negotiation",
        headers=headers,
        json={
            "decision_makers_confirmed": True,
            "decision_makers": ["Jordan Seller"],
            "offer_presented_cents": 17_000_000,
            "agreed_price_cents": 17_500_000,
            "commitments": ["Send title information tomorrow"],
            "outcome": "accepted",
        },
    )
    assert accepted.status_code == 200, accepted.text
    assert accepted.json()["approved_ceiling_cents"] == 18_000_000

    transfer = client.post(
        f"/api/v1/field-operations/inspections/{inspection_id}/underwriting-transfer",
        headers=headers,
    )
    assert transfer.status_code == 200, transfer.text
    assert transfer.json()["created_underwriting_version_number"] == 2
    db_session.expire_all()
    original = db_session.get(UnderwritingVersion, original_underwriting.id)
    assert original is not None
    assert original.status == "approved"
    assert original.max_offer_cents == 18_000_000
    new_version = db_session.scalar(
        select(UnderwritingVersion).where(
            UnderwritingVersion.lead_id == lead.id,
            UnderwritingVersion.version_number == 2,
        )
    )
    assert new_version is not None
    assert new_version.status == "draft"
    assert new_version.repair_low_cents == 2_000_000
    assert new_version.repair_high_cents == 2_300_000
    assert new_version.max_offer_cents is None
    repair = db_session.scalar(select(RepairEstimate).where(RepairEstimate.lead_id == lead.id))
    assert repair is not None
    assert repair.total_cents == 2_300_000


def test_prospecting_caller_cannot_access_field_operations(
    db_session: Session,
    api_db_override: None,
) -> None:
    bootstrap_foundation(
        db_session,
        organization_name="Stonegate Home Buyers",
        admin_email=OWNER_EMAIL,
        admin_name="Owner",
    )
    owner = db_session.scalar(select(User).where(User.email == OWNER_EMAIL))
    role = db_session.scalar(select(Role).where(Role.key == "prospecting_caller"))
    assert owner is not None and role is not None
    caller = User(
        organization_id=owner.organization_id,
        email="caller@example.com",
        display_name="VA Caller",
        external_auth_id=None,
        is_active=True,
    )
    db_session.add(caller)
    db_session.flush()
    db_session.add(
        RoleAssignment(
            organization_id=owner.organization_id,
            user_id=caller.id,
            role_id=role.id,
        )
    )
    db_session.commit()

    response = TestClient(app).get(
        "/api/v1/field-operations",
        headers={"X-Dev-User-Email": caller.email},
    )
    assert response.status_code == 403
