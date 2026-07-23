import hashlib
import json
from datetime import UTC, datetime, time, timedelta
from uuid import UUID

from pydantic import ValidationError
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.auth import Principal
from app.models.foundation import (
    AiAgentDefinition,
    AiRunLog,
    Appointment,
    AuditEvent,
    Conversation,
    Lead,
    LeadManagementCase,
    LeadManagerCopilotRecommendation,
    LeadManagerCopilotReview,
    LeadQualificationScriptVersion,
    LeadQualificationSession,
)
from app.schemas.ai import AiRuntimeExecuteCreate
from app.schemas.lead_manager import (
    LeadManagerCopilotAnalyzeRead,
    LeadManagerCopilotAnalyzeRequest,
    LeadManagerCopilotMetrics,
    LeadManagerCopilotModelOutput,
    LeadManagerCopilotOverview,
    LeadManagerCopilotRecommendationRead,
    LeadManagerCopilotReviewRead,
    LeadManagerCopilotReviewRequest,
    LeadManagerCopilotWorkItemRead,
)
from app.services.ai_runtime import execute_runtime, get_runtime_overview
from app.services.lead_manager import (
    as_utc,
    case_read,
    ensure_case_access,
    get_active_script,
    scoped_case,
)

LEAD_FIELD_BY_QUESTION = {
    "motivation": "motivation",
    "timeline": "desired_timeline",
    "property_condition": "property_condition",
    "occupancy": "occupancy_status",
    "asking_price": "asking_price",
    "mortgage_balance": "mortgage_balance",
}
RECOMMENDATION_STATUSES = {"draft", "accepted", "edited", "rejected"}


def get_copilot_overview(
    db: Session,
    principal: Principal,
) -> LeadManagerCopilotOverview:
    now = datetime.now(UTC)
    cases = _visible_cases(db, principal)
    work_items = sorted(
        (_work_item(db, case, now) for case in cases if case.status != "closed"),
        key=lambda item: (-item.priority_score, item.seller_name.lower()),
    )
    all_recommendations = list(
        db.scalars(
            _visible_recommendations_statement(principal)
            .order_by(LeadManagerCopilotRecommendation.generated_at.desc())
        ).all()
    )
    runtime = get_runtime_overview(db, principal)
    lead_runtime = next(
        (
            capability
            for capability in runtime.capabilities
            if capability.capability_key == "lead.next_action"
        ),
        None,
    )
    return LeadManagerCopilotOverview(
        pilot_mode="draft_only",
        runtime_status=runtime.status,
        capability_status=lead_runtime.status if lead_runtime else "not_installed",
        external_actions_blocked=(
            runtime.policy is None or not runtime.policy.external_actions_enabled
        ),
        work_items=work_items,
        recommendations=[
            recommendation_read(item) for item in all_recommendations[:50]
        ],
        metrics=_copilot_metrics(db, principal, cases, all_recommendations, now),
    )


