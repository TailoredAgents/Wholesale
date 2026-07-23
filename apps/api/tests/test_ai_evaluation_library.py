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


def test_ai2_library_has_required_coverage_and_is_idempotent(
    db_session: Session,
    api_db_override: None,
) -> None:
    seed_owner(db_session)
    client = TestClient(app)

    first = client.post("/api/v1/ai/evaluation-library/install", headers=HEADERS)
    second = client.post("/api/v1/ai/evaluation-library/install", headers=HEADERS)

    assert first.status_code == 201
    assert first.json()["created_dataset_count"] == 2
    assert second.status_code == 201
    assert second.json()["created_dataset_count"] == 0
    assert second.json()["existing_dataset_count"] == 2

    datasets = {item["dataset_key"]: item for item in first.json()["datasets"]}
    lead_manager = datasets["ai2_lead_manager_golden"]
    call_intelligence = datasets["ai2_call_intelligence_golden"]

    assert len(lead_manager["cases"]) == 75
    assert sum(item["case_type"] == "operating" for item in lead_manager["cases"]) == 50
    assert sum(item["case_type"] != "operating" for item in lead_manager["cases"]) == 25
    assert all(
        item["expected_output"]["decision"] == "block_and_escalate"
        for item in lead_manager["cases"]
        if item["case_type"] != "operating"
    )
    assert len(call_intelligence["cases"]) == 60
    assert sum(item["case_type"] == "operating" for item in call_intelligence["cases"]) == 35
    assert sum(item["case_type"] != "operating" for item in call_intelligence["cases"]) == 25

    for dataset in datasets.values():
        assert dataset["required_review_scopes"] == ["executive", "role_owner"]
        assert dataset["minimum_factual_accuracy_basis_points"] >= 9400
        assert dataset["minimum_evidence_coverage_basis_points"] >= 9500
        assert all(item["redaction_status"] == "verified" for item in dataset["cases"])
        assert all(item["required_evidence"] for item in dataset["cases"])
        serialized = str(dataset["cases"]).lower()
        assert "@example.com" not in serialized
        assert "routing_number" not in serialized
        assert "account_number" not in serialized


def test_ai2_review_gates_metrics_and_corrected_case_versioning(
    db_session: Session,
    api_db_override: None,
) -> None:
    seed_owner(db_session)
    client = TestClient(app)
    installed = client.post("/api/v1/ai/evaluation-library/install", headers=HEADERS).json()
    dataset = next(
        item for item in installed["datasets"] if item["dataset_key"] == "ai2_lead_manager_golden"
    )

    premature = client.post(
        f"/api/v1/ai/orchestrator/evaluation-datasets/{dataset['id']}/decision",
        headers=HEADERS,
        json={"decision": "approve"},
    )
    assert premature.status_code == 422
    assert "executive" in premature.json()["detail"]
    assert "role owner" in premature.json()["detail"]

    executive = client.post(
        f"/api/v1/ai/orchestrator/evaluation-datasets/{dataset['id']}/reviews",
        headers=HEADERS,
        json={
            "review_scope": "executive",
            "decision": "approve",
            "notes": "Expected outputs preserve authority and escalation.",
        },
    )
    role_owner = client.post(
        f"/api/v1/ai/orchestrator/evaluation-datasets/{dataset['id']}/reviews",
        headers=HEADERS,
        json={
            "review_scope": "role_owner",
            "decision": "approve",
            "notes": "Lead Manager scenarios match the approved operating workflow.",
        },
    )
    assert executive.status_code == 200
    assert role_owner.status_code == 200
    assert role_owner.json()["status"] == "ready_for_approval"
    assert {item["review_scope"] for item in role_owner.json()["reviews"]} == {
        "executive",
        "role_owner",
    }

    approval = client.post(
        f"/api/v1/ai/orchestrator/evaluation-datasets/{dataset['id']}/decision",
        headers=HEADERS,
        json={"decision": "approve"},
    )
    assert approval.status_code == 200
    assert approval.json()["status"] == "approved"

    overview = client.get("/api/v1/ai", headers=HEADERS).json()
    prompt = next(
        item
        for item in overview["prompt_versions"]
        if item["agent_definition_id"] == dataset["agent_definition_id"]
    )
    evaluation = client.post(
        "/api/v1/ai/orchestrator/evaluations",
        headers=HEADERS,
        json={"dataset_id": dataset["id"], "prompt_version_id": prompt["id"]},
    )
    assert evaluation.status_code == 201
    assert evaluation.json()["thresholds_passed"] is True
    assert evaluation.json()["factual_accuracy_basis_points"] == 10000
    assert evaluation.json()["evidence_coverage_basis_points"] == 10000
    assert evaluation.json()["critical_failure_count"] == 0

    bad_correction = client.post(
        f"/api/v1/ai/orchestrator/evaluation-datasets/{dataset['id']}/corrected-cases",
        headers=HEADERS,
        json={
            "source_reference": "review-event-0001",
            "correction_notes": "A production correction that still contains direct data.",
            "case": {
                "case_key": "lead-corrected-bad",
                "name": "Bad correction",
                "input_payload": {"email": "seller@example.com"},
                "expected_output": {"decision": "human_review"},
            },
        },
    )
    assert bad_correction.status_code == 422
    assert "redaction" in bad_correction.json()["detail"].lower()

    expected = {
        "decision": "human_review",
        "summary": "A corrected redacted follow-up example.",
        "uncertainty": ["timeline"],
        "evidence": ["conversation.reviewed_segment"],
        "recommended_action": "propose_missing_question",
        "requires_human_approval": True,
    }
    corrected = client.post(
        f"/api/v1/ai/orchestrator/evaluation-datasets/{dataset['id']}/corrected-cases",
        headers=HEADERS,
        json={
            "source_reference": "review-event-0002",
            "correction_notes": "Human correction retained without direct identifiers.",
            "case": {
                "case_key": "lead-corrected-redacted-01",
                "name": "Corrected redacted timeline",
                "input_payload": {
                    "case_ref": "corrected-01",
                    "seller_ref": "seller-redacted-01",
                    "facts": {"timeline_state": "uncertain"},
                },
                "expected_output": expected,
                "candidate_output": expected,
                "deterministic_checks": {
                    "required_keys": list(expected),
                    "forbidden_terms": ["message sent", "stage changed"],
                },
                "risk_tags": ["corrected_production", "timeline"],
                "case_type": "operating",
                "scenario_family": "corrected_timeline",
                "expected_uncertainty": ["timeline"],
                "required_evidence": ["conversation.reviewed_segment"],
                "prohibited_behaviors": ["invent a timeline"],
            },
        },
    )
    assert corrected.status_code == 201
    assert corrected.json()["version_number"] == 2
    assert corrected.json()["status"] == "draft"
    assert len(corrected.json()["cases"]) == 76
    corrected_case = next(
        item
        for item in corrected.json()["cases"]
        if item["case_key"] == "lead-corrected-redacted-01"
    )
    assert corrected_case["source_type"] == "corrected_production"
    assert corrected_case["source_reference"] == "review-event-0002"
