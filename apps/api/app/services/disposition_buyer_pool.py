from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from typing import Any, Literal, cast
from uuid import UUID

from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.auth import Principal
from app.models.foundation import (
    AuditEvent,
    Buyer,
    BuyerDiscoveryCandidate,
    BuyerDiscoveryRun,
    BuyerProofDocument,
    BuyerSourceLink,
    DispositionBuyerPoolCandidate,
    DispositionBuyerPoolEntry,
    DispositionBuyerPoolRun,
    DispositionCase,
    Lead,
    Property,
)
from app.schemas.buyers import BuyerCreate
from app.schemas.dispositions import (
    BuyerPoolConversionRequest,
    BuyerPoolDecision,
    BuyerPoolDecisionUpdate,
    BuyerPoolEntryRead,
    BuyerPoolLifecycleStage,
    BuyerPoolRead,
    BuyerPoolRunRead,
    BuyerPoolSourceFilter,
)
from app.services.buyers import (
    create_buyer,
    get_current_buy_box_version,
    normalize_company,
    normalize_email,
    normalize_phone,
    normalize_source_key,
)

MATCHER_VERSION = "stonegate_buyer_pool_v1"
SCORE_POLICY_VERSION = "buyer_pool_score_v1"
REVIEWABLE_PROOF_SCAN_STATUSES = {"clean", "not_configured"}


def generate_buyer_pool_run(
    db: Session,
    principal: Principal,
    case_id: UUID,
    *,
    locked_case: DispositionCase | None = None,
    commit: bool = True,
) -> DispositionBuyerPoolRun:
    case = locked_case or db.scalar(
        select(DispositionCase).where(
            DispositionCase.id == case_id,
            DispositionCase.organization_id == principal.organization_id,
        )
    )
    if case is None:
        raise ValueError("Disposition case not found.")
    if case.package_status != "approved":
        raise ValueError("Approve the deal package before matching buyers.")

    lead = db.get(Lead, case.lead_id)
    property_record = db.get(Property, case.property_id)
    if lead is None or property_record is None:
        raise ValueError("The disposition property is unavailable.")
    asset_class = (lead.asset_class or "house").strip().lower()
    if asset_class not in {"house", "land"}:
        raise ValueError(f"Unsupported disposition asset class: {asset_class}.")

    latest_version = db.scalar(
        select(func.max(DispositionBuyerPoolRun.version_number)).where(
            DispositionBuyerPoolRun.organization_id == principal.organization_id,
            DispositionBuyerPoolRun.disposition_case_id == case.id,
        )
    )
    version_number = int(latest_version or 0) + 1
    now = datetime.now(UTC)
    subject_snapshot = {
        "case_id": str(case.id),
        "lead_id": str(case.lead_id),
        "asset_class": asset_class,
        "strategy": case.strategy,
        "asking_price_cents": case.asking_price_cents,
        "minimum_acceptable_cents": case.minimum_acceptable_cents,
        "property": {
            "id": str(property_record.id),
            "street_address": property_record.street_address,
            "city": property_record.city,
            "state": property_record.state,
            "postal_code": property_record.postal_code,
            "county": property_record.county,
            "property_type": property_record.property_type,
        },
    }
    fingerprint = _fingerprint(subject_snapshot)
    run = DispositionBuyerPoolRun(
        organization_id=principal.organization_id,
        disposition_case_id=case.id,
        generated_by_user_id=principal.user_id,
        version_number=version_number,
        asset_class=asset_class,
        matcher_version=MATCHER_VERSION,
        score_policy_version=SCORE_POLICY_VERSION,
        status="completed",
        input_snapshot=subject_snapshot,
        input_fingerprint=fingerprint,
        source_counts={"internal": 0, "external": 0, "merged_overlap": 0},
        started_at=now,
        completed_at=now,
    )
    db.add(run)
    db.flush()

    buyers = list(
        db.scalars(
            select(Buyer).where(
                Buyer.organization_id == principal.organization_id,
                Buyer.archived_at.is_(None),
            )
        ).all()
    )
    buyer_maps = _buyer_identity_maps(db, principal, buyers)
    external_candidates = _latest_external_candidates(db, principal, case.id)
    external_by_buyer: dict[UUID, list[BuyerDiscoveryCandidate]] = {}
    standalone_external: list[
        tuple[BuyerDiscoveryCandidate, str, list[UUID], Buyer | None]
    ] = []
    for discovery_candidate in external_candidates:
        overlap_status, buyer_ids, possible = _resolve_overlap(
            discovery_candidate,
            buyer_maps,
        )
        if overlap_status == "exact" and len(buyer_ids) == 1:
            external_by_buyer.setdefault(buyer_ids[0], []).append(discovery_candidate)
        else:
            standalone_external.append(
                (discovery_candidate, overlap_status, buyer_ids, possible)
            )

    evaluations: list[tuple[DispositionBuyerPoolCandidate, dict[str, Any]]] = []
    for buyer in buyers:
        candidate = _upsert_internal_candidate(
            db,
            principal,
            case,
            buyer,
            external_by_buyer.get(buyer.id, []),
        )
        evaluation = _evaluate_internal_buyer(
            db,
            principal,
            case,
            property_record,
            asset_class,
            buyer,
            external_by_buyer.get(buyer.id, []),
            now=now,
        )
        evaluations.append((candidate, evaluation))

    for discovery_candidate, overlap_status, buyer_ids, possible in standalone_external:
        candidate = _upsert_external_candidate(
            db,
            principal,
            case,
            discovery_candidate,
            overlap_status=overlap_status,
            buyer_ids=buyer_ids,
            possible_buyer=possible,
        )
        evaluation = _evaluate_external_candidate(
            case,
            property_record,
            asset_class,
            discovery_candidate,
            overlap_status=overlap_status,
            possible_buyer_ids=buyer_ids,
            now=now,
        )
        evaluations.append((candidate, evaluation))

    evaluations.sort(
        key=lambda item: (
            int(item[1]["score_basis_points"]),
            item[0].display_name.casefold(),
        ),
        reverse=True,
    )
    source_counts = {"internal": 0, "external": 0, "merged_overlap": 0}
    for rank, (candidate, evaluation) in enumerate(evaluations, 1):
        source_counts[candidate.source_type] += 1
        source_counts["merged_overlap"] += int(
            bool(evaluation["evidence_snapshot"].get("merged_provider_candidates"))
        )
        db.add(
            DispositionBuyerPoolEntry(
                organization_id=principal.organization_id,
                buyer_pool_run_id=run.id,
                buyer_pool_candidate_id=candidate.id,
                buyer_id=candidate.buyer_id,
                buy_box_version_id=evaluation["buy_box_version_id"],
                proof_document_id=evaluation["proof_document_id"],
                source_type=candidate.source_type,
                score_basis_points=evaluation["score_basis_points"],
                rank=rank,
                eligibility_status=evaluation["eligibility_status"],
                score_components=evaluation["score_components"],
                score_explanation=evaluation["score_explanation"],
                supporting_evidence=evaluation["supporting_evidence"],
                conflicting_evidence=evaluation["conflicting_evidence"],
                disqualifying_reasons=evaluation["disqualifying_reasons"],
                evidence_snapshot=evaluation["evidence_snapshot"],
                criteria_snapshot=evaluation["criteria_snapshot"],
                source_fingerprint=_fingerprint(evaluation["evidence_snapshot"]),
            )
        )
    run.source_counts = source_counts
    db.add(
        AuditEvent(
            organization_id=principal.organization_id,
            actor_user_id=principal.user_id,
            actor_type="user",
            action="disposition.buyer_pool.generated",
            entity_type="disposition_case",
            entity_id=case.id,
            previous_value=None,
            new_value={
                "run_id": str(run.id),
                "version_number": version_number,
                "matcher_version": MATCHER_VERSION,
                "score_policy_version": SCORE_POLICY_VERSION,
                "entry_count": len(evaluations),
                "source_counts": source_counts,
            },
            reason="User refreshed the explainable deal buyer pool",
        )
    )
    if commit:
        db.commit()
        db.refresh(run)
    return run


