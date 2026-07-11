from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.auth import Principal
from app.models.foundation import ActivityEvent, AuditEvent, Contact, Deal, Lead, Property, User
from app.schemas.leads import DashboardSummary, LeadCreate, LeadRead, PipelineStageCount

PAID_LEAD_SOURCES = ("google_ppc", "meta_ads", "facebook_ads", "instagram_ads", "website")


def create_lead(db: Session, principal: Principal, payload: LeadCreate) -> LeadRead:
    contact = Contact(
        organization_id=principal.organization_id,
        legal_name=payload.contact.legal_name,
        preferred_name=payload.contact.preferred_name,
        contact_type=payload.contact.contact_type,
        assigned_user_id=principal.user_id,
    )
    db.add(contact)
    db.flush()

    property_record = Property(
        organization_id=principal.organization_id,
        street_address=payload.property.street_address,
        city=payload.property.city,
        state=payload.property.state.upper(),
        postal_code=payload.property.postal_code,
        county=payload.property.county,
        property_type=payload.property.property_type,
    )
    db.add(property_record)
    db.flush()

    lead = Lead(
        organization_id=principal.organization_id,
        contact_id=contact.id,
        property_id=property_record.id,
        assigned_user_id=principal.user_id,
        source=payload.source,
        stage_key=payload.stage_key,
        lead_temperature=payload.lead_temperature,
    )
    db.add(lead)
    db.flush()

    db.add(
        ActivityEvent(
            organization_id=principal.organization_id,
            actor_user_id=principal.user_id,
            entity_type="lead",
            entity_id=lead.id,
            event_type="lead.created",
            summary=f"Lead created for {contact.legal_name}.",
        )
    )
    db.add(
        AuditEvent(
            organization_id=principal.organization_id,
            actor_user_id=principal.user_id,
            actor_type="user",
            action="lead.create",
            entity_type="lead",
            entity_id=lead.id,
            previous_value=None,
            new_value={"source": lead.source, "stage_key": lead.stage_key},
            reason="Manual local lead creation",
        )
    )
    db.commit()
    db.refresh(lead)
    return lead_to_read(db, lead)


def list_leads(db: Session, principal: Principal, limit: int = 25) -> list[LeadRead]:
    leads = db.scalars(
        select(Lead)
        .where(Lead.organization_id == principal.organization_id)
        .order_by(Lead.created_at.desc())
        .limit(limit)
    ).all()
    return [lead_to_read(db, lead) for lead in leads]


def get_dashboard_summary(db: Session, principal: Principal) -> DashboardSummary:
    total_leads = count_scalar(db, select(func.count(Lead.id)).where(
        Lead.organization_id == principal.organization_id
    ))
    new_paid_leads = count_scalar(db, select(func.count(Lead.id)).where(
        Lead.organization_id == principal.organization_id,
        Lead.stage_key == "new",
        Lead.source.in_(PAID_LEAD_SOURCES),
    ))
    active_contracts = count_scalar(db, select(func.count(Deal.id)).where(
        Deal.organization_id == principal.organization_id,
        Deal.stage_key == "under_contract",
    ))
    collected_revenue_cents = int(
        db.scalar(
            select(func.coalesce(func.sum(Deal.assignment_fee_cents), 0)).where(
                Deal.organization_id == principal.organization_id,
                Deal.stage_key == "closed",
            )
        )
        or 0
    )
    pipeline_rows = db.execute(
        select(Lead.stage_key, func.count(Lead.id))
        .where(Lead.organization_id == principal.organization_id)
        .group_by(Lead.stage_key)
        .order_by(Lead.stage_key)
    ).all()

    return DashboardSummary(
        total_leads=total_leads,
        new_paid_leads=new_paid_leads,
        active_contracts=active_contracts,
        offers_pending=0,
        collected_revenue_cents=collected_revenue_cents,
        pipeline=[
            PipelineStageCount(stage_key=str(stage_key), count=int(count))
            for stage_key, count in pipeline_rows
        ],
    )


def count_scalar(db: Session, statement: Any) -> int:
    return int(db.scalar(statement) or 0)


def lead_to_read(db: Session, lead: Lead) -> LeadRead:
    contact = db.get(Contact, lead.contact_id)
    property_record = db.get(Property, lead.property_id)
    assigned_user = db.get(User, lead.assigned_user_id) if lead.assigned_user_id else None
    if contact is None or property_record is None:
        raise RuntimeError("lead is missing required contact or property")

    return LeadRead(
        id=lead.id,
        contact_id=lead.contact_id,
        property_id=lead.property_id,
        source=lead.source,
        stage_key=lead.stage_key,
        lead_temperature=lead.lead_temperature,
        seller_name=contact.legal_name,
        property_address=(
            f"{property_record.street_address}, {property_record.city}, "
            f"{property_record.state} {property_record.postal_code}"
        ),
        assigned_user_email=assigned_user.email if assigned_user else None,
        created_at=lead.created_at,
    )
