import json
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.auth import Principal
from app.core.config import Settings
from app.integrations.openai_client import OpenAIClientError, validate_strict_json_schema
from app.models.foundation import (
    AiAgentDefinition,
    AiCapabilityRuntimePolicy,
    AiPromptVersion,
    AiRunLog,
    AiRuntimePolicy,
)
from app.services.bootstrap import bootstrap_foundation
from app.services.va_performance_coach import (
    CAPABILITY_KEY,
    VA_PERFORMANCE_COACH_OUTPUT_SCHEMA,
    VaPerformanceCoachError,
    _expire_reservation,
    _persist_run,
    _reserve_run,
    _validate_output,
    generate_va_performance_coaching_report,
    get_latest_va_performance_coaching_report,
    get_latest_va_performance_coaching_reports,
)


def _foundation(db: Session) -> Principal:
    result = bootstrap_foundation(
        db,
        organization_name="VA Coach Test",
        admin_email="owner@example.com",
        admin_name="Owner",
    )
    assert result.admin_user is not None
    agent = AiAgentDefinition(
        organization_id=result.organization.id,
        key="prospecting_intelligence",
        name="Prospecting Intelligence",
        description="Evidence-bound prospecting guidance.",
        status="active",
        model_name="gpt-5.6-sol",
        risk_level="medium",
        requires_human_approval=True,
        autonomy_level="observe",
        max_cost_microusd_per_run=100_000,
        max_daily_cost_microusd=1_000_000,
        max_attempts=2,
        rollback_owner_user_id=result.admin_user.id,
    )
    db.add(agent)
    db.flush()
    db.add(
        AiPromptVersion(
            organization_id=result.organization.id,
            agent_definition_id=agent.id,
            version_number=1,
            status="active",
            prompt_text="Use supplied facts and keep every output draft-only.",
            change_notes="Test prompt",
            created_by_user_id=result.admin_user.id,
        )
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
            allowed_knowledge_keys=[
                "operating_model",
                "prospecting_scripts",
                "ai_agent_policy",
            ],
            max_output_tokens=1800,
            max_cost_microusd_per_run=100_000,
            requires_human_review=True,
            updated_by_user_id=result.admin_user.id,
        )
    )
    db.commit()
    return Principal(
        user_id=result.admin_user.id,
        organization_id=result.organization.id,
        email=result.admin_user.email,
        permission_keys=frozenset(),
    )


def _settings() -> Settings:
    return Settings.model_validate(
        {
            "DATABASE_URL": "sqlite+pysqlite:///:memory:",
            "OPENAI_API_KEY": "test-key",
            "OPENAI_DEFAULT_MODEL": "gpt-5.6-sol",
        }
    )


def _snapshot() -> dict[str, Any]:
    return {
        "provider": "batchdialer",
        "provider_agent": {"id": "agent-17", "name": "Richard"},
        "metrics": {
            "outbound_calls": 174,
            "human_connections": 121,
            "verified_qualified_leads": 1,
            "provider_qualified_calls": 2,
            "qualification_false_positives": 1,
        },
        "comparison_metrics": {
            "campaign_peer_sample_size": 3,
            "same_campaign": True,
        },
        "provider_events": [
            {
                "provider_event_id": "cdr-101",
                "outcome": "verified_qualified",
            },
            {
                "provider_event_id": "cdr-102",
                "outcome": "needs_review",
            },
        ],
        "metric_definitions": {
            "qualification_false_positives": (
                "A workflow-quality signal, not proof that the VA made an error."
            )
        },
        "api_key": "must-not-be-persisted",
    }


def _valid_output() -> dict[str, Any]:
    return {
        "draft_only": True,
        "summary": {
            "text": "Calling activity was high, but verified qualification volume was limited.",
            "evidence_refs": [
                "metrics.outbound_calls",
                "metrics.verified_qualified_leads",
            ],
        },
        "strengths": [
            {
                "observation": "The VA generated substantial outbound activity.",
                "evidence_refs": ["metrics.outbound_calls"],
            }
        ],
        "concerns": [
            {
                "observation": "Provider-qualified calls exceeded verified qualified leads.",
                "evidence_refs": [
                    "metrics.provider_qualified_calls",
                    "metrics.verified_qualified_leads",
                ],
            }
        ],
        "next_shift_actions": [
            {
                "action": "Review the qualification evidence before marking the next handoff.",
                "rationale": "One supplied call requires evidence review.",
                "evidence_refs": ["cdr-102"],
            }
        ],
        "calls_to_review": [
            {
                "provider_event_id": "cdr-102",
                "reason": "This event was routed for review.",
                "evidence_refs": ["cdr-102"],
            }
        ],
        "comparison_caveats": [
            {
                "caveat": "The comparable peer sample is small.",
                "evidence_refs": ["comparison_metrics.campaign_peer_sample_size"],
            }
        ],
        "confidence": {
            "level": "medium",
            "rationale": "Activity and lead evidence exist, but the peer sample is small.",
            "evidence_refs": [
                "metrics.outbound_calls",
                "comparison_metrics.campaign_peer_sample_size",
            ],
        },
    }


_VALID_OUTPUT_EVIDENCE_REFS = {
    "metrics.outbound_calls",
    "metrics.verified_qualified_leads",
    "metrics.provider_qualified_calls",
    "comparison_metrics.campaign_peer_sample_size",
    "cdr-101",
    "cdr-102",
}


def test_va_performance_coach_schema_is_strict() -> None:
    validate_strict_json_schema(VA_PERFORMANCE_COACH_OUTPUT_SCHEMA)


@pytest.mark.parametrize(
    ("text", "expected_error"),
    [
        ("Let the VA go after this shift.", "employment-decision boundary"),
        ("Dismiss the VA based on these results.", "employment-decision boundary"),
        ("Replace the VA.", "employment-decision boundary"),
        ("The VA should be replaced.", "employment-decision boundary"),
        ("Do not retain this VA.", "employment-decision boundary"),
        ("The agent must not be kept.", "employment-decision boundary"),
        ("Give the VA a pay cut for low qualification.", "employment-decision boundary"),
        ("Give the VA a bonus for high connection volume.", "employment-decision boundary"),
        ("Demote the VA to a lower role.", "employment-decision boundary"),
        ("Suspend the VA for one week.", "employment-decision boundary"),
        ("Reward the VA for these results.", "employment-decision boundary"),
        ("Change their commission based on lead volume.", "employment-decision boundary"),
        ("The VA worked for 8 hours.", "unsupported exact work hours"),
        ("The VA worked for eight hours.", "unsupported exact work hours"),
        ("The VA was on shift for twelve hours.", "unsupported exact work hours"),
        ("She put in nine and a half hours.", "unsupported exact work hours"),
        ("The VA worked an eight-hour shift.", "unsupported exact work hours"),
        ("This VA's shift lasted eight hours.", "unsupported exact work hours"),
        ("Their shift was 8 hours.", "unsupported exact work hours"),
        ("Her workday totaled nine hours.", "unsupported exact work hours"),
        ("The agent's shift duration amounted to ten hours.", "unsupported exact work hours"),
        ("The VA worked from 9 AM to 5 PM.", "unsupported exact work hours"),
        ("Their shift ran from 9 to 5.", "unsupported exact work hours"),
        ("The agent's workday began at 9.", "unsupported exact work hours"),
    ],
)
def test_output_boundary_rejects_employment_decisions_and_exact_hour_claims(
    text: str,
    expected_error: str,
) -> None:
    output = _valid_output()
    output["summary"]["text"] = text

    with pytest.raises(ValueError, match=expected_error):
        _validate_output(output, _VALID_OUTPUT_EVIDENCE_REFS, {"cdr-101", "cdr-102"})


@pytest.mark.parametrize(
    "text",
    [
        "Coach the VA to confirm seller motivation before qualifying the next lead.",
        "Recognize strong call openings and reinforce that workflow next shift.",
        "Review eight calls during the next coaching session.",
        (
            "The eight-hour reporting window contains calling events but does not establish "
            "time worked."
        ),
        "Suspend judgment until an authorized reviewer checks the call evidence.",
        "Raise the quality of follow-up questions through role-play coaching.",
        "Reward consistent practice with verbal recognition during coaching.",
        "Replace the opening script with the approved version.",
        "Retain the evidence caveat in the manager's draft.",
        "Their shift contained eight reviewed calls in the supplied evidence.",
        "The first supplied call occurred at 9 AM.",
        "Review calls from 9 AM to 5 PM during the next coaching session.",
    ],
)
def test_output_boundary_allows_benign_coaching_language(text: str) -> None:
    output = _valid_output()
    output["summary"]["text"] = text

    _validate_output(output, _VALID_OUTPUT_EVIDENCE_REFS, {"cdr-101", "cdr-102"})


