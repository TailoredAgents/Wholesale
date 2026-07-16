from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.integrations.rentcast_client import RentCastValueEstimate
from app.main import app
from app.models.foundation import (
    ActivityEvent,
    Appointment,
    AuditEvent,
    BuyerOffer,
    CommunicationRecord,
    Deal,
    Task,
    Transaction,
    TransactionChecklistItem,
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
