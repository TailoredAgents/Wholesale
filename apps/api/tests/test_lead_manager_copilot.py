from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.main import app
from app.models.foundation import (
    Appointment,
    CommunicationRecord,
    Conversation,
    LeadManagementCase,
    LeadManagerCopilotRecommendation,
    LeadManagerCopilotReview,
    Task,
)
from app.services.bootstrap import bootstrap_foundation

OWNER_EMAIL = "owner@example.com"
HEADERS = {"X-Dev-User-Email": OWNER_EMAIL}


def seller_payload() -> dict[str, object]:
    return {
        "property_address": "55 Auburn Ave",
        "property_city": "Atlanta",
        "property_state": "GA",
        "property_postal_code": "30303",
        "property_type": "single_family",
        "name": "Sam Seller",
        "phone": "4045551212",
        "email": "sam@example.com",
        "preferred_contact_method": "phone",
        "reason_for_selling": "Inherited property",
        "desired_timeline": "30 days",
        "property_condition": "major_repairs",
        "occupancy_status": "vacant",
        "asking_price": "",
        "mortgage_balance": "",
        "comments": "Needs repairs",
        "consent_to_contact": True,
        "sms_consent": True,
    }


def seed_owner(db: Session) -> None:
    bootstrap_foundation(
        db,
        organization_name="Stonegate Home Buyers",
        admin_email=OWNER_EMAIL,
        admin_name="Owner",
    )


def install_runtime(client: TestClient) -> None:
    assert client.post(
        "/api/v1/ai/orchestrator/portfolio/install", headers=HEADERS
    ).status_code == 201
    assert client.post("/api/v1/ai/copilots/install", headers=HEADERS).status_code == 201
    assert client.post(
        "/api/v1/ai/copilots/foundation/decision",
        headers=HEADERS,
        json={"decision": "approve", "notes": "Approved for AI4 pilot test."},
    ).status_code == 200
    assert client.post("/api/v1/ai/runtime/install", headers=HEADERS).status_code == 201


def model_output() -> dict[str, object]:
    return {
        "summary": "Sam inherited a vacant property and wants to sell within 30 days.",
        "priority_explanation": "The warm handoff is waiting for acceptance.",
        "qualification_gaps": ["Price expectation", "Mortgage or liens"],
        "recommended_questions": [
            "Do you have a price in mind?",
            "Is there a mortgage, lien, or other balance?",
        ],
        "message_draft": {
            "channel": "sms",
            "body": "Hi Sam, this is Stonegate. When is a convenient time to talk?",
        },
        "next_task": {
            "title": "Call Sam about the inherited property",
            "reason": "Confirm the missing price and title facts.",
            "due_timing": "Within 15 minutes",
        },
        "appointment_proposal": {
            "recommended": False,
            "reason": "Complete the initial qualification first.",
        },
        "handoff_summary": "Warm website lead; owner follow-up is pending.",
        "risks": ["Price expectation is unknown."],
        "evidence": [
            "Lead source is the seller website.",
            "Desired timeline is 30 days.",
        ],
        "confidence": 84,
    }


