import json
from datetime import UTC, datetime
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.auth import principal_for_user
from app.core.config import Settings
from app.main import app
from app.models.foundation import (
    AiAgentDefinition,
    AiCapabilityRuntimePolicy,
    AiPromptVersion,
    AiRunLog,
    AiRuntimePolicy,
    User,
)
from app.services.ai_orchestrator import install_portfolio
from app.services.batchdialer_direct import archive_batchdialer_cdr
from app.services.bootstrap import bootstrap_foundation
from app.services.va_performance_coach import CAPABILITY_KEY, VA_PERFORMANCE_COACH_OUTPUT_SCHEMA

OWNER_EMAIL = "owner@example.com"


def _seed(db: Session) -> None:
    result = bootstrap_foundation(
        db,
        organization_name="VA Coach API Test",
        admin_email=OWNER_EMAIL,
        admin_name="Owner",
    )
    assert result.admin_user is not None
    install_portfolio(db, principal_for_user(db, result.admin_user))
    agent = db.scalar(
        select(AiAgentDefinition).where(
            AiAgentDefinition.organization_id == result.organization.id,
            AiAgentDefinition.key == "prospecting_intelligence",
        )
    )
    assert agent is not None
    cdr = {
        "id": 88101,
        "direction": "out",
        "callStartTime": "2026-08-18T17:00:00Z",
        "callEndTime": "2026-08-18T17:03:00Z",
        "did": "+16785550100",
        "customerNumber": "+16785550199",
        "disposition": "Qualified Seller - Follow Up",
        "duration": 180,
        "status": "completed",
        "callid": "provider-call-88101",
        "recordingenabled": True,
        "comments": ["Seller asked for a follow-up."],
        "agent": {"id": 7, "firstname": "VA", "lastname": "Agent"},
        "contact": {
            "id": 44,
            "firstname": "Test",
            "lastname": "Seller",
            "state": "GA",
            "email": "seller@example.com",
        },
        "campaign": {"id": 88, "name": "Georgia Distressed Homeowners"},
    }
    assert (
        archive_batchdialer_cdr(
            db,
            organization_id=result.organization.id,
            cdr=cdr,
            now=datetime(2026, 8, 18, 17, 4, tzinfo=UTC),
        )
        == "archived"
    )
    db.add(
        AiRuntimePolicy(
            organization_id=result.organization.id,
            provider_status="enabled",
            emergency_stop=False,
            high_volume_model="gpt-5.6-sol",
            default_model="gpt-5.6-sol",
            escalation_model="gpt-5.6-sol",
            max_context_characters=80_000,
            max_requests_per_minute=30,
            max_daily_cost_microusd=10_000_000,
            circuit_failure_threshold=3,
            circuit_cooldown_seconds=300,
            consecutive_failure_count=0,
            trace_redaction_enabled=True,
            external_actions_enabled=False,
            updated_by_user_id=result.admin_user.id,
        )
    )
    db.add(
        AiCapabilityRuntimePolicy(
            organization_id=result.organization.id,
            agent_definition_id=agent.id,
            capability_key=CAPABILITY_KEY,
            status="enabled",
            model_route="default",
            output_schema=VA_PERFORMANCE_COACH_OUTPUT_SCHEMA,
            allowed_tool_keys=[],
            allowed_knowledge_keys=["operating_model"],
            max_output_tokens=1800,
            max_cost_microusd_per_run=100_000,
            requires_human_review=True,
            updated_by_user_id=result.admin_user.id,
        )
    )
    db.commit()


def _settings() -> Settings:
    return Settings.model_validate(
        {
            "DATABASE_URL": "sqlite+pysqlite:///:memory:",
            "OPENAI_API_KEY": "test-key",
            "OPENAI_DEFAULT_MODEL": "gpt-5.6-sol",
            "BATCHDIALER_ACCOUNT_TIMEZONE": "America/New_York",
        }
    )


