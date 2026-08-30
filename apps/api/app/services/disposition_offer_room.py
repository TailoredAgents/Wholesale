from __future__ import annotations

import json
from datetime import UTC, datetime
from hashlib import sha256
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.auth import Principal
from app.core.config import Settings
from app.domain.assets import require_house_workflow
from app.domain.rbac import PermissionKeys
from app.models.foundation import (
    Buyer,
    BuyerOffer,
    BuyerProofDocument,
    ContractPackage,
    DispositionBuyerOutcome,
    DispositionBuyerSelection,
    DispositionBuyerSelectionSlot,
    DispositionCase,
    DispositionClosingCheckpoint,
    DispositionDeadlineAlert,
    DispositionMatch,
    DispositionOfferNegotiationEvent,
    DispositionOfferRevision,
    EsignEnvelope,
    EsignRecipient,
    Lead,
    Transaction,
    TransactionChecklistItem,
    TransactionDocument,
    User,
)
from app.schemas.disposition_offer_room import (
    BuyerOutcomeCreate,
    BuyerOutcomeRead,
    BuyerSelectionRead,
    ClosingCheckpointCreate,
    ClosingCheckpointRead,
    ClosingCheckpointUpdate,
    DeadlineAlertRead,
    NegotiationEventRead,
    OfferNegotiationCreate,
    OfferPrimaryReplacementCreate,
    OfferRevisionRead,
    OfferRiskFlagRead,
    OfferRoomOfferCreate,
    OfferRoomOfferRead,
    OfferRoomOfferUpdate,
    OfferRoomRead,
    OfferSelectionCreate,
    ReplacementOptionRead,
    SelectionSlotRead,
    StrategyAgreementReadinessRead,
)
from app.services.dispositions import _proof_is_current_verified, audit, scoped_case
from app.services.lead_lifecycle import lock_organization_lead, require_lead_not_closed_out

ACTIVE_CASE_STATUSES = {
    "package_prep",
    "buyer_matching",
    "marketed",
    "offers_received",
    "buyer_selected",
}
VIABLE_OFFER_STATUSES = {"received", "countering", "backup", "selected"}
TERMINAL_CHECKPOINT_STATUSES = {"completed", "waived", "cancelled"}
MANAGER_PERMISSION = PermissionKeys.APPROVE_DISPOSITION_BUYER_SELECTION


def _aware(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def _canonical_hash(value: object) -> str:
    serialized = json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)
    return sha256(serialized.encode("utf-8")).hexdigest()


def _normalize_identity_text(value: str | None) -> str:
    return "".join(character for character in (value or "").casefold() if character.isalnum())


def _normalize_email(value: str | None) -> str:
    return (value or "").strip().casefold()


def _normalized_business_date(value: datetime | None) -> str | None:
    return _aware(value).date().isoformat() if value is not None else None


def _normalized_instant(value: datetime | None) -> str | None:
    return _aware(value).isoformat() if value is not None else None


def assignment_buyer_identity_snapshot(buyer: Buyer) -> dict[str, Any]:
    """Return the immutable normalized buyer identity bound to an assignment."""
    return {
        "name": buyer.name.strip(),
        "normalized_name": _normalize_identity_text(buyer.name),
        "company_name": buyer.company_name.strip() if buyer.company_name else None,
        "normalized_company_name": _normalize_identity_text(buyer.company_name),
        "email": _normalize_email(buyer.normalized_email or buyer.email) or None,
    }


def assignment_signer_identity_snapshot(
    binding: dict[str, Any],
    *,
    signer_name: str,
    signer_email: str,
    source: str,
) -> dict[str, Any]:
    """Validate the actual assignee against the buyer frozen into the package."""
    expected = binding.get("buyer_identity_snapshot")
    if not isinstance(expected, dict):
        raise ValueError("The assignment package is missing its selected-buyer identity binding.")
    normalized_name = _normalize_identity_text(signer_name)
    permitted_names = {
        str(expected.get("normalized_name") or ""),
        str(expected.get("normalized_company_name") or ""),
    } - {""}
    if not normalized_name or normalized_name not in permitted_names:
        raise ValueError(
            "The assignment assignee name or entity does not match the selected buyer."
        )
    normalized_email = _normalize_email(signer_email)
    expected_email = _normalize_email(str(expected.get("email") or ""))
    if not expected_email or normalized_email != expected_email:
        raise ValueError("The assignment assignee email does not match the selected buyer.")
    snapshot = {
        "source": source,
        "name": signer_name.strip(),
        "normalized_name": normalized_name,
        "email": normalized_email,
    }
    return {**snapshot, "identity_hash": _canonical_hash(snapshot)}


def assignment_offer_economics_snapshot(
    offer: BuyerOffer,
    transaction: Transaction,
    *,
    base_purchase_price_cents: int,
    earnest_money_cents: int | None,
    closing_date: datetime | None,
    inspection_period_days: int | None,
) -> dict[str, Any]:
    """Normalize assignment economics and reject a package that changed approved terms."""
    assignment_fee_cents = transaction.assignment_fee_cents
    if assignment_fee_cents is None:
        raise ValueError(
            "Record the assignment fee before drafting the buyer assignment agreement."
        )
    end_buyer_price_cents = base_purchase_price_cents + assignment_fee_cents
    if end_buyer_price_cents != offer.amount_cents:
        raise ValueError(
            "The assignment agreement economics do not equal the approved buyer offer."
        )
    if earnest_money_cents != offer.earnest_money_cents:
        raise ValueError(
            "The assignment agreement earnest money does not equal the approved buyer offer."
        )
    if _normalized_business_date(closing_date) != _normalized_business_date(
        offer.proposed_closing_at
    ):
        raise ValueError(
            "The assignment agreement closing date does not equal the approved buyer offer."
        )
    if inspection_period_days != offer.due_diligence_days:
        raise ValueError(
            "The assignment agreement inspection period does not equal the approved buyer offer."
        )
    return {
        "selected_offer_amount_cents": offer.amount_cents,
        "base_purchase_price_cents": base_purchase_price_cents,
        "assignment_fee_cents": assignment_fee_cents,
        "end_buyer_price_cents": end_buyer_price_cents,
        "earnest_money_cents": offer.earnest_money_cents,
        "deposit_due_at": _normalized_instant(offer.deposit_due_at),
        "closing_date": _normalized_business_date(offer.proposed_closing_at),
        "inspection_period_days": offer.due_diligence_days,
    }


def _has_substantive_evidence(value: object) -> bool:
    if value is None or value is False:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, dict):
        return any(_has_substantive_evidence(item) for item in value.values())
    if isinstance(value, (list, tuple, set)):
        return any(_has_substantive_evidence(item) for item in value)
    return True


def _has_deposit_evidence_note(value: object) -> bool:
    if not isinstance(value, dict):
        return False
    candidate = value.get("confirmation_note") or value.get("support_note")
    return isinstance(candidate, str) and len("".join(candidate.split())) >= 10


def _require_no_live_assignment_obligation(
    db: Session,
    principal: Principal,
    transaction: Transaction,
    *,
    action: str,
    offer_id: UUID | None = None,
) -> None:
    packages = list(
        db.scalars(
            select(ContractPackage).where(
                ContractPackage.organization_id == principal.organization_id,
                ContractPackage.transaction_id == transaction.id,
                ContractPackage.status.in_(("approved", "sending", "sent", "executed")),
            )
        ).all()
    )
    for package in packages:
        snapshot = package.terms_snapshot if isinstance(package.terms_snapshot, dict) else {}
        if str(snapshot.get("document_type")) != "assignment_contract":
            continue
        binding = snapshot.get("disposition_buyer_binding")
        if offer_id is not None and (
            not isinstance(binding, dict) or str(binding.get("offer_id")) != str(offer_id)
        ):
            continue
        if package.status == "executed":
            raise ValueError(f"Resolve the executed buyer assignment before {action}.")
        if package.status == "approved":
            raise ValueError(f"Void the approved buyer assignment package before {action}.")
        raise ValueError(f"Withdraw or cancel the active buyer assignment request before {action}.")


def _require_manager(principal: Principal) -> None:
    if MANAGER_PERMISSION not in principal.permission_keys:
        raise PermissionError(
            "Final buyer selection and replacement require disposition manager approval."
        )


def _lock_case(
    db: Session,
    principal: Principal,
    case_id: UUID,
    *,
    allowed_statuses: set[str] = ACTIVE_CASE_STATUSES,
) -> tuple[DispositionCase, Transaction]:
    existing = scoped_case(db, principal, case_id)
    if existing is None:
        raise LookupError("Disposition case not found.")
    lead = lock_organization_lead(
        db,
        organization_id=principal.organization_id,
        lead_id=existing.lead_id,
    )
    if lead is None:
        raise ValueError("The disposition lead is no longer available.")
    require_lead_not_closed_out(lead)
    require_house_workflow(lead.asset_class, workflow="Residential buyer disposition")
    transaction = db.scalar(
        select(Transaction)
        .where(
            Transaction.id == existing.transaction_id,
            Transaction.organization_id == principal.organization_id,
        )
        .with_for_update()
    )
    if transaction is None:
        raise ValueError("The disposition transaction is no longer available.")
    case = db.scalar(
        select(DispositionCase)
        .where(
            DispositionCase.id == case_id,
            DispositionCase.organization_id == principal.organization_id,
        )
        .execution_options(populate_existing=True)
        .with_for_update()
    )
    if case is None:
        raise LookupError("Disposition case not found.")
    if case.status not in allowed_statuses:
        raise ValueError(
            "Offer Room changes are unavailable while this disposition case is "
            f"{case.status.replace('_', ' ')}."
        )
    return case, transaction


def _scoped_buyer(db: Session, principal: Principal, buyer_id: UUID) -> Buyer | None:
    return db.scalar(
        select(Buyer).where(
            Buyer.id == buyer_id,
            Buyer.organization_id == principal.organization_id,
            Buyer.archived_at.is_(None),
        )
    )


def _scoped_proof(
    db: Session,
    principal: Principal,
    buyer_id: UUID,
    proof_document_id: UUID | None,
) -> BuyerProofDocument | None:
    if proof_document_id is None:
        return None
    return db.scalar(
        select(BuyerProofDocument).where(
            BuyerProofDocument.id == proof_document_id,
            BuyerProofDocument.organization_id == principal.organization_id,
            BuyerProofDocument.buyer_id == buyer_id,
            BuyerProofDocument.deleted_at.is_(None),
        )
    )


def _terms_snapshot(offer: BuyerOffer) -> dict[str, Any]:
    return {
        "amount_cents": offer.amount_cents,
        "earnest_money_cents": offer.earnest_money_cents,
        "deposit_due_at": offer.deposit_due_at.isoformat() if offer.deposit_due_at else None,
        "due_diligence_days": offer.due_diligence_days,
        "contingencies": list(offer.contingencies or []),
        "contingencies_confirmed": offer.contingencies_confirmed,
        "proposed_closing_at": (
            offer.proposed_closing_at.isoformat() if offer.proposed_closing_at else None
        ),
        "funding_method": offer.financing_type,
        "funding_confidence_basis_points": offer.funding_confidence_basis_points,
        "proof_document_id": str(offer.proof_document_id) if offer.proof_document_id else None,
        "special_terms": offer.special_terms,
        "notes": offer.notes,
        "status": offer.status,
    }


def _risk_and_score(
    offer: BuyerOffer,
    buyer: Buyer,
    proof: BuyerProofDocument | None,
    *,
    now: datetime,
    max_amount_cents: int,
    prior_retrades: int,
) -> tuple[int, list[dict[str, Any]], list[str], int, list[str]]:
    flags: list[dict[str, Any]] = []
    strengths: list[str] = []
    blockers: list[str] = []
    risk = 0

    proof_current = proof is not None and _proof_is_current_verified(proof, now=now)
    proof_amount = proof.verified_amount_cents if proof_current and proof else None
    if proof is None:
        risk += 2600
        blockers.append("Current verified proof of funds is missing.")
        flags.append(
            {
                "code": "proof_missing",
                "severity": "danger",
                "message": "No proof-of-funds document is attached.",
                "evidence": {"proof_document_id": None},
            }
        )
    elif not proof_current:
        risk += 2400
        blockers.append("Proof of funds is expired or unverified.")
        flags.append(
            {
                "code": "proof_not_current",
                "severity": "danger",
                "message": "The attached proof is expired or has not been verified.",
                "evidence": {
                    "status": proof.status,
                    "expires_at": proof.expires_at.isoformat() if proof.expires_at else None,
                },
            }
        )
    elif proof_amount is None or proof_amount < offer.amount_cents:
        risk += 2200
        blockers.append("Verified funds do not cover the offer amount.")
        flags.append(
            {
                "code": "proof_insufficient",
                "severity": "danger",
                "message": "Verified funds do not cover this offer.",
                "evidence": {
                    "verified_amount_cents": proof_amount,
                    "offer_amount_cents": offer.amount_cents,
                },
            }
        )
    else:
        strengths.append("Current verified funds cover the offer.")

    deposit_bps = (
        round((offer.earnest_money_cents or 0) * 10000 / offer.amount_cents)
        if offer.amount_cents
        else 0
    )
    if offer.earnest_money_cents is None:
        risk += 1000
        flags.append(
            {
                "code": "deposit_missing",
                "severity": "warning",
                "message": "No earnest-money deposit is stated.",
                "evidence": {"earnest_money_cents": offer.earnest_money_cents},
            }
        )
    elif offer.earnest_money_cents == 0:
        risk += 1000
        flags.append(
            {
                "code": "deposit_zero",
                "severity": "warning",
                "message": "The buyer offer explicitly requires no earnest-money deposit.",
                "evidence": {"earnest_money_cents": 0},
            }
        )
    elif deposit_bps < 100:
        risk += 650
        flags.append(
            {
                "code": "deposit_weak",
                "severity": "warning",
                "message": "The deposit is less than 1% of the offer.",
                "evidence": {"deposit_basis_points": deposit_bps},
            }
        )
    else:
        strengths.append("Deposit is at least 1% of the offer.")
    if offer.earnest_money_cents and offer.deposit_due_at is None:
        risk += 350
        flags.append(
            {
                "code": "deposit_due_missing",
                "severity": "warning",
                "message": "The deposit has no due date.",
                "evidence": {},
            }
        )

    if offer.due_diligence_days is not None and offer.due_diligence_days > 14:
        risk += min(1000, (offer.due_diligence_days - 14) * 60)
        flags.append(
            {
                "code": "due_diligence_long",
                "severity": "warning",
                "message": "The requested due-diligence period exceeds 14 days.",
                "evidence": {"due_diligence_days": offer.due_diligence_days},
            }
        )
    elif offer.due_diligence_days is not None:
        strengths.append("Due-diligence timing is 14 days or less.")

    if offer.contingencies:
        risk += min(1600, len(offer.contingencies) * 400)
        flags.append(
            {
                "code": "contingencies_present",
                "severity": "warning",
                "message": "The offer includes contingencies requiring review.",
                "evidence": {"contingencies": list(offer.contingencies)},
            }
        )
    elif offer.contingencies_confirmed:
        strengths.append("No buyer contingencies are recorded.")
    else:
        risk += 700
        flags.append(
            {
                "code": "contingencies_unknown",
                "severity": "warning",
                "message": "Buyer contingency terms have not been confirmed.",
                "evidence": {"contingencies_confirmed": False},
            }
        )

    if offer.proposed_closing_at is None:
        risk += 500
        flags.append(
            {
                "code": "closing_date_missing",
                "severity": "warning",
                "message": "No proposed closing date is recorded.",
                "evidence": {},
            }
        )
    elif _aware(offer.proposed_closing_at) <= now:
        risk += 1500
        blockers.append("The proposed closing date has passed.")
        flags.append(
            {
                "code": "closing_date_past",
                "severity": "danger",
                "message": "The proposed closing date has passed.",
                "evidence": {"proposed_closing_at": offer.proposed_closing_at.isoformat()},
            }
        )

    if offer.financing_type.strip().lower() in {"", "unknown", "not confirmed"}:
        risk += 700
        flags.append(
            {
                "code": "funding_method_unknown",
                "severity": "warning",
                "message": "The buyer's funding method has not been confirmed.",
                "evidence": {"funding_method": offer.financing_type},
            }
        )
    if offer.funding_confidence_basis_points < 6000:
        risk += round((6000 - offer.funding_confidence_basis_points) * 0.25)
        flags.append(
            {
                "code": "funding_confidence_low",
                "severity": "warning",
                "message": "Recorded funding confidence is below 60%.",
                "evidence": {
                    "funding_confidence_basis_points": (offer.funding_confidence_basis_points)
                },
            }
        )
    if buyer.failed_deals:
        risk += min(1200, buyer.failed_deals * 250)
        flags.append(
            {
                "code": "prior_fallout",
                "severity": "warning",
                "message": "Buyer history includes failed deals.",
                "evidence": {
                    "completed_deals": buyer.completed_deals,
                    "failed_deals": buyer.failed_deals,
                },
            }
        )
    if prior_retrades:
        risk += min(1000, prior_retrades * 250)
        flags.append(
            {
                "code": "prior_retrade",
                "severity": "warning",
                "message": "Buyer history includes retrade activity.",
                "evidence": {"retrade_count": prior_retrades},
            }
        )

    price_score = round(4000 * offer.amount_cents / max(max_amount_cents, 1))
    proof_score = (
        2000 if proof_current and proof_amount and proof_amount >= offer.amount_cents else 0
    )
    deposit_score = min(1000, deposit_bps * 10)
    funding_score = round(offer.funding_confidence_basis_points * 0.15)
    reliability_score = round(buyer.reliability_score_basis_points * 0.15)
    terms_score = (
        max(0, 500 - len(offer.contingencies or []) * 100) if offer.contingencies_confirmed else 0
    )
    execution_score = max(
        0,
        min(
            10000,
            price_score
            + proof_score
            + deposit_score
            + funding_score
            + reliability_score
            + terms_score
            - round(min(risk, 10000) * 0.2),
        ),
    )
    return min(risk, 10000), flags, strengths, execution_score, blockers


