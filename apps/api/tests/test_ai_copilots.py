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


def test_ai1_foundation_is_complete_idempotent_and_human_owned(
    db_session: Session,
    api_db_override: None,
) -> None:
    seed_owner(db_session)
    client = TestClient(app)

    first = client.post("/api/v1/ai/copilots/install", headers=HEADERS)
    second = client.post("/api/v1/ai/copilots/install", headers=HEADERS)

    assert first.status_code == 201
    assert first.json()["created_copilot_count"] == 8
    assert first.json()["created_contract_count"] == 14
    assert first.json()["created_policy_count"] == 7
    assert first.json()["created_knowledge_source_count"] == 6
    assert first.json()["created_data_quality_rule_count"] == 6
    assert first.json()["foundation"]["status"] == "draft"

    assert second.status_code == 201
    assert second.json()["created_copilot_count"] == 0
    assert second.json()["created_mapping_count"] == 0
    assert second.json()["created_contract_count"] == 0
    assert second.json()["created_policy_count"] == 0
    assert second.json()["created_knowledge_source_count"] == 0
    assert second.json()["created_data_quality_rule_count"] == 0

    foundation = first.json()["foundation"]
    assert len({item["key"] for item in foundation["copilots"]}) == 8
    lead_manager = next(
        item for item in foundation["copilots"] if item["key"] == "lead_manager_copilot"
    )
    assert lead_manager["human_owner_title"] == "Lead Manager"
    assert "human Lead Manager owns" in lead_manager["human_authority_summary"]
    assert {item["agent_key"] for item in lead_manager["specialist_mappings"]} == {
        "inbound_lead",
        "lead_management",
        "call_intelligence",
        "compliance",
    }
    next_action = next(
        item
        for item in lead_manager["capability_contracts"]
        if item["capability_key"] == "lead.next_action"
    )
    assert next_action["approval_policy"]["external_execution_enabled"] is False
    assert "change stage" in next_action["approval_policy"]["human_approval_required_for"]
    assert (
        "Silently qualify, disqualify, or reassign a seller." in next_action["prohibited_actions"]
    )

    seller_policy = next(
        item
        for item in foundation["data_governance_policies"]
        if item["key"] == "seller_identity_contact"
    )
    assert seller_policy["source_precedence"][0] == "human_confirmed"
    assert "cannot be overwritten" in seller_policy["overwrite_policy"]

    legal_source = next(
        item for item in foundation["knowledge_sources"] if item["key"] == "legal_templates"
    )
    assert legal_source["status"] == "pending_external_review"
    assert legal_source["is_authoritative"] is False


def test_owner_can_approve_and_return_ai1_foundation_to_draft(
    db_session: Session,
    api_db_override: None,
) -> None:
    seed_owner(db_session)
    client = TestClient(app)
    client.post("/api/v1/ai/copilots/install", headers=HEADERS)

    approved = client.post(
        "/api/v1/ai/copilots/foundation/decision",
        headers=HEADERS,
        json={"decision": "approve", "notes": "Owner approved the governed AI1 baseline."},
    )

    assert approved.status_code == 200
    assert approved.json()["status"] == "approved"
    assert all(item["status"] == "active" for item in approved.json()["copilots"])
    assert all(
        contract["status"] == "approved"
        for copilot in approved.json()["copilots"]
        for contract in copilot["capability_contracts"]
    )
    assert all(
        item["status"] == "approved"
        for item in approved.json()["knowledge_sources"]
        if item["is_authoritative"]
    )
    legal_source = next(
        item for item in approved.json()["knowledge_sources"] if item["key"] == "legal_templates"
    )
    assert legal_source["status"] == "pending_external_review"

    overview = client.get("/api/v1/ai", headers=HEADERS)
    assert overview.status_code == 200
    assert overview.json()["orchestrator"]["metrics"]["copilot_count"] == 8
    assert overview.json()["orchestrator"]["metrics"]["active_copilot_count"] == 8
    assert overview.json()["orchestrator"]["foundation"]["status"] == "approved"

    returned = client.post(
        "/api/v1/ai/copilots/foundation/decision",
        headers=HEADERS,
        json={"decision": "return_to_draft", "notes": "Revise the owner authority wording."},
    )
    assert returned.status_code == 200
    assert returned.json()["status"] == "draft"
    assert all(item["status"] == "draft" for item in returned.json()["copilots"])
