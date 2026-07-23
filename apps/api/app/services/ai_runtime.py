import hashlib
import json
import re
import time
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.core.auth import Principal
from app.core.config import get_settings
from app.domain.rbac import PermissionKeys
from app.integrations.openai_client import OpenAIClientError, OpenAIResponsesClient
from app.models.foundation import (
    AiAgentDefinition,
    AiCapabilityRuntimePolicy,
    AiEvaluationComparison,
    AiEvaluationRun,
    AiKnowledgeSource,
    AiKnowledgeUseLog,
    AiPromptVersion,
    AiRunLog,
    AiToolCallLog,
    AiToolPermission,
    AuditEvent,
    CallRecord,
    CallRecording,
    CallTranscript,
    Campaign,
    Prospect,
    ProspectCallingBatch,
    ProspectCallingBatchEntry,
    ProspectHandoff,
    ProspectingAttempt,
    ProspectingScriptVersion,
)
from app.schemas.ai import (
    AiCapabilityRuntimeRead,
    AiCapabilityRuntimeUpdate,
    AiEvaluationComparisonCreate,
    AiEvaluationComparisonRead,
    AiRuntimeExecuteCreate,
    AiRuntimeInstallRead,
    AiRuntimeMetrics,
    AiRuntimeOverview,
    AiRuntimePolicyRead,
    AiRuntimePolicyUpdate,
)
from app.services.ai import build_lead_context, run_to_read
from app.services.ai_costs import cents_from_microusd, estimate_openai_cost
from app.services.ai_orchestrator import PORTFOLIO

MODEL_ROUTES = {"high_volume", "default", "escalation"}
CAPABILITY_STATUSES = {"enabled", "disabled"}
OUTPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "summary": {"type": "string"},
        "recommended_actions": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "action": {"type": "string"},
                    "reason": {"type": "string"},
                    "confidence": {"type": "integer", "minimum": 0, "maximum": 100},
                    "evidence": {"type": "array", "items": {"type": "string"}},
                    "requires_human_approval": {"type": "boolean"},
                },
                "required": [
                    "action",
                    "reason",
                    "confidence",
                    "evidence",
                    "requires_human_approval",
                ],
            },
        },
        "risks": {"type": "array", "items": {"type": "string"}},
        "uncertainties": {"type": "array", "items": {"type": "string"}},
        "knowledge_citations": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "source_key": {"type": "string"},
                    "version": {"type": "integer"},
                    "checksum": {"type": "string"},
                },
                "required": ["source_key", "version", "checksum"],
            },
        },
    },
    "required": [
        "summary",
        "recommended_actions",
        "risks",
        "uncertainties",
        "knowledge_citations",
    ],
}
LEAD_MANAGER_OUTPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "summary": {"type": "string"},
        "priority_explanation": {"type": "string"},
        "qualification_gaps": {"type": "array", "items": {"type": "string"}},
        "recommended_questions": {"type": "array", "items": {"type": "string"}},
        "message_draft": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "channel": {"type": "string", "enum": ["none", "sms", "email"]},
                "body": {"type": "string"},
            },
            "required": ["channel", "body"],
        },
        "next_task": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "title": {"type": "string"},
                "reason": {"type": "string"},
                "due_timing": {"type": "string"},
            },
            "required": ["title", "reason", "due_timing"],
        },
        "appointment_proposal": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "recommended": {"type": "boolean"},
                "reason": {"type": "string"},
            },
            "required": ["recommended", "reason"],
        },
        "handoff_summary": {"type": "string"},
        "risks": {"type": "array", "items": {"type": "string"}},
        "evidence": {"type": "array", "items": {"type": "string"}},
        "confidence": {"type": "integer", "minimum": 0, "maximum": 100},
    },
    "required": [
        "summary",
        "priority_explanation",
        "qualification_gaps",
        "recommended_questions",
        "message_draft",
        "next_task",
        "appointment_proposal",
        "handoff_summary",
        "risks",
        "evidence",
        "confidence",
    ],
}
PROSPECTING_OUTPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "pre_call_summary": {"type": "string"},
        "priority_explanation": {"type": "string"},
        "property_context": {"type": "array", "items": {"type": "string"}},
        "prior_attempt_context": {"type": "array", "items": {"type": "string"}},
        "opening_guidance": {"type": "string"},
        "required_questions": {"type": "array", "items": {"type": "string"}},
        "disposition_guidance": {"type": "array", "items": {"type": "string"}},
        "data_quality_warnings": {"type": "array", "items": {"type": "string"}},
        "compliance_reminders": {"type": "array", "items": {"type": "string"}},
        "evidence": {"type": "array", "items": {"type": "string"}},
        "confidence": {"type": "integer", "minimum": 0, "maximum": 100},
    },
    "required": [
        "pre_call_summary",
        "priority_explanation",
        "property_context",
        "prior_attempt_context",
        "opening_guidance",
        "required_questions",
        "disposition_guidance",
        "data_quality_warnings",
        "compliance_reminders",
        "evidence",
        "confidence",
    ],
}
CALL_QUALITY_OUTPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "call_summary": {"type": "string"},
        "suggested_disposition": {
            "type": "string",
            "enum": [
                "no_answer",
                "left_voicemail",
                "callback_requested",
                "follow_up",
                "interested",
                "appointment_set",
                "not_interested",
                "wrong_number",
                "do_not_call",
            ],
        },
        "disposition_reason": {"type": "string"},
        "callback_recommendation": {"type": "string"},
        "handoff_draft": {"type": "string"},
        "script_adherence_score": {"type": "integer", "minimum": 0, "maximum": 100},
        "qualification_completeness_score": {
            "type": "integer",
            "minimum": 0,
            "maximum": 100,
        },
        "objection_handling_score": {"type": "integer", "minimum": 0, "maximum": 100},
        "data_quality_score": {"type": "integer", "minimum": 0, "maximum": 100},
        "handoff_quality_score": {"type": "integer", "minimum": 0, "maximum": 100},
        "coaching_points": {"type": "array", "items": {"type": "string"}},
        "compliance_flags": {"type": "array", "items": {"type": "string"}},
        "evidence_timestamps": {"type": "array", "items": {"type": "string"}},
        "confidence": {"type": "integer", "minimum": 0, "maximum": 100},
    },
    "required": [
        "call_summary",
        "suggested_disposition",
        "disposition_reason",
        "callback_recommendation",
        "handoff_draft",
        "script_adherence_score",
        "qualification_completeness_score",
        "objection_handling_score",
        "data_quality_score",
        "handoff_quality_score",
        "coaching_points",
        "compliance_flags",
        "evidence_timestamps",
        "confidence",
    ],
}
KNOWLEDGE_BY_CAPABILITY = {
    "lead": ["operating_model", "lead_manager_qualification"],
    "call": ["operating_model"],
    "appointment": ["operating_model", "underwriting_method"],
    "underwriting": ["underwriting_method"],
    "negotiation": ["operating_model", "underwriting_method"],
    "prospecting": ["prospecting_scripts"],
    "compliance": ["ai_agent_policy"],
    "operations": ["operating_model", "ai_agent_policy"],
}
COMMON_LEAD_FIELDS = (
    "source",
    "stage",
    "temperature",
    "motivation",
    "desired_timeline",
    "property_condition",
    "occupancy_status",
    "asking_price",
    "mortgage_balance",
    "appointment_status",
    "next_follow_up_at",
    "created_at",
)
COMMON_PROPERTY_FIELDS = (
    "city",
    "state",
    "postal_code",
    "county",
    "property_type",
)
ADDRESS_ALLOWED_PREFIXES = {
    "appointment",
    "underwriting",
    "negotiation",
    "transaction",
    "disposition",
}
SENSITIVE_KEY_PARTS = {
    "api_key",
    "token",
    "secret",
    "password",
    "email",
    "phone",
    "address",
    "contact_method",
}
SENSITIVE_PATTERNS = (
    re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE),
    re.compile(r"\b(?:\+?1[-.\s]?)?\(?\d{3}\)?[-.\s]\d{3}[-.\s]\d{4}\b"),
)