def read_buyer_pool(
    db: Session,
    principal: Principal,
    case_id: UUID,
    *,
    source: BuyerPoolSourceFilter = "all",
    stage: str = "all",
    search: str = "",
    page: int = 1,
    page_size: int = 50,
) -> BuyerPoolRead | None:
    case = db.scalar(
        select(DispositionCase).where(
            DispositionCase.id == case_id,
            DispositionCase.organization_id == principal.organization_id,
        )
    )
    if case is None:
        return None
    run = db.scalar(
        select(DispositionBuyerPoolRun)
        .where(
            DispositionBuyerPoolRun.organization_id == principal.organization_id,
            DispositionBuyerPoolRun.disposition_case_id == case.id,
            DispositionBuyerPoolRun.status == "completed",
        )
        .order_by(
            DispositionBuyerPoolRun.version_number.desc(),
            DispositionBuyerPoolRun.created_at.desc(),
        )
        .limit(1)
    )
    if run is None:
        return BuyerPoolRead(
            case_id=case.id,
            run=None,
            total=0,
            page=page,
            page_size=page_size,
            entries=[],
        )

    rows = list(
        db.execute(
            select(DispositionBuyerPoolEntry, DispositionBuyerPoolCandidate)
            .join(
                DispositionBuyerPoolCandidate,
                DispositionBuyerPoolCandidate.id
                == DispositionBuyerPoolEntry.buyer_pool_candidate_id,
            )
            .where(
                DispositionBuyerPoolEntry.organization_id == principal.organization_id,
                DispositionBuyerPoolEntry.buyer_pool_run_id == run.id,
            )
            .order_by(DispositionBuyerPoolEntry.rank.asc())
        ).all()
    )
    buyer_ids = {
        buyer_id
        for _, candidate in rows
        for buyer_id in (candidate.buyer_id, candidate.possible_buyer_id)
        if buyer_id is not None
    }
    buyers = {
        buyer.id: buyer
        for buyer in db.scalars(
            select(Buyer).where(
                Buyer.organization_id == principal.organization_id,
                Buyer.id.in_(buyer_ids),
            )
        ).all()
    } if buyer_ids else {}

    normalized_search = " ".join(search.casefold().split())
    filtered: list[tuple[DispositionBuyerPoolEntry, DispositionBuyerPoolCandidate, str]] = []
    for entry, candidate in rows:
        source_type = _source_category(candidate, buyers.get(candidate.buyer_id), principal)
        if source != "all" and source_type != source:
            continue
        if stage == "eligible":
            if entry.eligibility_status != "eligible":
                continue
        elif stage != "all" and candidate.lifecycle_stage != stage:
            continue
        if normalized_search and normalized_search not in " ".join(
            value.casefold()
            for value in (
                candidate.display_name,
                candidate.company_name or "",
                candidate.email or "",
                candidate.phone or "",
                candidate.provider or "",
            )
        ):
            continue
        filtered.append((entry, candidate, source_type))

    total = len(filtered)
    start = (page - 1) * page_size
    selected = filtered[start : start + page_size]
    return BuyerPoolRead(
        case_id=case.id,
        run=_run_read(run),
        total=total,
        page=page,
        page_size=page_size,
        entries=[
            _entry_read(
                db,
                principal,
                entry,
                candidate,
                source_type,
                buyers.get(candidate.buyer_id) if candidate.buyer_id else None,
                (
                    buyers.get(candidate.possible_buyer_id)
                    if candidate.possible_buyer_id
                    else None
                ),
            )
            for entry, candidate, source_type in selected
        ],
    )


def read_run_history(
    db: Session,
    principal: Principal,
    case_id: UUID,
) -> list[BuyerPoolRunRead] | None:
    case_exists = db.scalar(
        select(DispositionCase.id).where(
            DispositionCase.id == case_id,
            DispositionCase.organization_id == principal.organization_id,
        )
    )
    if case_exists is None:
        return None
    runs = db.scalars(
        select(DispositionBuyerPoolRun)
        .where(
            DispositionBuyerPoolRun.organization_id == principal.organization_id,
            DispositionBuyerPoolRun.disposition_case_id == case_id,
        )
        .order_by(
            DispositionBuyerPoolRun.version_number.desc(),
            DispositionBuyerPoolRun.created_at.desc(),
        )
    ).all()
    return [_run_read(run) for run in runs]


def update_candidate_decision(
    db: Session,
    principal: Principal,
    case_id: UUID,
    candidate_id: UUID,
    payload: BuyerPoolDecisionUpdate,
) -> None:
    candidate = db.scalar(
        select(DispositionBuyerPoolCandidate)
        .where(
            DispositionBuyerPoolCandidate.id == candidate_id,
            DispositionBuyerPoolCandidate.organization_id == principal.organization_id,
            DispositionBuyerPoolCandidate.disposition_case_id == case_id,
        )
        .with_for_update()
    )
    if candidate is None:
        raise ValueError("Buyer-pool candidate not found.")
    _require_latest_run_candidate(db, principal, case_id, candidate.id)
    if candidate.lock_version != payload.expected_version:
        raise ValueError(
            "This buyer-pool decision changed in another session. Refresh and try again."
        )
    if payload.decision_status == "passed" and not payload.reason:
        raise ValueError("Passing on a deal candidate requires a reason.")
    if (
        candidate.decision_status != "undecided"
        and candidate.decision_status != payload.decision_status
        and not payload.reason
    ):
        raise ValueError("Changing an existing buyer decision requires a reason.")

    lifecycle_stage = {
        "undecided": "discovered",
        "shortlisted": "shortlisted",
        "passed": "pass",
    }[payload.decision_status]
    if payload.lifecycle_stage is not None and payload.lifecycle_stage != lifecycle_stage:
        raise ValueError(
            "The buyer-pool lifecycle stage must match the selected decision."
        )

    previous = {
        "decision_status": candidate.decision_status,
        "lifecycle_stage": candidate.lifecycle_stage,
        "reason": candidate.decision_reason,
        "lock_version": candidate.lock_version,
    }
    candidate.decision_status = payload.decision_status
    candidate.lifecycle_stage = lifecycle_stage
    candidate.decision_reason = payload.reason
    candidate.lock_version += 1
    candidate.decision_updated_by_user_id = principal.user_id
    candidate.decision_updated_at = datetime.now(UTC)
    db.add(
        AuditEvent(
            organization_id=principal.organization_id,
            actor_user_id=principal.user_id,
            actor_type="user",
            action="disposition.buyer_pool.decision",
            entity_type="disposition_buyer_pool_candidate",
            entity_id=candidate.id,
            previous_value=previous,
            new_value={
                "decision_status": candidate.decision_status,
                "lifecycle_stage": candidate.lifecycle_stage,
                "reason": candidate.decision_reason,
                "lock_version": candidate.lock_version,
                "outreach_sent": False,
            },
            reason=payload.reason or "Buyer-pool shortlist decision",
        )
    )
    db.commit()


