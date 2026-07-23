import json
import re
from datetime import UTC, datetime, time
from typing import Any, Literal, cast
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.auth import Principal
from app.models.foundation import (
    ActivityEvent,
    AiAgentDefinition,
    AiCapabilityPromotion,
    AiCopilotDefinition,
    AiEvaluationCase,
    AiEvaluationDataset,
    AiEvaluationDatasetReview,
    AiEvaluationResult,
    AiEvaluationRun,
    AiOrchestratorEvent,
    AiPromptVersion,
    AiRunLog,
    AiToolCallLog,
    AiToolPermission,
    ApprovalRequest,
    AuditEvent,
    Lead,
    Role,
    RoleAssignment,
)
from app.schemas.ai import (
    AiCorrectedEvaluationCaseCreate,
    AiDryRunCreate,
    AiEvaluationCaseCreate,
    AiEvaluationDatasetCreate,
    AiEvaluationDatasetRead,
    AiEvaluationDecision,
    AiEvaluationReviewCreate,
    AiEvaluationRunCreate,
    AiEvaluationRunRead,
    AiOrchestratorEventCreate,
    AiOrchestratorEventRead,
    AiOrchestratorMetrics,
    AiOrchestratorOverview,
    AiPortfolioInstallRead,
    AiPromotionCreate,
    AiPromotionRead,
    AiRollbackCreate,
    AiRunRead,
    AiTraceReview,
)
from app.services.ai import run_to_read

AUTONOMY_ORDER = {"observe": 0, "draft": 1, "recommend": 2, "execute_internal": 3}
PORTFOLIO = (
    (
        "prospecting_intelligence",
        "Prospecting Intelligence",
        "Rank outreach records and explain the evidence behind prioritization.",
        "prospecting.prioritize",
        "high",
    ),
    (
        "inbound_lead",
        "Inbound Lead",
        "Triage new inbound leads and prepare a response draft.",
        "lead.triage",
        "medium",
    ),
    (
        "lead_management",
        "Lead Manager Support",
        "Assist the human Lead Manager with stale-lead protection and next-action proposals.",
        "lead.next_action",
        "medium",
    ),
    (
        "call_intelligence",
        "Call Intelligence",
        "Extract evidence-backed notes from recorded conversations.",
        "call.summarize",
        "high",
    ),
    (
        "appointment_preparation",
        "Appointment Preparation",
        "Build a factual seller appointment briefing.",
        "appointment.brief",
        "medium",
    ),
    (
        "underwriting_comp",
        "Underwriting and Comp",
        "Prepare valuation evidence without approving an offer.",
        "underwriting.analyze",
        "high",
    ),
    (
        "negotiation_coach",
        "Negotiation Coach",
        "Recommend questions and negotiation options within approved authority.",
        "negotiation.coach",
        "high",
    ),
    (
        "disposition",
        "Disposition",
        "Match contracted deals to buyers and draft outreach.",
        "disposition.match",
        "high",
    ),
    (
        "buyer_relationship",
        "Buyer Relationship",
        "Maintain buyer preferences and relationship follow-up drafts.",
        "buyer.follow_up",
        "medium",
    ),
    (
        "transaction_coordinator",
        "Transaction Coordinator",
        "Track transaction milestones and missing internal work.",
        "transaction.coordinate",
        "high",
    ),
    (
        "compliance",
        "Compliance",
        "Flag consent, suppression, and communication-policy risks.",
        "compliance.review",
        "high",
    ),
    (
        "finance_commission",
        "Finance and Commission",
        "Reconcile deal economics and draft commission calculations.",
        "finance.reconcile",
        "high",
    ),
    (
        "marketing_intelligence",
        "Marketing Intelligence",
        "Compare source performance and recommend budget experiments.",
        "marketing.analyze",
        "medium",
    ),
    (
        "executive_operations",
        "Executive Operations",
        "Summarize operating risks, bottlenecks, and decisions for the owner.",
        "operations.brief",
        "high",
    ),
)
DEFAULT_PROMPT = """You are Stonegate Home Buyers' {name} agent.
Operate only on supplied facts. State uncertainty. Never invent seller, property, buyer,
legal, financial, or consent facts.
Do not contact anyone, approve offers, sign contracts, move money, or change external systems.
Return a concise recommendation with evidence, risks, and the next human decision."""


def install_portfolio(db: Session, principal: Principal) -> AiPortfolioInstallRead:
    existing = {
        item.key: item
        for item in db.scalars(
            select(AiAgentDefinition).where(
                AiAgentDefinition.organization_id == principal.organization_id
            )
        ).all()
    }
    created = 0
    for key, name, description, capability, risk in PORTFOLIO:
        if key in existing:
            existing[key].name = name
            existing[key].description = description
            continue
        agent = AiAgentDefinition(
            organization_id=principal.organization_id,
            key=key,
            name=name,
            description=description,
            status="draft",
            model_name="gpt-5.6-terra",
            risk_level=risk,
            requires_human_approval=True,
            autonomy_level="observe",
            max_cost_microusd_per_run=100_000,
            max_daily_cost_microusd=1_000_000,
            max_attempts=2,
            rollback_owner_user_id=principal.user_id,
        )
        db.add(agent)
        db.flush()
        db.add(
            AiPromptVersion(
                organization_id=principal.organization_id,
                agent_definition_id=agent.id,
                version_number=1,
                status="active",
                prompt_text=DEFAULT_PROMPT.format(name=name),
                change_notes="Phase 10 governed baseline",
                created_by_user_id=principal.user_id,
            )
        )
        for tool_key, tool_name, permission in (
            (f"{capability}.read", f"Read inputs for {name}", "read"),
            (f"{capability}.draft", f"Draft {name} output", "draft"),
            (f"{capability}.execute", f"Execute {name} action", "write_blocked"),
        ):
            db.add(
                AiToolPermission(
                    organization_id=principal.organization_id,
                    agent_definition_id=agent.id,
                    tool_key=tool_key,
                    tool_name=tool_name,
                    permission_level=permission,
                    is_enabled=True,
                    requires_approval=permission != "read",
                )
            )
        created += 1
    _audit(
        db,
        principal,
        "ai.portfolio_install",
        "organization",
        principal.organization_id,
        {"created": created},
    )
    db.commit()
    total = int(
        db.scalar(
            select(func.count(AiAgentDefinition.id)).where(
                AiAgentDefinition.organization_id == principal.organization_id
            )
        )
        or 0
    )
    return AiPortfolioInstallRead(
        created_agent_count=created, existing_agent_count=total - created, total_agent_count=total
    )


