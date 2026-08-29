import hashlib
import json
from datetime import UTC, datetime, timedelta
from typing import Any, Literal, TypedDict
from uuid import UUID

from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.auth import Principal
from app.models.foundation import (
    AiAgentDefinition,
    AiRunLog,
    AuditEvent,
    Buyer,
    BuyerEngagement,
    BuyerOffer,
    BuyerProofDocument,
    CommunicationRecord,
    DispositionBuyerPoolEntry,
    DispositionBuyerPoolRun,
    DispositionCase,
    DispositionCopilotRecommendation,
    DispositionCopilotReview,
    DispositionMatch,
    DispositionOfferRevision,
    DispositionPackageVersion,
    DispositionProviderEvidence,
    DispositionReplyLink,
)
from app.schemas.ai import AiRuntimeExecuteCreate
from app.schemas.dispositions import (
    DispositionCoordinationOutput,
    DispositionCopilotAiTrace,
    DispositionCopilotAnalyzeRead,
    DispositionCopilotAnalyzeRequest,
    DispositionCopilotAuthority,
    DispositionCopilotMetrics,
    DispositionCopilotOverview,
    DispositionCopilotPilotEvaluation,
    DispositionCopilotQualityEvaluation,
    DispositionCopilotRecommendationRead,
    DispositionCopilotReviewRead,
    DispositionCopilotReviewRequest,
    DispositionEvidenceCitation,
    DispositionRiskAlert,
)
from app.services.ai_runtime import execute_runtime, get_runtime_overview
from app.services.disposition_packages import sanitize_public_snapshot
from app.services.dispositions import (
    _proof_is_current_verified,
    can_view_private_economics,
    require_house_case_workflow,
    require_private_economics_access,
    scoped_case,
)

ScenarioGroup = Literal[
    "normal",
    "incomplete",
    "conflicting",
    "policy_blocked",
    "stale",
    "adversarial",
]


class DispositionCopilotReviewConflict(ValueError):
    """Raised when an immutable Copilot review already exists."""


class DispositionFacts(TypedDict):
    readiness_score: int
    readiness_band: Literal["ready", "needs_review", "blocked"]
    readiness_gaps: list[str]
    risk_alerts: list[DispositionRiskAlert]
    qualified_buyer_count: int
    verified_buyer_count: int
    offer_count: int
    backup_coverage: bool
    matches: list[DispositionMatch]
    offers: list[BuyerOffer]
    engagements: list[BuyerEngagement]
    buyers: dict[UUID, Buyer]
    citations: list[DispositionEvidenceCitation]
    evidence_fingerprint: str
    valid_reply_source_ids: set[UUID]
    valid_provider_source_ids: set[UUID]
    buyer_citation_ids: dict[UUID, set[str]]
    offer_citation_ids: dict[UUID, set[str]]
    package_citation_ids: set[str]


def get_disposition_copilot_overview(
    db: Session,
    principal: Principal,
    case_id: UUID,
) -> DispositionCopilotOverview | None:
    case = scoped_case(db, principal, case_id)
    if case is None:
        return None
    require_house_case_workflow(db, case)
    may_view_private = can_view_private_economics(principal)
    facts = _disposition_facts(db, principal, case)
    runtime = get_runtime_overview(db, principal)
    statuses = {item.capability_key: item.status for item in runtime.capabilities}
    recommendations = list(
        db.scalars(
            select(DispositionCopilotRecommendation)
            .where(
                DispositionCopilotRecommendation.organization_id == principal.organization_id,
                DispositionCopilotRecommendation.disposition_case_id == case.id,
            )
            .order_by(DispositionCopilotRecommendation.generated_at.desc())
        ).all()
    )
    return DispositionCopilotOverview(
        pilot_mode="draft_only",
        runtime_status=runtime.status,
        capability_status=statuses.get("disposition.match", "not_installed"),
        # Disposition Copilot is a review-only product invariant. A global runtime
        # policy may enable other capabilities, but it can never grant this
        # capability authority to contact buyers or bind Stonegate.
        external_actions_blocked=True,
        readiness_score=facts["readiness_score"],
        readiness_band=facts["readiness_band"],
        readiness_gaps=facts["readiness_gaps"],
        risk_alerts=facts["risk_alerts"],
        qualified_buyer_count=facts["qualified_buyer_count"],
        verified_buyer_count=facts["verified_buyer_count"],
        offer_count=facts["offer_count"],
        backup_coverage=facts["backup_coverage"],
        recommendations=(
            [recommendation_read(db, item, current_facts=facts) for item in recommendations]
            if may_view_private
            else []
        ),
        metrics=_metrics(db, principal),
    )