def analyze_case(
    db: Session,
    principal: Principal,
    case_id: UUID,
    payload: LeadManagerCopilotAnalyzeRequest,
) -> LeadManagerCopilotAnalyzeRead | None:
    case = scoped_case(db, principal, case_id)
    if case is None:
        return None
    ensure_case_access(principal, case)
    now = datetime.now(UTC)
    work_item = _work_item(db, case, now)
    agent = db.scalar(
        select(AiAgentDefinition).where(
            AiAgentDefinition.organization_id == principal.organization_id,
            AiAgentDefinition.key == "lead_management",
        )
    )
    if agent is None:
        raise ValueError("Install the governed AI agent portfolio first.")
    idempotency_key = payload.idempotency_key or _analysis_idempotency_key(
        db, case, work_item
    )
    existing = db.scalar(
        select(LeadManagerCopilotRecommendation).where(
            LeadManagerCopilotRecommendation.organization_id == principal.organization_id,
            LeadManagerCopilotRecommendation.idempotency_key == idempotency_key,
        )
    )
    if existing is not None:
        if existing.ai_run_log_id is None:
            raise ValueError("The existing recommendation has no governed AI trace.")
        return LeadManagerCopilotAnalyzeRead(
            run_id=existing.ai_run_log_id,
            run_status="needs_review",
            message="The current draft recommendation is already available.",
            recommendation=recommendation_read(existing),
        )

    run = execute_runtime(
        db,
        principal,
        AiRuntimeExecuteCreate(
            agent_definition_id=agent.id,
            capability_key="lead.next_action",
            idempotency_key=idempotency_key,
            input_payload={
                "pilot_mode": "draft_only",
                "priority_score": work_item.priority_score,
                "priority_band": work_item.priority_band,
                "recommended_action": work_item.recommended_action,
                "alerts": work_item.alerts,
                "qualification_gaps": work_item.qualification_gaps,
                "recommended_questions": work_item.recommended_questions,
                "deterministic_evidence": work_item.evidence,
                "restrictions": [
                    "Do not send a message.",
                    "Do not change CRM facts.",
                    "Do not schedule an appointment.",
                    "Do not transfer lead ownership.",
                    "Return drafts for human review only.",
                ],
            },
            lead_id=case.lead_id,
        ),
    )
    if run.status not in {"needs_review", "completed"} or not run.output_summary:
        return LeadManagerCopilotAnalyzeRead(
            run_id=run.id,
            run_status=run.status,
            message=run.error_message or "The governed runtime did not produce a draft.",
            recommendation=None,
        )
    try:
        raw_output = json.loads(run.output_summary)
        model_output = LeadManagerCopilotModelOutput.model_validate(raw_output)
    except (json.JSONDecodeError, ValidationError) as exc:
        raise ValueError(
            "The model response did not match the Lead Manager Copilot contract."
        ) from exc
    recommendation = LeadManagerCopilotRecommendation(
        organization_id=principal.organization_id,
        case_id=case.id,
        lead_id=case.lead_id,
        ai_run_log_id=run.id,
        generated_for_user_id=case.assigned_user_id,
        idempotency_key=idempotency_key,
        status="draft",
        priority_score=work_item.priority_score,
        priority_band=work_item.priority_band,
        model_name=run.model_name,
        output_payload=model_output.model_dump(),
        evidence_snapshot={
            "alerts": work_item.alerts,
            "qualification_gaps": work_item.qualification_gaps,
            "evidence": work_item.evidence,
            "priority_score": work_item.priority_score,
            "priority_band": work_item.priority_band,
        },
        confidence_score=model_output.confidence,
        generated_at=now,
        reviewed_at=None,
    )
    db.add(recommendation)
    db.flush()
    _audit(
        db,
        principal,
        "lead_manager.copilot_recommendation_generated",
        "lead_manager_copilot_recommendation",
        recommendation.id,
        {
            "case_id": str(case.id),
            "ai_run_log_id": str(run.id),
            "priority_score": work_item.priority_score,
            "status": "draft",
        },
    )
    db.commit()
    db.refresh(recommendation)
    return LeadManagerCopilotAnalyzeRead(
        run_id=run.id,
        run_status=run.status,
        message="Draft recommendation generated for human review.",
        recommendation=recommendation_read(recommendation),
    )


def review_recommendation(
    db: Session,
    principal: Principal,
    recommendation_id: UUID,
    payload: LeadManagerCopilotReviewRequest,
) -> LeadManagerCopilotReviewRead | None:
    recommendation = db.scalar(
        select(LeadManagerCopilotRecommendation).where(
            LeadManagerCopilotRecommendation.organization_id == principal.organization_id,
            LeadManagerCopilotRecommendation.id == recommendation_id,
        )
    )
    if recommendation is None:
        return None
    case = scoped_case(db, principal, recommendation.case_id)
    if case is None:
        raise ValueError("The recommendation points to a missing Lead Manager case.")
    ensure_case_access(principal, case)
    existing = db.scalar(
        select(LeadManagerCopilotReview).where(
            LeadManagerCopilotReview.recommendation_id == recommendation.id
        )
    )
    if existing is not None:
        return review_read(existing)
    if recommendation.status not in RECOMMENDATION_STATUSES or recommendation.status != "draft":
        raise ValueError("Only a draft recommendation can be reviewed.")
    final_output: dict[str, object] | None
    if payload.decision == "edited":
        assert payload.final_output is not None
        try:
            final_output = LeadManagerCopilotModelOutput.model_validate(
                payload.final_output
            ).model_dump()
        except ValidationError as exc:
            raise ValueError(
                "The corrected output must preserve the copilot response contract."
            ) from exc
    elif payload.decision == "accepted":
        final_output = recommendation.output_payload
    else:
        final_output = None
    now = datetime.now(UTC)
    review = LeadManagerCopilotReview(
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
        "lead_manager.copilot_recommendation_reviewed",
        "lead_manager_copilot_recommendation",
        recommendation.id,
        {
            "decision": payload.decision,
            "estimated_time_saved_seconds": payload.estimated_time_saved_seconds,
            "crm_changes_applied": False,
            "external_actions_executed": False,
        },
    )
    db.commit()
    db.refresh(review)
    return review_read(review)