def register_event(
    db: Session, principal: Principal, payload: AiOrchestratorEventCreate
) -> AiOrchestratorEventRead:
    existing = db.scalar(
        select(AiOrchestratorEvent).where(
            AiOrchestratorEvent.organization_id == principal.organization_id,
            AiOrchestratorEvent.event_key == payload.event_key,
        )
    )
    if existing is not None:
        return _event_read(existing)
    event = AiOrchestratorEvent(
        organization_id=principal.organization_id,
        event_key=payload.event_key,
        event_type=payload.event_type,
        entity_type=payload.entity_type,
        entity_id=payload.entity_id,
        status="pending",
        payload=payload.payload,
        occurred_at=payload.occurred_at or datetime.now(UTC),
    )
    db.add(event)
    db.commit()
    db.refresh(event)
    return _event_read(event)


def create_dry_run(
    db: Session, principal: Principal, payload: AiDryRunCreate, *, parent: AiRunLog | None = None
) -> AiRunRead:
    existing = db.scalar(
        select(AiRunLog).where(
            AiRunLog.organization_id == principal.organization_id,
            AiRunLog.idempotency_key == payload.idempotency_key,
        )
    )
    if existing is not None:
        return run_to_read(existing, _tool_calls(db, principal, existing.id))
    agent = _agent(db, principal, payload.agent_definition_id)
    if agent is None:
        raise ValueError("AI agent not found.")
    if agent.status in {"paused", "retired"}:
        raise ValueError("Paused or retired agents cannot run.")
    prompt = db.scalar(
        select(AiPromptVersion)
        .where(
            AiPromptVersion.organization_id == principal.organization_id,
            AiPromptVersion.agent_definition_id == agent.id,
        )
        .order_by(AiPromptVersion.status.asc(), AiPromptVersion.version_number.desc())
    )
    if prompt is None:
        raise ValueError("The agent needs a prompt before it can run.")
    if (
        payload.lead_id is not None
        and db.scalar(
            select(Lead.id).where(
                Lead.organization_id == principal.organization_id,
                Lead.id == payload.lead_id,
                Lead.archived_at.is_(None),
            )
        )
        is None
    ):
        raise ValueError("Lead not found.")
    event = None
    if payload.orchestrator_event_id is not None:
        event = db.scalar(
            select(AiOrchestratorEvent).where(
                AiOrchestratorEvent.organization_id == principal.organization_id,
                AiOrchestratorEvent.id == payload.orchestrator_event_id,
            )
        )
        if event is None:
            raise ValueError("Orchestrator event not found.")
    start_day = datetime.combine(datetime.now(UTC).date(), time.min, tzinfo=UTC)
    daily_cost = int(
        db.scalar(
            select(func.coalesce(func.sum(AiRunLog.cost_microusd), 0)).where(
                AiRunLog.organization_id == principal.organization_id,
                AiRunLog.agent_definition_id == agent.id,
                AiRunLog.started_at >= start_day,
            )
        )
        or 0
    )
    requested_limit = (
        payload.budget_limit_microusd
        if payload.budget_limit_microusd is not None
        else agent.max_cost_microusd_per_run
    )
    budget_limit = min(requested_limit, agent.max_cost_microusd_per_run)
    budget_status = (
        "daily_limit_exceeded" if daily_cost >= agent.max_daily_cost_microusd else "within_budget"
    )
    run = AiRunLog(
        organization_id=principal.organization_id,
        agent_definition_id=agent.id,
        prompt_version_id=prompt.id,
        lead_id=payload.lead_id,
        status="blocked" if budget_status != "within_budget" else "needs_review",
        model_name=agent.model_name,
        input_summary=payload.input_summary,
        output_summary="Dry run only. No model or external action executed.",
        cost_microusd=0,
        cost_cents=0,
        latency_ms=0,
        started_at=datetime.now(UTC),
        completed_at=datetime.now(UTC),
        orchestrator_event_id=event.id if event else None,
        parent_run_id=parent.id if parent else None,
        requested_by_user_id=principal.user_id,
        execution_mode="dry_run",
        capability_key=payload.capability_key,
        attempt_number=(parent.attempt_number + 1) if parent else 1,
        idempotency_key=payload.idempotency_key,
        budget_limit_microusd=budget_limit,
        budget_status=budget_status,
        trace_status="unreviewed",
        rollback_status="not_required",
        run_metadata={
            "policy": {
                "autonomy_level": agent.autonomy_level,
                "external_actions": "blocked",
                "daily_cost_before_run": daily_cost,
            },
            "proposed_tools": payload.proposed_tools,
        },
    )
    db.add(run)
    db.flush()
    permissions = {
        item.tool_key: item
        for item in db.scalars(
            select(AiToolPermission).where(
                AiToolPermission.organization_id == principal.organization_id,
                AiToolPermission.agent_definition_id == agent.id,
            )
        ).all()
    }
    calls: list[AiToolCallLog] = []
    for key in payload.proposed_tools:
        permission = permissions.get(key)
        allowed = (
            permission is not None
            and permission.is_enabled
            and permission.permission_level != "write_blocked"
            and budget_status == "within_budget"
        )
        call = AiToolCallLog(
            organization_id=principal.organization_id,
            ai_run_log_id=run.id,
            approval_request_id=None,
            tool_key=key,
            status="simulated" if allowed else "blocked",
            requires_approval=bool(permission.requires_approval) if permission else True,
            input_payload={"dry_run": True},
            output_payload={"would_execute": allowed},
            error_message=None
            if allowed
            else "Tool is missing, disabled, write-blocked, or over budget.",
        )
        db.add(call)
        calls.append(call)
    if event is not None:
        event.status = "processed"
        event.processed_at = datetime.now(UTC)
    _audit(
        db,
        principal,
        "ai.dry_run_create",
        "ai_run_log",
        run.id,
        {"capability_key": payload.capability_key, "budget_status": budget_status},
    )
    db.commit()
    db.refresh(run)
    return run_to_read(run, calls)


