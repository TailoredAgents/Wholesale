from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.auth import Principal
from app.models.foundation import ActivityEvent, AuditEvent, Lead, RepairEstimate
from app.schemas.leads import (
    RepairEstimateCreate,
    RepairEstimateItemInput,
    RepairEstimateRead,
)


def list_repair_estimates(
    db: Session,
    principal: Principal,
    lead_id: UUID,
) -> list[RepairEstimateRead] | None:
    lead = scoped_lead(db, principal, lead_id)
    if lead is None:
        return None
    estimates = db.scalars(
        select(RepairEstimate)
        .where(
            RepairEstimate.organization_id == principal.organization_id,
            RepairEstimate.lead_id == lead.id,
        )
        .order_by(RepairEstimate.estimate_date.desc(), RepairEstimate.created_at.desc())
    ).all()
    return [repair_estimate_to_read(estimate) for estimate in estimates]


def create_repair_estimate(
    db: Session,
    principal: Principal,
    lead_id: UUID,
    payload: RepairEstimateCreate,
) -> RepairEstimateRead | None:
    lead = scoped_lead(db, principal, lead_id)
    if lead is None:
        return None
    if payload.source_type == "contractor_bid" and not (
        payload.contractor_name and payload.contractor_name.strip()
    ):
        raise ValueError("Contractor name is required for a contractor bid.")

    scope_items = []
    for item in payload.scope_items:
        if (
            item.labor_cost_cents is not None
            and item.material_cost_cents is not None
            and item.labor_cost_cents + item.material_cost_cents
            != item.estimated_cost_cents
        ):
            raise ValueError(
                "Labor and material costs must add up to the work-item estimate."
            )
        scope_items.append(item.model_dump(mode="json"))

    subtotal_cents = sum(item.estimated_cost_cents for item in payload.scope_items)
    contingency_cents = round(subtotal_cents * payload.contingency_percentage / 100)
    estimate = RepairEstimate(
        organization_id=principal.organization_id,
        lead_id=lead.id,
        property_id=lead.property_id,
        created_by_user_id=principal.user_id,
        source_type=payload.source_type,
        contractor_name=(
            payload.contractor_name.strip() if payload.contractor_name else None
        ),
        estimate_date=payload.estimate_date,
        scope_items=scope_items,
        subtotal_cents=subtotal_cents,
        contingency_percentage=payload.contingency_percentage,
        contingency_cents=contingency_cents,
        total_cents=subtotal_cents + contingency_cents,
        evidence_reference=payload.evidence_reference,
        notes=payload.notes,
    )
    db.add(estimate)
    db.flush()
    db.add(
        ActivityEvent(
            organization_id=principal.organization_id,
            actor_user_id=principal.user_id,
            entity_type="lead",
            entity_id=lead.id,
            event_type="underwriting.repair_estimate.create",
            summary=(
                f"{payload.source_type.replace('_', ' ').title()} recorded at "
                f"${estimate.total_cents / 100:,.0f} including contingency."
            ),
        )
    )
    db.add(
        AuditEvent(
            organization_id=principal.organization_id,
            actor_user_id=principal.user_id,
            actor_type="user",
            action="underwriting.repair_estimate.create",
            entity_type="repair_estimate",
            entity_id=estimate.id,
            previous_value=None,
            new_value=repair_estimate_audit_value(estimate),
            reason="Repair scope evidence recorded",
        )
    )
    db.commit()
    db.refresh(estimate)
    return repair_estimate_to_read(estimate)


def get_repair_estimate(
    db: Session,
    principal: Principal,
    lead_id: UUID,
    estimate_id: UUID,
) -> RepairEstimate | None:
    return db.scalar(
        select(RepairEstimate).where(
            RepairEstimate.id == estimate_id,
            RepairEstimate.organization_id == principal.organization_id,
            RepairEstimate.lead_id == lead_id,
        )
    )


def scoped_lead(db: Session, principal: Principal, lead_id: UUID) -> Lead | None:
    return db.scalar(
        select(Lead).where(
            Lead.id == lead_id,
            Lead.organization_id == principal.organization_id,
        )
    )


def repair_estimate_to_read(estimate: RepairEstimate) -> RepairEstimateRead:
    return RepairEstimateRead(
        id=estimate.id,
        lead_id=estimate.lead_id,
        property_id=estimate.property_id,
        source_type=estimate.source_type,
        contractor_name=estimate.contractor_name,
        estimate_date=estimate.estimate_date,
        scope_items=[
            RepairEstimateItemInput.model_validate(item) for item in estimate.scope_items
        ],
        subtotal_cents=estimate.subtotal_cents,
        contingency_percentage=estimate.contingency_percentage,
        contingency_cents=estimate.contingency_cents,
        total_cents=estimate.total_cents,
        evidence_reference=estimate.evidence_reference,
        notes=estimate.notes,
        created_by_user_id=estimate.created_by_user_id,
        created_at=estimate.created_at,
    )


def repair_estimate_audit_value(estimate: RepairEstimate) -> dict[str, object]:
    return {
        "lead_id": str(estimate.lead_id),
        "property_id": str(estimate.property_id),
        "source_type": estimate.source_type,
        "contractor_name": estimate.contractor_name,
        "estimate_date": estimate.estimate_date.isoformat(),
        "scope_items": estimate.scope_items,
        "subtotal_cents": estimate.subtotal_cents,
        "contingency_percentage": estimate.contingency_percentage,
        "contingency_cents": estimate.contingency_cents,
        "total_cents": estimate.total_cents,
        "evidence_reference": estimate.evidence_reference,
        "notes": estimate.notes,
    }