def install_runtime(db: Session, principal: Principal) -> AiRuntimeInstallRead:
    settings = get_settings()
    runtime = _runtime_policy(db, principal)
    created_runtime = runtime is None
    if runtime is None:
        default_model = settings.openai_default_model
        runtime = _new_runtime_policy(
            principal,
            high_volume_model=settings.openai_high_volume_model or default_model,
            default_model=default_model,
            escalation_model=settings.openai_escalation_model or default_model,
        )
        db.add(runtime)
        db.flush()

    existing_capabilities = {
        item.capability_key: item
        for item in db.scalars(
            select(AiCapabilityRuntimePolicy).where(
                AiCapabilityRuntimePolicy.organization_id == principal.organization_id
            )
        ).all()
    }
    agents = {
        item.key: item
        for item in db.scalars(
            select(AiAgentDefinition).where(
                AiAgentDefinition.organization_id == principal.organization_id
            )
        ).all()
    }
    created_capabilities = 0
    for agent_key, _, _, capability_key, risk_level in PORTFOLIO:
        agent = agents.get(agent_key)
        if agent is None:
            continue
        existing_capability = existing_capabilities.get(capability_key)
        if existing_capability is not None:
            if capability_key in {
                "lead.next_action",
                "prospecting.prioritize",
            }:
                existing_capability.output_schema = (
                    LEAD_MANAGER_OUTPUT_SCHEMA
                    if capability_key == "lead.next_action"
                    else PROSPECTING_OUTPUT_SCHEMA
                )
                existing_capability.updated_by_user_id = principal.user_id
            continue
        route = "escalation" if risk_level == "high" else "default"
        knowledge_prefix = capability_key.split(".", 1)[0]
        db.add(
            AiCapabilityRuntimePolicy(
                organization_id=principal.organization_id,
                agent_definition_id=agent.id,
                capability_key=capability_key,
                status="disabled",
                model_route=route,
                output_schema={
                    "lead.next_action": LEAD_MANAGER_OUTPUT_SCHEMA,
                    "prospecting.prioritize": PROSPECTING_OUTPUT_SCHEMA,
                }.get(capability_key, OUTPUT_SCHEMA),
                allowed_tool_keys=[f"{capability_key}.read"],
                allowed_knowledge_keys=KNOWLEDGE_BY_CAPABILITY.get(
                    knowledge_prefix, ["operating_model"]
                ),
                max_output_tokens=1200,
                max_cost_microusd_per_run=min(agent.max_cost_microusd_per_run, 100_000),
                requires_human_review=True,
                updated_by_user_id=principal.user_id,
            )
        )
        created_capabilities += 1

    call_agent = agents.get("call_intelligence")
    if call_agent is not None:
        existing_quality = existing_capabilities.get("call.quality_coach")
        if existing_quality is not None:
            existing_quality.output_schema = CALL_QUALITY_OUTPUT_SCHEMA
            existing_quality.updated_by_user_id = principal.user_id
        else:
            db.add(
                AiCapabilityRuntimePolicy(
                    organization_id=principal.organization_id,
                    agent_definition_id=call_agent.id,
                    capability_key="call.quality_coach",
                    status="disabled",
                    model_route="escalation",
                    output_schema=CALL_QUALITY_OUTPUT_SCHEMA,
                    allowed_tool_keys=["call.summarize.read"],
                    allowed_knowledge_keys=[
                        "operating_model",
                        "prospecting_scripts",
                        "ai_agent_policy",
                    ],
                    max_output_tokens=1600,
                    max_cost_microusd_per_run=100_000,
                    requires_human_review=True,
                    updated_by_user_id=principal.user_id,
                )
            )
            created_capabilities += 1

    updated_knowledge = 0
    knowledge_sources = db.scalars(
        select(AiKnowledgeSource).where(
            AiKnowledgeSource.organization_id == principal.organization_id
        )
    ).all()
    for source in knowledge_sources:
        if source.content_snapshot and source.content_checksum:
            continue
        snapshot = (
            f"{source.title} is the registered {source.category} source for Stonegate. "
            f"Use only an approved version from {source.content_reference}. "
            "Cite the source key, version, and checksum; never infer missing policy."
        )
        source.content_snapshot = snapshot
        source.content_checksum = hashlib.sha256(snapshot.encode("utf-8")).hexdigest()
        updated_knowledge += 1

    _audit(
        db,
        principal,
        "ai.runtime_install",
        "ai_runtime_policy",
        runtime.id,
        {
            "created_runtime": created_runtime,
            "created_capabilities": created_capabilities,
            "updated_knowledge": updated_knowledge,
        },
    )
    db.commit()
    return AiRuntimeInstallRead(
        created_runtime_policy=created_runtime,
        created_capability_policy_count=created_capabilities,
        updated_knowledge_source_count=updated_knowledge,
        runtime=get_runtime_overview(db, principal),
    )


