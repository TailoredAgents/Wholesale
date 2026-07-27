import json
from datetime import UTC, datetime, timedelta
from typing import cast
from uuid import UUID

from pydantic import ValidationError
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.auth import Principal
from app.models.foundation import (
    AiAgentDefinition,
    AiCapabilityRuntimePolicy,
    AiRunLog,
    AuditEvent,
    ManagementCopilotRecommendation,
    ManagementCopilotReview,
)
from app.schemas.ai import AiRuntimeExecuteCreate
from app.schemas.management_copilots import (
    ManagementCapability,
    ManagementCopilotAnalyzeRead,
    ManagementCopilotAnalyzeRequest,
    ManagementCopilotMetrics,
    ManagementCopilotOutput,
    ManagementCopilotOverview,
    ManagementCopilotRecommendationRead,
    ManagementCopilotReviewRead,
    ManagementCopilotReviewRequest,
)
from app.services.ai_runtime import execute_runtime, get_runtime_overview
from app.services.management_intelligence import build_management_facts

CAPABILITY_CONFIG: dict[ManagementCapability, dict[str, object]] = {
    "finance.reconcile": {
        "agent_key": "finance_commission",
        "copilot_name": "Finance Copilot",
        "restrictions": [
            "Do not mark a deal funded or approve a reconciliation.",
            "Do not approve or alter compensation, reserves, or distributions.",
            "Do not approve or post journals, match bank lines, close periods, or move money.",
            "Do not change accounting policy or make a final tax classification.",
            "Treat classification, journal, and bank-match output only as review proposals.",
            "Distinguish recorded amounts from missing or conflicting evidence.",
        ],
    },
    "finance.tax_review": {
        "agent_key": "tax_deductions",
        "copilot_name": "Tax and Deductions Copilot",
        "restrictions": [
            "Do not file a return, submit an election, or represent tax-professional approval.",
            "Do not promise deductibility or final tax treatment.",
            "Do not post, delete, or alter accounting entries.",
            "Do not move money or approve owner compensation.",
            "Separate recorded facts, missing evidence, proposed classification, and professional decisions.",
        ],
    },
    "marketing.analyze": {
        "agent_key": "marketing_intelligence",
        "copilot_name": "Marketing Copilot",
        "restrictions": [
            "Do not change budgets, campaigns, creative, audiences, or attribution.",
            "Do not publish an experiment or send an offline conversion.",
            "Do not recommend scaling from a small or incomplete sample without warning.",
            "Distinguish correlation, attribution, and confirmed funded revenue.",
        ],
    },
    "operations.brief": {
        "agent_key": "executive_operations",
        "copilot_name": "Executive Copilot",
        "restrictions": [
            "Do not change staffing, budgets, priorities, permissions, or AI authority.",
            "Do not approve exceptions, offers, buyers, payments, or market launches.",
            "Separate confirmed facts, estimates, and recommendations.",
            "Use only aggregate operating evidence and identify stale or missing data.",
        ],
    },
}


def ensure_management_capability(
    db: Session,
    principal: Principal,
    capability_key: ManagementCapability,
) -> None:
    if capability_key != "finance.tax_review":
        return
    installed = db.scalar(
        select(AiCapabilityRuntimePolicy.id).where(
            AiCapabilityRuntimePolicy.organization_id == principal.organization_id,
            AiCapabilityRuntimePolicy.capability_key == capability_key,
        )
    )
    if installed is not None:
        return
    from app.services.ai_copilots import install_copilot_foundation
    from app.services.ai_runtime import install_runtime

    install_copilot_foundation(db, principal)
    install_runtime(db, principal)