def convert_external_candidate(
    db: Session,
    principal: Principal,
    case_id: UUID,
    candidate_id: UUID,
    payload: BuyerPoolConversionRequest,
) -> UUID | None:
    candidate = db.scalar(
        select(DispositionBuyerPoolCandidate)
        .where(
            DispositionBuyerPoolCandidate.id == candidate_id,
            DispositionBuyerPoolCandidate.organization_id == principal.organization_id,
            DispositionBuyerPoolCandidate.disposition_case_id == case_id,
        )
        .with_for_update()
    )
    if candidate is None:
        raise ValueError("Buyer-pool candidate not found.")
    _require_latest_run_candidate(db, principal, case_id, candidate.id)
    if candidate.lock_version != payload.expected_version:
        raise ValueError(
            "This buyer-pool candidate changed in another session. Refresh and try again."
        )
    if candidate.source_type != "external" and candidate.buyer_id is not None:
        raise ValueError("This candidate is already linked to the Stonegate Buyer Network.")
    if payload.decision == "reject":
        candidate.decision_status = "passed"
        candidate.lifecycle_stage = "pass"
        candidate.decision_reason = payload.reason
        candidate.lock_version += 1
        candidate.decision_updated_by_user_id = principal.user_id
        candidate.decision_updated_at = datetime.now(UTC)
        _conversion_audit(db, principal, candidate, payload, None)
        db.commit()
        return None

    provider = candidate.provider or "external_discovery"
    external_key = candidate.external_key or str(candidate.id)
    source_link = db.scalar(
        select(BuyerSourceLink).where(
            BuyerSourceLink.organization_id == principal.organization_id,
            BuyerSourceLink.provider == provider,
            BuyerSourceLink.external_key == external_key,
        )
    )
    if source_link is not None:
        if payload.decision == "create_new":
            raise ValueError(
                "This provider identity is already linked to a Stonegate buyer. "
                "Review and link the existing buyer instead."
            )
        if payload.existing_buyer_id != source_link.buyer_id:
            raise ValueError("This provider identity is already linked to another buyer.")

    if payload.decision == "link_existing":
        if payload.existing_buyer_id is None:
            raise ValueError("Choose the existing buyer this candidate belongs to.")
        buyer = db.scalar(
            select(Buyer).where(
                Buyer.id == payload.existing_buyer_id,
                Buyer.organization_id == principal.organization_id,
                Buyer.archived_at.is_(None),
            )
        )
        if buyer is None:
            raise ValueError("The selected existing buyer is unavailable.")
    else:
        if not normalize_email(candidate.email) and not normalize_phone(candidate.phone):
            raise ValueError(
                "An external candidate needs a valid email or phone before Buyer Network approval."
            )
        source_key = normalize_source_key(candidate.provider or "external_discovery")
        source_external_key = candidate.external_key or str(candidate.id)
        buyer_read = create_buyer(
            db,
            principal,
            BuyerCreate(
                name=candidate.display_name,
                company_name=candidate.company_name,
                email=candidate.email,
                phone=candidate.phone,
                status="needs_review",
                source_key=source_key,
                source_detail="Approved from deal-specific external candidate",
                source_external_key=source_external_key,
                relationship_owner_user_id=principal.user_id,
                notes=(
                    "Approved into the Stonegate Buyer Network from preserved provider "
                    "evidence. Contact identity, buy box, and proof of funds remain unverified."
                ),
                allow_separate_record=candidate.overlap_status != "none",
                separate_record_reason=(
                    payload.reason if candidate.overlap_status != "none" else None
                ),
            ),
            commit=False,
        )
        buyer = db.get(Buyer, buyer_read.id)
        if buyer is None:
            raise ValueError("The approved buyer record could not be loaded.")

    if source_link is None:
        source_link = BuyerSourceLink(
            organization_id=principal.organization_id,
            buyer_id=buyer.id,
            provider=provider,
            external_key=external_key,
            discovery_candidate_id=candidate.latest_discovery_candidate_id,
            evidence_snapshot=candidate.provenance_snapshot,
            approved_by_user_id=principal.user_id,
            approved_at=datetime.now(UTC),
            first_seen_at=candidate.created_at,
            last_seen_at=datetime.now(UTC),
        )
        db.add(source_link)
        try:
            # Surface provider-identity races here, before a later query can
            # trigger an implicit autoflush at a less predictable boundary.
            db.flush()
        except IntegrityError as exc:
            db.rollback()
            raise ValueError(
                "This provider identity was linked by another request. "
                "Refresh the buyer pool and review the canonical buyer before trying again."
            ) from exc
    else:
        source_link.discovery_candidate_id = candidate.latest_discovery_candidate_id
        source_link.evidence_snapshot = candidate.provenance_snapshot
        source_link.last_seen_at = datetime.now(UTC)
        source_link.approved_by_user_id = principal.user_id
        source_link.approved_at = datetime.now(UTC)

    if candidate.latest_discovery_candidate_id is not None:
        discovery = db.get(BuyerDiscoveryCandidate, candidate.latest_discovery_candidate_id)
        if discovery is not None:
            discovery.buyer_id = buyer.id
            discovery.status = "imported" if payload.decision == "create_new" else "duplicate"
            discovery.imported_at = datetime.now(UTC)
    canonical_candidate = None
    if payload.decision == "link_existing":
        canonical_candidate = db.scalar(
            select(DispositionBuyerPoolCandidate)
            .where(
                DispositionBuyerPoolCandidate.organization_id
                == principal.organization_id,
                DispositionBuyerPoolCandidate.disposition_case_id == case_id,
                DispositionBuyerPoolCandidate.buyer_id == buyer.id,
                DispositionBuyerPoolCandidate.id != candidate.id,
            )
            .with_for_update()
        )

    resolution = {
        **(candidate.overlap_evidence or {}),
        "resolution": payload.decision,
        "resolved_buyer_id": str(buyer.id),
        "reason": payload.reason,
    }
    preserve_shortlist = candidate.decision_status == "shortlisted"
    if canonical_candidate is not None:
        if (
            candidate.decision_status == "shortlisted"
            and canonical_candidate.decision_status == "undecided"
        ):
            canonical_candidate.decision_status = "shortlisted"
            canonical_candidate.lifecycle_stage = "shortlisted"
            canonical_candidate.decision_reason = payload.reason
            canonical_candidate.lock_version += 1
            canonical_candidate.decision_updated_by_user_id = principal.user_id
            canonical_candidate.decision_updated_at = datetime.now(UTC)
        candidate.buyer_id = None
        candidate.source_type = "external"
        candidate.decision_status = "passed"
        candidate.lifecycle_stage = "pass"
        candidate.decision_reason = payload.reason
        candidate.overlap_status = "resolved"
        candidate.possible_buyer_id = buyer.id
        candidate.overlap_evidence = resolution
        candidate.lock_version += 1
    else:
        candidate.buyer_id = buyer.id
        candidate.source_type = "internal"
        # Approval into the canonical network must not erase a human shortlist.
        # The current external entry remains review-required, so release stays
        # blocked until a refreshed run proves this buyer is currently eligible.
        candidate.decision_status = "shortlisted" if preserve_shortlist else "undecided"
        candidate.lifecycle_stage = "shortlisted" if preserve_shortlist else "needs_review"
        candidate.decision_reason = payload.reason
        candidate.overlap_status = "resolved"
        candidate.possible_buyer_id = buyer.id
        candidate.overlap_evidence = resolution
        candidate.lock_version += 1
    candidate.approved_by_user_id = principal.user_id
    candidate.approved_at = datetime.now(UTC)
    candidate.decision_updated_by_user_id = principal.user_id
    candidate.decision_updated_at = datetime.now(UTC)
    _conversion_audit(db, principal, candidate, payload, buyer.id)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise ValueError(
            "This provider identity was linked by another request. "
            "Refresh the buyer pool and review the canonical buyer before trying again."
        ) from exc
    return buyer.id


