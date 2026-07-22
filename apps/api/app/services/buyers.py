from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.auth import Principal
from app.models.foundation import ActivityEvent, AuditEvent, Buyer, BuyerCriteria
from app.schemas.buyers import BuyerCreate, BuyerCriteriaRead, BuyerRead

BUYER_TYPES = {"cash_buyer", "landlord", "flipper", "builder", "hedge_fund", "agent"}
BUYER_STATUSES = {"active", "paused", "inactive"}
PROOF_OF_FUNDS_STATUSES = {"unknown", "requested", "received", "expired", "rejected"}


def list_buyers(db: Session, principal: Principal, limit: int = 100) -> list[BuyerRead]:
    buyers = db.scalars(
        select(Buyer)
        .where(Buyer.organization_id == principal.organization_id)
        .order_by(Buyer.created_at.desc())
        .limit(limit)
    ).all()
    criteria_by_buyer = get_criteria_by_buyer_id(db, principal, [buyer.id for buyer in buyers])
    return [buyer_to_read(buyer, criteria_by_buyer.get(buyer.id)) for buyer in buyers]


def create_buyer(db: Session, principal: Principal, payload: BuyerCreate) -> BuyerRead:
    validate_buyer_payload(payload)
    buyer = Buyer(
        organization_id=principal.organization_id,
        name=payload.name,
        company_name=payload.company_name,
        email=payload.email,
        phone=payload.phone,
        buyer_type=payload.buyer_type,
        status=payload.status,
        proof_of_funds_status=payload.proof_of_funds_status,
        max_purchase_price_cents=payload.max_purchase_price_cents,
        notes=payload.notes,
    )
    db.add(buyer)
    db.flush()
    criteria = None
    if payload.criteria is not None:
        if (
            payload.criteria.min_price_cents is not None
            and payload.criteria.max_price_cents is not None
            and payload.criteria.min_price_cents > payload.criteria.max_price_cents
        ):
            raise ValueError("Buyer minimum price cannot exceed maximum price.")
        criteria = BuyerCriteria(
            organization_id=principal.organization_id,
            buyer_id=buyer.id,
            markets=payload.criteria.markets,
            property_types=payload.criteria.property_types,
            min_price_cents=payload.criteria.min_price_cents,
            max_price_cents=payload.criteria.max_price_cents,
            rehab_levels=payload.criteria.rehab_levels,
            notes=payload.criteria.notes,
        )
        db.add(criteria)
    db.add(
        ActivityEvent(
            organization_id=principal.organization_id,
            actor_user_id=principal.user_id,
            entity_type="buyer",
            entity_id=buyer.id,
            event_type="buyer.created",
            summary=f"Buyer created: {buyer.name}.",
        )
    )
    db.add(
        AuditEvent(
            organization_id=principal.organization_id,
            actor_user_id=principal.user_id,
            actor_type="user",
            action="buyer.create",
            entity_type="buyer",
            entity_id=buyer.id,
            previous_value=None,
            new_value={
                "name": buyer.name,
                "buyer_type": buyer.buyer_type,
                "status": buyer.status,
                "proof_of_funds_status": buyer.proof_of_funds_status,
                "max_purchase_price_cents": buyer.max_purchase_price_cents,
            },
            reason="Manual buyer creation",
        )
    )
    db.commit()
    db.refresh(buyer)
    if criteria is not None:
        db.refresh(criteria)
    return buyer_to_read(buyer, criteria)


def validate_buyer_payload(payload: BuyerCreate) -> None:
    if payload.buyer_type not in BUYER_TYPES:
        raise ValueError(f"Unsupported buyer type: {payload.buyer_type}")
    if payload.status not in BUYER_STATUSES:
        raise ValueError(f"Unsupported buyer status: {payload.status}")
    if payload.proof_of_funds_status not in PROOF_OF_FUNDS_STATUSES:
        raise ValueError(f"Unsupported proof of funds status: {payload.proof_of_funds_status}")


def get_criteria_by_buyer_id(
    db: Session,
    principal: Principal,
    buyer_ids: list[object],
) -> dict[object, BuyerCriteria]:
    if not buyer_ids:
        return {}
    criteria_rows = db.scalars(
        select(BuyerCriteria)
        .where(
            BuyerCriteria.organization_id == principal.organization_id,
            BuyerCriteria.buyer_id.in_(buyer_ids),
        )
        .order_by(BuyerCriteria.created_at.desc())
    ).all()
    criteria_by_buyer: dict[object, BuyerCriteria] = {}
    for criteria in criteria_rows:
        criteria_by_buyer.setdefault(criteria.buyer_id, criteria)
    return criteria_by_buyer


def buyer_to_read(buyer: Buyer, criteria: BuyerCriteria | None) -> BuyerRead:
    return BuyerRead(
        id=buyer.id,
        name=buyer.name,
        company_name=buyer.company_name,
        email=buyer.email,
        phone=buyer.phone,
        buyer_type=buyer.buyer_type,
        status=buyer.status,
        proof_of_funds_status=buyer.proof_of_funds_status,
        max_purchase_price_cents=buyer.max_purchase_price_cents,
        reliability_score_basis_points=buyer.reliability_score_basis_points,
        completed_deals=buyer.completed_deals,
        failed_deals=buyer.failed_deals,
        proof_of_funds_expires_at=buyer.proof_of_funds_expires_at,
        notes=buyer.notes,
        criteria=BuyerCriteriaRead(
            markets=criteria.markets,
            property_types=criteria.property_types,
            min_price_cents=criteria.min_price_cents,
            max_price_cents=criteria.max_price_cents,
            rehab_levels=criteria.rehab_levels,
            notes=criteria.notes,
        )
        if criteria
        else None,
        created_at=buyer.created_at,
    )