def _offer_revision(
    db: Session,
    principal: Principal,
    case: DispositionCase,
    offer: BuyerOffer,
    *,
    idempotency_key: str,
    change_reason: str,
) -> DispositionOfferRevision:
    prior_count = len(
        db.scalars(
            select(DispositionOfferRevision.id).where(DispositionOfferRevision.offer_id == offer.id)
        ).all()
    )
    buyer = db.get(Buyer, offer.buyer_id)
    proof = _scoped_proof(db, principal, offer.buyer_id, offer.proof_document_id)
    assert buyer is not None
    risk, flags, strengths, score, blockers = _risk_and_score(
        offer,
        buyer,
        proof,
        now=datetime.now(UTC),
        max_amount_cents=offer.amount_cents,
        prior_retrades=0,
    )
    revision = DispositionOfferRevision(
        organization_id=principal.organization_id,
        disposition_case_id=case.id,
        offer_id=offer.id,
        buyer_id=offer.buyer_id,
        created_by_user_id=principal.user_id,
        revision_number=prior_count + 1,
        idempotency_key=idempotency_key,
        terms_snapshot=_terms_snapshot(offer),
        risk_snapshot={
            "risk_score_basis_points": risk,
            "risk_flags": flags,
            "strengths": strengths,
            "execution_score_basis_points": score,
            "selection_blockers": blockers,
            "evaluated_at": datetime.now(UTC).isoformat(),
        },
        change_reason=change_reason,
    )
    db.add(revision)
    return revision


def create_offer(
    db: Session,
    principal: Principal,
    case_id: UUID,
    payload: OfferRoomOfferCreate,
) -> OfferRoomRead:
    case, _ = _lock_case(db, principal, case_id)
    existing = db.scalar(
        select(BuyerOffer).where(
            BuyerOffer.organization_id == principal.organization_id,
            BuyerOffer.disposition_case_id == case.id,
            BuyerOffer.idempotency_key == payload.idempotency_key,
        )
    )
    if existing is not None:
        return read_workspace(db, principal, case.id)
    buyer = _scoped_buyer(db, principal, payload.buyer_id)
    if buyer is None:
        raise ValueError("Buyer not found or archived.")
    proof = _scoped_proof(db, principal, buyer.id, payload.proof_document_id)
    if payload.proof_document_id is not None and proof is None:
        raise ValueError("The selected proof-of-funds document is unavailable for this buyer.")
    now = datetime.now(UTC)
    offer = BuyerOffer(
        organization_id=principal.organization_id,
        lead_id=case.lead_id,
        deal_id=case.deal_id,
        buyer_id=buyer.id,
        disposition_case_id=case.id,
        proof_document_id=proof.id if proof else None,
        idempotency_key=payload.idempotency_key,
        lock_version=1,
        amount_cents=payload.amount_cents,
        earnest_money_cents=payload.earnest_money_cents,
        financing_type=payload.funding_method,
        funding_confidence_basis_points=payload.funding_confidence_basis_points,
        due_diligence_days=payload.due_diligence_days,
        contingencies=payload.contingencies,
        contingencies_confirmed=payload.contingencies_confirmed,
        proposed_closing_at=payload.proposed_closing_at,
        special_terms=payload.special_terms,
        status="received",
        proof_of_funds_received=proof is not None,
        notes=payload.notes,
        received_at=now,
        deposit_due_at=payload.deposit_due_at,
        deposit_received_at=None,
        selected_at=None,
    )
    db.add(offer)
    db.flush()
    _offer_revision(
        db,
        principal,
        case,
        offer,
        idempotency_key=payload.idempotency_key,
        change_reason=payload.change_reason,
    )
    if case.status != "buyer_selected":
        case.status = "offers_received"
    audit(
        db,
        principal,
        "disposition.offer_created",
        "buyer_offer",
        offer.id,
        {"buyer_id": str(buyer.id), "amount_cents": offer.amount_cents},
        payload.change_reason,
    )
    db.commit()
    return read_workspace(db, principal, case.id)


def revise_offer(
    db: Session,
    principal: Principal,
    case_id: UUID,
    offer_id: UUID,
    payload: OfferRoomOfferUpdate,
) -> OfferRoomRead:
    case, transaction = _lock_case(db, principal, case_id)
    existing_revision = db.scalar(
        select(DispositionOfferRevision).where(
            DispositionOfferRevision.organization_id == principal.organization_id,
            DispositionOfferRevision.disposition_case_id == case.id,
            DispositionOfferRevision.idempotency_key == payload.idempotency_key,
        )
    )
    if existing_revision is not None:
        return read_workspace(db, principal, case.id)
    offer = db.scalar(
        select(BuyerOffer)
        .where(
            BuyerOffer.id == offer_id,
            BuyerOffer.organization_id == principal.organization_id,
            BuyerOffer.disposition_case_id == case.id,
        )
        .with_for_update()
    )
    if offer is None:
        raise LookupError("Offer not found.")
    if offer.status not in VIABLE_OFFER_STATUSES:
        raise ValueError("Terminal offers cannot be revised.")
    if offer.lock_version != payload.expected_lock_version:
        raise ValueError("Offer changed since it was opened. Refresh the Offer Room and retry.")
    if offer.status == "selected":
        _require_no_live_assignment_obligation(
            db,
            principal,
            transaction,
            action="revising the selected buyer's offer",
            offer_id=offer.id,
        )
    fields = payload.model_fields_set
    mapping = {
        "amount_cents": "amount_cents",
        "earnest_money_cents": "earnest_money_cents",
        "deposit_due_at": "deposit_due_at",
        "due_diligence_days": "due_diligence_days",
        "contingencies": "contingencies",
        "contingencies_confirmed": "contingencies_confirmed",
        "proposed_closing_at": "proposed_closing_at",
        "funding_method": "financing_type",
        "funding_confidence_basis_points": "funding_confidence_basis_points",
        "special_terms": "special_terms",
        "notes": "notes",
    }
    for input_name, model_name in mapping.items():
        if input_name in fields:
            setattr(offer, model_name, getattr(payload, input_name))
    if "proof_document_id" in fields:
        proof = _scoped_proof(db, principal, offer.buyer_id, payload.proof_document_id)
        if payload.proof_document_id is not None and proof is None:
            raise ValueError("The selected proof-of-funds document is unavailable for this buyer.")
        offer.proof_document_id = proof.id if proof else None
        offer.proof_of_funds_received = proof is not None
    offer.lock_version += 1
    _offer_revision(
        db,
        principal,
        case,
        offer,
        idempotency_key=payload.idempotency_key,
        change_reason=payload.change_reason,
    )
    audit(
        db,
        principal,
        "disposition.offer_revised",
        "buyer_offer",
        offer.id,
        {"lock_version": offer.lock_version, "changed_fields": sorted(fields)},
        payload.change_reason,
    )
    db.commit()
    return read_workspace(db, principal, case.id)


def record_negotiation(
    db: Session,
    principal: Principal,
    case_id: UUID,
    offer_id: UUID,
    payload: OfferNegotiationCreate,
) -> OfferRoomRead:
    case, _ = _lock_case(db, principal, case_id)
    existing = db.scalar(
        select(DispositionOfferNegotiationEvent).where(
            DispositionOfferNegotiationEvent.organization_id == principal.organization_id,
            DispositionOfferNegotiationEvent.disposition_case_id == case.id,
            DispositionOfferNegotiationEvent.idempotency_key == payload.idempotency_key,
        )
    )
    if existing is not None:
        return read_workspace(db, principal, case.id)
    offer = db.scalar(
        select(BuyerOffer)
        .where(
            BuyerOffer.id == offer_id,
            BuyerOffer.organization_id == principal.organization_id,
            BuyerOffer.disposition_case_id == case.id,
        )
        .with_for_update()
    )
    if offer is None:
        raise LookupError("Offer not found.")
    db.add(
        DispositionOfferNegotiationEvent(
            organization_id=principal.organization_id,
            disposition_case_id=case.id,
            offer_id=offer.id,
            buyer_id=offer.buyer_id,
            actor_user_id=principal.user_id,
            event_type=payload.event_type,
            direction=payload.direction,
            summary=payload.summary,
            metadata_snapshot=payload.metadata,
            occurred_at=payload.occurred_at or datetime.now(UTC),
            idempotency_key=payload.idempotency_key,
        )
    )
    if payload.event_type in {"counter", "retrade"} and offer.status == "received":
        offer.status = "countering"
    db.commit()
    return read_workspace(db, principal, case.id)


def _lock_offers(
    db: Session,
    principal: Principal,
    case: DispositionCase,
    offer_ids: list[UUID],
) -> list[BuyerOffer]:
    rows = list(
        db.scalars(
            select(BuyerOffer)
            .where(
                BuyerOffer.organization_id == principal.organization_id,
                BuyerOffer.disposition_case_id == case.id,
                BuyerOffer.id.in_(offer_ids),
            )
            .order_by(BuyerOffer.id)
            .with_for_update()
        ).all()
    )
    if len(rows) != len(set(offer_ids)):
        raise ValueError("One or more selected offers are unavailable.")
    return rows


def _validate_primary(
    db: Session,
    principal: Principal,
    case: DispositionCase,
    offer: BuyerOffer,
    *,
    override_reason: str | None,
) -> None:
    buyer = db.scalar(
        select(Buyer).where(
            Buyer.id == offer.buyer_id,
            Buyer.organization_id == principal.organization_id,
        )
    )
    proof = _scoped_proof(db, principal, offer.buyer_id, offer.proof_document_id)
    now = datetime.now(UTC)
    if offer.amount_cents < case.minimum_acceptable_cents:
        raise ValueError("Primary offer must meet Stonegate's approved minimum price.")
    issues: list[str] = []
    if buyer is None or buyer.status != "active" or buyer.archived_at is not None:
        issues.append("buyer is inactive or archived")
    if (
        proof is None
        or not _proof_is_current_verified(proof, now=now)
        or proof.verified_amount_cents is None
        or proof.verified_amount_cents < offer.amount_cents
    ):
        issues.append("current verified proof does not cover the offer")
    if offer.proposed_closing_at and _aware(offer.proposed_closing_at) <= now:
        issues.append("proposed closing date has passed")
    match = db.scalar(
        select(DispositionMatch).where(
            DispositionMatch.organization_id == principal.organization_id,
            DispositionMatch.disposition_case_id == case.id,
            DispositionMatch.buyer_id == offer.buyer_id,
            DispositionMatch.qualification_status == "qualified",
        )
    )
    if match is None:
        issues.append("buyer has no qualified House match for this deal")
    if issues and not override_reason:
        raise ValueError(
            "Primary offer is not selection-ready: " + "; ".join(issues) + ". "
            "A disposition manager may record an explicit eligibility override."
        )


def _selection_snapshot(offer: BuyerOffer) -> dict[str, Any]:
    return {
        "offer_id": str(offer.id),
        "buyer_id": str(offer.buyer_id),
        "lock_version": offer.lock_version,
        "terms": _terms_snapshot(offer),
    }


def _coverage_snapshot(
    db: Session,
    principal: Principal,
    case: DispositionCase,
    offer: BuyerOffer,
) -> dict[str, Any]:
    return _coverage_snapshot_for_org(
        db,
        principal.organization_id,
        case,
        offer,
    )


def _coverage_snapshot_for_org(
    db: Session,
    organization_id: UUID,
    case: DispositionCase,
    offer: BuyerOffer,
) -> dict[str, Any]:
    buyer = db.scalar(
        select(Buyer).where(
            Buyer.id == offer.buyer_id,
            Buyer.organization_id == organization_id,
        )
    )
    proof = (
        db.scalar(
            select(BuyerProofDocument).where(
                BuyerProofDocument.id == offer.proof_document_id,
                BuyerProofDocument.organization_id == organization_id,
                BuyerProofDocument.buyer_id == offer.buyer_id,
                BuyerProofDocument.deleted_at.is_(None),
            )
        )
        if offer.proof_document_id is not None
        else None
    )
    now = datetime.now(UTC)
    blockers: list[str] = []
    if buyer is None or buyer.status != "active" or buyer.archived_at is not None:
        blockers.append("Buyer is inactive or archived.")
    if offer.amount_cents < case.minimum_acceptable_cents:
        blockers.append("Offer is below Stonegate's approved minimum.")
    if (
        proof is None
        or not _proof_is_current_verified(proof, now=now)
        or proof.verified_amount_cents is None
        or proof.verified_amount_cents < offer.amount_cents
    ):
        blockers.append("Current verified proof does not cover the offer.")
    if offer.proposed_closing_at and _aware(offer.proposed_closing_at) <= now:
        blockers.append("Proposed closing date has passed.")
    qualified_match = db.scalar(
        select(DispositionMatch).where(
            DispositionMatch.organization_id == organization_id,
            DispositionMatch.disposition_case_id == case.id,
            DispositionMatch.buyer_id == offer.buyer_id,
        )
    )
    if qualified_match is None or qualified_match.qualification_status != "qualified":
        blockers.append("Buyer has no qualified House match for this deal.")
    return {
        "readiness_status": "ready" if not blockers else "provisional",
        "readiness_blockers": blockers,
        "readiness_evidence": {
            "evaluated_at": now.isoformat(),
            "buyer_status": buyer.status if buyer is not None else None,
            "buyer_archived_at": (
                buyer.archived_at.isoformat() if buyer is not None and buyer.archived_at else None
            ),
            "proof_document_id": str(proof.id) if proof is not None else None,
            "proof_verified_at": (
                proof.verified_at.isoformat() if proof is not None and proof.verified_at else None
            ),
            "proof_expires_at": (
                proof.expires_at.isoformat() if proof is not None and proof.expires_at else None
            ),
            "qualified_match_id": (
                str(qualified_match.id) if qualified_match is not None else None
            ),
            "qualified_match_status": (
                qualified_match.qualification_status if qualified_match is not None else None
            ),
            "qualified_match_updated_at": (
                qualified_match.updated_at.isoformat()
                if qualified_match is not None and qualified_match.updated_at
                else None
            ),
        },
    }