def update_runtime_policy(
    db: Session,
    principal: Principal,
    payload: AiRuntimePolicyUpdate,
) -> AiRuntimeOverview:
    policy = _require_runtime_policy(db, principal)
    for field, value in payload.model_dump(exclude_none=True).items():
        setattr(policy, field, value)
    if payload.provider_status == "enabled":
        policy.emergency_stop = False
        policy.emergency_stop_reason = None
        policy.consecutive_failure_count = 0
        policy.circuit_open_until = None
    policy.updated_by_user_id = principal.user_id
    _audit(
        db,
        principal,
        "ai.runtime_policy_update",
        "ai_runtime_policy",
        policy.id,
        payload.model_dump(exclude_none=True),
    )
    db.commit()
    return get_runtime_overview(db, principal)


def update_capability_runtime(
    db: Session,
    principal: Principal,
    capability_key: str,
    payload: AiCapabilityRuntimeUpdate,
) -> AiRuntimeOverview:
    policy = db.scalar(
        select(AiCapabilityRuntimePolicy).where(
            AiCapabilityRuntimePolicy.organization_id == principal.organization_id,
            AiCapabilityRuntimePolicy.capability_key == capability_key,
        )
    )
    if policy is None:
        raise ValueError("Capability runtime policy not found.")
    policy.status = payload.status
    if payload.model_route is not None:
        policy.model_route = payload.model_route
    policy.updated_by_user_id = principal.user_id
    _audit(
        db,
        principal,
        "ai.capability_runtime_update",
        "ai_capability_runtime_policy",
        policy.id,
        {"status": policy.status, "model_route": policy.model_route},
    )
    db.commit()
    return get_runtime_overview(db, principal)


def emergency_shutdown(
    db: Session,
    principal: Principal,
    reason: str,
) -> AiRuntimeOverview:
    policy = _require_runtime_policy(db, principal)
    policy.provider_status = "disabled"
    policy.emergency_stop = True
    policy.emergency_stop_reason = reason
    policy.updated_by_user_id = principal.user_id
    db.execute(
        update(AiCapabilityRuntimePolicy)
        .where(AiCapabilityRuntimePolicy.organization_id == principal.organization_id)
        .values(status="disabled", updated_by_user_id=principal.user_id)
    )
    _audit(
        db,
        principal,
        "ai.runtime_emergency_shutdown",
        "ai_runtime_policy",
        policy.id,
        {"reason": reason},
    )
    db.commit()
    return get_runtime_overview(db, principal)