def _visible_cases(db: Session, principal: Principal) -> list[LeadManagementCase]:
    from app.services.lead_manager import can_manage

    statement = select(LeadManagementCase).where(
        LeadManagementCase.organization_id == principal.organization_id
    )
    if not can_manage(principal):
        statement = statement.where(
            LeadManagementCase.assigned_user_id == principal.user_id
        )
    return list(db.scalars(statement).all())


def _visible_recommendations_statement(principal: Principal):
    from app.services.lead_manager import can_manage

    statement = select(LeadManagerCopilotRecommendation).where(
        LeadManagerCopilotRecommendation.organization_id == principal.organization_id
    )
    if not can_manage(principal):
        statement = statement.where(
            LeadManagerCopilotRecommendation.generated_for_user_id == principal.user_id
        )
    return statement


def _work_item(
    db: Session,
    case: LeadManagementCase,
    now: datetime,
) -> LeadManagerCopilotWorkItemRead:
    case_details = case_read(db, case, now)
    lead = db.get(Lead, case.lead_id)
    if lead is None:
        raise ValueError("Lead Manager Copilot case points to a missing lead.")
    conversation = db.scalar(
        select(Conversation).where(
            Conversation.organization_id == case.organization_id,
            Conversation.lead_id == case.lead_id,
        )
    )
    today_start = datetime.combine(now.date(), time.min, tzinfo=UTC)
    appointment_today = (
        db.scalar(
            select(Appointment.id).where(
                Appointment.organization_id == case.organization_id,
                Appointment.lead_id == case.lead_id,
                Appointment.scheduled_start_at >= today_start,
                Appointment.scheduled_start_at < today_start + timedelta(days=1),
                Appointment.status.in_(("scheduled", "rescheduled")),
            )
        )
        is not None
    )
    missed_reply = bool(
        conversation
        and conversation.last_inbound_at
        and (
            conversation.last_outbound_at is None
            or as_utc(conversation.last_inbound_at)
            > as_utc(conversation.last_outbound_at)
        )
    )
    qualification_gaps, recommended_questions = _qualification_gaps(
        db, case, lead
    )
    score = 10 + min(case_details.age_hours, 24)
    alerts: list[str] = []
    evidence: list[str] = [
        f"Lead stage is {lead.stage_key}.",
        f"Case status is {case.status}.",
        f"Lead age is {case_details.age_hours} hours.",
    ]
    recommended_action = "Review the lead and preserve a dated next action."
    if case_details.is_acceptance_overdue:
        score += 100
        alerts.append("Warm handoff acceptance SLA is overdue.")
        evidence.append(f"Acceptance was due {case.acceptance_due_at.isoformat()}.")
        recommended_action = "Accept and contact the warm lead immediately."
    elif case.accepted_at is None:
        score += 85
        alerts.append("Warm handoff is awaiting acceptance.")
        evidence.append(f"Acceptance is due {case.acceptance_due_at.isoformat()}.")
        recommended_action = "Review and accept the warm handoff."
    if missed_reply:
        score += 95
        alerts.append("Seller sent the latest message and needs a reply.")
        evidence.append("Last inbound activity is newer than last outbound activity.")
        recommended_action = "Review the conversation and prepare a reply."
    if case_details.is_next_action_overdue:
        score += 80
        alerts.append("The dated follow-up is overdue.")
        evidence.append(f"Next action was due {case.next_action_due_at.isoformat()}.")
        recommended_action = "Complete or reschedule the overdue follow-up."
    if case.accepted_at is not None and case.qualification_completed_at is None:
        score += 65
        alerts.append("Seller qualification is incomplete.")
        evidence.append(f"{len(qualification_gaps)} qualification fields remain open.")
        if not missed_reply:
            recommended_action = "Complete seller qualification."
    if (
        case.accepted_at is not None
        and case.qualification_completed_at is not None
        and (
            case.next_action_due_at is None
            or as_utc(case.next_action_due_at) <= now - timedelta(hours=24)
        )
    ):
        score += 75
        alerts.append("Active lead does not have a protected future action.")
        evidence.append("No future next action protects this seller relationship.")
        recommended_action = "Set a dated next action before ending the review."
    if appointment_today:
        score += 55
        alerts.append("Seller appointment is scheduled today.")
        evidence.append("An internal calendar appointment is scheduled today.")
        if score < 90:
            recommended_action = "Prepare the seller appointment brief."
    score = min(score, 300)
    return LeadManagerCopilotWorkItemRead(
        case_id=case.id,
        lead_id=case.lead_id,
        seller_name=case_details.seller_name,
        property_address=case_details.property_address,
        assigned_user_name=case_details.assigned_user_name,
        priority_score=score,
        priority_band=_priority_band(score),
        recommended_action=recommended_action,
        alerts=alerts,
        qualification_gaps=qualification_gaps,
        recommended_questions=recommended_questions,
        evidence=evidence,
        missed_reply=missed_reply,
        appointment_today=appointment_today,
        lead_url=case_details.lead_url,
    )