def retry_run(db: Session, principal: Principal, run_id: UUID) -> AiRunRead | None:
    run = db.scalar(
        select(AiRunLog).where(
            AiRunLog.organization_id == principal.organization_id, AiRunLog.id == run_id
        )
    )
    if run is None:
        return None
    agent = _agent(db, principal, run.agent_definition_id)
    if agent is None or run.attempt_number >= agent.max_attempts:
        raise ValueError("This run has reached its retry limit.")
    if run.status not in {"failed", "blocked"}:
        raise ValueError("Only failed or blocked runs can be retried.")
    return create_dry_run(
        db,
        principal,
        AiDryRunCreate(
            agent_definition_id=agent.id,
            capability_key=run.capability_key,
            input_summary=run.input_summary,
            idempotency_key=f"retry:{run.id}:{run.attempt_number + 1}",
            lead_id=run.lead_id,
            orchestrator_event_id=run.orchestrator_event_id,
            budget_limit_microusd=run.budget_limit_microusd,
            proposed_tools=[item.tool_key for item in _tool_calls(db, principal, run.id)],
        ),
        parent=run,
    )


def review_trace(
    db: Session, principal: Principal, run_id: UUID, payload: AiTraceReview
) -> AiRunRead | None:
    run = db.scalar(
        select(AiRunLog).where(
            AiRunLog.organization_id == principal.organization_id, AiRunLog.id == run_id
        )
    )
    if run is None:
        return None
    run.trace_status = payload.status
    run.trace_reviewed_by_user_id = principal.user_id
    run.trace_reviewed_at = datetime.now(UTC)
    run.trace_review_notes = payload.notes
    if payload.status == "flagged":
        run.rollback_status = "review_required"
    db.commit()
    db.refresh(run)
    return run_to_read(run, _tool_calls(db, principal, run.id))


def create_dataset(
    db: Session, principal: Principal, payload: AiEvaluationDatasetCreate
) -> AiEvaluationDatasetRead:
    if _agent(db, principal, payload.agent_definition_id) is None:
        raise ValueError("AI agent not found.")
    keys = [case.case_key for case in payload.cases]
    if len(keys) != len(set(keys)):
        raise ValueError("Evaluation case keys must be unique.")
    for case in payload.cases:
        violations = evaluation_case_redaction_violations(case)
        if violations:
            raise ValueError(
                f"Evaluation case {case.case_key} failed redaction validation: "
                + "; ".join(violations)
            )
    version = (
        int(
            db.scalar(
                select(func.coalesce(func.max(AiEvaluationDataset.version_number), 0)).where(
                    AiEvaluationDataset.agent_definition_id == payload.agent_definition_id,
                    AiEvaluationDataset.capability_key == payload.capability_key,
                )
            )
            or 0
        )
        + 1
    )
    dataset = AiEvaluationDataset(
        organization_id=principal.organization_id,
        agent_definition_id=payload.agent_definition_id,
        capability_key=payload.capability_key,
        dataset_key=payload.dataset_key,
        name=payload.name,
        version_number=version,
        status="draft",
        description=payload.description,
        minimum_case_count=payload.minimum_case_count,
        minimum_pass_rate_basis_points=payload.minimum_pass_rate_basis_points,
        minimum_factual_accuracy_basis_points=(payload.minimum_factual_accuracy_basis_points),
        minimum_evidence_coverage_basis_points=(payload.minimum_evidence_coverage_basis_points),
        maximum_critical_failures=payload.maximum_critical_failures,
        maximum_average_latency_ms=payload.maximum_average_latency_ms,
        maximum_average_cost_microusd=payload.maximum_average_cost_microusd,
        owner_role_key=payload.owner_role_key,
        case_schema_version=payload.case_schema_version,
        reviewer_instructions=payload.reviewer_instructions,
        disagreement_policy=payload.disagreement_policy,
        redaction_policy=payload.redaction_policy,
        required_review_scopes=list(dict.fromkeys(payload.required_review_scopes)),
        created_by_user_id=principal.user_id,
    )
    db.add(dataset)
    db.flush()
    for item in payload.cases:
        db.add(
            AiEvaluationCase(
                organization_id=principal.organization_id,
                dataset_id=dataset.id,
                **item.model_dump(),
            )
        )
    db.commit()
    db.refresh(dataset)
    return evaluation_dataset_to_read(db, dataset)


