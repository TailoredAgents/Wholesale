from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.integrations.openai_client import OpenAITextResponse
from app.main import app
from app.models.foundation import (
    AiAgentDefinition,
    AiPromptVersion,
    AiRunLog,
    AiToolCallLog,
    AiToolPermission,
    ApprovalRequest,
    AuditEvent,
    Lead,
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


def public_payload() -> dict[str, object]:
    return {
        "property_address": "55 Auburn Ave",
        "property_city": "Atlanta",
        "property_state": "GA",
        "property_postal_code": "30303",
        "name": "Sam Seller",
        "phone": "4045551212",
        "email": "sam@example.com",
        "preferred_contact_method": "phone",
        "reason_for_selling": "Inherited property",
        "desired_timeline": "30 days",
        "asking_price": "180000",
        "comments": "Needs repairs",
        "consent_to_contact": True,
        "attribution": {"landing_page": "/get-a-cash-offer"},
    }


def create_public_lead(client: TestClient) -> str:
    response = client.post("/api/v1/public/seller-leads", json=public_payload())
    assert response.status_code == 201
    return str(response.json()["lead_id"])


def test_ai_control_center_logs_run_and_creates_approval(
    db_session: Session,
    api_db_override: None,
) -> None:
    seed_owner(db_session)
    client = TestClient(app)

    agent_response = client.post(
        "/api/v1/ai/agents",
        headers={"X-Dev-User-Email": OWNER_EMAIL},
        json={
            "key": "follow_up_drafter",
            "name": "Follow-up drafter",
            "description": "Drafts seller follow-up messages for human approval.",
            "status": "active",
            "model_name": "gpt-5.6-terra",
            "risk_level": "medium",
            "requires_human_approval": True,
            "tool_permissions": [
                {
                    "tool_key": "communications.draft_sms",
                    "tool_name": "Draft SMS",
                    "permission_level": "draft",
                    "is_enabled": True,
                    "requires_approval": True,
                }
            ],
        },
    )
    agent_id = agent_response.json()["id"]
    prompt_response = client.post(
        f"/api/v1/ai/agents/{agent_id}/prompts",
        headers={"X-Dev-User-Email": OWNER_EMAIL},
        json={
            "status": "active",
            "prompt_text": "Draft concise seller follow-up messages. Do not send anything.",
            "change_notes": "Initial controlled prompt.",
        },
    )
    prompt_id = prompt_response.json()["id"]
    run_response = client.post(
        "/api/v1/ai/runs",
        headers={"X-Dev-User-Email": OWNER_EMAIL},
        json={
            "agent_definition_id": agent_id,
            "prompt_version_id": prompt_id,
            "status": "needs_review",
            "input_summary": "Seller has not responded after first call attempt.",
            "output_summary": "Drafted a short follow-up SMS.",
            "total_tokens": 800,
            "cost_cents": 12,
            "latency_ms": 950,
            "tool_calls": [
                {
                    "tool_key": "communications.draft_sms",
                    "status": "proposed",
                    "requires_approval": True,
                    "input_payload": {"lead_id": "example", "channel": "sms"},
                    "output_payload": {"draft": "Hi Jane, is now still a good time?"},
                }
            ],
        },
    )

    assert agent_response.status_code == 201
    assert prompt_response.status_code == 201
    assert prompt_response.json()["version_number"] == 1
    assert run_response.status_code == 201
    run_payload = run_response.json()
    assert run_payload["tool_calls"][0]["status"] == "pending_approval"
    assert run_payload["tool_calls"][0]["approval_request_id"] is not None
    assert int(db_session.scalar(select(func.count()).select_from(AiAgentDefinition)) or 0) == 1
    assert int(db_session.scalar(select(func.count()).select_from(AiPromptVersion)) or 0) == 1
    assert int(db_session.scalar(select(func.count()).select_from(AiToolPermission)) or 0) == 1
    assert int(db_session.scalar(select(func.count()).select_from(AiRunLog)) or 0) == 1
    assert int(db_session.scalar(select(func.count()).select_from(AiToolCallLog)) or 0) == 1
    assert int(db_session.scalar(select(func.count()).select_from(ApprovalRequest)) or 0) == 1

    overview_response = client.get("/api/v1/ai", headers={"X-Dev-User-Email": OWNER_EMAIL})
    approval_response = client.get(
        "/api/v1/approvals",
        headers={"X-Dev-User-Email": OWNER_EMAIL},
    )
    approval_id = approval_response.json()["items"][0]["id"]
    decision_response = client.patch(
        f"/api/v1/approvals/{approval_id}/decision",
        headers={"X-Dev-User-Email": OWNER_EMAIL},
        json={"status": "approved", "decision_notes": "Draft is safe to use."},
    )

    assert overview_response.status_code == 200
    assert overview_response.json()["summary"]["pending_approval_count"] == 1
    assert overview_response.json()["summary"]["total_cost_cents"] == 12
    assert overview_response.json()["summary"]["total_cost_microusd"] == 120_000
    assert approval_response.status_code == 200
    assert approval_response.json()["items"][0]["request_type"] == "ai_tool_call"
    assert decision_response.status_code == 200
    assert decision_response.json()["status"] == "approved"
    assert int(
        db_session.scalar(
            select(func.count()).select_from(AuditEvent).where(
                AuditEvent.action.in_(
                    [
                        "ai.agent_create",
                        "ai.prompt_version_create",
                        "ai.run_log_create",
                        "approval.decide",
                    ]
                )
            )
        )
        or 0
    ) == 4


def test_ai_run_rejects_unconfigured_tool(
    db_session: Session,
    api_db_override: None,
) -> None:
    seed_owner(db_session)
    client = TestClient(app)
    agent_response = client.post(
        "/api/v1/ai/agents",
        headers={"X-Dev-User-Email": OWNER_EMAIL},
        json={
            "key": "compliance_monitor",
            "name": "Compliance monitor",
            "description": "Checks consent and approval requirements.",
            "status": "active",
            "risk_level": "low",
            "tool_permissions": [],
        },
    )

    response = client.post(
        "/api/v1/ai/runs",
        headers={"X-Dev-User-Email": OWNER_EMAIL},
        json={
            "agent_definition_id": agent_response.json()["id"],
            "status": "needs_review",
            "input_summary": "Review this lead.",
            "tool_calls": [{"tool_key": "communications.send_sms"}],
        },
    )

    assert agent_response.status_code == 201
    assert response.status_code == 422


def test_lead_intake_summary_logs_failed_run_when_openai_key_missing(
    db_session: Session,
    api_db_override: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seed_owner(db_session)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    get_settings.cache_clear()
    client = TestClient(app)
    lead_id = create_public_lead(client)

    response = client.post(
        "/api/v1/ai/lead-intake-summary",
        headers={"X-Dev-User-Email": OWNER_EMAIL},
        json={"lead_id": lead_id},
    )

    assert response.status_code == 201
    payload = response.json()
    assert payload["status"] == "failed"
    assert payload["error_message"] == "OPENAI_API_KEY is not configured."
    assert payload["lead_id"] == lead_id
    assert int(db_session.scalar(select(func.count()).select_from(AiAgentDefinition)) or 0) == 1
    assert int(db_session.scalar(select(func.count()).select_from(AiPromptVersion)) or 0) == 1
    assert int(db_session.scalar(select(func.count()).select_from(AiRunLog)) or 0) == 1
    get_settings.cache_clear()


def test_lead_intake_summary_calls_openai_and_logs_review_run(
    db_session: Session,
    api_db_override: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seed_owner(db_session)
    monkeypatch.setenv("OPENAI_API_KEY", "test-openai-key")
    get_settings.cache_clear()

    class FakeOpenAIResponsesClient:
        def __init__(self, **_: object) -> None:
            pass

        def create_text_response(self, **kwargs: object) -> OpenAITextResponse:
            assert kwargs["model"] == "gpt-5.6-terra"
            assert "Inherited property" in str(kwargs["user_prompt"])
            assert kwargs["reasoning_effort"] == "medium"
            assert kwargs["enable_web_search"] is False
            return OpenAITextResponse(
                text=(
                    "Seller inherited the property, wants a 30 day sale, "
                    "and needs repair context."
                ),
                total_tokens=321,
                input_tokens=200,
                output_tokens=121,
            )

    monkeypatch.setattr("app.services.ai.OpenAIResponsesClient", FakeOpenAIResponsesClient)
    client = TestClient(app)
    lead_id = create_public_lead(client)

    response = client.post(
        "/api/v1/ai/lead-intake-summary",
        headers={"X-Dev-User-Email": OWNER_EMAIL},
        json={"lead_id": lead_id},
    )

    assert response.status_code == 201
    payload = response.json()
    assert payload["status"] == "needs_review"
    assert payload["total_tokens"] == 321
    assert payload["input_tokens"] == 200
    assert payload["output_tokens"] == 121
    assert payload["cost_microusd"] == 2315
    assert payload["run_metadata"]["pricing_status"] == "priced"
    assert "inherited" in payload["output_summary"].lower()
    assert payload["lead_id"] == lead_id
    assert db_session.scalar(select(Lead).where(Lead.id == UUID(lead_id))) is not None
    get_settings.cache_clear()
