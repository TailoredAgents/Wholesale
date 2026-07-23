import hashlib
import json
from datetime import UTC, datetime, timedelta
from typing import TypedDict
from uuid import UUID

from pydantic import ValidationError
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.auth import Principal
from app.domain.rbac import PermissionKeys
from app.models.foundation import (
    AcquisitionsCopilotRecommendation,
    AcquisitionsCopilotReview,
    AiAgentDefinition,
    Appointment,
    ApprovalRequest,
    AuditEvent,
    CallRecord,
    CallRecording,
    CallTranscript,
    CommunicationRecord,
    FieldInspection,
    FieldMeetingBrief,
    FieldNegotiationSession,
    Lead,
    LeadQualificationSession,
    OfferNegotiationPlan,
    UnderwritingMarketAnalysis,
    UnderwritingVersion,
)
from app.schemas.ai import AiRuntimeExecuteCreate
from app.schemas.field_operations import (
    AcquisitionsCopilotAnalyzeRead,
    AcquisitionsCopilotAnalyzeRequest,
    AcquisitionsCopilotMetrics,
    AcquisitionsCopilotOverview,
    AcquisitionsCopilotRecommendationRead,
    AcquisitionsCopilotReviewRead,
    AcquisitionsCopilotReviewRequest,
    AcquisitionsFollowUpOutput,
    AcquisitionsPreparationOutput,
)
from app.services.ai_runtime import execute_runtime, get_runtime_overview

CAPABILITY_BY_TYPE = {
    "preparation": ("appointment_preparation", "appointment.brief"),
    "follow_up": ("negotiation_coach", "negotiation.coach"),
}


class AppointmentFacts(TypedDict):
    brief: FieldMeetingBrief | None
    qualification: LeadQualificationSession | None
    underwriting: UnderwritingVersion | None
    market_analysis: UnderwritingMarketAnalysis | None
    approved_plan: OfferNegotiationPlan | None
    inspection: FieldInspection | None
    negotiation: FieldNegotiationSession | None
    readiness_score: int
    readiness_band: str
    readiness_gaps: list[str]
    evidence_available: list[str]
    authority_status: str
    approved_ceiling_cents: int | None


def get_acquisitions_copilot_overview(
    db: Session,
    principal: Principal,
    appointment: Appointment,
) -> AcquisitionsCopilotOverview:
    facts = _appointment_facts(db, principal, appointment)
    runtime = get_runtime_overview(db, principal)
    statuses = {
        item.capability_key: item.status for item in runtime.capabilities
    }
    recommendations = list(
        db.scalars(
            select(AcquisitionsCopilotRecommendation)
            .where(
                AcquisitionsCopilotRecommendation.organization_id
                == principal.organization_id,
                AcquisitionsCopilotRecommendation.appointment_id == appointment.id,
            )
            .order_by(AcquisitionsCopilotRecommendation.generated_at.desc())
        ).all()
    )
    return AcquisitionsCopilotOverview(
        pilot_mode="draft_only",
        runtime_status=runtime.status,
        preparation_capability_status=statuses.get(
            "appointment.brief", "not_installed"
        ),
        follow_up_capability_status=statuses.get(
            "negotiation.coach", "not_installed"
        ),
        external_actions_blocked=(
            runtime.policy is None or not runtime.policy.external_actions_enabled
        ),
        readiness_score=facts["readiness_score"],
        readiness_band=facts["readiness_band"],
        readiness_gaps=facts["readiness_gaps"],
        evidence_available=facts["evidence_available"],
        authority_status=facts["authority_status"],
        approved_ceiling_cents=facts["approved_ceiling_cents"],
        recommendations=[recommendation_read(item) for item in recommendations],
        metrics=_metrics(db, principal),
    )