def execute_runtime(
    db: Session,
    principal: Principal,
    payload: AiRuntimeExecuteCreate,
):
    existing = db.scalar(
        select(AiRunLog).where(
            AiRunLog.organization_id == principal.organization_id,
            AiRunLog.idempotency_key == payload.idempotency_key,
        )
    )
    if existing is not None:
        return run_to_read(existing, _tool_calls(db, existing.id))

    settings = get_settings()
    runtime = _require_runtime_policy(db, principal)
    capability = db.scalar(
        select(AiCapabilityRuntimePolicy).where(
            AiCapabilityRuntimePolicy.organization_id == principal.organization_id,
            AiCapabilityRuntimePolicy.agent_definition_id == payload.agent_definition_id,
            AiCapabilityRuntimePolicy.capability_key == payload.capability_key,
        )
    )
    if capability is None:
        raise ValueError("Capability runtime policy not found.")
    agent = db.scalar(
        select(AiAgentDefinition).where(
            AiAgentDefinition.organization_id == principal.organization_id,
            AiAgentDefinition.id == payload.agent_definition_id,
        )
    )
    if agent is None:
        raise ValueError("AI agent not found.")
    prompt = db.scalar(
        select(AiPromptVersion)
        .where(
            AiPromptVersion.organization_id == principal.organization_id,
            AiPromptVersion.agent_definition_id == agent.id,
            AiPromptVersion.status == "active",
        )
        .order_by(AiPromptVersion.version_number.desc())
    )
    if prompt is None:
        raise ValueError("The capability needs an active prompt.")

    block_reason = _runtime_block_reason(db, principal, runtime, capability, settings.ai_enabled)
    if block_reason:
        return _record_blocked_run(db, principal, payload, agent, prompt, capability, block_reason)
    if not settings.openai_api_key:
        return _record_blocked_run(
            db,
            principal,
            payload,
            agent,
            prompt,
            capability,
            "OPENAI_API_KEY is not configured.",
        )

    tool_context, tool_log = _execute_read_tool(db, principal, agent, capability, payload)
    knowledge = _approved_knowledge(db, principal, capability.allowed_knowledge_keys)
    request_context = {
        "request": payload.input_payload,
        "read_tool_result": tool_context,
        "approved_knowledge": [
            {
                "source_key": item.key,
                "version": item.version_number,
                "checksum": item.content_checksum,
                "content": item.content_snapshot,
            }
            for item in knowledge
        ],
    }
    serialized_context = json.dumps(request_context, sort_keys=True, default=str)
    if len(serialized_context) > runtime.max_context_characters:
        return _record_blocked_run(
            db,
            principal,
            payload,
            agent,
            prompt,
            capability,
            "Runtime context exceeds the organization limit.",
        )

    model_name = _model_for_route(runtime, capability.model_route)
    started_monotonic = time.perf_counter()
    client = OpenAIResponsesClient(
        api_key=settings.openai_api_key,
        base_url=settings.openai_base_url,
        timeout_seconds=settings.openai_request_timeout_seconds,
    )
    parsed: dict[str, Any] | None = None
    usage: dict[str, int | None] = {}
    error_message: str | None = None
    attempts = 0
    for attempt_number in range(1, min(agent.max_attempts, 2) + 1):
        attempts = attempt_number
        try:
            parsed, usage = client.create_structured_response(
                model=model_name,
                system_prompt=(
                    f"{prompt.prompt_text}\n"
                    "Return only the governed structured output. Every recommendation remains "
                    "a draft for human review. Cite only supplied approved knowledge snapshots."
                ),
                user_prompt=serialized_context,
                schema_name="stonegate_copilot_output",
                json_schema=capability.output_schema,
                reasoning_effort=settings.openai_reasoning_effort,
                max_output_tokens=capability.max_output_tokens,
                safety_identifier=_safety_identifier(principal),
                prompt_cache_key=(f"stonegate:{agent.key}:prompt-v{prompt.version_number}"),
            )
            break
        except OpenAIClientError as exc:
            error_message = str(exc)

    latency_ms = round((time.perf_counter() - started_monotonic) * 1000)
    if parsed is None:
        _record_runtime_failure(runtime)
        run = _new_runtime_run(
            principal,
            payload,
            agent,
            prompt,
            capability,
            model_name=model_name,
            status="failed",
            input_summary=_redacted_json(payload.input_payload),
            output_summary=None,
            latency_ms=latency_ms,
            error_message=error_message or "OpenAI request failed.",
            attempts=attempts,
        )
        db.add(run)
        db.commit()
        db.refresh(run)
        return run_to_read(run, [])

    cost = estimate_openai_cost(
        settings,
        model=model_name,
        input_tokens=usage.get("input_tokens"),
        output_tokens=usage.get("output_tokens"),
    )
    if cost.cost_microusd is not None and cost.cost_microusd > capability.max_cost_microusd_per_run:
        parsed = {
            "summary": "The model result exceeded the capability cost ceiling and was blocked.",
            "recommended_actions": [],
            "risks": ["cost_limit_exceeded"],
            "uncertainties": [],
            "knowledge_citations": [],
        }
        status = "blocked"
        budget_status = "per_run_limit_exceeded"
    else:
        status = "needs_review"
        budget_status = "within_budget"
    runtime.consecutive_failure_count = 0
    runtime.circuit_open_until = None
    output_summary = _redacted_json(parsed)
    run = _new_runtime_run(
        principal,
        payload,
        agent,
        prompt,
        capability,
        model_name=model_name,
        status=status,
        input_summary=_redacted_json(payload.input_payload),
        output_summary=output_summary,
        latency_ms=latency_ms,
        attempts=attempts,
    )
    run.input_tokens = usage.get("input_tokens")
    run.output_tokens = usage.get("output_tokens")
    run.total_tokens = usage.get("total_tokens")
    run.cost_microusd = cost.cost_microusd
    run.cost_cents = cents_from_microusd(cost.cost_microusd)
    run.budget_status = budget_status
    run.run_metadata = {
        **(run.run_metadata or {}),
        "model_route": capability.model_route,
        "pricing_status": cost.pricing_status,
        "trace_redacted": runtime.trace_redaction_enabled,
        "knowledge_source_count": len(knowledge),
        "prospect_id": str(payload.prospect_id) if payload.prospect_id else None,
        "prospecting_entry_id": (
            str(payload.prospecting_entry_id) if payload.prospecting_entry_id else None
        ),
        "prospecting_attempt_id": (
            str(payload.prospecting_attempt_id) if payload.prospecting_attempt_id else None
        ),
    }
    db.add(run)
    db.flush()
    tool_log.ai_run_log_id = run.id
    db.add(tool_log)
    for item in knowledge:
        db.add(
            AiKnowledgeUseLog(
                organization_id=principal.organization_id,
                ai_run_log_id=run.id,
                knowledge_source_id=item.id,
                source_key=item.key,
                source_version_number=item.version_number,
                content_checksum=item.content_checksum or "",
                content_reference=item.content_reference,
            )
        )
    _audit(
        db,
        principal,
        "ai.runtime_execute",
        "ai_run_log",
        run.id,
        {
            "capability_key": capability.capability_key,
            "model_route": capability.model_route,
            "status": status,
        },
    )
    db.commit()
    db.refresh(run)
    db.refresh(tool_log)
    return run_to_read(run, [tool_log])


def compare_evaluations(
    db: Session,
    principal: Principal,
    payload: AiEvaluationComparisonCreate,
) -> AiEvaluationComparisonRead:
    existing = db.scalar(
        select(AiEvaluationComparison).where(
            AiEvaluationComparison.organization_id == principal.organization_id,
            AiEvaluationComparison.baseline_evaluation_run_id == payload.baseline_evaluation_run_id,
            AiEvaluationComparison.challenger_evaluation_run_id
            == payload.challenger_evaluation_run_id,
        )
    )
    if existing is not None:
        return _comparison_read(existing)
    runs = db.scalars(
        select(AiEvaluationRun).where(
            AiEvaluationRun.organization_id == principal.organization_id,
            AiEvaluationRun.id.in_(
                [
                    payload.baseline_evaluation_run_id,
                    payload.challenger_evaluation_run_id,
                ]
            ),
        )
    ).all()
    by_id = {item.id: item for item in runs}
    baseline = by_id.get(payload.baseline_evaluation_run_id)
    challenger = by_id.get(payload.challenger_evaluation_run_id)
    if baseline is None or challenger is None:
        raise ValueError("Both evaluation runs must exist.")
    if baseline.dataset_id != challenger.dataset_id:
        raise ValueError("Evaluation comparisons require the same dataset version.")
    quality_delta = challenger.pass_rate_basis_points - baseline.pass_rate_basis_points
    latency_delta = _optional_delta(challenger.average_latency_ms, baseline.average_latency_ms)
    cost_delta = _optional_delta(challenger.average_cost_microusd, baseline.average_cost_microusd)
    regression_reasons = []
    if not challenger.thresholds_passed:
        regression_reasons.append("challenger_failed_dataset_thresholds")
    if quality_delta < 0:
        regression_reasons.append("pass_rate_regressed")
    if challenger.critical_failure_count > baseline.critical_failure_count:
        regression_reasons.append("critical_failures_increased")
    comparison = AiEvaluationComparison(
        organization_id=principal.organization_id,
        dataset_id=baseline.dataset_id,
        baseline_evaluation_run_id=baseline.id,
        challenger_evaluation_run_id=challenger.id,
        status="blocked" if regression_reasons else "passed",
        regression_blocked=bool(regression_reasons),
        quality_delta_basis_points=quality_delta,
        latency_delta_ms=latency_delta,
        cost_delta_microusd=cost_delta,
        summary={
            "regression_reasons": regression_reasons,
            "baseline_model": baseline.model_name,
            "challenger_model": challenger.model_name,
            "same_dataset_required": True,
        },
        created_by_user_id=principal.user_id,
    )
    db.add(comparison)
    db.commit()
    db.refresh(comparison)
    return _comparison_read(comparison)