def load_current_assignment_authority(
    db: Session,
    organization_id: UUID,
    transaction: Transaction,
    *,
    lock: bool,
) -> tuple[
    DispositionCase,
    DispositionBuyerSelection,
    DispositionBuyerSelectionSlot,
    BuyerOffer,
    Buyer,
]:
    def statement_for(model: type[Any], *criteria: Any) -> Any:
        statement = select(model).where(*criteria)
        return statement.with_for_update(of=model) if lock else statement

    case = db.scalar(
        statement_for(
            DispositionCase,
            DispositionCase.organization_id == organization_id,
            DispositionCase.transaction_id == transaction.id,
            DispositionCase.strategy == "assignment",
            DispositionCase.status == "buyer_selected",
        )
    )
    if case is None:
        raise ValueError(
            "Approve current primary and backup buyer coverage before using an assignment "
            "agreement."
        )
    selection = db.scalar(
        statement_for(
            DispositionBuyerSelection,
            DispositionBuyerSelection.organization_id == organization_id,
            DispositionBuyerSelection.disposition_case_id == case.id,
            DispositionBuyerSelection.status == "active",
        )
    )
    if selection is None or selection.approved_by_user_id is None:
        raise ValueError("The assignment buyer selection is no longer active and approved.")
    primary_slot = db.scalar(
        statement_for(
            DispositionBuyerSelectionSlot,
            DispositionBuyerSelectionSlot.selection_id == selection.id,
            DispositionBuyerSelectionSlot.role == "primary",
        )
    )
    if primary_slot is None:
        raise ValueError("The active assignment selection has no primary buyer.")
    offer = db.scalar(
        statement_for(
            BuyerOffer,
            BuyerOffer.id == primary_slot.offer_id,
            BuyerOffer.organization_id == organization_id,
            BuyerOffer.disposition_case_id == case.id,
        )
    )
    buyer = db.scalar(
        statement_for(
            Buyer,
            Buyer.id == primary_slot.buyer_id,
            Buyer.organization_id == organization_id,
        )
    )
    if offer is None or buyer is None:
        raise ValueError("The approved primary buyer or offer is no longer available.")
    if (
        offer.buyer_id != buyer.id
        or primary_slot.offer_id != offer.id
        or primary_slot.buyer_id != buyer.id
        or offer.status != "selected"
    ):
        raise ValueError("The active assignment primary-buyer coverage is inconsistent.")
    if int(primary_slot.offer_snapshot.get("lock_version", 0)) != offer.lock_version:
        raise ValueError(
            "The approved primary offer changed. Reapprove buyer coverage before continuing."
        )
    return case, selection, primary_slot, offer, buyer


def validate_assignment_package_authority(
    db: Session,
    transaction: Transaction,
    package: ContractPackage,
    *,
    gate: str,
    lock: bool = False,
) -> dict[str, Any] | None:
    """Prevent a stale or replaced selected buyer from receiving/executing an assignment."""
    snapshot = package.terms_snapshot if isinstance(package.terms_snapshot, dict) else {}
    if str(snapshot.get("document_type") or "purchase_agreement") != "assignment_contract":
        return None
    if (
        package.organization_id != transaction.organization_id
        or package.transaction_id != transaction.id
    ):
        raise ValueError("The assignment package does not match its Stonegate transaction.")
    binding = snapshot.get("disposition_buyer_binding")
    if not isinstance(binding, dict):
        raise ValueError(
            f"This assignment has no governed selected-buyer binding. Redraft it before {gate}."
        )
    case, selection, primary_slot, offer, buyer = load_current_assignment_authority(
        db,
        transaction.organization_id,
        transaction,
        lock=lock,
    )
    if (
        str(binding.get("case_id")) != str(case.id)
        or str(binding.get("offer_id")) != str(offer.id)
        or str(binding.get("buyer_id")) != str(buyer.id)
        or int(binding.get("offer_lock_version") or 0) != offer.lock_version
    ):
        raise ValueError(
            f"The assignment's selected-buyer authority is stale before {gate}. "
            "Redraft it for the current approved primary buyer."
        )
    try:
        bound_selection_id = UUID(str(binding.get("selection_id")))
    except (TypeError, ValueError) as exc:
        raise ValueError("The assignment package has an invalid buyer-selection binding.") from exc
    seen: set[UUID] = set()
    lineage_matches = False
    while bound_selection_id not in seen:
        if bound_selection_id == selection.id:
            lineage_matches = True
            break
        seen.add(bound_selection_id)
        statement = select(DispositionBuyerSelection).where(
            DispositionBuyerSelection.id == bound_selection_id,
            DispositionBuyerSelection.organization_id == transaction.organization_id,
            DispositionBuyerSelection.disposition_case_id == case.id,
        )
        if lock:
            statement = statement.with_for_update(of=DispositionBuyerSelection)
        prior = db.scalar(statement)
        if prior is None or prior.superseded_by_selection_id is None:
            break
        bound_selection_id = prior.superseded_by_selection_id
    if not lineage_matches:
        raise ValueError(
            f"The assignment buyer-selection lineage is stale before {gate}. Redraft it."
        )
    expected_identity = assignment_buyer_identity_snapshot(buyer)
    if binding.get("buyer_identity_snapshot") != expected_identity:
        raise ValueError(
            f"The assignment buyer identity changed before {gate}. Redraft the agreement."
        )
    expected_economics = assignment_offer_economics_snapshot(
        offer,
        transaction,
        base_purchase_price_cents=package.purchase_price_cents,
        earnest_money_cents=package.earnest_money_cents,
        closing_date=package.closing_date,
        inspection_period_days=package.inspection_period_days,
    )
    if binding.get("offer_economics_snapshot") != expected_economics or binding.get(
        "offer_economics_hash"
    ) != _canonical_hash(expected_economics):
        raise ValueError(f"The assignment economics changed before {gate}. Redraft the agreement.")
    coverage = _coverage_snapshot_for_org(
        db,
        transaction.organization_id,
        case,
        offer,
    )
    if coverage["readiness_blockers"]:
        raise ValueError(
            f"The selected buyer is no longer assignment-ready before {gate}: "
            + "; ".join(coverage["readiness_blockers"])
        )
    return {
        "case": case,
        "selection": selection,
        "primary_slot": primary_slot,
        "offer": offer,
        "buyer": buyer,
        "binding": binding,
    }


def _assignment_execution_identity_is_valid(
    db: Session,
    transaction: Transaction,
    package: ContractPackage,
    binding: dict[str, Any],
) -> bool:
    def valid_identity_evidence(
        evidence: object,
        *,
        signer_name: str,
        signer_email: str,
        source: str,
    ) -> bool:
        if not isinstance(evidence, dict) or evidence.get("source") != source:
            return False
        try:
            expected = assignment_signer_identity_snapshot(
                binding,
                signer_name=signer_name,
                signer_email=signer_email,
                source=source,
            )
        except ValueError:
            return False
        return all(
            evidence.get(key) == expected.get(key)
            for key in ("source", "name", "normalized_name", "email", "identity_hash")
        )

    package_snapshot = package.terms_snapshot or {}
    manual_evidence = package_snapshot.get("assignment_execution_identity")
    if isinstance(manual_evidence, dict) and valid_identity_evidence(
        manual_evidence,
        signer_name=str(manual_evidence.get("name") or ""),
        signer_email=str(manual_evidence.get("email") or ""),
        source="manual_execution_attestation",
    ):
        try:
            document_id = UUID(str(manual_evidence.get("document_id")))
        except (TypeError, ValueError):
            document_id = None
        if document_id is not None:
            document = db.scalar(
                select(TransactionDocument).where(
                    TransactionDocument.id == document_id,
                    TransactionDocument.organization_id == transaction.organization_id,
                    TransactionDocument.transaction_id == transaction.id,
                    TransactionDocument.contract_package_id == package.id,
                    TransactionDocument.document_type == "assignment_contract",
                    TransactionDocument.status == "executed",
                    TransactionDocument.deleted_at.is_(None),
                )
            )
            if document is not None and document.sha256 == manual_evidence.get(
                "document_sha256"
            ):
                return True

    envelopes = list(
        db.scalars(
            select(EsignEnvelope).where(
                EsignEnvelope.organization_id == transaction.organization_id,
                EsignEnvelope.transaction_id == transaction.id,
                EsignEnvelope.contract_package_id == package.id,
                EsignEnvelope.status == "completed",
                EsignEnvelope.completed_document_id.is_not(None),
            )
        ).all()
    )
    for envelope in envelopes:
        completed_document = db.scalar(
            select(TransactionDocument).where(
                TransactionDocument.id == envelope.completed_document_id,
                TransactionDocument.organization_id == transaction.organization_id,
                TransactionDocument.transaction_id == transaction.id,
                TransactionDocument.contract_package_id == package.id,
                TransactionDocument.document_type == "assignment_contract",
                TransactionDocument.status == "executed",
                TransactionDocument.deleted_at.is_(None),
            )
        )
        if completed_document is None:
            continue
        assignees = [
            recipient
            for recipient in db.scalars(
                select(EsignRecipient).where(
                    EsignRecipient.esign_envelope_id == envelope.id,
                    EsignRecipient.organization_id == transaction.organization_id,
                )
            ).all()
            if any(
                role in recipient.placeholder_name.strip().casefold()
                for role in ("assignee", "end buyer")
            )
        ]
        if (
            len(assignees) != 1
            or assignees[0].status != "signed"
            or assignees[0].signed_at is None
        ):
            continue
        provider_evidence = (envelope.provider_payload or {}).get(
            "assignment_execution_identity"
        )
        if valid_identity_evidence(
            provider_evidence,
            signer_name=assignees[0].name,
            signer_email=assignees[0].email,
            source="esign_recipient",
        ):
            return True
    return False


def has_current_executed_assignment_agreement(
    db: Session,
    transaction: Transaction,
    *,
    lock: bool = False,
) -> bool:
    """Return true only for an executed assignment bound to the current approved buyer."""
    statement = select(ContractPackage).where(
        ContractPackage.organization_id == transaction.organization_id,
        ContractPackage.transaction_id == transaction.id,
        ContractPackage.status == "executed",
    )
    if lock:
        statement = statement.with_for_update(of=ContractPackage)
    for package in db.scalars(statement).all():
        try:
            authority = validate_assignment_package_authority(
                db,
                transaction,
                package,
                gate="confirming executed buyer-agreement evidence",
                lock=lock,
            )
        except ValueError:
            continue
        if authority is not None and _assignment_execution_identity_is_valid(
            db,
            transaction,
            package,
            authority["binding"],
        ):
            return True
    return False


def _strategy_agreement_readiness(
    case: DispositionCase,
    *,
    assignment_execution_verified: bool,
) -> StrategyAgreementReadinessRead:
    if case.strategy == "assignment":
        return StrategyAgreementReadinessRead(
            strategy="assignment",
            label="Buyer assignment executed",
            ready=assignment_execution_verified,
            blockers=(
                []
                if assignment_execution_verified
                else [
                    "Complete the governed assignment and signature workflow for the current "
                    "approved buyer."
                ]
            ),
        )
    if case.strategy == "double_close":
        return StrategyAgreementReadinessRead(
            strategy="double_close",
            label="End-buyer resale agreement executed",
            ready=False,
            blockers=[
                "A governed second-leg end-buyer agreement is not yet available in the "
                "Double Close workflow. Do not treat an assignment agreement as evidence."
            ],
        )
    return StrategyAgreementReadinessRead(
        strategy="novation",
        label="Novation buyer agreement executed",
        ready=False,
        blockers=[
            "A governed executed novation buyer agreement is not yet available in this "
            "workflow. Do not treat an assignment agreement as evidence."
        ],
    )


def build_assignment_buyer_binding(
    db: Session,
    principal: Principal,
    case: DispositionCase,
    transaction: Transaction,
    selection: DispositionBuyerSelection,
    primary_slot: DispositionBuyerSelectionSlot,
    offer: BuyerOffer,
    buyer: Buyer,
    *,
    base_purchase_price_cents: int,
    earnest_money_cents: int | None,
    closing_date: datetime | None,
    inspection_period_days: int | None,
) -> dict[str, Any]:
    """Build immutable assignment evidence from the live, manager-approved primary offer."""
    if selection.status != "active" or primary_slot.selection_id != selection.id:
        raise ValueError("Buyer coverage changed. Refresh the Offer Room before drafting.")
    if primary_slot.offer_id != offer.id or primary_slot.buyer_id != buyer.id:
        raise ValueError("The approved primary-buyer identity changed before drafting.")
    if offer.status != "selected":
        raise ValueError("The approved primary offer is no longer selected.")
    frozen_lock_version = int(primary_slot.offer_snapshot.get("lock_version", 0))
    if frozen_lock_version != offer.lock_version:
        raise ValueError(
            "The approved primary offer terms changed. Reapprove buyer coverage before drafting."
        )
    coverage = _coverage_snapshot(db, principal, case, offer)
    if coverage["readiness_blockers"]:
        raise ValueError(
            "The selected buyer is no longer assignment-ready: "
            + "; ".join(coverage["readiness_blockers"])
        )
    buyer_identity_snapshot = assignment_buyer_identity_snapshot(buyer)
    offer_economics_snapshot = assignment_offer_economics_snapshot(
        offer,
        transaction,
        base_purchase_price_cents=base_purchase_price_cents,
        earnest_money_cents=earnest_money_cents,
        closing_date=closing_date,
        inspection_period_days=inspection_period_days,
    )
    return {
        "case_id": str(case.id),
        "selection_id": str(selection.id),
        "offer_id": str(offer.id),
        "buyer_id": str(buyer.id),
        "offer_lock_version": offer.lock_version,
        "buyer_identity_snapshot": buyer_identity_snapshot,
        "offer_economics_snapshot": offer_economics_snapshot,
        "offer_economics_hash": _canonical_hash(offer_economics_snapshot),
    }


def _create_selection_record(
    db: Session,
    principal: Principal,
    case: DispositionCase,
    *,
    primary: BuyerOffer,
    backups: list[BuyerOffer],
    reason: str,
    idempotency_key: str,
    old_selection: DispositionBuyerSelection | None = None,
    approved_by_user_id: UUID | None = None,
    approved_at: datetime | None = None,
) -> DispositionBuyerSelection:
    now = approved_at or datetime.now(UTC)
    approver_id = approved_by_user_id or principal.user_id
    primary_snapshot = {
        **_selection_snapshot(primary),
        **_coverage_snapshot(db, principal, case, primary),
    }
    backup_snapshots = [
        {**_selection_snapshot(item), **_coverage_snapshot(db, principal, case, item)}
        for item in backups
    ]
    manifest = {
        "primary": primary_snapshot,
        "backups": backup_snapshots,
        "reason": reason,
        "approved_by_user_id": str(approver_id),
        "approved_at": now.isoformat(),
    }
    selection = DispositionBuyerSelection(
        organization_id=principal.organization_id,
        disposition_case_id=case.id,
        approved_by_user_id=approver_id,
        superseded_by_selection_id=None,
        status="active",
        lock_version=1,
        idempotency_key=idempotency_key,
        reason=reason,
        evidence_hash=_canonical_hash(manifest),
        approved_at=now,
        replaced_at=None,
    )
    if old_selection is not None:
        old_selection.status = "replaced"
        old_selection.replaced_at = now
        old_selection.lock_version += 1
        db.flush()
    db.add(selection)
    db.flush()
    if old_selection is not None:
        old_selection.superseded_by_selection_id = selection.id
    for role, rank, offer in [
        ("primary", 1, primary),
        *[("backup", index, item) for index, item in enumerate(backups, 1)],
    ]:
        db.add(
            DispositionBuyerSelectionSlot(
                organization_id=principal.organization_id,
                disposition_case_id=case.id,
                selection_id=selection.id,
                offer_id=offer.id,
                buyer_id=offer.buyer_id,
                role=role,
                rank=rank,
                offer_snapshot=(
                    primary_snapshot if role == "primary" else backup_snapshots[rank - 1]
                ),
            )
        )
    primary.status = "selected"
    primary.selected_at = now
    for backup in backups:
        backup.status = "backup"
    case.selected_buyer_id = primary.buyer_id
    case.backup_buyer_id = backups[0].buyer_id if backups else None
    case.selection_approved_by_user_id = approver_id
    case.selection_approved_at = now
    case.status = "buyer_selected"
    return selection