def analyze_appointment(
    db: Session,
    principal: Principal,
    appointment_id: UUID,
    payload: AcquisitionsCopilotAnalyzeRequest,
) -> AcquisitionsCopilotAnalyzeRead | None:
    appointment = _scoped_appointment(db, principal, appointment_id)
    if appointment is None:
        return None
    facts = _appointment_facts(db, principal, appointment)
    if facts["brief"] is None:
        raise ValueError("Generate the deterministic meeting brief before using the copilot.")
    if payload.recommendation_type == "follow_up":
        negotiation = facts["negotiation"]
        if negotiation is None or negotiation.outcome == "pending":
            raise ValueError(
                "Record the human meeting outcome before generating follow-up coaching."
            )

    agent_key, capability_key = CAPABILITY_BY_TYPE[payload.recommendation_type]
    agent = db.scalar(
        select(AiAgentDefinition).where(
            AiAgentDefinition.organization_id == principal.organization_id,
            AiAgentDefinition.key == agent_key,
        )
    )
    if agent is None:
        raise ValueError("Install the governed AI agent portfolio first.")
    idempotency_key = payload.idempotency_key or _idempotency_key(
        appointment, payload.recommendation_type, facts
    )
    existing = db.scalar(
        select(AcquisitionsCopilotRecommendation).where(
            AcquisitionsCopilotRecommendation.organization_id
            == principal.organization_id,
            AcquisitionsCopilotRecommendation.idempotency_key == idempotency_key,
        )
    )
    if existing is not None:
        if existing.ai_run_log_id is None:
            raise ValueError("The existing recommendation has no governed AI trace.")
        return AcquisitionsCopilotAnalyzeRead(
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
            capability_key=capability_key,
            idempotency_key=idempotency_key,
            input_payload={
                "pilot_mode": "draft_only",
                "recommendation_type": payload.recommendation_type,
                "readiness_score": facts["readiness_score"],
                "readiness_gaps": facts["readiness_gaps"],
                "authority_status": facts["authority_status"],
                "restrictions": [
                    "Do not calculate or approve a new offer.",
                    "Do not exceed or reinterpret approved seller authority.",
                    "Do not change CRM, underwriting, appointment, or task records.",
                    "Do not contact the seller.",
                    "Return a factual draft for human review only.",
                ],
            },
            lead_id=appointment.lead_id,
            appointment_id=appointment.id,
        ),
    )
    if run.status not in {"needs_review", "completed"} or not run.output_summary:
        return AcquisitionsCopilotAnalyzeRead(
            run_id=run.id,
            run_status=run.status,
            message=run.error_message or "The governed runtime did not produce a draft.",
            recommendation=None,
        )
    output_model = (
        AcquisitionsPreparationOutput
        if payload.recommendation_type == "preparation"
        else AcquisitionsFollowUpOutput
    )
    try:
        parsed = output_model.model_validate(json.loads(run.output_summary))
    except (json.JSONDecodeError, ValidationError) as exc:
        raise ValueError(
            "The model response did not match the Acquisitions Copilot contract."
        ) from exc

    recommendation = AcquisitionsCopilotRecommendation(
        organization_id=principal.organization_id,
        appointment_id=appointment.id,
        lead_id=appointment.lead_id,
        recommendation_type=payload.recommendation_type,
        field_meeting_brief_id=facts["brief"].id,
        field_inspection_id=(
            facts["inspection"].id if facts["inspection"] else None
        ),
        field_negotiation_session_id=(
            facts["negotiation"].id if facts["negotiation"] else None
        ),
        underwriting_version_id=(
            facts["underwriting"].id if facts["underwriting"] else None
        ),
        offer_negotiation_plan_id=(
            facts["approved_plan"].id if facts["approved_plan"] else None
        ),
        generated_for_user_id=appointment.owner_user_id or principal.user_id,
        ai_run_log_id=run.id,
        idempotency_key=idempotency_key,
        status="draft",
        output_payload=parsed.model_dump(),
        evidence_snapshot={
            "readiness_score": facts["readiness_score"],
            "readiness_gaps": facts["readiness_gaps"],
            "evidence_available": facts["evidence_available"],
            "authority_status": facts["authority_status"],
            "approved_ceiling_cents": facts["approved_ceiling_cents"],
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
        "acquisitions.copilot_recommendation_generated",
        recommendation.id,
        {
            "appointment_id": str(appointment.id),
            "recommendation_type": payload.recommendation_type,
            "ai_run_log_id": str(run.id),
            "external_actions_executed": False,
        },
    )
    db.commit()
    db.refresh(recommendation)
    return AcquisitionsCopilotAnalyzeRead(
        run_id=run.id,
        run_status=run.status,
        message="Draft acquisitions guidance generated for human review.",
        recommendation=recommendation_read(recommendation),
    )


def review_recommendation(
    db: Session,
    principal: Principal,
    recommendation_id: UUID,
    payload: AcquisitionsCopilotReviewRequest,
) -> AcquisitionsCopilotReviewRead | None:
    recommendation = db.scalar(
        select(AcquisitionsCopilotRecommendation).where(
            AcquisitionsCopilotRecommendation.organization_id
            == principal.organization_id,
            AcquisitionsCopilotRecommendation.id == recommendation_id,
        )
    )
    if recommendation is None:
        return None
    appointment = _scoped_appointment(db, principal, recommendation.appointment_id)
    if appointment is None:
        raise ValueError("The recommendation points to a missing appointment.")
    existing = db.scalar(
        select(AcquisitionsCopilotReview).where(
            AcquisitionsCopilotReview.recommendation_id == recommendation.id
        )
    )
    if existing is not None:
        return review_read(existing)
    if recommendation.status != "draft":
        raise ValueError("Only a draft recommendation can be reviewed.")

    if payload.decision == "edited":
        assert payload.final_output is not None
        contract = (
            AcquisitionsPreparationOutput
            if recommendation.recommendation_type == "preparation"
            else AcquisitionsFollowUpOutput
        )
        try:
            final_output = contract.model_validate(payload.final_output).model_dump()
        except ValidationError as exc:
            raise ValueError(
                "The corrected output must preserve the acquisitions response contract."
            ) from exc
    elif payload.decision == "accepted":
        final_output = recommendation.output_payload
    else:
        final_output = None

    now = datetime.now(UTC)
    review = AcquisitionsCopilotReview(
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
        "acquisitions.copilot_recommendation_reviewed",
        recommendation.id,
        {
            "decision": payload.decision,
            "crm_changes_applied": False,
            "external_actions_executed": False,
        },
    )
    db.commit()
    db.refresh(review)
    return review_read(review)


def recommendation_read(
    item: AcquisitionsCopilotRecommendation,
) -> AcquisitionsCopilotRecommendationRead:
    return AcquisitionsCopilotRecommendationRead(
        id=item.id,
        appointment_id=item.appointment_id,
        lead_id=item.lead_id,
        recommendation_type=item.recommendation_type,
        ai_run_log_id=item.ai_run_log_id,
        status=item.status,
        output_payload=item.output_payload,
        confidence_score=item.confidence_score,
        generated_at=item.generated_at,
        reviewed_at=item.reviewed_at,
    )


def review_read(item: AcquisitionsCopilotReview) -> AcquisitionsCopilotReviewRead:
    return AcquisitionsCopilotReviewRead(
        id=item.id,
        recommendation_id=item.recommendation_id,
        decision=item.decision,
        final_output=item.final_output,
        notes=item.notes,
        estimated_time_saved_seconds=item.estimated_time_saved_seconds,
        reviewed_at=item.reviewed_at,
    )


def _scoped_appointment(
    db: Session, principal: Principal, appointment_id: UUID
) -> Appointment | None:
    appointment = db.scalar(
        select(Appointment).where(
            Appointment.organization_id == principal.organization_id,
            Appointment.id == appointment_id,
        )
    )
    if appointment is None:
        return None
    can_manage = PermissionKeys.MANAGE_ACQUISITION_OPERATIONS in principal.permission_keys
    if not can_manage and appointment.owner_user_id != principal.user_id:
        raise PermissionError(
            "Only the assigned closer or an acquisition manager can access it."
        )
    return appointment


def _appointment_facts(
    db: Session, principal: Principal, appointment: Appointment
) -> AppointmentFacts:
    brief = db.scalar(
        select(FieldMeetingBrief)
        .where(
            FieldMeetingBrief.organization_id == principal.organization_id,
            FieldMeetingBrief.appointment_id == appointment.id,
            FieldMeetingBrief.status == "current",
        )
        .order_by(FieldMeetingBrief.version_number.desc())
    )
    qualification = db.scalar(
        select(LeadQualificationSession)
        .where(
            LeadQualificationSession.organization_id == principal.organization_id,
            LeadQualificationSession.lead_id == appointment.lead_id,
        )
        .order_by(LeadQualificationSession.completed_at.desc())
    )
    underwriting = db.scalar(
        select(UnderwritingVersion)
        .where(
            UnderwritingVersion.organization_id == principal.organization_id,
            UnderwritingVersion.lead_id == appointment.lead_id,
        )
        .order_by(UnderwritingVersion.version_number.desc())
    )
    market_analysis = db.scalar(
        select(UnderwritingMarketAnalysis)
        .where(
            UnderwritingMarketAnalysis.organization_id == principal.organization_id,
            UnderwritingMarketAnalysis.lead_id == appointment.lead_id,
        )
        .order_by(UnderwritingMarketAnalysis.created_at.desc())
    )
    plan = db.scalar(
        select(OfferNegotiationPlan)
        .where(
            OfferNegotiationPlan.organization_id == principal.organization_id,
            OfferNegotiationPlan.lead_id == appointment.lead_id,
        )
        .order_by(OfferNegotiationPlan.created_at.desc())
    )
    approval = (
        db.scalar(
            select(ApprovalRequest).where(
                ApprovalRequest.organization_id == principal.organization_id,
                ApprovalRequest.id == plan.approval_request_id,
            )
        )
        if plan and plan.approval_request_id
        else None
    )
    approved_plan = (
        plan
        if plan
        and plan.status == "approved"
        and approval
        and approval.status == "approved"
        else None
    )
    inspection = db.scalar(
        select(FieldInspection).where(
            FieldInspection.organization_id == principal.organization_id,
            FieldInspection.appointment_id == appointment.id,
        )
    )
    negotiation = db.scalar(
        select(FieldNegotiationSession).where(
            FieldNegotiationSession.organization_id == principal.organization_id,
            FieldNegotiationSession.appointment_id == appointment.id,
        )
    )
    lead = db.get(Lead, appointment.lead_id)
    gaps: list[str] = []
    evidence: list[str] = []
    score = 100
    for present, gap, label, penalty in (
        (brief is not None, "Generate the current meeting brief.", "Meeting brief", 25),
        (
            qualification is not None,
            "Complete seller qualification.",
            "Seller qualification",
            15,
        ),
        (underwriting is not None, "Complete underwriting.", "Underwriting", 20),
        (
            market_analysis is not None,
            "Run and review market analysis.",
            "Market analysis",
            15,
        ),
        (
            approved_plan is not None,
            "Obtain approved offer authority before discussing a final price.",
            "Approved offer authority",
            15,
        ),
    ):
        if present:
            evidence.append(label)
        else:
            gaps.append(gap)
            score -= penalty
    if lead:
        for field, label in (
            ("motivation", "seller motivation"),
            ("desired_timeline", "seller timeline"),
            ("property_condition", "property condition"),
            ("occupancy_status", "occupancy"),
        ):
            if not getattr(lead, field):
                gaps.append(f"Confirm {label}.")
                score -= 5
    if inspection:
        evidence.append("Field inspection")
    if negotiation and negotiation.outcome != "pending":
        evidence.append("Recorded meeting outcome")
    communication_count = int(
        db.scalar(
            select(func.count(CommunicationRecord.id)).where(
                CommunicationRecord.organization_id == principal.organization_id,
                CommunicationRecord.lead_id == appointment.lead_id,
            )
        )
        or 0
    )
    if communication_count:
        evidence.append("Communication history")
    approved_call_note_count = int(
        db.scalar(
            select(func.count(CallTranscript.id))
            .join(CallRecording, CallRecording.id == CallTranscript.recording_id)
            .join(CallRecord, CallRecord.id == CallRecording.call_record_id)
            .where(
                CallTranscript.organization_id == principal.organization_id,
                CallRecord.lead_id == appointment.lead_id,
                CallTranscript.approved_at.is_not(None),
            )
        )
        or 0
    )
    if approved_call_note_count:
        evidence.append("Approved call notes")
    score = max(0, score)
    band = "ready" if score >= 80 else "needs_review" if score >= 55 else "blocked"
    if approved_plan:
        authority_status = (
            "Approved offer authority is available. The human closer remains bound "
            "to the seller ceiling."
        )
    elif plan:
        authority_status = (
            "An offer plan exists but is not approved. Do not present a final price."
        )
    else:
        authority_status = "No approved offer authority. Do not present a final price."
    return {
        "brief": brief,
        "qualification": qualification,
        "underwriting": underwriting,
        "market_analysis": market_analysis,
        "approved_plan": approved_plan,
        "inspection": inspection,
        "negotiation": negotiation,
        "readiness_score": score,
        "readiness_band": band,
        "readiness_gaps": gaps,
        "evidence_available": evidence,
        "authority_status": authority_status,
        "approved_ceiling_cents": (
            approved_plan.seller_ceiling_cents if approved_plan else None
        ),
    }


def _idempotency_key(
    appointment: Appointment,
    recommendation_type: str,
    facts: AppointmentFacts,
) -> str:
    fingerprint = {
        "appointment_id": str(appointment.id),
        "appointment_updated_at": appointment.updated_at.isoformat(),
        "recommendation_type": recommendation_type,
        "brief_updated_at": _updated(facts["brief"]),
        "inspection_updated_at": _updated(facts["inspection"]),
        "negotiation_updated_at": _updated(facts["negotiation"]),
        "underwriting_updated_at": _updated(facts["underwriting"]),
        "approved_plan_updated_at": _updated(facts["approved_plan"]),
    }
    digest = hashlib.sha256(
        json.dumps(fingerprint, sort_keys=True).encode()
    ).hexdigest()[:24]
    return f"acquisitions-copilot:{appointment.id}:{recommendation_type}:{digest}"


def _updated(value: object) -> str | None:
    updated_at = getattr(value, "updated_at", None)
    return updated_at.isoformat() if updated_at else None


def _metrics(
    db: Session, principal: Principal
) -> AcquisitionsCopilotMetrics:
    since = datetime.now(UTC) - timedelta(days=30)
    recommendations = list(
        db.scalars(
            select(AcquisitionsCopilotRecommendation).where(
                AcquisitionsCopilotRecommendation.organization_id
                == principal.organization_id,
                AcquisitionsCopilotRecommendation.generated_at >= since,
            )
        ).all()
    )
    ids = [item.id for item in recommendations]
    reviews = (
        list(
            db.scalars(
                select(AcquisitionsCopilotReview).where(
                    AcquisitionsCopilotReview.organization_id
                    == principal.organization_id,
                    AcquisitionsCopilotReview.recommendation_id.in_(ids),
                )
            ).all()
        )
        if ids
        else []
    )
    reviewed = len(reviews)
    accepted_or_edited = sum(
        item.decision in {"accepted", "edited"} for item in reviews
    )
    edited = sum(item.decision == "edited" for item in reviews)
    return AcquisitionsCopilotMetrics(
        generated=len(recommendations),
        reviewed=reviewed,
        accepted_or_corrected_rate_basis_points=(
            round(accepted_or_edited / reviewed * 10_000) if reviewed else 0
        ),
        correction_rate_basis_points=(
            round(edited / reviewed * 10_000) if reviewed else 0
        ),
        estimated_time_saved_minutes=round(
            sum(item.estimated_time_saved_seconds for item in reviews) / 60
        ),
    )


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
            entity_type="acquisitions_copilot_recommendation",
            entity_id=entity_id,
            previous_value=None,
            new_value=value,
            reason="Acquisitions Copilot draft-only pilot",
        )
    )
