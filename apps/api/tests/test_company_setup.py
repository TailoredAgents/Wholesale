from typing import Any, cast

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.main import app
from app.models.foundation import AuditEvent
from app.services.bootstrap import bootstrap_foundation

OWNER_EMAIL = "owner@example.com"
LEAD_MANAGER_EMAIL = "lead.manager@example.com"


def test_company_setup_seats_counterparties_and_role_acceptance(
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
    manager_headers = {"X-Dev-User-Email": LEAD_MANAGER_EMAIL}

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

    install_response = client.post(
        "/api/v1/operating-model/setup/install",
        headers=owner_headers,
    )
    assert install_response.status_code == 200, install_response.text
    installed = cast(dict[str, Any], install_response.json())
    assert installed["created_seat_count"] == 9
    assert len(installed["setup"]["seats"]) == 9

    repeat_response = client.post(
        "/api/v1/operating-model/setup/install",
        headers=owner_headers,
    )
    assert repeat_response.status_code == 200, repeat_response.text
    assert repeat_response.json()["created_seat_count"] == 0

    lead_management_seat = next(
        seat
        for seat in installed["setup"]["seats"]
        if seat["seat_key"] == "lead_management"
    )
    seat_response = client.patch(
        f"/api/v1/operating-model/setup/seats/{lead_management_seat['id']}",
        headers=owner_headers,
        json={
            "status": "covered",
            "primary_user_id": lead_manager["id"],
            "backup_user_id": None,
            "notes": "Owns warm lead qualification and appointment setting.",
        },
    )
    assert seat_response.status_code == 200, seat_response.text
    assert seat_response.json()["primary_user_name"] == "Lead Manager"

    counterparty_response = client.post(
        "/api/v1/operating-model/setup/counterparties",
        headers=owner_headers,
        json={
            "counterparty_type": "closing_attorney",
            "name": "Georgia Closing Counsel",
            "company_name": "Closing Counsel LLC",
            "email": "closings@example.com",
            "notes": "Initial Georgia closing partner.",
        },
    )
    assert counterparty_response.status_code == 201, counterparty_response.text
    counterparty = cast(dict[str, Any], counterparty_response.json())
    assert counterparty["status"] == "pending"

    verify_response = client.post(
        f"/api/v1/operating-model/setup/counterparties/{counterparty['id']}/decision",
        headers=owner_headers,
        json={"decision": "verify", "reason": "Engagement and wiring process confirmed."},
    )
    assert verify_response.status_code == 200, verify_response.text
    assert verify_response.json()["status"] == "verified"

    acceptance_response = client.post(
        "/api/v1/operating-model/setup/role-acceptances",
        headers=owner_headers,
        json={
            "user_id": lead_manager["id"],
            "role_key": "acquisition_manager",
            "manual_key": "lead_manager",
            "manual_version": "2026.07",
        },
    )
    assert acceptance_response.status_code == 201, acceptance_response.text
    acceptance = cast(dict[str, Any], acceptance_response.json())
    assert acceptance["status"] == "assigned"

    my_setup_response = client.get(
        "/api/v1/operating-model/my-setup",
        headers=manager_headers,
    )
    assert my_setup_response.status_code == 200, my_setup_response.text
    assert my_setup_response.json()["role_keys"] == ["acquisition_manager"]
    assert len(my_setup_response.json()["acceptances"]) == 1

    submit_response = client.post(
        f"/api/v1/operating-model/my-setup/role-acceptances/{acceptance['id']}/submit",
        headers=manager_headers,
        json={
            "workspace_test_evidence": (
                "Opened an assigned lead, reviewed the inbox timeline, created a follow-up "
                "task, and confirmed restricted finance access."
            ),
            "employee_notes": "Ready for manager review.",
        },
    )
    assert submit_response.status_code == 200, submit_response.text
    assert submit_response.json()["status"] == "submitted"

    decision_response = client.post(
        f"/api/v1/operating-model/setup/role-acceptances/{acceptance['id']}/decision",
        headers=owner_headers,
        json={
            "decision": "approve",
            "manager_notes": "Workspace test and role boundaries confirmed.",
        },
    )
    assert decision_response.status_code == 200, decision_response.text
    assert decision_response.json()["status"] == "approved"

    overview_response = client.get(
        "/api/v1/operating-model",
        headers=owner_headers,
    )
    assert overview_response.status_code == 200, overview_response.text
    setup = cast(dict[str, Any], overview_response.json())["company_setup"]
    checks = {item["key"]: item for item in setup["checks"]}
    assert checks["closing_partner"]["status"] == "complete"
    assert checks["role_acceptance"]["status"] == "complete"

    restricted_response = client.post(
        "/api/v1/operating-model/setup/install",
        headers=manager_headers,
    )
    assert restricted_response.status_code == 403

    actions = set(db_session.scalars(select(AuditEvent.action)))
    assert {
        "company_setup.installed",
        "operating_seat.updated",
        "business_counterparty.created",
        "business_counterparty.verify",
        "staff_role_acceptance.assigned",
        "staff_role_acceptance.submitted",
        "staff_role_acceptance.approve",
    } <= actions