def _qualification_gaps(
    db: Session,
    case: LeadManagementCase,
    lead: Lead,
) -> tuple[list[str], list[str]]:
    script = get_active_script(db, case.organization_id)
    if script is None:
        return ["Approved qualification standard"], [
            "Ask a manager to approve the qualification standard."
        ]
    session = db.scalar(
        select(LeadQualificationSession)
        .where(
            LeadQualificationSession.organization_id == case.organization_id,
            LeadQualificationSession.case_id == case.id,
        )
        .order_by(LeadQualificationSession.completed_at.desc())
    )
    answers = session.answers if session else {}
    gaps: list[str] = []
    questions: list[str] = []
    for question in script.questions:
        key = str(question.get("key", ""))
        answer = answers.get(key)
        mapped_field = LEAD_FIELD_BY_QUESTION.get(key)
        lead_value = getattr(lead, mapped_field, None) if mapped_field else None
        if _has_value(answer) or _has_value(lead_value):
            continue
        gaps.append(str(question.get("label") or key))
        questions.append(str(question.get("prompt") or question.get("label") or key))
    return gaps, questions


def _analysis_idempotency_key(
    db: Session,
    case: LeadManagementCase,
    work_item: LeadManagerCopilotWorkItemRead,
) -> str:
    conversation = db.scalar(
        select(Conversation).where(
            Conversation.organization_id == case.organization_id,
            Conversation.lead_id == case.lead_id,
        )
    )
    script: LeadQualificationScriptVersion | None = get_active_script(
        db, case.organization_id
    )
    fingerprint = {
        "case_id": str(case.id),
        "case_updated_at": as_utc(case.updated_at).isoformat(),
        "conversation_updated_at": (
            as_utc(conversation.updated_at).isoformat() if conversation else None
        ),
        "script_version": script.version_number if script else None,
        "priority_score": work_item.priority_score,
    }
    digest = hashlib.sha256(
        json.dumps(fingerprint, sort_keys=True).encode()
    ).hexdigest()[:24]
    return f"lead-manager-copilot:{case.id}:{digest}"


