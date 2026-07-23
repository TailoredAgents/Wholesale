import json
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.main import app
from app.models.foundation import (
    AiEvaluationRun,
    AiKnowledgeUseLog,
    AiRunLog,
)
from app.services.ai_runtime import _scope_lead_context
from app.services.bootstrap import bootstrap_foundation

OWNER_EMAIL = "owner@example.com"
HEADERS = {"X-Dev-User-Email": OWNER_EMAIL}


def test_runtime_lead_context_is_field_scoped_by_capability() -> None:
    source = {
        "lead": {"stage": "qualified", "motivation": "Relocating", "id": "private-id"},
        "seller": {
            "preferred_name": "Taylor",
            "contact_methods": [{"type": "phone", "value": "404-555-1212"}],
        },
        "property": {
            "street_address": "100 Main Street",
            "city": "Atlanta",
            "state": "GA",
        },
        "latest_form_submission": {"private": "raw payload"},
    }

    lead_scope = _scope_lead_context("lead.next_action", source)
    underwriting_scope = _scope_lead_context("underwriting.analyze", source)

    assert "contact_methods" not in lead_scope["seller"]
    assert "latest_form_submission" not in lead_scope
    assert "street_address" not in lead_scope["property"]
    assert underwriting_scope["property"]["street_address"] == "100 Main Street"


def seed_owner(db: Session) -> None:
    bootstrap_foundation(
        db,
        organization_name="Stonegate Home Buyers",
        admin_email=OWNER_EMAIL,
        admin_name="Owner",
    )


def install_ai_foundation(client: TestClient) -> dict[str, object]:
    assert client.post(
        "/api/v1/ai/orchestrator/portfolio/install", headers=HEADERS
    ).status_code == 201
    assert client.post("/api/v1/ai/copilots/install", headers=HEADERS).status_code == 201
    assert client.post(
        "/api/v1/ai/copilots/foundation/decision",
        headers=HEADERS,
        json={"decision": "approve", "notes": "Approved for governed runtime tests."},
    ).status_code == 200
    response = client.post("/api/v1/ai/runtime/install", headers=HEADERS)
    assert response.status_code == 201
    return response.json()


def test_runtime_is_disabled_by_default_and_shutdown_is_global(
    db_session: Session,
    api_db_override: None,
) -> None:
    seed_owner(db_session)
    client = TestClient(app)
    first = install_ai_foundation(client)
    second = client.post("/api/v1/ai/runtime/install", headers=HEADERS).json()

    assert first["created_runtime_policy"] is True
    assert first["created_capability_policy_count"] == 14
    assert first["runtime"]["status"] == "disabled"
    assert first["runtime"]["policy"]["external_actions_enabled"] is False
    assert second["created_runtime_policy"] is False
    assert second["created_capability_policy_count"] == 0

    capability = first["runtime"]["capabilities"][0]
    blocked = client.post(
        "/api/v1/ai/runtime/execute",
        headers=HEADERS,
        json={
            "agent_definition_id": capability["agent_definition_id"],
            "capability_key": capability["capability_key"],
            "idempotency_key": "runtime:disabled:1",
            "input_payload": {"question": "What should happen next?"},
        },
    )
    duplicate = client.post(
        "/api/v1/ai/runtime/execute",
        headers=HEADERS,
        json={
            "agent_definition_id": capability["agent_definition_id"],
            "capability_key": capability["capability_key"],
            "idempotency_key": "runtime:disabled:1",
            "input_payload": {"question": "This duplicate cannot create another run."},
        },
    )
    assert blocked.status_code == 201
    assert blocked.json()["status"] == "blocked"
    assert duplicate.json()["id"] == blocked.json()["id"]

    assert client.patch(
        "/api/v1/ai/runtime/policy",
        headers=HEADERS,
        json={"provider_status": "enabled"},
    ).status_code == 200
    assert client.patch(
        f"/api/v1/ai/runtime/capabilities/{capability['capability_key']}",
        headers=HEADERS,
        json={"status": "enabled"},
    ).status_code == 200
    shutdown = client.post(
        "/api/v1/ai/runtime/shutdown",
        headers=HEADERS,
        json={"reason": "Owner emergency stop test."},
    )
    assert shutdown.status_code == 200
    assert shutdown.json()["status"] == "emergency_stopped"
    assert shutdown.json()["metrics"]["enabled_capability_count"] == 0