def decide_dataset(
    db: Session, principal: Principal, dataset_id: UUID, payload: AiEvaluationDecision
) -> AiEvaluationDatasetRead | None:
    dataset = _dataset(db, principal, dataset_id)
    if dataset is None:
        return None
    cases = _cases(db, dataset.id)
    if payload.decision == "approve" and len(cases) < dataset.minimum_case_count:
        raise ValueError(f"This dataset needs at least {dataset.minimum_case_count} cases.")
    if payload.decision == "approve":
        violations = []
        for case in cases:
            case_violations = evaluation_case_redaction_violations(case)
            if case_violations:
                violations.append((case.case_key, case_violations))
        if violations:
            raise ValueError(
                f"Redaction review is incomplete for {len(violations)} evaluation case(s)."
            )
        approved_scopes = {
            item.review_scope
            for item in _dataset_reviews(db, dataset.id)
            if item.status == "approved"
        }
        missing_scopes = set(dataset.required_review_scopes) - approved_scopes
        if missing_scopes:
            raise ValueError(
                "Dataset approval still needs: "
                + ", ".join(sorted(scope.replace("_", " ") for scope in missing_scopes))
                + "."
            )
    dataset.status = "approved" if payload.decision == "approve" else "retired"
    dataset.approved_by_user_id = principal.user_id if payload.decision == "approve" else None
    dataset.approved_at = datetime.now(UTC) if payload.decision == "approve" else None
    db.commit()
    db.refresh(dataset)
    return evaluation_dataset_to_read(db, dataset)


def review_dataset(
    db: Session,
    principal: Principal,
    dataset_id: UUID,
    payload: AiEvaluationReviewCreate,
) -> AiEvaluationDatasetRead | None:
    dataset = _dataset(db, principal, dataset_id)
    if dataset is None:
        return None
    if dataset.status in {"approved", "retired"}:
        raise ValueError("Approved or retired datasets cannot receive new review decisions.")
    if payload.review_scope not in dataset.required_review_scopes:
        raise ValueError("This review scope is not required for the dataset.")
    role_keys = _principal_role_keys(db, principal)
    if payload.review_scope == "executive":
        eligible_roles = ("owner", "founder_operator", "ceo")
        reviewer_role = next((role for role in eligible_roles if role in role_keys), None)
    else:
        eligible_roles = (dataset.owner_role_key, "owner", "founder_operator")
        reviewer_role = next((role for role in eligible_roles if role in role_keys), None)
    if reviewer_role is None:
        raise PermissionError("Your assigned role cannot sign this review scope.")

    review = db.scalar(
        select(AiEvaluationDatasetReview).where(
            AiEvaluationDatasetReview.organization_id == principal.organization_id,
            AiEvaluationDatasetReview.dataset_id == dataset.id,
            AiEvaluationDatasetReview.review_scope == payload.review_scope,
        )
    )
    now = datetime.now(UTC)
    if review is None:
        review = AiEvaluationDatasetReview(
            organization_id=principal.organization_id,
            dataset_id=dataset.id,
            review_scope=payload.review_scope,
            reviewer_role_key=reviewer_role,
            status="approved" if payload.decision == "approve" else "changes_requested",
            notes=payload.notes,
            reviewed_by_user_id=principal.user_id,
            reviewed_at=now,
        )
        db.add(review)
    else:
        review.reviewer_role_key = reviewer_role
        review.status = "approved" if payload.decision == "approve" else "changes_requested"
        review.notes = payload.notes
        review.reviewed_by_user_id = principal.user_id
        review.reviewed_at = now

    reviews = {
        item.review_scope: item.status
        for item in _dataset_reviews(db, dataset.id)
        if item.review_scope != payload.review_scope
    }
    reviews[payload.review_scope] = review.status
    if review.status == "changes_requested":
        dataset.status = "draft"
    elif all(reviews.get(scope) == "approved" for scope in dataset.required_review_scopes):
        dataset.status = "ready_for_approval"
    _audit(
        db,
        principal,
        "ai.evaluation_dataset_reviewed",
        "ai_evaluation_dataset",
        dataset.id,
        {
            "review_scope": payload.review_scope,
            "decision": payload.decision,
            "reviewer_role_key": reviewer_role,
        },
    )
    db.commit()
    db.refresh(dataset)
    return evaluation_dataset_to_read(db, dataset)


def add_corrected_case_version(
    db: Session,
    principal: Principal,
    dataset_id: UUID,
    payload: AiCorrectedEvaluationCaseCreate,
) -> AiEvaluationDatasetRead | None:
    dataset = _dataset(db, principal, dataset_id)
    if dataset is None:
        return None
    corrected_case = payload.case.model_copy(
        update={
            "source_type": "corrected_production",
            "source_reference": payload.source_reference,
            "redaction_status": "verified",
            "reviewer_notes": payload.correction_notes,
        }
    )
    violations = evaluation_case_redaction_violations(corrected_case)
    if violations:
        raise ValueError(
            "Corrected production case failed redaction validation: " + "; ".join(violations)
        )
    cases = [_case_to_create(case) for case in _cases(db, dataset.id)]
    if corrected_case.case_key in {case.case_key for case in cases}:
        raise ValueError("The corrected case key must be unique in the next dataset version.")
    cases.append(corrected_case)
    return create_dataset(
        db,
        principal,
        AiEvaluationDatasetCreate(
            agent_definition_id=dataset.agent_definition_id,
            capability_key=dataset.capability_key,
            dataset_key=dataset.dataset_key,
            name=dataset.name,
            description=dataset.description,
            minimum_case_count=dataset.minimum_case_count,
            minimum_pass_rate_basis_points=dataset.minimum_pass_rate_basis_points,
            minimum_factual_accuracy_basis_points=(dataset.minimum_factual_accuracy_basis_points),
            minimum_evidence_coverage_basis_points=(dataset.minimum_evidence_coverage_basis_points),
            maximum_critical_failures=dataset.maximum_critical_failures,
            maximum_average_latency_ms=dataset.maximum_average_latency_ms,
            maximum_average_cost_microusd=dataset.maximum_average_cost_microusd,
            owner_role_key=dataset.owner_role_key,
            case_schema_version=dataset.case_schema_version,
            reviewer_instructions=dataset.reviewer_instructions,
            disagreement_policy=dataset.disagreement_policy,
            redaction_policy=dataset.redaction_policy,
            required_review_scopes=cast(
                list[Literal["executive", "role_owner"]],
                dataset.required_review_scopes,
            ),
            cases=cases,
        ),
    )


