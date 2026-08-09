from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.foundation import ContractPackage, Transaction


def lock_offer_authority_for_mutation(
    db: Session,
    organization_id: UUID,
    lead_id: UUID,
) -> None:
    """Serialize authority changes with contract delivery and reject post-reservation drift."""
    transactions = list(
        db.scalars(
            select(Transaction)
            .where(
                Transaction.organization_id == organization_id,
                Transaction.lead_id == lead_id,
            )
            .order_by(Transaction.created_at, Transaction.id)
            .with_for_update(of=Transaction)
        )
    )
    if not transactions:
        return
    packages = list(
        db.scalars(
            select(ContractPackage).where(
                ContractPackage.organization_id == organization_id,
                ContractPackage.transaction_id.in_([item.id for item in transactions]),
                ContractPackage.status.in_(("sending", "sent")),
            )
        )
    )
    frozen = next(
        (
            item
            for item in packages
            if str(item.terms_snapshot.get("document_type") or "purchase_agreement")
            == "purchase_agreement"
        ),
        None,
    )
    if frozen is not None:
        raise ValueError(
            "Offer authority is temporarily frozen while a purchase agreement is being "
            "delivered or remains open for signature. Reconcile, cancel, or finish that "
            "signature request before recording new seller authority."
        )