def _copilot_metrics(
    db: Session,
    principal: Principal,
    cases: list[LeadManagementCase],
    recommendations: list[LeadManagerCopilotRecommendation],
    now: datetime,
) -> LeadManagerCopilotMetrics:
    since = now - timedelta(days=30)
    recent_recommendations = [
        item for item in recommendations if as_utc(item.generated_at) >= since
    ]
    recommendation_ids = [item.id for item in recent_recommendations]
    reviews = (
        list(
            db.scalars(
                select(LeadManagerCopilotReview).where(
                    LeadManagerCopilotReview.organization_id
                    == principal.organization_id,
                    LeadManagerCopilotReview.recommendation_id.in_(
                        recommendation_ids
                    ),
                )
            ).all()
        )
        if recommendation_ids
        else []
    )
    reviewed_count = len(reviews)
    accepted_count = sum(item.decision == "accepted" for item in reviews)
    edited_count = sum(item.decision == "edited" for item in reviews)
    rejected_count = sum(item.decision == "rejected" for item in reviews)
    run_ids = [
        item.ai_run_log_id
        for item in recent_recommendations
        if item.ai_run_log_id is not None
    ]
    total_cost = (
        int(
            db.scalar(
                select(func.coalesce(func.sum(AiRunLog.cost_microusd), 0)).where(
                    AiRunLog.organization_id == principal.organization_id,
                    AiRunLog.id.in_(run_ids),
                )
            )
            or 0
        )
        if run_ids
        else 0
    )
    acceptance_minutes = [
        max(
            0,
            round(
                (
                    as_utc(case.accepted_at) - as_utc(case.created_at)
                ).total_seconds()
                / 60
            ),
        )
        for case in cases
        if case.accepted_at is not None and as_utc(case.created_at) >= since
    ]
    lead_ids = [case.lead_id for case in cases]
    appointments_set = (
        int(
            db.scalar(
                select(func.count(Appointment.id)).where(
                    Appointment.organization_id == principal.organization_id,
                    Appointment.lead_id.in_(lead_ids),
                    Appointment.created_at >= since,
                )
            )
            or 0
        )
        if lead_ids
        else 0
    )
    return LeadManagerCopilotMetrics(
        generated_count=len(recent_recommendations),
        reviewed_count=reviewed_count,
        accepted_count=accepted_count,
        edited_count=edited_count,
        rejected_count=rejected_count,
        acceptance_rate_basis_points=(
            round((accepted_count + edited_count) / reviewed_count * 10_000)
            if reviewed_count
            else 0
        ),
        correction_rate_basis_points=(
            round(edited_count / reviewed_count * 10_000) if reviewed_count else 0
        ),
        estimated_time_saved_minutes=round(
            sum(item.estimated_time_saved_seconds for item in reviews) / 60
        ),
        total_cost_microusd=total_cost,
        average_response_minutes=(
            round(sum(acceptance_minutes) / len(acceptance_minutes))
            if acceptance_minutes
            else None
        ),
        appointments_set=appointments_set,
    )


def recommendation_read(
    item: LeadManagerCopilotRecommendation,
) -> LeadManagerCopilotRecommendationRead:
    return LeadManagerCopilotRecommendationRead(
        id=item.id,
        case_id=item.case_id,
        lead_id=item.lead_id,
        ai_run_log_id=item.ai_run_log_id,
        status=item.status,
        priority_score=item.priority_score,
        priority_band=item.priority_band,
        model_name=item.model_name,
        output_payload=item.output_payload,
        evidence_snapshot=item.evidence_snapshot,
        confidence_score=item.confidence_score,
        generated_at=item.generated_at,
        reviewed_at=item.reviewed_at,
    )


def review_read(item: LeadManagerCopilotReview) -> LeadManagerCopilotReviewRead:
    return LeadManagerCopilotReviewRead(
        id=item.id,
        recommendation_id=item.recommendation_id,
        reviewed_by_user_id=item.reviewed_by_user_id,
        decision=item.decision,
        final_output=item.final_output,
        notes=item.notes,
        estimated_time_saved_seconds=item.estimated_time_saved_seconds,
        reviewed_at=item.reviewed_at,
    )


def _priority_band(score: int) -> str:
    if score >= 100:
        return "urgent"
    if score >= 80:
        return "high"
    if score >= 50:
        return "normal"
    return "low"


def _has_value(value: object) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    return True


def _audit(
    db: Session,
    principal: Principal,
    action: str,
    entity_type: str,
    entity_id: UUID,
    value: dict[str, object],
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
            reason="Lead Manager Copilot draft-only pilot",
        )
    )
