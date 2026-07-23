import hashlib
import json
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from uuid import UUID

from pydantic import ValidationError
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.core.auth import Principal
from app.domain.rbac import PermissionKeys
from app.models.foundation import (
    AiAgentDefinition,
    AuditEvent,
    CallRecording,
    CallTranscript,
    Campaign,
    Prospect,
    ProspectCallingBatch,
    ProspectCallingBatchEntry,
    ProspectHandoff,
    ProspectingAttempt,
    ProspectingCallQualityReview,
    ProspectingCopilotRecommendation,
    ProspectingCopilotReview,
    Role,
    RoleAssignment,
    User,
)
from app.schemas.ai import AiRuntimeExecuteCreate
from app.schemas.prospecting import (
    ProspectingCallQualityAnalyzeRead,
    ProspectingCallQualityModelOutput,
    ProspectingCallQualityRead,
    ProspectingCallQualityReviewRequest,
    ProspectingCopilotAnalyzeRead,
    ProspectingCopilotAnalyzeRequest,
    ProspectingCopilotMetrics,
    ProspectingCopilotModelOutput,
    ProspectingCopilotOverview,
    ProspectingCopilotRecommendationRead,
    ProspectingCopilotReviewRead,
    ProspectingCopilotReviewRequest,
    ProspectingCopilotWorkItemRead,
)
from app.services.acquisition_operations import create_notification
from app.services.ai_runtime import execute_runtime, get_runtime_overview

MANAGER_ROLE_KEYS = {
    "owner",
    "founder_operator",
    "ceo",
    "administrator",
    "acquisition_manager",
}
WARM_OUTCOMES = {"interested", "appointment_set"}


def can_manage(principal: Principal) -> bool:
    return PermissionKeys.MANAGE_ACQUISITION_OPERATIONS in principal.permission_keys


def get_copilot_overview(
    db: Session,
    principal: Principal,
) -> ProspectingCopilotOverview:
    now = datetime.now(UTC)
    entries = _visible_due_entries(db, principal, now)
    work_items = sorted(
        (_work_item(db, entry, now) for entry in entries),
        key=lambda item: (-item.priority_score, item.seller_name.lower()),
    )
    recommendations = list(
        db.scalars(
            _recommendation_statement(principal).order_by(
                ProspectingCopilotRecommendation.generated_at.desc()
            )
        ).all()
    )
    quality_reviews = list(
        db.scalars(
            _quality_statement(principal).order_by(ProspectingCallQualityReview.created_at.desc())
        ).all()
    )
    runtime = get_runtime_overview(db, principal)
    capability_statuses = {item.capability_key: item.status for item in runtime.capabilities}
    return ProspectingCopilotOverview(
        pilot_mode="draft_only",
        runtime_status=runtime.status,
        priority_capability_status=capability_statuses.get(
            "prospecting.prioritize", "not_installed"
        ),
        quality_capability_status=capability_statuses.get("call.quality_coach", "not_installed"),
        external_actions_blocked=(
            runtime.policy is None or not runtime.policy.external_actions_enabled
        ),
        work_items=work_items,
        recommendations=[recommendation_read(item) for item in recommendations[:50]],
        quality_queue=[quality_read(db, item) for item in quality_reviews[:100]],
        metrics=_metrics(db, principal, recommendations, quality_reviews, now),
    )