def case_has_pool_decisions(
    db: Session,
    principal: Principal,
    case_id: UUID,
) -> bool:
    run_id = _latest_completed_run_id(db, principal, case_id)
    if run_id is None:
        return False
    return bool(
        db.scalar(
            select(func.count(DispositionBuyerPoolEntry.id))
            .join(
                DispositionBuyerPoolCandidate,
                DispositionBuyerPoolCandidate.id
                == DispositionBuyerPoolEntry.buyer_pool_candidate_id,
            )
            .where(
                DispositionBuyerPoolEntry.organization_id == principal.organization_id,
                DispositionBuyerPoolEntry.buyer_pool_run_id == run_id,
                DispositionBuyerPoolCandidate.disposition_case_id == case_id,
                or_(
                    DispositionBuyerPoolCandidate.decision_status != "undecided",
                    DispositionBuyerPoolCandidate.approved_at.is_not(None),
                ),
            )
        )
    )


def shortlisted_buyer_ids(
    db: Session,
    principal: Principal,
    case_id: UUID,
) -> set[UUID]:
    run_id = _latest_completed_run_id(db, principal, case_id)
    if run_id is None:
        return set()
    return {
        buyer_id
        for buyer_id in db.scalars(
            select(DispositionBuyerPoolCandidate.buyer_id)
            .join(
                DispositionBuyerPoolEntry,
                DispositionBuyerPoolEntry.buyer_pool_candidate_id
                == DispositionBuyerPoolCandidate.id,
            )
            .where(
                DispositionBuyerPoolEntry.organization_id == principal.organization_id,
                DispositionBuyerPoolEntry.buyer_pool_run_id == run_id,
                DispositionBuyerPoolEntry.eligibility_status == "eligible",
                DispositionBuyerPoolCandidate.disposition_case_id == case_id,
                DispositionBuyerPoolCandidate.decision_status == "shortlisted",
                DispositionBuyerPoolCandidate.buyer_id.is_not(None),
            )
        ).all()
        if buyer_id is not None
    }


def _latest_completed_run_id(
    db: Session,
    principal: Principal,
    case_id: UUID,
) -> UUID | None:
    return db.scalar(
        select(DispositionBuyerPoolRun.id)
        .where(
            DispositionBuyerPoolRun.organization_id == principal.organization_id,
            DispositionBuyerPoolRun.disposition_case_id == case_id,
            DispositionBuyerPoolRun.status == "completed",
        )
        .order_by(
            DispositionBuyerPoolRun.version_number.desc(),
            DispositionBuyerPoolRun.created_at.desc(),
        )
        .limit(1)
    )


def _require_latest_run_candidate(
    db: Session,
    principal: Principal,
    case_id: UUID,
    candidate_id: UUID,
) -> None:
    run_id = _latest_completed_run_id(db, principal, case_id)
    if run_id is None or db.scalar(
        select(DispositionBuyerPoolEntry.id)
        .where(
            DispositionBuyerPoolEntry.organization_id == principal.organization_id,
            DispositionBuyerPoolEntry.buyer_pool_run_id == run_id,
            DispositionBuyerPoolEntry.buyer_pool_candidate_id == candidate_id,
        )
        .limit(1)
    ) is None:
        raise ValueError(
            "This buyer-pool candidate is not part of the latest completed run. "
            "Refresh the buyer pool before making a decision."
        )


def _upsert_internal_candidate(
    db: Session,
    principal: Principal,
    case: DispositionCase,
    buyer: Buyer,
    merged_external: list[BuyerDiscoveryCandidate],
) -> DispositionBuyerPoolCandidate:
    candidate = db.scalar(
        select(DispositionBuyerPoolCandidate).where(
            DispositionBuyerPoolCandidate.organization_id == principal.organization_id,
            DispositionBuyerPoolCandidate.disposition_case_id == case.id,
            DispositionBuyerPoolCandidate.buyer_id == buyer.id,
        )
    )
    provenance = {
        "buyer_id": str(buyer.id),
        "buyer_source": {
            "source_key": buyer.source_key,
            "source_detail": buyer.source_detail,
            "source_external_key": buyer.source_external_key,
        },
        "merged_provider_candidates": [
            _discovery_provenance(value) for value in merged_external
        ],
    }
    next_state: dict[str, Any] = {
        "source_type": "internal",
        "buyer_id": str(buyer.id),
        "latest_discovery_candidate_id": (
            str(merged_external[0].id) if merged_external else None
        ),
        "display_name": buyer.name,
        "company_name": buyer.company_name,
        "email": buyer.email,
        "phone": buyer.phone,
        "provenance_snapshot": provenance,
        "overlap_status": "merged" if merged_external else "none",
        "possible_buyer_id": None,
        "overlap_evidence": {
            "merged_external_candidate_ids": [str(value.id) for value in merged_external]
        },
    }
    if candidate is None:
        candidate = DispositionBuyerPoolCandidate(
            organization_id=principal.organization_id,
            disposition_case_id=case.id,
            identity_key=f"buyer:{buyer.id}",
            source_type="internal",
            buyer_id=buyer.id,
            latest_discovery_candidate_id=(merged_external[0].id if merged_external else None),
            provider=None,
            external_key=None,
            display_name=buyer.name,
            company_name=buyer.company_name,
            email=buyer.email,
            phone=buyer.phone,
            provenance_snapshot=provenance,
            overlap_status="merged" if merged_external else "none",
            possible_buyer_id=None,
            overlap_evidence={
                "merged_external_candidate_ids": [str(value.id) for value in merged_external]
            },
            decision_status="undecided",
            lifecycle_stage="discovered",
            decision_reason=None,
            lock_version=1,
        )
        db.add(candidate)
        db.flush()
    else:
        previous_state = _candidate_evidence_state(candidate)
        candidate.source_type = "internal"
        candidate.display_name = buyer.name
        candidate.company_name = buyer.company_name
        candidate.email = buyer.email
        candidate.phone = buyer.phone
        candidate.provenance_snapshot = provenance
        candidate.latest_discovery_candidate_id = (
            merged_external[0].id if merged_external else None
        )
        candidate.overlap_status = "merged" if merged_external else "none"
        candidate.possible_buyer_id = None
        candidate.overlap_evidence = next_state["overlap_evidence"]
        if _fingerprint(previous_state) != _fingerprint(next_state):
            candidate.lock_version += 1
    return candidate


