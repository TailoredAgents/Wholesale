import hashlib
import json
from datetime import UTC, datetime, timedelta
from typing import Literal, TypedDict
from uuid import UUID

from pydantic import ValidationError
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.auth import Principal
from app.models.foundation import (
    AiAgentDefinition,
    AuditEvent,
    ContractPackage,
    Transaction,
    TransactionChecklistItem,
    TransactionCopilotRecommendation,
    TransactionCopilotReview,
    TransactionDocument,
    TransactionDocumentFact,
    TransactionParty,
)
from app.schemas.ai import AiRuntimeExecuteCreate
from app.schemas.transactions import (
    TransactionCoordinationOutput,
    TransactionCopilotAnalyzeRead,
    TransactionCopilotAnalyzeRequest,
    TransactionCopilotMetrics,
    TransactionCopilotOverview,
    TransactionCopilotRecommendationRead,
    TransactionCopilotReviewRead,
    TransactionCopilotReviewRequest,
    TransactionDeadlineRisk,
)
from app.services.ai_runtime import execute_runtime, get_runtime_overview
from app.services.transactions import scoped_transaction, utc_datetime


class TransactionFacts(TypedDict):
    readiness_score: int
    readiness_band: Literal["ready", "needs_review", "blocked"]
    readiness_gaps: list[str]
    deadline_risks: list[TransactionDeadlineRisk]
    evidence_available: list[str]
    confirmed_document_fact_count: int
    documents: list[TransactionDocument]
    checklist: list[TransactionChecklistItem]
    parties: list[TransactionParty]
    packages: list[ContractPackage]


def get_transaction_copilot_overview(
    db: Session,
    principal: Principal,
    transaction_id: UUID,
) -> TransactionCopilotOverview | None:
    transaction = scoped_transaction(db, principal, transaction_id)
    if transaction is None:
        return None
    facts = _transaction_facts(db, principal, transaction)
    runtime = get_runtime_overview(db, principal)
    statuses = {item.capability_key: item.status for item in runtime.capabilities}
    recommendations = list(
        db.scalars(
            select(TransactionCopilotRecommendation)
            .where(
                TransactionCopilotRecommendation.organization_id
                == principal.organization_id,
                TransactionCopilotRecommendation.transaction_id == transaction.id,
            )
            .order_by(TransactionCopilotRecommendation.generated_at.desc())
        ).all()
    )
    return TransactionCopilotOverview(
        pilot_mode="draft_only",
        runtime_status=runtime.status,
        capability_status=statuses.get("transaction.coordinate", "not_installed"),
        external_actions_blocked=(
            runtime.policy is None or not runtime.policy.external_actions_enabled
        ),
        readiness_score=facts["readiness_score"],
        readiness_band=facts["readiness_band"],
        readiness_gaps=facts["readiness_gaps"],
        deadline_risks=facts["deadline_risks"],
        evidence_available=facts["evidence_available"],
        confirmed_document_fact_count=facts["confirmed_document_fact_count"],
        recommendations=[recommendation_read(item) for item in recommendations],
        metrics=_metrics(db, principal),
    )


