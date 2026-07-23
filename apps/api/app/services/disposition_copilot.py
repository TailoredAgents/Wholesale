import hashlib
import json
from datetime import UTC, datetime, timedelta
from typing import Literal, TypedDict
from uuid import UUID

from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.auth import Principal
from app.models.foundation import (
    AiAgentDefinition,
    AuditEvent,
    Buyer,
    BuyerEngagement,
    BuyerOffer,
    DispositionCase,
    DispositionCopilotRecommendation,
    DispositionCopilotReview,
    DispositionMatch,
)
from app.schemas.ai import AiRuntimeExecuteCreate
from app.schemas.dispositions import (
    DispositionCoordinationOutput,
    DispositionCopilotAnalyzeRead,
    DispositionCopilotAnalyzeRequest,
    DispositionCopilotMetrics,
    DispositionCopilotOverview,
    DispositionCopilotRecommendationRead,
    DispositionCopilotReviewRead,
    DispositionCopilotReviewRequest,
    DispositionRiskAlert,
)
from app.services.ai_runtime import execute_runtime, get_runtime_overview
from app.services.dispositions import scoped_case


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


def get_disposition_copilot_overview(
    db: Session,
    principal: Principal,
    case_id: UUID,
) -> DispositionCopilotOverview | None:
    case = scoped_case(db, principal, case_id)
    if case is None:
        return None
    facts = _disposition_facts(db, principal, case)
    runtime = get_runtime_overview(db, principal)
    statuses = {item.capability_key: item.status for item in runtime.capabilities}
    recommendations = list(
        db.scalars(
            select(DispositionCopilotRecommendation)
            .where(
                DispositionCopilotRecommendation.organization_id
                == principal.organization_id,
                DispositionCopilotRecommendation.disposition_case_id == case.id,
            )
            .order_by(DispositionCopilotRecommendation.generated_at.desc())
        ).all()
    )
    return DispositionCopilotOverview(
        pilot_mode="draft_only",
        runtime_status=runtime.status,
        capability_status=statuses.get("disposition.match", "not_installed"),
        external_actions_blocked=(
            runtime.policy is None or not runtime.policy.external_actions_enabled
        ),
        readiness_score=facts["readiness_score"],
        readiness_band=facts["readiness_band"],
        readiness_gaps=facts["readiness_gaps"],
        risk_alerts=facts["risk_alerts"],
        qualified_buyer_count=facts["qualified_buyer_count"],
        verified_buyer_count=facts["verified_buyer_count"],
        offer_count=facts["offer_count"],
        backup_coverage=facts["backup_coverage"],
        recommendations=[recommendation_read(item) for item in recommendations],
        metrics=_metrics(db, principal),
    )