def _model_output(metric_keys: list[str], event_ids: list[str]) -> dict[str, Any]:
    assert "metrics.calls" in metric_keys
    assert "metrics.qualified_candidates" in metric_keys
    assert "coverage_metrics.peer_agent_count" in metric_keys
    assert "coverage_metrics.archive_history_status" in metric_keys
    assert "coverage_metrics.provider_sync_freshness" in metric_keys
    assert "coverage_metrics.provider_sync_status" in metric_keys
    assert "coverage_metrics.provider_sync_coverage_complete" in metric_keys
    assert "coverage_metrics.continuous_archive_history_proven" in metric_keys
    assert "coverage_metrics.outcome_maturity_normalized" in metric_keys
    assert "coverage_metrics.downstream_outcomes_as_of" in metric_keys
    assert "coverage_metrics.paid_hours_available" in metric_keys
    assert event_ids
    event_id = event_ids[0]
    return {
        "draft_only": True,
        "summary": {
            "text": "The period contains calling activity and a qualification candidate.",
            "evidence_refs": ["metrics.calls", "metrics.qualified_candidates"],
        },
        "strengths": [
            {
                "observation": "A qualification candidate was created.",
                "evidence_refs": ["metrics.qualified_candidates"],
            }
        ],
        "concerns": [],
        "next_shift_actions": [
            {
                "action": "Review the supplied candidate call before the next shift.",
                "rationale": "The provider event is the available call-level evidence.",
                "evidence_refs": [event_id],
            }
        ],
        "calls_to_review": [
            {
                "provider_event_id": event_id,
                "reason": "This call supplied the qualification candidate.",
                "evidence_refs": [event_id],
            }
        ],
        "comparison_caveats": [
            {
                "caveat": (
                    "No peer-agent normalization is available, and recent provider call "
                    "coverage may be incomplete."
                ),
                "evidence_refs": [
                    "coverage_metrics.peer_agent_count",
                    "coverage_metrics.provider_sync_freshness",
                    "coverage_metrics.outcome_maturity_normalized",
                    "coverage_metrics.paid_hours_available",
                ],
            }
        ],
        "confidence": {
            "level": "medium",
            "rationale": "Call-level evidence exists, but the sample is small.",
            "evidence_refs": ["metrics.calls", event_id],
        },
    }


