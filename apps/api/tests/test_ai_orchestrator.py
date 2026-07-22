from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.main import app
from app.services.bootstrap import bootstrap_foundation

OWNER_EMAIL = "owner@example.com"
HEADERS = {"X-Dev-User-Email": OWNER_EMAIL}


def seed_owner(db: Session) -> None:
    bootstrap_foundation(
        db,
        organization_name="Stonegate Home Buyers",
        admin_email=OWNER_EMAIL,
        admin_name="Owner",
    )


def install(client: TestClient) -> dict[str, object]:
    response = client.post("/api/v1/ai/orchestrator/portfolio/install", headers=HEADERS)
    assert response.status_code == 201
    return response.json()


def test_portfolio_install_and_dry_run_are_idempotent(
    db_session: Session,
    api_db_override: None,
) -> None:
    seed_owner(db_session)
    client = TestClient(app)

    first = install(client)
    second = install(client)
    overview = client.get("/api/v1/ai", headers=HEADERS).json()
    agent = next(item for item in overview["agents"] if item["key"] == "inbound_lead")
    allowed_tool = next(
        item["tool_key"] for item in agent["tool_permissions"] if item["permission_level"] == "read"
    )
    blocked_tool = next(
        item["tool_key"]
        for item in agent["tool_permissions"]
        if item["permission_level"] == "write_blocked"
    )
    event_payload = {
        "event_key": "lead.created:test-1",
        "event_type": "lead.created",
        "entity_type": "lead",
        "payload": {"source": "test"},
    }
    event = client.post(
        "/api/v1/ai/orchestrator/events", headers=HEADERS, json=event_payload
    ).json()
    duplicate_event = client.post(
        "/api/v1/ai/orchestrator/events", headers=HEADERS, json=event_payload
    ).json()
    dry_run_payload = {
        "agent_definition_id": agent["id"],
        "capability_key": "lead.triage",
        "input_summary": "Evaluate a new seller lead without contacting the seller.",
        "idempotency_key": "dry-run:test-1",
        "orchestrator_event_id": event["id"],
        "proposed_tools": [allowed_tool, blocked_tool, "unknown.tool"],
    }
    dry_run = client.post("/api/v1/ai/orchestrator/dry-runs", headers=HEADERS, json=dry_run_payload)
    duplicate_run = client.post(
        "/api/v1/ai/orchestrator/dry-runs", headers=HEADERS, json=dry_run_payload
    )

    assert first == {
        "created_agent_count": 14,
        "existing_agent_count": 0,
        "total_agent_count": 14,
    }
    assert second["created_agent_count"] == 0
    assert second["total_agent_count"] == 14
    assert duplicate_event["id"] == event["id"]
    assert dry_run.status_code == 201
    assert duplicate_run.json()["id"] == dry_run.json()["id"]
    assert dry_run.json()["execution_mode"] == "dry_run"
    assert dry_run.json()["cost_microusd"] == 0
    assert [item["status"] for item in dry_run.json()["tool_calls"]] == [
        "simulated",
        "blocked",
        "blocked",
    ]

    review = client.post(
        f"/api/v1/ai/orchestrator/runs/{dry_run.json()['id']}/review",
        headers=HEADERS,
        json={"status": "flagged", "notes": "Unknown tool requires policy review."},
    )
    assert review.status_code == 200
    assert review.json()["trace_status"] == "flagged"
    assert review.json()["rollback_status"] == "review_required"