def analyze_disposition(
    db: Session,
    principal: Principal,
    case_id: UUID,
    payload: DispositionCopilotAnalyzeRequest,
) -> DispositionCopilotAnalyzeRead | None:
    case = scoped_case(db, principal, case_id)
    if case is None:
        return None
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
            DispositionCopilotRecommendation.organization_id
            == principal.organization_id,
            DispositionCopilotRecommendation.idempotency_key == idempotency_key,
        )
    )
    if existing is not None:
        if existing.ai_run_log_id is None:
            raise ValueError("The existing recommendation has no governed AI trace.")
        return DispositionCopilotAnalyzeRead(
            run_id=existing.ai_run_log_id,
            run_status="needs_review",
            message="The current disposition draft is already available.",
            recommendation=recommendation_read(existing),
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
                "readiness_score": facts["readiness_score"],
                "readiness_gaps": facts["readiness_gaps"],
                "deterministic_risk_alerts": [
                    item.model_dump(mode="json") for item in facts["risk_alerts"]
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
        parsed = DispositionCoordinationOutput.model_validate(
            json.loads(run.output_summary)
        )
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
        generated_for_user_id=case.owner_user_id,
        ai_run_log_id=run.id,
        idempotency_key=idempotency_key,
        status="draft",
        output_payload=parsed.model_dump(mode="json"),
        evidence_snapshot={
            "readiness_score": facts["readiness_score"],
            "readiness_gaps": facts["readiness_gaps"],
            "risk_alerts": [
                item.model_dump(mode="json") for item in facts["risk_alerts"]
            ],
            "qualified_buyer_count": facts["qualified_buyer_count"],
            "verified_buyer_count": facts["verified_buyer_count"],
            "offer_count": facts["offer_count"],
            "backup_coverage": facts["backup_coverage"],
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
        recommendation=recommendation_read(recommendation),
    )


def review_recommendation(
    db: Session,
    principal: Principal,
    recommendation_id: UUID,
    payload: DispositionCopilotReviewRequest,
) -> DispositionCopilotReviewRead | None:
    recommendation = db.scalar(
        select(DispositionCopilotRecommendation).where(
            DispositionCopilotRecommendation.organization_id
            == principal.organization_id,
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
        return review_read(existing)
    if recommendation.status != "draft":
        raise ValueError("Only a draft recommendation can be reviewed.")

    case = scoped_case(db, principal, recommendation.disposition_case_id)
    if case is None:
        raise ValueError("Disposition case not found.")
    facts = _disposition_facts(db, principal, case)
    if payload.decision == "edited":
        assert payload.final_output is not None
        try:
            parsed = DispositionCoordinationOutput.model_validate(
                payload.final_output
            )
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
    review = DispositionCopilotReview(
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
        "disposition.copilot_recommendation_reviewed",
        recommendation.id,
        {
            "decision": payload.decision,
            "buyer_changes_applied": False,
            "campaign_released": False,
            "external_actions_executed": False,
        },
    )
    db.commit()
    db.refresh(review)
    return review_read(review)


def recommendation_read(
    item: DispositionCopilotRecommendation,
) -> DispositionCopilotRecommendationRead:
    return DispositionCopilotRecommendationRead(
        id=item.id,
        disposition_case_id=item.disposition_case_id,
        transaction_id=item.transaction_id,
        lead_id=item.lead_id,
        ai_run_log_id=item.ai_run_log_id,
        status=item.status,
        output_payload=DispositionCoordinationOutput.model_validate(
            item.output_payload
        ),
        confidence_score=item.confidence_score,
        generated_at=item.generated_at,
        reviewed_at=item.reviewed_at,
    )


def review_read(item: DispositionCopilotReview) -> DispositionCopilotReviewRead:
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
        reviewed_at=item.reviewed_at,
    )


def _disposition_facts(
    db: Session,
    principal: Principal,
    case: DispositionCase,
) -> DispositionFacts:
    matches = list(
        db.scalars(
            select(DispositionMatch)
            .where(
                DispositionMatch.organization_id == principal.organization_id,
                DispositionMatch.disposition_case_id == case.id,
            )
            .order_by(DispositionMatch.rank)
        ).all()
    )
    buyer_ids = {item.buyer_id for item in matches}
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

    gaps: list[str] = []
    risks: list[DispositionRiskAlert] = []
    score = 100
    if case.package_status != "approved":
        gaps.append("Approve the fact-checked investor package.")
        score -= 35
    for field, label in (
        ("property_address", "property address"),
        ("property_type", "property type"),
    ):
        if not case.package_snapshot.get(field):
            gaps.append(f"Confirm the {label}.")
            score -= 10
    if not matches:
        gaps.append("Generate the deterministic buyer ranking.")
        score -= 20
    qualified = [
        item for item in matches if item.qualification_status == "qualified"
    ]
    if matches and not qualified:
        gaps.append("Resolve buyer qualification and proof-of-funds gaps.")
        score -= 20
    verified = [
        item
        for item in qualified
        if item.buyer_id in buyers
        and buyers[item.buyer_id].proof_of_funds_status == "received"
        and (
            buyers[item.buyer_id].proof_of_funds_expires_at is None
            or _aware(buyers[item.buyer_id].proof_of_funds_expires_at)
            >= datetime.now(UTC)
        )
    ]
    if qualified and not verified:
        gaps.append("Verify current proof of funds for at least one qualified buyer.")
        score -= 15
    if case.status in {"marketed", "offers_received"} and not offers:
        gaps.append("Record buyer responses and offers.")
        score -= 10

    now = datetime.now(UTC)
    for match in matches:
        buyer = buyers.get(match.buyer_id)
        if buyer is None:
            continue
        if buyer.proof_of_funds_expires_at and _aware(
            buyer.proof_of_funds_expires_at
        ) < now:
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
        if offer.amount_cents < case.minimum_acceptable_cents:
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
    return {
        "readiness_score": score,
        "readiness_band": band,
        "readiness_gaps": gaps,
        "risk_alerts": sorted(
            risks, key=lambda item: severity_order[item.severity]
        ),
        "qualified_buyer_count": len(qualified),
        "verified_buyer_count": len(verified),
        "offer_count": len(offers),
        "backup_coverage": backup_coverage,
        "matches": matches,
        "offers": offers,
        "engagements": engagements,
        "buyers": buyers,
    }


def _validate_output(
    case: DispositionCase,
    facts: DispositionFacts,
    output: DispositionCoordinationOutput,
) -> None:
    buyers = facts["buyers"]
    valid_buyer_ids = {str(item.buyer_id) for item in facts["matches"]}
    valid_offer_ids = {str(item.id) for item in facts["offers"]}
    for item in output.recommended_buyers:
        if str(item.buyer_id) not in valid_buyer_ids:
            raise ValueError("The model recommended a buyer outside the ranked buyer pool.")
        buyer = buyers.get(item.buyer_id)
        if buyer is None or item.buyer_name.strip().lower() != buyer.name.strip().lower():
            raise ValueError("The model buyer recommendation did not match the CRM record.")
    for item in output.offer_comparison:
        if str(item.offer_id) not in valid_offer_ids:
            raise ValueError("The model compared an offer outside this disposition case.")

    external_draft = (
        f"{output.buyer_outreach_subject}\n{output.buyer_outreach_body}".lower()
    )
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
    fingerprint = {
        "case_id": str(case.id),
        "case_updated_at": case.updated_at.isoformat(),
        "matches": [
            (str(item.id), item.updated_at.isoformat()) for item in facts["matches"]
        ],
        "offers": [
            (str(item.id), item.updated_at.isoformat()) for item in facts["offers"]
        ],
        "engagements": [
            (str(item.id), item.updated_at.isoformat())
            for item in facts["engagements"]
        ],
    }
    digest = hashlib.sha256(
        json.dumps(fingerprint, sort_keys=True).encode()
    ).hexdigest()[:24]
    return f"disposition-copilot:{case.id}:{digest}"


def _metrics(db: Session, principal: Principal) -> DispositionCopilotMetrics:
    since = datetime.now(UTC) - timedelta(days=30)
    recommendations = list(
        db.scalars(
            select(DispositionCopilotRecommendation).where(
                DispositionCopilotRecommendation.organization_id
                == principal.organization_id,
                DispositionCopilotRecommendation.generated_at >= since,
            )
        ).all()
    )
    recommendation_ids = [item.id for item in recommendations]
    reviews = (
        list(
            db.scalars(
                select(DispositionCopilotReview).where(
                    DispositionCopilotReview.organization_id
                    == principal.organization_id,
                    DispositionCopilotReview.recommendation_id.in_(
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
    return DispositionCopilotMetrics(
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
            entity_type="disposition_copilot_recommendation",
            entity_id=entity_id,
            previous_value=None,
            new_value=value,
            reason="Disposition Copilot draft-only pilot",
        )
    )


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)
