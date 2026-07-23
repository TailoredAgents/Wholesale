from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.main import app
from app.models.foundation import (
    ManagementCopilotRecommendation,
    ManagementCopilotReview,
    MarketingSpend,
    RevenueRecord,
    Task,
    User,
)
from app.services.bootstrap import bootstrap_foundation

OWNER_EMAIL = "owner@example.com"
HEADERS = {"X-Dev-User-Email": OWNER_EMAIL}


def test_ai9_management_copilots_generate_reviewed_drafts_without_mutation(
    db_session: Session,
    api_db_override: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    bootstrap_foundation(
        db_session,
        organization_name="Stonegate Home Buyers",
        admin_email=OWNER_EMAIL,
        admin_name="Owner",
    )
    owner = db_session.scalar(select(User).where(User.email == OWNER_EMAIL))
    assert owner is not None
    client = TestClient(app)
    lead = client.post(
        "/api/v1/leads",
        headers=HEADERS,
        json={
            "contact": {
                "legal_name": "Private Seller Name",
                "contact_type": "seller",
            },
            "property": {
                "street_address": "500 Management Test Way",
                "city": "Atlanta",
                "state": "GA",
                "postal_code": "30303",
                "property_type": "single_family",
            },
            "source": "google_ppc",
            "stage_key": "new",
        },
    )
    assert lead.status_code == 201
    lead_id = lead.json()["id"]
    assert client.post(
        "/api/v1/finance/revenue",
        headers=HEADERS,
        json={
            "lead_id": lead_id,
            "source": "assignment_fee",
            "status": "collected",
            "amount_cents": 2500000,
        },
    ).status_code == 201
    assert client.post(
        "/api/v1/finance/marketing-spend",
        headers=HEADERS,
        json={
            "source": "google_ppc",
            "campaign": "atlanta-seller",
            "amount_cents": 500000,
        },
    ).status_code == 201
    db_session.add(
        Task(
            organization_id=owner.organization_id,
            lead_id=UUID(lead_id),
            responsible_user_id=owner.id,
            task_type="follow_up",
            title="Overdue seller follow-up",
            status="open",
            priority="high",
            due_at=datetime.now(UTC) - timedelta(days=1),
            completed_at=None,
        )
    )
    db_session.commit()

    with monkeypatch.context() as configured_environment:
        configured_environment.setenv("AI_ENABLED", "true")
        configured_environment.setenv("OPENAI_API_KEY", "test-openai-key")
        get_settings.cache_clear()
        assert client.post(
            "/api/v1/ai/orchestrator/portfolio/install",
            headers=HEADERS,
        ).status_code == 201
        assert client.post(
            "/api/v1/ai/copilots/install",
            headers=HEADERS,
        ).status_code == 201
        assert client.post(
            "/api/v1/ai/copilots/foundation/decision",
            headers=HEADERS,
            json={"decision": "approve", "notes": "Approved for AI9 test."},
        ).status_code == 200
        installed = client.post("/api/v1/ai/runtime/install", headers=HEADERS)
        assert installed.status_code == 201
        statuses = {
            item["capability_key"]: item
            for item in installed.json()["runtime"]["capabilities"]
        }
        for capability in (
            "finance.reconcile",
            "marketing.analyze",
            "operations.brief",
        ):
            assert statuses[capability]["status"] == "enabled"
            assert statuses[capability]["requires_human_review"] is True

        class FakeOpenAIResponsesClient:
            def __init__(self, **_: object) -> None:
                pass

            def create_structured_response(self, **kwargs: object):
                prompt = kwargs["user_prompt"]
                assert isinstance(prompt, str)
                assert "Private Seller Name" not in prompt
                assert "500 Management Test Way" not in prompt
                schema = kwargs["json_schema"]
                assert isinstance(schema, dict)
                assert schema["additionalProperties"] is False
                return (
                    {
                        "brief": (
                            "Management evidence shows one priority requiring human review."
                        ),
                        "confirmed_facts": [
                            {
                                "label": "Reporting period",
                                "value": "30 days",
                                "evidence": ["Period-bounded Stonegate records"],
                            }
                        ],
                        "exceptions": [
                            {
                                "severity": "warning",
                                "category": "operations",
                                "title": "Review required",
                                "detail": "A recorded exception needs an owner decision.",
                                "evidence": ["Deterministic management risk ledger"],
                            }
                        ],
                        "analysis": [
                            {
                                "category": "performance",
                                "subject": "Current operating evidence",
                                "signal": "warning",
                                "analysis": "The sample supports review but not autonomous action.",
                                "evidence": ["Approved aggregate management records"],
                            }
                        ],
                        "draft_actions": [
                            {
                                "action": "Review the linked exception in its source workspace.",
                                "reason": "Human authority is required.",
                                "owner": "Owner",
                                "workspace": "dashboard",
                                "evidence": ["Deterministic management risk ledger"],
                                "requires_human_decision": True,
                            }
                        ],
                        "decision_requests": [
                            {
                                "decision": "Choose whether to investigate now.",
                                "why_now": "The exception is active in the reporting period.",
                                "options": ["Investigate now", "Assign a human review"],
                                "evidence": ["Deterministic management risk ledger"],
                            }
                        ],
                        "uncertainties": [
                            "Provider ledgers are not connected in this test."
                        ],
                        "evidence": ["Stonegate aggregate records"],
                        "confidence": 86,
                    },
                    {"input_tokens": 180, "output_tokens": 220, "total_tokens": 400},
                )

        monkeypatch.setattr(
            "app.services.ai_runtime.OpenAIResponsesClient",
            FakeOpenAIResponsesClient,
        )

        endpoint_specs = (
            (
                "/api/v1/finance/copilot",
                "/api/v1/finance/copilot/analyze",
                "/api/v1/finance/copilot/recommendations",
            ),
            (
                "/api/v1/marketing/copilot",
                "/api/v1/marketing/copilot/analyze",
                "/api/v1/marketing/copilot/recommendations",
            ),
            (
                "/api/v1/dashboard/executive-copilot",
                "/api/v1/dashboard/executive-copilot/analyze",
                "/api/v1/dashboard/executive-copilot/recommendations",
            ),
        )
        for index, (overview_path, analyze_path, review_base) in enumerate(
            endpoint_specs
        ):
            overview = client.get(
                f"{overview_path}?period_days=30",
                headers=HEADERS,
            )
            assert overview.status_code == 200, overview.text
            assert overview.json()["capability_status"] == "enabled"
            assert overview.json()["external_actions_blocked"] is True
            assert len(overview.json()["metric_cards"]) == 4

            analyzed = client.post(
                analyze_path,
                headers=HEADERS,
                json={
                    "period_days": 30,
                    "idempotency_key": f"management-copilot:test:{index}",
                },
            )
            assert analyzed.status_code == 200, analyzed.text
            recommendation = analyzed.json()["recommendation"]
            assert recommendation["status"] == "draft"
            repeated = client.post(
                analyze_path,
                headers=HEADERS,
                json={
                    "period_days": 30,
                    "idempotency_key": f"management-copilot:test:{index}",
                },
            )
            assert repeated.json()["recommendation"]["id"] == recommendation["id"]
            review = client.post(
                f"{review_base}/{recommendation['id']}/review",
                headers=HEADERS,
                json={
                    "decision": "accepted",
                    "notes": "Owner reviewed the evidence.",
                    "estimated_time_saved_seconds": 300,
                },
            )
            assert review.status_code == 200, review.text
            assert review.json()["decision"] == "accepted"

    get_settings.cache_clear()
    assert db_session.scalar(
        select(func.count(ManagementCopilotRecommendation.id))
    ) == 3
    assert db_session.scalar(select(func.count(ManagementCopilotReview.id))) == 3
    assert db_session.scalar(select(func.count(RevenueRecord.id))) == 1
    assert db_session.scalar(select(func.count(MarketingSpend.id))) == 1
    task = db_session.scalar(select(Task))
    assert task is not None
    assert task.status == "open"