def analyze_entry(
    db: Session,
    principal: Principal,
    entry_id: UUID,
    payload: ProspectingCopilotAnalyzeRequest,
) -> ProspectingCopilotAnalyzeRead | None:
    entry = _scoped_entry(db, principal, entry_id)
    if entry is None:
        return None
    prospect = db.get(Prospect, entry.prospect_id)
    if prospect is None:
        raise ValueError("The assigned prospect is unavailable.")
    if prospect.call_eligibility != "eligible" or prospect.suppression_status == "suppressed":
        raise ValueError("Only eligible, unsuppressed assigned prospects may be analyzed.")
    now = datetime.now(UTC)
    work_item = _work_item(db, entry, now)
    agent = db.scalar(
        select(AiAgentDefinition).where(
            AiAgentDefinition.organization_id == principal.organization_id,
            AiAgentDefinition.key == "prospecting_intelligence",
        )
    )
    if agent is None:
        raise ValueError("Install the governed AI agent portfolio first.")
    idempotency_key = payload.idempotency_key or _entry_idempotency_key(entry, prospect, work_item)
    existing = db.scalar(
        select(ProspectingCopilotRecommendation).where(
            ProspectingCopilotRecommendation.organization_id == principal.organization_id,
            ProspectingCopilotRecommendation.idempotency_key == idempotency_key,
        )
    )
    if existing is not None:
        if existing.ai_run_log_id is None:
            raise ValueError("The existing recommendation has no governed AI trace.")
        return ProspectingCopilotAnalyzeRead(
            run_id=existing.ai_run_log_id,
            run_status="needs_review",
            message="The current pre-call brief is already available.",
            recommendation=recommendation_read(existing),
        )
    run = execute_runtime(
        db,
        principal,
        AiRuntimeExecuteCreate(
            agent_definition_id=agent.id,
            capability_key="prospecting.prioritize",
            idempotency_key=idempotency_key,
            input_payload={
                "pilot_mode": "draft_only",
                "deterministic_priority": work_item.priority_score,
                "recommended_action": work_item.recommended_action,
                "restrictions": [
                    "Do not change eligibility or assignment.",
                    "Do not place a call or send a message.",
                    "Do not invent property or seller facts.",
                    "Do not select a final disposition.",
                    "Return preparation guidance for human review only.",
                ],
            },
            prospect_id=prospect.id,
            prospecting_entry_id=entry.id,
        ),
    )
    if run.status not in {"needs_review", "completed"} or not run.output_summary:
        return ProspectingCopilotAnalyzeRead(
            run_id=run.id,
            run_status=run.status,
            message=run.error_message or "The governed runtime did not produce a brief.",
            recommendation=None,
        )
    try:
        output = ProspectingCopilotModelOutput.model_validate(json.loads(run.output_summary))
    except (json.JSONDecodeError, ValidationError) as exc:
        raise ValueError(
            "The model response did not match the Prospecting Copilot contract."
        ) from exc
    recommendation = ProspectingCopilotRecommendation(
        organization_id=principal.organization_id,
        batch_entry_id=entry.id,
        prospect_id=prospect.id,
        generated_for_user_id=entry.assigned_user_id,
        ai_run_log_id=run.id,
        idempotency_key=idempotency_key,
        status="draft",
        priority_score=work_item.priority_score,
        priority_band=work_item.priority_band,
        output_payload=output.model_dump(),
        evidence_snapshot={
            "priority_reasons": work_item.reasons,
            "eligibility_evidence": work_item.eligibility_evidence,
            "data_quality_warnings": work_item.data_quality_warnings,
        },
        confidence_score=output.confidence,
        generated_at=now,
        reviewed_at=None,
    )
    db.add(recommendation)
    db.flush()
    _audit(
        db,
        principal,
        "prospecting.copilot_brief_generated",
        "prospecting_copilot_recommendation",
        recommendation.id,
        {"entry_id": str(entry.id), "ai_run_id": str(run.id)},
    )
    db.commit()
    db.refresh(recommendation)
    return ProspectingCopilotAnalyzeRead(
        run_id=run.id,
        run_status=run.status,
        message="Pre-call brief generated for human review.",
        recommendation=recommendation_read(recommendation),
    )


