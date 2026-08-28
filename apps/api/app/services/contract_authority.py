from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.foundation import (
    ApprovalRequest,
    ContractPackage,
    OfferConcession,
    OfferNegotiationEvent,
    OfferNegotiationPlan,
    Transaction,
    UnderwritingVersion,
)
from app.services.offer_concessions import latest_approved_plan

PURCHASE_AGREEMENT = "purchase_agreement"
PURCHASE_AUTHORITY_SNAPSHOT_KEY = "purchase_authority"
PURCHASE_AUTHORITY_SCHEMA_VERSION = 1
VALID_CONCESSION_STATUSES = {"authorized", "approved", "presented"}
ACCEPTABLE_EXECUTION_SCAN_STATUSES = {"clean", "not_configured"}

AUTHORITY_SOURCE_KEYS = (
    "schema_version",
    "offer_negotiation_plan_id",
    "offer_plan_approval_request_id",
    "underwriting_version_id",
    "underwriting_version_number",
    "price_source",
    "agreement_event_id",
    "purchase_price_cents",
    "transaction_purchase_price_cents",
    "opening_offer_cents",
    "target_contract_cents",
    "stretch_contract_cents",
    "seller_ceiling_cents",
    "governing_concession_id",
    "concession_approval_request_id",
)


def package_document_type(package: ContractPackage) -> str:
    snapshot = package.terms_snapshot if isinstance(package.terms_snapshot, dict) else {}
    return str(snapshot.get("document_type") or PURCHASE_AGREEMENT)


def package_purchase_authority_snapshot(package: ContractPackage) -> dict[str, Any] | None:
    snapshot = package.terms_snapshot if isinstance(package.terms_snapshot, dict) else {}
    authority = snapshot.get(PURCHASE_AUTHORITY_SNAPSHOT_KEY)
    return dict(authority) if isinstance(authority, dict) else None


def capture_purchase_authority(
    db: Session,
    transaction: Transaction,
    purchase_price_cents: int,
) -> dict[str, Any]:
    plan = latest_approved_plan(db, transaction.organization_id, transaction.lead_id)
    if plan is None:
        raise ValueError(
            "A current approved offer plan is required before drafting a purchase agreement."
        )
    if plan.property_id != transaction.property_id:
        raise ValueError("The current offer plan does not match this transaction property.")

    approval = (
        db.get(ApprovalRequest, plan.approval_request_id)
        if plan.approval_request_id is not None
        else None
    )
    if (
        approval is None
        or approval.status != "approved"
        or approval.request_type not in {"offer_ceiling", "seller_offer"}
        or approval.entity_type != "offer_negotiation_plan"
        or approval.entity_id != plan.id
    ):
        raise ValueError("The current offer plan no longer has an approved decision.")
    version = db.get(UnderwritingVersion, plan.underwriting_version_id)
    if (
        version is None
        or version.organization_id != transaction.organization_id
        or version.lead_id != transaction.lead_id
        or version.property_id != transaction.property_id
        or version.status != "approved"
    ):
        raise ValueError("The approved offer plan's underwriting version is unavailable.")

    agreement = latest_seller_agreement(db, plan)
    current_price = (
        int(agreement.amount_cents)
        if agreement is not None and agreement.amount_cents is not None
        else transaction.purchase_price_cents
    )
    price_source = "seller_agreement" if agreement is not None else "transaction_current"
    if agreement is not None and transaction.purchase_price_cents != current_price:
        raise ValueError(
            "The transaction purchase price does not match the latest seller-accepted price."
        )
    if purchase_price_cents != current_price:
        raise ValueError(
            "The purchase agreement price must match the latest seller-accepted/current "
            "transaction purchase price."
        )

    concession, concession_approval = validate_price_authority(
        db,
        plan,
        current_price,
        agreement,
    )
    return {
        "schema_version": PURCHASE_AUTHORITY_SCHEMA_VERSION,
        "captured_at": datetime.now(UTC).isoformat(),
        "offer_negotiation_plan_id": str(plan.id),
        "offer_plan_approval_request_id": str(approval.id),
        "offer_plan_approved_at": (
            approval.decided_at.isoformat() if approval.decided_at is not None else None
        ),
        "underwriting_version_id": str(version.id),
        "underwriting_version_number": version.version_number,
        "price_source": price_source,
        "agreement_event_id": str(agreement.id) if agreement is not None else None,
        "purchase_price_cents": current_price,
        "transaction_purchase_price_cents": transaction.purchase_price_cents,
        "opening_offer_cents": plan.opening_offer_cents,
        "target_contract_cents": plan.target_contract_cents,
        "stretch_contract_cents": plan.stretch_contract_cents,
        "seller_ceiling_cents": plan.seller_ceiling_cents,
        "governing_concession_id": str(concession.id) if concession is not None else None,
        "governing_concession_status": concession.status if concession is not None else None,
        "concession_approval_request_id": (
            str(concession_approval.id) if concession_approval is not None else None
        ),
        "concession_approved_at": (
            concession_approval.decided_at.isoformat()
            if concession_approval is not None and concession_approval.decided_at is not None
            else None
        ),
    }


