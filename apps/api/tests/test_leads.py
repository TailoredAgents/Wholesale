from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.integrations.rentcast_client import RentCastRentEstimate, RentCastValueEstimate
from app.main import app
from app.models.foundation import (
    ActivityEvent,
    Appointment,
    AuditEvent,
    BuyerOffer,
    CommunicationRecord,
    Contact,
    Deal,
    Lead,
    Property,
    Task,
    Transaction,
    TransactionChecklistItem,
    UnderwritingMarketAnalysis,
    UnderwritingVersion,
)
from app.services.bootstrap import bootstrap_foundation

OWNER_EMAIL = "owner@example.com"


def seed_owner(db_session: Session) -> None:
    bootstrap_foundation(
        db_session,
        organization_name="Stonegate Home Buyers",
        admin_email=OWNER_EMAIL,
        admin_name="Owner",
    )


def lead_payload() -> dict[str, object]:
    return {
        "contact": {
            "legal_name": "Jane Seller",
            "preferred_name": "Jane",
            "contact_type": "seller",
        },
        "property": {
            "street_address": "123 Peachtree St",
            "city": "Atlanta",
            "state": "ga",
            "postal_code": "30303",
            "county": "Fulton",
            "property_type": "single_family",
        },
        "source": "google_ppc",
        "stage_key": "new",
        "lead_temperature": "hot",
        "motivation": "Seller wants a fast close.",
        "desired_timeline": "30_days",
        "property_condition": "needs_repairs",
        "occupancy_status": "vacant",
        "asking_price": "185000",
        "mortgage_balance": "90000",
        "appointment_status": "not_scheduled",
    }


def test_create_and_list_lead(
    db_session: Session,
    api_db_override: None,
) -> None:
    seed_owner(db_session)
    client = TestClient(app)

    create_response = client.post(
        "/api/v1/leads",
        headers={"X-Dev-User-Email": OWNER_EMAIL},
        json=lead_payload(),
    )

    assert create_response.status_code == 201
    created = create_response.json()
    assert created["seller_name"] == "Jane Seller"
    assert created["property_address"] == "123 Peachtree St, Atlanta, GA 30303"
    assert created["property_state"] == "GA"
    assert created["property_county"] == "Fulton"
    assert created["source"] == "google_ppc"
    assert created["motivation"] == "Seller wants a fast close."
    assert created["desired_timeline"] == "30_days"
    assert created["property_condition"] == "needs_repairs"
    assert created["occupancy_status"] == "vacant"
    assert created["asking_price"] == "185000"
    assert created["mortgage_balance"] == "90000"
    assert created["appointment_status"] == "not_scheduled"

    list_response = client.get("/api/v1/leads", headers={"X-Dev-User-Email": OWNER_EMAIL})

    assert list_response.status_code == 200
    items = list_response.json()["items"]
    assert len(items) == 1
    assert items[0]["id"] == created["id"]
    assert int(db_session.scalar(select(func.count()).select_from(ActivityEvent)) or 0) == 1
    assert int(
        db_session.scalar(
            select(func.count()).select_from(AuditEvent).where(AuditEvent.action == "lead.create")
        )
        or 0
    ) == 1


def test_archive_restore_and_permanently_delete_lead(
    db_session: Session,
    api_db_override: None,
) -> None:
    seed_owner(db_session)
    client = TestClient(app)
    created = client.post(
        "/api/v1/leads",
        headers={"X-Dev-User-Email": OWNER_EMAIL},
        json=lead_payload(),
    ).json()
    lead_id = created["id"]
    client.post(
        f"/api/v1/leads/{lead_id}/tasks",
        headers={"X-Dev-User-Email": OWNER_EMAIL},
        json={"title": "Call test seller", "priority": "normal"},
    )

    archive_response = client.delete(
        f"/api/v1/leads/{lead_id}",
        headers={"X-Dev-User-Email": OWNER_EMAIL},
    )
    assert archive_response.status_code == 200
    assert archive_response.json()["archived_at"] is not None
    assert client.get(
        "/api/v1/leads", headers={"X-Dev-User-Email": OWNER_EMAIL}
    ).json()["items"] == []
    archived_items = client.get(
        "/api/v1/leads?archived=true",
        headers={"X-Dev-User-Email": OWNER_EMAIL},
    ).json()["items"]
    assert [item["id"] for item in archived_items] == [lead_id]
    assert client.get(
        "/api/v1/tasks/open", headers={"X-Dev-User-Email": OWNER_EMAIL}
    ).json()["items"] == []

    restore_response = client.post(
        f"/api/v1/leads/{lead_id}/restore",
        headers={"X-Dev-User-Email": OWNER_EMAIL},
    )
    assert restore_response.status_code == 200
    assert restore_response.json()["archived_at"] is None

    unarchived_delete_response = client.delete(
        f"/api/v1/leads/{lead_id}/permanent?confirmation=DELETE",
        headers={"X-Dev-User-Email": OWNER_EMAIL},
    )
    assert unarchived_delete_response.status_code == 422

    client.delete(
        f"/api/v1/leads/{lead_id}",
        headers={"X-Dev-User-Email": OWNER_EMAIL},
    )
    missing_confirmation_response = client.delete(
        f"/api/v1/leads/{lead_id}/permanent",
        headers={"X-Dev-User-Email": OWNER_EMAIL},
    )
    assert missing_confirmation_response.status_code == 422

    delete_response = client.delete(
        f"/api/v1/leads/{lead_id}/permanent?confirmation=DELETE",
        headers={"X-Dev-User-Email": OWNER_EMAIL},
    )
    assert delete_response.status_code == 204
    assert int(db_session.scalar(select(func.count()).select_from(Lead)) or 0) == 0
    assert int(db_session.scalar(select(func.count()).select_from(Contact)) or 0) == 0
    assert int(db_session.scalar(select(func.count()).select_from(Property)) or 0) == 0
    task = db_session.scalar(select(Task))
    assert task is not None
    assert task.lead_id is None
    assert int(
        db_session.scalar(
            select(func.count()).select_from(AuditEvent).where(
                AuditEvent.action == "lead.delete_permanently"
            )
        )
        or 0
    ) == 1