def review_recommendation(
    db: Session,
    principal: Principal,
    recommendation_id: UUID,
    payload: ProspectingCopilotReviewRequest,
) -> ProspectingCopilotReviewRead | None:
    recommendation = db.scalar(
        select(ProspectingCopilotRecommendation).where(
            ProspectingCopilotRecommendation.organization_id == principal.organization_id,
            ProspectingCopilotRecommendation.id == recommendation_id,
        )
    )
    if recommendation is None:
        return None
    if _scoped_entry(db, principal, recommendation.batch_entry_id) is None:
        raise PermissionError("The recommendation is outside this caller's assignment.")
    existing = db.scalar(
        select(ProspectingCopilotReview).where(
            ProspectingCopilotReview.recommendation_id == recommendation.id
        )
    )
    if existing is not None:
        return copilot_review_read(existing)
    if recommendation.status != "draft":
        raise ValueError("Only a draft pre-call brief can be reviewed.")
    final_output: dict[str, object] | None
    if payload.decision == "edited":
        assert payload.final_output is not None
        try:
            final_output = ProspectingCopilotModelOutput.model_validate(
                payload.final_output
            ).model_dump()
        except ValidationError as exc:
            raise ValueError(
                "Corrected output must preserve the Prospecting Copilot contract."
            ) from exc
    elif payload.decision == "accepted":
        final_output = recommendation.output_payload
    else:
        final_output = None
    now = datetime.now(UTC)
    review = ProspectingCopilotReview(
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
        "prospecting.copilot_brief_reviewed",
        "prospecting_copilot_recommendation",
        recommendation.id,
        {
            "decision": payload.decision,
            "external_actions_executed": False,
            "queue_changes_applied": False,
        },
    )
    db.commit()
    db.refresh(review)
    return copilot_review_read(review)


def ensure_call_quality_review(
    db: Session,
    principal: Principal,
    attempt: ProspectingAttempt,
    reported_flags: Sequence[str],
) -> ProspectingCallQualityReview:
    existing = db.scalar(
        select(ProspectingCallQualityReview).where(
            ProspectingCallQualityReview.attempt_id == attempt.id
        )
    )
    flags = sorted(
        {
            *(existing.compliance_flags if existing else []),
            *reported_flags,
            *(["do_not_call_request"] if attempt.outcome == "do_not_call" else []),
        }
    )
    transcript = _approved_transcript(db, attempt)
    scores = _deterministic_scores(db, attempt)
    status = "escalated" if flags else "ready_for_analysis" if transcript else "awaiting_transcript"
    if existing is None:
        review = ProspectingCallQualityReview(
            organization_id=attempt.organization_id,
            attempt_id=attempt.id,
            caller_user_id=attempt.caller_user_id,
            call_record_id=attempt.call_record_id,
            transcript_id=transcript.id if transcript else None,
            ai_run_log_id=None,
            status=status,
            deterministic_scores=scores,
            ai_output=None,
            final_output=None,
            compliance_flags=flags,
            escalation_required=bool(flags),
            reviewed_by_user_id=None,
            review_notes=None,
            reviewed_at=None,
        )
        db.add(review)
        db.flush()
    else:
        review = existing
        review.call_record_id = attempt.call_record_id
        review.transcript_id = transcript.id if transcript else None
        review.deterministic_scores = scores
        review.compliance_flags = flags
        review.escalation_required = bool(flags)
        if review.status not in {"approved", "corrected", "rejected"}:
            review.status = status
    if flags:
        _notify_compliance_escalation(db, principal, attempt, review, flags)
        _audit(
            db,
            principal,
            "prospecting.call_compliance_escalated",
            "prospecting_call_quality_review",
            review.id,
            {"attempt_id": str(attempt.id), "flags": flags},
        )
    return review