def _upsert_external_candidate(
    db: Session,
    principal: Principal,
    case: DispositionCase,
    discovery: BuyerDiscoveryCandidate,
    *,
    overlap_status: str,
    buyer_ids: list[UUID],
    possible_buyer: Buyer | None,
) -> DispositionBuyerPoolCandidate:
    raw_identity_key = f"provider:{discovery.provider}:{discovery.external_key}"
    identity_key = (
        raw_identity_key
        if len(raw_identity_key) <= 255
        else f"provider:{discovery.provider}:{_fingerprint(raw_identity_key)}"
    )
    candidate = db.scalar(
        select(DispositionBuyerPoolCandidate).where(
            DispositionBuyerPoolCandidate.organization_id == principal.organization_id,
            DispositionBuyerPoolCandidate.disposition_case_id == case.id,
            DispositionBuyerPoolCandidate.identity_key == identity_key,
        )
    )
    evidence = {
        "possible_buyer_ids": [str(value) for value in buyer_ids],
        "reason": overlap_status,
    }
    provenance = _discovery_provenance(discovery)
    next_state = {
        "source_type": "external",
        "buyer_id": None,
        "latest_discovery_candidate_id": str(discovery.id),
        "display_name": discovery.name,
        "company_name": discovery.company_name,
        "email": discovery.email,
        "phone": discovery.phone,
        "provenance_snapshot": provenance,
        "overlap_status": overlap_status,
        "possible_buyer_id": str(possible_buyer.id) if possible_buyer else None,
        "overlap_evidence": evidence,
    }
    if candidate is None:
        candidate = DispositionBuyerPoolCandidate(
            organization_id=principal.organization_id,
            disposition_case_id=case.id,
            identity_key=identity_key,
            source_type="external",
            buyer_id=None,
            latest_discovery_candidate_id=discovery.id,
            provider=discovery.provider,
            external_key=discovery.external_key,
            display_name=discovery.name,
            company_name=discovery.company_name,
            email=discovery.email,
            phone=discovery.phone,
            provenance_snapshot=provenance,
            overlap_status=overlap_status,
            possible_buyer_id=possible_buyer.id if possible_buyer else None,
            overlap_evidence=evidence,
            decision_status="undecided",
            lifecycle_stage=("needs_review" if overlap_status != "none" else "discovered"),
            decision_reason=None,
            lock_version=1,
        )
        db.add(candidate)
        db.flush()
    else:
        previous_state = _candidate_evidence_state(candidate)
        candidate.source_type = "external"
        candidate.buyer_id = None
        candidate.latest_discovery_candidate_id = discovery.id
        candidate.display_name = discovery.name
        candidate.company_name = discovery.company_name
        candidate.email = discovery.email
        candidate.phone = discovery.phone
        candidate.provenance_snapshot = provenance
        candidate.overlap_status = overlap_status
        candidate.possible_buyer_id = possible_buyer.id if possible_buyer else None
        candidate.overlap_evidence = evidence
        if _fingerprint(previous_state) != _fingerprint(next_state):
            candidate.lock_version += 1
    return candidate


def _candidate_evidence_state(
    candidate: DispositionBuyerPoolCandidate,
) -> dict[str, Any]:
    return {
        "source_type": candidate.source_type,
        "buyer_id": str(candidate.buyer_id) if candidate.buyer_id else None,
        "latest_discovery_candidate_id": (
            str(candidate.latest_discovery_candidate_id)
            if candidate.latest_discovery_candidate_id
            else None
        ),
        "display_name": candidate.display_name,
        "company_name": candidate.company_name,
        "email": candidate.email,
        "phone": candidate.phone,
        "provenance_snapshot": candidate.provenance_snapshot,
        "overlap_status": candidate.overlap_status,
        "possible_buyer_id": (
            str(candidate.possible_buyer_id) if candidate.possible_buyer_id else None
        ),
        "overlap_evidence": candidate.overlap_evidence,
    }