def run_evaluation(
    db: Session, principal: Principal, payload: AiEvaluationRunCreate
) -> AiEvaluationRunRead:
    dataset = _dataset(db, principal, payload.dataset_id)
    if dataset is None or dataset.status != "approved":
        raise ValueError("An approved evaluation dataset is required.")
    prompt = db.scalar(
        select(AiPromptVersion).where(
            AiPromptVersion.organization_id == principal.organization_id,
            AiPromptVersion.id == payload.prompt_version_id,
            AiPromptVersion.agent_definition_id == dataset.agent_definition_id,
        )
    )
    if prompt is None:
        raise ValueError("Prompt version not found for this agent.")
    cases = _cases(db, dataset.id)
    evaluation = AiEvaluationRun(
        organization_id=principal.organization_id,
        dataset_id=dataset.id,
        prompt_version_id=prompt.id,
        created_by_user_id=principal.user_id,
        status="running",
        execution_mode="fixture",
        model_name="deterministic-fixture",
        case_count=len(cases),
        passed_case_count=0,
        pass_rate_basis_points=0,
        factual_accuracy_basis_points=0,
        evidence_coverage_basis_points=0,
        critical_failure_count=0,
        average_latency_ms=0,
        average_cost_microusd=0,
        total_cost_microusd=0,
        thresholds_passed=False,
        summary={},
        started_at=datetime.now(UTC),
    )
    db.add(evaluation)
    db.flush()
    results: list[AiEvaluationResult] = []
    for case in cases:
        passed, checks, factual_accuracy, evidence_coverage = _evaluate_case(case)
        result = AiEvaluationResult(
            organization_id=principal.organization_id,
            evaluation_run_id=evaluation.id,
            evaluation_case_id=case.id,
            status="passed" if passed else "failed",
            score_basis_points=10_000 if passed else 0,
            factual_accuracy_basis_points=factual_accuracy,
            evidence_coverage_basis_points=evidence_coverage,
            critical_failure=case.is_critical and not passed,
            actual_output=case.candidate_output,
            check_results=checks,
            latency_ms=0,
            cost_microusd=0,
        )
        db.add(result)
        results.append(result)
    passed_count = sum(item.status == "passed" for item in results)
    critical_count = sum(item.critical_failure for item in results)
    pass_rate = round(passed_count / len(cases) * 10_000) if cases else 0
    factual_accuracy = (
        round(sum(item.factual_accuracy_basis_points for item in results) / len(results))
        if results
        else 0
    )
    evidence_coverage = (
        round(sum(item.evidence_coverage_basis_points for item in results) / len(results))
        if results
        else 0
    )
    latency_passed = (
        dataset.maximum_average_latency_ms is None
        or (evaluation.average_latency_ms or 0) <= dataset.maximum_average_latency_ms
    )
    cost_passed = (
        dataset.maximum_average_cost_microusd is None
        or (evaluation.average_cost_microusd or 0) <= dataset.maximum_average_cost_microusd
    )
    thresholds = (
        len(cases) >= dataset.minimum_case_count
        and pass_rate >= dataset.minimum_pass_rate_basis_points
        and factual_accuracy >= dataset.minimum_factual_accuracy_basis_points
        and evidence_coverage >= dataset.minimum_evidence_coverage_basis_points
        and critical_count <= dataset.maximum_critical_failures
        and latency_passed
        and cost_passed
    )
    evaluation.status = "completed"
    evaluation.passed_case_count = passed_count
    evaluation.pass_rate_basis_points = pass_rate
    evaluation.factual_accuracy_basis_points = factual_accuracy
    evaluation.evidence_coverage_basis_points = evidence_coverage
    evaluation.critical_failure_count = critical_count
    evaluation.thresholds_passed = thresholds
    evaluation.summary = {
        "dataset_version": dataset.version_number,
        "thresholds": {
            "pass_rate": pass_rate >= dataset.minimum_pass_rate_basis_points,
            "factual_accuracy": (factual_accuracy >= dataset.minimum_factual_accuracy_basis_points),
            "evidence_coverage": (
                evidence_coverage >= dataset.minimum_evidence_coverage_basis_points
            ),
            "critical_failures": critical_count <= dataset.maximum_critical_failures,
            "case_count": len(cases) >= dataset.minimum_case_count,
            "latency": latency_passed,
            "cost": cost_passed,
        },
    }
    evaluation.completed_at = datetime.now(UTC)
    db.commit()
    db.refresh(evaluation)
    return _evaluation_read(db, evaluation)


def request_promotion(
    db: Session, principal: Principal, agent_id: UUID, payload: AiPromotionCreate
) -> AiPromotionRead:
    agent = _agent(db, principal, agent_id)
    if agent is None:
        raise ValueError("AI agent not found.")
    evaluation = db.scalar(
        select(AiEvaluationRun).where(
            AiEvaluationRun.organization_id == principal.organization_id,
            AiEvaluationRun.id == payload.evaluation_run_id,
        )
    )
    if evaluation is None or not evaluation.thresholds_passed:
        raise ValueError("A passing evaluation run is required before promotion.")
    dataset = _dataset(db, principal, evaluation.dataset_id)
    if dataset is None or dataset.agent_definition_id != agent.id:
        raise ValueError("Evaluation does not belong to this agent.")
    if AUTONOMY_ORDER[payload.to_level] <= AUTONOMY_ORDER.get(agent.autonomy_level, 0):
        raise ValueError("Promotion must increase the current autonomy level.")
    promotion = AiCapabilityPromotion(
        organization_id=principal.organization_id,
        agent_definition_id=agent.id,
        capability_key=dataset.capability_key,
        evaluation_run_id=evaluation.id,
        requested_by_user_id=principal.user_id,
        from_level=agent.autonomy_level,
        to_level=payload.to_level,
        status="pending_approval",
        reason=payload.reason,
    )
    db.add(promotion)
    db.flush()
    approval = ApprovalRequest(
        organization_id=principal.organization_id,
        requested_by_user_id=principal.user_id,
        assigned_to_user_id=agent.rollback_owner_user_id or principal.user_id,
        request_type="ai_capability_promotion",
        entity_type="ai_capability_promotion",
        entity_id=promotion.id,
        status="pending",
        title=f"Promote {agent.name} to {payload.to_level.replace('_', ' ')}",
        summary=f"Evaluation passed for {dataset.capability_key}. Human approval is required.",
        approval_metadata={
            "promotion_id": str(promotion.id),
            "agent_id": str(agent.id),
            "capability_key": dataset.capability_key,
            "evaluation_run_id": str(evaluation.id),
        },
    )
    db.add(approval)
    db.flush()
    promotion.approval_request_id = approval.id
    db.commit()
    db.refresh(promotion)
    return _promotion_read(promotion)


