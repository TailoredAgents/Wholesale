from datetime import UTC, datetime, timedelta
from typing import Any, cast

from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.main import app
from app.models.foundation import (
    Appointment,
    AuditEvent,
    Contact,
    Lead,
    Prospect,
    ProspectHandoff,
    ProspectingAttempt,
    ProspectingScriptVersion,
    SuppressionRecord,
)
from app.services.bootstrap import bootstrap_foundation

OWNER_EMAIL = "owner@example.com"
VA_EMAIL = "va@example.com"
ACQUISITIONS_EMAIL = "acquisitions@example.com"


def create_user(
    client: TestClient,
    headers: dict[str, str],
    email: str,
    name: str,
    role_key: str,
) -> dict[str, Any]:
    response = client.post(
        "/api/v1/operations/users",
        headers=headers,
        json={"email": email, "display_name": name, "role_key": role_key},
    )
    assert response.status_code == 201, response.text
    return cast(dict[str, Any], response.json())


def create_prospecting_batch(
    client: TestClient,
    owner_headers: dict[str, str],
    va_id: str,
) -> dict[str, Any]:
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
    campaign_response = client.post(
        "/api/v1/operations/campaigns",
        headers=owner_headers,
        json={
            "market_id": market_response.json()["id"],
            "name": "Owner Outreach",
            "code": "owner-outreach",
            "channel": "cold_call",
        },
    )
    assert campaign_response.status_code == 201, campaign_response.text
    mapping_response = client.post(
        "/api/v1/campaign-management/import-mappings",
        headers=owner_headers,
        json={
            "name": "VA Workbench Import",
            "field_mapping": {
                "source_record_key": "ID",
                "legal_name": "Owner",
                "phone": "Phone",
                "street_address": "Address",
                "city": "City",
                "state_code": "State",
                "postal_code": "ZIP",
                "dnc_status": "DNC",
            },
        },
    )
    assert mapping_response.status_code == 201, mapping_response.text
    csv_content = """ID,Owner,Phone,Address,City,State,ZIP,DNC
1,Interested Seller,4045550101,101 Main St,Atlanta,GA,30303,No
2,DNC Seller,4045550102,102 Main St,Atlanta,GA,30303,No
3,Callback Seller,4045550103,103 Main St,Atlanta,GA,30303,No
"""
    import_response = client.post(
        "/api/v1/campaign-management/imports",
        headers=owner_headers,
        json={
            "campaign_id": campaign_response.json()["id"],
            "mapping_id": mapping_response.json()["id"],
            "default_assignee_user_id": va_id,
            "file_name": "va-workbench.csv",
            "csv_content": csv_content,
        },
    )
    assert import_response.status_code == 201, import_response.text
    batch_response = client.post(
        "/api/v1/campaign-management/calling-batches",
        headers=owner_headers,
        json={
            "campaign_id": campaign_response.json()["id"],
            "import_batch_id": import_response.json()["id"],
            "assigned_user_id": va_id,
            "name": "VA Daily Queue",
            "maximum_records": 100,
        },
    )
    assert batch_response.status_code == 201, batch_response.text
    return cast(dict[str, Any], batch_response.json())


def create_approved_script(client: TestClient, headers: dict[str, str]) -> dict[str, Any]:
    response = client.post(
        "/api/v1/prospecting/scripts",
        headers=headers,
        json={
            "title": "Stonegate Seller Conversation",
            "opening_script": (
                "Hi, this is Stonegate Home Buyers. I am calling about the property. "
                "Did I catch you at an okay time?"
            ),
            "qualification_questions": [
                {
                    "key": "motivation",
                    "label": "Reason for selling",
                    "prompt": "What has you considering selling the property?",
                    "required_for_handoff": True,
                },
                {
                    "key": "timeline",
                    "label": "Timeline",
                    "prompt": "When would you ideally like to sell?",
                    "required_for_handoff": True,
                },
                {
                    "key": "property_condition",
                    "label": "Property condition",
                    "prompt": "What repairs or updates does the property need?",
                    "required_for_handoff": True,
                },
                {
                    "key": "occupancy",
                    "label": "Occupancy",
                    "prompt": "Is the property owner occupied, tenant occupied, or vacant?",
                    "answer_type": "choice",
                    "choices": ["Owner occupied", "Tenant occupied", "Vacant"],
                    "required_for_handoff": True,
                },
                {
                    "key": "asking_price",
                    "label": "Price expectation",
                    "prompt": "Do you have a price in mind?",
                    "required_for_handoff": False,
                },
            ],
        },
    )
    assert response.status_code == 201, response.text
    script = cast(dict[str, Any], response.json())
    approval = client.post(
        f"/api/v1/prospecting/scripts/{script['id']}/approve",
        headers=headers,
    )
    assert approval.status_code == 200, approval.text
    return cast(dict[str, Any], approval.json())