def analyze_call_quality(
    db: Session,
    principal: Principal,
    attempt_id: UUID,
) -> ProspectingCallQualityAnalyzeRead | None:
    attempt = db.scalar(
        select(ProspectingAttempt).where(
            ProspectingAttempt.organization_id == principal.organization_id,
            ProspectingAttempt.id == attempt_id,
        )
    )
    if attempt is None:
        return None
    if not can_manage(principal) and attempt.caller_user_id != principal.user_id:
        raise PermissionError("The call is outside this caller's assignment.")
    review = ensure_call_quality_review(db, principal, attempt, [])
    transcript = _approved_transcript(db, attempt)
    if transcript is None:
        raise ValueError("Call-quality coaching requires an approved, consented transcript.")
    agent = db.scalar(
        select(AiAgentDefinition).where(
            AiAgentDefinition.organization_id == principal.organization_id,
            AiAgentDefinition.key == "call_intelligence",
        )
    )
    if agent is None:
        raise ValueError("Install the governed AI agent portfolio first.")
    idempotency_key = (
        f"prospecting-call-quality:{attempt.id}:"
        f"{hashlib.sha256(str(transcript.updated_at).encode()).hexdigest()[:24]}"
    )
    run = execute_runtime(
        db,
        principal,
        AiRuntimeExecuteCreate(
            agent_definition_id=agent.id,
            capability_key="call.quality_coach",
            idempotency_key=idempotency_key,
            input_payload={
                "pilot_mode": "draft_only",
                "restrictions": [
                    "Do not change the human disposition or handoff facts.",
                    "Do not publish coaching.",
                    "Use transcript evidence timestamps for every material conclusion.",
                    "Escalate stop requests, complaints, unclear identity, and policy uncertainty.",
                ],
            },
            prospecting_attempt_id=attempt.id,
        ),
    )
    if run.status not in {"needs_review", "completed"} or not run.output_summary:
        return ProspectingCallQualityAnalyzeRead(
            run_id=run.id,
            run_status=run.status,
            message=run.error_message or "The governed runtime did not produce coaching.",
            quality_review=quality_read(db, review),
        )
    try:
        output = ProspectingCallQualityModelOutput.model_validate(json.loads(run.output_summary))
    except (json.JSONDecodeError, ValidationError) as exc:
        raise ValueError("The model response did not match the call-quality contract.") from exc
    review.ai_run_log_id = run.id
    review.transcript_id = transcript.id
    review.ai_output = output.model_dump()
    review.status = "needs_review"
    model_flags = sorted({*review.compliance_flags, *output.compliance_flags})
    review.compliance_flags = model_flags
    review.escalation_required = bool(model_flags)
    if model_flags:
        _notify_compliance_escalation(db, principal, attempt, review, model_flags)
    _audit(
        db,
        principal,
        "prospecting.call_quality_generated",
        "prospecting_call_quality_review",
        review.id,
        {"attempt_id": str(attempt.id), "ai_run_id": str(run.id)},
    )
    db.commit()
    db.refresh(review)
    return ProspectingCallQualityAnalyzeRead(
        run_id=run.id,
        run_status=run.status,
        message="Call-quality coaching generated for manager review.",
        quality_review=quality_read(db, review),
    )


def review_call_quality(
    db: Session,
    principal: Principal,
    attempt_id: UUID,
    payload: ProspectingCallQualityReviewRequest,
) -> ProspectingCallQualityRead | None:
    review = db.scalar(
        select(ProspectingCallQualityReview)
        .join(
            ProspectingAttempt,
            ProspectingAttempt.id == ProspectingCallQualityReview.attempt_id,
        )
        .where(
            ProspectingCallQualityReview.organization_id == principal.organization_id,
            ProspectingAttempt.id == attempt_id,
        )
    )
    if review is None:
        return None
    if review.status != "needs_review":
        raise ValueError("Only generated coaching awaiting review can be decided.")
    if review.ai_output is None:
        raise ValueError("No generated coaching is available.")
    final_output: dict[str, object] | None
    if payload.decision == "corrected":
        assert payload.final_output is not None
        try:
            final_output = ProspectingCallQualityModelOutput.model_validate(
                payload.final_output
            ).model_dump()
        except ValidationError as exc:
            raise ValueError("Corrected coaching must preserve the call-quality contract.") from exc
    elif payload.decision == "approved":
        final_output = review.ai_output
    else:
        final_output = None
    review.status = payload.decision
    review.final_output = final_output
    review.review_notes = payload.notes
    review.reviewed_by_user_id = principal.user_id
    review.reviewed_at = datetime.now(UTC)
    _audit(
        db,
        principal,
        "prospecting.call_quality_reviewed",
        "prospecting_call_quality_review",
        review.id,
        {
            "decision": payload.decision,
            "human_disposition_changed": False,
            "coaching_published": False,
        },
    )
    db.commit()
    db.refresh(review)
    return quality_read(db, review)