def apply_promotion_decision(
    db: Session, principal: Principal, request: ApprovalRequest, status: str, notes: str | None
) -> None:
    promotion = db.scalar(
        select(AiCapabilityPromotion).where(
            AiCapabilityPromotion.organization_id == principal.organization_id,
            AiCapabilityPromotion.id == request.entity_id,
        )
    )
    if promotion is None or promotion.status != "pending_approval":
        raise ValueError("The AI promotion is no longer pending.")
    promotion.status = "approved" if status == "approved" else "rejected"
    promotion.decision_notes = notes
    promotion.decided_by_user_id = principal.user_id
    if status == "approved":
        promotion.effective_at = datetime.now(UTC)
        agent = _agent(db, principal, promotion.agent_definition_id)
        if agent is not None:
            agent.autonomy_level = promotion.to_level
            agent.status = "active"


def rollback_promotion(
    db: Session, principal: Principal, promotion_id: UUID, payload: AiRollbackCreate
) -> AiPromotionRead | None:
    promotion = db.scalar(
        select(AiCapabilityPromotion).where(
            AiCapabilityPromotion.organization_id == principal.organization_id,
            AiCapabilityPromotion.id == promotion_id,
        )
    )
    if promotion is None:
        return None
    if promotion.status != "approved" or promotion.rolled_back_at is not None:
        raise ValueError("Only an active approved promotion can be rolled back.")
    promotion.status = "rolled_back"
    promotion.rolled_back_at = datetime.now(UTC)
    promotion.rollback_reason = payload.reason
    agent = _agent(db, principal, promotion.agent_definition_id)
    if agent is not None:
        agent.autonomy_level = promotion.from_level
        agent.status = "paused"
    db.commit()
    db.refresh(promotion)
    return _promotion_read(promotion)


def get_overview(db: Session, principal: Principal) -> AiOrchestratorOverview:
    from app.services.ai_copilots import get_copilot_foundation

    events = db.scalars(
        select(AiOrchestratorEvent)
        .where(AiOrchestratorEvent.organization_id == principal.organization_id)
        .order_by(AiOrchestratorEvent.created_at.desc())
        .limit(30)
    ).all()
    datasets = db.scalars(
        select(AiEvaluationDataset)
        .where(AiEvaluationDataset.organization_id == principal.organization_id)
        .order_by(AiEvaluationDataset.created_at.desc())
        .limit(30)
    ).all()
    evaluations = db.scalars(
        select(AiEvaluationRun)
        .where(AiEvaluationRun.organization_id == principal.organization_id)
        .order_by(AiEvaluationRun.created_at.desc())
        .limit(30)
    ).all()
    promotions = db.scalars(
        select(AiCapabilityPromotion)
        .where(AiCapabilityPromotion.organization_id == principal.organization_id)
        .order_by(AiCapabilityPromotion.created_at.desc())
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

    metrics = AiOrchestratorMetrics(
        portfolio_agent_count=count(AiAgentDefinition),
        copilot_count=count(AiCopilotDefinition),
        active_copilot_count=count(AiCopilotDefinition, AiCopilotDefinition.status == "active"),
        governed_run_count=count(AiRunLog, AiRunLog.execution_mode != "manual"),
        unreviewed_trace_count=count(
            AiRunLog, AiRunLog.execution_mode != "manual", AiRunLog.trace_status == "unreviewed"
        ),
        approved_dataset_count=count(AiEvaluationDataset, AiEvaluationDataset.status == "approved"),
        passing_evaluation_count=count(
            AiEvaluationRun, AiEvaluationRun.thresholds_passed.is_(True)
        ),
        pending_promotion_count=count(
            AiCapabilityPromotion, AiCapabilityPromotion.status == "pending_approval"
        ),
        active_promotion_count=count(
            AiCapabilityPromotion, AiCapabilityPromotion.status == "approved"
        ),
        budget_blocked_run_count=count(AiRunLog, AiRunLog.budget_status != "within_budget"),
    )
    return AiOrchestratorOverview(
        metrics=metrics,
        foundation=get_copilot_foundation(db, principal),
        events=[_event_read(item) for item in events],
        datasets=[evaluation_dataset_to_read(db, item) for item in datasets],
        evaluation_runs=[_evaluation_read(db, item) for item in evaluations],
        promotions=[_promotion_read(item) for item in promotions],
    )


SENSITIVE_EVALUATION_KEYS = {
    "name",
    "email",
    "phone",
    "address",
    "ssn",
    "social_security",
    "routing_number",
    "account_number",
    "card_number",
    "api_key",
    "token",
    "password",
    "secret",
}
SENSITIVE_EVALUATION_PATTERNS = (
    re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE),
    re.compile(r"\b\d{3}[-.\s]\d{3}[-.\s]\d{4}\b"),
    re.compile(r"\b\d{3}-\d{2}-\d{4}\b"),
    re.compile(r"\b(?:\d[ -]*?){13,19}\b"),
)


