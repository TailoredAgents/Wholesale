from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.main import app
from app.models.foundation import (
    AiAgentDefinition,
    AiPromptVersion,
    AiRunLog,
    AiToolCallLog,
    AiToolPermission,
    ApprovalRequest,
    AuditEvent,
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
            "model_name": "gpt-4.1-mini",
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