def select_buyers(
    db: Session,
    principal: Principal,
    case_id: UUID,
    payload: OfferSelectionCreate,
) -> OfferRoomRead:
    _require_manager(principal)
    case, transaction = _lock_case(db, principal, case_id)
    existing = db.scalar(
        select(DispositionBuyerSelection).where(
            DispositionBuyerSelection.organization_id == principal.organization_id,
            DispositionBuyerSelection.disposition_case_id == case.id,
            DispositionBuyerSelection.idempotency_key == payload.idempotency_key,
        )
    )
    if existing is not None:
        return read_workspace(db, principal, case.id)
    requested_ids = [payload.primary_offer_id, *payload.backup_offer_ids]
    current, current_slots = _current_selection_with_slots(db, principal, case.id)
    current_primary_slot = next(
        (item for item in current_slots if item.role == "primary"),
        None,
    )
    if (
        current_primary_slot is not None
        and current_primary_slot.offer_id != payload.primary_offer_id
    ):
        _require_no_live_assignment_obligation(
            db,
            principal,
            transaction,
            action="changing the approved primary buyer",
        )
    current_offer_ids = [item.offer_id for item in current_slots]
    locked_offers = _lock_offers(
        db,
        principal,
        case,
        list(dict.fromkeys([*requested_ids, *current_offer_ids])),
    )
    offer_by_id = {item.id: item for item in locked_offers}
    offers = [offer_by_id[item_id] for item_id in requested_ids]
    stale_offer_ids = [
        offer.id
        for offer in offers
        if offer.lock_version != payload.expected_offer_lock_versions[offer.id]
    ]
    if stale_offer_ids:
        raise ValueError("Offer terms changed. Refresh the Offer Room before approving buyers.")
    current = db.scalar(
        select(DispositionBuyerSelection)
        .where(
            DispositionBuyerSelection.organization_id == principal.organization_id,
            DispositionBuyerSelection.disposition_case_id == case.id,
            DispositionBuyerSelection.status == "active",
        )
        .with_for_update()
    )
    if current is not None and current.id != (
        current_slots[0].selection_id if current_slots else None
    ):
        raise ValueError("Buyer coverage changed. Refresh the Offer Room before approving buyers.")
    if current is not None and payload.expected_selection_lock_version != current.lock_version:
        raise ValueError("Buyer coverage changed. Refresh the Offer Room before approving buyers.")
    if current is None and payload.expected_selection_lock_version is not None:
        raise ValueError(
            "No active buyer coverage exists. Refresh the Offer Room before approving."
        )
    by_id = {item.id: item for item in offers}
    primary = by_id[payload.primary_offer_id]
    backups = [by_id[item_id] for item_id in payload.backup_offer_ids]
    if any(item.status not in VIABLE_OFFER_STATUSES for item in offers):
        raise ValueError("Only viable offers can be selected as primary or backup.")
    if len({item.buyer_id for item in offers}) != len(offers):
        raise ValueError("Primary and backup positions must belong to different buyers.")
    selected_buyers = {
        item.id: item
        for item in db.scalars(
            select(Buyer).where(
                Buyer.organization_id == principal.organization_id,
                Buyer.id.in_({item.buyer_id for item in offers}),
            )
        ).all()
    }
    if any(
        item.buyer_id not in selected_buyers
        or selected_buyers[item.buyer_id].status != "active"
        or selected_buyers[item.buyer_id].archived_at is not None
        for item in offers
    ):
        raise ValueError("Primary and backup coverage requires active, non-archived buyers.")
    _validate_primary(
        db,
        principal,
        case,
        primary,
        override_reason=payload.eligibility_override_reason,
    )
    prior_offer_ids = {item.offer_id for item in current_slots}
    requested_offer_ids = set(requested_ids)
    for old_offer_id in prior_offer_ids - requested_offer_ids:
        old_offer = offer_by_id[old_offer_id]
        if old_offer.status in {"selected", "backup"}:
            old_offer.status = "received"
            old_offer.selected_at = None
            old_offer.lock_version += 1
    selection = _create_selection_record(
        db,
        principal,
        case,
        primary=primary,
        backups=backups,
        reason=(
            payload.reason
            + (
                f" Eligibility override: {payload.eligibility_override_reason}"
                if payload.eligibility_override_reason
                else ""
            )
        ),
        idempotency_key=payload.idempotency_key,
        old_selection=current,
    )
    if current is not None:
        _cancel_selection_checkpoints(db, current.id)
    _sync_canonical_checkpoints(db, principal, case, transaction, selection, primary)
    audit(
        db,
        principal,
        "disposition.buyer_selection_approved",
        "disposition_buyer_selection",
        selection.id,
        {
            "primary_offer_id": str(primary.id),
            "backup_offer_ids": [str(item.id) for item in backups],
            "evidence_hash": selection.evidence_hash,
        },
        payload.reason,
    )
    db.commit()
    return read_workspace(db, principal, case.id)


def _current_selection_with_slots(
    db: Session,
    principal: Principal,
    case_id: UUID,
) -> tuple[DispositionBuyerSelection | None, list[DispositionBuyerSelectionSlot]]:
    selection = db.scalar(
        select(DispositionBuyerSelection).where(
            DispositionBuyerSelection.organization_id == principal.organization_id,
            DispositionBuyerSelection.disposition_case_id == case_id,
            DispositionBuyerSelection.status == "active",
        )
    )
    if selection is None:
        return None, []
    slots = list(
        db.scalars(
            select(DispositionBuyerSelectionSlot)
            .where(DispositionBuyerSelectionSlot.selection_id == selection.id)
            .order_by(DispositionBuyerSelectionSlot.role.desc(), DispositionBuyerSelectionSlot.rank)
        ).all()
    )
    return selection, slots


def replace_primary(
    db: Session,
    principal: Principal,
    case_id: UUID,
    selection_id: UUID,
    payload: OfferPrimaryReplacementCreate,
) -> OfferRoomRead:
    _require_manager(principal)
    case, transaction = _lock_case(db, principal, case_id, allowed_statuses={"buyer_selected"})
    replay = db.scalar(
        select(DispositionBuyerSelection).where(
            DispositionBuyerSelection.organization_id == principal.organization_id,
            DispositionBuyerSelection.disposition_case_id == case.id,
            DispositionBuyerSelection.idempotency_key == payload.idempotency_key,
        )
    )
    if replay is not None:
        return read_workspace(db, principal, case.id)
    current, slots = _current_selection_with_slots(db, principal, case.id)
    if current is None or current.id != selection_id:
        raise ValueError("The selected buyer coverage changed. Refresh the Offer Room and retry.")
    if current.lock_version != payload.expected_lock_version:
        raise ValueError("Buyer selection changed. Refresh the Offer Room and retry.")
    _require_no_live_assignment_obligation(
        db,
        principal,
        transaction,
        action="replacing the approved primary buyer",
    )
    primary_slot = next(item for item in slots if item.role == "primary")
    backup_slots = sorted(
        (item for item in slots if item.role == "backup"), key=lambda item: item.rank
    )
    replacement_slot = (
        next(
            (item for item in backup_slots if item.offer_id == payload.replacement_offer_id),
            None,
        )
        if payload.replacement_offer_id
        else (backup_slots[0] if backup_slots else None)
    )
    if replacement_slot is None:
        raise ValueError("Choose an available ranked backup before replacing the primary buyer.")
    offer_ids = [item.offer_id for item in slots]
    offers = _lock_offers(db, principal, case, offer_ids)
    offer_by_id = {item.id: item for item in offers}
    old_primary = offer_by_id[primary_slot.offer_id]
    replacement = offer_by_id[replacement_slot.offer_id]
    remaining = [
        offer_by_id[item.offer_id] for item in backup_slots if item.offer_id != replacement.id
    ]
    stale_backup_ids = [
        slot.offer_id
        for slot in backup_slots
        if int(slot.offer_snapshot.get("lock_version", 0))
        != offer_by_id[slot.offer_id].lock_version
    ]
    if stale_backup_ids:
        raise ValueError(
            "Approved backup terms changed. Reapprove buyer coverage before promoting a backup."
        )
    if replacement.status not in VIABLE_OFFER_STATUSES or any(
        item.status not in VIABLE_OFFER_STATUSES for item in remaining
    ):
        raise ValueError(
            "Approved backup coverage is no longer viable. Reapprove coverage before replacing."
        )
    locked_current = db.scalar(
        select(DispositionBuyerSelection)
        .where(DispositionBuyerSelection.id == current.id)
        .execution_options(populate_existing=True)
        .with_for_update()
    )
    assert locked_current is not None
    replacement_coverage = _coverage_snapshot(db, principal, case, replacement)
    if replacement_coverage["readiness_blockers"]:
        raise ValueError(
            "The replacement buyer is no longer ready: "
            + "; ".join(replacement_coverage["readiness_blockers"])
        )
    _validate_primary(db, principal, case, replacement, override_reason=None)
    _record_outcome_locked(
        db,
        principal,
        case,
        old_primary,
        selection=locked_current,
        outcome_type=payload.outcome_type,
        cause_category=payload.cause_category,
        reason=payload.reason,
        details=payload.details,
        evidence=payload.evidence,
        occurred_at=datetime.now(UTC),
        idempotency_key=f"replacement-outcome:{payload.idempotency_key}",
    )
    new_selection = _create_selection_record(
        db,
        principal,
        case,
        primary=replacement,
        backups=remaining,
        reason=payload.reason,
        idempotency_key=payload.idempotency_key,
        old_selection=locked_current,
    )
    _cancel_selection_checkpoints(db, locked_current.id)
    _sync_canonical_checkpoints(db, principal, case, transaction, new_selection, replacement)
    audit(
        db,
        principal,
        "disposition.primary_buyer_replaced",
        "disposition_buyer_selection",
        new_selection.id,
        {
            "prior_selection_id": str(locked_current.id),
            "prior_primary_offer_id": str(old_primary.id),
            "replacement_offer_id": str(replacement.id),
        },
        payload.reason,
    )
    db.commit()
    return read_workspace(db, principal, case.id)


def _checkpoint_status_from_source(status: str, completed_at: datetime | None) -> str:
    if completed_at is not None or status in {"complete", "completed"}:
        return "completed"
    if status in {"cancelled", "canceled", "not_applicable"}:
        return "cancelled" if status != "not_applicable" else "waived"
    if status in {"blocked", "in_progress"}:
        return "in_progress"
    return "pending"


def _buyer_deposit_due_at(
    offer: BuyerOffer,
    transaction: Transaction,
) -> datetime | None:
    """Return an actionable deposit/waiver deadline without treating unknown EMD as zero."""
    if offer.earnest_money_cents == 0:
        return None
    return offer.deposit_due_at or offer.proposed_closing_at or transaction.closing_date


def _checklist_checkpoint_type(item: TransactionChecklistItem) -> str | None:
    """Map stable transaction checklist records into Offer Room closing controls."""
    item_key = (item.item_key or "").strip().casefold()
    category = (item.category or "").strip().casefold()
    haystack = f"{item_key} {category} {item.title}".casefold()
    if item_key in {"open_title", "seller_documents"} or category == "title":
        return "title"
    if item_key == "due_diligence" or category == "access" or "access" in haystack:
        return "access"
    if item_key == "closing_confirmed" or category == "closing" or "closing" in haystack:
        return "closing"
    return None


def _checklist_checkpoint_due_at(
    item: TransactionChecklistItem,
    transaction: Transaction,
    primary: BuyerOffer,
    checkpoint_type: str,
) -> datetime | None:
    if item.due_at is not None:
        return item.due_at
    if item.completed_at is not None:
        return item.completed_at
    if checkpoint_type == "access":
        return (
            transaction.due_diligence_deadline
            or transaction.closing_date
            or primary.proposed_closing_at
        )
    return transaction.closing_date or primary.proposed_closing_at


def _upsert_canonical_checkpoint(
    db: Session,
    principal: Principal,
    case: DispositionCase,
    selection: DispositionBuyerSelection,
    primary: BuyerOffer,
    *,
    checkpoint_type: str,
    label: str,
    due_at: datetime | None,
    source: str,
    source_record_id: UUID,
    status: str,
    completed_at: datetime | None,
    evidence: dict[str, Any],
    responsible_user_id: UUID | None,
) -> None:
    checkpoint = db.scalar(
        select(DispositionClosingCheckpoint)
        .where(
            DispositionClosingCheckpoint.organization_id == principal.organization_id,
            DispositionClosingCheckpoint.disposition_case_id == case.id,
            DispositionClosingCheckpoint.selection_id == selection.id,
            DispositionClosingCheckpoint.checkpoint_type == checkpoint_type,
            DispositionClosingCheckpoint.canonical_source == source,
            DispositionClosingCheckpoint.source_record_id == source_record_id,
        )
        .execution_options(populate_existing=True)
        .with_for_update(of=DispositionClosingCheckpoint)
    )
    if due_at is None:
        if checkpoint is not None and checkpoint.status not in TERMINAL_CHECKPOINT_STATUSES:
            now = datetime.now(UTC)
            checkpoint.status = "cancelled"
            checkpoint.completed_at = now
            checkpoint.updated_by_user_id = principal.user_id
            checkpoint.lock_version += 1
            _resolve_checkpoint_alerts(db, checkpoint.id, resolved_at=now)
        return
    normalized_status = _checkpoint_status_from_source(status, completed_at)
    if checkpoint is None:
        db.add(
            DispositionClosingCheckpoint(
                organization_id=principal.organization_id,
                disposition_case_id=case.id,
                selection_id=selection.id,
                offer_id=primary.id,
                buyer_id=primary.buyer_id,
                responsible_user_id=responsible_user_id or case.owner_user_id,
                created_by_user_id=principal.user_id,
                updated_by_user_id=principal.user_id,
                idempotency_key=(
                    f"canonical:{selection.id}:{source}:{source_record_id}:{checkpoint_type}"
                ),
                checkpoint_type=checkpoint_type,
                label=label,
                canonical_source=source,
                source_record_id=source_record_id,
                due_at=due_at,
                status=normalized_status,
                lock_version=1,
                deadline_version=1,
                completed_at=completed_at,
                notes=None,
                evidence_snapshot=evidence,
            )
        )
        return
    deadline_changed = _aware(checkpoint.due_at) != _aware(due_at)
    if source == "buyer_offer" and checkpoint.status == "waived" and completed_at is None:
        normalized_status = "waived"
        completed_at = checkpoint.completed_at
    if (
        checkpoint.status == "missed"
        and normalized_status in {"pending", "in_progress"}
        and not deadline_changed
    ):
        normalized_status = "missed"
    checkpoint.offer_id = primary.id
    checkpoint.buyer_id = primary.buyer_id
    checkpoint.responsible_user_id = responsible_user_id or case.owner_user_id
    checkpoint.label = label
    checkpoint.due_at = due_at
    checkpoint.status = normalized_status
    checkpoint.completed_at = completed_at
    checkpoint.evidence_snapshot = {**(checkpoint.evidence_snapshot or {}), **evidence}
    checkpoint.updated_by_user_id = principal.user_id
    checkpoint.lock_version += 1
    if deadline_changed:
        checkpoint.deadline_version += 1
        _resolve_checkpoint_alerts(db, checkpoint.id)
    elif normalized_status in TERMINAL_CHECKPOINT_STATUSES:
        _resolve_checkpoint_alerts(db, checkpoint.id)