def _evaluate_case(
    case: AiEvaluationCase,
) -> tuple[bool, dict[str, Any], int, int]:
    actual = case.candidate_output
    checks: dict[str, Any] = {}
    checks["candidate_present"] = actual is not None
    if actual is None:
        return False, checks, 0, 0
    expected_items = list(case.expected_output.items())
    matching_items = sum(actual.get(key) == value for key, value in expected_items)
    factual_accuracy = (
        round(matching_items / len(expected_items) * 10_000) if expected_items else 10_000
    )
    checks["expected_values"] = factual_accuracy == 10_000
    required = case.deterministic_checks.get("required_keys", [])
    checks["required_keys"] = all(key in actual for key in required)
    text = json.dumps(actual, sort_keys=True).lower()
    forbidden = case.deterministic_checks.get("forbidden_terms", [])
    checks["forbidden_terms"] = all(str(term).lower() not in text for term in forbidden)
    actual_evidence = actual.get("evidence", [])
    if isinstance(actual_evidence, str):
        actual_evidence = [actual_evidence]
    required_evidence = case.required_evidence
    matched_evidence = sum(item in actual_evidence for item in required_evidence)
    evidence_coverage = (
        round(matched_evidence / len(required_evidence) * 10_000) if required_evidence else 10_000
    )
    checks["evidence_coverage"] = evidence_coverage == 10_000
    checks["redaction"] = not evaluation_case_redaction_violations(case)
    return all(checks.values()), checks, factual_accuracy, evidence_coverage


def evaluation_case_redaction_violations(
    case: AiEvaluationCaseCreate | AiEvaluationCase,
) -> list[str]:
    violations: list[str] = []
    if case.redaction_status != "verified":
        violations.append("redaction status is not verified")
    for label, payload in (
        ("input", case.input_payload),
        ("expected", case.expected_output),
        ("candidate", case.candidate_output),
    ):
        if payload is None:
            continue
        _scan_evaluation_value(payload, label, violations)
    if case.source_reference:
        _scan_evaluation_value(case.source_reference, "source reference", violations)
    return sorted(set(violations))


def _scan_evaluation_value(value: Any, path: str, violations: list[str]) -> None:
    if isinstance(value, dict):
        for key, nested in value.items():
            normalized = str(key).lower().strip()
            if normalized in SENSITIVE_EVALUATION_KEYS:
                violations.append(f"{path} contains prohibited key '{key}'")
            _scan_evaluation_value(nested, f"{path}.{key}", violations)
        return
    if isinstance(value, list):
        for index, nested in enumerate(value):
            _scan_evaluation_value(nested, f"{path}[{index}]", violations)
        return
    if not isinstance(value, str):
        return
    if any(pattern.search(value) for pattern in SENSITIVE_EVALUATION_PATTERNS):
        violations.append(f"{path} contains a possible direct identifier or credential")


def _case_to_create(case: AiEvaluationCase) -> AiEvaluationCaseCreate:
    return AiEvaluationCaseCreate(
        case_key=case.case_key,
        name=case.name,
        input_payload=case.input_payload,
        expected_output=case.expected_output,
        candidate_output=case.candidate_output,
        deterministic_checks=case.deterministic_checks,
        risk_tags=case.risk_tags,
        is_critical=case.is_critical,
        case_type=cast(
            Literal["operating", "policy", "failure", "adversarial"],
            case.case_type,
        ),
        scenario_family=case.scenario_family,
        source_type=cast(
            Literal["synthetic", "corrected_production"],
            case.source_type,
        ),
        source_reference=case.source_reference,
        redaction_status=cast(
            Literal["verified", "needs_review"],
            case.redaction_status,
        ),
        expected_uncertainty=case.expected_uncertainty,
        required_evidence=case.required_evidence,
        prohibited_behaviors=case.prohibited_behaviors,
        reviewer_notes=case.reviewer_notes,
    )


def _agent(db: Session, principal: Principal, agent_id: UUID) -> AiAgentDefinition | None:
    return db.scalar(
        select(AiAgentDefinition).where(
            AiAgentDefinition.organization_id == principal.organization_id,
            AiAgentDefinition.id == agent_id,
        )
    )


def _dataset(db: Session, principal: Principal, dataset_id: UUID) -> AiEvaluationDataset | None:
    return db.scalar(
        select(AiEvaluationDataset).where(
            AiEvaluationDataset.organization_id == principal.organization_id,
            AiEvaluationDataset.id == dataset_id,
        )
    )


def _cases(db: Session, dataset_id: UUID) -> list[AiEvaluationCase]:
    return list(
        db.scalars(
            select(AiEvaluationCase)
            .where(AiEvaluationCase.dataset_id == dataset_id)
            .order_by(AiEvaluationCase.created_at)
        ).all()
    )


def _dataset_reviews(db: Session, dataset_id: UUID) -> list[AiEvaluationDatasetReview]:
    return list(
        db.scalars(
            select(AiEvaluationDatasetReview)
            .where(AiEvaluationDatasetReview.dataset_id == dataset_id)
            .order_by(AiEvaluationDatasetReview.review_scope)
        ).all()
    )


def _principal_role_keys(db: Session, principal: Principal) -> set[str]:
    return set(
        db.scalars(
            select(Role.key)
            .join(RoleAssignment, RoleAssignment.role_id == Role.id)
            .where(
                RoleAssignment.organization_id == principal.organization_id,
                RoleAssignment.user_id == principal.user_id,
            )
        ).all()
    )


def _tool_calls(db: Session, principal: Principal, run_id: UUID) -> list[AiToolCallLog]:
    return list(
        db.scalars(
            select(AiToolCallLog).where(
                AiToolCallLog.organization_id == principal.organization_id,
                AiToolCallLog.ai_run_log_id == run_id,
            )
        ).all()
    )


def _event_read(item: AiOrchestratorEvent) -> AiOrchestratorEventRead:
    return AiOrchestratorEventRead(
        id=item.id,
        event_key=item.event_key,
        event_type=item.event_type,
        entity_type=item.entity_type,
        entity_id=item.entity_id,
        status=item.status,
        payload=item.payload,
        occurred_at=item.occurred_at,
        processed_at=item.processed_at,
        last_error=item.last_error,
        created_at=item.created_at,
    )