def _visible_due_entries(
    db: Session,
    principal: Principal,
    now: datetime,
) -> list[ProspectCallingBatchEntry]:
    statement = (
        select(ProspectCallingBatchEntry)
        .join(Prospect, Prospect.id == ProspectCallingBatchEntry.prospect_id)
        .where(
            ProspectCallingBatchEntry.organization_id == principal.organization_id,
            ProspectCallingBatchEntry.status.in_(
                ("queued", "ready", "needs_correction", "in_progress")
            ),
            Prospect.call_eligibility == "eligible",
            Prospect.suppression_status != "suppressed",
            or_(
                ProspectCallingBatchEntry.next_attempt_at.is_(None),
                ProspectCallingBatchEntry.next_attempt_at <= now,
            ),
        )
    )
    if not can_manage(principal):
        statement = statement.where(ProspectCallingBatchEntry.assigned_user_id == principal.user_id)
    return list(db.scalars(statement).all())


def _scoped_entry(
    db: Session,
    principal: Principal,
    entry_id: UUID,
) -> ProspectCallingBatchEntry | None:
    statement = select(ProspectCallingBatchEntry).where(
        ProspectCallingBatchEntry.organization_id == principal.organization_id,
        ProspectCallingBatchEntry.id == entry_id,
    )
    if not can_manage(principal):
        statement = statement.where(ProspectCallingBatchEntry.assigned_user_id == principal.user_id)
    return db.scalar(statement)


def _work_item(
    db: Session,
    entry: ProspectCallingBatchEntry,
    now: datetime,
) -> ProspectingCopilotWorkItemRead:
    prospect = db.get(Prospect, entry.prospect_id)
    batch = db.get(ProspectCallingBatch, entry.prospect_calling_batch_id)
    campaign = db.get(Campaign, batch.campaign_id) if batch else None
    if prospect is None:
        raise ValueError("Calling entry points to a missing prospect.")
    score = 20
    reasons: list[str] = []
    warnings: list[str] = []
    callback_due = bool(entry.next_attempt_at and entry.next_attempt_at <= now)
    correction_required = entry.status == "needs_correction"
    if correction_required:
        score += 120
        reasons.append("Acquisitions returned this handoff for correction.")
        action = "Resolve the handoff correction before starting new records."
    elif callback_due:
        score += 100
        reasons.append("The seller-requested callback is due.")
        action = "Complete the promised callback now."
    elif entry.status == "in_progress":
        score += 90
        reasons.append("This record is locked to an active attempt.")
        action = "Finish and save the active call outcome."
    elif entry.attempt_count == 0:
        score += 45
        reasons.append("This eligible record has not been attempted.")
        action = "Review the brief and begin the first attempt."
    else:
        score += max(10, 40 - entry.attempt_count * 5)
        reasons.append(f"This record has {entry.attempt_count} prior attempts.")
        action = "Review attempt history before the next outreach."
    if prospect.phone_validation_status not in {"valid", "verified"}:
        warnings.append(f"Phone status is {prospect.phone_validation_status.replace('_', ' ')}.")
    if prospect.address_validation_status not in {"valid", "verified"}:
        warnings.append(
            f"Address status is {prospect.address_validation_status.replace('_', ' ')}."
        )
    if not all((prospect.street_address, prospect.city, prospect.state_code, prospect.postal_code)):
        warnings.append("Property address is incomplete.")
    evidence = [
        f"Call eligibility is {prospect.call_eligibility}.",
        f"Suppression status is {prospect.suppression_status}.",
        (
            f"Suppression reviewed {prospect.suppression_checked_at.isoformat()}."
            if prospect.suppression_checked_at
            else "Suppression review timestamp is unavailable."
        ),
        f"Assigned queue status is {entry.status}.",
    ]
    return ProspectingCopilotWorkItemRead(
        entry_id=entry.id,
        prospect_id=prospect.id,
        seller_name=prospect.legal_name,
        property_address=_property_address(prospect),
        campaign_name=campaign.name if campaign else "Unknown campaign",
        priority_score=min(score, 300),
        priority_band=_priority_band(score),
        recommended_action=action,
        reasons=reasons,
        data_quality_warnings=warnings,
        eligibility_evidence=evidence,
        callback_due=callback_due,
        correction_required=correction_required,
    )


