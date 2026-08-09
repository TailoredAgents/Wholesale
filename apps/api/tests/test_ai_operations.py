from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any
from uuid import UUID, uuid4

from fastapi.testclient import TestClient
from pytest import MonkeyPatch
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.main import app
from app.models.foundation import (
    ActivityEvent,
    AiOrchestratorEvent,
    AiRunLog,
    CommunicationRecord,
    Lead,
)
from app.services.ai_operations import process_next_ai_operation
from tests.test_leads import OWNER_EMAIL, lead_payload, seed_owner

HEADERS = {"X-Dev-User-Email": OWNER_EMAIL}


def install_runtime(client: TestClient) -> None:
    assert (
        client.post("/api/v1/ai/orchestrator/portfolio/install", headers=HEADERS).status_code == 201
    )
    assert client.post("/api/v1/ai/copilots/install", headers=HEADERS).status_code == 201
    assert (
        client.post(
            "/api/v1/ai/copilots/foundation/decision",
            headers=HEADERS,
            json={"decision": "approve", "notes": "Approved for AI operations test."},
        ).status_code
        == 200
    )
    assert client.post("/api/v1/ai/runtime/install", headers=HEADERS).status_code == 201


def test_new_lead_is_prepared_and_reviewed_from_shared_work_queue(
    db_session: Session,
    api_db_override: None,
    monkeypatch: MonkeyPatch,
) -> None:
    seed_owner(db_session)
    monkeypatch.setenv("AI_ENABLED", "true")
    monkeypatch.setenv("OPENAI_API_KEY", "test-openai-key")
    get_settings.cache_clear()
    client = TestClient(app)
    install_runtime(client)

    class FakeOpenAIResponsesClient:
        def __init__(self, **_: object) -> None:
            pass

        def create_structured_response(
            self,
            **_: object,
        ) -> tuple[dict[str, Any], dict[str, int]]:
            return (
                {
                    "summary": "Seller wants a fast close and the property needs repairs.",
                    "priority_explanation": "The seller supplied a short timeline.",
                    "qualification_gaps": ["Confirm repair scope"],
                    "recommended_questions": ["Which repairs are most urgent?"],
                    "message_draft": {"channel": "none", "body": ""},
                    "next_task": {
                        "title": "Confirm seller repair scope",
                        "reason": "Repair details are incomplete.",
                        "due_timing": "today",
                    },
                    "appointment_proposal": {
                        "recommended": False,
                        "reason": "Qualification is incomplete.",
                    },
                    "handoff_summary": "Continue seller qualification.",
                    "risks": [],
                    "evidence": ["lead.desired_timeline", "lead.property_condition"],
                    "confidence": 90,
                },
                {"input_tokens": 100, "output_tokens": 50, "total_tokens": 150},
            )

    monkeypatch.setattr(
        "app.services.ai_runtime.OpenAIResponsesClient",
        FakeOpenAIResponsesClient,
    )
    created_response = client.post("/api/v1/leads", headers=HEADERS, json=lead_payload())
    assert created_response.status_code == 201, created_response.text
    lead_id = created_response.json()["id"]

    event = db_session.scalar(select(AiOrchestratorEvent))
    assert event is not None
    assert event.event_key == f"lead.created:{lead_id}"
    assert event.status == "queued"

    processed_id = process_next_ai_operation(db_session, get_settings())
    assert processed_id == event.id
    db_session.refresh(event)
    assert event.status == "needs_review"
    run = db_session.scalar(select(AiRunLog).where(AiRunLog.orchestrator_event_id == event.id))
    assert run is not None
    assert run.capability_key == "lead.next_action"
    assert run.status == "needs_review"

    workspace_response = client.get("/api/v1/tasks/workspace", headers=HEADERS)
    assert workspace_response.status_code == 200, workspace_response.text
    ai_item = next(
        item for item in workspace_response.json()["items"] if item["id"] == f"ai:{event.id}"
    )
    assert ai_item["item_type"] == "ai_work"
    assert ai_item["work_kind"] == "ai_review"
    assert ai_item["can_decide"] is True
    assert ai_item["ai_output"]["confidence"] == 90

    review_response = client.patch(
        f"/api/v1/tasks/ai-work/{event.id}/review",
        headers=HEADERS,
        json={"decision": "accepted", "notes": "Brief matches the lead."},
    )
    assert review_response.status_code == 200, review_response.text
    db_session.refresh(event)
    db_session.refresh(run)
    assert event.status == "completed"
    assert run.status == "accepted"
    assert (
        int(
            db_session.scalar(
                select(func.count())
                .select_from(CommunicationRecord)
                .where(CommunicationRecord.provider_message_id == f"ai-operations:{event.id}")
            )
            or 0
        )
        == 1
    )

    completed_workspace = client.get("/api/v1/tasks/workspace", headers=HEADERS).json()
    completed_item = next(
        item for item in completed_workspace["items"] if item["id"] == f"ai:{event.id}"
    )
    assert completed_item["work_kind"] == "ai_completed"
    assert completed_item["outcome"] == "accepted"

    get_settings.cache_clear()


def test_worker_finalization_does_not_resurrect_ai_event_closed_during_runtime(
    db_session: Session,
    api_db_override: None,
    monkeypatch: MonkeyPatch,
) -> None:
    seed_owner(db_session)
    client = TestClient(app)
    install_runtime(client)
    created_response = client.post("/api/v1/leads", headers=HEADERS, json=lead_payload())
    assert created_response.status_code == 201, created_response.text
    lead_id = UUID(created_response.json()["id"])
    event = db_session.scalar(select(AiOrchestratorEvent))
    assert event is not None and event.status == "queued"
    event_id = event.id

    def close_during_runtime(
        runtime_db: Session,
        _principal: object,
        _payload: object,
    ) -> SimpleNamespace:
        lead = runtime_db.get(Lead, lead_id)
        runtime_event = runtime_db.get(AiOrchestratorEvent, event_id)
        assert lead is not None and runtime_event is not None
        closed_at = datetime.now(UTC)
        lead.stage_key = "dead"
        lead.archived_at = closed_at
        lead.close_out_disposition = "dead"
        lead.close_out_reason = "Seller closed discussions while AI work was running."
        lead.closed_out_at = closed_at
        runtime_event.status = "dismissed"
        runtime_event.processed_at = closed_at
        runtime_db.commit()
        return SimpleNamespace(status="needs_review", id=uuid4(), error_message=None)

    monkeypatch.setattr("app.services.ai_runtime.execute_runtime", close_during_runtime)
    assert process_next_ai_operation(db_session, get_settings()) == event_id
    db_session.expire_all()
    persisted_event = db_session.get(AiOrchestratorEvent, event_id)
    assert persisted_event is not None
    assert persisted_event.status == "dismissed"
    assert persisted_event.last_error == "Lead closed while AI next-action work was running."
    assert db_session.scalar(
        select(func.count(ActivityEvent.id)).where(
            ActivityEvent.entity_id == lead_id,
            ActivityEvent.event_type == "ai_operations.needs_review",
        )
    ) == 0