def test_va_coach_post_reuses_report_and_latest_returns_it(
    db_session: Session,
    api_db_override: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    del api_db_override
    _seed(db_session)
    requests: list[dict[str, Any]] = []

    def structured_response(
        *_args: object,
        **kwargs: Any,
    ) -> tuple[dict[str, Any], dict[str, int]]:
        prompt = json.loads(kwargs["user_prompt"])
        requests.append(prompt)
        return (
            _model_output(
                prompt["allowed_metric_keys"],
                prompt["allowed_provider_event_ids"],
            ),
            {"input_tokens": 500, "output_tokens": 150, "total_tokens": 650},
        )

    monkeypatch.setattr("app.routers.prospecting.get_settings", _settings)
    monkeypatch.setattr(
        "app.services.va_performance_coach.OpenAIResponsesClient.create_structured_response",
        structured_response,
    )
    client = TestClient(app)
    request_body = {
        "provider_agent_id": "7",
        "date_from": "2026-08-18",
        "date_to": "2026-08-18",
    }

    first = client.post(
        "/api/v1/prospecting/batchdialer/va-coach",
        headers={"X-Dev-User-Email": OWNER_EMAIL},
        json=request_body,
    )
    second = client.post(
        "/api/v1/prospecting/batchdialer/va-coach",
        headers={"X-Dev-User-Email": OWNER_EMAIL},
        json=request_body,
    )

    assert first.status_code == 200, first.text
    assert first.headers["cache-control"] == "private, no-store"
    assert second.status_code == 200, second.text
    first_payload = first.json()
    second_payload = second.json()
    assert first_payload["provider_agent_id"] == "7"
    assert first_payload["status"] == "needs_review"
    assert first_payload["reused"] is False
    assert first_payload["output"]["draft_only"] is True
    assert first_payload["output"]["calls_to_review"][0]["provider_event_id"]
    assert second_payload["run_id"] == first_payload["run_id"]
    assert second_payload["reused"] is True
    assert len(requests) == 1
    assert requests[0]["deterministic_performance_snapshot"]["provider_agent"] == {
        "provider_agent_id": "7",
        "stonegate_user_id": None,
    }
    assert "VA Agent" not in json.dumps(requests[0])

    latest = client.get(
        "/api/v1/prospecting/batchdialer/va-coach/latest",
        headers={"X-Dev-User-Email": OWNER_EMAIL},
        params={
            "provider_agent_id": "7",
            "date_from": "2026-08-18",
            "date_to": "2026-08-18",
        },
    )
    assert latest.status_code == 200, latest.text
    assert latest.headers["cache-control"] == "private, no-store"
    assert latest.json()["run_id"] == first_payload["run_id"]
    assert latest.json()["reused"] is True
    assert latest.json()["is_stale"] is False
    assert latest.json()["refresh_required"] is False
    assert latest.json()["stale_reasons"] == []
    assert latest.json()["current_evidence_as_of"]
    assert latest.json()["output"]["draft_only"] is True
    assert (
        db_session.scalar(
            select(func.count(AiRunLog.id)).where(AiRunLog.capability_key == CAPABILITY_KEY)
        )
        == 1
    )
    run = db_session.scalar(select(AiRunLog).where(AiRunLog.capability_key == CAPABILITY_KEY))
    assert run is not None and run.run_metadata is not None
    assert run.run_metadata["provider_agent_name"] == "VA Agent"
    assert run.run_metadata["evidence_snapshot"]["metrics"]["calls"] == 1
    assert run.run_metadata["reporting_date_from"] == "2026-08-18"
    assert run.run_metadata["reporting_date_to"] == "2026-08-18"

    wrong_range = client.get(
        "/api/v1/prospecting/batchdialer/va-coach/latest",
        headers={"X-Dev-User-Email": OWNER_EMAIL},
        params={
            "provider_agent_id": "7",
            "date_from": "2026-08-19",
            "date_to": "2026-08-19",
        },
    )
    reversed_range = client.get(
        "/api/v1/prospecting/batchdialer/va-coach/latest",
        headers={"X-Dev-User-Email": OWNER_EMAIL},
        params={
            "provider_agent_id": "7",
            "date_from": "2026-08-19",
            "date_to": "2026-08-18",
        },
    )
    assert wrong_range.status_code == 404
    assert wrong_range.headers["cache-control"] == "private, no-store"
    assert reversed_range.status_code == 422
    assert reversed_range.headers["cache-control"] == "private, no-store"
    assert "date_from must be on or before date_to" in reversed_range.json()["detail"]


def test_latest_va_coach_hides_draft_when_same_range_evidence_changes(
    db_session: Session,
    api_db_override: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    del api_db_override
    _seed(db_session)
    requests = 0

    def structured_response(
        *_args: object,
        **kwargs: Any,
    ) -> tuple[dict[str, Any], dict[str, int]]:
        nonlocal requests
        requests += 1
        prompt = json.loads(kwargs["user_prompt"])
        return (
            _model_output(
                prompt["allowed_metric_keys"],
                prompt["allowed_provider_event_ids"],
            ),
            {"input_tokens": 500, "output_tokens": 150, "total_tokens": 650},
        )

    monkeypatch.setattr("app.routers.prospecting.get_settings", _settings)
    monkeypatch.setattr(
        "app.services.va_performance_coach.OpenAIResponsesClient.create_structured_response",
        structured_response,
    )
    client = TestClient(app)
    headers = {"X-Dev-User-Email": OWNER_EMAIL}
    params = {
        "provider_agent_id": "7",
        "date_from": "2026-08-18",
        "date_to": "2026-08-18",
    }
    generated = client.post(
        "/api/v1/prospecting/batchdialer/va-coach",
        headers=headers,
        json=params,
    )
    assert generated.status_code == 200, generated.text
    assert generated.json()["is_stale"] is False

    second_cdr = {
        "id": 88102,
        "direction": "out",
        "callStartTime": "2026-08-18T18:00:00Z",
        "callEndTime": "2026-08-18T18:02:00Z",
        "did": "+16785550100",
        "customerNumber": "+16785550200",
        "disposition": "Not Interested",
        "duration": 120,
        "status": "completed",
        "callid": "provider-call-88102",
        "recordingenabled": True,
        "comments": ["Seller declined."],
        "agent": {"id": 7, "firstname": "VA", "lastname": "Agent"},
        "contact": {
            "id": 45,
            "firstname": "Second",
            "lastname": "Seller",
            "state": "GA",
        },
        "campaign": {"id": 88, "name": "Georgia Distressed Homeowners"},
    }
    organization_id = db_session.scalar(
        select(User.organization_id).where(User.email == OWNER_EMAIL)
    )
    assert organization_id is not None
    assert (
        archive_batchdialer_cdr(
            db_session,
            organization_id=organization_id,
            cdr=second_cdr,
            now=datetime(2026, 8, 18, 18, 3, tzinfo=UTC),
        )
        == "archived"
    )

    latest = client.get(
        "/api/v1/prospecting/batchdialer/va-coach/latest",
        headers=headers,
        params=params,
    )
    assert latest.status_code == 200, latest.text
    payload = latest.json()
    assert payload["run_id"] == generated.json()["run_id"]
    assert payload["is_stale"] is True
    assert payload["refresh_required"] is True
    assert payload["stale_reasons"] == ["evidence_changed"]
    assert payload["output"] is None
    assert payload["current_evidence_as_of"]
    assert requests == 1


def test_latest_va_coach_hides_draft_when_generation_contract_changes(
    db_session: Session,
    api_db_override: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    del api_db_override
    _seed(db_session)

    def structured_response(
        *_args: object,
        **kwargs: Any,
    ) -> tuple[dict[str, Any], dict[str, int]]:
        prompt = json.loads(kwargs["user_prompt"])
        return (
            _model_output(
                prompt["allowed_metric_keys"],
                prompt["allowed_provider_event_ids"],
            ),
            {"input_tokens": 500, "output_tokens": 150, "total_tokens": 650},
        )

    monkeypatch.setattr("app.routers.prospecting.get_settings", _settings)
    monkeypatch.setattr(
        "app.services.va_performance_coach.OpenAIResponsesClient.create_structured_response",
        structured_response,
    )
    client = TestClient(app)
    headers = {"X-Dev-User-Email": OWNER_EMAIL}
    params = {
        "provider_agent_id": "7",
        "date_from": "2026-08-18",
        "date_to": "2026-08-18",
    }
    generated = client.post(
        "/api/v1/prospecting/batchdialer/va-coach",
        headers=headers,
        json=params,
    )
    assert generated.status_code == 200, generated.text
    active_prompt = db_session.scalar(
        select(AiPromptVersion).where(AiPromptVersion.status == "active")
    )
    assert active_prompt is not None
    active_prompt.prompt_text = f"{active_prompt.prompt_text}\nRevised governed safety contract."
    db_session.commit()

    latest = client.get(
        "/api/v1/prospecting/batchdialer/va-coach/latest",
        headers=headers,
        params=params,
    )
    assert latest.status_code == 200, latest.text
    payload = latest.json()
    assert payload["run_id"] == generated.json()["run_id"]
    assert payload["is_stale"] is True
    assert payload["refresh_required"] is True
    assert payload["stale_reasons"] == ["generation_contract_changed"]
    assert payload["output"] is None


def test_va_coach_endpoints_reject_missing_evidence_and_blank_latest_agent(
    db_session: Session,
    api_db_override: None,
) -> None:
    del api_db_override
    result = bootstrap_foundation(
        db_session,
        organization_name="VA Coach Empty Test",
        admin_email=OWNER_EMAIL,
        admin_name="Owner",
    )
    assert result.admin_user is not None
    client = TestClient(app)
    headers = {"X-Dev-User-Email": OWNER_EMAIL}

    missing = client.post(
        "/api/v1/prospecting/batchdialer/va-coach",
        headers=headers,
        json={
            "provider_agent_id": "missing-agent",
            "date_from": "2026-08-18",
            "date_to": "2026-08-18",
        },
    )
    blank_latest = client.get(
        "/api/v1/prospecting/batchdialer/va-coach/latest",
        headers=headers,
        params={"provider_agent_id": "   "},
    )

    assert missing.status_code == 422
    assert "No BatchDialer call evidence" in missing.json()["detail"]
    assert missing.headers["cache-control"] == "private, no-store"
    assert blank_latest.status_code == 404
    assert blank_latest.headers["cache-control"] == "private, no-store"
    assert (
        db_session.scalar(
            select(func.count(AiRunLog.id)).where(AiRunLog.capability_key == CAPABILITY_KEY)
        )
        == 0
    )
    assert db_session.scalar(select(func.count(User.id))) == 1