def test_output_requires_provider_sync_caveat_when_coverage_is_incomplete() -> None:
    output = _valid_output()
    sync_ref = "coverage_metrics.provider_sync_freshness"
    allowed_refs = _VALID_OUTPUT_EVIDENCE_REFS | {sync_ref}

    with pytest.raises(ValueError, match="comparison limitation caveat"):
        _validate_output(
            output,
            allowed_refs,
            {"cdr-101", "cdr-102"},
            required_comparison_caveat_refs={sync_ref},
        )

    output["comparison_caveats"].append(
        {
            "caveat": "Recent provider call coverage may be incomplete.",
            "evidence_refs": [sync_ref],
        }
    )
    _validate_output(
        output,
        allowed_refs,
        {"cdr-101", "cdr-102"},
        required_comparison_caveat_refs={sync_ref},
    )


def test_output_requires_peer_and_paid_hours_comparison_limitations() -> None:
    output = _valid_output()
    campaign_ref = "coverage_metrics.campaign_mix_normalized"
    hours_ref = "coverage_metrics.paid_hours_available"
    required_refs = {campaign_ref, hours_ref}
    allowed_refs = _VALID_OUTPUT_EVIDENCE_REFS | required_refs

    with pytest.raises(ValueError, match="comparison limitation caveat"):
        _validate_output(
            output,
            allowed_refs,
            {"cdr-101", "cdr-102"},
            required_comparison_caveat_refs=required_refs,
        )

    output["comparison_caveats"].append(
        {
            "caveat": (
                "Peer campaign mix is not normalized and calling spans do not establish paid hours."
            ),
            "evidence_refs": [campaign_ref, hours_ref],
        }
    )
    _validate_output(
        output,
        allowed_refs,
        {"cdr-101", "cdr-102"},
        required_comparison_caveat_refs=required_refs,
    )