def get_management_copilot_overview(
    db: Session,
    principal: Principal,
    capability_key: ManagementCapability,
    period_days: int,
) -> ManagementCopilotOverview:
    ensure_management_capability(db, principal, capability_key)
    facts = build_management_facts(db, principal, capability_key, period_days)
    runtime = get_runtime_overview(db, principal)
    statuses = {item.capability_key: item.status for item in runtime.capabilities}
    recommendations = list(
        db.scalars(
            select(ManagementCopilotRecommendation)
            .where(
                ManagementCopilotRecommendation.organization_id
                == principal.organization_id,
                ManagementCopilotRecommendation.capability_key == capability_key,
                ManagementCopilotRecommendation.reporting_period_days == period_days,
            )
            .order_by(ManagementCopilotRecommendation.generated_at.desc())
            .limit(20)
        ).all()
    )
    config = CAPABILITY_CONFIG[capability_key]
    return ManagementCopilotOverview(
        capability_key=capability_key,
        copilot_name=str(config["copilot_name"]),
        pilot_mode="draft_only",
        runtime_status=runtime.status,
        capability_status=statuses.get(capability_key, "not_installed"),
        external_actions_blocked=(
            runtime.policy is None or not runtime.policy.external_actions_enabled
        ),
        reporting_period_days=period_days,
        health_score=facts["health_score"],
        health_band=facts["health_band"],
        readiness_gaps=facts["readiness_gaps"],
        risk_alerts=facts["risk_alerts"],
        metric_cards=facts["metric_cards"],
        recommendations=[
            recommendation_read(item) for item in recommendations
        ],
        metrics=_metrics(db, principal, capability_key),
    )