def validate_purchase_contract_authority(
    db: Session,
    transaction: Transaction,
    package: ContractPackage,
    *,
    gate: str,
) -> dict[str, Any] | None:
    if package_document_type(package) != PURCHASE_AGREEMENT:
        return None
    snapshot = package_purchase_authority_snapshot(package)
    if snapshot is None:
        raise ValueError(
            "This legacy purchase agreement has no offer-authority snapshot. "
            f"Create a new package before {gate}."
        )
    if snapshot.get("schema_version") != PURCHASE_AUTHORITY_SCHEMA_VERSION:
        raise ValueError(
            "This purchase agreement uses an unsupported offer-authority snapshot. "
            f"Create a new package before {gate}."
        )
    try:
        current = capture_purchase_authority(db, transaction, package.purchase_price_cents)
    except ValueError as exc:
        raise ValueError(
            f"The purchase agreement's offer authority is stale before {gate}: {exc} "
            "Create and approve a new package."
        ) from exc
    changed = [key for key in AUTHORITY_SOURCE_KEYS if snapshot.get(key) != current.get(key)]
    if changed:
        raise ValueError(
            "The purchase agreement's approved authority or source version changed before "
            f"{gate} ({', '.join(changed)}). Create and approve a new package."
        )
    return snapshot


def validate_contract_package_authority(
    db: Session,
    transaction: Transaction,
    package: ContractPackage,
    *,
    gate: str,
    lock_assignment: bool = False,
) -> dict[str, Any] | None:
    """Validate the current governed authority for either seller or buyer contracts."""
    document_type = package_document_type(package)
    if document_type == "assignment_contract":
        from app.services.disposition_offer_room import (
            validate_assignment_package_authority,
        )

        return validate_assignment_package_authority(
            db,
            transaction,
            package,
            gate=gate,
            lock=lock_assignment,
        )
    return validate_purchase_contract_authority(
        db,
        transaction,
        package,
        gate=gate,
    )


def latest_seller_agreement(
    db: Session,
    plan: OfferNegotiationPlan,
) -> OfferNegotiationEvent | None:
    return db.scalar(
        select(OfferNegotiationEvent)
        .where(
            OfferNegotiationEvent.organization_id == plan.organization_id,
            OfferNegotiationEvent.lead_id == plan.lead_id,
            OfferNegotiationEvent.property_id == plan.property_id,
            OfferNegotiationEvent.offer_negotiation_plan_id == plan.id,
            OfferNegotiationEvent.event_type == "agreement",
            OfferNegotiationEvent.amount_cents.is_not(None),
        )
        .order_by(
            OfferNegotiationEvent.occurred_at.desc(),
            OfferNegotiationEvent.created_at.desc(),
            OfferNegotiationEvent.id.desc(),
        )
        .limit(1)
    )


def validate_price_authority(
    db: Session,
    plan: OfferNegotiationPlan,
    amount_cents: int,
    agreement: OfferNegotiationEvent | None,
) -> tuple[OfferConcession | None, ApprovalRequest | None]:
    concession: OfferConcession | None = None
    if agreement is not None and agreement.concession_id is not None:
        concession = db.get(OfferConcession, agreement.concession_id)
    elif amount_cents > plan.opening_offer_cents:
        concession = db.scalar(
            select(OfferConcession)
            .where(
                OfferConcession.organization_id == plan.organization_id,
                OfferConcession.lead_id == plan.lead_id,
                OfferConcession.property_id == plan.property_id,
                OfferConcession.offer_negotiation_plan_id == plan.id,
                OfferConcession.underwriting_version_id == plan.underwriting_version_id,
                OfferConcession.proposed_offer_cents == amount_cents,
                OfferConcession.status.in_(VALID_CONCESSION_STATUSES),
            )
            .order_by(OfferConcession.created_at.desc(), OfferConcession.id.desc())
            .limit(1)
        )

    if concession is not None and (
        concession.offer_negotiation_plan_id != plan.id
        or concession.underwriting_version_id != plan.underwriting_version_id
        or concession.proposed_offer_cents != amount_cents
        or concession.status not in VALID_CONCESSION_STATUSES
    ):
        concession = None

    concession_approval = (
        db.get(ApprovalRequest, concession.approval_request_id)
        if concession is not None and concession.approval_request_id is not None
        else None
    )
    manager_approval_required = amount_cents > plan.seller_ceiling_cents or (
        concession is not None and concession.authority_basis == "manager_exception"
    )
    if manager_approval_required and (
        concession is None
        or concession.status not in {"approved", "presented"}
        or concession_approval is None
        or concession_approval.status != "approved"
        or concession_approval.request_type != "offer_concession"
        or concession_approval.entity_type != "offer_concession"
        or concession_approval.entity_id != concession.id
    ):
        raise ValueError(
            "The current purchase price exceeds the approved seller ceiling without an exact "
            "manager-approved concession."
        )
    if amount_cents > plan.opening_offer_cents and concession is None:
        raise ValueError(
            "The current purchase price exceeds opening authority without an exact authorized "
            "concession."
        )
    return concession, concession_approval
