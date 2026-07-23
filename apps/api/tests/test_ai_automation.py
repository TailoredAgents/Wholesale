from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.main import app
from app.models.foundation import (
    AiExternalActionAttempt,
    AiExternalActionPolicy,
    AuditEvent,
)
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


def test_ai10_external_action_controls_are_idempotent_audited_and_delivery_locked(
    db_session: Session,
    api_db_override: None,
) -> None:
    seed_owner(db_session)
    client = TestClient(app)
    assert (
        client.post("/api/v1/ai/orchestrator/portfolio/install", headers=HEADERS).status_code
        == 201
    )
    assert client.post("/api/v1/ai/copilots/install", headers=HEADERS).status_code == 201
    assert (
        client.post("/api/v1/ai/runtime/install", headers=HEADERS).status_code
        == 201
    )

    first = client.post("/api/v1/ai/automation/install", headers=HEADERS)
    second = client.post("/api/v1/ai/automation/install", headers=HEADERS)

    assert first.status_code == 201
    assert first.json()["created_policy_count"] == 4
    assert second.json()["created_policy_count"] == 0
    assert second.json()["existing_policy_count"] == 4

    overview = client.get("/api/v1/ai", headers=HEADERS).json()
    automation = overview["orchestrator"]["automation"]
    assert automation["phase_status"] == "control_plane_only"
    assert automation["external_delivery_globally_enabled"] is False
    assert automation["metrics"]["policy_count"] == 4
    assert automation["metrics"]["external_delivery_enabled_count"] == 0
    assert automation["metrics"]["external_delivery_attempt_count"] == 0
    assert automation["metrics"]["delivered_message_count"] == 0
    assert {item["action_key"] for item in automation["policies"]} == {
        "seller_acknowledgement.sms",
        "appointment_reminder.sms",
        "seller_follow_up.sms",
        "buyer_campaign.email",
    }
    assert all(item["dry_run_only"] for item in automation["policies"])
    assert all(not item["external_delivery_enabled"] for item in automation["policies"])

    policy = next(
        item
        for item in automation["policies"]
        if item["action_key"] == "seller_acknowledgement.sms"
    )
    decision = client.post(
        f"/api/v1/ai/automation/policies/{policy['id']}/decision",
        headers=HEADERS,
        json={
            "decision": "approve_control",
            "notes": "Approve this simulation contract without external delivery.",
        },
    )
    assert decision.status_code == 200
    assert decision.json()["status"] == "control_approved"
    assert decision.json()["approved_at"] is not None
    assert decision.json()["external_delivery_enabled"] is False

    simulation_payload = {
        "idempotency_key": "ai10:seller-ack:simulation-1",
        "audience_count": 1,
        "estimated_cost_microusd": 10_000,
        "consent_verified": True,
        "template_approved": True,
        "within_contact_hours": True,
        "frequency_allowed": True,
        "suppression_checked": True,
        "human_takeover_ready": True,
    }
    simulation = client.post(
        f"/api/v1/ai/automation/policies/{policy['id']}/simulations",
        headers=HEADERS,
        json=simulation_payload,
    )
    duplicate = client.post(
        f"/api/v1/ai/automation/policies/{policy['id']}/simulations",
        headers=HEADERS,
        json=simulation_payload,
    )
    assert simulation.status_code == 201
    assert simulation.json()["status"] == "blocked"
    assert duplicate.json()["id"] == simulation.json()["id"]
    assert simulation.json()["external_delivery_attempted"] is False
    assert simulation.json()["delivered_count"] == 0
    assert "External delivery is locked by the AI10 control-plane release." in (
        simulation.json()["block_reasons"]
    )

    paused = client.post(
        f"/api/v1/ai/automation/policies/{policy['id']}/pause",
        headers=HEADERS,
        json={"reason": "Owner pause test."},
    )
    assert paused.status_code == 200
    assert paused.json()["status"] == "paused"
    resumed = client.post(
        f"/api/v1/ai/automation/policies/{policy['id']}/resume-control",
        headers=HEADERS,
    )
    assert resumed.status_code == 200
    assert resumed.json()["status"] == "control_approved"
    assert resumed.json()["external_delivery_enabled"] is False

    assert (
        db_session.scalar(select(func.count(AiExternalActionPolicy.id)))
        == 4
    )
    assert (
        db_session.scalar(select(func.count(AiExternalActionAttempt.id)))
        == 1
    )
    attempt = db_session.scalar(select(AiExternalActionAttempt))
    assert attempt is not None
    assert attempt.external_delivery_attempted is False
    assert attempt.delivered_count == 0
    assert (
        db_session.scalar(
            select(func.count(AuditEvent.id)).where(
                AuditEvent.action == "ai.external_action.simulate"
            )
        )
        == 1
    )