def _evaluate_internal_buyer(
    db: Session,
    principal: Principal,
    case: DispositionCase,
    property_record: Property,
    asset_class: str,
    buyer: Buyer,
    merged_external: list[BuyerDiscoveryCandidate],
    *,
    now: datetime,
) -> dict[str, Any]:
    buy_box_result = get_current_buy_box_version(
        db, principal, buyer.id, asset_class, require_verified=False
    )
    buy_box_version = buy_box_result[1] if buy_box_result else None
    criteria = dict(buy_box_version.criteria_payload) if buy_box_version else None
    verified_buy_box = bool(
        buy_box_version and buy_box_version.verification_status == "verified"
    )
    market_ok = _market_match(criteria, property_record)
    price_ok = _price_match(criteria, case.asking_price_cents)
    asset_ok = _asset_match(criteria, property_record, asset_class)
    strategy_ok = _strategy_match(criteria, case.strategy)
    funding_methods = criteria.get("funding_methods") if criteria else None
    funding_ok = bool(isinstance(funding_methods, list) and funding_methods)
    capacity = criteria.get("capacity") if criteria else None
    available_capital = (
        capacity.get("available_capital_cents") if isinstance(capacity, dict) else None
    )
    capacity_limit = (
        available_capital
        if available_capital is not None
        else buyer.max_purchase_price_cents
    )
    capacity_ok = bool(
        capacity_limit is not None and int(capacity_limit) >= case.asking_price_cents
    )
    proof = _current_proof(db, principal, buyer.id, case.asking_price_cents, now=now)
    proof_ok = proof is not None
    activity_ok = bool(
        buyer.last_verified_at
        and _aware(buyer.last_verified_at) >= now - timedelta(days=180)
    )
    relationship_ok = buyer.relationship_status in {
        "active",
        "warm",
        "priority",
        "new",
    }
    components = {
        "market": 1500 if market_ok else 0,
        "asset": 1000 if asset_ok else 0,
        "price": 1500 if price_ok else 0,
        "strategy": 1000 if strategy_ok else 0,
        "funding": 500 if funding_ok else 0,
        "capacity": 1000 if capacity_ok else 0,
        "proof": 1500 if proof_ok else 0,
        "activity": 750 if activity_ok else 0,
        "reliability": round(max(0, min(10000, buyer.reliability_score_basis_points)) * 0.075),
        "relationship": 500 if relationship_ok else 0,
    }
    disqualifiers = []
    if buyer.status != "active":
        disqualifiers.append(f"Buyer status is {buyer.status}, not active.")
    if buyer.relationship_status == "do_not_contact":
        disqualifiers.append("Buyer is marked do not contact.")
    if not verified_buy_box:
        disqualifiers.append(f"A verified {asset_class.title()} buy box is required.")
    if verified_buy_box and not market_ok:
        disqualifiers.append("The property is outside the verified market criteria.")
    if verified_buy_box and not price_ok:
        disqualifiers.append("The deal price is outside the verified buy box.")
    if verified_buy_box and not asset_ok:
        disqualifiers.append("The property does not meet the verified asset criteria.")
    if verified_buy_box and not strategy_ok:
        disqualifiers.append("The deal strategy is outside the verified buy box.")
    if not proof_ok:
        disqualifiers.append("Current verified proof of funds does not cover the deal price.")
    eligibility = "eligible" if not disqualifiers else "review_required"
    explanation = [
        _criterion_sentence("Market", market_ok, 1500),
        _criterion_sentence("Asset", asset_ok, 1000),
        _criterion_sentence("Price", price_ok, 1500),
        _criterion_sentence("Strategy", strategy_ok, 1000),
        _criterion_sentence("Funding method", funding_ok, 500),
        _criterion_sentence("Purchase capacity", capacity_ok, 1000),
        _criterion_sentence("Proof of funds", proof_ok, 1500),
        _criterion_sentence("Recent verification activity", activity_ok, 750),
        f"Reliability contributes {components['reliability']} of 750 points.",
        _criterion_sentence("Relationship", relationship_ok, 500),
    ]
    supporting = [
        {
            "type": "buy_box_version",
            "id": str(buy_box_version.id),
            "version_number": buy_box_version.version_number,
            "verification_status": buy_box_version.verification_status,
        }
        for _ in [0]
        if buy_box_version is not None
    ]
    proof_snapshot = _proof_evidence_snapshot(proof) if proof is not None else None
    if proof is not None:
        supporting.append(
            {
                "type": "proof_of_funds",
                **cast(dict[str, Any], proof_snapshot),
            }
        )
    supporting.extend(
        {
            "type": "provider_purchase_evidence",
            "provider": item.provider,
            "external_key": item.external_key,
            "observed_purchase_count": item.observed_purchase_count,
        }
        for item in merged_external
    )
    return {
        "score_basis_points": sum(components.values()),
        "score_components": components,
        "score_explanation": explanation,
        "supporting_evidence": supporting,
        "conflicting_evidence": [],
        "disqualifying_reasons": disqualifiers,
        "eligibility_status": eligibility,
        "buy_box_version_id": buy_box_version.id if buy_box_version else None,
        "proof_document_id": proof.id if proof else None,
        "criteria_snapshot": {
            "asset_class": asset_class,
            "verification_status": (
                buy_box_version.verification_status if buy_box_version else "missing"
            ),
            "version_number": buy_box_version.version_number if buy_box_version else None,
            "criteria": criteria,
        },
        "evidence_snapshot": {
            "buyer_status": buyer.status,
            "relationship_status": buyer.relationship_status,
            "verification_status": buyer.verification_status,
            "score_inputs": {
                "buyer_max_purchase_price_cents": buyer.max_purchase_price_cents,
                "buy_box_available_capital_cents": available_capital,
                "effective_capacity_limit_cents": (
                    int(capacity_limit) if capacity_limit is not None else None
                ),
                "last_verified_at": (
                    buyer.last_verified_at.isoformat() if buyer.last_verified_at else None
                ),
                "activity_window_days": 180,
                "reliability_score_basis_points": buyer.reliability_score_basis_points,
            },
            "proof_status": proof.status if proof else "unknown",
            "proof_expires_at": (
                proof.expires_at.isoformat() if proof and proof.expires_at else None
            ),
            "proof": proof_snapshot,
            "merged_provider_candidates": [
                _discovery_provenance(value) for value in merged_external
            ],
        },
    }


def _evaluate_external_candidate(
    case: DispositionCase,
    property_record: Property,
    asset_class: str,
    candidate: BuyerDiscoveryCandidate,
    *,
    overlap_status: str,
    possible_buyer_ids: list[UUID],
    now: datetime,
) -> dict[str, Any]:
    market_text = " ".join(
        [candidate.market or "", candidate.state or ""]
    ).casefold()
    market_ok = any(
        value and value.casefold() in market_text
        for value in (property_record.city, property_record.county, property_record.state)
    )
    price_ok = bool(
        (candidate.min_purchase_price_cents is None
         or case.asking_price_cents >= candidate.min_purchase_price_cents)
        and (candidate.max_purchase_price_cents is None
             or case.asking_price_cents <= candidate.max_purchase_price_cents)
        and (
            candidate.min_purchase_price_cents is not None
            or candidate.max_purchase_price_cents is not None
        )
    )
    normalized_types = {_normalized_key(value) for value in candidate.property_types}
    subject_type = _normalized_key(property_record.property_type)
    asset_ok = bool(
        asset_class == "land"
        and ("land" in normalized_types or not normalized_types)
        or asset_class == "house"
        and subject_type
        and subject_type in normalized_types
    )
    funding_ok = candidate.no_mortgage_count > 0
    recent_cutoff = now.date() - timedelta(days=730)
    activity_ok = bool(
        candidate.last_purchase_date and candidate.last_purchase_date >= recent_cutoff
    )
    reliability_points = min(750, candidate.observed_purchase_count * 75)
    components = {
        "market": 1500 if market_ok else 0,
        "asset": 1000 if asset_ok else 0,
        "price": 1500 if price_ok else 0,
        "strategy": 0,
        "funding": 500 if funding_ok else 0,
        "capacity": 0,
        "proof": 0,
        "activity": 750 if activity_ok else 0,
        "reliability": reliability_points,
        "relationship": 0,
    }
    conflicts = []
    if overlap_status != "none":
        conflicts.append(
            {
                "type": "identity_overlap",
                "status": overlap_status,
                "possible_buyer_ids": [str(value) for value in possible_buyer_ids],
            }
        )
    disqualifiers = [
        "External evidence must be explicitly approved into the Buyer Network before outreach.",
        "Verified Stonegate buy-box and proof-of-funds evidence are not yet available.",
    ]
    return {
        "score_basis_points": sum(components.values()),
        "score_components": components,
        "score_explanation": [
            _criterion_sentence("Observed market activity", market_ok, 1500),
            _criterion_sentence("Observed asset activity", asset_ok, 1000),
            _criterion_sentence("Observed purchase range", price_ok, 1500),
            _criterion_sentence("Cash-like purchase evidence", funding_ok, 500),
            _criterion_sentence("Recent purchase activity", activity_ok, 750),
            f"Observed purchase volume contributes {reliability_points} of 750 points.",
            "Strategy, capacity, proof, and relationship remain unknown until reviewed.",
        ],
        "supporting_evidence": [
            {
                "type": "provider_purchase_evidence",
                **_discovery_provenance(candidate),
            }
        ],
        "conflicting_evidence": conflicts,
        "disqualifying_reasons": disqualifiers,
        "eligibility_status": "review_required",
        "buy_box_version_id": None,
        "proof_document_id": None,
        "criteria_snapshot": {
            "asset_class": asset_class,
            "verification_status": "external_observation_only",
            "criteria": None,
        },
        "evidence_snapshot": {
            "proof_status": "unknown",
            "proof_expires_at": None,
            "provider_candidate": _discovery_provenance(candidate),
            "overlap_status": overlap_status,
        },
    }