def _sync_canonical_checkpoints(
    db: Session,
    principal: Principal,
    case: DispositionCase,
    transaction: Transaction,
    selection: DispositionBuyerSelection,
    primary: BuyerOffer,
) -> None:
    _upsert_canonical_checkpoint(
        db,
        principal,
        case,
        selection,
        primary,
        checkpoint_type="closing",
        label="Contract closing",
        due_at=transaction.closing_date,
        source="transaction",
        source_record_id=transaction.id,
        status="complete" if transaction.funded_at or transaction.closed_at else "open",
        completed_at=transaction.funded_at or transaction.closed_at,
        evidence={
            "transaction_id": str(transaction.id),
            "title_company": transaction.title_company,
        },
        responsible_user_id=transaction.coordinator_user_id,
    )
    _upsert_canonical_checkpoint(
        db,
        principal,
        case,
        selection,
        primary,
        checkpoint_type="buyer_deposit",
        label=(
            "Buyer earnest-money terms or waiver"
            if primary.earnest_money_cents is None
            else "Buyer earnest-money deposit"
        ),
        due_at=_buyer_deposit_due_at(primary, transaction),
        source="buyer_offer",
        source_record_id=primary.id,
        status="complete" if primary.deposit_received_at else "open",
        completed_at=primary.deposit_received_at,
        evidence={
            "offer_id": str(primary.id),
            "earnest_money_cents": primary.earnest_money_cents,
        },
        responsible_user_id=case.owner_user_id,
    )
    checklist = list(
        db.scalars(
            select(TransactionChecklistItem).where(
                TransactionChecklistItem.organization_id == principal.organization_id,
                TransactionChecklistItem.transaction_id == transaction.id,
            )
        ).all()
    )
    for item in checklist:
        checkpoint_type = _checklist_checkpoint_type(item)
        if checkpoint_type is None:
            continue
        _upsert_canonical_checkpoint(
            db,
            principal,
            case,
            selection,
            primary,
            checkpoint_type=checkpoint_type,
            label=item.title,
            due_at=_checklist_checkpoint_due_at(
                item,
                transaction,
                primary,
                checkpoint_type,
            ),
            source="transaction_checklist",
            source_record_id=item.id,
            status=item.status,
            completed_at=item.completed_at,
            evidence={
                "checklist_item_id": str(item.id),
                "description": item.description,
                "evidence_document_id": (
                    str(item.evidence_document_id) if item.evidence_document_id else None
                ),
                "evidence_notes": item.evidence_notes,
            },
            responsible_user_id=item.responsible_user_id,
        )


def _cancel_selection_checkpoints(db: Session, selection_id: UUID) -> None:
    now = datetime.now(UTC)
    for checkpoint in db.scalars(
        select(DispositionClosingCheckpoint)
        .where(
            DispositionClosingCheckpoint.selection_id == selection_id,
            DispositionClosingCheckpoint.status.notin_(TERMINAL_CHECKPOINT_STATUSES),
        )
        .order_by(DispositionClosingCheckpoint.id)
        .with_for_update()
    ).all():
        checkpoint.status = "cancelled"
        checkpoint.completed_at = now
        checkpoint.lock_version += 1
        _resolve_checkpoint_alerts(db, checkpoint.id, resolved_at=now)


def create_checkpoint(
    db: Session,
    principal: Principal,
    case_id: UUID,
    payload: ClosingCheckpointCreate,
) -> OfferRoomRead:
    case, _ = _lock_case(db, principal, case_id, allowed_statuses={"buyer_selected"})
    existing = db.scalar(
        select(DispositionClosingCheckpoint).where(
            DispositionClosingCheckpoint.organization_id == principal.organization_id,
            DispositionClosingCheckpoint.disposition_case_id == case.id,
            DispositionClosingCheckpoint.idempotency_key == payload.idempotency_key,
        )
    )
    if existing is not None:
        return read_workspace(db, principal, case.id)
    selection, slots = _current_selection_with_slots(db, principal, case.id)
    if selection is None:
        raise ValueError("Select a primary buyer before adding closing checkpoints.")
    if payload.selection_id and payload.selection_id != selection.id:
        raise ValueError("Checkpoint selection is no longer current.")
    primary_slot = next(item for item in slots if item.role == "primary")
    offer_id = payload.offer_id or primary_slot.offer_id
    slot = next((item for item in slots if item.offer_id == offer_id), None)
    if slot is None:
        raise ValueError("Checkpoint offer is not part of current buyer coverage.")
    responsible_user_id = payload.responsible_user_id or case.owner_user_id
    if responsible_user_id is not None:
        responsible_user = db.scalar(
            select(User).where(
                User.id == responsible_user_id,
                User.organization_id == principal.organization_id,
                User.is_active.is_(True),
            )
        )
        if responsible_user is None:
            raise ValueError("Responsible user must be an active user in this organization.")
    checkpoint = DispositionClosingCheckpoint(
        organization_id=principal.organization_id,
        disposition_case_id=case.id,
        selection_id=selection.id,
        offer_id=slot.offer_id,
        buyer_id=slot.buyer_id,
        responsible_user_id=responsible_user_id,
        created_by_user_id=principal.user_id,
        updated_by_user_id=principal.user_id,
        idempotency_key=payload.idempotency_key,
        checkpoint_type=payload.checkpoint_type,
        label=payload.label,
        canonical_source="offer_room",
        source_record_id=None,
        due_at=payload.due_at,
        status="pending",
        lock_version=1,
        deadline_version=1,
        completed_at=None,
        notes=payload.notes,
        evidence_snapshot=payload.evidence,
    )
    db.add(checkpoint)
    db.commit()
    return read_workspace(db, principal, case.id)


def _resolve_checkpoint_alerts(
    db: Session,
    checkpoint_id: UUID,
    *,
    resolved_at: datetime | None = None,
) -> None:
    now = resolved_at or datetime.now(UTC)
    for alert in db.scalars(
        select(DispositionDeadlineAlert).where(
            DispositionDeadlineAlert.checkpoint_id == checkpoint_id,
            DispositionDeadlineAlert.status.in_(("open", "acknowledged")),
        )
    ).all():
        alert.status = "resolved"
        alert.resolved_at = now


def _cancel_checkpoint(
    db: Session,
    checkpoint: DispositionClosingCheckpoint,
    *,
    cancelled_at: datetime,
) -> None:
    if checkpoint.status not in TERMINAL_CHECKPOINT_STATUSES:
        checkpoint.status = "cancelled"
        checkpoint.completed_at = cancelled_at
        checkpoint.lock_version += 1
    _resolve_checkpoint_alerts(db, checkpoint.id, resolved_at=cancelled_at)


def _refresh_checkpoint_from_canonical_source(
    db: Session,
    checkpoint: DispositionClosingCheckpoint,
    *,
    now: datetime,
) -> None:
    if checkpoint.selection_id is not None:
        selection = db.get(DispositionBuyerSelection, checkpoint.selection_id)
        if selection is None or selection.status != "active":
            _cancel_checkpoint(db, checkpoint, cancelled_at=now)
            return
    if checkpoint.canonical_source == "offer_room":
        return

    due_at: datetime | None = None
    normalized_status = "pending"
    completed_at: datetime | None = None
    evidence: dict[str, Any] = {}
    if checkpoint.canonical_source == "transaction":
        transaction_source = db.get(Transaction, checkpoint.source_record_id)
        if transaction_source is not None:
            due_at = transaction_source.closing_date
            if transaction_source.status in {"cancelled", "canceled"}:
                normalized_status = "cancelled"
                completed_at = transaction_source.cancelled_at
            else:
                completed_at = transaction_source.funded_at or transaction_source.closed_at
                normalized_status = "completed" if completed_at else "pending"
            evidence = {
                "transaction_id": str(transaction_source.id),
                "title_company": transaction_source.title_company,
            }
    elif checkpoint.canonical_source == "transaction_checklist":
        checklist_source = db.get(TransactionChecklistItem, checkpoint.source_record_id)
        if checklist_source is not None:
            source_transaction = db.get(Transaction, checklist_source.transaction_id)
            source_offer = db.get(BuyerOffer, checkpoint.offer_id)
            checkpoint_type = _checklist_checkpoint_type(checklist_source)
            if (
                source_transaction is not None
                and source_offer is not None
                and checkpoint_type is not None
            ):
                due_at = _checklist_checkpoint_due_at(
                    checklist_source,
                    source_transaction,
                    source_offer,
                    checkpoint_type,
                )
            completed_at = checklist_source.completed_at
            normalized_status = _checkpoint_status_from_source(
                checklist_source.status,
                completed_at,
            )
            evidence = {
                "checklist_item_id": str(checklist_source.id),
                "description": checklist_source.description,
                "evidence_document_id": (
                    str(checklist_source.evidence_document_id)
                    if checklist_source.evidence_document_id
                    else None
                ),
                "evidence_notes": checklist_source.evidence_notes,
            }
    elif checkpoint.canonical_source == "buyer_offer":
        offer_source = db.get(BuyerOffer, checkpoint.source_record_id)
        if offer_source is not None:
            source_case = db.get(DispositionCase, checkpoint.disposition_case_id)
            source_transaction = (
                db.get(Transaction, source_case.transaction_id) if source_case is not None else None
            )
            if source_transaction is not None:
                due_at = _buyer_deposit_due_at(offer_source, source_transaction)
            completed_at = offer_source.deposit_received_at
            normalized_status = "completed" if completed_at else "pending"
            if checkpoint.status == "waived" and completed_at is None:
                normalized_status = "waived"
                completed_at = checkpoint.completed_at
            evidence = {
                "offer_id": str(offer_source.id),
                "earnest_money_cents": offer_source.earnest_money_cents,
            }
    if due_at is None:
        _cancel_checkpoint(db, checkpoint, cancelled_at=now)
        return

    deadline_changed = _aware(checkpoint.due_at) != _aware(due_at)
    if (
        checkpoint.status == "missed"
        and normalized_status in {"pending", "in_progress"}
        and not deadline_changed
    ):
        normalized_status = "missed"
    checkpoint.due_at = due_at
    checkpoint.status = normalized_status
    checkpoint.completed_at = completed_at
    checkpoint.evidence_snapshot = {**(checkpoint.evidence_snapshot or {}), **evidence}
    checkpoint.lock_version += 1
    if deadline_changed:
        checkpoint.deadline_version += 1
        _resolve_checkpoint_alerts(db, checkpoint.id, resolved_at=now)
    elif normalized_status in TERMINAL_CHECKPOINT_STATUSES:
        _resolve_checkpoint_alerts(db, checkpoint.id, resolved_at=now)


def update_checkpoint(
    db: Session,
    principal: Principal,
    case_id: UUID,
    checkpoint_id: UUID,
    payload: ClosingCheckpointUpdate,
) -> OfferRoomRead:
    case, _ = _lock_case(db, principal, case_id, allowed_statuses={"buyer_selected"})
    candidate = db.scalar(
        select(DispositionClosingCheckpoint).where(
            DispositionClosingCheckpoint.id == checkpoint_id,
            DispositionClosingCheckpoint.organization_id == principal.organization_id,
            DispositionClosingCheckpoint.disposition_case_id == case.id,
        )
    )
    if candidate is None:
        raise LookupError("Closing checkpoint not found.")
    canonical_offer = None
    if candidate.canonical_source == "buyer_offer":
        canonical_offer = db.scalar(
            select(BuyerOffer)
            .where(
                BuyerOffer.id == candidate.offer_id,
                BuyerOffer.organization_id == principal.organization_id,
                BuyerOffer.disposition_case_id == case.id,
            )
            .with_for_update()
        )
        if canonical_offer is None:
            raise ValueError("The canonical buyer offer is no longer available.")
    elif candidate.canonical_source == "transaction":
        source_transaction = db.scalar(
            select(Transaction)
            .where(
                Transaction.id == candidate.source_record_id,
                Transaction.organization_id == principal.organization_id,
            )
            .with_for_update()
        )
        if source_transaction is None:
            raise ValueError("The canonical transaction is no longer available.")
    elif candidate.canonical_source == "transaction_checklist":
        source_transaction_id = db.scalar(
            select(TransactionChecklistItem.transaction_id).where(
                TransactionChecklistItem.id == candidate.source_record_id,
                TransactionChecklistItem.organization_id == principal.organization_id,
            )
        )
        if source_transaction_id is None:
            raise ValueError("The canonical checklist item is no longer available.")
        source_transaction = db.scalar(
            select(Transaction)
            .where(
                Transaction.id == source_transaction_id,
                Transaction.organization_id == principal.organization_id,
            )
            .with_for_update()
        )
        source_checklist_item = db.scalar(
            select(TransactionChecklistItem)
            .where(
                TransactionChecklistItem.id == candidate.source_record_id,
                TransactionChecklistItem.organization_id == principal.organization_id,
            )
            .with_for_update()
        )
        if source_transaction is None or source_checklist_item is None:
            raise ValueError("The canonical checklist source is no longer available.")
    checkpoint = db.scalar(
        select(DispositionClosingCheckpoint)
        .where(
            DispositionClosingCheckpoint.id == checkpoint_id,
            DispositionClosingCheckpoint.organization_id == principal.organization_id,
            DispositionClosingCheckpoint.disposition_case_id == case.id,
        )
        .execution_options(populate_existing=True)
        .with_for_update()
    )
    if checkpoint is None:
        raise LookupError("Closing checkpoint not found.")
    if checkpoint.lock_version != payload.expected_lock_version:
        raise ValueError("Checkpoint changed. Refresh the Offer Room and retry.")
    active_selection = db.scalar(
        select(DispositionBuyerSelection).where(
            DispositionBuyerSelection.organization_id == principal.organization_id,
            DispositionBuyerSelection.disposition_case_id == case.id,
            DispositionBuyerSelection.status == "active",
        )
    )
    if active_selection is None or checkpoint.selection_id != active_selection.id:
        raise ValueError(
            "This checkpoint belongs to superseded buyer coverage and cannot be changed."
        )
    if checkpoint.status in TERMINAL_CHECKPOINT_STATUSES:
        raise ValueError(
            "Completed, waived, or cancelled checkpoints are immutable. Create a corrective "
            "checkpoint instead."
        )
    if checkpoint.canonical_source in {"transaction", "transaction_checklist"} and (
        payload.status is not None or payload.due_at is not None
    ):
        raise ValueError(
            "This deadline is controlled by the Transaction workspace. Update its canonical "
            "transaction or checklist record instead."
        )
    if checkpoint.canonical_source == "buyer_offer" and payload.due_at is not None:
        raise ValueError(
            "The deposit due date is an approved offer term. Revise and reapprove buyer "
            "coverage instead."
        )
    if checkpoint.checkpoint_type == "buyer_deposit" and payload.status in {
        "completed",
        "waived",
    }:
        if not _has_deposit_evidence_note(payload.evidence):
            raise ValueError(
                "Record a deposit confirmation or waiver support note containing at least "
                "10 non-whitespace characters."
            )
        if payload.status == "waived":
            _require_manager(principal)
    prior_due = checkpoint.due_at
    if (
        checkpoint.canonical_source == "buyer_offer"
        and payload.status is not None
        and payload.status not in {"completed", "waived"}
    ):
        raise ValueError(
            "A buyer-deposit checkpoint can only be completed or explicitly waived here."
        )
    if payload.status is not None:
        checkpoint.status = payload.status
        checkpoint.completed_at = (
            datetime.now(UTC) if payload.status in TERMINAL_CHECKPOINT_STATUSES else None
        )
    if payload.due_at is not None:
        checkpoint.due_at = payload.due_at
    if payload.responsible_user_id is not None:
        user = db.scalar(
            select(User).where(
                User.id == payload.responsible_user_id,
                User.organization_id == principal.organization_id,
                User.is_active.is_(True),
            )
        )
        if user is None:
            raise ValueError("Responsible user is unavailable.")
        checkpoint.responsible_user_id = user.id
    if payload.notes is not None:
        checkpoint.notes = payload.notes
    if payload.evidence is not None:
        checkpoint.evidence_snapshot = payload.evidence
    if canonical_offer is not None and payload.status == "completed":
        canonical_offer.deposit_received_at = checkpoint.completed_at
    checkpoint.updated_by_user_id = principal.user_id
    checkpoint.lock_version += 1
    if _aware(prior_due) != _aware(checkpoint.due_at):
        checkpoint.deadline_version += 1
        if checkpoint.status == "missed":
            checkpoint.status = "pending"
        _resolve_checkpoint_alerts(db, checkpoint.id)
    elif checkpoint.status in TERMINAL_CHECKPOINT_STATUSES:
        _resolve_checkpoint_alerts(db, checkpoint.id)
    audit(
        db,
        principal,
        "disposition.checkpoint_updated",
        "disposition_closing_checkpoint",
        checkpoint.id,
        {"status": checkpoint.status, "lock_version": checkpoint.lock_version},
        payload.reason,
    )
    db.commit()
    return read_workspace(db, principal, case.id)