def analyze_management(
    db: Session,
    principal: Principal,
    capability_key: ManagementCapability,
    payload: ManagementCopilotAnalyzeRequest,
) -> ManagementCopilotAnalyzeRead:
    ensure_management_capability(db, principal, capability_key)
    facts = build_management_facts(
        db,
        principal,
        capability_key,
        payload.period_days,
    )
    config = CAPABILITY_CONFIG[capability_key]
    agent = db.scalar(
        select(AiAgentDefinition).where(
            AiAgentDefinition.organization_id == principal.organization_id,
            AiAgentDefinition.key == config["agent_key"],
        )
    )
    if agent is None:
        raise ValueError("Install the governed AI agent portfolio first.")
    idempotency_key = payload.idempotency_key or (
        f"management:{capability_key}:{payload.period_days}:"
        f"{facts['fingerprint'][:24]}"
    )
    existing = db.scalar(
        select(ManagementCopilotRecommendation).where(
            ManagementCopilotRecommendation.organization_id
            == principal.organization_id,
            ManagementCopilotRecommendation.idempotency_key == idempotency_key,
        )
    )
    if existing is not None:
        if existing.ai_run_log_id is None:
            raise ValueError("The existing recommendation has no governed AI trace.")
        return ManagementCopilotAnalyzeRead(
            run_id=existing.ai_run_log_id,
            run_status="needs_review",
            message="The current management draft is already available.",
            recommendation=recommendation_read(existing),
        )

    run = execute_runtime(
        db,
        principal,
        AiRuntimeExecuteCreate(
            agent_definition_id=agent.id,
            capability_key=capability_key,
            idempotency_key=idempotency_key,
            input_payload={
                "pilot_mode": "draft_only",
                "period_days": payload.period_days,
                "health_score": facts["health_score"],
                "readiness_gaps": facts["readiness_gaps"],
                "deterministic_risk_alerts": [
                    item.model_dump(mode="json") for item in facts["risk_alerts"]
                ],
                "restrictions": config["restrictions"],
                "required_output_rules": [
                    "Every factual statement must cite supplied evidence.",
                    "Every proposed action remains a draft requiring a human decision.",
                    "Do not claim any external or financial action was executed.",
                    *(
                        [
                            (
                                "Use exact Stonegate citation identifiers for every "
                                "accounting conclusion."
                            ),
                            (
                                "Propose a bank match only when the deterministic context "
                                "contains one exact unused cash candidate; cite both records."
                            ),
                            (
                                "Cite the source and approved posting rule for every "
                                "classification or balanced-journal proposal."
                            ),
                            (
                                "Explain statement variance without inventing a cause; "
                                "request evidence when causation is not recorded."
                            ),
                        ]
                        if capability_key
                        in {"finance.reconcile", "finance.tax_review"}
                        else []
                    ),
                ],
            },
        ),
    )
    if run.status not in {"needs_review", "completed"} or not run.output_summary:
        return ManagementCopilotAnalyzeRead(
            run_id=run.id,
            run_status=run.status,
            message=run.error_message or "The governed runtime did not produce a draft.",
            recommendation=None,
        )
    try:
        parsed = ManagementCopilotOutput.model_validate(
            json.loads(run.output_summary)
        )
    except (json.JSONDecodeError, ValidationError) as exc:
        _record_blocked_output(
            db,
            principal,
            capability_key,
            run.id,
            "The model response did not match the governed output contract.",
        )
        raise ValueError(
            "The model response did not match the management copilot contract."
        ) from exc
    try:
        _validate_output(parsed, capability_key)
    except ValueError as exc:
        _record_blocked_output(
            db,
            principal,
            capability_key,
            run.id,
            str(exc),
        )
        raise

    recommendation = ManagementCopilotRecommendation(
        organization_id=principal.organization_id,
        capability_key=capability_key,
        reporting_period_days=payload.period_days,
        generated_for_user_id=principal.user_id,
        ai_run_log_id=run.id,
        idempotency_key=idempotency_key,
        status="draft",
        output_payload=parsed.model_dump(mode="json"),
        evidence_snapshot={
            "health_score": facts["health_score"],
            "health_band": facts["health_band"],
            "readiness_gaps": facts["readiness_gaps"],
            "risk_alerts": [
                item.model_dump(mode="json") for item in facts["risk_alerts"]
            ],
            "metric_cards": [
                item.model_dump(mode="json") for item in facts["metric_cards"]
            ],
            "source_fingerprint": facts["fingerprint"],
        },
        confidence_score=parsed.confidence,
        generated_at=datetime.now(UTC),
        reviewed_at=None,
    )
    db.add(recommendation)
    db.flush()
    _audit(
        db,
        principal,
        "management.copilot_recommendation_generated",
        recommendation.id,
        {
            "capability_key": capability_key,
            "reporting_period_days": payload.period_days,
            "financial_changes_applied": False,
            "marketing_changes_applied": False,
            "operating_changes_applied": False,
            "external_actions_executed": False,
        },
    )
    db.commit()
    db.refresh(recommendation)
    return ManagementCopilotAnalyzeRead(
        run_id=run.id,
        run_status=run.status,
        message="Draft management guidance generated for human review.",
        recommendation=recommendation_read(recommendation),
    )


def review_management_recommendation(
    db: Session,
    principal: Principal,
    capability_key: ManagementCapability,
    recommendation_id: UUID,
    payload: ManagementCopilotReviewRequest,
) -> ManagementCopilotReviewRead | None:
    recommendation = db.scalar(
        select(ManagementCopilotRecommendation).where(
            ManagementCopilotRecommendation.organization_id
            == principal.organization_id,
            ManagementCopilotRecommendation.capability_key == capability_key,
            ManagementCopilotRecommendation.id == recommendation_id,
        )
    )
    if recommendation is None:
        return None
    existing = db.scalar(
        select(ManagementCopilotReview).where(
            ManagementCopilotReview.recommendation_id == recommendation.id
        )
    )
    if existing is not None:
        return review_read(existing)
    if recommendation.status != "draft":
        raise ValueError("Only a draft recommendation can be reviewed.")

    if payload.decision == "edited":
        assert payload.final_output is not None
        try:
            parsed = ManagementCopilotOutput.model_validate(payload.final_output)
        except ValidationError as exc:
            raise ValueError(
                "The corrected output must preserve the management response contract."
            ) from exc
        _validate_output(parsed, capability_key)
        final_output = parsed.model_dump(mode="json")
    elif payload.decision == "accepted":
        final_output = recommendation.output_payload
    else:
        final_output = None

    now = datetime.now(UTC)
    review = ManagementCopilotReview(
        organization_id=principal.organization_id,
        recommendation_id=recommendation.id,
        reviewed_by_user_id=principal.user_id,
        decision=payload.decision,
        original_output=recommendation.output_payload,
        final_output=final_output,
        notes=payload.notes,
        estimated_time_saved_seconds=payload.estimated_time_saved_seconds,
        reviewed_at=now,
    )
    db.add(review)
    recommendation.status = payload.decision
    recommendation.reviewed_at = now
    _audit(
        db,
        principal,
        "management.copilot_recommendation_reviewed",
        recommendation.id,
        {
            "capability_key": capability_key,
            "decision": payload.decision,
            "financial_changes_applied": False,
            "marketing_changes_applied": False,
            "operating_changes_applied": False,
            "external_actions_executed": False,
        },
    )
    db.commit()
    db.refresh(review)
    return review_read(review)