def get_runtime_overview(db: Session, principal: Principal) -> AiRuntimeOverview:
    policy = _runtime_policy(db, principal)
    capabilities = db.scalars(
        select(AiCapabilityRuntimePolicy)
        .where(AiCapabilityRuntimePolicy.organization_id == principal.organization_id)
        .order_by(AiCapabilityRuntimePolicy.capability_key)
    ).all()
    agent_names = {
        item.id: item.name
        for item in db.scalars(
            select(AiAgentDefinition).where(
                AiAgentDefinition.organization_id == principal.organization_id
            )
        ).all()
    }
    comparisons = db.scalars(
        select(AiEvaluationComparison)
        .where(AiEvaluationComparison.organization_id == principal.organization_id)
        .order_by(AiEvaluationComparison.created_at.desc())
        .limit(30)
    ).all()

    def count(model: Any, *conditions: Any) -> int:
        return int(
            db.scalar(
                select(func.count(model.id)).where(
                    model.organization_id == principal.organization_id, *conditions
                )
            )
            or 0
        )

    runtime_status = "not_installed"
    if policy is not None:
        if policy.emergency_stop:
            runtime_status = "emergency_stopped"
        elif policy.provider_status == "enabled":
            runtime_status = "enabled"
        else:
            runtime_status = "disabled"
    return AiRuntimeOverview(
        status=runtime_status,
        policy=_runtime_policy_read(policy) if policy else None,
        capabilities=[
            _capability_read(item, agent_names.get(item.agent_definition_id, "Unknown agent"))
            for item in capabilities
        ],
        comparisons=[_comparison_read(item) for item in comparisons],
        metrics=AiRuntimeMetrics(
            enabled_capability_count=sum(item.status == "enabled" for item in capabilities),
            blocked_run_count=count(AiRunLog, AiRunLog.status == "blocked"),
            failed_run_count=count(
                AiRunLog,
                AiRunLog.execution_mode == "production",
                AiRunLog.status == "failed",
            ),
            redacted_trace_count=count(
                AiRunLog,
                AiRunLog.execution_mode == "production",
            ),
            knowledge_use_count=count(AiKnowledgeUseLog),
            regression_block_count=count(
                AiEvaluationComparison,
                AiEvaluationComparison.regression_blocked.is_(True),
            ),
        ),
    )


def _new_runtime_policy(
    principal: Principal,
    *,
    high_volume_model: str,
    default_model: str,
    escalation_model: str,
):
    from app.models.foundation import AiRuntimePolicy

    return AiRuntimePolicy(
        organization_id=principal.organization_id,
        provider_status="disabled",
        emergency_stop=False,
        high_volume_model=high_volume_model,
        default_model=default_model,
        escalation_model=escalation_model,
        max_context_characters=24_000,
        max_requests_per_minute=30,
        max_daily_cost_microusd=10_000_000,
        circuit_failure_threshold=3,
        circuit_cooldown_seconds=300,
        consecutive_failure_count=0,
        trace_redaction_enabled=True,
        external_actions_enabled=False,
        updated_by_user_id=principal.user_id,
    )


def _runtime_policy(db: Session, principal: Principal):
    from app.models.foundation import AiRuntimePolicy

    return db.scalar(
        select(AiRuntimePolicy).where(AiRuntimePolicy.organization_id == principal.organization_id)
    )


def _require_runtime_policy(db: Session, principal: Principal):
    policy = _runtime_policy(db, principal)
    if policy is None:
        raise ValueError("Install the AI3 runtime before using it.")
    return policy


def _runtime_block_reason(
    db: Session,
    principal: Principal,
    runtime: Any,
    capability: AiCapabilityRuntimePolicy,
    ai_enabled: bool,
) -> str | None:
    now = datetime.now(UTC)
    if not ai_enabled:
        return "AI is disabled by AI_ENABLED."
    if runtime.provider_status != "enabled" or runtime.emergency_stop:
        return "The OpenAI provider runtime is disabled."
    if capability.status != "enabled":
        return "This capability runtime is disabled."
    if runtime.external_actions_enabled:
        return "Unsafe runtime configuration: external actions must remain disabled."
    if runtime.circuit_open_until and runtime.circuit_open_until > now:
        return "The OpenAI circuit breaker is open."
    minute_ago = now - timedelta(minutes=1)
    recent_runs = int(
        db.scalar(
            select(func.count(AiRunLog.id)).where(
                AiRunLog.organization_id == principal.organization_id,
                AiRunLog.execution_mode == "production",
                AiRunLog.started_at >= minute_ago,
            )
        )
        or 0
    )
    if recent_runs >= runtime.max_requests_per_minute:
        return "The organization AI rate limit has been reached."
    start_day = datetime.combine(now.date(), datetime.min.time(), tzinfo=UTC)
    daily_cost = int(
        db.scalar(
            select(func.coalesce(func.sum(AiRunLog.cost_microusd), 0)).where(
                AiRunLog.organization_id == principal.organization_id,
                AiRunLog.started_at >= start_day,
            )
        )
        or 0
    )
    if daily_cost >= runtime.max_daily_cost_microusd:
        return "The organization AI daily cost limit has been reached."
    return None