def test_dashboard_summary_counts_leads(
    db_session: Session,
    api_db_override: None,
) -> None:
    seed_owner(db_session)
    client = TestClient(app)
    client.post("/api/v1/leads", headers={"X-Dev-User-Email": OWNER_EMAIL}, json=lead_payload())

    response = client.get(
        "/api/v1/dashboard/summary",
        headers={"X-Dev-User-Email": OWNER_EMAIL},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["total_leads"] == 1
    assert payload["new_paid_leads"] == 1
    assert payload["offers_pending"] == 0
    assert payload["active_contracts"] == 0
    assert payload["pipeline"] == [{"stage_key": "new", "count": 1}]
    assert payload["source_performance"] == [
        {
            "source": "google_ppc",
            "medium": "unknown",
            "campaign": "uncategorized",
            "page_views": 0,
            "form_starts": 0,
            "form_abandons": 0,
            "form_submits": 0,
            "call_clicks": 0,
            "leads_created": 1,
        }
    ]


def test_read_lead_detail_and_update_stage(
    db_session: Session,
    api_db_override: None,
) -> None:
    seed_owner(db_session)
    client = TestClient(app)
    created_response = client.post(
        "/api/v1/leads",
        headers={"X-Dev-User-Email": OWNER_EMAIL},
        json=lead_payload(),
    )
    lead_id = created_response.json()["id"]

    detail_response = client.get(
        f"/api/v1/leads/{lead_id}",
        headers={"X-Dev-User-Email": OWNER_EMAIL},
    )

    assert detail_response.status_code == 200
    detail = detail_response.json()
    assert detail["id"] == lead_id
    assert detail["seller_name"] == "Jane Seller"
    assert detail["open_tasks"] == []
    assert detail["communications"] == []
    assert detail["appointments"] == []
    assert detail["underwriting_versions"] == []
    assert detail["transactions"] == []
    assert detail["buyer_offers"] == []
    assert detail["recent_activity"][0]["event_type"] == "lead.created"
    assert detail["intelligence"]["quality_score"] == 85
    assert detail["intelligence"]["urgency_score"] == 88
    assert detail["intelligence"]["priority_label"] == "critical"
    assert detail["intelligence"]["next_best_action"]["action_type"] == "ask_missing_question"
    assert detail["intelligence"]["missing_fields"] == [
        {
            "field_key": "contact_method",
            "label": "Contact method",
            "question": "What is the best phone number or email for seller follow-up?",
            "severity": "high",
        }
    ]
    assert detail["intelligence"]["ai_ready_summary"]["known_facts"][:2] == [
        "Stage: new.",
        "Source: google_ppc.",
    ]

    update_response = client.patch(
        f"/api/v1/leads/{lead_id}/stage",
        headers={"X-Dev-User-Email": OWNER_EMAIL},
        json={"stage_key": "contacted", "reason": "Reached seller by phone."},
    )

    assert update_response.status_code == 200
    updated = update_response.json()
    assert updated["stage_key"] == "contacted"
    assert updated["intelligence"]["urgency_score"] == 76
    assert "lead.stage_changed" in [
        activity["event_type"] for activity in updated["recent_activity"]
    ]
    assert int(
        db_session.scalar(
            select(func.count()).select_from(AuditEvent).where(
                AuditEvent.action == "lead.stage_update"
            )
        )
        or 0
    ) == 1


def test_update_lead_stage_rejects_unknown_stage(
    db_session: Session,
    api_db_override: None,
) -> None:
    seed_owner(db_session)
    client = TestClient(app)
    created_response = client.post(
        "/api/v1/leads",
        headers={"X-Dev-User-Email": OWNER_EMAIL},
        json=lead_payload(),
    )
    lead_id = created_response.json()["id"]

    response = client.patch(
        f"/api/v1/leads/{lead_id}/stage",
        headers={"X-Dev-User-Email": OWNER_EMAIL},
        json={"stage_key": "not_a_real_stage"},
    )

    assert response.status_code == 422


def test_update_lead_staff_details_records_audit(
    db_session: Session,
    api_db_override: None,
) -> None:
    seed_owner(db_session)
    client = TestClient(app)
    created_response = client.post(
        "/api/v1/leads",
        headers={"X-Dev-User-Email": OWNER_EMAIL},
        json=lead_payload(),
    )
    lead_id = created_response.json()["id"]

    response = client.patch(
        f"/api/v1/leads/{lead_id}",
        headers={"X-Dev-User-Email": OWNER_EMAIL},
        json={
            "seller_name": "Janet Seller",
            "preferred_name": "Janet",
            "phone": "(404) 555-0101",
            "email": "JANET@example.com",
            "property_street_address": "500 Edgewood Ave",
            "property_city": "Atlanta",
            "property_state": "ga",
            "property_postal_code": "30312",
            "property_county": "Fulton",
            "property_type": "duplex",
            "source": "referral",
            "lead_temperature": "warm",
            "motivation": "Needs certainty before relocating.",
            "desired_timeline": "asap",
            "property_condition": "dated",
            "occupancy_status": "owner_occupied",
            "asking_price": "210000",
            "mortgage_balance": "120000",
            "appointment_status": "appointment_requested",
            "reason": "Corrected seller intake after phone call.",
        },
    )

    assert response.status_code == 200
    updated = response.json()
    assert updated["seller_name"] == "Janet Seller"
    assert updated["source"] == "referral"
    assert updated["lead_temperature"] == "warm"
    assert updated["motivation"] == "Needs certainty before relocating."
    assert updated["desired_timeline"] == "asap"
    assert updated["property_condition"] == "dated"
    assert updated["occupancy_status"] == "owner_occupied"
    assert updated["asking_price"] == "210000"
    assert updated["mortgage_balance"] == "120000"
    assert updated["appointment_status"] == "appointment_requested"
    assert updated["property_address"] == "500 Edgewood Ave, Atlanta, GA 30312"
    assert updated["property_type"] == "duplex"
    assert {
        (method["method_type"], method["value"])
        for method in updated["contact_methods"]
    } == {
        ("email", "JANET@example.com"),
        ("phone", "(404) 555-0101"),
    }
    assert "lead.staff_updated" in [
        activity["event_type"] for activity in updated["recent_activity"]
    ]
    assert int(
        db_session.scalar(
            select(func.count()).select_from(AuditEvent).where(
                AuditEvent.action == "lead.staff_update"
            )
        )
        or 0
    ) == 1


def test_add_lead_note_and_follow_up_task(
    db_session: Session,
    api_db_override: None,
) -> None:
    seed_owner(db_session)
    client = TestClient(app)
    created_response = client.post(
        "/api/v1/leads",
        headers={"X-Dev-User-Email": OWNER_EMAIL},
        json=lead_payload(),
    )
    lead_id = created_response.json()["id"]

    note_response = client.post(
        f"/api/v1/leads/{lead_id}/notes",
        headers={"X-Dev-User-Email": OWNER_EMAIL},
        json={"note": "Seller said roof is older but HVAC is newer."},
    )

    assert note_response.status_code == 201
    note_payload = note_response.json()
    assert {
        (activity["event_type"], activity["summary"])
        for activity in note_payload["recent_activity"]
    } >= {("lead.note_added", "Seller said roof is older but HVAC is newer.")}

    task_response = client.post(
        f"/api/v1/leads/{lead_id}/tasks",
        headers={"X-Dev-User-Email": OWNER_EMAIL},
        json={
            "title": "Call seller about appointment window",
            "priority": "high",
            "due_at": "2026-07-16T14:30:00Z",
        },
    )

    assert task_response.status_code == 201
    task_payload = task_response.json()
    assert task_payload["open_tasks"][0]["title"] == "Call seller about appointment window"
    assert task_payload["open_tasks"][0]["priority"] == "high"
    assert task_payload["next_follow_up_at"].startswith("2026-07-16T14:30:00")
    assert int(db_session.scalar(select(func.count()).select_from(Task)) or 0) == 1

    queue_response = client.get(
        "/api/v1/tasks/open",
        headers={"X-Dev-User-Email": OWNER_EMAIL},
    )

    assert queue_response.status_code == 200
    queue = queue_response.json()["items"]
    assert len(queue) == 1
    assert queue[0]["lead_id"] == lead_id
    assert queue[0]["task_type"] == "follow_up"
    assert queue[0]["title"] == "Call seller about appointment window"
    assert queue[0]["seller_name"] == "Jane Seller"


def test_add_lead_communication_records_audit_and_activity(
    db_session: Session,
    api_db_override: None,
) -> None:
    seed_owner(db_session)
    client = TestClient(app)
    created_response = client.post(
        "/api/v1/leads",
        headers={"X-Dev-User-Email": OWNER_EMAIL},
        json=lead_payload(),
    )
    lead_id = created_response.json()["id"]

    response = client.post(
        f"/api/v1/leads/{lead_id}/communications",
        headers={"X-Dev-User-Email": OWNER_EMAIL},
        json={
            "direction": "outbound",
            "channel": "call",
            "status": "logged",
            "subject": "First contact attempt",
            "body": "Left voicemail and will follow up by text.",
            "occurred_at": "2026-07-16T14:30:00Z",
        },
    )

    assert response.status_code == 201
    payload = response.json()
    assert payload["communications"][0]["direction"] == "outbound"
    assert payload["communications"][0]["channel"] == "call"
    assert payload["communications"][0]["status"] == "logged"
    assert payload["communications"][0]["provider"] == "manual"
    assert payload["communications"][0]["subject"] == "First contact attempt"
    assert payload["communications"][0]["body"] == "Left voicemail and will follow up by text."
    assert "lead.communication_logged" in [
        activity["event_type"] for activity in payload["recent_activity"]
    ]
    assert int(db_session.scalar(select(func.count()).select_from(CommunicationRecord)) or 0) == 1
    assert int(
        db_session.scalar(
            select(func.count()).select_from(AuditEvent).where(
                AuditEvent.action == "communication.log"
            )
        )
        or 0
    ) == 1


def test_add_lead_communication_rejects_unknown_channel(
    db_session: Session,
    api_db_override: None,
) -> None:
    seed_owner(db_session)
    client = TestClient(app)
    created_response = client.post(
        "/api/v1/leads",
        headers={"X-Dev-User-Email": OWNER_EMAIL},
        json=lead_payload(),
    )
    lead_id = created_response.json()["id"]

    response = client.post(
        f"/api/v1/leads/{lead_id}/communications",
        headers={"X-Dev-User-Email": OWNER_EMAIL},
        json={
            "direction": "outbound",
            "channel": "fax",
            "status": "logged",
            "body": "Unsupported channel.",
        },
    )

    assert response.status_code == 422


def test_schedule_lead_appointment_updates_lead_and_records_audit(
    db_session: Session,
    api_db_override: None,
) -> None:
    seed_owner(db_session)
    client = TestClient(app)
    created_response = client.post(
        "/api/v1/leads",
        headers={"X-Dev-User-Email": OWNER_EMAIL},
        json=lead_payload(),
    )
    lead_id = created_response.json()["id"]

    response = client.post(
        f"/api/v1/leads/{lead_id}/appointments",
        headers={"X-Dev-User-Email": OWNER_EMAIL},
        json={
            "appointment_type": "walkthrough",
            "status": "scheduled",
            "scheduled_start_at": "2026-07-17T15:00:00Z",
            "scheduled_end_at": "2026-07-17T16:00:00Z",
            "location_type": "property",
            "location": "123 Peachtree St, Atlanta, GA 30303",
            "notes": "Seller wants us to look at roof and kitchen first.",
        },
    )

    assert response.status_code == 201
    payload = response.json()
    assert payload["stage_key"] == "appointment_scheduled"
    assert payload["appointment_status"] == "scheduled"
    assert payload["next_follow_up_at"].startswith("2026-07-17T15:00:00")
    assert payload["appointments"][0]["appointment_type"] == "walkthrough"
    assert payload["appointments"][0]["status"] == "scheduled"
    assert payload["appointments"][0]["location_type"] == "property"
    assert "lead.appointment_scheduled" in [
        activity["event_type"] for activity in payload["recent_activity"]
    ]
    assert int(db_session.scalar(select(func.count()).select_from(Appointment)) or 0) == 1
    assert int(
        db_session.scalar(
            select(func.count()).select_from(AuditEvent).where(
                AuditEvent.action == "appointment.create"
            )
        )
        or 0
    ) == 1


def test_schedule_lead_appointment_rejects_invalid_time_window(
    db_session: Session,
    api_db_override: None,
) -> None:
    seed_owner(db_session)
    client = TestClient(app)
    created_response = client.post(
        "/api/v1/leads",
        headers={"X-Dev-User-Email": OWNER_EMAIL},
        json=lead_payload(),
    )
    lead_id = created_response.json()["id"]

    response = client.post(
        f"/api/v1/leads/{lead_id}/appointments",
        headers={"X-Dev-User-Email": OWNER_EMAIL},
        json={
            "appointment_type": "seller_call",
            "status": "scheduled",
            "scheduled_start_at": "2026-07-17T15:00:00Z",
            "scheduled_end_at": "2026-07-17T14:00:00Z",
            "location_type": "phone",
        },
    )

    assert response.status_code == 422


def test_create_lead_underwriting_version_updates_stage_and_records_audit(
    db_session: Session,
    api_db_override: None,
) -> None:
    seed_owner(db_session)
    client = TestClient(app)
    created_response = client.post(
        "/api/v1/leads",
        headers={"X-Dev-User-Email": OWNER_EMAIL},
        json=lead_payload(),
    )
    lead_id = created_response.json()["id"]

    response = client.post(
        f"/api/v1/leads/{lead_id}/underwriting",
        headers={"X-Dev-User-Email": OWNER_EMAIL},
        json={
            "status": "needs_review",
            "arv_low_cents": 26000000,
            "arv_high_cents": 28500000,
            "repair_low_cents": 3500000,
            "repair_high_cents": 5000000,
            "max_offer_cents": 17000000,
            "recommended_offer_cents": 16250000,
            "offer_strategy": "cash_offer",
            "notes": "Manual first-pass underwriting before comp review.",
        },
    )

    assert response.status_code == 201
    payload = response.json()
    assert payload["stage_key"] == "underwriting"
    assert payload["underwriting_versions"][0]["version_number"] == 1
    assert payload["underwriting_versions"][0]["status"] == "needs_review"
    assert payload["underwriting_versions"][0]["recommended_offer_cents"] == 16250000
    assert "lead.underwriting_created" in [
        activity["event_type"] for activity in payload["recent_activity"]
    ]
    assert int(db_session.scalar(select(func.count()).select_from(UnderwritingVersion)) or 0) == 1
    assert int(
        db_session.scalar(
            select(func.count()).select_from(AuditEvent).where(
                AuditEvent.action == "underwriting.create"
            )
        )
        or 0
    ) == 1

    second_response = client.post(
        f"/api/v1/leads/{lead_id}/underwriting",
        headers={"X-Dev-User-Email": OWNER_EMAIL},
        json={
            "status": "approved",
            "arv_low_cents": 27000000,
            "arv_high_cents": 29000000,
            "repair_low_cents": 3000000,
            "repair_high_cents": 4500000,
            "max_offer_cents": 17500000,
            "recommended_offer_cents": 17000000,
            "offer_strategy": "cash_offer",
        },
    )

    assert second_response.status_code == 201
    second_payload = second_response.json()
    assert second_payload["stage_key"] == "offer_ready"
    assert second_payload["underwriting_versions"][0]["version_number"] == 2


def test_create_lead_underwriting_rejects_invalid_ranges(
    db_session: Session,
    api_db_override: None,
) -> None:
    seed_owner(db_session)
    client = TestClient(app)
    created_response = client.post(
        "/api/v1/leads",
        headers={"X-Dev-User-Email": OWNER_EMAIL},
        json=lead_payload(),
    )
    lead_id = created_response.json()["id"]

    response = client.post(
        f"/api/v1/leads/{lead_id}/underwriting",
        headers={"X-Dev-User-Email": OWNER_EMAIL},
        json={
            "status": "draft",
            "arv_low_cents": 30000000,
            "arv_high_cents": 25000000,
        },
    )

    assert response.status_code == 422


def test_preview_lead_market_value_uses_rentcast_without_saving_underwriting(
    db_session: Session,
    api_db_override: None,
    monkeypatch,
) -> None:
    seed_owner(db_session)
    monkeypatch.setenv("PROPERTY_DATA_PROVIDER", "rentcast")
    monkeypatch.setenv("RENTCAST_API_KEY", "test-rentcast-key")
    get_settings.cache_clear()

    captured: dict[str, object] = {}

    class FakeRentCastClient:
        def __init__(self, **kwargs: object) -> None:
            captured["init"] = kwargs

        def get_value_estimate(self, **kwargs: object) -> RentCastValueEstimate:
            captured["request"] = kwargs
            return RentCastValueEstimate(
                price=285000,
                price_range_low=260000,
                price_range_high=305000,
                subject_property={
                    "formattedAddress": "123 Peachtree St, Atlanta, GA 30303",
                    "propertyType": "Single Family",
                },
                comparables=[
                    {
                        "id": "comp-1",
                        "formattedAddress": "125 Peachtree St, Atlanta, GA 30303",
                        "status": "Inactive",
                        "listingType": "Standard",
                        "propertyType": "Single Family",
                        "price": 280000,
                        "bedrooms": 3,
                        "bathrooms": 2,
                        "squareFootage": 1800,
                        "yearBuilt": 1985,
                        "distance": 0.4,
                        "daysOld": 42,
                        "correlation": 0.98,
                    }
                ],
                raw_response={},
            )

    monkeypatch.setattr("app.services.leads.RentCastClient", FakeRentCastClient)
    client = TestClient(app)
    created_response = client.post(
        "/api/v1/leads",
        headers={"X-Dev-User-Email": OWNER_EMAIL},
        json=lead_payload(),
    )
    lead_id = created_response.json()["id"]

    response = client.get(
        f"/api/v1/leads/{lead_id}/underwriting/market-value",
        headers={"X-Dev-User-Email": OWNER_EMAIL},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["provider"] == "rentcast"
    assert payload["estimated_value_cents"] == 28500000
    assert payload["estimated_value_low_cents"] == 26000000
    assert payload["estimated_value_high_cents"] == 30500000
    assert payload["human_review_required"] is True
    assert payload["comparables"][0]["provider_id"] == "comp-1"
    assert payload["comparables"][0]["price_cents"] == 28000000
    assert captured["request"] == {
        "address": "123 Peachtree St, Atlanta, GA 30303",
        "property_type": "single_family",
    }
    assert int(db_session.scalar(select(func.count()).select_from(UnderwritingVersion)) or 0) == 0
    get_settings.cache_clear()


def test_preview_lead_market_value_requires_rentcast_key(
    db_session: Session,
    api_db_override: None,
    monkeypatch,
) -> None:
    seed_owner(db_session)
    monkeypatch.setenv("PROPERTY_DATA_PROVIDER", "rentcast")
    monkeypatch.delenv("RENTCAST_API_KEY", raising=False)
    get_settings.cache_clear()
    client = TestClient(app)
    created_response = client.post(
        "/api/v1/leads",
        headers={"X-Dev-User-Email": OWNER_EMAIL},
        json=lead_payload(),
    )
    lead_id = created_response.json()["id"]

    response = client.get(
        f"/api/v1/leads/{lead_id}/underwriting/market-value",
        headers={"X-Dev-User-Email": OWNER_EMAIL},
    )

    assert response.status_code == 422
    assert response.json()["detail"] == "RENTCAST_API_KEY is not configured."
    get_settings.cache_clear()


def test_create_lead_market_analysis_saves_draft_underwriting_and_mao(
    db_session: Session,
    api_db_override: None,
    monkeypatch,
) -> None:
    seed_owner(db_session)
    monkeypatch.setenv("PROPERTY_DATA_PROVIDER", "rentcast")
    monkeypatch.setenv("RENTCAST_API_KEY", "test-rentcast-key")
    monkeypatch.setenv("UNDERWRITING_DEFAULT_ASSIGNMENT_FEE_CENTS", "1500000")
    get_settings.cache_clear()
    provider_calls: list[str] = []

    class FakeRentCastClient:
        def __init__(self, **_: object) -> None:
            provider_calls.append("init")

        def get_value_estimate(self, **_: object) -> RentCastValueEstimate:
            provider_calls.append("value")
            return RentCastValueEstimate(
                price=300000,
                price_range_low=275000,
                price_range_high=325000,
                subject_property={
                    "id": "subject-1",
                    "formattedAddress": "123 Peachtree St, Atlanta, GA 30303",
                    "propertyType": "Single Family",
                    "bedrooms": 3,
                    "bathrooms": 2,
                    "squareFootage": 1800,
                    "yearBuilt": 1980,
                    "lotSize": 8000,
                },
                comparables=[],
                raw_response={
                    "price": 300000,
                    "priceRangeLow": 275000,
                    "priceRangeHigh": 325000,
                    "subjectProperty": {
                        "id": "subject-1",
                        "formattedAddress": "123 Peachtree St, Atlanta, GA 30303",
                        "propertyType": "Single Family",
                        "bedrooms": 3,
                        "bathrooms": 2,
                        "squareFootage": 1800,
                        "yearBuilt": 1980,
                        "lotSize": 8000,
                    },
                    "comparables": [],
                },
            )

        def get_property_record(self, **_: object) -> dict[str, object]:
            provider_calls.append("subject")
            return {
                "id": "subject-1",
                "formattedAddress": "123 Peachtree St, Atlanta, GA 30303",
                "propertyType": "Single Family",
                "bedrooms": 3,
                "bathrooms": 2,
                "squareFootage": 1800,
                "yearBuilt": 1980,
                "lotSize": 8000,
                "propertyTaxes": {"2025": 3600},
            }

        def get_recent_sales(self, **_: object) -> list[dict[str, object]]:
            provider_calls.append("sales")
            return [
                {
                    "id": "comp-1",
                    "formattedAddress": "125 Peachtree St, Atlanta, GA 30303",
                    "propertyType": "Single Family",
                    "lastSalePrice": 280000,
                    "lastSaleDate": "2026-05-01T00:00:00Z",
                    "bedrooms": 3,
                    "bathrooms": 2,
                    "squareFootage": 1700,
                    "yearBuilt": 1982,
                    "lotSize": 7000,
                    "distance": 0.2,
                },
                {
                    "id": "comp-2",
                    "formattedAddress": "127 Peachtree St, Atlanta, GA 30303",
                    "propertyType": "Single Family",
                    "lastSalePrice": 300000,
                    "lastSaleDate": "2026-04-15T00:00:00Z",
                    "bedrooms": 3,
                    "bathrooms": 2,
                    "squareFootage": 1800,
                    "yearBuilt": 1980,
                    "lotSize": 8000,
                    "distance": 0.4,
                },
                {
                    "id": "comp-3",
                    "formattedAddress": "129 Peachtree St, Atlanta, GA 30303",
                    "propertyType": "Single Family",
                    "lastSalePrice": 320000,
                    "lastSaleDate": "2026-03-20T00:00:00Z",
                    "bedrooms": 3,
                    "bathrooms": 2,
                    "squareFootage": 1900,
                    "yearBuilt": 1978,
                    "lotSize": 8500,
                    "distance": 0.6,
                },
                {
                    "id": "comp-4",
                    "formattedAddress": "131 Peachtree St, Atlanta, GA 30303",
                    "propertyType": "Single Family",
                    "lastSalePrice": 230000,
                    "lastSaleDate": "2026-05-12T00:00:00Z",
                    "bedrooms": 3,
                    "bathrooms": 2,
                    "squareFootage": 1750,
                    "yearBuilt": 1981,
                    "lotSize": 7800,
                    "distance": 0.3,
                },
                {
                    "id": "comp-5",
                    "formattedAddress": "133 Peachtree St, Atlanta, GA 30303",
                    "propertyType": "Single Family",
                    "lastSalePrice": 240000,
                    "lastSaleDate": "2026-04-28T00:00:00Z",
                    "bedrooms": 3,
                    "bathrooms": 2,
                    "squareFootage": 1850,
                    "yearBuilt": 1979,
                    "lotSize": 8200,
                    "distance": 0.5,
                },
                {
                    "id": "reject-size",
                    "formattedAddress": "200 Peachtree St, Atlanta, GA 30303",
                    "propertyType": "Single Family",
                    "lastSalePrice": 400000,
                    "lastSaleDate": "2026-05-03T00:00:00Z",
                    "bedrooms": 4,
                    "bathrooms": 3,
                    "squareFootage": 2400,
                    "yearBuilt": 1980,
                    "lotSize": 9000,
                    "distance": 0.8,
                },
            ]

        def get_rent_estimate(self, **_: object) -> RentCastRentEstimate:
            provider_calls.append("rent")
            return RentCastRentEstimate(
                rent=2400,
                rent_range_low=2200,
                rent_range_high=2600,
                comparables=[],
                raw_response={
                    "rent": 2400,
                    "rentRangeLow": 2200,
                    "rentRangeHigh": 2600,
                    "comparables": [],
                },
            )

    monkeypatch.setattr("app.services.leads.RentCastClient", FakeRentCastClient)
    client = TestClient(app)
    created_response = client.post(
        "/api/v1/leads",
        headers={"X-Dev-User-Email": OWNER_EMAIL},
        json=lead_payload(),
    )
    lead_id = created_response.json()["id"]

    response = client.post(
        f"/api/v1/leads/{lead_id}/underwriting/market-analysis",
        headers={"X-Dev-User-Email": OWNER_EMAIL},
        json={
            "input_verification_status": "pre_meeting_reviewed",
            "current_condition": "dated_livable",
            "target_condition": "standard_flip",
            "repair_level": "moderate",
            "repair_items": [
                {
                    "category": "roof",
                    "estimated_cost_cents": 1500000,
                    "details": "Replace architectural shingles.",
                },
                {
                    "category": "kitchen",
                    "estimated_cost_cents": 2500000,
                    "details": "Entry-level retail kitchen.",
                },
                {
                    "category": "hvac",
                    "estimated_cost_cents": 1000000,
                    "details": "Replace system.",
                },
            ],
            "contingency_override_percentage": 20,
            "holding_period_months": 9,
            "repair_notes": "Pre-meeting contractor estimate.",
            "comp_condition_overrides": {
                "comp-1": "renovated",
                "comp-2": "renovated",
                "comp-3": "renovated",
                "comp-4": "as_is",
                "comp-5": "as_is",
            },
        },
    )

    assert response.status_code == 201
    payload = response.json()
    assert payload["provider"] == "rentcast"
    assert payload["methodology_version"] == "v2"
    assert payload["as_is_value_cents"] == 23000000
    assert payload["arv_low_cents"] == 28000000
    assert payload["arv_point_cents"] == 30000000
    assert payload["arv_high_cents"] == 32000000
    assert payload["conservative_arv_cents"] == 29400000
    assert payload["repair_low_cents"] == 5000000
    assert payload["repair_high_cents"] == 6000000
    assert payload["base_rehab_cents"] == 5000000
    assert payload["total_rehab_cents"] == 6000000
    assert payload["flip_buyer_max_cents"] == 13314000
    assert payload["rental_buyer_max_cents"] == 13859700
    assert payload["seller_contract_ceiling_cents"] == 12109700
    assert payload["recommended_offer_cents"] == 11140924
    assert payload["report_stage"] == "pre_meeting_reviewed"
    assert payload["pre_meeting_inputs"]["repair_estimate_source"] == "itemized"
    assert payload["pre_meeting_inputs"]["holding_period_months"] == 9
    assert len(payload["pre_meeting_inputs"]["repair_items"]) == 3
    assert payload["assumptions"]["financing_holding_percentage"] == 0.09
    assert payload["manual_review_required"] is False
    assert payload["review_reasons"] == []
    assert payload["offer_low_percentage"] == 65
    assert payload["offer_high_percentage"] == 70
    assert len(payload["selected_comps"]) == 5
    assert len(payload["rejected_comps"]) == 1
    assert payload["selected_comps"][0]["price_source"] == "recorded_sale"
    assert payload["underwriting_version_id"] is not None
    assert int(
        db_session.scalar(select(func.count()).select_from(UnderwritingMarketAnalysis)) or 0
    ) == 1
    assert int(db_session.scalar(select(func.count()).select_from(UnderwritingVersion)) or 0) == 1
    saved_version = db_session.scalar(select(UnderwritingVersion))
    assert saved_version is not None
    assert saved_version.source == "rentcast_property_records"
    assert saved_version.status == "needs_review"
    assert saved_version.max_offer_cents == 12109700
    assert saved_version.recommended_offer_cents == 11140924

    latest_analysis_response = client.get(
        f"/api/v1/leads/{lead_id}/underwriting/market-analysis",
        headers={"X-Dev-User-Email": OWNER_EMAIL},
    )

    assert latest_analysis_response.status_code == 200
    assert latest_analysis_response.json()["id"] == payload["id"]

    investor_report_response = client.get(
        f"/api/v1/leads/{lead_id}/underwriting/market-analysis/{payload['id']}/report.pdf",
        headers={"X-Dev-User-Email": OWNER_EMAIL},
    )

    assert investor_report_response.status_code == 200
    assert investor_report_response.headers["content-type"] == "application/pdf"
    assert "stonegate-investor-property-report" in investor_report_response.headers[
        "content-disposition"
    ]
    assert investor_report_response.content.startswith(b"%PDF")
    assert b"Assignment fee assumption" in investor_report_response.content
    assert b"Repair scope and input record" in investor_report_response.content
    assert b"Pre-meeting reviewed" in investor_report_response.content
    assert b"Pre-meeting contractor estimate" in investor_report_response.content
    assert b"Roof" in investor_report_response.content

    client_report_response = client.get(
        (
            f"/api/v1/leads/{lead_id}/underwriting/market-analysis/"
            f"{payload['id']}/report.pdf?audience=client"
        ),
        headers={"X-Dev-User-Email": OWNER_EMAIL},
    )

    assert client_report_response.status_code == 200
    assert client_report_response.headers["content-type"] == "application/pdf"
    assert "stonegate-client-property-report" in client_report_response.headers[
        "content-disposition"
    ]
    assert client_report_response.content.startswith(b"%PDF")
    assert b"Assignment fee assumption" not in client_report_response.content
    assert b"Offer ceiling" not in client_report_response.content
    assert b"Recommended starting offer" not in client_report_response.content
    assert b"Repair scope and input record" not in client_report_response.content
    assert b"Pre-meeting contractor estimate" not in client_report_response.content
    assert b"Pre-meeting reviewed" in client_report_response.content
    unclassified_response = client.post(
        f"/api/v1/leads/{lead_id}/underwriting/market-analysis",
        headers={"X-Dev-User-Email": OWNER_EMAIL},
        json={"repair_level": "moderate"},
    )
    assert unclassified_response.status_code == 201
    assert unclassified_response.json()["manual_review_required"] is True
    assert unclassified_response.json()["confidence_score"] <= 59
    assert unclassified_response.json()["arv_point_cents"] == 30000000
    cached_response = client.post(
        f"/api/v1/leads/{lead_id}/underwriting/market-analysis",
        headers={"X-Dev-User-Email": OWNER_EMAIL},
        json={
            "repair_level": "light",
            "base_rehab_override_cents": 4000000,
            "contingency_override_percentage": 10,
            "comp_condition_overrides": {
                "comp-1": "renovated",
                "comp-2": "renovated",
                "comp-3": "renovated",
                "comp-4": "as_is",
                "comp-5": "as_is",
            },
        },
    )
    assert cached_response.status_code == 201
    assert provider_calls == ["init", "value", "subject", "sales", "rent"]
    assert cached_response.json()["base_rehab_cents"] == 4000000
    assert cached_response.json()["total_rehab_cents"] == 4400000
    assert (
        cached_response.json()["pre_meeting_inputs"]["repair_estimate_source"]
        == "user_total"
    )
    itemized_precedence_response = client.post(
        f"/api/v1/leads/{lead_id}/underwriting/market-analysis",
        headers={"X-Dev-User-Email": OWNER_EMAIL},
        json={
            "repair_level": "light",
            "base_rehab_override_cents": 10000000,
            "repair_items": [
                {
                    "category": "roof",
                    "estimated_cost_cents": 2000000,
                },
            ],
            "contingency_override_percentage": 10,
            "comp_condition_overrides": {
                "comp-1": "renovated",
                "comp-2": "renovated",
                "comp-3": "renovated",
                "comp-4": "as_is",
                "comp-5": "as_is",
            },
        },
    )
    assert itemized_precedence_response.status_code == 201
    assert provider_calls == ["init", "value", "subject", "sales", "rent"]
    assert itemized_precedence_response.json()["base_rehab_cents"] == 2000000
    assert itemized_precedence_response.json()["total_rehab_cents"] == 2200000
    assert (
        itemized_precedence_response.json()["pre_meeting_inputs"][
            "repair_estimate_source"
        ]
        == "itemized"
    )
    get_settings.cache_clear()


def test_open_lead_transaction_creates_deal_checklist_and_audit(
    db_session: Session,
    api_db_override: None,
) -> None:
    seed_owner(db_session)
    client = TestClient(app)
    created_response = client.post(
        "/api/v1/leads",
        headers={"X-Dev-User-Email": OWNER_EMAIL},
        json=lead_payload(),
    )
    lead_id = created_response.json()["id"]

    response = client.post(
        f"/api/v1/leads/{lead_id}/transactions",
        headers={"X-Dev-User-Email": OWNER_EMAIL},
        json={
            "contract_type": "purchase_agreement",
            "purchase_price_cents": 17000000,
            "assignment_fee_cents": 2500000,
            "earnest_money_cents": 100000,
            "title_company": "Stonegate Title Partner",
            "closing_date": "2026-08-14T21:00:00Z",
            "inspection_period_days": 7,
            "notes": "Seller accepted the approved offer.",
        },
    )

    assert response.status_code == 201
    payload = response.json()
    assert payload["stage_key"] == "under_contract"
    assert payload["transactions"][0]["status"] == "contract_prep"
    assert payload["transactions"][0]["contract_type"] == "purchase_agreement"
    assert payload["transactions"][0]["purchase_price_cents"] == 17000000
    assert len(payload["transactions"][0]["checklist_items"]) == 8
    assert "lead.transaction_opened" in [
        activity["event_type"] for activity in payload["recent_activity"]
    ]
    assert int(db_session.scalar(select(func.count()).select_from(Deal)) or 0) == 1
    assert int(db_session.scalar(select(func.count()).select_from(Transaction)) or 0) == 1
    assert int(
        db_session.scalar(select(func.count()).select_from(TransactionChecklistItem)) or 0
    ) == 8
    assert int(
        db_session.scalar(
            select(func.count()).select_from(AuditEvent).where(
                AuditEvent.action == "transaction.create"
            )
        )
        or 0
    ) == 1


def test_open_lead_transaction_rejects_duplicate_active_transaction(
    db_session: Session,
    api_db_override: None,
) -> None:
    seed_owner(db_session)
    client = TestClient(app)
    created_response = client.post(
        "/api/v1/leads",
        headers={"X-Dev-User-Email": OWNER_EMAIL},
        json=lead_payload(),
    )
    lead_id = created_response.json()["id"]
    payload = {
        "contract_type": "purchase_agreement",
        "purchase_price_cents": 17000000,
    }

    first_response = client.post(
        f"/api/v1/leads/{lead_id}/transactions",
        headers={"X-Dev-User-Email": OWNER_EMAIL},
        json=payload,
    )
    second_response = client.post(
        f"/api/v1/leads/{lead_id}/transactions",
        headers={"X-Dev-User-Email": OWNER_EMAIL},
        json=payload,
    )

    assert first_response.status_code == 201
    assert second_response.status_code == 422


def test_record_lead_buyer_offer_creates_offer_and_audit(
    db_session: Session,
    api_db_override: None,
) -> None:
    seed_owner(db_session)
    client = TestClient(app)
    created_response = client.post(
        "/api/v1/leads",
        headers={"X-Dev-User-Email": OWNER_EMAIL},
        json=lead_payload(),
    )
    lead_id = created_response.json()["id"]
    transaction_response = client.post(
        f"/api/v1/leads/{lead_id}/transactions",
        headers={"X-Dev-User-Email": OWNER_EMAIL},
        json={
            "contract_type": "purchase_agreement",
            "purchase_price_cents": 17000000,
        },
    )
    buyer_response = client.post(
        "/api/v1/buyers",
        headers={"X-Dev-User-Email": OWNER_EMAIL},
        json={
            "name": "Acme Cash Buyer",
            "company_name": "Acme Holdings",
            "email": "buyer@example.com",
            "buyer_type": "cash_buyer",
            "status": "active",
            "proof_of_funds_status": "received",
            "max_purchase_price_cents": 24000000,
        },
    )

    assert transaction_response.status_code == 201
    assert buyer_response.status_code == 201
    response = client.post(
        f"/api/v1/leads/{lead_id}/buyer-offers",
        headers={"X-Dev-User-Email": OWNER_EMAIL},
        json={
            "buyer_id": buyer_response.json()["id"],
            "amount_cents": 19500000,
            "earnest_money_cents": 500000,
            "financing_type": "cash",
            "status": "received",
            "proof_of_funds_received": True,
            "notes": "Can close in 10 days.",
        },
    )

    assert response.status_code == 201
    payload = response.json()
    assert payload["buyer_offers"][0]["buyer_name"] == "Acme Cash Buyer"
    assert payload["buyer_offers"][0]["amount_cents"] == 19500000
    assert payload["buyer_offers"][0]["earnest_money_cents"] == 500000
    assert payload["buyer_offers"][0]["proof_of_funds_received"] is True
    assert "lead.buyer_offer_received" in [
        activity["event_type"] for activity in payload["recent_activity"]
    ]
    assert int(db_session.scalar(select(func.count()).select_from(BuyerOffer)) or 0) == 1
    assert int(
        db_session.scalar(
            select(func.count()).select_from(AuditEvent).where(
                AuditEvent.action == "buyer_offer.create"
            )
        )
        or 0
    ) == 1


def test_update_lead_staff_details_requires_permission(api_db_override: None) -> None:
    client = TestClient(app)

    response = client.patch(
        "/api/v1/leads/00000000-0000-0000-0000-000000000000",
        json={"seller_name": "Jane Seller"},
    )

    assert response.status_code == 401


def test_create_lead_requires_permission(api_db_override: None) -> None:
    client = TestClient(app)

    response = client.post("/api/v1/leads", json=lead_payload())

    assert response.status_code == 401