def recommendation_read(
    item: ManagementCopilotRecommendation,
) -> ManagementCopilotRecommendationRead:
    return ManagementCopilotRecommendationRead(
        id=item.id,
        capability_key=cast(ManagementCapability, item.capability_key),
        reporting_period_days=item.reporting_period_days,
        ai_run_log_id=item.ai_run_log_id,
        status=item.status,
        output_payload=ManagementCopilotOutput.model_validate(item.output_payload),
        confidence_score=item.confidence_score,
        generated_at=item.generated_at,
        reviewed_at=item.reviewed_at,
    )


def review_read(item: ManagementCopilotReview) -> ManagementCopilotReviewRead:
    return ManagementCopilotReviewRead(
        id=item.id,
        recommendation_id=item.recommendation_id,
        decision=item.decision,
        final_output=(
            ManagementCopilotOutput.model_validate(item.final_output)
            if item.final_output is not None
            else None
        ),
        notes=item.notes,
        estimated_time_saved_seconds=item.estimated_time_saved_seconds,
        reviewed_at=item.reviewed_at,
    )


def _validate_output(
    output: ManagementCopilotOutput,
    capability_key: ManagementCapability,
) -> None:
    evidence_groups = [
        *(item.evidence for item in output.confirmed_facts),
        *(item.evidence for item in output.exceptions),
        *(item.evidence for item in output.analysis),
        *(item.evidence for item in output.draft_actions),
        *(item.evidence for item in output.decision_requests),
    ]
    if any(not evidence for evidence in evidence_groups):
        raise ValueError("Every management conclusion must include supporting evidence.")
    if capability_key in {"finance.reconcile", "finance.tax_review"}:
        exact_prefixes = (
            "accounting_",
            "balance_sheet:",
            "bank_",
            "close_check:",
            "deal_deduction:",
            "deal_reconciliation:",
            "finance_summary:",
            "financial_statement:",
            "journal_",
            "marketing_spend:",
            "revenue_record:",
            "trial_balance:",
        )
        if any(
            not any(reference.startswith(exact_prefixes) for reference in evidence)
            for evidence in evidence_groups
        ):
            raise ValueError(
                "Every finance conclusion must cite an exact Stonegate source identifier."
            )
        if not any(
            reference.startswith(exact_prefixes) for reference in output.evidence
        ):
            raise ValueError(
                "Finance evidence must include an exact Stonegate source identifier."
            )
    completed_action_claims = (
        "i changed ",
        "i approved ",
        "i posted ",
        "i paid ",
        "i moved ",
        "i matched ",
        "i closed ",
        "i published ",
        "i sent ",
    )
    serialized = json.dumps(output.model_dump(mode="json")).lower()
    if any(claim in serialized for claim in completed_action_claims):
        raise ValueError("The management draft claimed an action was already executed.")