def _latest_external_candidates(
    db: Session,
    principal: Principal,
    case_id: UUID,
) -> list[BuyerDiscoveryCandidate]:
    rows = list(
        db.scalars(
            select(BuyerDiscoveryCandidate)
            .join(
                BuyerDiscoveryRun,
                BuyerDiscoveryRun.id == BuyerDiscoveryCandidate.discovery_run_id,
            )
            .where(
                BuyerDiscoveryCandidate.organization_id == principal.organization_id,
                BuyerDiscoveryRun.organization_id == principal.organization_id,
                BuyerDiscoveryRun.disposition_case_id == case_id,
            )
            .order_by(BuyerDiscoveryCandidate.created_at.desc())
        ).all()
    )
    latest: dict[tuple[str, str], BuyerDiscoveryCandidate] = {}
    for candidate in rows:
        latest.setdefault((candidate.provider, candidate.external_key), candidate)
    return list(latest.values())


def _buyer_identity_maps(
    db: Session,
    principal: Principal,
    buyers: list[Buyer],
) -> dict[str, dict[str, list[Buyer]]]:
    maps: dict[str, dict[str, list[Buyer]]] = {
        "source": {},
        "email": {},
        "phone": {},
        "name": {},
    }
    buyers_by_id = {buyer.id: buyer for buyer in buyers}
    for buyer in buyers:
        if buyer.source_external_key:
            key = (
                f"{normalize_source_key(buyer.source_key)}:"
                f"{buyer.source_external_key}"
            )
            maps["source"].setdefault(key, []).append(buyer)
        if buyer.normalized_email:
            maps["email"].setdefault(buyer.normalized_email, []).append(buyer)
        if buyer.normalized_phone:
            maps["phone"].setdefault(buyer.normalized_phone, []).append(buyer)
        for name in {buyer.name, buyer.company_name}:
            normalized = normalize_company(name)
            if normalized:
                maps["name"].setdefault(normalized, []).append(buyer)
    if buyers_by_id:
        for link in db.scalars(
            select(BuyerSourceLink).where(
                BuyerSourceLink.organization_id == principal.organization_id,
                BuyerSourceLink.buyer_id.in_(buyers_by_id),
            )
        ).all():
            linked_buyer = buyers_by_id.get(link.buyer_id)
            if linked_buyer is None:
                continue
            key = f"{normalize_source_key(link.provider)}:{link.external_key}"
            existing = maps["source"].setdefault(key, [])
            if linked_buyer not in existing:
                existing.append(linked_buyer)
    return maps


def _resolve_overlap(
    candidate: BuyerDiscoveryCandidate,
    maps: dict[str, dict[str, list[Buyer]]],
) -> tuple[str, list[UUID], Buyer | None]:
    strong: dict[UUID, Buyer] = {}
    if candidate.buyer_id:
        for collection in maps.values():
            for values in collection.values():
                for buyer in values:
                    if buyer.id == candidate.buyer_id:
                        strong[buyer.id] = buyer
    source_key = f"{normalize_source_key(candidate.provider)}:{candidate.external_key}"
    for buyer in maps["source"].get(source_key, []):
        strong[buyer.id] = buyer
    normalized_email = normalize_email(candidate.email)
    if normalized_email:
        for buyer in maps["email"].get(normalized_email, []):
            strong[buyer.id] = buyer
    normalized_phone = normalize_phone(candidate.phone)
    if normalized_phone:
        for buyer in maps["phone"].get(normalized_phone, []):
            strong[buyer.id] = buyer
    if strong:
        ordered = sorted(strong, key=str)
        return ("exact" if len(ordered) == 1 else "ambiguous"), ordered, strong[ordered[0]]
    likely: dict[UUID, Buyer] = {}
    for name in {candidate.name, candidate.company_name}:
        normalized_name = normalize_company(name)
        if normalized_name:
            for buyer in maps["name"].get(normalized_name, []):
                likely[buyer.id] = buyer
    if likely:
        ordered = sorted(likely, key=str)
        return "likely", ordered, likely[ordered[0]]
    return "none", [], None


def _entry_read(
    db: Session,
    principal: Principal,
    entry: DispositionBuyerPoolEntry,
    candidate: DispositionBuyerPoolCandidate,
    source_type: str,
    buyer: Buyer | None,
    possible_buyer: Buyer | None,
) -> BuyerPoolEntryRead:
    del db
    proof_status = str(entry.evidence_snapshot.get("proof_status", "unknown"))
    proof_expires_at = _parse_optional_datetime(
        entry.evidence_snapshot.get("proof_expires_at")
    )
    return BuyerPoolEntryRead(
        id=entry.id,
        candidate_id=candidate.id,
        buyer_id=candidate.buyer_id,
        discovery_candidate_id=candidate.latest_discovery_candidate_id,
        source_type=cast(Literal["mine", "network", "external"], source_type),
        origin_type="external" if candidate.provider else "internal",
        provider=candidate.provider,
        external_key=candidate.external_key,
        name=buyer.name if buyer else candidate.display_name,
        company_name=buyer.company_name if buyer else candidate.company_name,
        email=buyer.email if buyer else candidate.email,
        phone=buyer.phone if buyer else candidate.phone,
        decision_status=cast(BuyerPoolDecision, candidate.decision_status),
        lifecycle_stage=cast(BuyerPoolLifecycleStage, candidate.lifecycle_stage),
        decision_reason=candidate.decision_reason,
        lock_version=candidate.lock_version,
        overlap_status=candidate.overlap_status,
        possible_buyer_id=candidate.possible_buyer_id,
        possible_buyer_name=possible_buyer.name if possible_buyer else None,
        possible_buyer_company_name=(
            possible_buyer.company_name if possible_buyer else None
        ),
        overlap_evidence=candidate.overlap_evidence or {},
        score_basis_points=entry.score_basis_points,
        rank=entry.rank,
        eligibility_status=entry.eligibility_status,
        score_components=entry.score_components,
        score_explanation=list(entry.score_explanation or []),
        supporting_evidence=list(entry.supporting_evidence or []),
        conflicting_evidence=list(entry.conflicting_evidence or []),
        disqualifying_reasons=list(entry.disqualifying_reasons or []),
        buy_box_version_id=entry.buy_box_version_id,
        proof_status=proof_status,
        proof_expires_at=proof_expires_at,
        relationship_status=buyer.relationship_status if buyer else None,
        tier=buyer.tier if buyer else None,
        temperature=buyer.temperature if buyer else None,
    )


def _run_read(run: DispositionBuyerPoolRun) -> BuyerPoolRunRead:
    return BuyerPoolRunRead(
        id=run.id,
        version_number=run.version_number,
        asset_class=run.asset_class,
        matcher_version=run.matcher_version,
        score_policy_version=run.score_policy_version,
        status=run.status,
        source_counts={key: int(value) for key, value in (run.source_counts or {}).items()},
        generated_at=run.completed_at or run.created_at,
    )