def _entry_idempotency_key(
    entry: ProspectCallingBatchEntry,
    prospect: Prospect,
    work_item: ProspectingCopilotWorkItemRead,
) -> str:
    fingerprint = {
        "entry_updated_at": entry.updated_at.isoformat(),
        "prospect_updated_at": prospect.updated_at.isoformat(),
        "priority_score": work_item.priority_score,
    }
    digest = hashlib.sha256(json.dumps(fingerprint, sort_keys=True).encode()).hexdigest()[:24]
    return f"prospecting-copilot:{entry.id}:{digest}"


def _approved_transcript(
    db: Session,
    attempt: ProspectingAttempt,
) -> CallTranscript | None:
    if attempt.call_record_id is None:
        return None
    recording = db.scalar(
        select(CallRecording).where(
            CallRecording.organization_id == attempt.organization_id,
            CallRecording.call_record_id == attempt.call_record_id,
            CallRecording.deleted_at.is_(None),
            CallRecording.consent_status == "disclosed",
        )
    )
    if recording is None:
        return None
    return db.scalar(
        select(CallTranscript)
        .where(
            CallTranscript.organization_id == attempt.organization_id,
            CallTranscript.recording_id == recording.id,
            CallTranscript.status == "approved",
        )
        .order_by(CallTranscript.approved_at.desc())
    )


def _deterministic_scores(
    db: Session,
    attempt: ProspectingAttempt,
) -> dict[str, int | None]:
    handoff = db.scalar(
        select(ProspectHandoff).where(
            ProspectHandoff.organization_id == attempt.organization_id,
            ProspectHandoff.attempt_id == attempt.id,
        )
    )
    qualification_score = (
        round(attempt.quality_score_basis_points / 100)
        if attempt.quality_score_basis_points is not None
        else None
    )
    return {
        "script_adherence_score": None,
        "qualification_completeness_score": qualification_score,
        "objection_handling_score": None,
        "data_quality_score": 0 if attempt.outcome == "wrong_number" else 100,
        "handoff_quality_score": (
            100
            if handoff and handoff.status == "accepted"
            else 50
            if handoff and handoff.status == "needs_correction"
            else None
        ),
    }


def recommendation_read(
    item: ProspectingCopilotRecommendation,
) -> ProspectingCopilotRecommendationRead:
    return ProspectingCopilotRecommendationRead(
        id=item.id,
        entry_id=item.batch_entry_id,
        prospect_id=item.prospect_id,
        ai_run_log_id=item.ai_run_log_id,
        status=item.status,
        priority_score=item.priority_score,
        priority_band=item.priority_band,
        output_payload=ProspectingCopilotModelOutput.model_validate(item.output_payload),
        confidence_score=item.confidence_score,
        generated_at=item.generated_at,
        reviewed_at=item.reviewed_at,
    )


def copilot_review_read(
    item: ProspectingCopilotReview,
) -> ProspectingCopilotReviewRead:
    return ProspectingCopilotReviewRead(
        id=item.id,
        recommendation_id=item.recommendation_id,
        decision=item.decision,
        final_output=item.final_output,
        notes=item.notes,
        estimated_time_saved_seconds=item.estimated_time_saved_seconds,
        reviewed_at=item.reviewed_at,
    )


def quality_read(
    db: Session,
    item: ProspectingCallQualityReview,
) -> ProspectingCallQualityRead:
    attempt = db.get(ProspectingAttempt, item.attempt_id)
    prospect = db.get(Prospect, attempt.prospect_id) if attempt else None
    caller = db.get(User, item.caller_user_id)
    return ProspectingCallQualityRead(
        id=item.id,
        attempt_id=item.attempt_id,
        caller_user_id=item.caller_user_id,
        caller_name=caller.display_name if caller else "Unknown caller",
        seller_name=prospect.legal_name if prospect else "Unknown seller",
        outcome=attempt.outcome if attempt else None,
        status=item.status,
        deterministic_scores=item.deterministic_scores,
        ai_output=(
            ProspectingCallQualityModelOutput.model_validate(item.ai_output)
            if item.ai_output
            else None
        ),
        final_output=(
            ProspectingCallQualityModelOutput.model_validate(item.final_output)
            if item.final_output
            else None
        ),
        compliance_flags=item.compliance_flags,
        escalation_required=item.escalation_required,
        transcript_available=item.transcript_id is not None,
        reviewed_at=item.reviewed_at,
        review_notes=item.review_notes,
        completed_at=attempt.completed_at if attempt else None,
    )