def test_generate_reuses_evidence_bound_report_and_logs_usage(
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    principal = _foundation(db_session)
    calls: list[dict[str, Any]] = []

    def structured_response(*_args: object, **kwargs: Any) -> tuple[dict[str, Any], dict[str, int]]:
        calls.append(kwargs)
        return _valid_output(), {
            "input_tokens": 1_000,
            "output_tokens": 200,
            "total_tokens": 1_200,
        }

    monkeypatch.setattr(
        "app.services.va_performance_coach.OpenAIResponsesClient.create_structured_response",
        structured_response,
    )
    start = datetime(2026, 8, 22, 13, tzinfo=UTC)
    end = start + timedelta(hours=8)

    first = generate_va_performance_coaching_report(
        db_session,
        principal,
        _settings(),
        provider_agent_id="agent-17",
        range_start=start,
        range_end=end,
        performance_snapshot=_snapshot(),
    )
    second = generate_va_performance_coaching_report(
        db_session,
        principal,
        _settings(),
        provider_agent_id="agent-17",
        range_start=start,
        range_end=end,
        performance_snapshot=_snapshot(),
    )

    assert first.status == "needs_review"
    assert first.output["draft_only"] is True
    assert first.reused is False
    assert second.run_id == first.run_id
    assert second.reused is True
    assert len(calls) == 1
    assert calls[0]["json_schema"] == VA_PERFORMANCE_COACH_OUTPUT_SCHEMA
    assert "Never calculate" in calls[0]["system_prompt"]
    assert "exact hours worked" in calls[0]["system_prompt"]
    assert "Never infer, guess, mention, or use a person's race" in calls[0]["system_prompt"]
    assert "allowed_metric_keys" in calls[0]["user_prompt"]
    assert "qualification_false_positive_definition" in calls[0]["user_prompt"]
    assert "not proof that the VA made an error" in calls[0]["user_prompt"]
    sent_context = json.loads(calls[0]["user_prompt"])
    sent_snapshot = sent_context["deterministic_performance_snapshot"]
    assert sent_snapshot["provider_agent"] == {"id": "agent-17"}
    assert "Richard" not in calls[0]["user_prompt"]
    assert (
        sent_context["interpretation_guardrails"]["protected_characteristics_boundary"]
        == "Never infer, mention, compare, or use protected or personal characteristics. "
        "Use only supplied job-related operational evidence."
    )

    run = db_session.get(AiRunLog, first.run_id)
    assert run is not None
    assert run.capability_key == CAPABILITY_KEY
    assert run.execution_mode == "production"
    assert run.requested_by_user_id == principal.user_id
    assert run.input_tokens == 1_000
    assert run.output_tokens == 200
    assert run.total_tokens == 1_200
    assert run.cost_microusd == 11_000
    assert run.cost_cents == 1
    assert run.run_metadata is not None
    assert run.run_metadata["hours_basis"] == "calling_activity_only"
    assert run.run_metadata["external_actions"] == "blocked"
    assert run.run_metadata["runtime_gate_evaluated"] is True
    assert run.run_metadata["reservation_status"] == "finalized"
    assert run.run_metadata["tool_execution"] == "none"
    evidence = run.run_metadata["evidence_snapshot"]
    assert evidence["metrics"] == _snapshot()["metrics"]
    assert evidence["provider_events"] == _snapshot()["provider_events"]
    assert evidence["provider_agent"]["name"] == "Richard"
    assert evidence["api_key"] == "[redacted]"
    capability = db_session.scalar(
        select(AiCapabilityRuntimePolicy).where(
            AiCapabilityRuntimePolicy.capability_key == CAPABILITY_KEY
        )
    )
    assert capability is not None
    assert capability.status == "enabled"
    assert capability.allowed_tool_keys == []

    latest = get_latest_va_performance_coaching_report(
        db_session,
        principal,
        provider_agent_id="agent-17",
    )
    assert latest is not None and latest.run_id == first.run_id
    assert get_latest_va_performance_coaching_reports(db_session, principal, limit=10) == [latest]


def test_generation_contract_change_does_not_reuse_an_old_draft(
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    principal = _foundation(db_session)
    calls = 0

    def structured_response(
        *_args: object,
        **_kwargs: Any,
    ) -> tuple[dict[str, Any], dict[str, int]]:
        nonlocal calls
        calls += 1
        return _valid_output(), {
            "input_tokens": 100,
            "output_tokens": 50,
            "total_tokens": 150,
        }

    monkeypatch.setattr(
        "app.services.va_performance_coach.OpenAIResponsesClient.create_structured_response",
        structured_response,
    )
    start = datetime(2026, 8, 22, 13, tzinfo=UTC)
    first = generate_va_performance_coaching_report(
        db_session,
        principal,
        _settings(),
        provider_agent_id="agent-17",
        range_start=start,
        range_end=start + timedelta(hours=8),
        performance_snapshot=_snapshot(),
    )
    prompt = db_session.scalar(select(AiPromptVersion))
    assert prompt is not None
    prompt.prompt_text = "Use supplied facts under the revised coaching contract."
    db_session.commit()
    second = generate_va_performance_coaching_report(
        db_session,
        principal,
        _settings(),
        provider_agent_id="agent-17",
        range_start=start,
        range_end=start + timedelta(hours=8),
        performance_snapshot=_snapshot(),
    )

    assert calls == 2
    assert first.run_id != second.run_id
    runs = list(db_session.scalars(select(AiRunLog).order_by(AiRunLog.created_at)).all())
    assert len(runs) == 2
    assert runs[0].run_metadata is not None
    assert runs[1].run_metadata is not None
    assert (
        runs[0].run_metadata["generation_contract_sha256"]
        != runs[1].run_metadata["generation_contract_sha256"]
    )


def test_provider_poll_heartbeat_changes_do_not_buy_an_identical_coaching_draft(
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    principal = _foundation(db_session)
    calls = 0

    def structured_response(
        *_args: object,
        **_kwargs: Any,
    ) -> tuple[dict[str, Any], dict[str, int]]:
        nonlocal calls
        calls += 1
        return _valid_output(), {
            "input_tokens": 100,
            "output_tokens": 50,
            "total_tokens": 150,
        }

    monkeypatch.setattr(
        "app.services.va_performance_coach.OpenAIResponsesClient.create_structured_response",
        structured_response,
    )
    start = datetime(2026, 8, 22, 13, tzinfo=UTC)
    first_snapshot = _snapshot()
    first_snapshot["reporting_range"] = {
        "date_from": "2026-08-22",
        "date_to": "2026-08-22",
        "as_of": "2026-08-22T17:00:00Z",
    }
    first_snapshot["coverage_metrics"] = {
        "provider_sync_status": "healthy",
        "provider_sync_freshness": "fresh",
        "provider_sync_coverage_complete": True,
        "provider_sync_last_success_at": "2026-08-22T16:59:00Z",
        "outcome_maturity_normalized": True,
        "downstream_outcomes_as_of": "2026-08-22T17:00:00Z",
    }
    second_snapshot = json.loads(json.dumps(first_snapshot))
    second_snapshot["reporting_range"]["as_of"] = "2026-08-22T17:02:00Z"
    second_snapshot["coverage_metrics"]["provider_sync_last_success_at"] = "2026-08-22T17:01:00Z"
    second_snapshot["coverage_metrics"]["downstream_outcomes_as_of"] = "2026-08-22T17:02:00Z"

    first = generate_va_performance_coaching_report(
        db_session,
        principal,
        _settings(),
        provider_agent_id="agent-17",
        range_start=start,
        range_end=start + timedelta(hours=8),
        performance_snapshot=first_snapshot,
    )
    second = generate_va_performance_coaching_report(
        db_session,
        principal,
        _settings(),
        provider_agent_id="agent-17",
        range_start=start,
        range_end=start + timedelta(hours=8),
        performance_snapshot=second_snapshot,
    )

    assert calls == 1
    assert second.run_id == first.run_id
    assert second.reused is True


def test_personal_name_change_neither_reaches_model_nor_buys_new_draft(
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    principal = _foundation(db_session)
    calls: list[dict[str, Any]] = []

    def structured_response(
        *_args: object,
        **kwargs: Any,
    ) -> tuple[dict[str, Any], dict[str, int]]:
        calls.append(kwargs)
        return _valid_output(), {
            "input_tokens": 100,
            "output_tokens": 50,
            "total_tokens": 150,
        }

    monkeypatch.setattr(
        "app.services.va_performance_coach.OpenAIResponsesClient.create_structured_response",
        structured_response,
    )
    start = datetime(2026, 8, 22, 13, tzinfo=UTC)
    first_snapshot = _snapshot()
    first_snapshot["provider_agent"]["stonegate_user_name"] = "Austin Dugger"
    second_snapshot = json.loads(json.dumps(first_snapshot))
    second_snapshot["provider_agent"]["name"] = "Different Display Name"
    second_snapshot["provider_agent"]["stonegate_user_name"] = "Different User Name"

    first = generate_va_performance_coaching_report(
        db_session,
        principal,
        _settings(),
        provider_agent_id="agent-17",
        range_start=start,
        range_end=start + timedelta(hours=8),
        performance_snapshot=first_snapshot,
    )
    second = generate_va_performance_coaching_report(
        db_session,
        principal,
        _settings(),
        provider_agent_id="agent-17",
        range_start=start,
        range_end=start + timedelta(hours=8),
        performance_snapshot=second_snapshot,
    )

    assert len(calls) == 1
    assert first.run_id == second.run_id
    assert second.reused is True
    assert "Richard" not in calls[0]["user_prompt"]
    assert "Austin Dugger" not in calls[0]["user_prompt"]
    assert "agent-17" in calls[0]["user_prompt"]


def test_semantic_retry_accumulates_usage_from_every_charged_response(
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    principal = _foundation(db_session)
    calls = 0

    def structured_response(
        *_args: object,
        **_kwargs: Any,
    ) -> tuple[dict[str, Any], dict[str, int]]:
        nonlocal calls
        calls += 1
        output = _valid_output()
        if calls == 1:
            output["summary"]["evidence_refs"] = ["metrics.not_supplied"]
            return output, {
                "input_tokens": 100,
                "output_tokens": 50,
                "total_tokens": 150,
            }
        return output, {
            "input_tokens": 200,
            "output_tokens": 75,
            "total_tokens": 275,
        }

    monkeypatch.setattr(
        "app.services.va_performance_coach.OpenAIResponsesClient.create_structured_response",
        structured_response,
    )
    start = datetime(2026, 8, 22, 13, tzinfo=UTC)
    report = generate_va_performance_coaching_report(
        db_session,
        principal,
        _settings(),
        provider_agent_id="agent-17",
        range_start=start,
        range_end=start + timedelta(hours=8),
        performance_snapshot=_snapshot(),
    )

    run = db_session.get(AiRunLog, report.run_id)
    assert run is not None
    assert calls == 2
    assert run.input_tokens == 300
    assert run.output_tokens == 125
    assert run.total_tokens == 425
    assert run.cost_microusd == 5_250
    assert run.run_metadata is not None
    assert run.run_metadata["model_attempts"] == 2


@pytest.mark.parametrize(
    ("mutate", "expected_error"),
    [
        (
            lambda output: output["next_shift_actions"][0].update(
                {"evidence_refs": ["metrics.invented"]}
            ),
            "cited evidence that was not supplied",
        ),
        (
            lambda output: output["next_shift_actions"][0].update(
                {"action": "Fire the VA because this call was weak."}
            ),
            "employment-decision boundary",
        ),
        (
            lambda output: output["summary"].update({"text": "The VA worked exactly 8 hours."}),
            "unsupported exact work hours",
        ),
    ],
)
def test_generate_blocks_unsupported_or_employment_outputs(
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
    mutate: Any,
    expected_error: str,
) -> None:
    principal = _foundation(db_session)

    def structured_response(
        *_args: object,
        **_kwargs: Any,
    ) -> tuple[dict[str, Any], dict[str, int]]:
        output = _valid_output()
        mutate(output)
        return output, {"input_tokens": 100, "output_tokens": 50, "total_tokens": 150}

    monkeypatch.setattr(
        "app.services.va_performance_coach.OpenAIResponsesClient.create_structured_response",
        structured_response,
    )
    start = datetime(2026, 8, 22, 13, tzinfo=UTC)

    with pytest.raises(VaPerformanceCoachError, match=expected_error) as exc_info:
        generate_va_performance_coaching_report(
            db_session,
            principal,
            _settings(),
            provider_agent_id="agent-17",
            range_start=start,
            range_end=start + timedelta(hours=8),
            performance_snapshot=_snapshot(),
        )

    run = db_session.scalar(select(AiRunLog).where(AiRunLog.capability_key == CAPABILITY_KEY))
    assert run is not None
    assert run.id == exc_info.value.run_id
    assert run.status == "failed"
    assert run.output_summary is None
    assert expected_error in (run.error_message or "")
    assert run.attempt_number == 1
    assert run.run_metadata is not None
    assert run.run_metadata["generation_attempt"] == 1
    assert run.run_metadata["model_attempts"] == 2
    assert run.run_metadata["coaching_report"] is None


def test_failed_snapshot_retries_then_reuses_successful_attempt(
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    principal = _foundation(db_session)
    calls = 0

    def structured_response(
        *_args: object,
        **_kwargs: Any,
    ) -> tuple[dict[str, Any], dict[str, int]]:
        nonlocal calls
        calls += 1
        if calls <= 2:
            raise OpenAIClientError("Provider temporarily unavailable.")
        return _valid_output(), {
            "input_tokens": 500,
            "output_tokens": 150,
            "total_tokens": 650,
        }

    monkeypatch.setattr(
        "app.services.va_performance_coach.OpenAIResponsesClient.create_structured_response",
        structured_response,
    )
    start = datetime(2026, 8, 22, 13, tzinfo=UTC)

    def generate() -> Any:
        return generate_va_performance_coaching_report(
            db_session,
            principal,
            _settings(),
            provider_agent_id="agent-17",
            range_start=start,
            range_end=start + timedelta(hours=8),
            performance_snapshot=_snapshot(),
        )

    with pytest.raises(VaPerformanceCoachError, match="temporarily unavailable"):
        generate()
    runtime = db_session.scalar(select(AiRuntimePolicy))
    assert runtime is not None
    assert runtime.consecutive_failure_count == 1
    assert runtime.circuit_open_until is None
    recovered = generate()
    db_session.refresh(runtime)
    assert runtime.consecutive_failure_count == 0
    assert runtime.circuit_open_until is None
    reused = generate()

    runs = list(
        db_session.scalars(
            select(AiRunLog)
            .where(AiRunLog.capability_key == CAPABILITY_KEY)
            .order_by(AiRunLog.attempt_number)
        )
    )
    assert calls == 3
    assert [(run.attempt_number, run.status) for run in runs] == [
        (1, "failed"),
        (2, "needs_review"),
    ]
    assert recovered.run_id == runs[1].id
    assert recovered.reused is False
    assert reused.run_id == recovered.run_id
    assert reused.reused is True


def test_identical_failed_snapshot_stops_after_three_generation_attempts(
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    principal = _foundation(db_session)
    calls = 0

    def structured_response(
        *_args: object, **_kwargs: Any
    ) -> tuple[dict[str, Any], dict[str, int]]:
        nonlocal calls
        calls += 1
        raise OpenAIClientError("Provider remains unavailable.")

    monkeypatch.setattr(
        "app.services.va_performance_coach.OpenAIResponsesClient.create_structured_response",
        structured_response,
    )
    start = datetime(2026, 8, 22, 13, tzinfo=UTC)

    def generate() -> Any:
        return generate_va_performance_coaching_report(
            db_session,
            principal,
            _settings(),
            provider_agent_id="agent-17",
            range_start=start,
            range_end=start + timedelta(hours=8),
            performance_snapshot=_snapshot(),
        )

    for _ in range(4):
        with pytest.raises(VaPerformanceCoachError, match="remains unavailable"):
            generate()

    runs = list(
        db_session.scalars(
            select(AiRunLog)
            .where(AiRunLog.capability_key == CAPABILITY_KEY)
            .order_by(AiRunLog.attempt_number)
        )
    )
    assert calls == 6
    assert [run.attempt_number for run in runs] == [1, 2, 3]
    assert all(run.status == "failed" for run in runs)


def test_blocked_snapshot_can_retry_and_then_reuse_success(
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    principal = _foundation(db_session)
    agent = db_session.scalar(
        select(AiAgentDefinition).where(AiAgentDefinition.key == "prospecting_intelligence")
    )
    assert agent is not None
    agent.max_cost_microusd_per_run = 1
    db_session.commit()
    calls = 0

    def structured_response(
        *_args: object,
        **_kwargs: Any,
    ) -> tuple[dict[str, Any], dict[str, int]]:
        nonlocal calls
        calls += 1
        return _valid_output(), {
            "input_tokens": 1_000,
            "output_tokens": 200,
            "total_tokens": 1_200,
        }

    monkeypatch.setattr(
        "app.services.va_performance_coach.OpenAIResponsesClient.create_structured_response",
        structured_response,
    )
    start = datetime(2026, 8, 22, 13, tzinfo=UTC)

    def generate() -> Any:
        return generate_va_performance_coaching_report(
            db_session,
            principal,
            _settings(),
            provider_agent_id="agent-17",
            range_start=start,
            range_end=start + timedelta(hours=8),
            performance_snapshot=_snapshot(),
        )

    with pytest.raises(VaPerformanceCoachError, match="per-run cost limit"):
        generate()
    blocked_run = db_session.scalar(
        select(AiRunLog).where(AiRunLog.capability_key == CAPABILITY_KEY)
    )
    assert blocked_run is not None
    assert blocked_run.status == "blocked"
    assert blocked_run.output_summary is None
    assert blocked_run.input_tokens == 1_000
    assert blocked_run.output_tokens == 200
    assert blocked_run.total_tokens == 1_200
    assert blocked_run.cost_microusd is not None
    assert blocked_run.run_metadata is not None
    assert blocked_run.run_metadata["coaching_report"] is None
    assert blocked_run.run_metadata["output_validated"] is True
    assert blocked_run.run_metadata["output_discarded"] is True
    discarded_hash = blocked_run.run_metadata["discarded_output_sha256"]
    assert isinstance(discarded_hash, str) and len(discarded_hash) == 64
    assert "Calling activity was high" not in json.dumps(blocked_run.run_metadata)
    assert (
        get_latest_va_performance_coaching_report(
            db_session,
            principal,
            provider_agent_id="agent-17",
        )
        is None
    )
    runtime = db_session.scalar(select(AiRuntimePolicy))
    assert runtime is not None
    assert runtime.consecutive_failure_count == 0
    agent.max_cost_microusd_per_run = 100_000
    db_session.commit()
    recovered = generate()
    reused = generate()

    runs = list(
        db_session.scalars(
            select(AiRunLog)
            .where(AiRunLog.capability_key == CAPABILITY_KEY)
            .order_by(AiRunLog.attempt_number)
        )
    )
    assert calls == 2
    assert [(run.attempt_number, run.status) for run in runs] == [
        (1, "blocked"),
        (2, "needs_review"),
    ]
    assert recovered.run_id == runs[1].id
    assert reused.run_id == recovered.run_id
    assert reused.reused is True


def test_unpriced_model_discards_output_and_holds_the_governed_daily_budget(
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    principal = _foundation(db_session)
    runtime = db_session.scalar(select(AiRuntimePolicy))
    agent = db_session.scalar(
        select(AiAgentDefinition).where(AiAgentDefinition.key == "prospecting_intelligence")
    )
    assert runtime is not None
    assert agent is not None
    runtime.default_model = "unpriced-coaching-model"
    runtime.max_daily_cost_microusd = 100_000
    agent.max_daily_cost_microusd = 100_000
    db_session.commit()
    calls = 0

    def structured_response(
        *_args: object,
        **_kwargs: Any,
    ) -> tuple[dict[str, Any], dict[str, int]]:
        nonlocal calls
        calls += 1
        return _valid_output(), {
            "input_tokens": 100,
            "output_tokens": 50,
            "total_tokens": 150,
        }

    monkeypatch.setattr(
        "app.services.va_performance_coach.OpenAIResponsesClient.create_structured_response",
        structured_response,
    )
    start = datetime(2026, 8, 22, 13, tzinfo=UTC)

    with pytest.raises(VaPerformanceCoachError, match="cost could not be verified") as exc_info:
        generate_va_performance_coaching_report(
            db_session,
            principal,
            _settings(),
            provider_agent_id="agent-17",
            range_start=start,
            range_end=start + timedelta(hours=8),
            performance_snapshot=_snapshot(),
        )

    run = db_session.get(AiRunLog, exc_info.value.run_id)
    assert run is not None
    assert run.status == "blocked"
    assert run.budget_status == "cost_unverifiable"
    assert run.cost_microusd is None
    assert run.input_tokens == 100
    assert run.output_tokens == 50
    assert run.output_summary is None
    assert run.run_metadata is not None
    assert run.run_metadata["pricing_status"] == "unpriced_model"
    assert run.run_metadata["coaching_report"] is None
    assert run.run_metadata["output_validated"] is True
    assert run.run_metadata["output_discarded"] is True
    assert "Calling activity was high" not in json.dumps(run.run_metadata)

    second_snapshot = _snapshot()
    second_snapshot["provider_agent"] = {"id": "agent-18", "name": "Jordan"}
    with pytest.raises(VaPerformanceCoachError, match="daily budget"):
        generate_va_performance_coaching_report(
            db_session,
            principal,
            _settings(),
            provider_agent_id="agent-18",
            range_start=start,
            range_end=start + timedelta(hours=8),
            performance_snapshot=second_snapshot,
        )
    assert calls == 1


def test_missing_usage_discards_valid_output_as_cost_unverifiable(
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    principal = _foundation(db_session)

    def structured_response(
        *_args: object,
        **_kwargs: Any,
    ) -> tuple[dict[str, Any], dict[str, int | None]]:
        return _valid_output(), {
            "input_tokens": None,
            "output_tokens": None,
            "total_tokens": None,
        }

    monkeypatch.setattr(
        "app.services.va_performance_coach.OpenAIResponsesClient.create_structured_response",
        structured_response,
    )
    start = datetime(2026, 8, 22, 13, tzinfo=UTC)

    with pytest.raises(VaPerformanceCoachError, match="cost could not be verified") as exc_info:
        generate_va_performance_coaching_report(
            db_session,
            principal,
            _settings(),
            provider_agent_id="agent-17",
            range_start=start,
            range_end=start + timedelta(hours=8),
            performance_snapshot=_snapshot(),
        )

    run = db_session.get(AiRunLog, exc_info.value.run_id)
    assert run is not None
    assert run.status == "blocked"
    assert run.budget_status == "cost_unverifiable"
    assert run.cost_microusd is None
    assert run.input_tokens is None
    assert run.output_tokens is None
    assert run.total_tokens is None
    assert run.output_summary is None
    assert run.run_metadata is not None
    assert run.run_metadata["pricing_status"] == "usage_unavailable"
    assert run.run_metadata["pricing_components"][0]["input_tokens"] is None
    assert run.run_metadata["coaching_report"] is None
    assert run.run_metadata["output_discarded"] is True


@pytest.mark.parametrize("missing_usage_attempt", [1, 2])
def test_missing_usage_in_one_retry_poisons_aggregate_cost_verification(
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
    missing_usage_attempt: int,
) -> None:
    principal = _foundation(db_session)
    calls = 0

    def structured_response(
        *_args: object,
        **_kwargs: Any,
    ) -> tuple[dict[str, Any], dict[str, int | None]]:
        nonlocal calls
        calls += 1
        output = _valid_output()
        if calls == 1:
            output["summary"]["evidence_refs"] = ["metrics.not_supplied"]
        if calls == missing_usage_attempt:
            attempt_usage = {
                "input_tokens": None,
                "output_tokens": None,
                "total_tokens": None,
            }
        else:
            attempt_usage = {
                "input_tokens": 200,
                "output_tokens": 75,
                "total_tokens": 275,
            }
        return output, attempt_usage

    monkeypatch.setattr(
        "app.services.va_performance_coach.OpenAIResponsesClient.create_structured_response",
        structured_response,
    )
    start = datetime(2026, 8, 22, 13, tzinfo=UTC)

    with pytest.raises(VaPerformanceCoachError, match="cost could not be verified") as exc_info:
        generate_va_performance_coaching_report(
            db_session,
            principal,
            _settings(),
            provider_agent_id="agent-17",
            range_start=start,
            range_end=start + timedelta(hours=8),
            performance_snapshot=_snapshot(),
        )

    assert calls == 2
    run = db_session.get(AiRunLog, exc_info.value.run_id)
    assert run is not None
    assert run.status == "blocked"
    assert run.budget_status == "cost_unverifiable"
    assert run.input_tokens is None
    assert run.output_tokens is None
    assert run.total_tokens is None
    assert run.cost_microusd is None
    assert run.run_metadata is not None
    assert run.run_metadata["pricing_status"] == "usage_unavailable"
    assert run.run_metadata["coaching_report"] is None


@pytest.mark.parametrize(
    ("model_name", "usage", "pricing_status"),
    [
        (
            "unpriced-invalid-output-model",
            {"input_tokens": 100, "output_tokens": 50, "total_tokens": 150},
            "unpriced_model",
        ),
        (
            "gpt-5.6-sol",
            {"input_tokens": None, "output_tokens": None, "total_tokens": None},
            "usage_unavailable",
        ),
    ],
)
def test_invalid_output_with_unverifiable_provider_cost_retains_budget_hold(
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
    model_name: str,
    usage: dict[str, int | None],
    pricing_status: str,
) -> None:
    principal = _foundation(db_session)
    runtime = db_session.scalar(select(AiRuntimePolicy))
    agent = db_session.scalar(
        select(AiAgentDefinition).where(AiAgentDefinition.key == "prospecting_intelligence")
    )
    assert runtime is not None and agent is not None
    runtime.default_model = model_name
    runtime.max_daily_cost_microusd = 100_000
    agent.max_daily_cost_microusd = 100_000
    db_session.commit()
    calls = 0

    def structured_response(
        *_args: object,
        **_kwargs: Any,
    ) -> tuple[dict[str, Any], dict[str, int | None]]:
        nonlocal calls
        calls += 1
        output = _valid_output()
        output["summary"]["evidence_refs"] = ["metrics.not_supplied"]
        return output, usage

    monkeypatch.setattr(
        "app.services.va_performance_coach.OpenAIResponsesClient.create_structured_response",
        structured_response,
    )
    start = datetime(2026, 8, 22, 13, tzinfo=UTC)

    with pytest.raises(VaPerformanceCoachError, match="cited evidence") as exc_info:
        generate_va_performance_coaching_report(
            db_session,
            principal,
            _settings(),
            provider_agent_id="agent-17",
            range_start=start,
            range_end=start + timedelta(hours=8),
            performance_snapshot=_snapshot(),
        )

    run = db_session.get(AiRunLog, exc_info.value.run_id)
    assert run is not None
    assert run.status == "failed"
    assert run.budget_status == "cost_unverifiable"
    assert run.cost_microusd is None
    assert run.output_summary is None
    assert run.run_metadata is not None
    assert run.run_metadata["pricing_status"] == pricing_status
    assert run.run_metadata["coaching_report"] is None

    other_snapshot = _snapshot()
    other_snapshot["provider_agent"] = {"id": "agent-18", "name": "Jordan"}
    with pytest.raises(VaPerformanceCoachError, match="daily budget"):
        generate_va_performance_coaching_report(
            db_session,
            principal,
            _settings(),
            provider_agent_id="agent-18",
            range_start=start,
            range_end=start + timedelta(hours=8),
            performance_snapshot=other_snapshot,
        )
    assert calls == 2


def test_invalid_output_over_per_run_limit_preserves_failed_status_and_overrun_accounting(
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    principal = _foundation(db_session)
    agent = db_session.scalar(
        select(AiAgentDefinition).where(AiAgentDefinition.key == "prospecting_intelligence")
    )
    assert agent is not None
    agent.max_cost_microusd_per_run = 1
    db_session.commit()

    def structured_response(
        *_args: object,
        **_kwargs: Any,
    ) -> tuple[dict[str, Any], dict[str, int]]:
        output = _valid_output()
        output["summary"]["evidence_refs"] = ["metrics.not_supplied"]
        return output, {
            "input_tokens": 100,
            "output_tokens": 50,
            "total_tokens": 150,
        }

    monkeypatch.setattr(
        "app.services.va_performance_coach.OpenAIResponsesClient.create_structured_response",
        structured_response,
    )
    start = datetime(2026, 8, 22, 13, tzinfo=UTC)

    with pytest.raises(VaPerformanceCoachError, match="cited evidence") as exc_info:
        generate_va_performance_coaching_report(
            db_session,
            principal,
            _settings(),
            provider_agent_id="agent-17",
            range_start=start,
            range_end=start + timedelta(hours=8),
            performance_snapshot=_snapshot(),
        )

    run = db_session.get(AiRunLog, exc_info.value.run_id)
    assert run is not None
    assert run.status == "failed"
    assert run.budget_status == "per_run_limit_exceeded"
    assert run.cost_microusd is not None and run.cost_microusd > 1
    assert run.output_summary is None
    assert run.run_metadata is not None
    assert run.run_metadata["budget_status"] == "per_run_limit_exceeded"
    assert run.run_metadata["coaching_report"] is None


def test_large_report_uses_bounded_summary_and_reads_full_metadata_output(
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    principal = _foundation(db_session)
    output = _valid_output()
    output["summary"]["text"] = "S" * 450
    output["strengths"] = [
        {
            "observation": "A" * 260,
            "evidence_refs": ["metrics.outbound_calls"] * 4,
        }
        for _ in range(3)
    ]
    output["concerns"] = [
        {
            "observation": "C" * 260,
            "evidence_refs": ["metrics.verified_qualified_leads"] * 4,
        }
        for _ in range(3)
    ]
    output["next_shift_actions"] = [
        {
            "action": "N" * 220,
            "rationale": "R" * 260,
            "evidence_refs": ["cdr-102"] * 4,
        }
        for _ in range(3)
    ]
    output["calls_to_review"] = [
        {
            "provider_event_id": "cdr-102",
            "reason": "V" * 260,
            "evidence_refs": ["cdr-102"] * 4,
        }
        for _ in range(4)
    ]
    output["comparison_caveats"] = [
        {
            "caveat": "L" * 260,
            "evidence_refs": ["comparison_metrics.campaign_peer_sample_size"] * 4,
        }
        for _ in range(3)
    ]
    output["confidence"]["rationale"] = "Q" * 260

    def structured_response(
        *_args: object,
        **_kwargs: Any,
    ) -> tuple[dict[str, Any], dict[str, int]]:
        return output, {"input_tokens": 500, "output_tokens": 150, "total_tokens": 650}

    monkeypatch.setattr(
        "app.services.va_performance_coach.OpenAIResponsesClient.create_structured_response",
        structured_response,
    )
    start = datetime(2026, 8, 22, 13, tzinfo=UTC)
    report = generate_va_performance_coaching_report(
        db_session,
        principal,
        _settings(),
        provider_agent_id="agent-17",
        range_start=start,
        range_end=start + timedelta(hours=8),
        performance_snapshot=_snapshot(),
    )

    run = db_session.get(AiRunLog, report.run_id)
    assert run is not None and run.output_summary is not None
    assert len(run.output_summary) <= 4_000
    assert json.loads(run.output_summary)["full_output_reference"] == (
        "run_metadata.coaching_report"
    )
    assert run.run_metadata is not None
    assert run.run_metadata["coaching_report"] == output
    assert report.output == output
    latest = get_latest_va_performance_coaching_report(
        db_session,
        principal,
        provider_agent_id="agent-17",
    )
    assert latest is not None
    assert latest.output == output


@pytest.mark.parametrize(
    ("runtime_updates", "expected_error"),
    [
        ({"provider_status": "disabled"}, "provider runtime is disabled"),
        ({"emergency_stop": True}, "provider runtime is disabled"),
        (
            {"circuit_open_until": datetime.now(UTC) + timedelta(hours=1)},
            "circuit breaker is open",
        ),
        ({"max_requests_per_minute": 0}, "rate limit has been reached"),
        ({"max_daily_cost_microusd": 0}, "daily cost limit has been reached"),
        ({"max_context_characters": 10}, "context exceeds the organization limit"),
    ],
)
def test_runtime_governance_blocks_before_provider_spend(
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
    runtime_updates: dict[str, Any],
    expected_error: str,
) -> None:
    principal = _foundation(db_session)
    runtime = db_session.scalar(select(AiRuntimePolicy))
    assert runtime is not None
    for field, value in runtime_updates.items():
        setattr(runtime, field, value)
    db_session.commit()
    calls = 0

    def structured_response(
        *_args: object,
        **_kwargs: Any,
    ) -> tuple[dict[str, Any], dict[str, int]]:
        nonlocal calls
        calls += 1
        return _valid_output(), {}

    monkeypatch.setattr(
        "app.services.va_performance_coach.OpenAIResponsesClient.create_structured_response",
        structured_response,
    )
    start = datetime(2026, 8, 22, 13, tzinfo=UTC)
    with pytest.raises(VaPerformanceCoachError, match=expected_error):
        generate_va_performance_coaching_report(
            db_session,
            principal,
            _settings(),
            provider_agent_id="agent-17",
            range_start=start,
            range_end=start + timedelta(hours=8),
            performance_snapshot=_snapshot(),
        )

    assert calls == 0
    run = db_session.scalar(select(AiRunLog).where(AiRunLog.capability_key == CAPABILITY_KEY))
    assert run is not None
    assert run.status == "blocked"
    assert run.run_metadata is not None
    assert run.run_metadata["model_attempts"] == 0
    assert run.run_metadata["reservation_status"] == "finalized"


def test_capability_policy_is_enforced_and_admin_limits_are_preserved(
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    principal = _foundation(db_session)
    runtime = db_session.scalar(select(AiRuntimePolicy))
    agent = db_session.scalar(select(AiAgentDefinition))
    assert runtime is not None and agent is not None
    runtime.escalation_model = "gpt-5.6-terra"
    capability = db_session.scalar(
        select(AiCapabilityRuntimePolicy).where(
            AiCapabilityRuntimePolicy.capability_key == CAPABILITY_KEY
        )
    )
    assert capability is not None
    capability.status = "disabled"
    capability.model_route = "escalation"
    capability.output_schema = {}
    capability.allowed_tool_keys = ["unsafe.write"]
    capability.max_output_tokens = 777
    capability.max_cost_microusd_per_run = 55_000
    capability.requires_human_review = False
    db_session.commit()
    calls: list[dict[str, Any]] = []

    def structured_response(
        *_args: object,
        **kwargs: Any,
    ) -> tuple[dict[str, Any], dict[str, int]]:
        calls.append(kwargs)
        return _valid_output(), {
            "input_tokens": 100,
            "output_tokens": 50,
            "total_tokens": 150,
        }

    monkeypatch.setattr(
        "app.services.va_performance_coach.OpenAIResponsesClient.create_structured_response",
        structured_response,
    )
    start = datetime(2026, 8, 22, 13, tzinfo=UTC)

    def generate() -> Any:
        return generate_va_performance_coaching_report(
            db_session,
            principal,
            _settings(),
            provider_agent_id="agent-17",
            range_start=start,
            range_end=start + timedelta(hours=8),
            performance_snapshot=_snapshot(),
        )

    for _ in range(3):
        with pytest.raises(VaPerformanceCoachError, match="capability runtime is disabled"):
            generate()
    assert calls == []
    db_session.refresh(capability)
    assert capability.status == "disabled"
    assert capability.model_route == "escalation"
    assert capability.max_output_tokens == 777
    assert capability.max_cost_microusd_per_run == 55_000
    assert capability.output_schema == {}
    assert capability.allowed_tool_keys == ["unsafe.write"]
    assert capability.requires_human_review is False
    blocked_runs = list(
        db_session.scalars(select(AiRunLog).where(AiRunLog.capability_key == CAPABILITY_KEY))
    )
    assert len(blocked_runs) == 1
    assert blocked_runs[0].run_metadata is not None
    assert blocked_runs[0].run_metadata["generation_attempt"] == 0
    assert blocked_runs[0].run_metadata["model_attempts"] == 0

    capability.status = "enabled"
    db_session.commit()
    report = generate()
    assert report.status == "needs_review"
    assert calls[0]["model"] == "gpt-5.6-terra"
    assert calls[0]["max_output_tokens"] == 777
    run = db_session.get(AiRunLog, report.run_id)
    assert run is not None
    assert run.attempt_number == 1
    assert run.budget_limit_microusd == 55_000


def test_concurrent_same_agent_run_is_capped_by_remaining_reserved_daily_budget(
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    principal = _foundation(db_session)
    runtime = db_session.scalar(select(AiRuntimePolicy))
    agent = db_session.scalar(
        select(AiAgentDefinition).where(AiAgentDefinition.key == "prospecting_intelligence")
    )
    assert runtime is not None and agent is not None
    runtime.max_daily_cost_microusd = 1_000_000
    agent.max_daily_cost_microusd = 150_000
    db_session.commit()
    start = datetime(2026, 8, 22, 13, tzinfo=UTC)
    calls = 0
    nested_run_id = None

    def generate(provider_agent_id: str, outbound_calls: int) -> Any:
        snapshot = _snapshot()
        snapshot["metrics"]["outbound_calls"] = outbound_calls
        return generate_va_performance_coaching_report(
            db_session,
            principal,
            _settings(),
            provider_agent_id=provider_agent_id,
            range_start=start,
            range_end=start + timedelta(hours=8),
            performance_snapshot=snapshot,
        )

    def structured_response(
        *_args: object,
        **_kwargs: Any,
    ) -> tuple[dict[str, Any], dict[str, int]]:
        nonlocal calls, nested_run_id
        calls += 1
        if calls == 1:
            nested = generate("agent-18", 175)
            nested_run_id = nested.run_id
        return _valid_output(), {
            "input_tokens": 100,
            "output_tokens": 50,
            "total_tokens": 150,
        }

    monkeypatch.setattr(
        "app.services.va_performance_coach.OpenAIResponsesClient.create_structured_response",
        structured_response,
    )
    outer = generate("agent-17", 174)

    runs = list(
        db_session.scalars(select(AiRunLog).where(AiRunLog.capability_key == CAPABILITY_KEY))
    )
    assert calls == 2
    assert len(runs) == 2
    by_provider = {run.run_metadata["provider_agent_id"]: run for run in runs}
    assert by_provider["agent-17"].id == outer.run_id
    assert by_provider["agent-17"].budget_limit_microusd == 100_000
    assert by_provider["agent-18"].id == nested_run_id
    assert by_provider["agent-18"].budget_limit_microusd == 50_000
    nested_guard = by_provider["agent-18"].run_metadata["daily_budget_guard"]
    assert nested_guard["agent_actual_microusd"] == 0
    assert nested_guard["agent_reserved_microusd"] == 100_000
    assert nested_guard["agent_remaining_microusd"] == 50_000
    assert nested_guard["effective_run_limit_microusd"] == 50_000


@pytest.mark.parametrize(
    ("other_agent_reservation", "expected_limit", "outcome"),
    [
        (120_000, 30_000, "success"),
        (150_000, 0, "preflight_block"),
        (149_999, 1, "cost_block"),
    ],
)
def test_different_agent_reservation_reduces_organization_daily_capacity(
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
    other_agent_reservation: int,
    expected_limit: int,
    outcome: str,
) -> None:
    principal = _foundation(db_session)
    runtime = db_session.scalar(select(AiRuntimePolicy))
    assert runtime is not None
    runtime.max_daily_cost_microusd = 150_000
    other_agent = AiAgentDefinition(
        organization_id=principal.organization_id,
        key="other_governed_agent",
        name="Other governed agent",
        description="Concurrent organization-budget test agent.",
        status="active",
        model_name="gpt-5.6-sol",
        risk_level="medium",
        requires_human_approval=True,
        autonomy_level="observe",
        max_cost_microusd_per_run=other_agent_reservation,
        max_daily_cost_microusd=1_000_000,
        max_attempts=1,
        rollback_owner_user_id=principal.user_id,
    )
    db_session.add(other_agent)
    db_session.flush()
    db_session.add(
        AiRunLog(
            organization_id=principal.organization_id,
            agent_definition_id=other_agent.id,
            status="in_progress",
            model_name="gpt-5.6-sol",
            input_summary="Concurrent governed request",
            started_at=datetime.now(UTC),
            run_metadata={"reservation_status": "active"},
            requested_by_user_id=principal.user_id,
            execution_mode="production",
            capability_key="other.concurrent_capability",
            attempt_number=1,
            idempotency_key=f"other-reservation-{other_agent_reservation}",
            budget_limit_microusd=other_agent_reservation,
            budget_status="reserved",
            trace_status="unreviewed",
            rollback_status="not_required",
        )
    )
    db_session.commit()
    calls = 0

    def structured_response(
        *_args: object,
        **_kwargs: Any,
    ) -> tuple[dict[str, Any], dict[str, int]]:
        nonlocal calls
        calls += 1
        return _valid_output(), {
            "input_tokens": 100,
            "output_tokens": 50,
            "total_tokens": 150,
        }

    monkeypatch.setattr(
        "app.services.va_performance_coach.OpenAIResponsesClient.create_structured_response",
        structured_response,
    )
    start = datetime(2026, 8, 22, 13, tzinfo=UTC)
    if outcome == "preflight_block":
        with pytest.raises(VaPerformanceCoachError, match="exhausted or fully reserved"):
            generate_va_performance_coaching_report(
                db_session,
                principal,
                _settings(),
                provider_agent_id="agent-17",
                range_start=start,
                range_end=start + timedelta(hours=8),
                performance_snapshot=_snapshot(),
            )
        assert calls == 0
        blocked_run = db_session.scalar(
            select(AiRunLog).where(AiRunLog.capability_key == CAPABILITY_KEY)
        )
        assert blocked_run is not None
        assert blocked_run.budget_limit_microusd == 0
    elif outcome == "cost_block":
        with pytest.raises(VaPerformanceCoachError, match="per-run cost limit"):
            generate_va_performance_coaching_report(
                db_session,
                principal,
                _settings(),
                provider_agent_id="agent-17",
                range_start=start,
                range_end=start + timedelta(hours=8),
                performance_snapshot=_snapshot(),
            )
        assert calls == 1
        blocked_run = db_session.scalar(
            select(AiRunLog).where(AiRunLog.capability_key == CAPABILITY_KEY)
        )
        assert blocked_run is not None
        assert blocked_run.status == "blocked"
        assert blocked_run.budget_limit_microusd == expected_limit
        assert blocked_run.output_summary is None
        assert blocked_run.run_metadata is not None
        assert blocked_run.run_metadata["coaching_report"] is None
        assert blocked_run.run_metadata["output_discarded"] is True
    else:
        report = generate_va_performance_coaching_report(
            db_session,
            principal,
            _settings(),
            provider_agent_id="agent-17",
            range_start=start,
            range_end=start + timedelta(hours=8),
            performance_snapshot=_snapshot(),
        )
        run = db_session.get(AiRunLog, report.run_id)
        assert run is not None
        assert calls == 1
        assert run.budget_limit_microusd == expected_limit
        assert run.run_metadata is not None
        guard = run.run_metadata["daily_budget_guard"]
        assert guard["organization_reserved_microusd"] == other_agent_reservation
        assert guard["organization_remaining_microusd"] == expected_limit
        assert guard["effective_run_limit_microusd"] == expected_limit


def test_missing_capability_requires_governed_install_and_is_not_created(
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    principal = _foundation(db_session)
    capability = db_session.scalar(
        select(AiCapabilityRuntimePolicy).where(
            AiCapabilityRuntimePolicy.capability_key == CAPABILITY_KEY
        )
    )
    assert capability is not None
    db_session.delete(capability)
    db_session.commit()
    calls = 0

    def structured_response(
        *_args: object,
        **_kwargs: Any,
    ) -> tuple[dict[str, Any], dict[str, int]]:
        nonlocal calls
        calls += 1
        return _valid_output(), {}

    monkeypatch.setattr(
        "app.services.va_performance_coach.OpenAIResponsesClient.create_structured_response",
        structured_response,
    )
    start = datetime(2026, 8, 22, 13, tzinfo=UTC)

    with pytest.raises(ValueError, match="AI administrator.*governed AI runtime installation"):
        generate_va_performance_coaching_report(
            db_session,
            principal,
            _settings(),
            provider_agent_id="agent-17",
            range_start=start,
            range_end=start + timedelta(hours=8),
            performance_snapshot=_snapshot(),
        )

    assert calls == 0
    assert (
        db_session.scalar(
            select(AiCapabilityRuntimePolicy).where(
                AiCapabilityRuntimePolicy.capability_key == CAPABILITY_KEY
            )
        )
        is None
    )
    assert (
        db_session.scalar(select(AiRunLog).where(AiRunLog.capability_key == CAPABILITY_KEY)) is None
    )


def test_committed_reservation_blocks_an_identical_nested_request(
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    principal = _foundation(db_session)
    start = datetime(2026, 8, 22, 13, tzinfo=UTC)
    calls = 0

    def generate() -> Any:
        return generate_va_performance_coaching_report(
            db_session,
            principal,
            _settings(),
            provider_agent_id="agent-17",
            range_start=start,
            range_end=start + timedelta(hours=8),
            performance_snapshot=_snapshot(),
        )

    def structured_response(
        *_args: object,
        **_kwargs: Any,
    ) -> tuple[dict[str, Any], dict[str, int]]:
        nonlocal calls
        calls += 1
        reservation = db_session.scalar(
            select(AiRunLog).where(AiRunLog.capability_key == CAPABILITY_KEY)
        )
        assert reservation is not None
        assert reservation.status == "in_progress"
        assert reservation.completed_at is None
        with pytest.raises(VaPerformanceCoachError, match="already being generated"):
            generate()
        return _valid_output(), {
            "input_tokens": 100,
            "output_tokens": 50,
            "total_tokens": 150,
        }

    monkeypatch.setattr(
        "app.services.va_performance_coach.OpenAIResponsesClient.create_structured_response",
        structured_response,
    )
    report = generate()

    assert calls == 1
    assert report.status == "needs_review"
    run = db_session.scalar(select(AiRunLog).where(AiRunLog.capability_key == CAPABILITY_KEY))
    assert run is not None
    assert run.status == "needs_review"


def test_late_stale_request_cannot_finalize_after_recovery_succeeds(
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    principal = _foundation(db_session)
    start = datetime(2026, 8, 22, 13, tzinfo=UTC)
    calls = 0
    recovered_run_id = None

    def generate() -> Any:
        return generate_va_performance_coaching_report(
            db_session,
            principal,
            _settings(),
            provider_agent_id="agent-17",
            range_start=start,
            range_end=start + timedelta(hours=8),
            performance_snapshot=_snapshot(),
        )

    def structured_response(
        *_args: object,
        **_kwargs: Any,
    ) -> tuple[dict[str, Any], dict[str, int]]:
        nonlocal calls, recovered_run_id
        calls += 1
        if calls == 1:
            first_reservation = db_session.scalar(
                select(AiRunLog).where(
                    AiRunLog.capability_key == CAPABILITY_KEY,
                    AiRunLog.attempt_number == 1,
                )
            )
            assert first_reservation is not None
            assert first_reservation.status == "in_progress"
            first_reservation.started_at = datetime.now(UTC) - timedelta(minutes=11)
            db_session.commit()

            recovered = generate()
            recovered_run_id = recovered.run_id
            assert recovered.status == "needs_review"

        return _valid_output(), {
            "input_tokens": 100,
            "output_tokens": 50,
            "total_tokens": 150,
        }

    monkeypatch.setattr(
        "app.services.va_performance_coach.OpenAIResponsesClient.create_structured_response",
        structured_response,
    )

    with pytest.raises(VaPerformanceCoachError, match="reservation is no longer active"):
        generate()

    runs = list(
        db_session.scalars(
            select(AiRunLog)
            .where(AiRunLog.capability_key == CAPABILITY_KEY)
            .order_by(AiRunLog.attempt_number)
        )
    )
    assert calls == 2
    assert len(runs) == 2
    assert [(run.attempt_number, run.status) for run in runs] == [
        (1, "failed"),
        (2, "needs_review"),
    ]
    assert runs[0].run_metadata is not None
    assert runs[0].run_metadata["reservation_status"] == "superseded_finalized"
    assert runs[0].run_metadata["late_provider_result_accounted"] is True
    assert runs[0].run_metadata["late_provider_result_discarded"] is True
    assert runs[0].run_metadata["coaching_report"] is None
    assert runs[0].output_summary is None
    assert runs[0].input_tokens == 100
    assert runs[0].output_tokens == 50
    assert runs[0].total_tokens == 150
    assert runs[0].cost_microusd is not None
    assert runs[1].id == recovered_run_id
    assert runs[1].cost_microusd is not None
    assert runs[0].cost_microusd == runs[1].cost_microusd
    accounted_cost = sum(run.cost_microusd or 0 for run in runs)
    assert accounted_cost == runs[0].cost_microusd + runs[1].cost_microusd

    agent = db_session.scalar(
        select(AiAgentDefinition).where(AiAgentDefinition.key == "prospecting_intelligence")
    )
    prompt = db_session.get(AiPromptVersion, runs[0].prompt_version_id)
    assert agent is not None and prompt is not None
    assert runs[0].idempotency_key is not None
    with pytest.raises(VaPerformanceCoachError, match="reservation is no longer active"):
        _persist_run(
            db_session,
            principal,
            reserved_run=runs[0],
            runtime_policy=None,
            agent=agent,
            prompt=prompt,
            idempotency_key=runs[0].idempotency_key,
            model_name=runs[0].model_name,
            status="needs_review",
            started_at=runs[0].started_at,
            input_summary=runs[0].input_summary,
            output=_valid_output(),
            usage={"input_tokens": 100, "output_tokens": 50, "total_tokens": 150},
            latency_ms=500,
            metadata=runs[0].run_metadata,
            settings=_settings(),
            error_message=None,
            generation_attempt=1,
            model_attempts=1,
            max_cost_microusd_per_run=100_000,
        )

    refreshed_runs = list(
        db_session.scalars(
            select(AiRunLog)
            .where(AiRunLog.capability_key == CAPABILITY_KEY)
            .order_by(AiRunLog.attempt_number)
        )
    )
    assert sum(run.cost_microusd or 0 for run in refreshed_runs) == accounted_cost
    assert refreshed_runs[0].status == "failed"
    assert refreshed_runs[0].output_summary is None

    runtime = db_session.scalar(select(AiRuntimePolicy))
    assert runtime is not None
    current_day_start = datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)

    def started_today(run: AiRunLog) -> bool:
        started_at = run.started_at
        if started_at.tzinfo is None:
            started_at = started_at.replace(tzinfo=UTC)
        return started_at >= current_day_start

    current_day_cost = sum(run.cost_microusd or 0 for run in refreshed_runs if started_today(run))
    assert current_day_cost > 0
    runtime.max_daily_cost_microusd = current_day_cost
    db_session.commit()
    changed_snapshot = _snapshot()
    changed_snapshot["metrics"]["outbound_calls"] = 175
    with pytest.raises(VaPerformanceCoachError, match="daily cost limit has been reached"):
        generate_va_performance_coaching_report(
            db_session,
            principal,
            _settings(),
            provider_agent_id="agent-17",
            range_start=start,
            range_end=start + timedelta(hours=8),
            performance_snapshot=changed_snapshot,
        )
    assert calls == 2


def test_stale_failure_does_not_override_recovery_success_circuit_state(
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    principal = _foundation(db_session)
    start = datetime(2026, 8, 22, 13, tzinfo=UTC)
    calls = 0

    def generate() -> Any:
        return generate_va_performance_coaching_report(
            db_session,
            principal,
            _settings(),
            provider_agent_id="agent-17",
            range_start=start,
            range_end=start + timedelta(hours=8),
            performance_snapshot=_snapshot(),
        )

    def invalid_output() -> dict[str, Any]:
        output = _valid_output()
        output["summary"]["text"] = "Dismiss the VA based on these results."
        return output

    def structured_response(
        *_args: object,
        **_kwargs: Any,
    ) -> tuple[dict[str, Any], dict[str, int]]:
        nonlocal calls
        calls += 1
        if calls == 1:
            reservation = db_session.scalar(
                select(AiRunLog).where(
                    AiRunLog.capability_key == CAPABILITY_KEY,
                    AiRunLog.attempt_number == 1,
                )
            )
            assert reservation is not None
            reservation.started_at = datetime.now(UTC) - timedelta(minutes=11)
            db_session.commit()
            winner = generate()
            assert winner.status == "needs_review"
            return invalid_output(), {
                "input_tokens": 100,
                "output_tokens": 50,
                "total_tokens": 150,
            }
        if calls == 2:
            return _valid_output(), {
                "input_tokens": 100,
                "output_tokens": 50,
                "total_tokens": 150,
            }
        return invalid_output(), {
            "input_tokens": 100,
            "output_tokens": 50,
            "total_tokens": 150,
        }

    monkeypatch.setattr(
        "app.services.va_performance_coach.OpenAIResponsesClient.create_structured_response",
        structured_response,
    )

    with pytest.raises(VaPerformanceCoachError, match="reservation is no longer active"):
        generate()

    runtime = db_session.scalar(select(AiRuntimePolicy))
    assert runtime is not None
    assert runtime.consecutive_failure_count == 0
    assert runtime.circuit_open_until is None
    runs = list(
        db_session.scalars(
            select(AiRunLog)
            .where(AiRunLog.capability_key == CAPABILITY_KEY)
            .order_by(AiRunLog.attempt_number)
        )
    )
    assert calls == 3
    assert [(run.attempt_number, run.status) for run in runs] == [
        (1, "failed"),
        (2, "needs_review"),
    ]
    assert runs[0].run_metadata is not None
    assert runs[0].run_metadata["reservation_status"] == "superseded_finalized"
    assert runs[0].total_tokens == 300


@pytest.mark.parametrize(
    ("model_name", "usage", "pricing_status"),
    [
        (
            "unpriced-late-result-model",
            {"input_tokens": 100, "output_tokens": 50, "total_tokens": 150},
            "unpriced_model",
        ),
        (
            "gpt-5.6-sol",
            {"input_tokens": None, "output_tokens": None, "total_tokens": None},
            "usage_unavailable",
        ),
    ],
)
def test_late_unverifiable_provider_result_retains_full_budget_hold(
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
    model_name: str,
    usage: dict[str, int | None],
    pricing_status: str,
) -> None:
    principal = _foundation(db_session)
    runtime = db_session.scalar(select(AiRuntimePolicy))
    agent = db_session.scalar(
        select(AiAgentDefinition).where(AiAgentDefinition.key == "prospecting_intelligence")
    )
    assert runtime is not None and agent is not None
    prompt = db_session.scalar(
        select(AiPromptVersion).where(AiPromptVersion.agent_definition_id == agent.id)
    )
    assert prompt is not None
    runtime.default_model = model_name
    runtime.max_daily_cost_microusd = 100_000
    agent.max_daily_cost_microusd = 100_000
    db_session.commit()
    started_at = datetime.now(UTC)
    reservation, acquired = _reserve_run(
        db_session,
        principal,
        agent=agent,
        prompt=prompt,
        idempotency_key=f"late-unverifiable:{pricing_status}",
        model_name=model_name,
        started_at=started_at,
        input_summary="late provider result",
        metadata={"provider_agent_id": "late-agent"},
        generation_attempt=1,
        budget_limit_microusd=100_000,
    )
    assert acquired is True
    _expire_reservation(reservation)
    db_session.commit()

    with pytest.raises(VaPerformanceCoachError, match="reservation is no longer active"):
        _persist_run(
            db_session,
            principal,
            reserved_run=reservation,
            runtime_policy=None,
            agent=agent,
            prompt=prompt,
            idempotency_key=reservation.idempotency_key or "",
            model_name=model_name,
            status="needs_review",
            started_at=started_at,
            input_summary="late provider result",
            output=_valid_output(),
            usage=usage,
            latency_ms=500,
            metadata={"provider_agent_id": "late-agent"},
            settings=_settings(),
            error_message=None,
            generation_attempt=1,
            model_attempts=1,
            max_cost_microusd_per_run=100_000,
        )

    db_session.refresh(reservation)
    assert reservation.status == "failed"
    assert reservation.budget_status == "cost_unverifiable"
    assert reservation.cost_microusd is None
    assert reservation.budget_limit_microusd == 100_000
    assert reservation.run_metadata is not None
    assert reservation.run_metadata["pricing_status"] == pricing_status
    assert reservation.run_metadata["late_provider_result_discarded"] is True
    assert reservation.run_metadata["coaching_report"] is None

    calls = 0

    def structured_response(
        *_args: object,
        **_kwargs: Any,
    ) -> tuple[dict[str, Any], dict[str, int]]:
        nonlocal calls
        calls += 1
        return _valid_output(), {
            "input_tokens": 100,
            "output_tokens": 50,
            "total_tokens": 150,
        }

    monkeypatch.setattr(
        "app.services.va_performance_coach.OpenAIResponsesClient.create_structured_response",
        structured_response,
    )
    start = datetime.now(UTC)
    with pytest.raises(VaPerformanceCoachError, match="daily budget"):
        generate_va_performance_coaching_report(
            db_session,
            principal,
            _settings(),
            provider_agent_id="agent-18",
            range_start=start,
            range_end=start + timedelta(hours=8),
            performance_snapshot=_snapshot(),
        )
    assert calls == 0


def test_stale_success_does_not_override_recovery_failure_circuit_state(
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    principal = _foundation(db_session)
    start = datetime(2026, 8, 22, 13, tzinfo=UTC)
    calls = 0

    def generate() -> Any:
        return generate_va_performance_coaching_report(
            db_session,
            principal,
            _settings(),
            provider_agent_id="agent-17",
            range_start=start,
            range_end=start + timedelta(hours=8),
            performance_snapshot=_snapshot(),
        )

    def invalid_output() -> dict[str, Any]:
        output = _valid_output()
        output["summary"]["text"] = "The VA worked for eight hours."
        return output

    def structured_response(
        *_args: object,
        **_kwargs: Any,
    ) -> tuple[dict[str, Any], dict[str, int]]:
        nonlocal calls
        calls += 1
        if calls == 1:
            reservation = db_session.scalar(
                select(AiRunLog).where(
                    AiRunLog.capability_key == CAPABILITY_KEY,
                    AiRunLog.attempt_number == 1,
                )
            )
            assert reservation is not None
            reservation.started_at = datetime.now(UTC) - timedelta(minutes=11)
            db_session.commit()
            with pytest.raises(VaPerformanceCoachError, match="unsupported exact work hours"):
                generate()
            return _valid_output(), {
                "input_tokens": 100,
                "output_tokens": 50,
                "total_tokens": 150,
            }
        return invalid_output(), {
            "input_tokens": 100,
            "output_tokens": 50,
            "total_tokens": 150,
        }

    monkeypatch.setattr(
        "app.services.va_performance_coach.OpenAIResponsesClient.create_structured_response",
        structured_response,
    )

    with pytest.raises(VaPerformanceCoachError, match="reservation is no longer active"):
        generate()

    runtime = db_session.scalar(select(AiRuntimePolicy))
    assert runtime is not None
    assert runtime.consecutive_failure_count == 1
    assert runtime.circuit_open_until is None
    runs = list(
        db_session.scalars(
            select(AiRunLog)
            .where(AiRunLog.capability_key == CAPABILITY_KEY)
            .order_by(AiRunLog.attempt_number)
        )
    )
    assert calls == 3
    assert [(run.attempt_number, run.status) for run in runs] == [
        (1, "failed"),
        (2, "failed"),
    ]
    assert runs[0].run_metadata is not None
    assert runs[0].run_metadata["reservation_status"] == "superseded_finalized"
    assert runs[0].total_tokens == 150


def test_generate_requires_timezone_aware_range(db_session: Session) -> None:
    principal = _foundation(db_session)
    start = datetime(2026, 8, 22, 13)
    with pytest.raises(ValueError, match="timezone-aware"):
        generate_va_performance_coaching_report(
            db_session,
            principal,
            _settings(),
            provider_agent_id="agent-17",
            range_start=start,
            range_end=start + timedelta(hours=8),
            performance_snapshot=_snapshot(),
        )