def _escalate_checkpoint(
    db: Session,
    checkpoint: DispositionClosingCheckpoint,
    *,
    now: datetime,
) -> DispositionDeadlineAlert:
    dedupe_key = f"checkpoint:{checkpoint.id}:deadline:{checkpoint.deadline_version}"
    existing = db.scalar(
        select(DispositionDeadlineAlert).where(
            DispositionDeadlineAlert.organization_id == checkpoint.organization_id,
            DispositionDeadlineAlert.dedupe_key == dedupe_key,
        )
    )
    if existing is not None:
        if checkpoint.status != "missed":
            checkpoint.status = "missed"
            checkpoint.lock_version += 1
        return existing
    overdue_seconds = max(0, int((now - _aware(checkpoint.due_at)).total_seconds()))
    severity = "danger" if overdue_seconds >= 86400 else "warning"
    alert = DispositionDeadlineAlert(
        organization_id=checkpoint.organization_id,
        disposition_case_id=checkpoint.disposition_case_id,
        checkpoint_id=checkpoint.id,
        deadline_version=checkpoint.deadline_version,
        dedupe_key=dedupe_key,
        status="open",
        severity=severity,
        due_at=checkpoint.due_at,
        acknowledged_by_user_id=None,
        acknowledged_at=None,
        resolved_at=None,
    )
    try:
        with db.begin_nested():
            db.add(alert)
            db.flush()
    except IntegrityError:
        existing = db.scalar(
            select(DispositionDeadlineAlert).where(
                DispositionDeadlineAlert.organization_id == checkpoint.organization_id,
                DispositionDeadlineAlert.dedupe_key == dedupe_key,
            )
        )
        if existing is None:
            raise
        if checkpoint.status != "missed":
            checkpoint.status = "missed"
            checkpoint.lock_version += 1
        return existing
    checkpoint.status = "missed"
    checkpoint.lock_version += 1
    return alert


def scan_case_deadlines(
    db: Session,
    principal: Principal,
    case_id: UUID,
) -> OfferRoomRead:
    case, transaction = _lock_case(db, principal, case_id, allowed_statuses={"buyer_selected"})
    selection, slots = _current_selection_with_slots(db, principal, case.id)
    if selection is not None:
        primary_slot = next(item for item in slots if item.role == "primary")
        primary = db.get(BuyerOffer, primary_slot.offer_id)
        if primary is not None:
            _sync_canonical_checkpoints(db, principal, case, transaction, selection, primary)
            db.flush()
    now = datetime.now(UTC)
    checkpoints = list(
        db.scalars(
            select(DispositionClosingCheckpoint)
            .where(
                DispositionClosingCheckpoint.organization_id == principal.organization_id,
                DispositionClosingCheckpoint.disposition_case_id == case.id,
                DispositionClosingCheckpoint.status.in_(("pending", "in_progress")),
                DispositionClosingCheckpoint.due_at < now,
            )
            .order_by(DispositionClosingCheckpoint.id)
            .with_for_update()
        ).all()
    )
    for checkpoint in checkpoints:
        _escalate_checkpoint(db, checkpoint, now=now)
    db.commit()
    return read_workspace(db, principal, case.id)


def process_next_closing_deadline_escalation(
    db: Session,
    _settings: Settings,
) -> UUID | None:
    now = datetime.now(UTC)
    candidate = db.scalar(
        select(DispositionClosingCheckpoint)
        .where(
            DispositionClosingCheckpoint.status.in_(("pending", "in_progress")),
            DispositionClosingCheckpoint.due_at < now,
        )
        .order_by(DispositionClosingCheckpoint.due_at, DispositionClosingCheckpoint.id)
        .limit(1)
    )
    if candidate is None:
        return None
    if candidate.canonical_source == "buyer_offer":
        locked_source = db.scalar(
            select(BuyerOffer)
            .where(BuyerOffer.id == candidate.source_record_id)
            .with_for_update(skip_locked=True)
        )
        if locked_source is None:
            db.rollback()
            return None
    elif candidate.canonical_source == "transaction":
        locked_source = db.scalar(
            select(Transaction)
            .where(Transaction.id == candidate.source_record_id)
            .with_for_update(skip_locked=True)
        )
        if locked_source is None:
            db.rollback()
            return None
    elif candidate.canonical_source == "transaction_checklist":
        source_transaction_id = db.scalar(
            select(TransactionChecklistItem.transaction_id).where(
                TransactionChecklistItem.id == candidate.source_record_id
            )
        )
        if source_transaction_id is None:
            db.rollback()
            return None
        locked_transaction = db.scalar(
            select(Transaction)
            .where(Transaction.id == source_transaction_id)
            .with_for_update(skip_locked=True)
        )
        if locked_transaction is None:
            db.rollback()
            return None
        locked_source = db.scalar(
            select(TransactionChecklistItem)
            .where(TransactionChecklistItem.id == candidate.source_record_id)
            .with_for_update(skip_locked=True)
        )
        if locked_source is None:
            db.rollback()
            return None
    checkpoint = db.scalar(
        select(DispositionClosingCheckpoint)
        .where(
            DispositionClosingCheckpoint.id == candidate.id,
            DispositionClosingCheckpoint.status.in_(("pending", "in_progress")),
        )
        .execution_options(populate_existing=True)
        .with_for_update(skip_locked=True)
    )
    if checkpoint is None:
        db.rollback()
        return None
    _refresh_checkpoint_from_canonical_source(db, checkpoint, now=now)
    if checkpoint.status in TERMINAL_CHECKPOINT_STATUSES or _aware(checkpoint.due_at) >= now:
        db.commit()
        return checkpoint.id
    alert = _escalate_checkpoint(db, checkpoint, now=now)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        return None
    return alert.id


def acknowledge_alert(
    db: Session,
    principal: Principal,
    case_id: UUID,
    alert_id: UUID,
    *,
    reason: str,
) -> OfferRoomRead:
    case, _ = _lock_case(db, principal, case_id, allowed_statuses={"buyer_selected"})
    alert = db.scalar(
        select(DispositionDeadlineAlert)
        .where(
            DispositionDeadlineAlert.id == alert_id,
            DispositionDeadlineAlert.organization_id == principal.organization_id,
            DispositionDeadlineAlert.disposition_case_id == case.id,
        )
        .with_for_update()
    )
    if alert is None:
        raise LookupError("Deadline alert not found.")
    if alert.status == "open":
        alert.status = "acknowledged"
        alert.acknowledged_by_user_id = principal.user_id
        alert.acknowledged_at = datetime.now(UTC)
        audit(
            db,
            principal,
            "disposition.deadline_acknowledged",
            "disposition_deadline_alert",
            alert.id,
            {"status": alert.status},
            reason,
        )
        db.commit()
    return read_workspace(db, principal, case.id)


def _record_outcome_locked(
    db: Session,
    principal: Principal,
    case: DispositionCase,
    offer: BuyerOffer,
    *,
    selection: DispositionBuyerSelection | None,
    outcome_type: str,
    cause_category: str,
    reason: str,
    details: str | None,
    evidence: dict[str, Any],
    occurred_at: datetime,
    idempotency_key: str,
) -> DispositionBuyerOutcome:
    existing = db.scalar(
        select(DispositionBuyerOutcome).where(
            DispositionBuyerOutcome.organization_id == principal.organization_id,
            DispositionBuyerOutcome.disposition_case_id == case.id,
            DispositionBuyerOutcome.idempotency_key == idempotency_key,
        )
    )
    if existing is not None:
        return existing
    if outcome_type == "retrade":
        prior_retrades = list(
            db.scalars(
                select(DispositionBuyerOutcome).where(
                    DispositionBuyerOutcome.organization_id == principal.organization_id,
                    DispositionBuyerOutcome.disposition_case_id == case.id,
                    DispositionBuyerOutcome.offer_id == offer.id,
                    DispositionBuyerOutcome.outcome_type == "retrade",
                )
            ).all()
        )
        if any(
            int((item.evidence_snapshot or {}).get("offer_snapshot", {}).get("lock_version", 0))
            == offer.lock_version
            for item in prior_retrades
        ):
            raise ValueError(
                "A retrade was already recorded for this offer revision. Revise the offer "
                "terms before recording another retrade."
            )
    buyer = db.scalar(
        select(Buyer)
        .where(
            Buyer.id == offer.buyer_id,
            Buyer.organization_id == principal.organization_id,
        )
        .with_for_update()
    )
    if buyer is None:
        raise ValueError("Buyer is unavailable.")
    completed_delta = 1 if outcome_type == "completed_close" else 0
    buyer_responsible_failure = cause_category == "buyer" and outcome_type in {
        "fallout",
        "withdrawal",
        "missed_deadline",
    }
    failed_delta = 1 if buyer_responsible_failure else 0
    requested_reliability_delta = (
        250
        if outcome_type == "completed_close"
        else -500
        if buyer_responsible_failure
        else -150
        if cause_category == "buyer" and outcome_type == "retrade"
        else 0
    )
    completed_before = buyer.completed_deals
    failed_before = buyer.failed_deals
    reliability_before = buyer.reliability_score_basis_points
    buyer.completed_deals += completed_delta
    buyer.failed_deals += failed_delta
    buyer.reliability_score_basis_points = max(
        0,
        min(10000, reliability_before + requested_reliability_delta),
    )
    reliability_delta = buyer.reliability_score_basis_points - reliability_before
    now = datetime.now(UTC)
    outcome = DispositionBuyerOutcome(
        organization_id=principal.organization_id,
        disposition_case_id=case.id,
        selection_id=selection.id if selection else None,
        offer_id=offer.id,
        buyer_id=buyer.id,
        recorded_by_user_id=principal.user_id,
        outcome_type=outcome_type,
        cause_category=cause_category,
        reason=reason,
        details=details,
        evidence_snapshot={
            **evidence,
            "offer_snapshot": _selection_snapshot(offer),
            "buyer_history_before": {
                "completed_deals": completed_before,
                "failed_deals": failed_before,
                "reliability_score_basis_points": reliability_before,
            },
        },
        occurred_at=occurred_at,
        history_applied_at=now,
        completed_delta=completed_delta,
        failed_delta=failed_delta,
        reliability_delta_basis_points=reliability_delta,
        idempotency_key=idempotency_key,
    )
    status_by_outcome = {
        "pass": "passed",
        "withdrawal": "withdrawn",
        "fallout": "fell_out",
        "missed_deadline": "fell_out",
        "retrade": "countering",
        "completed_close": "closed",
    }
    offer.status = status_by_outcome[outcome_type]
    db.add(outcome)
    return outcome