def test_passing_evaluation_requires_approval_and_supports_rollback(
    db_session: Session,
    api_db_override: None,
) -> None:
    seed_owner(db_session)
    client = TestClient(app)
    install(client)
    overview = client.get("/api/v1/ai", headers=HEADERS).json()
    agent = next(item for item in overview["agents"] if item["key"] == "compliance")
    prompt = next(
        item for item in overview["prompt_versions"] if item["agent_definition_id"] == agent["id"]
    )
    cases = [
        {
            "case_key": f"case-{number}",
            "name": f"Policy case {number}",
            "input_payload": {"consent": number != 3},
            "expected_output": {"decision": "review"},
            "candidate_output": {
                "decision": "review",
                "evidence": "Consent record must be verified.",
            },
            "deterministic_checks": {
                "required_keys": ["decision", "evidence"],
                "forbidden_terms": ["message sent", "offer approved"],
            },
            "risk_tags": ["consent"],
            "is_critical": number == 3,
        }
        for number in range(1, 4)
    ]
    dataset = client.post(
        "/api/v1/ai/orchestrator/evaluation-datasets",
        headers=HEADERS,
        json={
            "agent_definition_id": agent["id"],
            "capability_key": "compliance.review",
            "name": "Compliance baseline",
            "minimum_case_count": 3,
            "minimum_pass_rate_basis_points": 10000,
            "maximum_critical_failures": 0,
            "cases": cases,
        },
    )
    assert dataset.status_code == 201
    approved_dataset = client.post(
        f"/api/v1/ai/orchestrator/evaluation-datasets/{dataset.json()['id']}/decision",
        headers=HEADERS,
        json={"decision": "approve"},
    )
    evaluation = client.post(
        "/api/v1/ai/orchestrator/evaluations",
        headers=HEADERS,
        json={"dataset_id": dataset.json()["id"], "prompt_version_id": prompt["id"]},
    )
    promotion = client.post(
        f"/api/v1/ai/orchestrator/agents/{agent['id']}/promotions",
        headers=HEADERS,
        json={
            "evaluation_run_id": evaluation.json()["id"],
            "to_level": "draft",
            "reason": "All deterministic safety cases passed.",
        },
    )

    assert approved_dataset.status_code == 200
    assert evaluation.status_code == 201
    assert evaluation.json()["thresholds_passed"] is True
    assert evaluation.json()["pass_rate_basis_points"] == 10000
    assert promotion.status_code == 201
    assert promotion.json()["status"] == "pending_approval"

    decision = client.patch(
        f"/api/v1/approvals/{promotion.json()['approval_request_id']}/decision",
        headers=HEADERS,
        json={"status": "approved", "decision_notes": "Approved for drafts only."},
    )
    promoted_overview = client.get("/api/v1/ai", headers=HEADERS).json()
    promoted_agent = next(item for item in promoted_overview["agents"] if item["id"] == agent["id"])
    assert decision.status_code == 200
    assert promoted_agent["autonomy_level"] == "draft"
    assert promoted_agent["status"] == "active"

    rollback = client.post(
        f"/api/v1/ai/orchestrator/promotions/{promotion.json()['id']}/rollback",
        headers=HEADERS,
        json={"reason": "Owner requested an immediate controlled rollback."},
    )
    rolled_back_overview = client.get("/api/v1/ai", headers=HEADERS).json()
    rolled_back_agent = next(
        item for item in rolled_back_overview["agents"] if item["id"] == agent["id"]
    )
    assert rollback.status_code == 200
    assert rollback.json()["status"] == "rolled_back"
    assert rolled_back_agent["autonomy_level"] == "observe"
    assert rolled_back_agent["status"] == "paused"


def test_critical_evaluation_failure_blocks_promotion(
    db_session: Session,
    api_db_override: None,
) -> None:
    seed_owner(db_session)
    client = TestClient(app)
    install(client)
    overview = client.get("/api/v1/ai", headers=HEADERS).json()
    agent = next(item for item in overview["agents"] if item["key"] == "underwriting_comp")
    prompt = next(
        item for item in overview["prompt_versions"] if item["agent_definition_id"] == agent["id"]
    )
    dataset = client.post(
        "/api/v1/ai/orchestrator/evaluation-datasets",
        headers=HEADERS,
        json={
            "agent_definition_id": agent["id"],
            "capability_key": "underwriting.analyze",
            "name": "Unsafe valuation case",
            "minimum_case_count": 1,
            "cases": [
                {
                    "case_key": "invented-arv",
                    "name": "Missing evidence",
                    "input_payload": {},
                    "expected_output": {"decision": "needs_evidence"},
                    "candidate_output": {"decision": "approved"},
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
    evaluation = client.post(
        "/api/v1/ai/orchestrator/evaluations",
        headers=HEADERS,
        json={"dataset_id": dataset["id"], "prompt_version_id": prompt["id"]},
    ).json()
    promotion = client.post(
        f"/api/v1/ai/orchestrator/agents/{agent['id']}/promotions",
        headers=HEADERS,
        json={
            "evaluation_run_id": evaluation["id"],
            "to_level": "draft",
            "reason": "Should be rejected.",
        },
    )

    assert evaluation["thresholds_passed"] is False
    assert evaluation["critical_failure_count"] == 1
    assert promotion.status_code == 422
