from typing import Any, cast
from uuid import UUID

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.main import app
from app.models.foundation import AuditEvent, Lead
from app.schemas.operating_model import CompensationPlanCreate
from app.schemas.operations import CampaignCreate, MarketCreate
from app.services.bootstrap import bootstrap_foundation

OWNER_EMAIL = "owner@example.com"
LEAD_MANAGER_EMAIL = "lead.manager@example.com"


def test_current_compensation_plan_defaults() -> None:
    payload = CompensationPlanCreate()

    assert payload.dispositions_basis_points == 2000
    assert payload.ai_managed_disposition_basis_points == 1000
    assert payload.target_company_margin_basis_points == 3000


def test_operating_codes_are_normalized_before_validation() -> None:
    market = MarketCreate(
        name="Metro Atlanta",
        code="Georgia State",
        state_code="GA",
        timezone="America/New_York",
    )
    campaign = CampaignCreate(
        market_id=UUID("00000000-0000-0000-0000-000000000001"),
        name="North Metro Absentee Owners",
        code="North Metro / August",
        channel="cold_call",
    )

    assert market.code == "georgia-state"
    assert campaign.code == "north-metro-august"


def create_lead(client: TestClient, headers: dict[str, str]) -> dict[str, Any]:
    response = client.post(
        "/api/v1/leads",
        headers=headers,
        json={
            "contact": {"legal_name": "Compensation Seller", "contact_type": "seller"},
            "property": {
                "street_address": "400 Operating Model Way",
                "city": "Atlanta",
                "state": "GA",
                "postal_code": "30303",
                "property_type": "single_family",
            },
            "source": "cold_call",
            "stage_key": "qualified",
        },
    )
    assert response.status_code == 201, response.text
    return cast(dict[str, Any], response.json())