def record_funded_transaction_buyer_outcome(
    db: Session,
    principal: Principal,
    transaction: Transaction,
    *,
    occurred_at: datetime,
) -> DispositionBuyerOutcome | None:
    """Apply the selected buyer's completed-close history in the funding transaction."""
    case = db.scalar(
        select(DispositionCase)
        .where(
            DispositionCase.organization_id == principal.organization_id,
            DispositionCase.transaction_id == transaction.id,
        )
        .with_for_update()
    )
    if case is None:
        return None
    if case.status != "buyer_selected":
        raise ValueError("Approve a primary buyer before funding this disposition transaction.")
    selection = db.scalar(
        select(DispositionBuyerSelection).where(
            DispositionBuyerSelection.organization_id == principal.organization_id,
            DispositionBuyerSelection.disposition_case_id == case.id,
            DispositionBuyerSelection.status == "active",
        )
    )
    if selection is None:
        if (
            case.selected_buyer_id is None
            or case.selection_approved_by_user_id is None
            or case.selection_approved_at is None
        ):
            raise ValueError(
                "An active manager-approved Offer Room buyer selection is required before funding."
            )
        selected_buyer_ids = {
            buyer_id
            for buyer_id in (case.selected_buyer_id, case.backup_buyer_id)
            if buyer_id is not None
        }
        legacy_offers = list(
            db.scalars(
                select(BuyerOffer).where(
                    BuyerOffer.organization_id == principal.organization_id,
                    BuyerOffer.disposition_case_id == case.id,
                    BuyerOffer.status.in_(VIABLE_OFFER_STATUSES),
                    BuyerOffer.buyer_id.in_(selected_buyer_ids),
                )
            ).all()
        )
        legacy_primary = next(
            (
                offer
                for offer in legacy_offers
                if offer.buyer_id == case.selected_buyer_id and offer.status == "selected"
            ),
            next(
                (offer for offer in legacy_offers if offer.buyer_id == case.selected_buyer_id),
                None,
            ),
        )
        if legacy_primary is None:
            raise ValueError(
                "The approved legacy buyer selection has no viable buyer offer to adopt."
            )
        legacy_backup = next(
            (
                offer
                for offer in legacy_offers
                if case.backup_buyer_id is not None and offer.buyer_id == case.backup_buyer_id
            ),
            None,
        )
        locked_legacy_offers = _lock_offers(
            db,
            principal,
            case,
            [
                legacy_primary.id,
                *([legacy_backup.id] if legacy_backup is not None else []),
            ],
        )
        legacy_by_id = {offer.id: offer for offer in locked_legacy_offers}
        primary = legacy_by_id[legacy_primary.id]
        backups = [legacy_by_id[legacy_backup.id]] if legacy_backup is not None else []
        selection = _create_selection_record(
            db,
            principal,
            case,
            primary=primary,
            backups=backups,
            reason="Governed adoption of the previously approved buyer selection.",
            idempotency_key=f"legacy-adoption:{case.id}",
            approved_by_user_id=case.selection_approved_by_user_id,
            approved_at=case.selection_approved_at,
        )
        db.flush()
        primary_slot = db.scalar(
            select(DispositionBuyerSelectionSlot)
            .where(
                DispositionBuyerSelectionSlot.selection_id == selection.id,
                DispositionBuyerSelectionSlot.role == "primary",
            )
            .with_for_update()
        )
        assert primary_slot is not None
    else:
        primary_slot = db.scalar(
            select(DispositionBuyerSelectionSlot).where(
                DispositionBuyerSelectionSlot.selection_id == selection.id,
                DispositionBuyerSelectionSlot.role == "primary",
            )
        )
        if primary_slot is None:
            raise ValueError("The approved selection does not contain a primary buyer.")
        primary = db.scalar(
            select(BuyerOffer)
            .where(
                BuyerOffer.id == primary_slot.offer_id,
                BuyerOffer.organization_id == principal.organization_id,
                BuyerOffer.disposition_case_id == case.id,
            )
            .with_for_update()
        )
        if primary is None:
            raise ValueError("The approved primary offer is no longer available.")
        locked_selection = db.scalar(
            select(DispositionBuyerSelection)
            .where(
                DispositionBuyerSelection.id == selection.id,
                DispositionBuyerSelection.status == "active",
            )
            .execution_options(populate_existing=True)
            .with_for_update()
        )
        if locked_selection is None or locked_selection.approved_by_user_id is None:
            raise ValueError("The approved buyer selection changed during funding.")
        selection = locked_selection
        locked_primary_slot = db.scalar(
            select(DispositionBuyerSelectionSlot)
            .where(
                DispositionBuyerSelectionSlot.id == primary_slot.id,
                DispositionBuyerSelectionSlot.selection_id == selection.id,
                DispositionBuyerSelectionSlot.offer_id == primary.id,
                DispositionBuyerSelectionSlot.role == "primary",
            )
            .with_for_update()
        )
        if locked_primary_slot is None:
            raise ValueError("The approved primary-buyer coverage changed during funding.")
        primary_slot = locked_primary_slot
    if case.selected_buyer_id != primary.buyer_id:
        raise ValueError("The case and Offer Room primary-buyer selections do not match.")
    if primary.status != "selected":
        raise ValueError("The approved primary offer is no longer in a selected state.")
    if int(primary_slot.offer_snapshot.get("lock_version", 0)) != primary.lock_version:
        raise ValueError(
            "The approved primary offer terms changed. Reapprove buyer coverage before funding."
        )
    buyer = _scoped_buyer(db, principal, primary.buyer_id)
    if buyer is None or buyer.status != "active":
        raise ValueError("The approved primary buyer is inactive or archived.")
    live_coverage = _coverage_snapshot(db, principal, case, primary)
    if live_coverage["readiness_blockers"]:
        raise ValueError(
            "The approved primary buyer is no longer funding-ready: "
            + "; ".join(live_coverage["readiness_blockers"])
        )

    if case.strategy == "assignment":
        packages = list(
            db.scalars(
                select(ContractPackage).where(
                    ContractPackage.organization_id == principal.organization_id,
                    ContractPackage.transaction_id == transaction.id,
                    ContractPackage.status == "executed",
                )
            ).all()
        )

        def valid_identity_evidence(
            evidence: object,
            binding: dict[str, Any],
            *,
            signer_name: str,
            signer_email: str,
            source: str,
        ) -> bool:
            if not isinstance(evidence, dict) or evidence.get("source") != source:
                return False
            try:
                expected = assignment_signer_identity_snapshot(
                    binding,
                    signer_name=signer_name,
                    signer_email=signer_email,
                    source=source,
                )
            except ValueError:
                return False
            return all(
                evidence.get(key) == expected.get(key)
                for key in ("source", "name", "normalized_name", "email", "identity_hash")
            )

        def package_has_valid_execution_identity(
            package: ContractPackage,
            binding: dict[str, Any],
        ) -> bool:
            package_snapshot = package.terms_snapshot or {}
            manual_evidence = package_snapshot.get("assignment_execution_identity")
            if isinstance(manual_evidence, dict) and valid_identity_evidence(
                manual_evidence,
                binding,
                signer_name=str(manual_evidence.get("name") or ""),
                signer_email=str(manual_evidence.get("email") or ""),
                source="manual_execution_attestation",
            ):
                try:
                    document_id = UUID(str(manual_evidence.get("document_id")))
                except (TypeError, ValueError):
                    document_id = None
                if document_id is not None:
                    document = db.scalar(
                        select(TransactionDocument).where(
                            TransactionDocument.id == document_id,
                            TransactionDocument.organization_id == principal.organization_id,
                            TransactionDocument.transaction_id == transaction.id,
                            TransactionDocument.contract_package_id == package.id,
                            TransactionDocument.document_type == "assignment_contract",
                            TransactionDocument.status == "executed",
                            TransactionDocument.deleted_at.is_(None),
                        )
                    )
                    if document is not None and document.sha256 == manual_evidence.get(
                        "document_sha256"
                    ):
                        return True

            envelopes = list(
                db.scalars(
                    select(EsignEnvelope).where(
                        EsignEnvelope.organization_id == principal.organization_id,
                        EsignEnvelope.transaction_id == transaction.id,
                        EsignEnvelope.contract_package_id == package.id,
                        EsignEnvelope.status == "completed",
                        EsignEnvelope.completed_document_id.is_not(None),
                    )
                ).all()
            )
            for envelope in envelopes:
                completed_document = db.scalar(
                    select(TransactionDocument).where(
                        TransactionDocument.id == envelope.completed_document_id,
                        TransactionDocument.organization_id == principal.organization_id,
                        TransactionDocument.transaction_id == transaction.id,
                        TransactionDocument.contract_package_id == package.id,
                        TransactionDocument.document_type == "assignment_contract",
                        TransactionDocument.status == "executed",
                        TransactionDocument.deleted_at.is_(None),
                    )
                )
                if completed_document is None:
                    continue
                assignees = [
                    recipient
                    for recipient in db.scalars(
                        select(EsignRecipient).where(
                            EsignRecipient.esign_envelope_id == envelope.id,
                            EsignRecipient.organization_id == principal.organization_id,
                        )
                    ).all()
                    if any(
                        role in recipient.placeholder_name.strip().casefold()
                        for role in ("assignee", "end buyer")
                    )
                ]
                if (
                    len(assignees) != 1
                    or assignees[0].status != "signed"
                    or assignees[0].signed_at is None
                ):
                    continue
                provider_evidence = (envelope.provider_payload or {}).get(
                    "assignment_execution_identity"
                )
                if valid_identity_evidence(
                    provider_evidence,
                    binding,
                    signer_name=assignees[0].name,
                    signer_email=assignees[0].email,
                    source="esign_recipient",
                ):
                    return True
            return False

        def package_matches_primary(package: ContractPackage) -> bool:
            snapshot = package.terms_snapshot or {}
            if str(snapshot.get("document_type")) != "assignment_contract":
                return False
            binding = snapshot.get("disposition_buyer_binding")
            if not isinstance(binding, dict):
                return False
            if (
                str(binding.get("case_id")) != str(case.id)
                or str(binding.get("offer_id")) != str(primary.id)
                or str(binding.get("buyer_id")) != str(primary.buyer_id)
                or int(binding.get("offer_lock_version") or 0) != primary.lock_version
            ):
                return False
            expected_identity = assignment_buyer_identity_snapshot(buyer)
            if binding.get("buyer_identity_snapshot") != expected_identity:
                return False
            try:
                expected_economics = assignment_offer_economics_snapshot(
                    primary,
                    transaction,
                    base_purchase_price_cents=package.purchase_price_cents,
                    earnest_money_cents=package.earnest_money_cents,
                    closing_date=package.closing_date,
                    inspection_period_days=package.inspection_period_days,
                )
            except ValueError:
                return False
            if binding.get("offer_economics_snapshot") != expected_economics:
                return False
            if binding.get("offer_economics_hash") != _canonical_hash(expected_economics):
                return False
            try:
                bound_selection_id = UUID(str(binding.get("selection_id")))
            except (TypeError, ValueError):
                return False
            seen: set[UUID] = set()
            lineage_matches = False
            while bound_selection_id not in seen:
                if bound_selection_id == selection.id:
                    lineage_matches = True
                    break
                seen.add(bound_selection_id)
                prior_selection = db.get(DispositionBuyerSelection, bound_selection_id)
                if (
                    prior_selection is None
                    or prior_selection.organization_id != principal.organization_id
                    or prior_selection.disposition_case_id != case.id
                    or prior_selection.superseded_by_selection_id is None
                ):
                    break
                bound_selection_id = prior_selection.superseded_by_selection_id
            return lineage_matches and package_has_valid_execution_identity(package, binding)

        has_buyer_agreement = any(package_matches_primary(package) for package in packages)
        if not has_buyer_agreement:
            raise ValueError("An executed buyer assignment agreement is required before funding.")

    _sync_canonical_checkpoints(db, principal, case, transaction, selection, primary)
    db.flush()
    deposit_checkpoint = db.scalar(
        select(DispositionClosingCheckpoint)
        .where(
            DispositionClosingCheckpoint.organization_id == principal.organization_id,
            DispositionClosingCheckpoint.disposition_case_id == case.id,
            DispositionClosingCheckpoint.selection_id == selection.id,
            DispositionClosingCheckpoint.offer_id == primary.id,
            DispositionClosingCheckpoint.checkpoint_type == "buyer_deposit",
            DispositionClosingCheckpoint.canonical_source == "buyer_offer",
            DispositionClosingCheckpoint.source_record_id == primary.id,
            DispositionClosingCheckpoint.status.in_(("completed", "waived")),
        )
        .order_by(DispositionClosingCheckpoint.updated_at.desc())
        .with_for_update()
    )
    if primary.earnest_money_cents is None and (
        deposit_checkpoint is None or deposit_checkpoint.status != "waived"
    ):
        raise ValueError(
            "The primary buyer's earnest money is unknown. Revise the approved offer to an "
            "explicit zero or record a manager-approved canonical deposit waiver before funding."
        )
    if primary.earnest_money_cents is not None and primary.earnest_money_cents > 0 and (
        deposit_checkpoint is None
    ):
        raise ValueError(
            "Record the primary buyer's deposit or an explicit deposit waiver before funding."
        )
    if (
        primary.earnest_money_cents != 0
        and deposit_checkpoint is not None
        and not _has_deposit_evidence_note(deposit_checkpoint.evidence_snapshot)
    ):
        raise ValueError(
            "The buyer deposit receipt or waiver requires a support note containing at least "
            "10 non-whitespace characters."
        )

    outcome = _record_outcome_locked(
        db,
        principal,
        case,
        primary,
        selection=selection,
        outcome_type="completed_close",
        cause_category="external",
        reason="Canonical transaction funding completed the selected buyer close.",
        details=None,
        evidence={
            "transaction_id": str(transaction.id),
            "funded_at": occurred_at.isoformat(),
            "selection_id": str(selection.id),
            "deposit_checkpoint_id": (
                str(deposit_checkpoint.id) if deposit_checkpoint is not None else None
            ),
        },
        occurred_at=occurred_at,
        idempotency_key=f"funded-close:{transaction.id}",
    )
    for checkpoint in db.scalars(
        select(DispositionClosingCheckpoint)
        .where(
            DispositionClosingCheckpoint.organization_id == principal.organization_id,
            DispositionClosingCheckpoint.disposition_case_id == case.id,
            DispositionClosingCheckpoint.selection_id == selection.id,
            DispositionClosingCheckpoint.status.notin_(TERMINAL_CHECKPOINT_STATUSES),
        )
        .order_by(DispositionClosingCheckpoint.id)
        .with_for_update()
    ).all():
        _cancel_checkpoint(db, checkpoint, cancelled_at=occurred_at)
    return outcome


def reconcile_cancelled_transaction_checkpoints(
    db: Session,
    principal: Principal,
    transaction: Transaction,
    *,
    cancelled_at: datetime,
) -> None:
    case_id = db.scalar(
        select(DispositionCase.id).where(
            DispositionCase.organization_id == principal.organization_id,
            DispositionCase.transaction_id == transaction.id,
        )
    )
    if case_id is None:
        return
    for checkpoint in db.scalars(
        select(DispositionClosingCheckpoint)
        .where(
            DispositionClosingCheckpoint.organization_id == principal.organization_id,
            DispositionClosingCheckpoint.disposition_case_id == case_id,
            DispositionClosingCheckpoint.status.notin_(TERMINAL_CHECKPOINT_STATUSES),
        )
        .order_by(DispositionClosingCheckpoint.id)
        .with_for_update()
    ).all():
        _cancel_checkpoint(db, checkpoint, cancelled_at=cancelled_at)


def sync_transaction_offer_room_checkpoints(
    db: Session,
    principal: Principal,
    transaction: Transaction,
) -> None:
    case = db.scalar(
        select(DispositionCase).where(
            DispositionCase.organization_id == principal.organization_id,
            DispositionCase.transaction_id == transaction.id,
        )
    )
    if case is None:
        return
    selection = db.scalar(
        select(DispositionBuyerSelection).where(
            DispositionBuyerSelection.organization_id == principal.organization_id,
            DispositionBuyerSelection.disposition_case_id == case.id,
            DispositionBuyerSelection.status == "active",
        )
    )
    if selection is None:
        return
    primary_slot = db.scalar(
        select(DispositionBuyerSelectionSlot).where(
            DispositionBuyerSelectionSlot.selection_id == selection.id,
            DispositionBuyerSelectionSlot.role == "primary",
        )
    )
    if primary_slot is None:
        return
    primary = db.get(BuyerOffer, primary_slot.offer_id)
    if primary is None:
        return
    _sync_canonical_checkpoints(db, principal, case, transaction, selection, primary)


def record_outcome(
    db: Session,
    principal: Principal,
    case_id: UUID,
    payload: BuyerOutcomeCreate,
) -> OfferRoomRead:
    case, _ = _lock_case(db, principal, case_id)
    existing = db.scalar(
        select(DispositionBuyerOutcome).where(
            DispositionBuyerOutcome.organization_id == principal.organization_id,
            DispositionBuyerOutcome.disposition_case_id == case.id,
            DispositionBuyerOutcome.idempotency_key == payload.idempotency_key,
        )
    )
    if existing is not None:
        return read_workspace(db, principal, case.id)
    offer = db.scalar(
        select(BuyerOffer)
        .where(
            BuyerOffer.id == payload.offer_id,
            BuyerOffer.organization_id == principal.organization_id,
            BuyerOffer.disposition_case_id == case.id,
        )
        .with_for_update()
    )
    if offer is None:
        raise LookupError("Offer not found.")
    if offer.status not in VIABLE_OFFER_STATUSES:
        raise ValueError("A terminal buyer outcome has already been recorded for this offer.")
    current_slot = db.scalar(
        select(DispositionBuyerSelectionSlot)
        .join(
            DispositionBuyerSelection,
            DispositionBuyerSelection.id == DispositionBuyerSelectionSlot.selection_id,
        )
        .where(
            DispositionBuyerSelection.organization_id == principal.organization_id,
            DispositionBuyerSelection.disposition_case_id == case.id,
            DispositionBuyerSelection.status == "active",
            DispositionBuyerSelectionSlot.offer_id == offer.id,
        )
    )
    if current_slot is not None and current_slot.role == "primary":
        raise ValueError(
            "Record the primary buyer outcome through Replace primary so backup coverage "
            "is promoted atomically."
        )
    selection = None
    if payload.selection_id:
        selection = db.scalar(
            select(DispositionBuyerSelection).where(
                DispositionBuyerSelection.id == payload.selection_id,
                DispositionBuyerSelection.organization_id == principal.organization_id,
                DispositionBuyerSelection.disposition_case_id == case.id,
            )
        )
        if selection is None:
            raise ValueError("Buyer selection not found.")
        selection_contains_offer = db.scalar(
            select(DispositionBuyerSelectionSlot.id).where(
                DispositionBuyerSelectionSlot.selection_id == selection.id,
                DispositionBuyerSelectionSlot.offer_id == offer.id,
            )
        )
        if selection_contains_offer is None:
            raise ValueError("The selected history record does not contain this offer.")
    outcome = _record_outcome_locked(
        db,
        principal,
        case,
        offer,
        selection=selection,
        outcome_type=payload.outcome_type,
        cause_category=payload.cause_category,
        reason=payload.reason,
        details=payload.details,
        evidence=payload.evidence,
        occurred_at=payload.occurred_at or datetime.now(UTC),
        idempotency_key=payload.idempotency_key,
    )
    if current_slot is not None and current_slot.role == "backup":
        live_backup = db.scalar(
            select(BuyerOffer)
            .join(
                DispositionBuyerSelectionSlot,
                DispositionBuyerSelectionSlot.offer_id == BuyerOffer.id,
            )
            .join(
                DispositionBuyerSelection,
                DispositionBuyerSelection.id == DispositionBuyerSelectionSlot.selection_id,
            )
            .where(
                DispositionBuyerSelection.organization_id == principal.organization_id,
                DispositionBuyerSelection.disposition_case_id == case.id,
                DispositionBuyerSelection.status == "active",
                DispositionBuyerSelectionSlot.role == "backup",
                DispositionBuyerSelectionSlot.offer_id != offer.id,
                BuyerOffer.status == "backup",
            )
            .order_by(DispositionBuyerSelectionSlot.rank)
        )
        case.backup_buyer_id = live_backup.buyer_id if live_backup is not None else None
    audit(
        db,
        principal,
        "disposition.buyer_outcome_recorded",
        "disposition_buyer_outcome",
        outcome.id,
        {
            "outcome_type": outcome.outcome_type,
            "cause_category": outcome.cause_category,
            "completed_delta": outcome.completed_delta,
            "failed_delta": outcome.failed_delta,
        },
        payload.reason,
    )
    db.commit()
    return read_workspace(db, principal, case.id)


def _selection_read(
    selection: DispositionBuyerSelection,
    slots: list[DispositionBuyerSelectionSlot],
    buyers: dict[UUID, Buyer],
    offers: dict[UUID, BuyerOffer],
    live_coverage_by_offer: dict[UUID, dict[str, Any]],
    completed_close_keys: set[tuple[UUID | None, UUID]],
) -> BuyerSelectionRead:
    reads: list[SelectionSlotRead] = []
    for item in sorted(slots, key=lambda value: (value.role != "primary", value.rank)):
        blockers = list(item.offer_snapshot.get("readiness_blockers", []))
        readiness_status = item.offer_snapshot.get("readiness_status", "provisional")
        live_offer = offers.get(item.offer_id)
        if selection.status == "active":
            completed_primary = (
                item.role == "primary"
                and (selection.id, item.offer_id) in completed_close_keys
                and live_offer is not None
                and live_offer.status == "closed"
            )
            if completed_primary:
                # Canonical funding already revalidated live eligibility. Preserve that
                # terminal fact instead of making a completed selection provisional later.
                blockers = []
            else:
                blockers.extend(
                    live_coverage_by_offer.get(item.offer_id, {}).get(
                        "readiness_blockers", []
                    )
                )
            expected_status = "selected" if item.role == "primary" else "backup"
            if live_offer is None:
                blockers.append("The approved offer is no longer available.")
            else:
                if live_offer.lock_version != int(item.offer_snapshot.get("lock_version", 0)):
                    blockers.append(
                        "Offer terms changed after approval; manager reapproval is required."
                    )
                if live_offer.status != expected_status and not completed_primary:
                    blockers.append(
                        f"Approved {item.role} offer is now {live_offer.status.replace('_', ' ')}."
                    )
            blockers = list(dict.fromkeys(blockers))
            if blockers:
                readiness_status = "provisional"
        reads.append(
            SelectionSlotRead(
                offer_id=item.offer_id,
                buyer_id=item.buyer_id,
                buyer_name=buyers[item.buyer_id].name,
                amount_cents=int(item.offer_snapshot["terms"]["amount_cents"]),
                role=item.role,  # type: ignore[arg-type]
                rank=item.rank,
                offer_snapshot=item.offer_snapshot,
                readiness_status=readiness_status,
                readiness_blockers=blockers,
            )
        )
    return BuyerSelectionRead(
        id=selection.id,
        status=selection.status,
        lock_version=selection.lock_version,
        primary=next(item for item in reads if item.role == "primary"),
        backups=[item for item in reads if item.role == "backup"],
        reason=selection.reason,
        evidence_hash=selection.evidence_hash,
        approved_by_user_id=selection.approved_by_user_id,
        approved_at=selection.approved_at,
        replaced_at=selection.replaced_at,
    )