def test_phase_four_guided_queue_handoff_review_and_scorecards(
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
    va_headers = {"X-Dev-User-Email": VA_EMAIL}
    va = create_user(client, owner_headers, VA_EMAIL, "VA Caller", "prospecting_caller")
    acquisitions = create_user(
        client,
        owner_headers,
        ACQUISITIONS_EMAIL,
        "Lead Manager",
        "acquisition_manager",
    )
    batch = create_prospecting_batch(client, owner_headers, va["id"])

    no_script_start = client.post(
        f"/api/v1/prospecting/entries/{batch['entries'][0]['id']}/start",
        headers=va_headers,
    )
    assert no_script_start.status_code == 422
    assert "approve a caller script" in no_script_start.json()["detail"]
    assert client.post(
        "/api/v1/prospecting/scripts",
        headers=va_headers,
        json={
            "title": "Unauthorized",
            "opening_script": "This caller cannot create an approved company script.",
            "qualification_questions": [
                {"key": "motivation", "label": "Motivation", "prompt": "Why sell?"}
            ],
        },
    ).status_code == 403
    script = create_approved_script(client, owner_headers)
    assert script["version_number"] == 1
    assert script["status"] == "approved"

    workbench_response = client.get("/api/v1/prospecting", headers=va_headers)
    assert workbench_response.status_code == 200, workbench_response.text
    workbench = workbench_response.json()
    assert workbench["can_manage"] is False
    assert workbench["current_entry"]["legal_name"] == "Interested Seller"
    assert workbench["queue"]["ready"] == 3
    assert workbench["scripts"] == []

    first_start = client.post(
        f"/api/v1/prospecting/entries/{batch['entries'][0]['id']}/start",
        headers=va_headers,
    )
    assert first_start.status_code == 200, first_start.text
    first_attempt_id = first_start.json()["active_attempt"]["id"]
    concurrent_start = client.post(
        f"/api/v1/prospecting/entries/{batch['entries'][1]['id']}/start",
        headers=va_headers,
    )
    assert concurrent_start.status_code == 422
    assert "Finish the active prospect" in concurrent_start.json()["detail"]

    incomplete_handoff = client.post(
        f"/api/v1/prospecting/attempts/{first_attempt_id}/complete",
        headers=va_headers,
        json={
            "outcome": "interested",
            "handoff_user_id": acquisitions["id"],
            "qualification_answers": {"motivation": "Inherited property"},
        },
    )
    assert incomplete_handoff.status_code == 422
    first_completion = client.post(
        f"/api/v1/prospecting/attempts/{first_attempt_id}/complete",
        headers=va_headers,
        json={
            "outcome": "appointment_set",
            "handoff_user_id": acquisitions["id"],
            "appointment_start_at": (datetime.now(UTC) + timedelta(days=2)).isoformat(),
            "appointment_location_type": "seller_property",
            "qualification_answers": {
                "motivation": "Inherited property",
                "timeline": "Within 30 days",
                "property_condition": "Needs roof and kitchen updates",
                "occupancy": "Vacant",
                "asking_price": "$180,000",
            },
            "notes": "Seller is available after 3 PM.",
        },
    )
    assert first_completion.status_code == 200, first_completion.text
    assert first_completion.json()["status"] == "handoff_pending"
    assert int(db_session.scalar(select(func.count()).select_from(Lead)) or 0) == 1
    assert int(db_session.scalar(select(func.count()).select_from(Contact)) or 0) == 1
    assert int(db_session.scalar(select(func.count()).select_from(Appointment)) or 0) == 1

    manager_overview = client.get("/api/v1/prospecting", headers=owner_headers)
    assert manager_overview.status_code == 200, manager_overview.text
    pending = manager_overview.json()["pending_handoffs"]
    assert len(pending) == 1
    assert pending[0]["seller_name"] == "Interested Seller"
    assert client.post(
        f"/api/v1/prospecting/handoffs/{pending[0]['id']}/decision",
        headers=va_headers,
        json={"decision": "accepted"},
    ).status_code == 403
    correction = client.post(
        f"/api/v1/prospecting/handoffs/{pending[0]['id']}/decision",
        headers=owner_headers,
        json={"decision": "needs_correction", "reason": "Confirm decision-maker authority."},
    )
    assert correction.status_code == 200, correction.text
    returned = client.get("/api/v1/prospecting", headers=va_headers).json()
    assert returned["current_entry"]["status"] == "needs_correction"
    assert returned["returned_handoffs"][0]["review_reason"] == (
        "Confirm decision-maker authority."
    )

    correction_start = client.post(
        f"/api/v1/prospecting/entries/{batch['entries'][0]['id']}/start",
        headers=va_headers,
    )
    correction_attempt_id = correction_start.json()["active_attempt"]["id"]
    corrected = client.post(
        f"/api/v1/prospecting/attempts/{correction_attempt_id}/complete",
        headers=va_headers,
        json={
            "outcome": "interested",
            "handoff_user_id": acquisitions["id"],
            "qualification_answers": {
                "motivation": "Inherited property; sole owner confirmed",
                "timeline": "Within 30 days",
                "property_condition": "Needs roof and kitchen updates",
                "occupancy": "Vacant",
            },
            "notes": "Seller confirmed they are the sole decision-maker.",
        },
    )
    assert corrected.status_code == 200, corrected.text
    assert int(db_session.scalar(select(func.count()).select_from(Lead)) or 0) == 1
    pending_again = client.get("/api/v1/prospecting", headers=owner_headers).json()[
        "pending_handoffs"
    ]
    assert len(pending_again) == 1
    accepted = client.post(
        f"/api/v1/prospecting/handoffs/{pending_again[0]['id']}/decision",
        headers=owner_headers,
        json={"decision": "accepted", "reason": "Qualification is complete."},
    )
    assert accepted.status_code == 200, accepted.text
    lead = db_session.scalar(select(Lead))
    prospect = db_session.scalar(
        select(Prospect).where(Prospect.legal_name == "Interested Seller")
    )
    assert lead is not None and lead.stage_key == "appointment_scheduled"
    assert prospect is not None and prospect.status == "converted"

    second_start = client.post(
        f"/api/v1/prospecting/entries/{batch['entries'][1]['id']}/start",
        headers=va_headers,
    )
    second_attempt_id = second_start.json()["active_attempt"]["id"]
    dnc_completion = client.post(
        f"/api/v1/prospecting/attempts/{second_attempt_id}/complete",
        headers=va_headers,
        json={"outcome": "do_not_call", "qualification_answers": {}},
    )
    assert dnc_completion.status_code == 200, dnc_completion.text
    assert dnc_completion.json()["status"] == "completed"
    assert int(db_session.scalar(select(func.count()).select_from(SuppressionRecord)) or 0) == 1

    third_start = client.post(
        f"/api/v1/prospecting/entries/{batch['entries'][2]['id']}/start",
        headers=va_headers,
    )
    third_attempt_id = third_start.json()["active_attempt"]["id"]
    callback_at = datetime.now(UTC) + timedelta(days=1)
    callback_completion = client.post(
        f"/api/v1/prospecting/attempts/{third_attempt_id}/complete",
        headers=va_headers,
        json={
            "outcome": "callback_requested",
            "callback_at": callback_at.isoformat(),
            "qualification_answers": {},
        },
    )
    assert callback_completion.status_code == 200, callback_completion.text
    assert callback_completion.json()["status"] == "queued"
    assert callback_completion.json()["next_attempt_at"] is not None

    final_overview = client.get("/api/v1/prospecting", headers=owner_headers).json()
    scorecard = final_overview["scorecards"][0]
    assert scorecard["attempts"] == 4
    assert scorecard["contacts"] == 4
    assert scorecard["handoffs"] == 2
    assert scorecard["accepted_handoffs"] == 1
    assert scorecard["dnc_requests"] == 1
    assert scorecard["script_completion_rate_basis_points"] == 5000
    assert int(db_session.scalar(select(func.count()).select_from(ProspectingAttempt)) or 0) == 4
    assert int(db_session.scalar(select(func.count()).select_from(ProspectHandoff)) or 0) == 2
    assert (
        int(db_session.scalar(select(func.count()).select_from(ProspectingScriptVersion)) or 0)
        == 1
    )
    actions = set(db_session.scalars(select(AuditEvent.action)))
    assert {
        "prospecting.script_created",
        "prospecting.script_approved",
        "prospecting.attempt_started",
        "prospecting.attempt_completed",
        "prospecting.handoff_needs_correction",
        "prospecting.handoff_accepted",
    } <= actions


def test_correction_reason_is_required(
    db_session: Session,
    api_db_override: None,
) -> None:
    bootstrap_foundation(
        db_session,
        organization_name="Stonegate Home Buyers",
        admin_email=OWNER_EMAIL,
        admin_name="Owner",
    )
    response = TestClient(app).post(
        "/api/v1/prospecting/handoffs/00000000-0000-0000-0000-000000000001/decision",
        headers={"X-Dev-User-Email": OWNER_EMAIL},
        json={"decision": "needs_correction"},
    )
    assert response.status_code == 422