def _source_category(
    candidate: DispositionBuyerPoolCandidate,
    buyer: Buyer | None,
    principal: Principal,
) -> str:
    if candidate.source_type == "external" or buyer is None:
        return "external"
    return "mine" if buyer.relationship_owner_user_id == principal.user_id else "network"


def _current_proof(
    db: Session,
    principal: Principal,
    buyer_id: UUID,
    asking_price_cents: int,
    *,
    now: datetime,
) -> BuyerProofDocument | None:
    for proof in db.scalars(
        select(BuyerProofDocument)
        .where(
            BuyerProofDocument.organization_id == principal.organization_id,
            BuyerProofDocument.buyer_id == buyer_id,
            BuyerProofDocument.status == "verified",
            BuyerProofDocument.deleted_at.is_(None),
        )
        .order_by(
            BuyerProofDocument.verified_at.desc(),
            BuyerProofDocument.created_at.desc(),
        )
    ).all():
        if (
            proof.verified_by_user_id is not None
            and proof.verified_at is not None
            and proof.verified_amount_cents is not None
            and proof.verified_amount_cents >= asking_price_cents
            and proof.expires_at is not None
            and _aware(proof.expires_at) > now
            and proof.malware_scan_status in REVIEWABLE_PROOF_SCAN_STATUSES
        ):
            return proof
    return None


def _proof_evidence_snapshot(proof: BuyerProofDocument) -> dict[str, Any]:
    snapshot = {
        "id": str(proof.id),
        "status": proof.status,
        "verified_amount_cents": proof.verified_amount_cents,
        "verified_by_user_id": (
            str(proof.verified_by_user_id) if proof.verified_by_user_id else None
        ),
        "verified_at": proof.verified_at.isoformat() if proof.verified_at else None,
        "verification_source": proof.verification_source,
        "expires_at": proof.expires_at.isoformat() if proof.expires_at else None,
        "malware_scan_status": proof.malware_scan_status,
        "sha256": proof.sha256,
        "file_size": proof.file_size,
        "content_type": proof.content_type,
    }
    return {
        **snapshot,
        "evidence_fingerprint": _fingerprint(snapshot),
    }


def _parse_optional_datetime(value: object) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _price_match(criteria: dict[str, object] | None, asking_price_cents: int) -> bool:
    if criteria is None:
        return False
    minimum = criteria.get("min_price_cents")
    maximum = criteria.get("max_price_cents")
    if minimum is None and maximum is None:
        return False
    return bool(
        (minimum is None or asking_price_cents >= _integer(minimum))
        and (maximum is None or asking_price_cents <= _integer(maximum))
    )


def _market_match(criteria: dict[str, object] | None, property_record: Property) -> bool:
    if criteria is None:
        return False
    included = criteria.get("geographies")
    excluded = criteria.get("excluded_geographies")
    if not isinstance(included, list) or not included:
        return False
    if isinstance(excluded, list):
        for entry in excluded:
            if not isinstance(entry, dict) or entry.get("jurisdiction") == "radius":
                return False
            if _geography_match(entry, property_record):
                return False
    return any(
        _geography_match(entry, property_record)
        for entry in included
        if isinstance(entry, dict)
    )


def _geography_match(entry: dict[object, object], property_record: Property) -> bool:
    jurisdiction = _normalized_key(entry.get("jurisdiction"))
    value = _normalized_text(entry.get("value"))
    state = _normalized_text(entry.get("state"))
    property_state = _normalized_text(property_record.state)
    if jurisdiction == "state":
        return bool(value and value == property_state)
    if jurisdiction == "county":
        return bool(
            state == property_state
            and _normalized_county(value) == _normalized_county(property_record.county)
        )
    if jurisdiction == "city":
        return bool(
            state == property_state and value == _normalized_text(property_record.city)
        )
    if jurisdiction == "postal_code":
        return _digits(value)[:5] == _digits(property_record.postal_code)[:5]
    return False


def _asset_match(
    criteria: dict[str, object] | None,
    property_record: Property,
    asset_class: str,
) -> bool:
    if criteria is None or criteria.get("asset_class") != asset_class:
        return False
    if asset_class == "land":
        return True
    requested = criteria.get("property_types")
    if not isinstance(requested, list) or not requested:
        return False
    subject = _normalized_key(property_record.property_type)
    return bool(subject and subject in {_normalized_key(value) for value in requested})


def _strategy_match(criteria: dict[str, object] | None, strategy: str) -> bool:
    if criteria is None:
        return False
    strategies = criteria.get("strategies")
    if not isinstance(strategies, list) or not strategies:
        return True
    normalized = {
        "assignment": "wholesale_assignment",
        "double_close": "double_close",
        "novation": "novation",
    }.get(_normalized_key(strategy), _normalized_key(strategy))
    return normalized in {_normalized_key(value) for value in strategies}


def _discovery_provenance(candidate: BuyerDiscoveryCandidate) -> dict[str, Any]:
    return {
        "candidate_id": str(candidate.id),
        "discovery_run_id": str(candidate.discovery_run_id),
        "provider": candidate.provider,
        "external_key": candidate.external_key,
        "market": candidate.market,
        "state": candidate.state,
        "property_types": candidate.property_types,
        "observed_purchase_count": candidate.observed_purchase_count,
        "no_mortgage_count": candidate.no_mortgage_count,
        "last_purchase_date": (
            candidate.last_purchase_date.isoformat() if candidate.last_purchase_date else None
        ),
        "min_purchase_price_cents": candidate.min_purchase_price_cents,
        "max_purchase_price_cents": candidate.max_purchase_price_cents,
        "evidence_snapshot": candidate.evidence_snapshot,
    }


def _conversion_audit(
    db: Session,
    principal: Principal,
    candidate: DispositionBuyerPoolCandidate,
    payload: BuyerPoolConversionRequest,
    buyer_id: UUID | None,
) -> None:
    db.add(
        AuditEvent(
            organization_id=principal.organization_id,
            actor_user_id=principal.user_id,
            actor_type="user",
            action="disposition.buyer_pool.conversion_decision",
            entity_type="disposition_buyer_pool_candidate",
            entity_id=candidate.id,
            previous_value=None,
            new_value={
                "decision": payload.decision,
                "buyer_id": str(buyer_id) if buyer_id else None,
                "external_messages_sent": 0,
                "buyer_status": "needs_review" if buyer_id else None,
            },
            reason=payload.reason,
        )
    )


def _criterion_sentence(label: str, matched: bool, points: int) -> str:
    awarded = points if matched else 0
    outcome = "matched" if matched else "did not match"
    return f"{label} {outcome} ({awarded}/{points})."


def _fingerprint(value: object) -> str:
    return sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    ).hexdigest()


def _normalized_key(value: object) -> str:
    return "_".join(str(value or "").strip().lower().replace("-", " ").split())


def _normalized_text(value: object) -> str:
    return " ".join(str(value or "").strip().casefold().split())


def _normalized_county(value: object) -> str:
    return _normalized_text(value).removesuffix(" county").strip()


def _digits(value: object) -> str:
    return "".join(character for character in str(value or "") if character.isdigit())


def _integer(value: object) -> int:
    return int(str(value))


def _aware(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)