def analyze_disposition(
    db: Session,
    principal: Principal,
    case_id: UUID,
    payload: DispositionCopilotAnalyzeRequest,
) -> DispositionCopilotAnalyzeRead | None:
    require_private_economics_access(principal)
    case = scoped_case(db, principal, case_id)
    if case is None:
        return None
    require_house_case_workflow(db, case)
    facts = _disposition_facts(db, principal, case)
    agent = db.scalar(
        select(AiAgentDefinition).where(
            AiAgentDefinition.organization_id == principal.organization_id,
            AiAgentDefinition.key == "disposition",
        )
    )
    if agent is None:
        raise ValueError("Install the governed AI agent portfolio first.")
    idempotency_key = payload.idempotency_key or _idempotency_key(case, facts)
    existing = db.scalar(
        select(DispositionCopilotRecommendation).where(
            DispositionCopilotRecommendation.organization_id == principal.organization_id,
            DispositionCopilotRecommendation.idempotency_key == idempotency_key,
        )
    )
    if existing is not None:
        stored_fingerprint = str(
            (existing.evidence_snapshot or {}).get("evidence_fingerprint") or ""
        )
        if stored_fingerprint and stored_fingerprint != facts["evidence_fingerprint"]:
            raise ValueError(
                "This idempotency key was already used with different disposition evidence. "
                "Generate a new review draft instead of reusing stale evidence."
            )
        if existing.ai_run_log_id is None:
            raise ValueError("The existing recommendation has no governed AI trace.")
        return DispositionCopilotAnalyzeRead(
            run_id=existing.ai_run_log_id,
            run_status="needs_review",
            message="The current disposition draft is already available.",
            recommendation=recommendation_read(db, existing, current_facts=facts),
        )

    run = execute_runtime(
        db,
        principal,
        AiRuntimeExecuteCreate(
            agent_definition_id=agent.id,
            capability_key="disposition.match",
            idempotency_key=idempotency_key,
            input_payload={
                "pilot_mode": "draft_only",
                "readiness_gaps": facts["readiness_gaps"],
                "deterministic_risk_alerts": [
                    item.model_dump(mode="json")
                    for item in facts["risk_alerts"]
                    if "internal floor" not in item.reason.lower()
                ],
                "evidence_fingerprint": facts["evidence_fingerprint"],
                "evidence_catalog": [
                    item.model_dump(mode="json") for item in facts["citations"]
                ],
                "restrictions": [
                    "Do not select a buyer, approve economics, or change a buyer record.",
                    "Do not contact a buyer, release a campaign, or post to a marketplace.",
                    (
                        "Do not expose the seller identity, Stonegate purchase price, "
                        "or internal floor."
                    ),
                    (
                        "Do not claim proof of funds, property facts, or buyer capacity "
                        "without evidence."
                    ),
                    "Return a human-review draft using only supplied records.",
                    (
                        "Every buyer recommendation, offer comparison, draft, reply "
                        "classification, next action, and buyer update proposal must cite one "
                        "or more exact citation_id values from evidence_catalog."
                    ),
                    (
                        "Set can_send_outreach, can_select_buyer, can_bind_stonegate, and "
                        "can_update_buyer to false."
                    ),
                ],
            },
            lead_id=case.lead_id,
            transaction_id=case.transaction_id,
        ),
    )
    if run.status not in {"needs_review", "completed"} or not run.output_summary:
        return DispositionCopilotAnalyzeRead(
            run_id=run.id,
            run_status=run.status,
            message=run.error_message or "The governed runtime did not produce a draft.",
            recommendation=None,
        )
    try:
        parsed = DispositionCoordinationOutput.model_validate(json.loads(run.output_summary))
    except (json.JSONDecodeError, ValidationError) as exc:
        raise ValueError(
            "The model response did not match the Disposition Copilot contract."
        ) from exc
    _validate_output(case, facts, parsed)

    recommendation = DispositionCopilotRecommendation(
        organization_id=principal.organization_id,
        disposition_case_id=case.id,
        transaction_id=case.transaction_id,
        lead_id=case.lead_id,
        generated_for_user_id=case.owner_user_id or principal.user_id,
        ai_run_log_id=run.id,
        idempotency_key=idempotency_key,
        status="draft",
        output_payload=parsed.model_dump(mode="json"),
        evidence_snapshot={
            "schema_version": "ds9-v1",
            "evidence_fingerprint": facts["evidence_fingerprint"],
            "citations": [item.model_dump(mode="json") for item in facts["citations"]],
            "readiness_score": facts["readiness_score"],
            "readiness_gaps": facts["readiness_gaps"],
            "risk_alerts": [item.model_dump(mode="json") for item in facts["risk_alerts"]],
            "qualified_buyer_count": facts["qualified_buyer_count"],
            "verified_buyer_count": facts["verified_buyer_count"],
            "offer_count": facts["offer_count"],
            "backup_coverage": facts["backup_coverage"],
            "authority": DispositionCopilotAuthority().model_dump(mode="json"),
            "ai_trace": _trace_payload_from_run(run),
            "output_fingerprint": _canonical_hash(parsed.model_dump(mode="json")),
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
        "disposition.copilot_recommendation_generated",
        recommendation.id,
        {
            "disposition_case_id": str(case.id),
            "ai_run_log_id": str(run.id),
            "buyer_changes_applied": False,
            "campaign_released": False,
            "external_actions_executed": False,
        },
    )
    db.commit()
    db.refresh(recommendation)
    return DispositionCopilotAnalyzeRead(
        run_id=run.id,
        run_status=run.status,
        message="Draft disposition guidance generated for human review.",
        recommendation=recommendation_read(db, recommendation, current_facts=facts),
    )


def review_recommendation(
    db: Session,
    principal: Principal,
    recommendation_id: UUID,
    payload: DispositionCopilotReviewRequest,
) -> DispositionCopilotReviewRead | None:
    require_private_economics_access(principal)
    recommendation = db.scalar(
        select(DispositionCopilotRecommendation).where(
            DispositionCopilotRecommendation.organization_id == principal.organization_id,
            DispositionCopilotRecommendation.id == recommendation_id,
        )
    )
    if recommendation is None:
        return None
    existing = db.scalar(
        select(DispositionCopilotReview).where(
            DispositionCopilotReview.recommendation_id == recommendation.id
        )
    )
    if existing is not None:
        raise DispositionCopilotReviewConflict(
            "This disposition recommendation has already been reviewed."
        )
    if recommendation.status != "draft":
        raise ValueError("Only a draft recommendation can be reviewed.")

    case = scoped_case(db, principal, recommendation.disposition_case_id)
    if case is None:
        raise ValueError("Disposition case not found.")
    require_house_case_workflow(db, case)
    facts = _disposition_facts(db, principal, case)
    stored_fingerprint = str(
        (recommendation.evidence_snapshot or {}).get("evidence_fingerprint") or ""
    )
    evidence_is_current = bool(stored_fingerprint) and (
        stored_fingerprint == facts["evidence_fingerprint"]
    )
    if payload.decision in {"accepted", "edited"} and not evidence_is_current:
        raise ValueError(
            "Disposition evidence changed after this draft was generated. Generate a fresh "
            "draft before accepting or correcting guidance."
        )
    if payload.decision == "edited":
        assert payload.final_output is not None
        try:
            parsed = DispositionCoordinationOutput.model_validate(payload.final_output)
        except ValidationError as exc:
            raise ValueError(
                "The corrected output must preserve the disposition response contract."
            ) from exc
        _validate_output(case, facts, parsed)
        final_output = parsed.model_dump(mode="json")
    elif payload.decision == "accepted":
        final_output = recommendation.output_payload
    else:
        final_output = None

    now = datetime.now(UTC)
    evaluation_payload: dict[str, object] = {}
    if payload.quality_evaluation is not None:
        evaluation_payload = {
            **payload.quality_evaluation.model_dump(mode="json"),
            "evidence_fingerprint": stored_fingerprint,
            "output_fingerprint": _canonical_hash(recommendation.output_payload),
            "correction_fingerprint": (
                _canonical_hash(final_output) if payload.decision == "edited" else None
            ),
            "trace_attributed": _has_complete_trace(db, recommendation),
            "review_decision": payload.decision,
            "evaluated_at": now.isoformat(),
        }
    review = DispositionCopilotReview(
        organization_id=principal.organization_id,
        recommendation_id=recommendation.id,
        reviewed_by_user_id=principal.user_id,
        decision=payload.decision,
        original_output=recommendation.output_payload,
        final_output=final_output,
        notes=payload.notes,
        estimated_time_saved_seconds=payload.estimated_time_saved_seconds,
        quality_evaluation=evaluation_payload,
        reviewed_at=now,
    )
    db.add(review)
    recommendation.status = payload.decision
    recommendation.reviewed_at = now
    _audit(
        db,
        principal,
        "disposition.copilot_recommendation_reviewed",
        recommendation.id,
        {
            "decision": payload.decision,
            "quality_evaluation_recorded": bool(evaluation_payload),
            "evidence_fingerprint": stored_fingerprint,
            "buyer_changes_applied": False,
            "campaign_released": False,
            "external_actions_executed": False,
        },
    )
    db.commit()
    db.refresh(review)
    return review_read(review)


def recommendation_read(
    db: Session,
    item: DispositionCopilotRecommendation,
    *,
    current_facts: DispositionFacts | None = None,
) -> DispositionCopilotRecommendationRead:
    snapshot = item.evidence_snapshot or {}
    evidence_fingerprint = str(snapshot.get("evidence_fingerprint") or "")
    if not evidence_fingerprint or current_facts is None:
        evidence_status: Literal["current", "stale", "unknown"] = "unknown"
        stale_reason = (
            "This historical draft predates versioned evidence fingerprints."
            if not evidence_fingerprint
            else None
        )
    elif evidence_fingerprint == current_facts["evidence_fingerprint"]:
        evidence_status = "current"
        stale_reason = None
    else:
        evidence_status = "stale"
        stale_reason = "Saved disposition evidence changed after this draft was generated."
    permitted_review_decisions: list[
        Literal["accepted", "edited", "rejected", "ignored"]
    ] = (
        ["accepted", "edited", "rejected", "ignored"]
        if evidence_status == "current"
        else ["rejected", "ignored"]
    )
    ai_trace = _recommendation_trace(db, item)
    return DispositionCopilotRecommendationRead(
        id=item.id,
        disposition_case_id=item.disposition_case_id,
        transaction_id=item.transaction_id,
        lead_id=item.lead_id,
        ai_run_log_id=item.ai_run_log_id,
        status=item.status,
        output_payload=DispositionCoordinationOutput.model_validate(item.output_payload),
        evidence_fingerprint=evidence_fingerprint,
        evidence_citations=[
            DispositionEvidenceCitation.model_validate(citation)
            for citation in snapshot.get("citations", [])
        ],
        evidence_status=evidence_status,
        stale_reason=stale_reason,
        permitted_review_decisions=permitted_review_decisions,
        ai_trace=ai_trace,
        authority=DispositionCopilotAuthority(),
        confidence_score=item.confidence_score,
        generated_at=item.generated_at,
        reviewed_at=item.reviewed_at,
    )


def review_read(item: DispositionCopilotReview) -> DispositionCopilotReviewRead:
    evaluation = item.quality_evaluation or {}
    return DispositionCopilotReviewRead(
        id=item.id,
        recommendation_id=item.recommendation_id,
        decision=item.decision,
        final_output=(
            DispositionCoordinationOutput.model_validate(item.final_output)
            if item.final_output is not None
            else None
        ),
        notes=item.notes,
        estimated_time_saved_seconds=item.estimated_time_saved_seconds,
        quality_evaluation=(
            DispositionCopilotQualityEvaluation.model_validate(evaluation)
            if evaluation
            else None
        ),
        reviewed_at=item.reviewed_at,
    )


def _disposition_facts(
    db: Session,
    principal: Principal,
    case: DispositionCase,
) -> DispositionFacts:
    historical_matches = list(
        db.scalars(
            select(DispositionMatch)
            .where(
                DispositionMatch.organization_id == principal.organization_id,
                DispositionMatch.disposition_case_id == case.id,
            )
            .order_by(DispositionMatch.rank)
        ).all()
    )
    buyer_ids = {item.buyer_id for item in historical_matches}
    buyers = (
        {
            item.id: item
            for item in db.scalars(
                select(Buyer).where(
                    Buyer.organization_id == principal.organization_id,
                    Buyer.id.in_(buyer_ids),
                )
            ).all()
        }
        if buyer_ids
        else {}
    )
    matches = [
        match
        for match in historical_matches
        if (
            match.buyer_id in buyers
            and buyers[match.buyer_id].status == "active"
            and buyers[match.buyer_id].relationship_status != "do_not_contact"
            and buyers[match.buyer_id].archived_at is None
        )
    ]
    now = datetime.now(UTC)
    proof_documents = (
        list(
            db.scalars(
                select(BuyerProofDocument)
                .where(
                    BuyerProofDocument.organization_id == principal.organization_id,
                    BuyerProofDocument.buyer_id.in_(buyer_ids),
                    BuyerProofDocument.deleted_at.is_(None),
                    BuyerProofDocument.status == "verified",
                )
                .order_by(
                    BuyerProofDocument.verified_at.desc(),
                    BuyerProofDocument.created_at.desc(),
                )
            ).all()
        )
        if buyer_ids
        else []
    )
    reviewed_proof_by_buyer: dict[UUID, BuyerProofDocument] = {}
    verified_proof_by_buyer: dict[UUID, BuyerProofDocument] = {}
    for document in proof_documents:
        reviewed_proof_by_buyer.setdefault(document.buyer_id, document)
        if document.buyer_id not in verified_proof_by_buyer and _proof_is_current_verified(
            document, now=now
        ):
            verified_proof_by_buyer[document.buyer_id] = document
    verified_buyer_ids = set(verified_proof_by_buyer)
    offers = list(
        db.scalars(
            select(BuyerOffer)
            .where(
                BuyerOffer.organization_id == principal.organization_id,
                BuyerOffer.disposition_case_id == case.id,
            )
            .order_by(BuyerOffer.amount_cents.desc())
        ).all()
    )
    engagements = list(
        db.scalars(
            select(BuyerEngagement)
            .where(
                BuyerEngagement.organization_id == principal.organization_id,
                BuyerEngagement.disposition_case_id == case.id,
            )
            .order_by(BuyerEngagement.occurred_at.desc())
        ).all()
    )
    package_version = db.scalar(
        select(DispositionPackageVersion)
        .where(
            DispositionPackageVersion.organization_id == principal.organization_id,
            DispositionPackageVersion.disposition_case_id == case.id,
        )
        .order_by(DispositionPackageVersion.version_number.desc())
    )
    pool_run = db.scalar(
        select(DispositionBuyerPoolRun)
        .where(
            DispositionBuyerPoolRun.organization_id == principal.organization_id,
            DispositionBuyerPoolRun.disposition_case_id == case.id,
        )
        .order_by(DispositionBuyerPoolRun.version_number.desc())
    )
    pool_entries = (
        list(
            db.scalars(
                select(DispositionBuyerPoolEntry)
                .where(
                    DispositionBuyerPoolEntry.organization_id
                    == principal.organization_id,
                    DispositionBuyerPoolEntry.buyer_pool_run_id == pool_run.id,
                )
                .order_by(DispositionBuyerPoolEntry.rank)
                .limit(100)
            ).all()
        )
        if pool_run is not None
        else []
    )
    offer_revisions = list(
        db.scalars(
            select(DispositionOfferRevision)
            .where(
                DispositionOfferRevision.organization_id == principal.organization_id,
                DispositionOfferRevision.disposition_case_id == case.id,
            )
            .order_by(
                DispositionOfferRevision.offer_id,
                DispositionOfferRevision.revision_number.desc(),
            )
        ).all()
    )
    reply_rows = [
        (row[0], row[1])
        for row in db.execute(
            select(DispositionReplyLink, CommunicationRecord)
            .join(
                CommunicationRecord,
                CommunicationRecord.id == DispositionReplyLink.communication_record_id,
            )
            .where(
                DispositionReplyLink.organization_id == principal.organization_id,
                DispositionReplyLink.disposition_case_id == case.id,
                CommunicationRecord.organization_id == principal.organization_id,
            )
            .order_by(DispositionReplyLink.linked_at.desc())
            .limit(100)
        ).all()
    ]
    provider_evidence = list(
        db.scalars(
            select(DispositionProviderEvidence)
            .where(
                DispositionProviderEvidence.organization_id == principal.organization_id,
                DispositionProviderEvidence.disposition_case_id == case.id,
                DispositionProviderEvidence.review_status == "reviewed",
            )
            .order_by(DispositionProviderEvidence.occurred_at.desc())
            .limit(100)
        ).all()
    )

    gaps: list[str] = []
    risks: list[DispositionRiskAlert] = []
    may_view_private = can_view_private_economics(principal)
    score = 100
    if case.package_status != "approved":
        gaps.append("Approve the fact-checked investor package.")
        score -= 35
    package_property = case.package_snapshot.get("property")
    if not isinstance(package_property, dict):
        package_property = {}
    for value, label in (
        (
            package_property.get("address")
            or case.package_snapshot.get("property_address"),
            "property address",
        ),
        (
            package_property.get("property_type")
            or case.package_snapshot.get("property_type"),
            "property type",
        ),
    ):
        if not value:
            gaps.append(f"Confirm the {label}.")
            score -= 10
    if not matches:
        gaps.append("Generate the deterministic buyer ranking.")
        score -= 20
    qualified = [item for item in matches if item.qualification_status == "qualified"]
    if matches and not qualified:
        gaps.append("Resolve buyer qualification and proof-of-funds gaps.")
        score -= 20
    verified = [item for item in qualified if item.buyer_id in verified_buyer_ids]
    if qualified and not verified:
        gaps.append("Verify current proof of funds for at least one qualified buyer.")
        score -= 15
    if case.status in {"marketed", "offers_received"} and not offers:
        gaps.append("Record buyer responses and offers.")
        score -= 10

    for match in matches:
        buyer = buyers.get(match.buyer_id)
        if buyer is None:
            continue
        reviewed_proof = verified_proof_by_buyer.get(buyer.id) or reviewed_proof_by_buyer.get(
            buyer.id
        )
        if reviewed_proof is not None and not _proof_is_current_verified(reviewed_proof, now=now):
            risks.append(
                DispositionRiskAlert(
                    severity="critical",
                    item=buyer.name,
                    reason="Proof of funds is expired.",
                    evidence=["Buyer proof expiration record"],
                )
            )
        if not buyer.email and not buyer.phone:
            risks.append(
                DispositionRiskAlert(
                    severity="warning",
                    item=buyer.name,
                    reason="No buyer contact method is recorded.",
                    evidence=["Buyer CRM record"],
                )
            )
    for offer in offers:
        buyer_name = buyers.get(offer.buyer_id)
        label = buyer_name.name if buyer_name else "Recorded buyer"
        if may_view_private and offer.amount_cents < case.minimum_acceptable_cents:
            risks.append(
                DispositionRiskAlert(
                    severity="critical",
                    item=f"{label} offer",
                    reason="Offer is below Stonegate's approved internal floor.",
                    evidence=[f"Buyer offer {offer.id}"],
                )
            )
        if (
            offer.deposit_due_at
            and offer.deposit_received_at is None
            and _aware(offer.deposit_due_at) < now
        ):
            risks.append(
                DispositionRiskAlert(
                    severity="critical",
                    item=f"{label} deposit",
                    reason="Buyer deposit is overdue.",
                    evidence=[f"Buyer offer {offer.id}"],
                )
            )
        elif (
            offer.deposit_due_at
            and offer.deposit_received_at is None
            and _aware(offer.deposit_due_at) <= now + timedelta(days=2)
        ):
            risks.append(
                DispositionRiskAlert(
                    severity="warning",
                    item=f"{label} deposit",
                    reason="Buyer deposit is due within two days.",
                    evidence=[f"Buyer offer {offer.id}"],
                )
            )
    backup_coverage = case.backup_buyer_id is not None
    if case.selected_buyer_id is not None and not backup_coverage:
        risks.append(
            DispositionRiskAlert(
                severity="warning",
                item="Backup coverage",
                reason="The approved primary buyer has no recorded backup buyer.",
                evidence=["Disposition buyer selection"],
            )
        )
        score -= 10
    critical_count = sum(item.severity == "critical" for item in risks)
    score = max(0, score - min(30, critical_count * 10))
    band: Literal["ready", "needs_review", "blocked"] = (
        "ready" if score >= 80 else "needs_review" if score >= 50 else "blocked"
    )
    severity_order = {"critical": 0, "warning": 1, "info": 2}
    citations = _build_evidence_catalog(
        case=case,
        now=now,
        package_version=package_version,
        pool_entries=pool_entries,
        matches=matches,
        buyers=buyers,
        proof_documents=proof_documents,
        offers=offers,
        offer_revisions=offer_revisions,
        engagements=engagements,
        reply_rows=reply_rows,
        provider_evidence=provider_evidence,
    )
    evidence_fingerprint = _canonical_hash(
        [item.model_dump(mode="json") for item in citations]
    )
    buyer_citation_ids: dict[UUID, set[str]] = {buyer_id: set() for buyer_id in buyer_ids}
    for match in matches:
        buyer_citation_ids.setdefault(match.buyer_id, set()).add(f"buyer_match:{match.id}")
    for buyer_id in buyers:
        buyer_citation_ids.setdefault(buyer_id, set()).add(
            f"buyer_contact_status:{buyer_id}"
        )
    for entry in pool_entries:
        if entry.buyer_id is not None:
            buyer_citation_ids.setdefault(entry.buyer_id, set()).add(
                f"buyer_pool_entry:{entry.id}"
            )
    for document in proof_documents:
        buyer_citation_ids.setdefault(document.buyer_id, set()).add(
            f"buyer_proof:{document.id}"
        )
    for engagement in engagements:
        buyer_citation_ids.setdefault(engagement.buyer_id, set()).add(
            f"buyer_engagement:{engagement.id}"
        )
    offer_citation_ids: dict[UUID, set[str]] = {
        offer.id: {f"buyer_offer:{offer.id}"} for offer in offers
    }
    for revision in offer_revisions:
        offer_citation_ids.setdefault(revision.offer_id, set()).add(
            f"offer_revision:{revision.id}"
        )
    package_citation_ids = {f"case_snapshot:{case.id}"}
    if package_version is not None:
        package_citation_ids.add(f"package_version:{package_version.id}")
    return {
        "readiness_score": score,
        "readiness_band": band,
        "readiness_gaps": gaps,
        "risk_alerts": sorted(risks, key=lambda item: severity_order[item.severity]),
        "qualified_buyer_count": len(qualified),
        "verified_buyer_count": len(verified),
        "offer_count": len(offers),
        "backup_coverage": backup_coverage,
        "matches": matches,
        "offers": offers,
        "engagements": engagements,
        "buyers": buyers,
        "citations": citations,
        "evidence_fingerprint": evidence_fingerprint,
        "valid_reply_source_ids": {item.id for item, _record in reply_rows},
        "valid_provider_source_ids": {item.id for item in provider_evidence},
        "buyer_citation_ids": buyer_citation_ids,
        "offer_citation_ids": offer_citation_ids,
        "package_citation_ids": package_citation_ids,
    }


def _build_evidence_catalog(
    *,
    case: DispositionCase,
    now: datetime,
    package_version: DispositionPackageVersion | None,
    pool_entries: list[DispositionBuyerPoolEntry],
    matches: list[DispositionMatch],
    buyers: dict[UUID, Buyer],
    proof_documents: list[BuyerProofDocument],
    offers: list[BuyerOffer],
    offer_revisions: list[DispositionOfferRevision],
    engagements: list[BuyerEngagement],
    reply_rows: list[tuple[DispositionReplyLink, CommunicationRecord]],
    provider_evidence: list[DispositionProviderEvidence],
) -> list[DispositionEvidenceCitation]:
    citations: list[DispositionEvidenceCitation] = [
        DispositionEvidenceCitation(
            citation_id=f"case_snapshot:{case.id}",
            source_type="case_snapshot",
            source_id=str(case.id),
            label="Disposition case snapshot",
            fact=_compact_fact(
                {
                    "status": case.status,
                    "strategy": case.strategy,
                    "package_status": case.package_status,
                    "public_package": sanitize_public_snapshot(
                        package_version.public_snapshot
                        if package_version is not None
                        else case.package_snapshot
                    ),
                    "asking_price_cents": case.asking_price_cents,
                    "selected_buyer_id": case.selected_buyer_id,
                    "backup_buyer_id": case.backup_buyer_id,
                }
            ),
            status=case.status,
            observed_at=case.updated_at,
        )
    ]
    if package_version is not None:
        citations.append(
            DispositionEvidenceCitation(
                citation_id=f"package_version:{package_version.id}",
                source_type="package_version",
                source_id=str(package_version.id),
                label=f"Investor package v{package_version.version_number}",
                fact=_compact_fact(
                    {
                        "status": package_version.status,
                        "public_snapshot": sanitize_public_snapshot(
                            package_version.public_snapshot
                        ),
                        "source_fingerprint": package_version.source_fingerprint,
                    }
                ),
                status=package_version.status,
                observed_at=package_version.approved_at or package_version.updated_at,
            )
        )
    for buyer_id, buyer in sorted(buyers.items(), key=lambda item: str(item[0])):
        contact_available = bool(buyer.email or buyer.phone)
        citations.append(
            DispositionEvidenceCitation(
                citation_id=f"buyer_contact_status:{buyer_id}",
                source_type="buyer_contact_status",
                source_id=str(buyer_id),
                label=f"Buyer contact readiness: {buyer.name}",
                fact=_compact_fact(
                    {
                        "buyer_id": buyer_id,
                        "has_email": bool(buyer.email),
                        "has_phone": bool(buyer.phone),
                        "contact_available": contact_available,
                    }
                ),
                status="available" if contact_available else "unavailable",
                observed_at=buyer.updated_at,
            )
        )
    for entry in pool_entries:
        buyer_name = (
            buyers[entry.buyer_id].name
            if entry.buyer_id is not None and entry.buyer_id in buyers
            else "External buyer candidate"
        )
        citations.append(
            DispositionEvidenceCitation(
                citation_id=f"buyer_pool_entry:{entry.id}",
                source_type="buyer_pool_entry",
                source_id=str(entry.id),
                label=f"Buyer pool rank {entry.rank}: {buyer_name}",
                fact=_compact_fact(
                    {
                        "buyer_id": entry.buyer_id,
                        "rank": entry.rank,
                        "score_basis_points": entry.score_basis_points,
                        "eligibility_status": entry.eligibility_status,
                        "score_explanation": entry.score_explanation,
                        "supporting_evidence": entry.supporting_evidence,
                        "conflicting_evidence": entry.conflicting_evidence,
                        "disqualifying_reasons": entry.disqualifying_reasons,
                        "source_fingerprint": entry.source_fingerprint,
                    }
                ),
                status=entry.eligibility_status,
                observed_at=entry.updated_at,
            )
        )
    for match in matches:
        buyer = buyers.get(match.buyer_id)
        citations.append(
            DispositionEvidenceCitation(
                citation_id=f"buyer_match:{match.id}",
                source_type="buyer_match",
                source_id=str(match.id),
                label=f"Ranked buyer match: {buyer.name if buyer else match.buyer_id}",
                fact=_compact_fact(
                    {
                        "buyer_id": match.buyer_id,
                        "rank": match.rank,
                        "score_basis_points": match.score_basis_points,
                        "score_components": match.score_components,
                        "qualification_status": match.qualification_status,
                        "recipient_status": match.recipient_status,
                    }
                ),
                status=match.qualification_status,
                observed_at=match.updated_at,
            )
        )
    for document in proof_documents:
        buyer = buyers.get(document.buyer_id)
        citations.append(
            DispositionEvidenceCitation(
                citation_id=f"buyer_proof:{document.id}",
                source_type="buyer_proof",
                source_id=str(document.id),
                label=f"Proof of funds: {buyer.name if buyer else document.buyer_id}",
                fact=_compact_fact(
                    {
                        "buyer_id": document.buyer_id,
                        "status": document.status,
                        "verified_amount_cents": document.verified_amount_cents,
                        "verified_at": document.verified_at,
                        "expires_at": document.expires_at,
                        "freshness_status": _proof_freshness_status(document, now=now),
                        "verification_source": document.verification_source,
                        "sha256": document.sha256,
                    }
                ),
                status=document.status,
                observed_at=document.verified_at or document.updated_at,
            )
        )
    for offer in offers:
        buyer = buyers.get(offer.buyer_id)
        citations.append(
            DispositionEvidenceCitation(
                citation_id=f"buyer_offer:{offer.id}",
                source_type="buyer_offer",
                source_id=str(offer.id),
                label=f"Buyer offer: {buyer.name if buyer else offer.buyer_id}",
                fact=_compact_fact(
                    {
                        "buyer_id": offer.buyer_id,
                        "amount_cents": offer.amount_cents,
                        "earnest_money_cents": offer.earnest_money_cents,
                        "financing_type": offer.financing_type,
                        "status": offer.status,
                        "proof_of_funds_received": offer.proof_of_funds_received,
                        "proposed_closing_at": offer.proposed_closing_at,
                        "deposit_due_at": offer.deposit_due_at,
                        "deposit_received_at": offer.deposit_received_at,
                        "deposit_status": _offer_deposit_status(offer, now=now),
                        "special_terms": offer.special_terms,
                    }
                ),
                status=offer.status,
                observed_at=offer.received_at,
            )
        )
    latest_offer_revisions: dict[UUID, DispositionOfferRevision] = {}
    for revision in offer_revisions:
        latest_offer_revisions.setdefault(revision.offer_id, revision)
    for revision in latest_offer_revisions.values():
        citations.append(
            DispositionEvidenceCitation(
                citation_id=f"offer_revision:{revision.id}",
                source_type="offer_revision",
                source_id=str(revision.id),
                label=f"Offer revision {revision.revision_number}",
                fact=_compact_fact(
                    {
                        "offer_id": revision.offer_id,
                        "buyer_id": revision.buyer_id,
                        "terms": revision.terms_snapshot,
                        "risk": revision.risk_snapshot,
                        "change_reason": revision.change_reason,
                    }
                ),
                status="recorded",
                observed_at=revision.created_at,
            )
        )
    for engagement in engagements[:100]:
        buyer = buyers.get(engagement.buyer_id)
        citations.append(
            DispositionEvidenceCitation(
                citation_id=f"buyer_engagement:{engagement.id}",
                source_type="buyer_engagement",
                source_id=str(engagement.id),
                label=f"Buyer engagement: {buyer.name if buyer else engagement.buyer_id}",
                fact=_compact_fact(
                    {
                        "buyer_id": engagement.buyer_id,
                        "engagement_type": engagement.engagement_type,
                        "status": engagement.status,
                        "scheduled_at": engagement.scheduled_at,
                        "occurred_at": engagement.occurred_at,
                        "notes": engagement.notes,
                    }
                ),
                status=engagement.status,
                observed_at=engagement.occurred_at,
            )
        )
    for reply, communication in reply_rows:
        citations.append(
            DispositionEvidenceCitation(
                citation_id=f"outreach_reply:{reply.id}",
                source_type="outreach_reply",
                source_id=str(reply.id),
                label=f"Buyer {communication.channel} reply",
                fact=_compact_fact(
                    {
                        "buyer_id": reply.buyer_id,
                        "routing_status": reply.routing_status,
                        "routing_confidence": reply.routing_confidence,
                        "existing_classification": reply.reply_classification,
                        "subject": communication.subject,
                        "body": communication.body,
                        "occurred_at": communication.occurred_at,
                    }
                ),
                status=reply.routing_status,
                observed_at=communication.occurred_at,
            )
        )
    for evidence in provider_evidence:
        citations.append(
            DispositionEvidenceCitation(
                citation_id=f"provider_evidence:{evidence.id}",
                source_type="provider_evidence",
                source_id=str(evidence.id),
                label=f"Provider {evidence.event_type} evidence",
                fact=_compact_fact(
                    {
                        "event_type": evidence.event_type,
                        "review_status": evidence.review_status,
                        "buyer_name": evidence.buyer_name,
                        "offer_amount_cents": evidence.offer_amount_cents,
                        "message": evidence.message,
                        "public_metadata": evidence.public_metadata,
                        "evidence_sha256": evidence.evidence_sha256,
                    }
                ),
                status=evidence.review_status,
                observed_at=evidence.occurred_at,
            )
        )
    return citations


def _validate_output(
    case: DispositionCase,
    facts: DispositionFacts,
    output: DispositionCoordinationOutput,
) -> None:
    buyers = facts["buyers"]
    valid_buyer_ids = {str(item.buyer_id) for item in facts["matches"]}
    valid_offer_ids = {str(item.id) for item in facts["offers"]}
    offer_buyer_ids = {str(item.id): str(item.buyer_id) for item in facts["offers"]}
    valid_citation_ids = {item.citation_id for item in facts["citations"]}

    def require_citations(citation_ids: list[str], label: str) -> None:
        if not citation_ids:
            raise ValueError(f"{label} must cite saved Stonegate evidence.")
        unsupported = sorted(set(citation_ids) - valid_citation_ids)
        if unsupported:
            raise ValueError(
                f"{label} cited evidence outside this disposition case: "
                f"{', '.join(unsupported[:3])}."
            )

    def require_buyer_citation(buyer_id: UUID, citation_ids: list[str], label: str) -> None:
        require_citations(citation_ids, label)
        relevant = facts["buyer_citation_ids"].get(buyer_id, set())
        if not relevant.intersection(citation_ids):
            raise ValueError(f"{label} must cite evidence for that exact buyer.")

    def require_offer_citation(offer_id: UUID, citation_ids: list[str], label: str) -> None:
        require_citations(citation_ids, label)
        exact_offer_citation = f"buyer_offer:{offer_id}"
        if exact_offer_citation not in citation_ids:
            raise ValueError(f"{label} must cite the exact recorded buyer offer.")

    require_citations(output.evidence, "The disposition summary")
    for item in output.recommended_buyers:
        if str(item.buyer_id) not in valid_buyer_ids:
            raise ValueError("The model recommended a buyer outside the ranked buyer pool.")
        buyer = buyers.get(item.buyer_id)
        if buyer is None or item.buyer_name.strip().lower() != buyer.name.strip().lower():
            raise ValueError("The model buyer recommendation did not match the CRM record.")
        require_buyer_citation(
            item.buyer_id,
            item.citation_ids,
            f"Buyer recommendation for {item.buyer_name}",
        )
    for offer_item in output.offer_comparison:
        if str(offer_item.offer_id) not in valid_offer_ids:
            raise ValueError("The model compared an offer outside this disposition case.")
        expected_buyer_id = offer_buyer_ids[str(offer_item.offer_id)]
        if offer_item.buyer_id is None or expected_buyer_id != str(offer_item.buyer_id):
            raise ValueError("The model offer comparison did not match its recorded buyer.")
        expected_buyer = buyers.get(offer_item.buyer_id)
        expected_buyer_name = expected_buyer.name if expected_buyer else "Recorded buyer"
        if offer_item.buyer_name.strip().lower() != expected_buyer_name.strip().lower():
            raise ValueError("The model offer comparison mislabeled its recorded buyer.")
        require_offer_citation(
            offer_item.offer_id,
            offer_item.citation_ids,
            f"Offer comparison for {offer_item.offer_id}",
        )
    for draft in output.drafts:
        if draft.buyer_id is not None and str(draft.buyer_id) not in valid_buyer_ids:
            raise ValueError("The model drafted content for a buyer outside the ranked pool.")
        require_citations(draft.citation_ids, f"{draft.draft_type} draft")
        if draft.buyer_id is not None:
            require_buyer_citation(
                draft.buyer_id,
                draft.citation_ids,
                f"{draft.draft_type} draft",
            )
        if not facts["package_citation_ids"].intersection(draft.citation_ids):
            raise ValueError(
                "A disposition draft must cite the case or saved package version."
            )
    for classification in output.reply_classifications:
        valid_sources = (
            facts["valid_reply_source_ids"]
            if classification.source_type == "outreach_reply"
            else facts["valid_provider_source_ids"]
        )
        if classification.source_id not in valid_sources:
            raise ValueError("The model classified a reply outside this disposition case.")
        require_citations(
            classification.citation_ids,
            f"Reply classification for {classification.source_id}",
        )
        expected_citation = f"{classification.source_type}:{classification.source_id}"
        if expected_citation not in classification.citation_ids:
            raise ValueError("A reply classification must cite the reply it classifies.")
    for action in output.next_actions:
        if action.buyer_id is not None and str(action.buyer_id) not in valid_buyer_ids:
            raise ValueError("The model proposed an action for a buyer outside the ranked pool.")
        if action.offer_id is not None and str(action.offer_id) not in valid_offer_ids:
            raise ValueError("The model proposed an action for an offer outside this case.")
        require_citations(action.citation_ids, f"{action.action_type} next action")
        if action.buyer_id is not None:
            require_buyer_citation(
                action.buyer_id,
                action.citation_ids,
                f"{action.action_type} next action",
            )
        if action.offer_id is not None:
            require_offer_citation(
                action.offer_id,
                action.citation_ids,
                f"{action.action_type} next action",
            )
        if (
            action.buyer_id is not None
            and action.offer_id is not None
            and offer_buyer_ids[str(action.offer_id)] != str(action.buyer_id)
        ):
            raise ValueError("The model paired a next action with another buyer's offer.")
    for proposal in output.buyer_update_proposals:
        if str(proposal.buyer_id) not in valid_buyer_ids:
            raise ValueError("The model proposed a change for a buyer outside the ranked pool.")
        require_buyer_citation(
            proposal.buyer_id,
            proposal.citation_ids,
            f"Buyer update proposal for {proposal.buyer_id}",
        )

    external_draft = "\n".join(
        [
            output.buyer_outreach_subject,
            output.buyer_outreach_body,
            *[
                f"{item.title}\n{item.body}"
                for item in output.drafts
                if item.draft_type
                in {"recipient_segment", "email", "sms", "call_brief", "follow_up"}
            ],
        ]
    ).lower()
    seller_name = str(case.package_snapshot.get("seller_name") or "").strip().lower()
    if seller_name and seller_name in external_draft:
        raise ValueError("The buyer outreach draft exposed the seller identity.")
    prohibited_terms = (
        "minimum acceptable",
        "internal floor",
        "stonegate purchase price",
        "seller motivation",
    )
    if any(term in external_draft for term in prohibited_terms):
        raise ValueError("The buyer outreach draft exposed restricted internal information.")
    if case.minimum_acceptable_cents != case.asking_price_cents:
        floor_formats = {
            str(case.minimum_acceptable_cents),
            f"{case.minimum_acceptable_cents / 100:.2f}",
            f"{case.minimum_acceptable_cents / 100:,.0f}",
        }
        if any(value in external_draft for value in floor_formats):
            raise ValueError("The buyer outreach draft exposed Stonegate's internal floor.")


def _idempotency_key(
    case: DispositionCase,
    facts: DispositionFacts,
) -> str:
    return f"disposition-copilot:{case.id}:{facts['evidence_fingerprint'][:24]}"


def _metrics(db: Session, principal: Principal) -> DispositionCopilotMetrics:
    since = datetime.now(UTC) - timedelta(days=30)
    recommendations = list(
        db.scalars(
            select(DispositionCopilotRecommendation).where(
                DispositionCopilotRecommendation.organization_id == principal.organization_id,
                DispositionCopilotRecommendation.generated_at >= since,
            )
        ).all()
    )
    recommendation_ids = [item.id for item in recommendations]
    reviews = (
        list(
            db.scalars(
                select(DispositionCopilotReview).where(
                    DispositionCopilotReview.organization_id == principal.organization_id,
                    DispositionCopilotReview.recommendation_id.in_(recommendation_ids),
                )
            ).all()
        )
        if recommendation_ids
        else []
    )
    decisive_reviews = [item for item in reviews if item.decision != "ignored"]
    reviewed = len(reviews)
    accepted = sum(item.decision == "accepted" for item in decisive_reviews)
    edited = sum(item.decision == "edited" for item in decisive_reviews)
    rejected = sum(item.decision == "rejected" for item in decisive_reviews)
    ignored = sum(item.decision == "ignored" for item in reviews)
    accepted_or_edited = accepted + edited
    run_ids = [
        item.ai_run_log_id
        for item in recommendations
        if item.ai_run_log_id is not None
    ]
    runs = (
        list(
            db.scalars(
                select(AiRunLog).where(
                    AiRunLog.organization_id == principal.organization_id,
                    AiRunLog.id.in_(run_ids),
                )
            ).all()
        )
        if run_ids
        else []
    )
    latencies = [item.latency_ms for item in runs if item.latency_ms is not None]
    input_tokens = [item.input_tokens for item in runs if item.input_tokens is not None]
    output_tokens = [item.output_tokens for item in runs if item.output_tokens is not None]
    costs = [item.cost_microusd for item in runs if item.cost_microusd is not None]
    pilot_recommendations = list(
        db.scalars(
            select(DispositionCopilotRecommendation).where(
                DispositionCopilotRecommendation.organization_id == principal.organization_id
            )
        ).all()
    )
    pilot_recommendation_ids = [item.id for item in pilot_recommendations]
    pilot_reviews = (
        list(
            db.scalars(
                select(DispositionCopilotReview).where(
                    DispositionCopilotReview.organization_id == principal.organization_id,
                    DispositionCopilotReview.recommendation_id.in_(pilot_recommendation_ids),
                )
            ).all()
        )
        if pilot_recommendation_ids
        else []
    )
    recommendations_by_id = {item.id: item for item in pilot_recommendations}
    evaluated: list[
        tuple[
            DispositionCopilotReview,
            DispositionCopilotQualityEvaluation,
            DispositionCopilotRecommendation,
        ]
    ] = []
    for review in pilot_reviews:
        if review.decision == "ignored":
            continue
        raw_evaluation = review.quality_evaluation or {}
        recommendation = recommendations_by_id.get(review.recommendation_id)
        if not raw_evaluation or recommendation is None:
            continue
        try:
            evaluation = DispositionCopilotQualityEvaluation.model_validate(raw_evaluation)
        except ValidationError:
            continue
        evaluated.append((review, evaluation, recommendation))

    package_scores = [
        {"correct": 1.0, "partially_correct": 0.5, "incorrect": 0.0}[
            evaluation.package_fact_correctness
        ]
        for _review, evaluation, _recommendation in evaluated
        if evaluation.package_fact_correctness != "not_applicable"
    ]
    match_scores = [
        {"relevant": 1.0, "partially_relevant": 0.5, "not_relevant": 0.0}[
            evaluation.buyer_match_relevance
        ]
        for _review, evaluation, _recommendation in evaluated
        if evaluation.buyer_match_relevance != "not_applicable"
    ]
    reply_scores = [
        {"correct": 1.0, "partially_correct": 0.5, "incorrect": 0.0}[
            evaluation.reply_classification_accuracy
        ]
        for _review, evaluation, _recommendation in evaluated
        if evaluation.reply_classification_accuracy != "not_applicable"
    ]
    action_scores = [
        1.0 if evaluation.next_action_usefulness in {"useful", "correctable"} else 0.0
        for _review, evaluation, _recommendation in evaluated
        if evaluation.next_action_usefulness != "not_applicable"
    ]
    critical_authority_violations = sum(
        evaluation.critical_authority_violation
        for _review, evaluation, _recommendation in evaluated
    )
    unsupported_citations = sum(
        evaluation.unsupported_or_hallucinated_citation
        for _review, evaluation, _recommendation in evaluated
    )
    evaluated_count = len(evaluated)
    distinct_cases = len(
        {recommendation.disposition_case_id for _review, _evaluation, recommendation in evaluated}
    )
    evaluated_accept_or_correct = sum(
        review.decision in {"accepted", "edited"}
        for review, _evaluation, _recommendation in evaluated
    )
    traced = sum(
        _has_complete_trace(db, recommendation, review=review)
        for review, _evaluation, recommendation in evaluated
    )
    package_rate = _score_basis_points(package_scores)
    match_rate = _score_basis_points(match_scores)
    reply_rate = _score_basis_points(reply_scores)
    action_rate = _score_basis_points(action_scores)
    accept_or_correct_rate = (
        round(evaluated_accept_or_correct / evaluated_count * 10_000)
        if evaluated_count
        else 0
    )
    trace_rate = round(traced / evaluated_count * 10_000) if evaluated_count else 0
    required_scenarios: set[ScenarioGroup] = {
        "normal",
        "incomplete",
        "conflicting",
        "policy_blocked",
        "stale",
        "adversarial",
    }
    observed_scenarios: set[ScenarioGroup] = {
        evaluation.scenario_group for _review, evaluation, _recommendation in evaluated
    }
    missing_scenarios = required_scenarios - observed_scenarios
    blockers: list[str] = []
    if evaluated_count < 50:
        blockers.append("Evaluate at least 50 human-reviewed recommendations.")
    if distinct_cases < 10:
        blockers.append("Evaluate recommendations across at least 10 disposition cases.")
    if missing_scenarios:
        blockers.append(
            "Complete the required pilot scenarios: "
            + ", ".join(sorted(missing_scenarios))
            + "."
        )
    if critical_authority_violations:
        blockers.append("Resolve all critical AI authority violations.")
    if unsupported_citations:
        blockers.append("Resolve all unsupported or hallucinated citations.")
    minimum_domain_sample_size = 10
    if len(package_scores) < minimum_domain_sample_size:
        blockers.append("Evaluate package facts in at least 10 recommendations.")
    elif package_rate < 9_000:
        blockers.append("Reach at least 90% package fact correctness.")
    if len(match_scores) < minimum_domain_sample_size:
        blockers.append("Evaluate buyer-match relevance in at least 10 recommendations.")
    elif match_rate < 8_000:
        blockers.append("Reach at least 80% buyer-match relevance.")
    if len(reply_scores) < minimum_domain_sample_size:
        blockers.append("Evaluate reply classification in at least 10 recommendations.")
    elif reply_rate < 9_000:
        blockers.append("Reach at least 90% reply-classification accuracy.")
    if len(action_scores) < minimum_domain_sample_size:
        blockers.append("Evaluate next actions in at least 10 recommendations.")
    elif action_rate < 8_000:
        blockers.append("Reach at least 80% useful-or-correctable next actions.")
    if accept_or_correct_rate < 8_000:
        blockers.append("Reach at least 80% accepted-or-corrected recommendations.")
    if trace_rate < 10_000:
        blockers.append(
            "Reach 100% model, prompt, evidence, output, cost, and reviewer traceability."
        )
    return DispositionCopilotMetrics(
        generated=len(recommendations),
        reviewed=reviewed,
        accepted=accepted,
        corrected=edited,
        rejected=rejected,
        ignored=ignored,
        accepted_or_corrected_rate_basis_points=(
            round(accepted_or_edited / len(decisive_reviews) * 10_000)
            if decisive_reviews
            else 0
        ),
        correction_rate_basis_points=(
            round(edited / len(decisive_reviews) * 10_000) if decisive_reviews else 0
        ),
        rejection_rate_basis_points=(
            round(rejected / len(decisive_reviews) * 10_000) if decisive_reviews else 0
        ),
        ignore_rate_basis_points=(
            round(ignored / reviewed * 10_000) if reviewed else 0
        ),
        estimated_time_saved_minutes=round(
            sum(item.estimated_time_saved_seconds for item in decisive_reviews) / 60
        ),
        average_latency_ms=_average_int(latencies),
        p95_latency_ms=_percentile_95(latencies),
        average_input_tokens=_average_int(input_tokens),
        average_output_tokens=_average_int(output_tokens),
        average_cost_microusd=_average_int(costs),
        total_cost_microusd=sum(costs),
        pilot_evaluation=DispositionCopilotPilotEvaluation(
            evaluated_recommendations=evaluated_count,
            distinct_cases=distinct_cases,
            observed_scenario_groups=sorted(observed_scenarios),
            missing_scenario_groups=sorted(missing_scenarios),
            critical_authority_violations=critical_authority_violations,
            unsupported_or_hallucinated_citations=unsupported_citations,
            package_fact_correctness_basis_points=package_rate,
            package_fact_sample_size=len(package_scores),
            buyer_match_relevance_basis_points=match_rate,
            buyer_match_sample_size=len(match_scores),
            reply_classification_accuracy_basis_points=reply_rate,
            reply_classification_sample_size=len(reply_scores),
            next_action_useful_or_correctable_basis_points=action_rate,
            next_action_sample_size=len(action_scores),
            accept_or_correct_basis_points=accept_or_correct_rate,
            trace_attribution_basis_points=trace_rate,
            pilot_ready=not blockers,
            blockers=blockers,
        ),
    )


def _recommendation_trace(
    db: Session,
    recommendation: DispositionCopilotRecommendation,
) -> DispositionCopilotAiTrace | None:
    run = None
    if recommendation.ai_run_log_id is not None:
        run = db.scalar(
            select(AiRunLog).where(
                AiRunLog.organization_id == recommendation.organization_id,
                AiRunLog.id == recommendation.ai_run_log_id,
            )
        )
    if run is not None:
        return DispositionCopilotAiTrace(
            model_name=run.model_name,
            prompt_version_id=run.prompt_version_id,
            input_tokens=run.input_tokens,
            output_tokens=run.output_tokens,
            total_tokens=run.total_tokens,
            cost_microusd=run.cost_microusd,
            latency_ms=run.latency_ms,
            started_at=run.started_at,
            completed_at=run.completed_at,
        )
    raw_trace = (recommendation.evidence_snapshot or {}).get("ai_trace")
    if not isinstance(raw_trace, dict):
        return None
    try:
        return DispositionCopilotAiTrace.model_validate(raw_trace)
    except ValidationError:
        return None


def _trace_payload_from_run(run: Any) -> dict[str, object]:
    return {
        "model_name": run.model_name,
        "prompt_version_id": str(run.prompt_version_id) if run.prompt_version_id else None,
        "input_tokens": run.input_tokens,
        "output_tokens": run.output_tokens,
        "total_tokens": run.total_tokens,
        "cost_microusd": run.cost_microusd,
        "latency_ms": run.latency_ms,
        "started_at": run.started_at.isoformat(),
        "completed_at": run.completed_at.isoformat() if run.completed_at else None,
    }


def _has_complete_trace(
    db: Session,
    recommendation: DispositionCopilotRecommendation,
    *,
    review: DispositionCopilotReview | None = None,
) -> bool:
    if recommendation.ai_run_log_id is None:
        return False
    run = db.scalar(
        select(AiRunLog).where(
            AiRunLog.organization_id == recommendation.organization_id,
            AiRunLog.id == recommendation.ai_run_log_id,
        )
    )
    snapshot = recommendation.evidence_snapshot or {}
    try:
        stored_output = json.loads(run.output_summary) if run and run.output_summary else None
    except json.JSONDecodeError:
        stored_output = None
    citations = snapshot.get("citations")
    generation_trace_is_complete = bool(
        run is not None
        and run.model_name
        and run.prompt_version_id is not None
        and run.requested_by_user_id is not None
        and run.input_summary
        and run.output_summary
        and run.cost_microusd is not None
        and snapshot.get("evidence_fingerprint")
        and snapshot.get("output_fingerprint")
        and citations
        and snapshot.get("evidence_fingerprint") == _canonical_hash(citations)
        and snapshot.get("output_fingerprint")
        == _canonical_hash(recommendation.output_payload)
        and stored_output == recommendation.output_payload
    )
    if not generation_trace_is_complete or review is None:
        return generation_trace_is_complete

    review_trace_is_complete = bool(
        review.reviewed_by_user_id
        and review.original_output
        and review.original_output == recommendation.output_payload
        and review.reviewed_at
    )
    if review.decision in {"accepted", "edited"}:
        review_trace_is_complete = review_trace_is_complete and bool(review.final_output)
    if review.decision == "edited":
        evaluation = review.quality_evaluation or {}
        review_trace_is_complete = bool(
            review_trace_is_complete
            and evaluation.get("correction_fingerprint")
            == _canonical_hash(review.final_output)
        )
    return review_trace_is_complete


def _score_basis_points(values: list[float]) -> int:
    return round(sum(values) / len(values) * 10_000) if values else 0


def _average_int(values: list[int]) -> int | None:
    return round(sum(values) / len(values)) if values else None


def _percentile_95(values: list[int]) -> int | None:
    if not values:
        return None
    ordered = sorted(values)
    rank = max(1, (len(ordered) * 95 + 99) // 100)
    return ordered[rank - 1]


def _compact_fact(value: object, *, max_characters: int = 2_000) -> str:
    rendered = json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)
    if len(rendered) <= max_characters:
        return rendered
    digest = hashlib.sha256(rendered.encode()).hexdigest()[:12]
    return f"{rendered[: max_characters - 32]}...[sha256:{digest}]"


def _canonical_hash(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode()
    ).hexdigest()


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
            entity_type="disposition_copilot_recommendation",
            entity_id=entity_id,
            previous_value=None,
            new_value=value,
            reason="Disposition Copilot draft-only pilot",
        )
    )


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


def _proof_freshness_status(
    document: BuyerProofDocument,
    *,
    now: datetime,
) -> str:
    if _proof_is_current_verified(document, now=now):
        return "current_verified"
    if document.expires_at is not None and _aware(document.expires_at) <= now:
        return "expired"
    return "not_current"


def _offer_deposit_status(offer: BuyerOffer, *, now: datetime) -> str:
    if offer.deposit_received_at is not None:
        return "received"
    if offer.deposit_due_at is None:
        return "not_scheduled"
    due_at = _aware(offer.deposit_due_at)
    if due_at < now:
        return "overdue"
    if due_at <= now + timedelta(days=2):
        return "due_within_two_days"
    return "pending"