def test_deactivated_unused_employee_can_be_deleted_but_work_history_is_preserved(
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
    owner_headers = {"X-Dev-User-Email": OWNER_EMAIL}

    duplicate_response = client.post(
        "/api/v1/operations/users",
        headers=owner_headers,
        json={
            "email": "devon.duplicate@example.com",
            "display_name": "Devon Duplicate",
            "role_key": "disposition_rep",
        },
    )
    assert duplicate_response.status_code == 201, duplicate_response.text
    duplicate = cast(dict[str, Any], duplicate_response.json())

    active_delete_response = client.delete(
        f"/api/v1/operations/users/{duplicate['id']}", headers=owner_headers
    )
    assert active_delete_response.status_code == 422
    assert "Deactivate" in active_delete_response.json()["detail"]

    team_response = client.post(
        "/api/v1/operations/teams",
        headers=owner_headers,
        json={
            "name": "Dispositions",
            "team_type": "dispositions",
            "manager_user_id": duplicate["id"],
        },
    )
    assert team_response.status_code == 201, team_response.text
    team = cast(dict[str, Any], team_response.json())
    membership_response = client.post(
        f"/api/v1/operations/teams/{team['id']}/members",
        headers=owner_headers,
        json={"user_id": duplicate["id"], "membership_role": "manager"},
    )
    assert membership_response.status_code == 200, membership_response.text

    deactivate_response = client.patch(
        f"/api/v1/operations/users/{duplicate['id']}",
        headers=owner_headers,
        json={
            "is_active": False,
            "reason": "Duplicate account replaced by the correct login.",
        },
    )
    assert deactivate_response.status_code == 200, deactivate_response.text
    delete_response = client.delete(
        f"/api/v1/operations/users/{duplicate['id']}", headers=owner_headers
    )
    assert delete_response.status_code == 204, delete_response.text

    overview_response = client.get("/api/v1/operations", headers=owner_headers)
    assert overview_response.status_code == 200, overview_response.text
    overview = cast(dict[str, Any], overview_response.json())
    assert all(user["id"] != duplicate["id"] for user in overview["users"])
    updated_team = next(item for item in overview["teams"] if item["id"] == team["id"])
    assert updated_team["manager_user_id"] is None
    assert all(member["user_id"] != duplicate["id"] for member in updated_team["members"])

    historical_response = client.post(
        "/api/v1/operations/users",
        headers=owner_headers,
        json={
            "email": "devon.history@example.com",
            "display_name": "Devon With History",
            "role_key": "disposition_rep",
        },
    )
    assert historical_response.status_code == 201, historical_response.text
    historical_user = cast(dict[str, Any], historical_response.json())
    lead = create_lead(client, owner_headers)
    lead_record = db_session.get(Lead, UUID(lead["id"]))
    assert lead_record is not None
    lead_record.assigned_user_id = UUID(historical_user["id"])
    db_session.commit()
    historical_deactivate_response = client.patch(
        f"/api/v1/operations/users/{historical_user['id']}",
        headers=owner_headers,
        json={
            "is_active": False,
            "reason": "Employee left after working assigned leads.",
        },
    )
    assert historical_deactivate_response.status_code == 200
    blocked_delete_response = client.delete(
        f"/api/v1/operations/users/{historical_user['id']}", headers=owner_headers
    )
    assert blocked_delete_response.status_code == 422
    assert "operating history" in blocked_delete_response.json()["detail"]


def test_versioned_compensation_role_credit_and_market_launch_controls(
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
    owner_headers = {"X-Dev-User-Email": OWNER_EMAIL}

    operations_response = client.get("/api/v1/operations", headers=owner_headers)
    assert operations_response.status_code == 200, operations_response.text
    owner = next(
        user for user in operations_response.json()["users"] if user["email"] == OWNER_EMAIL
    )
    rename_response = client.patch(
        f"/api/v1/operations/users/{owner['id']}",
        headers=owner_headers,
        json={
            "display_name": "Austin",
            "reason": "Owner corrected their staff display name.",
        },
    )
    assert rename_response.status_code == 200, rename_response.text
    assert rename_response.json()["display_name"] == "Austin"

    user_response = client.post(
        "/api/v1/operations/users",
        headers=owner_headers,
        json={
            "email": LEAD_MANAGER_EMAIL,
            "display_name": "Lead Manager",
            "role_key": "acquisition_manager",
        },
    )
    assert user_response.status_code == 201, user_response.text
    lead_manager = cast(dict[str, Any], user_response.json())
    lead = create_lead(client, owner_headers)

    market_response = client.post(
        "/api/v1/operations/markets",
        headers=owner_headers,
        json={
            "name": "Atlanta Metro",
            "code": "atlanta-metro",
            "state_code": "GA",
            "timezone": "America/New_York",
            "is_primary": True,
        },
    )
    assert market_response.status_code == 201, market_response.text
    market = cast(dict[str, Any], market_response.json())

    plan_response = client.post(
        "/api/v1/operating-model/compensation-plans",
        headers=owner_headers,
        json={
            "name": "Stonegate Standard",
            "acquisition_reserve_cents": 250000,
            "target_company_margin_basis_points": 3000,
            "lead_manager_basis_points": 1000,
            "acquisitions_closer_basis_points": 1000,
            "ceo_management_basis_points": 1000,
            "dispositions_basis_points": 2000,
            "transaction_coordinator_basis_points": 500,
            "transaction_coordinator_cap_cents": 100000,
            "ai_managed_disposition_basis_points": 1000,
            "ai_oversight_disposition_min_basis_points": 500,
            "ai_oversight_disposition_max_basis_points": 750,
            "notes": "Approved operating-model economics.",
        },
    )
    assert plan_response.status_code == 201, plan_response.text
    plan = cast(dict[str, Any], plan_response.json())
    assert plan["version_number"] == 1
    assert plan["status"] == "draft"
    assert {role["role_key"] for role in plan["roles"]} == {
        "lead_manager",
        "acquisitions_closer",
        "ceo_management",
        "dispositions",
        "transaction_coordinator",
    }
    modes = {mode["key"]: mode for mode in plan["disposition_modes"]}
    assert modes["human_led"]["status"] == "available"
    assert modes["ai_operated_human_managed"]["status"] == "locked"
    assert modes["ai_led_human_oversight"]["human_share_min_basis_points"] == 500
    assert modes["ai_led_human_oversight"]["human_share_max_basis_points"] == 750

    draft_credit_response = client.post(
        "/api/v1/operating-model/role-credits",
        headers=owner_headers,
        json={
            "compensation_plan_version_id": plan["id"],
            "lead_id": lead["id"],
            "user_id": lead_manager["id"],
            "role_key": "lead_manager",
            "credit_basis_points": 10000,
        },
    )
    assert draft_credit_response.status_code == 422

    activation_response = client.post(
        f"/api/v1/operating-model/compensation-plans/{plan['id']}/activate",
        headers=owner_headers,
        json={"reason": "Owner approved the initial compensation policy."},
    )
    assert activation_response.status_code == 200, activation_response.text
    assert activation_response.json()["status"] == "active"

    credit_response = client.post(
        "/api/v1/operating-model/role-credits",
        headers=owner_headers,
        json={
            "compensation_plan_version_id": plan["id"],
            "lead_id": lead["id"],
            "user_id": lead_manager["id"],
            "role_key": "lead_manager",
            "credit_basis_points": 10000,
            "notes": "Qualified and owned the seller handoff.",
        },
    )
    assert credit_response.status_code == 201, credit_response.text
    credit = cast(dict[str, Any], credit_response.json())
    assert credit["status"] == "proposed"
    assert credit["seller_name"] == "Compensation Seller"
    decision_response = client.post(
        f"/api/v1/operating-model/role-credits/{credit['id']}/decision",
        headers=owner_headers,
        json={"decision": "approve", "reason": "Contribution confirmed before closing."},
    )
    assert decision_response.status_code == 200, decision_response.text
    assert decision_response.json()["status"] == "approved"

    duplicate_credit_response = client.post(
        "/api/v1/operating-model/role-credits",
        headers=owner_headers,
        json={
            "compensation_plan_version_id": plan["id"],
            "lead_id": lead["id"],
            "user_id": lead_manager["id"],
            "role_key": "lead_manager",
            "credit_basis_points": 1,
        },
    )
    assert duplicate_credit_response.status_code == 422

    checklist_response = client.post(
        f"/api/v1/operating-model/markets/{market['id']}/launch-checklists",
        headers=owner_headers,
        json={
            "owner_user_id": lead_manager["id"],
            "notes": "Georgia launch control record.",
        },
    )
    assert checklist_response.status_code == 201, checklist_response.text
    checklist = cast(dict[str, Any], checklist_response.json())
    assert checklist["status"] == "draft"
    assert checklist["total_items"] == 11
    assert checklist["completed_items"] == 0

    early_approval_response = client.post(
        f"/api/v1/operating-model/launch-checklists/{checklist['id']}/approve",
        headers=owner_headers,
        json={"reason": "Attempted before completion."},
    )
    assert early_approval_response.status_code == 422

    for item in checklist["items"]:
        item_response = client.patch(
            f"/api/v1/operating-model/launch-checklist-items/{item['id']}",
            headers=owner_headers,
            json={
                "status": "complete",
                "responsible_user_id": lead_manager["id"],
                "evidence_notes": f"Verified evidence for {item['item_key']}.",
            },
        )
        assert item_response.status_code == 200, item_response.text

    overview_response = client.get("/api/v1/operating-model", headers=owner_headers)
    assert overview_response.status_code == 200, overview_response.text
    overview = cast(dict[str, Any], overview_response.json())
    ready_checklist = overview["launch_checklists"][0]
    assert ready_checklist["status"] == "ready"
    assert ready_checklist["completed_items"] == 11

    approval_response = client.post(
        f"/api/v1/operating-model/launch-checklists/{checklist['id']}/approve",
        headers=owner_headers,
        json={"reason": "Owner confirmed all launch evidence."},
    )
    assert approval_response.status_code == 200, approval_response.text
    assert approval_response.json()["status"] == "approved"

    restricted_response = client.get(
        "/api/v1/operating-model",
        headers={"X-Dev-User-Email": LEAD_MANAGER_EMAIL},
    )
    assert restricted_response.status_code == 403

    actions = set(db_session.scalars(select(AuditEvent.action)))
    assert {
        "operating_model.compensation_plan_create",
        "operating_model.compensation_plan_activate",
        "operating_model.role_credit_create",
        "operating_model.role_credit_decide",
        "operating_model.market_launch_checklist_create",
        "operating_model.market_launch_item_update",
        "operating_model.market_launch_checklist_approve",
    } <= actions