def _recommendation_statement(principal: Principal):
    statement = select(ProspectingCopilotRecommendation).where(
        ProspectingCopilotRecommendation.organization_id == principal.organization_id
    )
    if not can_manage(principal):
        statement = statement.where(
            ProspectingCopilotRecommendation.generated_for_user_id == principal.user_id
        )
    return statement


def _quality_statement(principal: Principal):
    statement = select(ProspectingCallQualityReview).where(
        ProspectingCallQualityReview.organization_id == principal.organization_id
    )
    if not can_manage(principal):
        statement = statement.where(
            ProspectingCallQualityReview.caller_user_id == principal.user_id
        )
    return statement


def _metrics(
    db: Session,
    principal: Principal,
    recommendations: list[ProspectingCopilotRecommendation],
    quality_reviews: list[ProspectingCallQualityReview],
    now: datetime,
) -> ProspectingCopilotMetrics:
    since = now - timedelta(days=30)
    recent_recommendations = [
        item for item in recommendations if _as_utc(item.generated_at) >= since
    ]
    ids = [item.id for item in recent_recommendations]
    reviews = (
        list(
            db.scalars(
                select(ProspectingCopilotReview).where(
                    ProspectingCopilotReview.organization_id == principal.organization_id,
                    ProspectingCopilotReview.recommendation_id.in_(ids),
                )
            ).all()
        )
        if ids
        else []
    )
    accepted = sum(item.decision in {"accepted", "edited"} for item in reviews)
    corrected = sum(item.decision == "edited" for item in reviews)
    recent_quality = [item for item in quality_reviews if _as_utc(item.created_at) >= since]
    return ProspectingCopilotMetrics(
        generated_briefs=len(recent_recommendations),
        reviewed_briefs=len(reviews),
        accepted_or_corrected_rate_basis_points=(
            round(accepted / len(reviews) * 10_000) if reviews else 0
        ),
        correction_rate_basis_points=(round(corrected / len(reviews) * 10_000) if reviews else 0),
        estimated_time_saved_minutes=round(
            sum(item.estimated_time_saved_seconds for item in reviews) / 60
        ),
        quality_reviews=len(recent_quality),
        transcript_ready=sum(item.transcript_id is not None for item in recent_quality),
        escalations=sum(item.escalation_required for item in recent_quality),
        coaching_approved=sum(item.status == "approved" for item in recent_quality),
        coaching_corrected=sum(item.status == "corrected" for item in recent_quality),
    )


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _notify_compliance_escalation(
    db: Session,
    principal: Principal,
    attempt: ProspectingAttempt,
    review: ProspectingCallQualityReview,
    flags: list[str],
) -> None:
    recipients = list(
        db.scalars(
            select(RoleAssignment.user_id)
            .join(Role, Role.id == RoleAssignment.role_id)
            .where(
                RoleAssignment.organization_id == principal.organization_id,
                Role.key.in_(MANAGER_ROLE_KEYS),
            )
            .distinct()
        ).all()
    )
    for recipient_id in recipients:
        create_notification(
            db,
            organization_id=principal.organization_id,
            recipient_user_id=recipient_id,
            notification_type="prospecting_compliance_escalation",
            title="Prospecting call needs compliance review",
            body="A caller recorded: " + ", ".join(flag.replace("_", " ") for flag in flags),
            entity_type="prospecting_call_quality_review",
            entity_id=review.id,
            action_url="/os/prospecting",
            dedupe_key=f"prospecting-compliance:{review.id}:{recipient_id}",
        )


def _priority_band(score: int) -> str:
    if score >= 120:
        return "urgent"
    if score >= 90:
        return "high"
    if score >= 50:
        return "normal"
    return "low"


def _property_address(prospect: Prospect) -> str | None:
    parts = [
        prospect.street_address,
        prospect.city,
        prospect.state_code,
        prospect.postal_code,
    ]
    value = ", ".join(part for part in parts if part)
    return value or None


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
            reason="Prospecting Copilot draft-only pilot",
        )
    )