def _execute_read_tool(
    db: Session,
    principal: Principal,
    agent: AiAgentDefinition,
    capability: AiCapabilityRuntimePolicy,
    payload: AiRuntimeExecuteCreate,
) -> tuple[dict[str, Any], AiToolCallLog]:
    tool_key = capability.allowed_tool_keys[0] if capability.allowed_tool_keys else ""
    permission = db.scalar(
        select(AiToolPermission).where(
            AiToolPermission.organization_id == principal.organization_id,
            AiToolPermission.agent_definition_id == agent.id,
            AiToolPermission.tool_key == tool_key,
            AiToolPermission.is_enabled.is_(True),
            AiToolPermission.permission_level == "read",
        )
    )
    if permission is None or not tool_key.endswith(".read"):
        raise ValueError("The runtime read tool is not permitted for this capability.")
    context: dict[str, Any] = {"request": payload.input_payload}
    field_scope: list[str]
    if payload.lead_id is not None:
        lead_context = build_lead_context(db, principal, payload.lead_id)
        if lead_context is None:
            raise ValueError("Lead not found.")
        context["lead"] = _scope_lead_context(capability.capability_key, lead_context)
        field_scope = [f"lead.{field}" for field in COMMON_LEAD_FIELDS] + [
            f"property.{field}" for field in COMMON_PROPERTY_FIELDS
        ]
        if capability.capability_key.split(".", 1)[0] in ADDRESS_ALLOWED_PREFIXES:
            field_scope.append("property.street_address")
    elif capability.capability_key == "prospecting.prioritize":
        prospect_context, field_scope = _prospecting_context(db, principal, payload)
        context["prospect"] = prospect_context
    elif capability.capability_key == "call.quality_coach":
        quality_context, field_scope = _call_quality_context(db, principal, payload)
        context["call_quality"] = quality_context
    else:
        field_scope = ["request"]
    tool_call = AiToolCallLog(
        organization_id=principal.organization_id,
        ai_run_log_id=UUID(int=0),
        approval_request_id=None,
        tool_key=tool_key,
        status="completed",
        requires_approval=False,
        input_payload={
            "lead_id": str(payload.lead_id) if payload.lead_id else None,
            "prospect_id": str(payload.prospect_id) if payload.prospect_id else None,
            "prospecting_entry_id": (
                str(payload.prospecting_entry_id) if payload.prospecting_entry_id else None
            ),
            "prospecting_attempt_id": (
                str(payload.prospecting_attempt_id) if payload.prospecting_attempt_id else None
            ),
        },
        output_payload={
            "record_scope": "organization",
            "field_scope": field_scope,
            "action_scope": "read",
            "result": "read_completed",
        },
    )
    return context, tool_call


def _prospecting_context(
    db: Session,
    principal: Principal,
    payload: AiRuntimeExecuteCreate,
) -> tuple[dict[str, Any], list[str]]:
    if payload.prospect_id is None or payload.prospecting_entry_id is None:
        raise ValueError("Prospecting analysis requires a prospect and assigned queue entry.")
    entry = db.scalar(
        select(ProspectCallingBatchEntry).where(
            ProspectCallingBatchEntry.organization_id == principal.organization_id,
            ProspectCallingBatchEntry.id == payload.prospecting_entry_id,
            ProspectCallingBatchEntry.prospect_id == payload.prospect_id,
        )
    )
    prospect = db.scalar(
        select(Prospect).where(
            Prospect.organization_id == principal.organization_id,
            Prospect.id == payload.prospect_id,
        )
    )
    if entry is None or prospect is None:
        raise ValueError("Assigned prospect not found.")
    can_manage = PermissionKeys.MANAGE_ACQUISITION_OPERATIONS in principal.permission_keys
    if not can_manage and entry.assigned_user_id != principal.user_id:
        raise ValueError("The prospect is not assigned to this caller.")
    if prospect.call_eligibility != "eligible" or prospect.suppression_status == "suppressed":
        raise ValueError("Only eligible, unsuppressed prospects may be analyzed.")
    batch = db.get(ProspectCallingBatch, entry.prospect_calling_batch_id)
    campaign = db.get(Campaign, batch.campaign_id) if batch else None
    attempts = list(
        db.scalars(
            select(ProspectingAttempt)
            .where(
                ProspectingAttempt.organization_id == principal.organization_id,
                ProspectingAttempt.batch_entry_id == entry.id,
            )
            .order_by(ProspectingAttempt.started_at.desc())
        ).all()
    )
    script = db.scalar(
        select(ProspectingScriptVersion)
        .where(
            ProspectingScriptVersion.organization_id == principal.organization_id,
            ProspectingScriptVersion.status == "approved",
        )
        .order_by(ProspectingScriptVersion.version_number.desc())
    )
    return (
        {
            "seller_name": prospect.legal_name,
            "property": {
                "street_address": prospect.street_address,
                "city": prospect.city,
                "state": prospect.state_code,
                "postal_code": prospect.postal_code,
                "address_validation_status": prospect.address_validation_status,
            },
            "campaign": campaign.name if campaign else None,
            "eligibility": {
                "call_eligibility": prospect.call_eligibility,
                "suppression_status": prospect.suppression_status,
                "suppression_checked_at": prospect.suppression_checked_at,
                "phone_validation_status": prospect.phone_validation_status,
            },
            "queue": {
                "status": entry.status,
                "attempt_count": entry.attempt_count,
                "last_attempt_at": entry.last_attempt_at,
                "next_attempt_at": entry.next_attempt_at,
                "last_disposition": entry.disposition,
            },
            "attempts": [
                {
                    "outcome": attempt.outcome,
                    "answers": attempt.qualification_answers,
                    "notes": attempt.notes,
                    "callback_at": attempt.callback_at,
                    "completed_at": attempt.completed_at,
                }
                for attempt in attempts[:5]
            ],
            "approved_script": (
                {
                    "version": script.version_number,
                    "opening_script": script.opening_script,
                    "questions": script.qualification_questions,
                }
                if script
                else None
            ),
        },
        [
            "prospect.identity",
            "prospect.property",
            "prospect.eligibility",
            "queue.assignment",
            "queue.attempt_history",
            "script.approved_version",
        ],
    )