def read_workspace(db: Session, principal: Principal, case_id: UUID) -> OfferRoomRead:
    case = scoped_case(db, principal, case_id)
    if case is None:
        raise LookupError("Disposition case not found.")
    lead = db.scalar(
        select(Lead).where(
            Lead.id == case.lead_id,
            Lead.organization_id == principal.organization_id,
        )
    )
    if lead is None:
        raise ValueError("The disposition lead is unavailable.")
    require_house_workflow(lead.asset_class, workflow="Residential buyer disposition")
    transaction = db.scalar(
        select(Transaction).where(
            Transaction.id == case.transaction_id,
            Transaction.organization_id == principal.organization_id,
        )
    )
    offers = list(
        db.scalars(
            select(BuyerOffer)
            .where(
                BuyerOffer.organization_id == principal.organization_id,
                BuyerOffer.disposition_case_id == case.id,
            )
            .order_by(BuyerOffer.received_at.desc(), BuyerOffer.id)
        ).all()
    )
    buyer_ids = {item.buyer_id for item in offers}
    buyers = {
        item.id: item
        for item in db.scalars(
            select(Buyer).where(
                Buyer.organization_id == principal.organization_id,
                Buyer.id.in_(buyer_ids) if buyer_ids else Buyer.id.is_(None),
            )
        ).all()
    }
    proofs = {
        item.id: item
        for item in db.scalars(
            select(BuyerProofDocument).where(
                BuyerProofDocument.organization_id == principal.organization_id,
                BuyerProofDocument.id.in_(
                    [item.proof_document_id for item in offers if item.proof_document_id]
                )
                if any(item.proof_document_id for item in offers)
                else BuyerProofDocument.id.is_(None),
                BuyerProofDocument.deleted_at.is_(None),
            )
        ).all()
    }
    outcome_rows = list(
        db.scalars(
            select(DispositionBuyerOutcome)
            .where(
                DispositionBuyerOutcome.organization_id == principal.organization_id,
                DispositionBuyerOutcome.disposition_case_id == case.id,
            )
            .order_by(DispositionBuyerOutcome.occurred_at.desc())
        ).all()
    )
    completed_close_keys = {
        (item.selection_id, item.offer_id)
        for item in outcome_rows
        if item.outcome_type == "completed_close"
        and transaction is not None
        and transaction.status == "funded"
        and transaction.funded_at is not None
        and item.evidence_snapshot.get("transaction_id") == str(transaction.id)
        and item.evidence_snapshot.get("selection_id") == str(item.selection_id)
    }
    revision_rows = list(
        db.scalars(
            select(DispositionOfferRevision)
            .where(
                DispositionOfferRevision.organization_id == principal.organization_id,
                DispositionOfferRevision.disposition_case_id == case.id,
            )
            .order_by(
                DispositionOfferRevision.created_at.desc(),
                DispositionOfferRevision.revision_number.desc(),
            )
        ).all()
    )
    prior_retrades: dict[UUID, int] = {}
    for item in outcome_rows:
        if item.outcome_type == "retrade":
            prior_retrades[item.buyer_id] = prior_retrades.get(item.buyer_id, 0) + 1
    now = datetime.now(UTC)
    max_amount = max((item.amount_cents for item in offers), default=1)
    live_coverage_by_offer = {
        offer.id: _coverage_snapshot(db, principal, case, offer) for offer in offers
    }
    evaluated: list[tuple[BuyerOffer, int, list[dict[str, Any]], list[str], int, list[str]]] = []
    for offer in offers:
        buyer = buyers[offer.buyer_id]
        risk, flags, strengths, score, blockers = _risk_and_score(
            offer,
            buyer,
            proofs.get(offer.proof_document_id),
            now=now,
            max_amount_cents=max_amount,
            prior_retrades=prior_retrades.get(offer.buyer_id, 0),
        )
        blockers = list(
            dict.fromkeys(
                [
                    *blockers,
                    *live_coverage_by_offer[offer.id]["readiness_blockers"],
                ]
            )
        )
        evaluated.append((offer, risk, flags, strengths, score, blockers))
    viable = [item for item in evaluated if item[0].status in VIABLE_OFFER_STATUSES]
    ranked = sorted(
        viable, key=lambda item: (-item[4], item[1], -item[0].amount_cents, str(item[0].id))
    )
    rank_by_id = {item[0].id: rank for rank, item in enumerate(ranked, 1)}
    recommended_id = ranked[0][0].id if ranked else None

    selection_rows = list(
        db.scalars(
            select(DispositionBuyerSelection)
            .where(
                DispositionBuyerSelection.organization_id == principal.organization_id,
                DispositionBuyerSelection.disposition_case_id == case.id,
            )
            .order_by(DispositionBuyerSelection.approved_at.desc())
        ).all()
    )
    selection_ids = [item.id for item in selection_rows]
    slots_by_selection: dict[UUID, list[DispositionBuyerSelectionSlot]] = {}
    if selection_ids:
        for slot in db.scalars(
            select(DispositionBuyerSelectionSlot).where(
                DispositionBuyerSelectionSlot.selection_id.in_(selection_ids)
            )
        ).all():
            slots_by_selection.setdefault(slot.selection_id, []).append(slot)
    active_selection = next((item for item in selection_rows if item.status == "active"), None)
    active_primary_slot = next(
        (
            slot
            for slot in slots_by_selection.get(active_selection.id, [])
            if slot.role == "primary"
        ),
        None,
    ) if active_selection is not None else None
    completed_assignment_close = bool(
        case.strategy == "assignment"
        and active_selection is not None
        and active_primary_slot is not None
        and (active_selection.id, active_primary_slot.offer_id) in completed_close_keys
    )
    assignment_execution_verified = bool(
        case.strategy == "assignment"
        and transaction is not None
        and (
            completed_assignment_close
            or has_current_executed_assignment_agreement(db, transaction)
        )
    )
    selection_reads = [
        _selection_read(
            item,
            slots_by_selection.get(item.id, []),
            buyers,
            {offer.id: offer for offer in offers},
            live_coverage_by_offer,
            completed_close_keys,
        )
        for item in selection_rows
    ]
    current_selection = next((item for item in selection_reads if item.status == "active"), None)

    negotiation_rows = list(
        db.scalars(
            select(DispositionOfferNegotiationEvent)
            .where(
                DispositionOfferNegotiationEvent.organization_id == principal.organization_id,
                DispositionOfferNegotiationEvent.disposition_case_id == case.id,
            )
            .order_by(DispositionOfferNegotiationEvent.occurred_at.desc())
        ).all()
    )
    alert_rows = list(
        db.scalars(
            select(DispositionDeadlineAlert)
            .where(
                DispositionDeadlineAlert.organization_id == principal.organization_id,
                DispositionDeadlineAlert.disposition_case_id == case.id,
                DispositionDeadlineAlert.status.in_(("open", "acknowledged")),
            )
            .order_by(DispositionDeadlineAlert.due_at)
        ).all()
    )
    alert_reads = {
        item.id: DeadlineAlertRead(
            id=item.id,
            checkpoint_id=item.checkpoint_id,
            status=item.status,
            severity=item.severity,
            title="Closing checkpoint missed",
            message=f"A buyer-closing checkpoint was due {item.due_at.isoformat()}.",
            due_at=item.due_at,
            deadline_version=item.deadline_version,
            acknowledged_by_user_id=item.acknowledged_by_user_id,
            acknowledged_at=item.acknowledged_at,
            resolved_at=item.resolved_at,
        )
        for item in alert_rows
    }
    active_alert_by_checkpoint = {
        item.checkpoint_id: alert_reads[item.id]
        for item in alert_rows
        if item.status in {"open", "acknowledged"}
    }
    checkpoint_rows = list(
        db.scalars(
            select(DispositionClosingCheckpoint)
            .where(
                DispositionClosingCheckpoint.organization_id == principal.organization_id,
                DispositionClosingCheckpoint.disposition_case_id == case.id,
            )
            .order_by(DispositionClosingCheckpoint.due_at)
        ).all()
    )

    offer_reads = [
        OfferRoomOfferRead(
            id=offer.id,
            buyer_id=offer.buyer_id,
            buyer_name=buyers[offer.buyer_id].name,
            amount_cents=offer.amount_cents,
            earnest_money_cents=offer.earnest_money_cents,
            deposit_due_at=offer.deposit_due_at,
            due_diligence_days=offer.due_diligence_days,
            contingencies=list(offer.contingencies or []),
            contingencies_confirmed=offer.contingencies_confirmed,
            proposed_closing_at=offer.proposed_closing_at,
            funding_method=offer.financing_type,
            funding_confidence_basis_points=offer.funding_confidence_basis_points,
            reliability_score_basis_points=buyers[offer.buyer_id].reliability_score_basis_points,
            reliability_evidence=[
                f"{buyers[offer.buyer_id].completed_deals} completed deal(s)",
                f"{buyers[offer.buyer_id].failed_deals} buyer-responsible failed deal(s)",
                f"{prior_retrades.get(offer.buyer_id, 0)} recorded retrade(s)",
            ],
            proof_document_id=offer.proof_document_id,
            proof_status=(
                proofs[offer.proof_document_id].status
                if offer.proof_document_id in proofs
                else "missing"
            ),
            proof_verified_amount_cents=(
                proofs[offer.proof_document_id].verified_amount_cents
                if offer.proof_document_id in proofs
                else None
            ),
            proof_expires_at=(
                proofs[offer.proof_document_id].expires_at
                if offer.proof_document_id in proofs
                else None
            ),
            special_terms=offer.special_terms,
            notes=offer.notes,
            status=offer.status,
            lock_version=offer.lock_version,
            received_at=offer.received_at,
            updated_at=offer.updated_at,
            risk_score_basis_points=risk,
            risk_flags=[OfferRiskFlagRead(**item) for item in flags],
            strengths=strengths,
            execution_score_basis_points=score,
            comparison_rank=rank_by_id.get(offer.id, len(offers) + 1),
            is_recommended=offer.id == recommended_id,
        )
        for offer, risk, flags, strengths, score, _ in sorted(
            evaluated,
            key=lambda item: (rank_by_id.get(item[0].id, len(offers) + 1), str(item[0].id)),
        )
    ]
    evaluated_by_id = {item[0].id: item for item in evaluated}
    backup_rank_by_offer = {
        slot.offer_id: slot.rank
        for selection in selection_rows
        if selection.status == "active"
        for slot in slots_by_selection.get(selection.id, [])
        if slot.role == "backup"
    }
    active_backup_slot_by_offer = {
        slot.offer_id: slot
        for selection in selection_rows
        if selection.status == "active"
        for slot in slots_by_selection.get(selection.id, [])
        if slot.role == "backup"
    }
    replacement_evaluated = []
    for offer, risk, flags, strengths, score, blockers in evaluated_by_id.values():
        replacement_blockers = list(blockers)
        approved_slot = active_backup_slot_by_offer.get(offer.id)
        if (
            approved_slot is not None
            and int(approved_slot.offer_snapshot.get("lock_version", 0)) != offer.lock_version
        ):
            replacement_blockers.append(
                "Approved backup terms changed; manager reapproval is required."
            )
        replacement_evaluated.append(
            (offer, risk, flags, strengths, score, list(dict.fromkeys(replacement_blockers)))
        )
    replacement_options = [
        ReplacementOptionRead(
            offer_id=offer.id,
            buyer_id=offer.buyer_id,
            buyer_name=buyers[offer.buyer_id].name,
            backup_rank=backup_rank_by_offer.get(offer.id),
            comparison_rank=rank_by_id.get(offer.id, len(offers) + 1),
            amount_cents=offer.amount_cents,
            execution_score_basis_points=score,
            risk_score_basis_points=risk,
            eligible=not blockers and offer.status in VIABLE_OFFER_STATUSES,
            blockers=blockers,
        )
        for offer, risk, _, _, score, blockers in sorted(
            replacement_evaluated,
            key=lambda item: (
                backup_rank_by_offer.get(item[0].id, 999),
                rank_by_id.get(item[0].id, 999),
            ),
        )
        if offer.id in backup_rank_by_offer
    ]
    return OfferRoomRead(
        case_id=case.id,
        case_status=case.status,
        disposition_strategy=case.strategy,
        assignment_execution_verified=assignment_execution_verified,
        strategy_agreement=_strategy_agreement_readiness(
            case,
            assignment_execution_verified=assignment_execution_verified,
        ),
        generated_at=now,
        offers=offer_reads,
        revision_history=[
            OfferRevisionRead(
                id=item.id,
                offer_id=item.offer_id,
                buyer_id=item.buyer_id,
                actor_user_id=item.created_by_user_id,
                revision_number=item.revision_number,
                terms_snapshot=item.terms_snapshot,
                risk_snapshot=item.risk_snapshot,
                change_reason=item.change_reason,
                created_at=item.created_at,
            )
            for item in revision_rows
        ],
        current_selection=current_selection,
        selection_history=selection_reads,
        negotiation_history=[
            NegotiationEventRead(
                id=item.id,
                offer_id=item.offer_id,
                buyer_id=item.buyer_id,
                buyer_name=buyers[item.buyer_id].name,
                actor_user_id=item.actor_user_id,
                event_type=item.event_type,
                direction=item.direction,
                summary=item.summary,
                metadata=item.metadata_snapshot,
                occurred_at=item.occurred_at,
            )
            for item in negotiation_rows
        ],
        checkpoints=[
            ClosingCheckpointRead(
                id=item.id,
                selection_id=item.selection_id,
                offer_id=item.offer_id,
                buyer_id=item.buyer_id,
                buyer_name=(buyers[item.buyer_id].name if item.buyer_id in buyers else None),
                checkpoint_type=item.checkpoint_type,
                label=item.label,
                canonical_source=item.canonical_source,
                source_record_id=item.source_record_id,
                due_at=item.due_at,
                status=item.status,
                lock_version=item.lock_version,
                deadline_version=item.deadline_version,
                responsible_user_id=item.responsible_user_id,
                completed_at=item.completed_at,
                notes=item.notes,
                evidence=item.evidence_snapshot,
                is_overdue=(
                    item.status not in TERMINAL_CHECKPOINT_STATUSES and _aware(item.due_at) < now
                ),
                active_alert=active_alert_by_checkpoint.get(item.id),
            )
            for item in checkpoint_rows
        ],
        alerts=list(alert_reads.values()),
        replacement_options=replacement_options,
        outcomes=[
            BuyerOutcomeRead(
                id=item.id,
                selection_id=item.selection_id,
                offer_id=item.offer_id,
                buyer_id=item.buyer_id,
                buyer_name=buyers[item.buyer_id].name,
                outcome_type=item.outcome_type,
                cause_category=item.cause_category,
                reason=item.reason,
                details=item.details,
                evidence=item.evidence_snapshot,
                occurred_at=item.occurred_at,
                completed_delta=item.completed_delta,
                failed_delta=item.failed_delta,
                reliability_delta_basis_points=item.reliability_delta_basis_points,
            )
            for item in outcome_rows
        ],
    )