def evaluation_dataset_to_read(
    db: Session,
    item: AiEvaluationDataset,
) -> AiEvaluationDatasetRead:
    from app.schemas.ai import AiEvaluationCaseRead, AiEvaluationDatasetReviewRead

    return AiEvaluationDatasetRead(
        id=item.id,
        agent_definition_id=item.agent_definition_id,
        capability_key=item.capability_key,
        dataset_key=item.dataset_key,
        name=item.name,
        version_number=item.version_number,
        status=item.status,
        description=item.description,
        minimum_case_count=item.minimum_case_count,
        minimum_pass_rate_basis_points=item.minimum_pass_rate_basis_points,
        minimum_factual_accuracy_basis_points=(item.minimum_factual_accuracy_basis_points),
        minimum_evidence_coverage_basis_points=(item.minimum_evidence_coverage_basis_points),
        maximum_critical_failures=item.maximum_critical_failures,
        maximum_average_latency_ms=item.maximum_average_latency_ms,
        maximum_average_cost_microusd=item.maximum_average_cost_microusd,
        owner_role_key=item.owner_role_key,
        case_schema_version=item.case_schema_version,
        reviewer_instructions=item.reviewer_instructions,
        disagreement_policy=item.disagreement_policy,
        redaction_policy=item.redaction_policy,
        required_review_scopes=item.required_review_scopes,
        reviews=[
            AiEvaluationDatasetReviewRead(
                id=review.id,
                review_scope=review.review_scope,
                reviewer_role_key=review.reviewer_role_key,
                status=review.status,
                notes=review.notes,
                reviewed_by_user_id=review.reviewed_by_user_id,
                reviewed_at=review.reviewed_at,
            )
            for review in _dataset_reviews(db, item.id)
        ],
        approved_by_user_id=item.approved_by_user_id,
        approved_at=item.approved_at,
        cases=[
            AiEvaluationCaseRead(
                id=case.id,
                case_key=case.case_key,
                name=case.name,
                input_payload=case.input_payload,
                expected_output=case.expected_output,
                candidate_output=case.candidate_output,
                deterministic_checks=case.deterministic_checks,
                risk_tags=case.risk_tags,
                is_critical=case.is_critical,
                case_type=case.case_type,
                scenario_family=case.scenario_family,
                source_type=case.source_type,
                source_reference=case.source_reference,
                redaction_status=case.redaction_status,
                expected_uncertainty=case.expected_uncertainty,
                required_evidence=case.required_evidence,
                prohibited_behaviors=case.prohibited_behaviors,
                reviewer_notes=case.reviewer_notes,
            )
            for case in _cases(db, item.id)
        ],
        created_at=item.created_at,
    )


def _evaluation_read(db: Session, item: AiEvaluationRun) -> AiEvaluationRunRead:
    from app.schemas.ai import AiEvaluationResultRead

    results = db.scalars(
        select(AiEvaluationResult)
        .where(AiEvaluationResult.evaluation_run_id == item.id)
        .order_by(AiEvaluationResult.created_at)
    ).all()
    return AiEvaluationRunRead(
        id=item.id,
        dataset_id=item.dataset_id,
        prompt_version_id=item.prompt_version_id,
        status=item.status,
        execution_mode=item.execution_mode,
        model_name=item.model_name,
        case_count=item.case_count,
        passed_case_count=item.passed_case_count,
        pass_rate_basis_points=item.pass_rate_basis_points,
        factual_accuracy_basis_points=item.factual_accuracy_basis_points,
        evidence_coverage_basis_points=item.evidence_coverage_basis_points,
        critical_failure_count=item.critical_failure_count,
        average_latency_ms=item.average_latency_ms,
        average_cost_microusd=item.average_cost_microusd,
        total_cost_microusd=item.total_cost_microusd,
        thresholds_passed=item.thresholds_passed,
        summary=item.summary,
        started_at=item.started_at,
        completed_at=item.completed_at,
        results=[
            AiEvaluationResultRead(
                id=result.id,
                evaluation_case_id=result.evaluation_case_id,
                status=result.status,
                score_basis_points=result.score_basis_points,
                factual_accuracy_basis_points=(result.factual_accuracy_basis_points),
                evidence_coverage_basis_points=(result.evidence_coverage_basis_points),
                critical_failure=result.critical_failure,
                actual_output=result.actual_output,
                check_results=result.check_results,
                latency_ms=result.latency_ms,
                cost_microusd=result.cost_microusd,
                error_message=result.error_message,
            )
            for result in results
        ],
        created_at=item.created_at,
    )


def _promotion_read(item: AiCapabilityPromotion) -> AiPromotionRead:
    return AiPromotionRead(
        id=item.id,
        agent_definition_id=item.agent_definition_id,
        capability_key=item.capability_key,
        evaluation_run_id=item.evaluation_run_id,
        approval_request_id=item.approval_request_id,
        from_level=item.from_level,
        to_level=item.to_level,
        status=item.status,
        reason=item.reason,
        decision_notes=item.decision_notes,
        effective_at=item.effective_at,
        rolled_back_at=item.rolled_back_at,
        rollback_reason=item.rollback_reason,
        created_at=item.created_at,
    )


def _audit(
    db: Session,
    principal: Principal,
    action: str,
    entity_type: str,
    entity_id: UUID,
    value: dict[str, Any],
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
            new_value=value,
            reason="Governed AI control plane",
        )
    )
    db.add(
        ActivityEvent(
            organization_id=principal.organization_id,
            actor_user_id=principal.user_id,
            entity_type=entity_type,
            entity_id=entity_id,
            event_type=action,
            summary=action.replace(".", " ").title(),
        )
    )