def _call_quality_context(
    db: Session,
    principal: Principal,
    payload: AiRuntimeExecuteCreate,
) -> tuple[dict[str, Any], list[str]]:
    if payload.prospecting_attempt_id is None:
        raise ValueError("Call-quality analysis requires a prospecting attempt.")
    attempt = db.scalar(
        select(ProspectingAttempt).where(
            ProspectingAttempt.organization_id == principal.organization_id,
            ProspectingAttempt.id == payload.prospecting_attempt_id,
        )
    )
    if attempt is None:
        raise ValueError("Prospecting attempt not found.")
    can_manage = PermissionKeys.MANAGE_ACQUISITION_OPERATIONS in principal.permission_keys
    if not can_manage and attempt.caller_user_id != principal.user_id:
        raise ValueError("The call is not assigned to this caller.")
    if attempt.call_record_id is None:
        raise ValueError("An attached recorded call is required for call-quality analysis.")
    call = db.scalar(
        select(CallRecord).where(
            CallRecord.organization_id == principal.organization_id,
            CallRecord.id == attempt.call_record_id,
        )
    )
    recording = db.scalar(
        select(CallRecording).where(
            CallRecording.organization_id == principal.organization_id,
            CallRecording.call_record_id == attempt.call_record_id,
            CallRecording.deleted_at.is_(None),
        )
    )
    transcript = (
        db.scalar(
            select(CallTranscript)
            .where(
                CallTranscript.organization_id == principal.organization_id,
                CallTranscript.recording_id == recording.id,
                CallTranscript.status == "approved",
            )
            .order_by(CallTranscript.approved_at.desc())
        )
        if recording
        else None
    )
    if call is None or recording is None or transcript is None:
        raise ValueError("An approved transcript is required for call-quality analysis.")
    if recording.consent_status != "disclosed":
        raise ValueError("Recording disclosure evidence is required for call-quality analysis.")
    script = db.get(ProspectingScriptVersion, attempt.script_version_id)
    handoff = db.scalar(
        select(ProspectHandoff).where(
            ProspectHandoff.organization_id == principal.organization_id,
            ProspectHandoff.attempt_id == attempt.id,
        )
    )
    return (
        {
            "approved_script": {
                "version": script.version_number if script else None,
                "opening_script": script.opening_script if script else None,
                "questions": script.qualification_questions if script else [],
            },
            "transcript": {
                "text": transcript.transcript_text,
                "speaker_segments": transcript.speaker_segments or [],
                "confidence": transcript.confidence_score,
            },
            "human_record": {
                "outcome": attempt.outcome,
                "qualification_answers": attempt.qualification_answers,
                "notes": attempt.notes,
                "callback_at": attempt.callback_at,
                "handoff_status": handoff.status if handoff else None,
                "handoff_review_reason": handoff.review_reason if handoff else None,
            },
        },
        [
            "script.approved_version",
            "call.approved_transcript",
            "call.speaker_segments",
            "attempt.human_disposition",
            "attempt.handoff_review",
        ],
    )


def _approved_knowledge(
    db: Session,
    principal: Principal,
    allowed_keys: list[str],
) -> list[AiKnowledgeSource]:
    if not allowed_keys:
        return []
    candidates = db.scalars(
        select(AiKnowledgeSource)
        .where(
            AiKnowledgeSource.organization_id == principal.organization_id,
            AiKnowledgeSource.key.in_(allowed_keys),
            AiKnowledgeSource.status == "approved",
            AiKnowledgeSource.is_authoritative.is_(True),
            AiKnowledgeSource.content_snapshot.is_not(None),
            AiKnowledgeSource.content_checksum.is_not(None),
        )
        .order_by(AiKnowledgeSource.key, AiKnowledgeSource.version_number.desc())
    ).all()
    latest_by_key: dict[str, AiKnowledgeSource] = {}
    for source in candidates:
        latest_by_key.setdefault(source.key, source)
    return list(latest_by_key.values())


def _scope_lead_context(
    capability_key: str,
    lead_context: dict[str, object],
) -> dict[str, object]:
    lead = lead_context.get("lead")
    property_record = lead_context.get("property")
    seller = lead_context.get("seller")
    scoped_lead = lead if isinstance(lead, dict) else {}
    scoped_property = property_record if isinstance(property_record, dict) else {}
    scoped_seller = seller if isinstance(seller, dict) else {}
    property_fields = list(COMMON_PROPERTY_FIELDS)
    if capability_key.split(".", 1)[0] in ADDRESS_ALLOWED_PREFIXES:
        property_fields.append("street_address")
    return {
        "lead": {field: scoped_lead.get(field) for field in COMMON_LEAD_FIELDS},
        "seller": {
            "preferred_name": scoped_seller.get("preferred_name"),
        },
        "property": {field: scoped_property.get(field) for field in property_fields},
    }


def _record_blocked_run(
    db: Session,
    principal: Principal,
    payload: AiRuntimeExecuteCreate,
    agent: AiAgentDefinition,
    prompt: AiPromptVersion,
    capability: AiCapabilityRuntimePolicy,
    reason: str,
):
    runtime = _runtime_policy(db, principal)
    model_name = _model_for_route(runtime, capability.model_route)
    run = _new_runtime_run(
        principal,
        payload,
        agent,
        prompt,
        capability,
        model_name=model_name,
        status="blocked",
        input_summary=_redacted_json(payload.input_payload),
        output_summary="No model or tool execution occurred.",
        latency_ms=0,
        error_message=reason,
        attempts=0,
    )
    run.budget_status = "limit_exceeded" if "limit" in reason.lower() else "within_budget"
    db.add(run)
    db.commit()
    db.refresh(run)
    return run_to_read(run, [])