def test_copilot_prioritizes_work_and_blocks_generation_until_runtime_is_enabled(
    db_session: Session,
    api_db_override: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    get_settings.cache_clear()
    seed_owner(db_session)
    client = TestClient(app)
    intake = client.post("/api/v1/public/seller-leads", json=seller_payload())
    assert intake.status_code == 201
    case = db_session.scalar(select(LeadManagementCase))
    conversation = db_session.scalar(select(Conversation))
    assert case is not None and conversation is not None
    conversation.last_outbound_at = datetime.now(UTC) - timedelta(hours=2)
    conversation.last_inbound_at = datetime.now(UTC) - timedelta(minutes=5)
    db_session.commit()

    overview = client.get("/api/v1/lead-manager", headers=HEADERS)
    assert overview.status_code == 200
    copilot = overview.json()["copilot"]
    assert copilot["pilot_mode"] == "draft_only"
    assert copilot["external_actions_blocked"] is True
    assert copilot["work_items"][0]["case_id"] == str(case.id)
    assert copilot["work_items"][0]["priority_band"] == "urgent"
    assert copilot["work_items"][0]["missed_reply"] is True
    assert "Seller sent the latest message and needs a reply." in copilot["work_items"][0][
        "alerts"
    ]

    install_runtime(client)
    blocked = client.post(
        f"/api/v1/lead-manager/cases/{case.id}/copilot/analyze",
        headers=HEADERS,
        json={"idempotency_key": "lead-manager:blocked"},
    )
    assert blocked.status_code == 200
    assert blocked.json()["run_status"] == "blocked"
    assert blocked.json()["recommendation"] is None
    assert (
        int(
            db_session.scalar(
                select(func.count()).select_from(LeadManagerCopilotRecommendation)
            )
            or 0
        )
        == 0
    )
    get_settings.cache_clear()


def test_copilot_generates_idempotent_draft_and_preserves_human_control(
    db_session: Session,
    api_db_override: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seed_owner(db_session)
    client = TestClient(app)
    intake = client.post("/api/v1/public/seller-leads", json=seller_payload())
    assert intake.status_code == 201
    case = db_session.scalar(select(LeadManagementCase))
    assert case is not None
    install_runtime(client)
    monkeypatch.setenv("OPENAI_API_KEY", "test-openai-key")
    get_settings.cache_clear()

    class FakeOpenAIResponsesClient:
        def __init__(self, **_: object) -> None:
            pass

        def create_structured_response(self, **kwargs: object):
            schema = kwargs["json_schema"]
            assert isinstance(schema, dict)
            assert schema["properties"]["message_draft"]["additionalProperties"] is False
            return (
                model_output(),
                {"input_tokens": 120, "output_tokens": 80, "total_tokens": 200},
            )

    monkeypatch.setattr(
        "app.services.ai_runtime.OpenAIResponsesClient", FakeOpenAIResponsesClient
    )
    assert client.patch(
        "/api/v1/ai/runtime/policy",
        headers=HEADERS,
        json={"provider_status": "enabled"},
    ).status_code == 200
    assert client.patch(
        "/api/v1/ai/runtime/capabilities/lead.next_action",
        headers=HEADERS,
        json={"status": "enabled", "model_route": "default"},
    ).status_code == 200
    task_count = int(db_session.scalar(select(func.count()).select_from(Task)) or 0)
    appointment_count = int(
        db_session.scalar(select(func.count()).select_from(Appointment)) or 0
    )
    communication_count = int(
        db_session.scalar(select(func.count()).select_from(CommunicationRecord)) or 0
    )
    request = {"idempotency_key": "lead-manager:generated:1"}

    first = client.post(
        f"/api/v1/lead-manager/cases/{case.id}/copilot/analyze",
        headers=HEADERS,
        json=request,
    )
    second = client.post(
        f"/api/v1/lead-manager/cases/{case.id}/copilot/analyze",
        headers=HEADERS,
        json=request,
    )
    assert first.status_code == 200, first.text
    assert second.status_code == 200, second.text
    recommendation = first.json()["recommendation"]
    assert recommendation["status"] == "draft"
    assert recommendation["output_payload"]["message_draft"]["channel"] == "sms"
    assert second.json()["recommendation"]["id"] == recommendation["id"]

    edited_output = model_output()
    edited_output["summary"] = "Human corrected summary."
    reviewed = client.post(
        f"/api/v1/lead-manager/copilot/recommendations/{recommendation['id']}/review",
        headers=HEADERS,
        json={
            "decision": "edited",
            "final_output": edited_output,
            "notes": "Corrected after checking the seller record.",
            "estimated_time_saved_seconds": 240,
        },
    )
    assert reviewed.status_code == 200, reviewed.text
    assert reviewed.json()["decision"] == "edited"
    assert reviewed.json()["final_output"]["summary"] == "Human corrected summary."

    stored_recommendation = db_session.scalar(select(LeadManagerCopilotRecommendation))
    stored_review = db_session.scalar(select(LeadManagerCopilotReview))
    assert stored_recommendation is not None and stored_recommendation.status == "edited"
    assert stored_review is not None
    assert stored_review.original_output["summary"] != stored_review.final_output["summary"]
    assert int(db_session.scalar(select(func.count()).select_from(Task)) or 0) == task_count
    assert (
        int(db_session.scalar(select(func.count()).select_from(Appointment)) or 0)
        == appointment_count
    )
    assert (
        int(db_session.scalar(select(func.count()).select_from(CommunicationRecord)) or 0)
        == communication_count
    )

    copilot = client.get("/api/v1/lead-manager", headers=HEADERS).json()["copilot"]
    assert copilot["metrics"]["generated_count"] == 1
    assert copilot["metrics"]["reviewed_count"] == 1
    assert copilot["metrics"]["edited_count"] == 1
    assert copilot["metrics"]["correction_rate_basis_points"] == 10000
    assert copilot["metrics"]["estimated_time_saved_minutes"] == 4
