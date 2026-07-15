from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.main import app
from app.models.foundation import ActivityEvent, AuditEvent, Task
from app.services.bootstrap import bootstrap_foundation

OWNER_EMAIL = "owner@example.com"


def seed_owner(db_session: Session) -> None:
    bootstrap_foundation(
        db_session,
        organization_name="Oakwell Home Buyers",
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
    assert detail["recent_activity"][0]["event_type"] == "lead.created"

    update_response = client.patch(
        f"/api/v1/leads/{lead_id}/stage",
        headers={"X-Dev-User-Email": OWNER_EMAIL},
        json={"stage_key": "contacted", "reason": "Reached seller by phone."},
    )

    assert update_response.status_code == 200
    updated = update_response.json()
    assert updated["stage_key"] == "contacted"
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