def analyze_transaction(
    db: Session,
    principal: Principal,
    transaction_id: UUID,
    payload: TransactionCopilotAnalyzeRequest,
) -> TransactionCopilotAnalyzeRead | None:
    transaction = scoped_transaction(db, principal, transaction_id)
    if transaction is None:
        return None
    facts = _transaction_facts(db, principal, transaction)
    agent = db.scalar(
        select(AiAgentDefinition).where(
            AiAgentDefinition.organization_id == principal.organization_id,
            AiAgentDefinition.key == "transaction_coordinator",
        )
    )
    if agent is None:
        raise ValueError("Install the governed AI agent portfolio first.")
    idempotency_key = payload.idempotency_key or _idempotency_key(transaction, facts)
    existing = db.scalar(
        select(TransactionCopilotRecommendation).where(
            TransactionCopilotRecommendation.organization_id
            == principal.organization_id,
            TransactionCopilotRecommendation.idempotency_key == idempotency_key,
        )
    )
    if existing is not None:
        if existing.ai_run_log_id is None:
            raise ValueError("The existing recommendation has no governed AI trace.")
        return TransactionCopilotAnalyzeRead(
            run_id=existing.ai_run_log_id,
            run_status="needs_review",
            message="The current coordination draft is already available.",
            recommendation=recommendation_read(existing),
        )

    run = execute_runtime(
        db,
        principal,
        AiRuntimeExecuteCreate(
            agent_definition_id=agent.id,
            capability_key="transaction.coordinate",
            idempotency_key=idempotency_key,
            input_payload={
                "pilot_mode": "draft_only",
                "readiness_score": facts["readiness_score"],
                "readiness_gaps": facts["readiness_gaps"],
                "deterministic_deadline_risks": [
                    item.model_dump(mode="json") for item in facts["deadline_risks"]
                ],
                "restrictions": [
                    "Do not edit, interpret, create, or sign legal documents.",
                    "Do not mark checklist items complete or change a deadline.",
                    "Do not contact any party or send a draft.",
                    "Do not mark the transaction funded, closed, or cancelled.",
                    "Use only supplied evidence and return a human-review draft.",
                ],
            },
            lead_id=transaction.lead_id,
            transaction_id=transaction.id,
        ),
    )
    if run.status not in {"needs_review", "completed"} or not run.output_summary:
        return TransactionCopilotAnalyzeRead(
            run_id=run.id,
            run_status=run.status,
            message=run.error_message or "The governed runtime did not produce a draft.",
            recommendation=None,
        )
    try:
        parsed = TransactionCoordinationOutput.model_validate(
            json.loads(run.output_summary)
        )
    except (json.JSONDecodeError, ValidationError) as exc:
        raise ValueError(
            "The model response did not match the Transaction Copilot contract."
        ) from exc

    recommendation = TransactionCopilotRecommendation(
        organization_id=principal.organization_id,
        transaction_id=transaction.id,
        lead_id=transaction.lead_id,
        generated_for_user_id=transaction.coordinator_user_id or principal.user_id,
        ai_run_log_id=run.id,
        idempotency_key=idempotency_key,
        status="draft",
        output_payload=parsed.model_dump(mode="json"),
        evidence_snapshot={
            "readiness_score": facts["readiness_score"],
            "readiness_gaps": facts["readiness_gaps"],
            "deadline_risks": [
                item.model_dump(mode="json") for item in facts["deadline_risks"]
            ],
            "evidence_available": facts["evidence_available"],
            "confirmed_document_fact_count": facts[
                "confirmed_document_fact_count"
            ],
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
        "transaction.copilot_recommendation_generated",
        recommendation.id,
        {
            "transaction_id": str(transaction.id),
            "ai_run_log_id": str(run.id),
            "crm_changes_applied": False,
            "external_actions_executed": False,
        },
    )
    db.commit()
    db.refresh(recommendation)
    return TransactionCopilotAnalyzeRead(
        run_id=run.id,
        run_status=run.status,
        message="Draft transaction guidance generated for human review.",
        recommendation=recommendation_read(recommendation),
    )


def review_recommendation(
    db: Session,
    principal: Principal,
    recommendation_id: UUID,
    payload: TransactionCopilotReviewRequest,
) -> TransactionCopilotReviewRead | None:
    recommendation = db.scalar(
        select(TransactionCopilotRecommendation).where(
            TransactionCopilotRecommendation.organization_id
            == principal.organization_id,
            TransactionCopilotRecommendation.id == recommendation_id,
        )
    )
    if recommendation is None:
        return None
    existing = db.scalar(
        select(TransactionCopilotReview).where(
            TransactionCopilotReview.recommendation_id == recommendation.id
        )
    )
    if existing is not None:
        return review_read(existing)
    if recommendation.status != "draft":
        raise ValueError("Only a draft recommendation can be reviewed.")
    if payload.decision == "edited":
        assert payload.final_output is not None
        try:
            final_output = TransactionCoordinationOutput.model_validate(
                payload.final_output
            ).model_dump(mode="json")
        except ValidationError as exc:
            raise ValueError(
                "The corrected output must preserve the transaction response contract."
            ) from exc
    elif payload.decision == "accepted":
        final_output = recommendation.output_payload
    else:
        final_output = None

    now = datetime.now(UTC)
    review = TransactionCopilotReview(
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
        "transaction.copilot_recommendation_reviewed",
        recommendation.id,
        {
            "decision": payload.decision,
            "transaction_changes_applied": False,
            "external_actions_executed": False,
        },
    )
    db.commit()
    db.refresh(review)
    return review_read(review)


def recommendation_read(
    item: TransactionCopilotRecommendation,
) -> TransactionCopilotRecommendationRead:
    return TransactionCopilotRecommendationRead(
        id=item.id,
        transaction_id=item.transaction_id,
        lead_id=item.lead_id,
        ai_run_log_id=item.ai_run_log_id,
        status=item.status,
        output_payload=item.output_payload,
        confidence_score=item.confidence_score,
        generated_at=item.generated_at,
        reviewed_at=item.reviewed_at,
    )


def review_read(item: TransactionCopilotReview) -> TransactionCopilotReviewRead:
    return TransactionCopilotReviewRead(
        id=item.id,
        recommendation_id=item.recommendation_id,
        decision=item.decision,
        final_output=item.final_output,
        notes=item.notes,
        estimated_time_saved_seconds=item.estimated_time_saved_seconds,
        reviewed_at=item.reviewed_at,
    )


def _transaction_facts(
    db: Session,
    principal: Principal,
    transaction: Transaction,
) -> TransactionFacts:
    documents = list(
        db.scalars(
            select(TransactionDocument).where(
                TransactionDocument.organization_id == principal.organization_id,
                TransactionDocument.transaction_id == transaction.id,
            )
        ).all()
    )
    checklist = list(
        db.scalars(
            select(TransactionChecklistItem).where(
                TransactionChecklistItem.organization_id
                == principal.organization_id,
                TransactionChecklistItem.transaction_id == transaction.id,
            )
        ).all()
    )
    parties = list(
        db.scalars(
            select(TransactionParty).where(
                TransactionParty.organization_id == principal.organization_id,
                TransactionParty.transaction_id == transaction.id,
            )
        ).all()
    )
    packages = list(
        db.scalars(
            select(ContractPackage).where(
                ContractPackage.organization_id == principal.organization_id,
                ContractPackage.transaction_id == transaction.id,
            )
        ).all()
    )
    confirmed_fact_count = int(
        db.scalar(
            select(func.count(TransactionDocumentFact.id)).where(
                TransactionDocumentFact.organization_id
                == principal.organization_id,
                TransactionDocumentFact.transaction_id == transaction.id,
                TransactionDocumentFact.status == "confirmed",
            )
        )
        or 0
    )
    risks = _deadline_risks(transaction, checklist)
    gaps: list[str] = []
    evidence: list[str] = []
    score = 100
    if transaction.coordinator_user_id is None:
        gaps.append("Assign a transaction coordinator.")
        score -= 10
    if transaction.closing_date is None:
        gaps.append("Confirm the closing date.")
        score -= 15
    if not transaction.title_company:
        gaps.append("Record the closing attorney or title company.")
        score -= 10
    if not any(
        item.party_type in {"closing_attorney", "title_company"} for item in parties
    ):
        gaps.append("Add the closing attorney or title contact.")
        score -= 10
    executed = [item for item in packages if item.status == "executed"]
    if executed:
        evidence.append("Executed contract package")
    else:
        gaps.append("Attach and confirm the executed purchase agreement.")
        score -= 20
    required_open = [
        item
        for item in checklist
        if item.is_required and item.status not in {"complete", "not_applicable"}
    ]
    if required_open:
        gaps.append(f"Resolve {len(required_open)} required checklist item(s).")
        score -= min(25, len(required_open) * 5)
    if documents:
        evidence.append(f"{len(documents)} private transaction document(s)")
    else:
        gaps.append("Upload the transaction evidence package.")
        score -= 10
    if confirmed_fact_count:
        evidence.append(
            f"{confirmed_fact_count} human-confirmed document fact(s)"
        )
    else:
        gaps.append("Confirm material facts with document page references.")
        score -= 5
    if parties:
        evidence.append(f"{len(parties)} closing party record(s)")
    completed = sum(
        item.status in {"complete", "not_applicable"} for item in checklist
    )
    if checklist:
        evidence.append(f"{completed}/{len(checklist)} checklist items complete")
    critical_count = sum(item.severity == "critical" for item in risks)
    score -= min(30, critical_count * 10)
    score = max(0, score)
    band: Literal["ready", "needs_review", "blocked"] = (
        "ready" if score >= 80 else "needs_review" if score >= 50 else "blocked"
    )
    return {
        "readiness_score": score,
        "readiness_band": band,
        "readiness_gaps": gaps,
        "deadline_risks": risks,
        "evidence_available": evidence,
        "confirmed_document_fact_count": confirmed_fact_count,
        "documents": documents,
        "checklist": checklist,
        "parties": parties,
        "packages": packages,
    }


def _deadline_risks(
    transaction: Transaction,
    checklist: list[TransactionChecklistItem],
) -> list[TransactionDeadlineRisk]:
    now = datetime.now(UTC)
    deadlines: list[tuple[str, datetime, str]] = []
    for label, value in (
        ("Earnest money", transaction.earnest_money_due_at),
        ("Due diligence", transaction.due_diligence_deadline),
        ("Assignment", transaction.assignment_deadline),
        ("Closing", transaction.closing_date),
    ):
        if value is not None:
            deadlines.append((label, utc_datetime(value), f"Transaction {label.lower()} date"))
    for item in checklist:
        if item.due_at and item.status not in {"complete", "not_applicable"}:
            deadlines.append(
                (
                    item.title,
                    utc_datetime(item.due_at),
                    f"Open checklist item {item.id}",
                )
            )
    risks: list[TransactionDeadlineRisk] = []
    for deadline_item, due_at, evidence in deadlines:
        remaining = due_at - now
        severity: Literal["info", "warning", "critical"]
        if remaining < timedelta(0):
            severity = "critical"
            reason = "Deadline is overdue."
        elif remaining <= timedelta(days=3):
            severity = "warning"
            reason = "Deadline is due within three days."
        elif remaining <= timedelta(days=7):
            severity = "info"
            reason = "Deadline is due within seven days."
        else:
            continue
        risks.append(
            TransactionDeadlineRisk(
                item=deadline_item,
                due_at=due_at,
                severity=severity,
                reason=reason,
                evidence=[evidence],
            )
        )
    severity_order = {"critical": 0, "warning": 1, "info": 2}
    return sorted(risks, key=lambda item: (severity_order[item.severity], item.due_at))


def _idempotency_key(
    transaction: Transaction,
    facts: TransactionFacts,
) -> str:
    fingerprint = {
        "transaction_id": str(transaction.id),
        "transaction_updated_at": transaction.updated_at.isoformat(),
        "documents": [
            (str(item.id), item.updated_at.isoformat()) for item in facts["documents"]
        ],
        "checklist": [
            (str(item.id), item.updated_at.isoformat()) for item in facts["checklist"]
        ],
        "parties": [
            (str(item.id), item.updated_at.isoformat()) for item in facts["parties"]
        ],
        "packages": [
            (str(item.id), item.updated_at.isoformat()) for item in facts["packages"]
        ],
        "confirmed_document_fact_count": facts["confirmed_document_fact_count"],
    }
    digest = hashlib.sha256(
        json.dumps(fingerprint, sort_keys=True).encode()
    ).hexdigest()[:24]
    return f"transaction-copilot:{transaction.id}:{digest}"


def _metrics(db: Session, principal: Principal) -> TransactionCopilotMetrics:
    since = datetime.now(UTC) - timedelta(days=30)
    recommendations = list(
        db.scalars(
            select(TransactionCopilotRecommendation).where(
                TransactionCopilotRecommendation.organization_id
                == principal.organization_id,
                TransactionCopilotRecommendation.generated_at >= since,
            )
        ).all()
    )
    ids = [item.id for item in recommendations]
    reviews = (
        list(
            db.scalars(
                select(TransactionCopilotReview).where(
                    TransactionCopilotReview.organization_id
                    == principal.organization_id,
                    TransactionCopilotReview.recommendation_id.in_(ids),
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
    return TransactionCopilotMetrics(
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
            entity_type="transaction_copilot_recommendation",
            entity_id=entity_id,
            previous_value=None,
            new_value=value,
            reason="Transaction Copilot draft-only pilot",
        )
    )