def _metrics(
    db: Session,
    principal: Principal,
    capability_key: ManagementCapability,
) -> ManagementCopilotMetrics:
    since = datetime.now(UTC) - timedelta(days=30)
    recommendations = list(
        db.scalars(
            select(ManagementCopilotRecommendation).where(
                ManagementCopilotRecommendation.organization_id
                == principal.organization_id,
                ManagementCopilotRecommendation.capability_key == capability_key,
                ManagementCopilotRecommendation.generated_at >= since,
            )
        ).all()
    )
    recommendation_ids = [item.id for item in recommendations]
    reviews = (
        list(
            db.scalars(
                select(ManagementCopilotReview).where(
                    ManagementCopilotReview.organization_id
                    == principal.organization_id,
                    ManagementCopilotReview.recommendation_id.in_(
                        recommendation_ids
                    ),
                )
            ).all()
        )
        if recommendation_ids
        else []
    )
    reviewed = len(reviews)
    accepted_or_edited = sum(
        item.decision in {"accepted", "edited"} for item in reviews
    )
    edited = sum(item.decision == "edited" for item in reviews)
    rejected = sum(item.decision == "rejected" for item in reviews)
    run_ids = [
        item.ai_run_log_id
        for item in recommendations
        if item.ai_run_log_id is not None
    ]
    run_metrics = (
        db.execute(
            select(
                func.avg(AiRunLog.latency_ms),
                func.coalesce(func.sum(AiRunLog.cost_microusd), 0),
            ).where(
                AiRunLog.organization_id == principal.organization_id,
                AiRunLog.id.in_(run_ids),
            )
        ).one()
        if run_ids
        else (None, 0)
    )
    blocked_output_count = int(
        db.scalar(
            select(func.count(AuditEvent.id)).where(
                AuditEvent.organization_id == principal.organization_id,
                AuditEvent.action
                == f"management.copilot_output_blocked.{capability_key}",
                AuditEvent.created_at >= since,
            )
        )
        or 0
    )
    return ManagementCopilotMetrics(
        generated=len(recommendations),
        reviewed=reviewed,
        accepted_or_corrected_rate_basis_points=(
            round(accepted_or_edited / reviewed * 10_000) if reviewed else 0
        ),
        correction_rate_basis_points=(
            round(edited / reviewed * 10_000) if reviewed else 0
        ),
        rejection_rate_basis_points=(
            round(rejected / reviewed * 10_000) if reviewed else 0
        ),
        blocked_output_count=blocked_output_count,
        average_latency_ms=(
            round(float(run_metrics[0])) if run_metrics[0] is not None else None
        ),
        total_cost_microusd=int(run_metrics[1] or 0),
        estimated_time_saved_minutes=round(
            sum(item.estimated_time_saved_seconds for item in reviews) / 60
        ),
    )


def _record_blocked_output(
    db: Session,
    principal: Principal,
    capability_key: ManagementCapability,
    run_id: UUID,
    reason: str,
) -> None:
    db.add(
        AuditEvent(
            organization_id=principal.organization_id,
            actor_user_id=principal.user_id,
            actor_type="system",
            action=f"management.copilot_output_blocked.{capability_key}",
            entity_type="ai_run_log",
            entity_id=run_id,
            previous_value=None,
            new_value={
                "capability_key": capability_key,
                "reason": reason[:500],
                "financial_changes_applied": False,
                "external_actions_executed": False,
            },
            reason="Governed management Copilot output validation",
        )
    )
    db.commit()


def _audit(
    db: Session,
    principal: Principal,
    action: str,
    entity_id: UUID,
    value: dict[str, object],
) -> None:
    db.add(
        AuditEvent(
            organization_id=principal.organization_id,
            actor_user_id=principal.user_id,
            actor_type="user",
            action=action,
            entity_type="management_copilot_recommendation",
            entity_id=entity_id,
            previous_value=None,
            new_value=value,
            reason="AI9 management copilot draft-only pilot",
        )
    )