def test_production_runtime_is_structured_scoped_redacted_and_idempotent(
    db_session: Session,
    api_db_override: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seed_owner(db_session)
    client = TestClient(app)
    installed = install_ai_foundation(client)
    capability = next(
        item
        for item in installed["runtime"]["capabilities"]
        if item["capability_key"] == "lead.next_action"
    )
    monkeypatch.setenv("OPENAI_API_KEY", "test-openai-key")
    get_settings.cache_clear()

    class FakeOpenAIResponsesClient:
        def __init__(self, **_: object) -> None:
            pass

        def create_structured_response(self, **kwargs: object):
            schema = kwargs["json_schema"]
            assert isinstance(schema, dict)
            assert schema["additionalProperties"] is False
            assert kwargs["model"] == "gpt-5.6-sol"
            assert len(str(kwargs["safety_identifier"])) == 64
            assert str(kwargs["prompt_cache_key"]).startswith("stonegate:lead_management:")
            return (
                {
                    "summary": "Human review is required before follow-up.",
                    "recommended_actions": [
                        {
                            "action": "Review qualification gaps",
                            "reason": "The supplied facts are incomplete.",
                            "confidence": 82,
                            "evidence": ["request.stage"],
                            "requires_human_approval": True,
                        }
                    ],
                    "risks": [],
                    "uncertainties": ["seller timeline"],
                    "knowledge_citations": [],
                },
                {"input_tokens": 100, "output_tokens": 50, "total_tokens": 150},
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

    request = {
        "agent_definition_id": capability["agent_definition_id"],
        "capability_key": "lead.next_action",
        "idempotency_key": "runtime:lead-next-action:1",
        "input_payload": {
            "stage": "qualified",
            "seller_email": "seller@example.com",
            "seller_phone": "404-555-1212",
        },
    }
    first = client.post(
        "/api/v1/ai/runtime/execute", headers=HEADERS, json=request
    )
    second = client.post(
        "/api/v1/ai/runtime/execute", headers=HEADERS, json=request
    )

    assert first.status_code == 201
    result = first.json()
    assert result["status"] == "needs_review"
    assert result["execution_mode"] == "production"
    assert result["model_name"] == "gpt-5.6-sol"
    assert result["tool_calls"][0]["tool_key"] == "lead.next_action.read"
    assert result["tool_calls"][0]["status"] == "completed"
    assert "seller@example.com" not in result["input_summary"]
    assert "404-555-1212" not in result["input_summary"]
    assert "[REDACTED]" in result["input_summary"]
    assert second.json()["id"] == result["id"]
    assert db_session.scalar(
        select(func.count(AiRunLog.id)).where(
            AiRunLog.idempotency_key == "runtime:lead-next-action:1"
        )
    ) == 1
    assert (
        db_session.scalar(
            select(func.count(AiKnowledgeUseLog.id)).where(
                AiKnowledgeUseLog.ai_run_log_id == UUID(result["id"])
            )
        )
        or 0
    ) >= 1
    get_settings.cache_clear()


def test_same_dataset_comparison_blocks_a_regression(
    db_session: Session,
    api_db_override: None,
) -> None:
    seed_owner(db_session)
    client = TestClient(app)
    install_ai_foundation(client)
    overview = client.get("/api/v1/ai", headers=HEADERS).json()
    agent = next(item for item in overview["agents"] if item["key"] == "compliance")
    prompt = next(
        item
        for item in overview["prompt_versions"]
        if item["agent_definition_id"] == agent["id"]
    )
    dataset = client.post(
        "/api/v1/ai/orchestrator/evaluation-datasets",
        headers=HEADERS,
        json={
            "agent_definition_id": agent["id"],
            "capability_key": "compliance.review",
            "name": "Runtime comparison baseline",
            "minimum_case_count": 1,
            "cases": [
                {
                    "case_key": "consent-check",
                    "name": "Consent check",
                    "input_payload": {"consent": "unknown"},
                    "expected_output": {"decision": "human_review"},
                    "candidate_output": {
                        "decision": "human_review",
                        "evidence": "Consent must be verified.",
                    },
                    "deterministic_checks": {
                        "required_keys": ["decision", "evidence"],
                    },
                    "is_critical": True,
                }
            ],
        },
    ).json()
    client.post(
        f"/api/v1/ai/orchestrator/evaluation-datasets/{dataset['id']}/decision",
        headers=HEADERS,
        json={"decision": "approve"},
    )
    baseline = client.post(
        "/api/v1/ai/orchestrator/evaluations",
        headers=HEADERS,
        json={"dataset_id": dataset["id"], "prompt_version_id": prompt["id"]},
    ).json()
    challenger = client.post(
        "/api/v1/ai/orchestrator/evaluations",
        headers=HEADERS,
        json={"dataset_id": dataset["id"], "prompt_version_id": prompt["id"]},
    ).json()
    challenger_model = db_session.get(AiEvaluationRun, UUID(challenger["id"]))
    assert challenger_model is not None
    challenger_model.thresholds_passed = False
    challenger_model.pass_rate_basis_points = 9000
    challenger_model.critical_failure_count = 1
    db_session.commit()

    comparison = client.post(
        "/api/v1/ai/runtime/evaluation-comparisons",
        headers=HEADERS,
        json={
            "baseline_evaluation_run_id": baseline["id"],
            "challenger_evaluation_run_id": challenger["id"],
        },
    )
    assert comparison.status_code == 201
    result = comparison.json()
    assert result["regression_blocked"] is True
    assert result["status"] == "blocked"
    assert "challenger_failed_dataset_thresholds" in json.dumps(result["summary"])