def _new_runtime_run(
    principal: Principal,
    payload: AiRuntimeExecuteCreate,
    agent: AiAgentDefinition,
    prompt: AiPromptVersion,
    capability: AiCapabilityRuntimePolicy,
    *,
    model_name: str,
    status: str,
    input_summary: str,
    output_summary: str | None,
    latency_ms: int,
    attempts: int,
    error_message: str | None = None,
) -> AiRunLog:
    now = datetime.now(UTC)
    return AiRunLog(
        organization_id=principal.organization_id,
        agent_definition_id=agent.id,
        prompt_version_id=prompt.id,
        lead_id=payload.lead_id,
        status=status,
        model_name=model_name,
        input_summary=input_summary[:4000],
        output_summary=output_summary[:4000] if output_summary else None,
        latency_ms=latency_ms,
        started_at=now,
        completed_at=now,
        error_message=error_message,
        requested_by_user_id=principal.user_id,
        execution_mode="production",
        capability_key=capability.capability_key,
        attempt_number=max(attempts, 1),
        idempotency_key=payload.idempotency_key,
        budget_limit_microusd=capability.max_cost_microusd_per_run,
        budget_status="within_budget",
        trace_status="unreviewed",
        rollback_status="not_required",
        run_metadata={
            "external_actions": "blocked",
            "requires_human_review": True,
            "trace_redacted": True,
        },
    )


def _record_runtime_failure(policy: Any) -> None:
    policy.consecutive_failure_count += 1
    if policy.consecutive_failure_count >= policy.circuit_failure_threshold:
        policy.circuit_open_until = datetime.now(UTC) + timedelta(
            seconds=policy.circuit_cooldown_seconds
        )


def _model_for_route(policy: Any, route: str) -> str:
    if route == "high_volume":
        return policy.high_volume_model
    if route == "escalation":
        return policy.escalation_model
    return policy.default_model


def _safety_identifier(principal: Principal) -> str:
    return hashlib.sha256(f"{principal.organization_id}:{principal.user_id}".encode()).hexdigest()[
        :64
    ]


def _redacted_json(value: Any) -> str:
    return json.dumps(_redact(value), sort_keys=True, default=str)[:4000]


def _redact(value: Any, key: str = "") -> Any:
    normalized_key = key.lower()
    if any(part in normalized_key for part in SENSITIVE_KEY_PARTS):
        return "[REDACTED]"
    if isinstance(value, dict):
        return {
            str(item_key): _redact(item_value, str(item_key))
            for item_key, item_value in value.items()
        }
    if isinstance(value, list):
        return [_redact(item, key) for item in value]
    if isinstance(value, str):
        result = value
        for pattern in SENSITIVE_PATTERNS:
            result = pattern.sub("[REDACTED]", result)
        return result
    return value


def _tool_calls(db: Session, run_id: UUID) -> list[AiToolCallLog]:
    return list(
        db.scalars(select(AiToolCallLog).where(AiToolCallLog.ai_run_log_id == run_id)).all()
    )


def _runtime_policy_read(item: Any) -> AiRuntimePolicyRead:
    return AiRuntimePolicyRead(
        id=item.id,
        provider_status=item.provider_status,
        emergency_stop=item.emergency_stop,
        emergency_stop_reason=item.emergency_stop_reason,
        high_volume_model=item.high_volume_model,
        default_model=item.default_model,
        escalation_model=item.escalation_model,
        max_context_characters=item.max_context_characters,
        max_requests_per_minute=item.max_requests_per_minute,
        max_daily_cost_microusd=item.max_daily_cost_microusd,
        circuit_failure_threshold=item.circuit_failure_threshold,
        circuit_cooldown_seconds=item.circuit_cooldown_seconds,
        consecutive_failure_count=item.consecutive_failure_count,
        circuit_open_until=item.circuit_open_until,
        trace_redaction_enabled=item.trace_redaction_enabled,
        external_actions_enabled=item.external_actions_enabled,
        updated_at=item.updated_at,
    )


def _capability_read(item: AiCapabilityRuntimePolicy, agent_name: str) -> AiCapabilityRuntimeRead:
    return AiCapabilityRuntimeRead(
        id=item.id,
        agent_definition_id=item.agent_definition_id,
        agent_name=agent_name,
        capability_key=item.capability_key,
        status=item.status,
        model_route=item.model_route,
        output_schema=item.output_schema,
        allowed_tool_keys=item.allowed_tool_keys,
        allowed_knowledge_keys=item.allowed_knowledge_keys,
        max_output_tokens=item.max_output_tokens,
        max_cost_microusd_per_run=item.max_cost_microusd_per_run,
        requires_human_review=item.requires_human_review,
        updated_at=item.updated_at,
    )


def _comparison_read(item: AiEvaluationComparison) -> AiEvaluationComparisonRead:
    return AiEvaluationComparisonRead(
        id=item.id,
        dataset_id=item.dataset_id,
        baseline_evaluation_run_id=item.baseline_evaluation_run_id,
        challenger_evaluation_run_id=item.challenger_evaluation_run_id,
        status=item.status,
        regression_blocked=item.regression_blocked,
        quality_delta_basis_points=item.quality_delta_basis_points,
        latency_delta_ms=item.latency_delta_ms,
        cost_delta_microusd=item.cost_delta_microusd,
        summary=item.summary,
        created_at=item.created_at,
    )


def _optional_delta(challenger: int | None, baseline: int | None) -> int | None:
    if challenger is None or baseline is None:
        return None
    return challenger - baseline


def _audit(
    db: Session,
    principal: Principal,
    action: str,
    entity_type: str,
    entity_id: UUID,
    metadata: dict[str, Any],
) -> None:
    db.add(
        AuditEvent(
            organization_id=principal.organization_id,
            actor_user_id=principal.user_id,
            actor_type="user",
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            previous_value=None,
            new_value=metadata,
            reason="Governed AI runtime control",
        )
    )
